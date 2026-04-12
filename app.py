import os
import sqlite3
import time
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
import tempfile

from flask import Flask, request, jsonify, send_file, render_template, session
from werkzeug.security import generate_password_hash, check_password_hash

from embroidery import (
    get_image,
    image_to_embroidery_canny,
    pattern_has_stitches,
    pattern_path_metrics,
    pattern_to_data_url,
    photo_to_raster_embroidery,
    photo_to_line_embroidery,
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
PROJECT_ROOT = Path(__file__).resolve().parent
LOCAL_APPDATA_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
DEFAULT_DB_DIR = LOCAL_APPDATA_DIR / 'EmbroideryDesign'
PROJECT_DB_PATH = PROJECT_ROOT / 'users.db'


def can_write_db_path(db_path):
    db_path = Path(db_path)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    if db_path.exists():
        try:
            with open(db_path, 'a+b'):
                pass
        except OSError:
            return False
    else:
        try:
            with open(db_path, 'a+b'):
                pass
            db_path.unlink()
        except OSError:
            return False

    probe_path = db_path.parent / f'.{db_path.name}.write-probe'
    try:
        with open(probe_path, 'xb'):
            pass
        probe_path.unlink()
    except OSError:
        return False

    return True


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
app.config['DB_INITIALIZED_FOR'] = None
FIXED_HOOP_WIDTH_MM = 130.0
FIXED_HOOP_HEIGHT_MM = 180.0
DEFAULT_EMBROIDERY_MODE = 'line'
DEFAULT_COMMON_SETTINGS = {
    'target_width_mm': 100.0,
    'min_stitch_len_mm': 0.8,
    'max_stitch_len_mm': 6.0,
}
DEFAULT_LINE_SETTINGS = {
    'line_precision': 50,
    'line_contrast_boost': 1.8,
}
DEFAULT_CANNY_SETTINGS = {
    'canny_low': 90,
    'canny_high': 210,
    'canny_contrast_boost': 1.0,
}
DEFAULT_RASTER_SETTINGS = {
    'raster_row_spacing': 6,
    'raster_min_stitch': 3,
    'raster_max_stitch': 10,
    'raster_white_threshold': 220,
    'raster_contrast_boost': 1.4,
}
MODE_PROCESSING_PX_PER_MM = {
    'line': 5.0,
    'raster': 4.0,
    'canny': 4.0,
}
MODE_DENSITY_LIMITS = {
    'line': 0.50,
    'raster': 0.65,
    'canny': 0.55,
}
MAX_UNTRIMMED_JUMP_RUN_MM = 8.0

#限制上传文件大小为5mb
# app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

ALLOWED_EXPORT_FORMATS = {'.pes', '.dst', '.jef', '.exp'}
ALLOWED_MODES = {'line', 'canny', 'raster'}


def get_db_path():
    return Path(app.config['DB_PATH'])


@contextmanager
def get_db_connection():
    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _create_users_table(conn):
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


def init_db():
    db_path = get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        with get_db_connection() as conn:
            _create_users_table(conn)
    except sqlite3.OperationalError:
        journal_path = Path(f"{db_path}-journal")
        if not journal_path.exists():
            raise

        recovery_path = Path(f"{journal_path}.stale")
        suffix = 1
        while recovery_path.exists():
            recovery_path = Path(f"{journal_path}.stale.{suffix}")
            suffix += 1

        rename_error = None
        for _ in range(10):
            try:
                journal_path.replace(recovery_path)
                rename_error = None
                break
            except PermissionError as exc:
                rename_error = exc
                time.sleep(0.1)

        if rename_error is not None:
            raise rename_error

        with get_db_connection() as conn:
            _create_users_table(conn)
    app.config['DB_INITIALIZED_FOR'] = str(db_path)


def ensure_db_ready():
    db_path = str(get_db_path())
    if app.config.get('DB_INITIALIZED_FOR') != db_path:
        init_db()


def current_user_payload():
    if 'user_id' not in session:
        return None
    return {
        'id': session.get('user_id'),
        'name': session.get('user_name'),
        'email': session.get('user_email')
    }


def parse_int(form, name, default, min_value=None, max_value=None):
    raw = form.get(name)
    try:
        value = default if raw in (None, '') else int(raw)
    except (TypeError, ValueError):
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


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


def resolve_processing_geometry(mode, source_width_px, target_width_mm):
    target_px_per_mm = MODE_PROCESSING_PX_PER_MM[mode]
    processed_width_px = max(
        1,
        min(source_width_px, int(round(target_width_mm * target_px_per_mm))),
    )
    processing_scale = processed_width_px / max(source_width_px, 1)
    processing_mm_per_pixel = target_width_mm / processed_width_px
    return processing_scale, processing_mm_per_pixel


def resolve_embroidery_settings(form):
    hoop_width_mm = FIXED_HOOP_WIDTH_MM
    hoop_height_mm = FIXED_HOOP_HEIGHT_MM

    mode = (form.get('mode') or DEFAULT_EMBROIDERY_MODE).lower()
    if mode not in ALLOWED_MODES:
        raise ValueError('Unsupported mode')

    target_width_mm = parse_float(
        form,
        'target_width_mm',
        DEFAULT_COMMON_SETTINGS['target_width_mm'],
        40.0,
        300.0,
    )
    min_stitch_len_mm = parse_float(
        form,
        'min_stitch_len_mm',
        DEFAULT_COMMON_SETTINGS['min_stitch_len_mm'],
        0.4,
        3.0,
    )
    max_stitch_len_mm = parse_float(
        form,
        'max_stitch_len_mm',
        DEFAULT_COMMON_SETTINGS['max_stitch_len_mm'],
        2.0,
        12.0,
    )
    if max_stitch_len_mm < min_stitch_len_mm:
        max_stitch_len_mm = min_stitch_len_mm

    settings = {
        'mode': mode,
        'target_width_mm': round(target_width_mm, 1),
        'min_stitch_len_mm': round(min_stitch_len_mm, 1),
        'max_stitch_len_mm': round(max_stitch_len_mm, 1),
        'hoop_width_mm': round(hoop_width_mm, 1),
        'hoop_height_mm': round(hoop_height_mm, 1),
    }

    if mode == 'line':
        line_precision = parse_int(
            form,
            'line_precision',
            DEFAULT_LINE_SETTINGS['line_precision'],
            0,
            100,
        )
        line_contrast_boost = parse_float(
            form,
            'line_contrast_boost',
            DEFAULT_LINE_SETTINGS['line_contrast_boost'],
            0.8,
            3.0,
        )
        settings.update({
            'line_precision': line_precision,
            'line_contrast_boost': round(line_contrast_boost, 1),
        })
        return settings

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
    settings.update({
        'canny_low': canny_low,
        'canny_high': canny_high,
        'canny_contrast_boost': round(canny_contrast_boost, 1),
    })
    return settings


def build_embroidery_pattern(img, form, return_details=False):
    settings = resolve_embroidery_settings(form)
    target_width_mm = settings['target_width_mm']
    source_width_px = max(img.shape[1], 1)

    min_stitch_len_mm = settings['min_stitch_len_mm']
    max_stitch_len_mm = settings['max_stitch_len_mm']
    mode = settings['mode']
    processing_scale, processing_mm_per_pixel = resolve_processing_geometry(
        mode,
        source_width_px,
        target_width_mm,
    )

    if mode == 'line':
        line_precision = settings['line_precision']
        line_contrast_boost = settings['line_contrast_boost']
        min_spacing = max(1, int(5 - line_precision / 25))
        max_spacing = max(min_spacing + 1, int(18 - line_precision / 8))
        line_white_threshold = int(245 - line_precision * 0.6)
        pattern = photo_to_line_embroidery(
            img,
            scale=processing_scale,
            contrast_boost=line_contrast_boost,
            mm_per_pixel=processing_mm_per_pixel,
            min_spacing=min_spacing,
            max_spacing=max_spacing,
            white_threshold=line_white_threshold,
            min_stitch_mm=min_stitch_len_mm,
            max_stitch_mm=max_stitch_len_mm,
        )
    elif mode == 'raster':
        pattern = photo_to_raster_embroidery(
            img,
            scale=processing_scale,
            contrast_boost=settings['raster_contrast_boost'],
            mm_per_pixel=processing_mm_per_pixel,
            row_spacing=settings['raster_row_spacing'],
            min_stitch=settings['raster_min_stitch'],
            max_stitch=settings['raster_max_stitch'],
            white_threshold=settings['raster_white_threshold'],
            min_stitch_mm=min_stitch_len_mm,
            max_stitch_mm=max_stitch_len_mm,
        )
    else:
        pattern = image_to_embroidery_canny(
            img,
            scale=processing_scale,
            threshold1=settings['canny_low'],
            threshold2=settings['canny_high'],
            contrast_boost=settings['canny_contrast_boost'],
            min_stitch_mm=min_stitch_len_mm,
            max_stitch_mm=max_stitch_len_mm,
            mm_per_pixel=processing_mm_per_pixel,
        )

    if not return_details:
        return pattern

    return {
        'pattern': pattern,
        'settings': settings,
    }


def get_export_blocking_error(pattern, settings):
    if not pattern_has_stitches(pattern):
        return 'No stitches generated for this image and parameter combination'

    metrics = pattern_path_metrics(pattern)
    if (
        metrics['design_width_mm'] > settings['hoop_width_mm'] + 1e-6
        or metrics['design_height_mm'] > settings['hoop_height_mm'] + 1e-6
    ):
        return (
            f"This size exceeds the hoop limit "
            f"({settings['hoop_width_mm']:g} x {settings['hoop_height_mm']:g} mm)."
        )
    if metrics['stitch_count'] > 60000:
        return 'Stitch count is too high for a safe first-pass export.'
    if metrics['max_untrimmed_jump_run_length_mm'] > MAX_UNTRIMMED_JUMP_RUN_MM:
        return 'Untrimmed jump travel is too long for a safe first-pass export.'

    density_limit = MODE_DENSITY_LIMITS.get(settings['mode'])
    if density_limit is not None and metrics['stitch_density_per_mm2'] > density_limit:
        return 'Stitch density is too high for a safe first-pass export.'

    return None


def get_preview_canvas_size(img, max_side=800):
    h, w = img.shape[:2]
    scale = 1.0 if max(h, w) <= max_side else max_side / max(h, w)
    return max(1, int(w * scale)), max(1, int(h * scale))

#首页路由
@app.route('/')
def index():
    return render_template('index.html')

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
    return render_template(
        'workspace.html',
        hoop_width_mm=FIXED_HOOP_WIDTH_MM,
        hoop_height_mm=FIXED_HOOP_HEIGHT_MM,
    )

#指南页路由
@app.route('/guide')
def guide():
    return render_template('guide.html')


#认证接口
@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    try:
        ensure_db_ready()
        payload = request.get_json(silent=True) or {}
        name = (payload.get('name') or '').strip()
        email = (payload.get('email') or '').strip().lower()
        password = payload.get('password') or ''

        if not name or not email or not password:
            return jsonify({'error': 'Name, email and password are required'}), 400
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400

        password_hash = generate_password_hash(password)

        with get_db_connection() as conn:
            try:
                cursor = conn.execute(
                    'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
                    (name, email, password_hash)
                )
                user_id = cursor.lastrowid
                conn.commit()
            except sqlite3.IntegrityError:
                return jsonify({'error': 'Email is already registered'}), 409

        session['user_id'] = user_id
        session['user_name'] = name
        session['user_email'] = email

        return jsonify({'message': 'Account created', 'user': current_user_payload()}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
            user = conn.execute(
                'SELECT id, name, email, password_hash FROM users WHERE email = ?',
                (email,)
            ).fetchone()

        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid email or password'}), 401

        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']

        return jsonify({'message': 'Login successful', 'user': current_user_payload()}), 200
    except Exception as e:
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
        export_error = get_export_blocking_error(pattern, result['settings'])
        if export_error:
            return jsonify({'error': export_error}), 400

        # Windows 下 NamedTemporaryFile 会持续占用句柄，因此先生成路径，再手动清理。
        temp_fd, temp_path = tempfile.mkstemp(suffix=export_format)
        os.close(temp_fd)
        try:
            pattern.write(temp_path)
            with open(temp_path, 'rb') as temp_file:
                output = BytesIO(temp_file.read())
                output.seek(0)
        finally:
            try:
                os.remove(temp_path)
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

    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

#预览接口
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
        preview = pattern_to_data_url(
            pattern,
            canvas_size=get_preview_canvas_size(img)
        )
        return jsonify({
            'preview': preview,
            'empty': not pattern_has_stitches(pattern),
            'applied_settings': result['settings'],
        }), 200

    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=False, port=5000)
