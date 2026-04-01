import os          # 读取系统环境变量（如 SECRET_KEY），实现配置与代码分离
import sqlite3     # Python 内置 SQLite 数据库驱动，用于用户账户的持久化存储
from pathlib import Path  # 面向对象的跨平台文件路径操作，避免手动拼接路径字符串

# Flask 核心对象与工具导入
from flask import Flask, request, jsonify, send_file, render_template, session
# Flask          — Web 应用主类，负责路由注册、请求处理和响应生成
# request        — 访问当前 HTTP 请求的数据（JSON 体、表单字段、上传文件等）
# jsonify        — 将 Python 字典/列表序列化为 JSON HTTP 响应，自动设置 Content-Type
# send_file      — 将文件流或路径作为附件发送给客户端（用于触发文件下载）
# render_template — 渲染 templates/ 目录中的 Jinja2 HTML 模板
# session        — 基于服务器端签名 Cookie 的用户会话，用于跟踪登录状态

from io import BytesIO     # 内存中的二进制流对象，用于存储生成的刺绣文件，避免额外落盘
import tempfile            # 创建系统临时文件，供 pyembroidery 写入再读取（需要文件名后缀）

# 密码安全工具（Werkzeug 提供，Flask 默认依赖）
from werkzeug.security import generate_password_hash, check_password_hash
# generate_password_hash — 对明文密码做加盐哈希后存入数据库，有效防止彩虹表攻击
# check_password_hash    — 登录时验证明文密码是否与数据库中的哈希值匹配

# 导入自定义刺绣算法模块中的各功能函数
from embroidery import (
    get_image,                   # 将上传的二进制图像数据解码为 OpenCV BGR 矩阵
    get_canny_preview,           # 返回 Canny 边缘检测结果的 base64 PNG 预览
    get_raster_preview,          # 返回光栅扫描预处理结果的 base64 PNG 预览
    image_to_embroidery_canny,   # Canny 边缘法：沿轮廓线生成刺绣针脚图案
    photo_to_raster_embroidery,  # 光栅法：蛇形逐行扫描亮度生成针脚图案
    photo_to_line_embroidery     # 线条法：按整行平均亮度自适应行间距生成针脚
)

# 创建 Flask 应用实例，__name__ 让 Flask 以当前文件所在目录作为根目录
app = Flask(__name__)

# 从环境变量读取密钥；生产环境必须设置真实随机值，开发环境使用占位符
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# 限制上传文件最大为 5 MB，防止超大文件耗尽服务器内存（单位：字节）
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# 允许导出的刺绣文件格式白名单：PES(Brother)、DST(Tajima)、JEF(Janome)、EXP(Melco)
ALLOWED_EXPORT_FORMATS = {'.pes', '.dst', '.jef', '.exp'}

# 允许的刺绣转换模式白名单，防止非法模式值进入算法函数
ALLOWED_MODES = {'line', 'canny', 'raster'}

# 数据库文件路径：与 app.py 同级目录下的 users.db（使用绝对路径避免工作目录差异）
DB_PATH = Path(__file__).with_name('users.db')


def get_db_connection():
    """创建并返回一个 SQLite 数据库连接。

    row_factory 设置为 sqlite3.Row，使查询结果支持按列名访问（如 row['email']），
    而不必依赖位置索引，代码更安全易读。
    """
    conn = sqlite3.connect(DB_PATH)   # 连接到指定路径的 SQLite 数据库文件
    conn.row_factory = sqlite3.Row    # 让查询结果行支持字典式按列名访问
    return conn


def init_db():
    """在应用启动时自动创建 users 表（若表不存在则建表，已存在则跳过）。

    字段说明：
    - id            : 自增整数主键，唯一标识每一个用户
    - name          : 用户昵称，非空
    - email         : 用户邮箱，全局唯一约束（UNIQUE），用作登录凭证
    - password_hash : 经 Werkzeug 加盐哈希后的密码，明文密码永不写入数据库
    - created_at    : 账户注册时间，由数据库自动填充当前时间戳
    """
    with get_db_connection() as conn:
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
        conn.commit()  # 提交事务，使 DDL 建表语句正式生效


