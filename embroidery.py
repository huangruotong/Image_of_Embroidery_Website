import cv2
import numpy as np
import pyembroidery
import math


def _add_stitch_limited(pattern, last_x, last_y, tx, ty, min_units, max_units):
    if last_x is None or last_y is None:
        return last_x, last_y, 0

    dist = math.hypot(tx - last_x, ty - last_y)
    if dist < min_units:
        return last_x, last_y, 0

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


def get_image(photo):
    nparr = np.frombuffer(photo, np.uint8) #讲二进制数据转换为数组
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR) #用imr解码数组成彩色图像3个通道

    if img is None:
        print("No image")
        return None

    return img #返回解码之后的图像



def image_to_embroidery_canny(img, #canny边缘法，outline
                        scale=0.5, threshold1=50, threshold2=150,
                        min_stitch_mm=0.8, max_stitch_mm=6.0):
    print("正在读取图片...")

    # 1. 缩放图片
    h, w = img.shape[:2]
    new_w, new_h = int(w * scale), int(h * scale)
    img = cv2.resize(img, (new_w, new_h))
    print(f"   尺寸: {new_w}x{new_h}")

    # 2. 边缘检测
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, threshold1, threshold2)

    # 3. 提取轮廓
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    # 4. 生成针脚
    pattern = pyembroidery.EmbPattern()
    stitch_count = 0

    # 刺绣坐标单位是 0.1mm
    pixel_to_emb_unit = 1.0
    min_units = max(1.0, min_stitch_mm * 10.0)
    max_units = max(min_units, max_stitch_mm * 10.0)

    for contour in contours:
        if len(contour) < 5:
            continue

        start_pt = contour[0][0]
        start_x = start_pt[0] * pixel_to_emb_unit
        start_y = start_pt[1] * pixel_to_emb_unit
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

    pattern.add_stitch_absolute(pyembroidery.END, 0, 0)

    print(f"Canny 模式针数: {stitch_count}")
    return pattern


'''
if __name__ == "__main__":
    image_to_embroidery(
        image_path=r"E:\python code\davidwhite.jpg",
        output_path="my_embroidery"
    )'''



