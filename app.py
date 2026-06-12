import os
import sqlite3
import time
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
import tempfile

from flask import Flask, request, jsonify, send_file, render_template, session
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import generate_password_hash, check_password_hash

from embroidery import (
    get_image,
    image_to_embroidery_canny,
    pattern_has_stitches,
    pattern_path_metrics,
    pattern_to_data_url,
    photo_to_raster_embroidery,
)

#创建一个网站应用，名字是地址。防止伪造登录，加上防伪签名
#项目的路径。获得系统数据地址。数据库的位置。备用数据库地址
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
PROJECT_ROOT = Path(__file__).resolve().parent 
LOCAL_APPDATA_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
DEFAULT_DB_DIR = LOCAL_APPDATA_DIR / 'EmbroideryDesign'
PROJECT_DB_PATH = PROJECT_ROOT / 'users.db'

#检查路径能否写数据库，防御
def can_write_db_path(db_path):
    db_path = Path(db_path)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True) #尝试建文件，失败退出
    except OSError:
        return False

    if db_path.exists():#文件是否存在。存在打开，不存在返回
        try:
            with open(db_path, 'a+b'): #打开模式
                pass
        except OSError:
            return False
    else:
        try:
            with open(db_path, 'a+b'): #文件不存在，新建打开。删除刚才测试文件
                pass
            db_path.unlink()
        except OSError:
            return False

    probe_path = db_path.parent / f'.{db_path.name}.write-probe'#确保能创建新文件
    try:
        with open(probe_path, 'xb'):
            pass
        probe_path.unlink()
    except OSError:
        return False

    return True

#防御，获取数据库优先级路径。手动指定，系统的数据地址，项目文件
def resolve_db_path(configured_db_path=None, preferred_db_path=None, fallback_db_path=None):
    configured_db_path = configured_db_path or os.environ.get('DB_PATH')
    if configured_db_path:
        return Path(configured_db_path)

    preferred_db_path = Path(preferred_db_path or (DEFAULT_DB_DIR / 'users.db'))
    fallback_db_path = Path(fallback_db_path or PROJECT_DB_PATH)

    if can_write_db_path(preferred_db_path):
        return preferred_db_path

    return fallback_db_path


app.config['DB_PATH'] = str(resolve_db_path())
app.config['DB_INITIALIZED_FOR'] = None #数据路径初始化为空

#参数初始化的设置
FIXED_TARGET_WIDTH_MM = 100.0
MAX_CANNY_WORK_LONG_SIDE = 2200
DEFAULT_EMBROIDERY_MODE = 'canny'
DEFAULT_COMMON_SETTINGS = {
    'min_stitch_len_mm': 0.8,
    'max_stitch_len_mm': 6.0,
}
DEFAULT_CANNY_SETTINGS = {
    'canny_low': 80,
    'canny_high': 180,
    'canny_contrast_boost': 1.3,
    'canny_auto_thresholds': True,
    'canny_min_stitch_mm': 0.7,
}
DEFAULT_RASTER_SETTINGS = {
    'raster_row_spacing': 5,
    'raster_min_stitch': 2,
    'raster_max_stitch': 12,
    'raster_white_threshold': 210,
    'raster_contrast_boost': 1.8,
}

# Limit uploaded files to 10MB.
MAX_UPLOAD_SIZE_MB = 10
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE_MB * 1024 * 1024

ALLOWED_EXPORT_FORMATS = {'.pes', '.dst', '.jef', '.exp'}
ALLOWED_MODES = {'canny', 'raster'}

#获取数据库路径
def get_db_path():
    return Path(app.config['DB_PATH'])

#连接数据库。获得路径，连接，能用名字取值，给别人使用，最后关闭连接
@contextmanager
def get_db_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

#建用户表。如果表不存在就建表
def create_users_table(conn):
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.commit()

#初始化数据库，才能存账号。获得路径，建文件夹，连接建表
def init_db():
    db_path = get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        with get_db_connection() as conn:
            create_users_table(conn)
    except sqlite3.OperationalError:
        journal_path = Path(f"{db_path}-journal")
        if not journal_path.exists():
            raise

        recovery_path = Path(f"{journal_path}.stale")
        suffix = 1
        while recovery_path.exists(): #之前的修复文件还在，命名加一
            recovery_path = Path(f"{journal_path}.stale.{suffix}")
            suffix += 1

        rename_error = None
        for _ in range(10):#十次循环，把文件搬走成功就跳出。有错误就等待再试
            try:
                journal_path.replace(recovery_path)
                rename_error = None
                break
            except PermissionError as exc:
                rename_error = exc
                time.sleep(0.1)

        if rename_error is not None:
            raise rename_error #最后一次尝试搬走文件，如果还失败就报错

        with get_db_connection() as conn:#搬走文件成功后再连接数据库，建表
            create_users_table(conn)
    app.config['DB_INITIALIZED_FOR'] = str(db_path) #标记已经初始化