def current_user_payload():
    """从当前请求的 Session 中读取用户信息，构造并返回用户数据字典。

    如果 Session 中不含 user_id（即用户未登录），返回 None。
    该函数被 /api/auth/me 以及注册/登录成功的响应复用，避免重复代码。
    """
    if 'user_id' not in session:
        return None  # 未登录状态，返回 None 表示匿名用户
    # 从 Session 中读取登录时写入的用户信息，封装为标准字典格式返回
    return {
        'id': session.get('user_id'),       # 数据库自增主键 ID
        'name': session.get('user_name'),   # 用户昵称
        'email': session.get('user_email')  # 用户邮箱
    }


# 应用启动时立即初始化数据库（确保 users 表存在），首次运行时自动建表
init_db()

# ── 页面路由 ─────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """首页：展示产品介绍和功能入口。"""
    return render_template('index.html')

@app.route('/login')
def login():
    """登录页面：用户输入邮箱和密码进行身份认证。"""
    return render_template('login.html')

@app.route('/signup')
def signup():
    """注册页面：新用户填写昵称、邮箱、密码创建账户。"""
    return render_template('signup.html')

@app.route('/workspace')
def workspace():
    """工作区页面：图像上传、参数调整、实时预览和导出刺绣文件的核心操作界面。"""
    return render_template('workspace.html')

@app.route('/guide')
def guide():
    """使用指南页面：说明各刺绣模式的参数含义和使用方法。"""
    return render_template('guide.html')


# ── 认证 API ─────────────────────────────────────────────────────────────────

@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    """用户注册接口：接收 JSON 请求体，校验字段后创建新用户账户。

    请求体（JSON）：
    - name     : 用户昵称（非空字符串）
    - email    : 用户邮箱（唯一，转小写存储）
    - password : 明文密码（长度 ≥ 8 位）

    成功返回 201；字段缺失返回 400；密码过短返回 400；邮箱重复返回 409。
    """
    try:
        # 解析 JSON 请求体；silent=True 表示解析失败时返回 None 而非抛出异常
        payload = request.get_json(silent=True) or {}
        # 提取并清洗字段：strip() 去除首尾空格，邮箱转小写保证唯一性判断准确
        name     = (payload.get('name') or '').strip()
        email    = (payload.get('email') or '').strip().lower()
        password = payload.get('password') or ''

        # 必填字段校验：任一字段为空则拒绝请求
        if not name or not email or not password:
            return jsonify({'error': 'Name, email and password are required'}), 400
        # 密码长度校验：至少 8 位，防止过于简单的密码
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400

        # 对明文密码进行加盐哈希处理，绝不将明文密码存入数据库
        password_hash = generate_password_hash(password)

        with get_db_connection() as conn:
            try:
                # 使用参数化查询（? 占位符）防止 SQL 注入攻击
                cursor = conn.execute(
                    'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
                    (name, email, password_hash)
                )
                conn.commit()  # 提交事务，使新用户数据持久化到磁盘
            except sqlite3.IntegrityError:
                # email 字段有 UNIQUE 约束，重复插入会抛出 IntegrityError
                return jsonify({'error': 'Email is already registered'}), 409

        # 读取刚插入行的自增主键，用于写入 Session
        user_id = cursor.lastrowid
        # 注册成功后自动登录：将用户信息写入 Session，后续请求无需再次登录
        session['user_id']    = user_id
        session['user_name']  = name
        session['user_email'] = email

        # 返回 201 Created，携带当前用户信息
        return jsonify({'message': 'Account created', 'user': current_user_payload()}), 201
    except Exception as e:
        # 捕获未预期的服务器内部错误，返回 500 且不暴露内部堆栈
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """用户登录接口：验证邮箱和密码，成功后写入 Session。

    请求体（JSON）：
    - email    : 用户邮箱
    - password : 明文密码

    成功返回 200；字段缺失返回 400；邮箱或密码错误统一返回 401。
    注意：邮箱不存在和密码错误返回相同的错误信息，防止用户枚举攻击。
    """
    try:
        # 解析请求体 JSON
        payload = request.get_json(silent=True) or {}
        # 提取邮箱（转小写与注册时保持一致）和明文密码
        email    = (payload.get('email') or '').strip().lower()
        password = payload.get('password') or ''

        # 必填字段校验
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        with get_db_connection() as conn:
            # 按邮箱查询用户记录；fetchone() 未找到时返回 None
            user = conn.execute(
                'SELECT id, name, email, password_hash FROM users WHERE email = ?',
                (email,)
            ).fetchone()

        # 用户不存在或密码不匹配时，统一返回 401（不区分两种情况，防止信息泄露）
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid email or password'}), 401

        # 验证通过：将用户信息存入 Session，标记为已登录状态
        session['user_id']    = user['id']
        session['user_name']  = user['name']
        session['user_email'] = user['email']

        # 返回 200 及当前用户信息
        return jsonify({'message': 'Login successful', 'user': current_user_payload()}), 200
    except Exception as e:
        # 捕获未预期的服务器内部错误，返回 500
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    """登出接口：清除当前 Session 中的所有用户数据，使登录状态失效。"""
    session.clear()  # 清除 Session 中的全部键值，前端 Cookie 签名将失效
    return jsonify({'message': 'Logged out'}), 200


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    """查询当前登录状态接口：前端可调用此接口判断用户是否已登录。

    已登录时返回 authenticated=true 及用户信息；
    未登录时返回 authenticated=false 且 user 为 null。
    """
    user = current_user_payload()  # 从 Session 读取用户信息，未登录时为 None
    # bool(user)：None → False（未登录），字典 → True（已登录）
    return jsonify({'authenticated': bool(user), 'user': user}), 200