def photo_to_raster_embroidery(img, #raster法
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
                               trim_gap_threshold=8):
    print("正在读取照片...")

    # 1. 图像预处理
    img = cv2.resize(img, None, fx=scale, fy=scale)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 增强对比度，让黑白分明
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.convertScaleAbs(gray, alpha=contrast_boost, beta=-50)

    h, w = gray.shape
    # 刺绣单位通常是 0.1mm
    scale_factor = mm_per_pixel * 10
    pattern = pyembroidery.EmbPattern()

    print("正在计算 Raster 针迹...")
    stitch_count = 0
    last_x, last_y = None, None
    gap_run = 0
    min_units = max(1.0, min_stitch_mm * 10.0)
    max_units = max(min_units, max_stitch_mm * 10.0)
    max_jump_units = max(max_units, max_jump_mm * 10.0)

    for y in range(0, h, row_spacing):
        # 蛇形路径逻辑：偶数行从左往右，奇数行从右往左
        is_reverse = (y // row_spacing) % 2 != 0
        x_range = range(w - 1, -1, -1) if is_reverse else range(0, w)
        x_list = list(x_range)

        i = 0
        while i < len(x_list):
            x = x_list[i]
            pixel = int(gray[y, x])

            # 跳过过亮的区域（白色背景）
            if pixel >= white_threshold:
                if last_x is not None:
                    gap_run += 1
                i += 1
                continue

            # 转换为刺绣物理坐标
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

            # 根据像素亮度决定下一个针点的间距
            # 越黑(0) i 增加越小 -> 针脚越密
            t = pixel / white_threshold
            stitch_gap = int(min_stitch + t * (max_stitch - min_stitch))
            i += max(stitch_gap, 1)

    # 关键步骤：将图案中心移至 (0,0)，否则刺绣机可能报错
    pattern.move_center_to_origin()
    pattern.add_command(pyembroidery.END)

    print(f"总针数: {stitch_count}")

    # 2. 导出文件
    return pattern, gray

'''
    print("正在生成预览图...") # 3. 生成更直观的预览图
    preview = np.ones((h, w), dtype=np.uint8) * 255
    # 由于做了平移，预览图需要重新计算坐标映射，这里简化处理
    for i in range(len(pattern.stitches) - 1):
        s1, s2 = pattern.stitches[i], pattern.stitches[i + 1]
        if s2[2] == pyembroidery.STITCH:
            # 还原回像素坐标进行绘制
            pt1 = (int(s1[0] / scale_factor + w / 2), int(s1[1] / scale_factor + h / 2))
            pt2 = (int(s2[0] / scale_factor + w / 2), int(s2[1] / scale_factor + h / 2))
            cv2.line(preview, pt1, pt2, (0), 1)

    cv2.imwrite(f"{output_path}_preview.png", preview)
    print(f"处理完成！")'''

'''
# ── 修正：把主程序移出函数 ──────────────────
if __name__ == "__main__":
    photo_to_raster_embroidery(
        image_path=r"E:\python code\white.jpg",
        output_path="result_raster",
        scale=0.5,
        row_spacing=5,  # 行距越大，缝纫越快，但细节越少
        min_stitch=3,  # 黑色部分每 3 像素一针
        max_stitch=15  # 灰色部分每 15 像素一针
    )'''


def photo_to_line_embroidery(img, #line法
                             scale=0.5,
                             contrast_boost=1.8,
                             mm_per_pixel=0.1,
                             min_spacing=2,
                             max_spacing=15,
                             white_threshold=230,
                             min_stitch_mm=0.8,
                             max_stitch_mm=6.0,
                             max_jump_mm=8.0):



    # 图像预处理
    img = cv2.resize(img, None, fx=scale, fy=scale)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.convertScaleAbs(gray, alpha=contrast_boost, beta=-50)

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
        # 计算这一整行的平均亮度
        row_brightness = float(np.mean(gray[y, :]))

        # 整行太白就跳过
        if row_brightness >= white_threshold:
            y += max_spacing
            row_index += 1
            continue

        # 平均亮度 -> 下一行的间距
        # 行越暗 -> 间距越小 -> 行越密
        # 行越亮 -> 间距越大 -> 行越疏
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

            # 单个像素太白就断开
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
                dist = math.hypot(tx - last_x, ty - last_y)
                if dist > max_jump_units:
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

        # 行结束后重置，防止下一行首针和上一行尾针连接
        last_x, last_y = None, None

        y += next_spacing
        row_index += 1

    pattern.add_command(pyembroidery.END)
    print(f"总针数: {stitch_count}")

    print("正在导出...")
    return pattern, gray

''' #生成预览图
    print("  正在生成预览图...")
    preview = np.ones((h, w), dtype=np.uint8) * 255
    for i in range(len(pattern.stitches) - 1):
        s1 = pattern.stitches[i]
        s2 = pattern.stitches[i + 1]
        x1 = max(0, min(w - 1, int(s1[0] / scale_factor)))
        y1 = max(0, min(h - 1, int(s1[1] / scale_factor)))
        x2 = max(0, min(w - 1, int(s2[0] / scale_factor)))
        y2 = max(0, min(h - 1, int(s2[1] / scale_factor)))
        if s2[2] == pyembroidery.STITCH:
            cv2.line(preview, (x1, y1), (x2, y2), 0, 1)

    cv2.imwrite(f"{output_path}_preview.png", preview)
    print(f"完成！输出文件：{output_path}.dst")'''

#生成浏览图
def check_preview(pattern, canvas_size=(400,400)):
    preview = np.ones((canvas_size[1], canvas_size[0]), dtype=np.uint8) * 255
    stitches = pattern.stitches
    if not stitches:
        return preview

    # 计算针迹的范围，自动缩放到预览图里
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



'''
if __name__ == "__main__":
    photo_to_line_embroidery(

        scale=0.5,
        contrast_boost=1.8,
        mm_per_pixel=0.1,
        min_spacing=2,      # 最密行间距（最黑的区域）
        max_spacing=15,     # 最疏行间距（最浅的区域）
        white_threshold=230 # 超过这个亮度跳过
    )'''