#确保数据库准备好
def ensure_db_ready():
    db_path = str(get_db_path())
    if app.config.get('DB_INITIALIZED_FOR') != db_path:
        init_db()

#获得用户信息。用户不在里面就返回，有就返回信息
def current_user_payload():
    if 'user_id' not in session:
        return None
    return {
        'id': session.get('user_id'),
        'name': session.get('user_name'),
        'email': session.get('user_email')
    }

#防御。将滑块的数值转换成正确的数字，为了后续传给后端刺绣
def parse_int(form, name, default, min_value=None, max_value=None):
    raw = form.get(name) #从表单中获得名字
    try: #上面变量为空用备用值，有值转换成数值
        value = default if raw in (None, '') else int(raw)
    except (TypeError, ValueError):
        value = default #类型错误，值错误，就用备用值
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value

#转成小数
def parse_float(form, name, default, min_value=None, max_value=None):
    raw = form.get(name)
    try:
        value = default if raw in (None, '') else float(raw)
    except (TypeError, ValueError):
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value

#转成布尔，获得字符串去掉空格变小写之后在括号里，为真。处理自动开关
def parse_bool(form, name, default=False):
    raw = form.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}

#重新翻译参数，传入表单里面是网站参数。获得模式或默认模式
#如果模式不在模式表里，抛出错误加信息不支持模式
def resolve_embroidery_settings(form):
    mode = (form.get('mode') or DEFAULT_EMBROIDERY_MODE).lower()
    if mode not in ALLOWED_MODES:
        raise ValueError('Unsupported mode')

    target_width_mm = FIXED_TARGET_WIDTH_MM
    min_stitch_len_mm = DEFAULT_COMMON_SETTINGS['min_stitch_len_mm']
    max_stitch_len_mm = DEFAULT_COMMON_SETTINGS['max_stitch_len_mm']

    #这里创建字典，键配对值，用了四舍五入保留一位小数
    settings = {
        'mode': mode,
        'target_width_mm': round(target_width_mm, 1),
        'min_stitch_len_mm': round(min_stitch_len_mm, 1),
        'max_stitch_len_mm': round(max_stitch_len_mm, 1),
    }

    if mode == 'raster':
        row_spacing = parse_int(
            form,
            'raster_row_spacing',
            DEFAULT_RASTER_SETTINGS['raster_row_spacing'],
            1,
            16,
        )
        min_stitch = parse_int(
            form,
            'raster_min_stitch',
            DEFAULT_RASTER_SETTINGS['raster_min_stitch'],
            1,
            20,
        )
        max_stitch = parse_int(
            form,
            'raster_max_stitch',
            DEFAULT_RASTER_SETTINGS['raster_max_stitch'],
            min_stitch,
            40,
        )
        if max_stitch < min_stitch:
            max_stitch = min_stitch
        white_threshold = parse_int(
            form,
            'raster_white_threshold',
            DEFAULT_RASTER_SETTINGS['raster_white_threshold'],
            120,
            250,
        )
        contrast_boost = parse_float(
            form,
            'raster_contrast_boost',
            DEFAULT_RASTER_SETTINGS['raster_contrast_boost'],
            0.8,
            3.0,
        )
        settings.update({
            'raster_row_spacing': row_spacing,
            'raster_min_stitch': min_stitch,
            'raster_max_stitch': max_stitch,
            'raster_white_threshold': white_threshold,
            'raster_contrast_boost': round(contrast_boost, 1),
        })
        return settings

    canny_low = parse_int(
        form,
        'canny_low',
        DEFAULT_CANNY_SETTINGS['canny_low'],
        0,
        255,
    )
    canny_high = parse_int(
        form,
        'canny_high',
        DEFAULT_CANNY_SETTINGS['canny_high'],
        canny_low,
        255,
    )
    if canny_high < canny_low:
        canny_high = canny_low
    canny_contrast_boost = parse_float(
        form,
        'canny_contrast_boost',
        DEFAULT_CANNY_SETTINGS['canny_contrast_boost'],
        0.8,
        3.0,
    )
    canny_auto_thresholds = parse_bool( #传入自动开关使用
        form,
        'canny_auto_thresholds',
        DEFAULT_CANNY_SETTINGS['canny_auto_thresholds'],
    )
    canny_min_stitch_mm = DEFAULT_CANNY_SETTINGS['canny_min_stitch_mm']
    settings.update({ #把参数数值保存更新
        'canny_low': canny_low,
        'canny_high': canny_high,
        'canny_contrast_boost': round(canny_contrast_boost, 1),
        'canny_auto_thresholds': canny_auto_thresholds,
        'canny_min_stitch_mm': round(canny_min_stitch_mm, 1),
    })
    return settings