# ── 业务 API ─────────────────────────────────────────────────────────────────

@app.route('/api/export', methods=['POST'])
def export_image():
    """刺绣文件导出接口：接收图像和参数，生成对应格式的刺绣文件供下载。

    表单字段（multipart/form-data）：
    - image           : 上传的图像文件
    - format          : 导出文件格式（.pes/.dst/.jef/.exp）
    - mode            : 刺绣转换模式（line/canny/raster）
    - target_width_mm : 目标绣品宽度（毫米），用于像素到物理坐标的换算
    - 其余模式特定参数（见各分支注释）
    """
    try:
        # 从 multipart 表单中获取上传的图像文件对象
        image = request.files.get('image')
        # 获取导出格式并转为小写（例如 ".dst"）
        export_format = (request.form.get('format') or '').lower()
        # 获取刺绣模式，默认为 'line'
        mode = (request.form.get('mode') or 'line').lower()

        # 图像和格式双重校验：图像缺失或格式不在白名单内时拒绝请求
        if not image or export_format not in ALLOWED_EXPORT_FORMATS:
            return jsonify({'error': 'Missing image or format'}), 400
        # 校验刺绣模式是否在允许范围内，防止非法值进入算法
        if mode not in ALLOWED_MODES:
            return jsonify({'error': 'Unsupported mode'}), 400

        def parse_int(name, default, min_value=None, max_value=None):
            """从表单中安全读取整数参数，支持默认值和范围裁剪。

            name      : 表单字段名
            default   : 字段不存在时使用的默认值
            min_value : 最小值边界（含），低于时取 min_value
            max_value : 最大值边界（含），高于时取 max_value
            """
            raw = request.form.get(name)                 # 读取原始字符串值
            value = default if raw is None else int(raw) # 字段缺失时用默认值，否则转整数
            if min_value is not None:
                value = max(min_value, value)            # 下限裁剪，防止值过小
            if max_value is not None:
                value = min(max_value, value)            # 上限裁剪，防止值过大
            return value

        def parse_float(name, default, min_value=None, max_value=None):
            """从表单中安全读取浮点数参数，支持默认值和范围裁剪。

            参数含义同 parse_int，但值类型为 float。
            """
            raw = request.form.get(name)                   # 读取原始字符串值
            value = default if raw is None else float(raw) # 字段缺失时用默认值，否则转浮点
            if min_value is not None:
                value = max(min_value, value)              # 下限裁剪
            if max_value is not None:
                value = min(max_value, value)              # 上限裁剪
            return value

        # 将上传的图像二进制数据解码为 OpenCV BGR 矩阵
        img = get_image(image.read())
        if img is None:
            return jsonify({'error': 'Invalid image'}), 400  # 解码失败说明文件不是有效图像

        # 读取目标绣品宽度（毫米），限制在 40–300mm 合理范围内
        target_width_mm = parse_float('target_width_mm', 100.0, 40.0, 300.0)
        # 获取图像原始像素宽度（img.shape: [高, 宽, 通道]），max 防止除以零
        source_width_px = max(img.shape[1], 1)
        # 计算毫米/像素换算比例，供算法将像素坐标转换为刺绣物理坐标（单位：mm）
        mm_per_pixel = target_width_mm / source_width_px

        # 全局针脚长度限制（三种模式共用），范围约束防止极端值导致异常针脚
        min_stitch_len_mm = parse_float('min_stitch_len_mm', 0.8, 0.4, 3.0)  # 最短针脚（mm）
        max_stitch_len_mm = parse_float('max_stitch_len_mm', 6.0, 2.0, 12.0) # 最长针脚（mm）
        # 防止用户传入 max < min 的非法组合，自动修正
        if max_stitch_len_mm < min_stitch_len_mm:
            max_stitch_len_mm = min_stitch_len_mm

        if mode == 'line':
            # ── Line 模式：按整行平均亮度自适应行间距 ─────────────────────────────
            # precision 范围 0–100：数值越大，行间距越小，绣制细节越丰富
            line_precision = parse_int('line_precision', 50, 0, 100)
            # 将 precision 映射到行间距：precision=100 → 间距最小（最密）；precision=0 → 间距最大（最疏）
            min_spacing = max(1, int(5 - line_precision / 25))               # 最密行间距（像素）
            max_spacing = max(min_spacing + 1, int(18 - line_precision / 8)) # 最疏行间距
            # 亮度阈值：precision 越高，更多灰色区域被识别为"暗"区并绣入针脚
            line_white_threshold = int(245 - line_precision * 0.6)
            # 对比度增益参数，范围 0.8–3.0
            line_contrast_boost = parse_float('line_contrast_boost', 1.8, 0.8, 3.0)
            # scale=1.0：尺寸已通过 mm_per_pixel 精确控制，算法内部不再额外缩放
            pattern, _ = photo_to_line_embroidery(
                img,
                scale=1.0,
                contrast_boost=line_contrast_boost,
                mm_per_pixel=mm_per_pixel,
                min_spacing=min_spacing,
                max_spacing=max_spacing,
                white_threshold=line_white_threshold,
                min_stitch_mm=min_stitch_len_mm,
                max_stitch_mm=max_stitch_len_mm,
            )
        elif mode == 'raster':
            # ── Raster 模式：蛇形逐像素扫描，针脚密度随亮度变化 ──────────────────
            row_spacing     = parse_int('raster_row_spacing', 4, 1, 16)          # 扫描行间距（像素）
            min_stitch      = parse_int('raster_min_stitch', 2, 1, 20)           # 黑色区域最密针距
            max_stitch      = parse_int('raster_max_stitch', 12, min_stitch, 40) # 灰色区域最疏针距
            white_threshold = parse_int('raster_white_threshold', 220, 120, 250) # 跳过亮度阈值
            contrast_boost  = parse_float('raster_contrast_boost', 1.8, 0.8, 3.0)
            pattern, _ = photo_to_raster_embroidery(
                img,
                scale=1.0,
                contrast_boost=contrast_boost,
                mm_per_pixel=mm_per_pixel,
                row_spacing=row_spacing,
                min_stitch=min_stitch,
                max_stitch=max_stitch,
                white_threshold=white_threshold,
                min_stitch_mm=min_stitch_len_mm,
                max_stitch_mm=max_stitch_len_mm,
            )
        else:
            # ── Canny 模式：提取图像边缘轮廓并沿轮廓生成针脚 ────────────────────────
            canny_low            = parse_int('canny_low', 50, 0, 255)           # Canny 低阈值
            canny_high           = parse_int('canny_high', 150, canny_low, 255) # Canny 高阈值（≥低阈值）
            canny_contrast_boost = parse_float('canny_contrast_boost', 1.8, 0.8, 3.0)
            pattern = image_to_embroidery_canny(
                img,
                scale=1.0,
                threshold1=canny_low,
                threshold2=canny_high,
                contrast_boost=canny_contrast_boost,
                min_stitch_mm=min_stitch_len_mm,
                max_stitch_mm=max_stitch_len_mm,
                mm_per_pixel=mm_per_pixel,
            )

        # pyembroidery 通过文件名后缀推断要使用的写入器（writer），
        # 因此必须先写入临时文件（带正确后缀），再读回内存流，以保留格式信息
        with tempfile.NamedTemporaryFile(suffix=export_format) as temp_file:
            pattern.write(temp_file.name)    # 将刺绣图案按格式写入临时磁盘文件
            temp_file.seek(0)                # 重置文件指针到开头，准备读取
            output = BytesIO(temp_file.read()) # 将磁盘文件内容加载到内存流
            output.seek(0)                   # 重置内存流指针到开头，供 send_file 读取

        # 根据导出格式设置对应的 MIME 类型，帮助浏览器正确识别文件类型
        mimetype = 'application/octet-stream'  # 默认通用二进制流类型
        if export_format == '.dst':
            mimetype = 'application/x-dst'     # Tajima DST 格式
        elif export_format == '.pes':
            mimetype = 'application/x-pes'     # Brother PES 格式
        elif export_format == '.jef':
            mimetype = 'application/x-jef'     # Janome JEF 格式
        elif export_format == '.exp':
            mimetype = 'application/x-exp'     # Melco EXP 格式

        # 将内存中的刺绣文件以附件形式发送给客户端，触发浏览器下载
        return send_file(
            output,
            mimetype=mimetype,
            as_attachment=True,                              # 触发浏览器"另存为"对话框
            download_name=f'embroidery_design{export_format}' # 指定下载文件名
        )

    except Exception as e:
        # 捕获所有未预期异常，避免服务器内部堆栈信息泄露给客户端
        return jsonify({'error': str(e)}), 500

