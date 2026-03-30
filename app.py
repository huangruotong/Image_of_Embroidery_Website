import os
import sqlite3
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template, session
from io import BytesIO
import tempfile
from werkzeug.security import generate_password_hash, check_password_hash

from embroidery import (
    get_image,
    image_to_embroidery_canny,
    photo_to_raster_embroidery,
    photo_to_line_embroidery
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# 配置最大文件大小（5MB）
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

ALLOWED_EXPORT_FORMATS = {'.pes', '.dst', '.jef', '.exp'}
ALLOWED_MODES = {'line', 'canny', 'raster'}
DB_PATH = Path(__file__).with_name('users.db')


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
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
        conn.commit()


def current_user_payload():
    if 'user_id' not in session:
        return None
    return {
        'id': session.get('user_id'),
        'name': session.get('user_name'),
        'email': session.get('user_email')
    }


init_db()

#home page
@app.route('/')
def index():
    return render_template('index.html')

# 登录页面
@app.route('/login')
def login():
    return render_template('login.html')

# 注册页面
@app.route('/signup')
def signup():
    return render_template('signup.html')

# 工作区页面
@app.route('/workspace')
def workspace():
    return render_template('workspace.html')

# 指南页面
@app.route('/guide')
def guide():
    return render_template('guide.html')


@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    try:
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
                conn.commit()
            except sqlite3.IntegrityError:
                return jsonify({'error': 'Email is already registered'}), 409

        user_id = cursor.lastrowid
        session['user_id'] = user_id
        session['user_name'] = name
        session['user_email'] = email

        return jsonify({'message': 'Account created', 'user': current_user_payload()}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    try:
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

#-----API接口——————
@app.route('/api/export', methods=['POST'])
def export_image():
    try:
        image = request.files.get('image')
        export_format = (request.form.get('format') or '').lower()
        mode = (request.form.get('mode') or 'line').lower()

        if not image or export_format not in ALLOWED_EXPORT_FORMATS:
            return jsonify({'error': 'Missing image or format'}), 400
        if mode not in ALLOWED_MODES:
            return jsonify({'error': 'Unsupported mode'}), 400

        def parse_int(name, default, min_value=None, max_value=None):
            raw = request.form.get(name)
            value = default if raw is None else int(raw)
            if min_value is not None:
                value = max(min_value, value)
            if max_value is not None:
                value = min(max_value, value)
            return value

        def parse_float(name, default, min_value=None, max_value=None):
            raw = request.form.get(name)
            value = default if raw is None else float(raw)
            if min_value is not None:
                value = max(min_value, value)
            if max_value is not None:
                value = min(max_value, value)
            return value

        img = get_image(image.read())
        if img is None:
            return jsonify({'error': 'Invalid image'}), 400

        target_width_mm = parse_float('target_width_mm', 100.0, 40.0, 300.0)
        source_width_px = max(img.shape[1], 1)
        mm_per_pixel = target_width_mm / source_width_px

        min_stitch_len_mm = parse_float('min_stitch_len_mm', 0.8, 0.4, 3.0)
        max_stitch_len_mm = parse_float('max_stitch_len_mm', 6.0, 2.0, 12.0)
        if max_stitch_len_mm < min_stitch_len_mm:
            max_stitch_len_mm = min_stitch_len_mm

        if mode == 'line':
            line_precision = parse_int('line_precision', 50, 0, 100)
            min_spacing = max(1, int(5 - line_precision / 25))
            max_spacing = max(min_spacing + 1, int(18 - line_precision / 8))
            line_white_threshold = int(245 - line_precision * 0.6)
            pattern, _ = photo_to_line_embroidery(
                img,
                scale=1.0,
                mm_per_pixel=mm_per_pixel,
                min_spacing=min_spacing,
                max_spacing=max_spacing,
                white_threshold=line_white_threshold,
                min_stitch_mm=min_stitch_len_mm,
                max_stitch_mm=max_stitch_len_mm,
            )
        elif mode == 'raster':
            row_spacing = parse_int('raster_row_spacing', 4, 1, 16)
            min_stitch = parse_int('raster_min_stitch', 2, 1, 20)
            max_stitch = parse_int('raster_max_stitch', 12, min_stitch, 40)
            white_threshold = parse_int('raster_white_threshold', 220, 120, 250)
            contrast_boost = parse_float('raster_contrast_boost', 1.8, 0.8, 3.0)
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
            canny_low = parse_int('canny_low', 50, 0, 255)
            canny_high = parse_int('canny_high', 150, canny_low, 255)
            pattern = image_to_embroidery_canny(
                img,
                scale=1.0,
                threshold1=canny_low,
                threshold2=canny_high,
                min_stitch_mm=min_stitch_len_mm,
                max_stitch_mm=max_stitch_len_mm,
            )

        # pyembroidery infers writer from filename extension, so write to temp file first.
        with tempfile.NamedTemporaryFile(suffix=export_format) as temp_file:
            pattern.write(temp_file.name)
            temp_file.seek(0)
            output = BytesIO(temp_file.read())
            output.seek(0)

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

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── 启动服务器 ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, port=5000)