#构建刺绣图案，表单里是网站里参数，后面是默认值。将数据整理放进字典中
def build_embroidery_pattern(img, form, return_details=False):
    settings = resolve_embroidery_settings(form)
    target_width_mm = settings['target_width_mm']
    source_width_px = max(img.shape[1], 1)
    mm_per_pixel = target_width_mm / source_width_px #计算每像素多少毫米，建字典
    stats = {}

    min_stitch_len_mm = settings['min_stitch_len_mm']
    max_stitch_len_mm = settings['max_stitch_len_mm']
    mode = settings['mode']

    if mode == 'raster':
        pattern = photo_to_raster_embroidery(
            img,
            scale=1.0,
            contrast_boost=settings['raster_contrast_boost'],
            mm_per_pixel=mm_per_pixel,
            row_spacing=settings['raster_row_spacing'],
            min_stitch=settings['raster_min_stitch'],
            max_stitch=settings['raster_max_stitch'],
            white_threshold=settings['raster_white_threshold'],
            min_stitch_mm=min_stitch_len_mm,
            max_stitch_mm=max_stitch_len_mm,
        )
    else:
        canny_result = image_to_embroidery_canny(
            img,
            scale=1.0, #这里检查是自动开关还是用户值
            threshold1=None if settings['canny_auto_thresholds'] else settings['canny_low'],
            threshold2=None if settings['canny_auto_thresholds'] else settings['canny_high'],
            contrast_boost=settings['canny_contrast_boost'],
            min_stitch_mm=settings['canny_min_stitch_mm'],
            max_stitch_mm=max_stitch_len_mm,
            mm_per_pixel=mm_per_pixel,
            target_width_mm=target_width_mm,
            max_work_long_side=MAX_CANNY_WORK_LONG_SIDE,
            return_details=return_details,
        )
        #变量为要不要返回详细信息，布尔值，为真执行。否则上面存的值赋值过去
        if return_details:
            pattern = canny_result['pattern']
            stats = canny_result['stats']
            settings['canny_resolved_low'] = canny_result['used_threshold1']
            settings['canny_resolved_high'] = canny_result['used_threshold2']
            settings['canny_processed_width_px'] = canny_result['processed_width_px']
            settings['canny_processed_height_px'] = canny_result['processed_height_px']
        else:
            pattern = canny_result

    if not return_details:
        return pattern

    return {
        'pattern': pattern,
        'settings': settings,
        'stats': stats,
    }

#导出前的检查，
def get_export_blocking_error(pattern):
    if not pattern_has_stitches(pattern): #检查是否有下针，没有就返回
        return 'No stitches generated for this image and parameter combination'

    metrics = pattern_path_metrics(pattern)
    if metrics['stitch_count'] > 60000:
        return 'Stitch count is too high for a safe first-pass export.'

    return None


def get_preview_canvas_size(img, max_side=800):
    h, w = img.shape[:2]
    scale = 1.0 if max(h, w) <= max_side else max_side / max(h, w)
    return max(1, int(w * scale)), max(1, int(h * scale))

#错误处理，文件太大了就返回错误信息
@app.errorhandler(RequestEntityTooLarge)
def handle_file_too_large(_exc):
    return jsonify({'error': f'File size cannot exceed {MAX_UPLOAD_SIZE_MB}MB'}), 413

#首页路由
@app.route('/')
def index():
    return render_template('index.html') #用了渲染

#登录页路由
@app.route('/login')
def login():
    return render_template('login.html')

#注册页路由
@app.route('/signup')
def signup():
    return render_template('signup.html')

#工作台路由
@app.route('/workspace')
def workspace():
    return render_template('workspace.html')

#指南页路由
@app.route('/guide')
def guide():
    return render_template('guide.html')