@app.route('/api/preview', methods=['POST'])
def preview_image():
    """实时预览接口：将上传图像按选定模式处理后返回 base64 PNG 数据 URL。

    前端每次调整参数时调用此接口，无需等待完整导出，实现所见即所得的预览体验。
    目前支持 canny 和 raster 两种模式（line 模式暂不提供独立预览）。
    """
    try:
        image = request.files.get('image')                   # 获取上传的图像文件
        mode = (request.form.get('mode') or 'canny').lower() # 获取预览模式，默认 canny
        if not image:
            return jsonify({'error': 'Missing image'}), 400
        # 解码图像为 OpenCV BGR 矩阵
        img = get_image(image.read())
        if img is None:
            return jsonify({'error': 'Invalid image'}), 400
        if mode == 'canny':
            # ── Canny 预览模式 ──────────────────────────────────────────────────
            def _safe_int(val, default):
                """安全地将值转为整数，转换失败时返回默认值，防止前端传入非数字导致 500。"""
                try:
                    return int(val)
                except (TypeError, ValueError):
                    return default
            def _safe_float(val, default):
                """安全地将值转为浮点数，转换失败时返回默认值。"""
                try:
                    return float(val)
                except (TypeError, ValueError):
                    return default
            # 读取 Canny 阈值并裁剪到合法范围 [0, 255]
            canny_low  = max(0, min(255, _safe_int(request.form.get('canny_low'), 50)))
            canny_high = max(0, min(255, _safe_int(request.form.get('canny_high'), 150)))
            # 读取对比度增益并裁剪到合法范围 [0.8, 3.0]
            contrast_boost = max(0.8, min(3.0, _safe_float(request.form.get('canny_contrast_boost'), 1.8)))
            # 调用 Canny 预览函数，返回 base64 编码的 PNG 图像数据 URL
            preview_data = get_canny_preview(
                img,
                threshold1=canny_low,
                threshold2=canny_high,
                contrast_boost=contrast_boost,
            )
            return jsonify({'preview': preview_data}), 200
        elif mode == 'raster':
            # ── Raster 预览模式 ─────────────────────────────────────────────────
            # 读取参数并裁剪到合法范围（与导出接口保持一致，确保预览即导出效果）
            row_spacing     = max(1, min(16, int(request.form.get('raster_row_spacing') or 4)))
            white_threshold = max(120, min(250, int(request.form.get('raster_white_threshold') or 220)))
            contrast_boost  = max(0.8, min(3.0, float(request.form.get('raster_contrast_boost') or 1.8)))
            # 调用 Raster 预览函数，返回 base64 编码的 PNG 图像数据 URL
            preview_data = get_raster_preview(
                img,
                contrast_boost=contrast_boost,
                white_threshold=white_threshold,
                row_spacing=row_spacing,
            )
            return jsonify({'preview': preview_data}), 200
        # line 模式暂不支持独立预览，返回 400 提示客户端
        return jsonify({'error': 'Preview not supported for this mode'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── 启动服务器 ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, port=5000)