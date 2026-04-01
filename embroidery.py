import cv2           # OpenCV：图像读写与预处理（灰度化、模糊、边缘检测、轮廓提取）
import numpy as np   # NumPy：像素矩阵运算与数组转换
import pyembroidery  # 刺绣格式库：组织针迹并导出 dst/pes/jef/exp 等格式
import math          # 数学函数：欧氏距离与向上取整
import base64        # Base64 编码：将预览图二进制转为 data URL


def _add_stitch_limited(pattern, last_x, last_y, tx, ty, min_units, max_units):
    """在两点之间按最短/最长针脚限制添加 STITCH。

    参数单位均为刺绣单位（0.1mm）。
    返回值：(new_last_x, new_last_y, added_count)
    """
    # 起点未初始化时无法计算距离，直接返回
    if last_x is None or last_y is None:
        return last_x, last_y, 0

    # 计算当前点到目标点的欧氏距离
    dist = math.hypot(tx - last_x, ty - last_y)

    # 距离太短（小于最短针脚）则跳过，避免过密针脚
    if dist < min_units:
        return last_x, last_y, 0

    # 距离太长时按最大针脚长度等分插值
    steps = 1
    if max_units > 0 and dist > max_units:
        steps = int(math.ceil(dist / max_units))

    added = 0
    for i in range(1, steps + 1):
        nx = last_x + (tx - last_x) * (i / steps)
        ny = last_y + (ty - last_y) * (i / steps)
        pattern.add_stitch_absolute(pyembroidery.STITCH, nx, ny)
        added += 1

    return tx, ty, added


def _sort_contours_nearest(contours):
    """贪心最近邻排序轮廓，减少轮廓间跳线距离。"""
    if len(contours) <= 1:
        return contours

    sorted_c = [contours[0]]
    remaining = list(contours[1:])
    last_pt = contours[0][-1][0]

    while remaining:
        dists = [
            math.hypot(c[0][0][0] - last_pt[0], c[0][0][1] - last_pt[1])
            for c in remaining
        ]
        idx = dists.index(min(dists))
        sorted_c.append(remaining.pop(idx))
        last_pt = sorted_c[-1][-1][0]

    return sorted_c