#认证接口，注册
@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    try:
        ensure_db_ready() #防御，
        payload = request.get_json(silent=True) or {} 
        name = (payload.get('name') or '').strip()#不能全是空格，去掉空格，邮箱小写
        email = (payload.get('email') or '').strip().lower()
        password = payload.get('password') or ''#把数据整理干净和格式统一

        if not name or not email or not password:
            return jsonify({'error': 'Name, email and password are required'}), 400
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400

        password_hash = generate_password_hash(password) #加密

        with get_db_connection() as conn:
            try:
                cursor = conn.execute(
                    'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
                    (name, email, password_hash)
                )
                user_id = cursor.lastrowid #拿到新用户，自动加一
                conn.commit() #保存到数据库
            except sqlite3.IntegrityError: #邮箱错误，
                return jsonify({'error': 'Email is already registered'}), 409

        session['user_id'] = user_id #登录状态保存在服务器session中，注册完不用再登录
        session['user_name'] = name
        session['user_email'] = email

        return jsonify({'message': 'Account created', 'user': current_user_payload()}), 201
    except RequestEntityTooLarge:
        return handle_file_too_large(None)
    except Exception as e: #获得其他错误信息
        return jsonify({'error': str(e)}), 500

#登录，读取用户。验证邮件和密码，
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    try:
        ensure_db_ready()
        payload = request.get_json(silent=True) or {}
        email = (payload.get('email') or '').strip().lower()
        password = payload.get('password') or ''

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        with get_db_connection() as conn:
            user = conn.execute( #查询数据库，看看有没有这个邮箱的用户
                'SELECT id, name, email, password_hash FROM users WHERE email = ?',
                (email,)
            ).fetchone() #获得查询信息

        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid email or password'}), 401

        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']

        return jsonify({'message': 'Login successful', 'user': current_user_payload()}), 200
    except RequestEntityTooLarge:
        return handle_file_too_large(None)
    except Exception as e: #获取错误信息
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'message': 'Logged out'}), 200


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    user = current_user_payload()
    return jsonify({'authenticated': bool(user), 'user': user}), 200

#导出接口
@app.route('/api/export', methods=['POST'])
def export_image():
    try:
        if not current_user_payload():
            return jsonify({'error': 'Authentication required'}), 401

        image = request.files.get('image')
        export_format = (request.form.get('format') or '').lower()

        if not image or export_format not in ALLOWED_EXPORT_FORMATS:
            return jsonify({'error': 'Missing image or format'}), 400

        img = get_image(image.read())
        if img is None:
            return jsonify({'error': 'Invalid image'}), 400

        result = build_embroidery_pattern(img, request.form, return_details=True)
        pattern = result['pattern']
        export_error = get_export_blocking_error(pattern)#检查是否有刺绣命令，没有就错误
        if export_error:
            return jsonify({'error': export_error}), 400

        # 临时文件问题。获得文件路径。会持续占用句柄，因此先生成路径，再手动清理。
        temp_fd, temp_path = tempfile.mkstemp(suffix=export_format)
        os.close(temp_fd)
        try:
            pattern.write(temp_path)#交给刺绣语言去写，读完后放在缓冲区
            with open(temp_path, 'rb') as temp_file:
                output = BytesIO(temp_file.read())
                output.seek(0)
        finally:
            try:
                os.remove(temp_path) #把临时文件删除，发给浏览器
            except OSError:
                pass

        mimetype = 'application/octet-stream'
        if export_format == '.dst':
            mimetype = 'application/x-dst'
        elif export_format == '.pes':
            mimetype = 'application/x-pes'
        elif export_format == '.jef':
            mimetype = 'application/x-jef'
        elif export_format == '.exp':
            mimetype = 'application/x-exp'

        return send_file(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=f'embroidery_design{export_format}'
        )

    except RequestEntityTooLarge:
        return handle_file_too_large(None)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

#实时预览接口
@app.route('/api/preview', methods=['POST'])
def preview_image():
    try:
        if not current_user_payload():
            return jsonify({'error': 'Authentication required'}), 401

        image = request.files.get('image')
        if not image:
            return jsonify({'error': 'Missing image'}), 400

        img = get_image(image.read())
        if img is None:
            return jsonify({'error': 'Invalid image'}), 400

        result = build_embroidery_pattern(img, request.form, return_details=True)
        pattern = result['pattern']
        stats = result.get('stats', {})
        metrics = pattern_path_metrics(pattern)
        preview = pattern_to_data_url( #将图案画成一张图
            pattern,
            canvas_size=get_preview_canvas_size(img)
        )
        return jsonify({
            'preview': preview,
            'empty': not pattern_has_stitches(pattern),
            'applied_settings': result['settings'],
            'metrics': metrics,
            'truncated': bool(stats.get('truncated', False)),
            'max_stitches': stats.get('max_stitches'),
        }), 200

    except RequestEntityTooLarge:
        return handle_file_too_large(None)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=False, port=5000)
