import os
import uuid
import cv2
import numpy as np
import pyembroidery
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_file, render_template
from io import BytesIO

# 把你的刺绣函数文件导入进来
from embroidery import (
    get_image,
    image_to_embroidery_canny,
    photo_to_raster_embroidery,
    photo_to_line_embroidery,
    check_preview
)

app = Flask(__name__)

# 配置上传文件夹
app.config['UPLOAD_FOLDER'] = 'uploads'

# 配置最大文件大小（5MB）
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# 临时文件夹，存生成的 .dst 和预览图
TEMP_DIR = "temp_files"
os.makedirs(TEMP_DIR, exist_ok=True)

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

#-----API接口——————
@app.route('/api/export', methods=['POST'])
def export_image():

    try:
        # 获取前端发来的图片文件
        image = request.files['image']

        # 获取前端发来的格式
        export_format = request.form.get('format')

        # 检查是否收到了图片和格式
        if not image or not export_format:
            return jsonify({'error': 'Missing image or format'}), 400

        # TODO: 这里需要生成真正的刺绣格式文件
        # 目前暂时返回原始图片

        # 读取图片数据
        image_data = image.read()

        # 返回文件给前端下载
        return send_file(
            BytesIO(image_data),
            mimetype='image/png',
            as_attachment=True,
            download_name=f'embroidery_design{export_format}'
        )

    except Exception as e:
        # 如果有错误，返回错误信息
        return jsonify({'error': str(e)}), 500

# ── 启动服务器 ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, port=5000)