def get_image(photo):
    """将上传二进制数据解码为 OpenCV BGR 图像矩阵。"""
    # bytes -> uint8 数组 -> OpenCV 图像
    nparr = np.frombuffer(photo, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        print("No image")
        return None

    return img


def get_canny_preview(img, threshold1=50, threshold2=150, contrast_boost=1.8):
    """返回 Canny 预览的 base64 PNG data URL。"""
    h, w = img.shape[:2]
    max_side = 800
    if max(h, w) > max_side:
        scale = max_side / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 局部对比度增强，提升边缘可见性
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.convertScaleAbs(gray, alpha=contrast_boost, beta=-50)

    # 分辨率自适应高斯模糊核，先降噪再做 Canny
    h, w = gray.shape
    long_side = max(w, h)
    ksize = max(3, int(long_side / 200) * 2 + 1)
    blurred = cv2.GaussianBlur(gray, (ksize, ksize), 0)

    edges = cv2.Canny(blurred, threshold1, threshold2)
    _, buffer = cv2.imencode('.png', edges)
    img_b64 = base64.b64encode(buffer).decode('utf-8')
    return f'data:image/png;base64,{img_b64}'


def get_raster_preview(img, contrast_boost=1.8, white_threshold=220, row_spacing=4):
    """返回 Raster 预处理预览的 base64 PNG data URL。"""
    h, w = img.shape[:2]
    max_side = 800
    if max(h, w) > max_side:
        scale = max_side / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 对比度增强，提升亮暗区分度
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.convertScaleAbs(gray, alpha=contrast_boost, beta=-50)

    # 百分位拉伸，适配不同曝光照片
    low_p = np.percentile(gray, 5)
    high_p = np.percentile(gray, 95)
    if high_p > low_p:
        gray = np.clip(
            (gray.astype(np.float32) - low_p) / (high_p - low_p) * 255,
            0, 255
        ).astype(np.uint8)

    # 仅在扫描行上绘制暗像素，模拟 raster 行扫描效果
    preview = np.ones_like(gray) * 255
    for y in range(0, gray.shape[0], row_spacing):
        for x in range(gray.shape[1]):
            if gray[y, x] < white_threshold:
                preview[y, x] = gray[y, x]

    _, buffer = cv2.imencode('.png', preview)
    img_b64 = base64.b64encode(buffer).decode('utf-8')
    return f'data:image/png;base64,{img_b64}'


def image_to_embroidery_canny(
    img,  # Canny 边缘法（outline）
    scale=0.5,
    threshold1=50,
    threshold2=150,
    contrast_boost=1.8,
    min_stitch_mm=0.8,
    max_stitch_mm=6.0,
    mm_per_pixel=0.1,
):
    """将图像转换为 Canny 轮廓刺绣图案。"""
    print("正在读取图片...")
    MAX_STITCHES = 80000

    # 1) 缩放
    h, w = img.shape[:2]
    new_w, new_h = int(w * scale), int(h * scale)
    img = cv2.resize(img, (new_w, new_h))
    print(f"   尺寸: {new_w}x{new_h}")

    # 2) 灰度 + 对比度增强
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.convertScaleAbs(gray, alpha=contrast_boost, beta=-50)

    # 3) 自适应高斯模糊
    long_side = max(new_w, new_h)
    ksize = max(3, int(long_side / 200) * 2 + 1)
    blurred = cv2.GaussianBlur(gray, (ksize, ksize), 0)

    # 4) Canny 边缘检测
    edges = cv2.Canny(blurred, threshold1, threshold2)

    # 5) 提取轮廓
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    # 6) 过滤噪声轮廓
    contours = [c for c in contours if len(c) >= 2 and cv2.contourArea(c) >= 2.0]

    # 7) 最近邻排序
    contours = _sort_contours_nearest(contours)

    # 8) 生成针脚
    pattern = pyembroidery.EmbPattern()
    stitch_count = 0

    # 像素坐标 -> 刺绣单位（0.1mm）
    pixel_to_emb_unit = mm_per_pixel * 10.0
    min_units = max(1.0, min_stitch_mm * 10.0)
    max_units = max(min_units, max_stitch_mm * 10.0)

    for contour in contours:
        if stitch_count >= MAX_STITCHES:
            print(f"警告：针数已达上限 {MAX_STITCHES}，提前终止。建议调高阈值或降低精度。")
            break

        start_pt = contour[0][0]
        start_x = start_pt[0] * pixel_to_emb_unit
        start_y = start_pt[1] * pixel_to_emb_unit
        pattern.add_command(pyembroidery.TRIM)
        pattern.add_stitch_absolute(pyembroidery.JUMP, start_x, start_y)
        last_x, last_y = start_x, start_y

        for point in contour[1:]:
            tx = point[0][0] * pixel_to_emb_unit
            ty = point[0][1] * pixel_to_emb_unit
            last_x, last_y, added = _add_stitch_limited(
                pattern,
                last_x,
                last_y,
                tx,
                ty,
                min_units,
                max_units,
            )
            stitch_count += added

    # 空图案时跳过 move_center，避免 NaN
    if any(s[2] == pyembroidery.STITCH for s in pattern.stitches):
        pattern.move_center_to_origin()
    pattern.add_command(pyembroidery.END)

    print(f"Canny 模式针数: {stitch_count}")
    return pattern


def photo_to_raster_embroidery(
    img,  # Raster 法
    scale=0.5,
    contrast_boost=1.8,
    mm_per_pixel=0.1,
    row_spacing=4,
    min_stitch=2,
    max_stitch=12,
    white_threshold=220,
    min_stitch_mm=0.8,
    max_stitch_mm=6.0,
    max_jump_mm=8.0,
    trim_gap_threshold=8,
):
    """将照片转换为 Raster 风格刺绣图案。"""
    print("正在读取照片...")
    MAX_STITCHES = 120000

    # 1) 图像预处理
    img = cv2.resize(img, None, fx=scale, fy=scale)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 增强对比度
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.convertScaleAbs(gray, alpha=contrast_boost, beta=-50)

    # 百分位归一化
    low_p = np.percentile(gray, 5)
    high_p = np.percentile(gray, 95)
    if high_p > low_p:
        gray = np.clip(
            (gray.astype(np.float32) - low_p) / (high_p - low_p) * 255,
            0, 255,
        ).astype(np.uint8)

    h, w = gray.shape
    scale_factor = mm_per_pixel * 10  # 0.1mm 单位换算
    pattern = pyembroidery.EmbPattern()

    print("正在计算 Raster 针迹...")
    stitch_count = 0
    last_x, last_y = None, None
    gap_run = 0
    min_units = max(1.0, min_stitch_mm * 10.0)
    max_units = max(min_units, max_stitch_mm * 10.0)
    max_jump_units = max(max_units, max_jump_mm * 10.0)

    for y in range(0, h, row_spacing):
        # 蛇形扫描：偶数行左->右，奇数行右->左
        is_reverse = (y // row_spacing) % 2 != 0
        x_range = range(w - 1, -1, -1) if is_reverse else range(0, w)
        x_list = list(x_range)

        if stitch_count >= MAX_STITCHES:
            print(f"警告：针数已达上限 {MAX_STITCHES}，提前终止。建议增大 Row Spacing 或提高 White Threshold。")
            break

        i = 0
        while i < len(x_list):
            x = x_list[i]
            pixel = int(gray[y, x])

            # 跳过过亮区域
            if pixel >= white_threshold:
                if last_x is not None:
                    gap_run += 1
                    if gap_run >= trim_gap_threshold:
                        last_x, last_y = None, None
                i += 1
                continue

            tx, ty = x * scale_factor, y * scale_factor

            if last_x is None:
                if gap_run >= trim_gap_threshold:
                    pattern.add_command(pyembroidery.TRIM)
                pattern.add_stitch_absolute(pyembroidery.JUMP, tx, ty)
                last_x, last_y = tx, ty
                gap_run = 0
            else:
                jump_dist = math.hypot(tx - last_x, ty - last_y)
                if jump_dist > max_jump_units:
                    pattern.add_command(pyembroidery.TRIM)
                    pattern.add_stitch_absolute(pyembroidery.JUMP, tx, ty)
                    last_x, last_y = tx, ty
                else:
                    last_x, last_y, added = _add_stitch_limited(
                        pattern,
                        last_x,
                        last_y,
                        tx,
                        ty,
                        min_units,
                        max_units,
                    )
                    stitch_count += added
                gap_run = 0

            # 亮度越低，步进越小（针脚越密）
            t = pixel / 255.0
            stitch_gap = int(min_stitch + t * (max_stitch - min_stitch))
            i += max(stitch_gap, 1)

    # 与原实现一致：结束前将图案移到原点
    pattern.move_center_to_origin()
    pattern.add_command(pyembroidery.END)

    print(f"总针数: {stitch_count}")
    return pattern, gray


def photo_to_line_embroidery(
    img,  # Line 法
    scale=0.5,
    contrast_boost=1.8,
    mm_per_pixel=0.1,
    min_spacing=2,
    max_spacing=15,
    white_threshold=230,
    min_stitch_mm=0.8,
    max_stitch_mm=6.0,
    max_jump_mm=8.0,
):
    """将照片转换为 Line 风格刺绣图案。"""
    # 图像预处理
    img = cv2.resize(img, None, fx=scale, fy=scale)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.convertScaleAbs(gray, alpha=contrast_boost, beta=-50)

    # 百分位亮度归一化
    low_p = np.percentile(gray, 5)
    high_p = np.percentile(gray, 95)
    if high_p > low_p:
        gray = np.clip(
            (gray.astype(np.float32) - low_p) / (high_p - low_p) * 255,
            0, 255,
        ).astype(np.uint8)

    h, w = gray.shape
    scale_factor = mm_per_pixel * 10
    pattern = pyembroidery.EmbPattern()

    print("正在计算 Line 针迹...")
    stitch_count = 0
    last_x, last_y = None, None
    y = 0
    row_index = 0
    min_units = max(1.0, min_stitch_mm * 10.0)
    max_units = max(min_units, max_stitch_mm * 10.0)
    max_jump_units = max(max_units, max_jump_mm * 10.0)

    while y < h:
        # 以整行平均亮度控制下一行间距
        row_brightness = float(np.mean(gray[y, :]))

        # 整行太白则直接跳过
        if row_brightness >= white_threshold:
            y += max_spacing
            row_index += 1
            continue

        # 行越暗，间距越小；行越亮，间距越大
        t = row_brightness / white_threshold
        next_spacing = int(min_spacing + t * (max_spacing - min_spacing))
        next_spacing = max(next_spacing, min_spacing)

        # 蛇形路径
        if row_index % 2 == 0:
            x_list = range(0, w)
        else:
            x_list = range(w - 1, -1, -1)

        for x in x_list:
            pixel = int(gray[y, x])

            # 单像素过白则断开当前线段
            if pixel >= white_threshold:
                last_x, last_y = None, None
                continue

            tx = x * scale_factor
            ty = y * scale_factor

            if last_x is None:
                pattern.add_command(pyembroidery.TRIM)
                pattern.add_stitch_absolute(pyembroidery.JUMP, tx, ty)
                last_x, last_y = tx, ty
            else:
                last_x, last_y, added = _add_stitch_limited(
                    pattern,
                    last_x,
                    last_y,
                    tx,
                    ty,
                    min_units,
                    max_units,
                )
                stitch_count += added

        # 行结束强制断开，避免跨行连接
        last_x, last_y = None, None

        y += next_spacing
        row_index += 1

    if any(s[2] == pyembroidery.STITCH for s in pattern.stitches):
        pattern.move_center_to_origin()
    pattern.add_command(pyembroidery.END)
    print(f"总针数: {stitch_count}")

    print("正在导出...")
    return pattern, gray


# 生成针迹浏览预览图（调试用途）
def check_preview(pattern, canvas_size=(400, 400)):
    """将 EmbPattern 绘制到固定大小灰度画布。"""
    preview = np.ones((canvas_size[1], canvas_size[0]), dtype=np.uint8) * 255
    stitches = pattern.stitches
    if not stitches:
        return preview

    # 只取真实 STITCH 点用于计算边界
    xs = [s[0] for s in stitches if s[2] == pyembroidery.STITCH]
    ys = [s[1] for s in stitches if s[2] == pyembroidery.STITCH]
    if not xs:
        return preview

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    range_x = max_x - min_x or 1
    range_y = max_y - min_y or 1
    margin = 20

    def to_px(sx, sy):
        # 将刺绣坐标线性映射到预览画布像素坐标
        px = int((sx - min_x) / range_x * (canvas_size[0] - margin * 2) + margin)
        py = int((sy - min_y) / range_y * (canvas_size[1] - margin * 2) + margin)
        return px, py

    for i in range(len(stitches) - 1):
        s1, s2 = stitches[i], stitches[i + 1]
        if s2[2] == pyembroidery.STITCH:
            pt1 = to_px(s1[0], s1[1])
            pt2 = to_px(s2[0], s2[1])
            cv2.line(preview, pt1, pt2, 0, 1)

    return preview
