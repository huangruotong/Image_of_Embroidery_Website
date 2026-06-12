import base64
import math
import cv2
import numpy as np
import pyembroidery


DEFAULT_PREVIEW_SIZE = (400, 400)
PREVIEW_MARGIN = 20
MAX_STITCHES_CANNY = 80000
MAX_STITCHES_RASTER = 120000
DEFAULT_TRIM_JUMP_MM = 8.0


#把上传图片字节流解码为BGR图像
def get_image(photo):
    nparr = np.frombuffer(photo, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)  #按彩色模式解码图片
    if img is None:
        print("No image")
        return None
    return img  #返回成功解码的图像


#Canny模式
def image_to_embroidery_canny(
    img,
    scale=0.5,
    threshold1=None,
    threshold2=None,
    contrast_boost=1.3,
    min_stitch_mm=0.7,
    max_stitch_mm=6.0,
    mm_per_pixel=0.1,
    max_jump_mm=8.0,
    trim_jump_mm=DEFAULT_TRIM_JUMP_MM,
    canny_sigma=0.33,
    target_width_mm=100.0,
    max_work_long_side=2200,
    return_details=False,
):
    print("Building Canny embroidery pattern...")  #输出当前处理模式
    max_stitches = MAX_STITCHES_CANNY  #最大针数上限

    gray = prepare_public_image(
        img,
        scale=scale,
        max_long_side=max_work_long_side,
    )  #预处理灰度图
    processed_width_px = max(gray.shape[1], 1)
    processed_height_px = max(gray.shape[0], 1)
    if target_width_mm is not None: #如果指定了大小，就来计算对应数值。输入宽度除像素宽等于比例
        mm_per_pixel = float(target_width_mm) / processed_width_px
    gray = prepare_canny_image(gray, contrast_boost=contrast_boost)
    long_side = max(gray.shape[1], gray.shape[0])  #取灰度图长边
    ksize = 5 if long_side < 2500 else 7
    blurred = cv2.GaussianBlur(gray, (ksize, ksize), 0)  #高斯模糊

    #网页中的自动阈值，默认自动开，然后调用计算阈值
    if threshold1 is None or threshold2 is None:
        used_threshold1, used_threshold2 = auto_canny_thresholds(
            blurred,
            sigma=canny_sigma,
        )
    else:
        used_threshold1 = int(threshold1)
        used_threshold2 = int(threshold2)

    
    #轮廓提取
    edges = cv2.Canny(blurred, used_threshold1, used_threshold2)#执行边缘检测
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)  #从边缘图提取轮廓
    contours = filter_canny_contours(contours, long_side) #中值过滤噪点
    contours = simplify_canny_contours(contours, epsilon_px=1.0) #简化

    scale_factor, min_units, max_units, max_jump_units, trim_jump_units = resolve_stitch_units(
        mm_per_pixel,
        min_stitch_mm,
        max_stitch_mm,
        max_jump_mm,
        trim_jump_mm,
    )

    pattern, stats = build_pattern_from_segments(
        collect_canny_segments(contours, scale_factor),  #把轮廓转换成路径列表
        min_units=min_units,  #最小最大针长
        max_units=max_units,
        max_jump_units=max_jump_units,  #最大跳针长度
        trim_jump_units=trim_jump_units,
        max_stitches=max_stitches,  #最大允许针数
    )

    if stats["stitch_count"] >= max_stitches:
        print(f"Warning: hit Canny stitch cap of {max_stitches}.")  #达到针数上限时输出警告

    print(
        "Canny pattern:",  #模式标签
        f"low={used_threshold1}",
        f"high={used_threshold2}",
        f"stitches={stats['stitch_count']}",  #输出总针数，跳针数，剪线数
        f"jumps={stats['jump_count']}",
        f"trims={stats['trim_count']}",
    )
    if return_details:
        return {
            "pattern": pattern,
            "stats": stats,
            "used_threshold1": used_threshold1,
            "used_threshold2": used_threshold2,
            "processed_width_px": processed_width_px,
            "processed_height_px": processed_height_px,
        }
    return pattern  #返回生成好的刺绣图案


#raster模式
def photo_to_raster_embroidery(
    img,
    scale=0.5,
    contrast_boost=1.8,
    mm_per_pixel=0.1, #一个像素等于实际刺绣的0.1mm
    row_spacing=4,
    min_stitch=2,
    max_stitch=12,
    white_threshold=220,
    min_stitch_mm=0.8,
    max_stitch_mm=6.0,
    max_jump_mm=8.0,
    trim_jump_mm=DEFAULT_TRIM_JUMP_MM,
):
    print("Building Raster embroidery pattern...")  #输出当前处理模式
    max_stitches = MAX_STITCHES_RASTER  #最大针数上限

    gray = prepare_public_image(img, scale=scale)  #预处理灰度图
    gray = prepare_raster_image(gray, contrast_boost=contrast_boost)

    scale_factor, min_units, max_units, max_jump_units, trim_jump_units = resolve_stitch_units(
        mm_per_pixel,
        min_stitch_mm,
        max_stitch_mm,
        max_jump_mm,
        trim_jump_mm,
    )

    pattern, stats = build_pattern_from_segments(
        collect_raster_segments(
            gray,  #输入灰度图
            scale_factor,  #坐标缩放因子
            row_spacing,  #行间距
            min_stitch,  #最小像素步长
            max_stitch,  #最大像素步长
            white_threshold,  #背景阈值
        ),
        min_units=min_units,  #最小针长
        max_units=max_units,  #最大针长
        max_jump_units=max_jump_units,  #最大跳针长度
        trim_jump_units=trim_jump_units,
        max_stitches=max_stitches,  #最大允许针数
    )

    if stats["stitch_count"] >= max_stitches:
        print(f"Warning: hit Raster stitch cap of {max_stitches}.")  #达到针数上限时输出警告

    print(
        "Raster pattern:",
        f"stitches={stats['stitch_count']}",
        f"jumps={stats['jump_count']}",
        f"trims={stats['trim_count']}",
    )
    return pattern  #返回生成好的刺绣图案


#把刺绣图案渲染成预览
def pattern_to_data_url(pattern, canvas_size=DEFAULT_PREVIEW_SIZE):
    preview = check_preview(pattern, canvas_size=canvas_size)  #先生成灰度预览图
    _, buffer = cv2.imencode(".png", preview)#将画好的图片存为png格式
    img_b64 = base64.b64encode(buffer).decode("utf-8")
    return f"data:image/png;base64,{img_b64}"


#检查刺绣文件是否有真实落针，有就能导出给用户
def pattern_has_stitches(pattern):
    for x, y, cmd in pattern.stitches:  #遍历图案中的全部针迹记录
        if cmd == pyembroidery.STITCH:  #只要发现真实落针命令，就说明图案不是空的
            return True
    return False


#统计已生成图案的数据，检查图像是否有问题，例落针数，跳针数，剪线数等
def pattern_path_metrics(pattern):
    metrics = {
        "stitch_count": 0,
        "jump_count": 0,
        "trim_count": 0,
        "max_stitch_length_mm": 0.0,
        "max_jump_length_mm": 0.0,
        "max_untrimmed_jump_length_mm": 0.0,
        "max_untrimmed_jump_run_length_mm": 0.0,
        "untrimmed_jump_run_count": 0,
    }

    prev_x = 0.0  #上一针的x,y
    prev_y = 0.0
    thread_trimmed = False
    current_untrimmed_jump_run_mm = 0.0

    #结束当前未剪线跳针段，并更新最长连续跳针统计
    def finalize_untrimmed_jump_run():
        nonlocal current_untrimmed_jump_run_mm
        if current_untrimmed_jump_run_mm <= 1e-6:
            return
        metrics["untrimmed_jump_run_count"] += 1
        metrics["max_untrimmed_jump_run_length_mm"] = max(
            metrics["max_untrimmed_jump_run_length_mm"],
            current_untrimmed_jump_run_mm,
        )
        current_untrimmed_jump_run_mm = 0.0

    for x, y, cmd in pattern.stitches:  #逐条遍历图案中的针迹命令
        if cmd == pyembroidery.TRIM:  #剪线命令只累计次数，不参与距离统计
            metrics["trim_count"] += 1  #记录一次剪线
            finalize_untrimmed_jump_run()
            thread_trimmed = True
            continue

        if cmd not in (pyembroidery.STITCH, pyembroidery.JUMP):  #只处理真实落针和跳针，其他命令跳过
            finalize_untrimmed_jump_run()
            continue

        dist_mm = math.hypot(x - prev_x, y - prev_y) / 10.0  #计算当前点与上一点之间的距离，勾股定理

        if cmd == pyembroidery.STITCH:  #如果是正常落针，则统计落针数和最大针长
            metrics["stitch_count"] += 1  #落针计数加一
            metrics["max_stitch_length_mm"] = max(metrics["max_stitch_length_mm"], dist_mm)  #更新最长针长
            finalize_untrimmed_jump_run()
            thread_trimmed = False
        else:
            metrics["jump_count"] += 1  #跳针计数加一
            metrics["max_jump_length_mm"] = max(metrics["max_jump_length_mm"], dist_mm)  #更新最长跳针
            if not thread_trimmed:
                metrics["max_untrimmed_jump_length_mm"] = max(
                    metrics["max_untrimmed_jump_length_mm"],  #更新跳针长度
                    dist_mm,  #因为没有剪线，所以记录最长一次有多长
                )
                current_untrimmed_jump_run_mm += dist_mm

        prev_x, prev_y = x, y  #更新上一针坐标

    finalize_untrimmed_jump_run()

    return metrics  #返回完整指标结果


#把输入图像转成灰度图，并按比例或最大边长缩小
def prepare_public_image(img, scale=1.0, max_long_side=None):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  #转成灰度图
    height, width = gray.shape[:2]
    resize_scale = float(scale)

    if max_long_side and max(height, width) > max_long_side:
        resize_scale = min(resize_scale, float(max_long_side) / max(height, width))

    if resize_scale < 1.0:
        new_width = max(1, int(width * resize_scale))
        new_height = max(1, int(height * resize_scale))
        gray = cv2.resize(gray, (new_width, new_height), interpolation=cv2.INTER_AREA)

    return gray


#为Canny边缘检测准备图像，先去噪再增强对比度
def prepare_canny_image(gray, contrast_boost=1.3):
    gray = cv2.medianBlur(gray, 3)  #轻度去噪，减少背景纹理和压缩噪声
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))  #温和增强对比度
    gray = clahe.apply(gray)  #提升局部对比度。对比度越大细节少，整体亮度
    gray = cv2.convertScaleAbs(gray, alpha=contrast_boost, beta=-40)  #再做一次整体对比度增强


    return gray


#为Raster扫描模式准备图像，做轻微模糊和整体对比度增强
def prepare_raster_image(gray, contrast_boost=1.8):
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    gray = cv2.convertScaleAbs(gray, alpha=contrast_boost, beta=0)
    return gray


#缩放和单位转换，把毫米转换成刺绣机单位
def resolve_stitch_units(
    mm_per_pixel,
    min_stitch_mm,
    max_stitch_mm,
    max_jump_mm,
    trim_jump_mm=DEFAULT_TRIM_JUMP_MM,
):
    scale_factor = mm_per_pixel * 10.0 #将像素转换成刺绣机单位
    min_units = max(1.0, min_stitch_mm * 10.0)
    max_units = max(min_units, max_stitch_mm * 10.0)
    max_jump_units = max(max_units, max_jump_mm * 10.0)
    trim_jump_units = max(max_units, trim_jump_mm * 10.0)
    return scale_factor, min_units, max_units, max_jump_units, trim_jump_units


#根据图像灰度中位数自动计算Canny低阈值和高阈值，关于自动阈值
def auto_canny_thresholds(gray, sigma=0.33):
    median = float(np.median(gray)) #得灰度图的中间值
    if median <= 1.0: #如果图片为全黑，返回固定值
        return 30, 90

    low = int(max(0, (1.0 - sigma) * median))
    high = int(min(255, (1.0 + sigma) * median))
    if high <= low:
        high = min(255, low + 1)
    return low, high


#过滤掉过短或面积过小的Canny轮廓，减少噪点路径
def filter_canny_contours(contours, long_side):
    min_area = 2.0
    filtered = [] #空列表，来装轮廓

    for contour in contours:
        if len(contour) < 2:
            continue

        area = cv2.contourArea(contour)
        if area < min_area: #面积太少不要
            continue

        filtered.append(contour) #装列表

    return filtered


#简化轮廓点数量，降低后续针迹复杂度，简化值是1
def simplify_canny_contours(contours, epsilon_px=1.0): 
    simplified = [] #保存简化后的轮廓列表，保证有值，零无意义
    epsilon_px = max(0.1, float(epsilon_px)) 

    for contour in contours: #遍历每一条轮廓
        if len(contour) < 3:
            if len(contour) >= 2:
                simplified.append(contour) #放进列表中，形成路径
            continue

        #里面都是大于二的点，简化轮廓功能，删除两个大点中的小点。只要两个点的
        approx = cv2.approxPolyDP(contour, epsilon_px, False) 
        if len(approx) >= 2: #简化之后大于2就保留，两点才一线
            simplified.append(approx)

    return simplified


#把Canny轮廓转换成刺绣坐标路径段
def collect_canny_segments(contours, scale_factor):
    segments = []  #保存Canny转出的路径
    for contour in contours:  #遍历每一条轮廓
        points = [
            (point[0][0] * scale_factor, point[0][1] * scale_factor)  #把像素坐标缩放成刺绣单位
            for point in contour  #处理当前轮廓里的每个点
        ]
        if len(points) >= 2:  #至少需要两个点才能构成路径
            segments.append(points)
    return segments  #返回全部轮廓路径


#从灰度图按行扫描生成Raster路径，并避开边缘区域
def collect_raster_segments(
    gray,
    scale_factor,
    row_spacing,
    min_stitch,
    max_stitch,
    white_threshold,
):
    if min(gray.shape[:2]) >= 3:
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    else:
        blurred = gray
    edge_low, edge_high = auto_canny_thresholds(blurred)
    edges = cv2.Canny(blurred, edge_low, edge_high)
    exclusion_mask = build_edge_exclusion_mask(edges, margin_px=2)
    return collect_raster_segments_masked(
        gray,
        scale_factor,
        row_spacing,
        min_stitch,
        max_stitch,
        white_threshold,
        exclusion_mask,
    )


#根据边缘图生成保护区，防止填充边缘，保护宽度为二像素，为了防止针线过密，导致断线
def build_edge_exclusion_mask(edges, margin_px=2):
    if margin_px <= 0:
        return edges > 0

    kernel_size = max(1, int(margin_px) * 2 + 1) #计算膨胀核大小，公式是为了边缘像素为中心
    kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8) #生成的刷子大小
    dilated = cv2.dilate(edges, kernel, iterations=1) #膨胀，把白色边缘扩大
    return dilated > 0


#根据图片灰度深浅，来横向设计针距，生成路径
def collect_raster_segments_masked(
    gray,
    scale_factor,
    row_spacing, #行间距，设计了四像素，所以隔四扫描一次
    min_stitch,
    max_stitch,
    white_threshold,
    exclusion_mask, #保护区，附件不生成针迹
):
    segments = [] #来保存全部的路径
    height, width = gray.shape

    row_spacing = max(1, int(row_spacing)) #参数保护，防止无意义
    min_stitch = max(1, int(min_stitch))
    max_stitch = max(min_stitch, int(max_stitch))
    white_threshold = int(white_threshold)

    for y in range(0, height, row_spacing): #对图片开始扫描，下面偶数从左往右，奇数相反
        x_values = range(width) if (y // row_spacing) % 2 == 0 else range(width - 1, -1, -1)
        current_segment = [] #这里是收集到有颜色的针路就放进来，白色不要
        i = 0
        x_values = list(x_values)

        while i < len(x_values):
            x = x_values[i]
            pixel = int(gray[y, x]) #判断灰度，大于阈值不要，
            blocked = bool(exclusion_mask[y, x]) if exclusion_mask is not None else False

            if pixel >= white_threshold or blocked: #太白或在保护区不要
                if len(current_segment) >= 2:
                    segments.append(current_segment) #两个点就保存起来
                current_segment = []
                i += 1
                continue

            current_segment.append((x * scale_factor, y * scale_factor)) #缩放坐标后放进当前路径段
            tone = pixel / 255.0 #将灰度值变成小数，为了针距，越小越黑越密
            stitch_gap = int(min_stitch + tone * (max_stitch - min_stitch))
            i += max(stitch_gap, 1)

        if len(current_segment) >= 2:
            segments.append(current_segment) #保存全部的路径

    return segments


#清洗、居中并排序多组路径段，然后写成刺绣图案
def build_pattern_from_segment_groups(
    segment_groups,
    *,
    min_units,
    max_units,
    max_jump_units,
    trim_jump_units,
    max_stitches,
):
    valid_groups = []

    for group in segment_groups:
        normalized_group = []
        for segment in group:
            normalized = normalize_segment(segment, min_units)
            if normalized is not None:
                normalized_group.append(normalized)
        valid_groups.append(normalized_group)

    all_segments = [segment for group in valid_groups for segment in group]
    if not all_segments:
        empty_pattern = pyembroidery.EmbPattern()
        empty_pattern.add_command(pyembroidery.END)
        return empty_pattern, {
            "stitch_count": 0,
            "jump_count": 0,
            "trim_count": 0,
        }

    centered_all = center_segments(all_segments)
    centered_groups = []
    offset = 0
    for group in valid_groups:
        count = len(group)
        centered_groups.append(centered_all[offset:offset + count])
        offset += count

    ordered_segments = []
    for group in centered_groups:
        ordered_segments.extend(order_segments_nearest(group))

    return write_segments_to_pattern(
        ordered_segments,
        min_units=min_units,
        max_units=max_units,
        max_jump_units=max_jump_units,
        trim_jump_units=trim_jump_units,
        max_stitches=max_stitches,
    )


#把单组路径段包装成路径组，再统一构建刺绣图案
def build_pattern_from_segments(
    segments,
    *,
    min_units,
    max_units,
    max_jump_units,
    trim_jump_units,
    max_stitches,
):
    return build_pattern_from_segment_groups(
        [segments],
        min_units=min_units,
        max_units=max_units,
        max_jump_units=max_jump_units,
        trim_jump_units=trim_jump_units,
        max_stitches=max_stitches,
    )


#去除重复点并过滤过短路径
def normalize_segment(points, min_path_length):
    normalized = []  #保存去重后的路径点

    for x, y in points:  #逐点清洗路径
        point = (float(x), float(y))  #统一转成浮点坐标
        if not normalized:
            normalized.append(point)  #如果为空，则是第一个点，直接保存
            continue
        last_x, last_y = normalized[-1]  #一直取出最后一个点

        if math.hypot(point[0] - last_x, point[1] - last_y) > 1e-6: #勾股定理，距离太小就不保留，相当于重复点
            normalized.append(point)

    if len(normalized) < 2:  #去重后如果点数不足，则路径无效，一条线要两点
        return None

    if segment_path_length(normalized) < min_path_length: #进入下一个函数，查看是否整段路径过短
        return None
    return normalized  #返回清洗后的有效路径


#计算一段路径中所有相邻点之间的总长度
def segment_path_length(points):
    if len(points) < 2:  #传进来的点少于两个，直接返回零
        return 0.0
    return sum( #依次计算相邻两个点的距离，两个点的距离用勾股，然后相加
        math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1])
        for i in range(1, len(points))  #从第二个点开始累加
    )


#把所有路径段整体平移到以外接框为原点的位置
def center_segments(segments):
    if not segments:  #没有路径时直接返回空列表
        return []

    xs = [] #收集所有坐标
    ys = []
    for segment in segments:  #收集所有点的x,y
        for x, y in segment:
            xs.append(x)
            ys.append(y)

    center_x = (min(xs) + max(xs)) / 2.0 #找最左最右的值，得到中心点坐标，这是横向
    center_y = (min(ys) + max(ys)) / 2.0 #垂直向

    centered_segments = [] #保存平移后的路径
    for segment in segments:  #对全部路径逐段处理
        new_segment = []
        for x, y in segment: #原来的坐标减去中心点坐标，这样图案能平移到中心
            new_segment.append((x - center_x, y - center_y)) 
        centered_segments.append(new_segment)

    return centered_segments


#使用最近邻算法对路径段进行排序，减少跳针距离
def order_segments_nearest(segments):
    left_segments = []  #复制一份待处理路径
    for segment in segments:
        left_segments.append(list(segment))

    ordered_segments = []  #保存排序后的结果

    current_x = 0.0  #当前针头x,y
    current_y = 0.0

    #只要还有未处理路径，就一直循环，每次循环都从剩下路径中选择离针头最近的一段
    while left_segments:
        nearest_index = -1  #当前最优路径索引
        nearest_distance = None  #当前最短距离
        reverse_flag = False  #当前路径是否需要反转来绣。针头离终点近，从终点开始绣就是反转

        #遍历所有剩余路径，寻找最近端点
        for i in range(len(left_segments)):
            one_segment = left_segments[i]

            start_x = one_segment[0][0]  #当前路径起点和终点
            start_y = one_segment[0][1]
            end_x = one_segment[-1][0]
            end_y = one_segment[-1][1]

            #计算当前针头到这段路径起点和终点，勾股
            distance_to_start = math.hypot(start_x - current_x, start_y - current_y)  
            distance_to_end = math.hypot(end_x - current_x, end_y - current_y)  

            if nearest_distance is None: #第一次循环先把第一个路径当成最优路径
                nearest_index = i
                nearest_distance = distance_to_start
                reverse_flag = False

            if distance_to_start < nearest_distance: #如果当前路径起点离针头更近，就更新成这个路径为最优
                nearest_index = i
                nearest_distance = distance_to_start
                reverse_flag = False

            if distance_to_end < nearest_distance: #如离终点针头近，更新，反转绣
                nearest_index = i
                nearest_distance = distance_to_end
                reverse_flag = True

        chosen_segment = left_segments.pop(nearest_index) #把最优路径从待处理列表中取出

        if reverse_flag:
            chosen_segment.reverse()  #反转路径方向

        ordered_segments.append(chosen_segment) #把选好的路径放进结果列表

        current_x = chosen_segment[-1][0]  #更新当前针头位置
        current_y = chosen_segment[-1][1]

    return ordered_segments  #返回排序后的路径列表


#把排序后的路径段写入刺绣图案，同时统计落针、跳针和剪线数量
def write_segments_to_pattern(
    segments,
    *,
    min_units,
    max_units,
    max_jump_units,
    trim_jump_units,
    max_stitches,
):
    pattern = pyembroidery.EmbPattern()  #创建新刺绣
    stitch_count = 0
    jump_count = 0
    trim_count = 0
    current_x = 0.0  #当前针头的x,y
    current_y = 0.0

    for segment in segments:  #按顺序把每一段路径写入图案
        if stitch_count >= max_stitches:  #达到针数上限后停止继续写入
            break

        start_x, start_y = segment[0]  #当前路径段起点
        if stitch_count == 0:
            pattern.add_stitch_absolute(pyembroidery.STITCH, start_x, start_y) #第一针下针
            stitch_count += 1
            current_x, current_y = start_x, start_y #记录针头位置
        else:
            travel_dist = math.hypot(start_x - current_x, start_y - current_y)  #计算到起点的移动距离

            if travel_dist > trim_jump_units: #距离超过剪线值，就先剪线再跳
                pattern.add_command(pyembroidery.TRIM)
                trim_count += 1  #记录剪线次数

            current_x, current_y, added_jumps = add_jump_limited(
                pattern,  #当前图案对象
                current_x,
                current_y,
                start_x,
                start_y,
                max_jump_units,
            )
            jump_count += added_jumps  #累加跳针数

            if stitch_count < max_stitches:
                pattern.add_stitch_absolute(pyembroidery.STITCH, start_x, start_y)
                stitch_count += 1
                current_x, current_y = start_x, start_y

        for tx, ty in segment[1:]:  #从第二个点开始，把路径段写成真实落针
            if stitch_count >= max_stitches:
                break
            current_x, current_y, added = add_stitch_limited( #为了针头移动新位置
                pattern,
                current_x,
                current_y,
                tx,  #目标点 x
                ty,
                min_units,
                max_units,
            )
            stitch_count += added  #累加新增针数

    pattern.add_command(pyembroidery.END)
    return pattern, {
        "stitch_count": stitch_count,  #最终落针数
        "jump_count": jump_count,
        "trim_count": trim_count,
        "truncated": stitch_count >= max_stitches,
        "max_stitches": max_stitches,
    }


#超过了最长针，就拆分
def add_stitch_limited(pattern, last_x, last_y, tx, ty, min_units, max_units):
    dist = math.hypot(tx - last_x, ty - last_y)  #计算当前位置到目标点的距离，勾股定理
    if dist < min_units:
        return last_x, last_y, 0  #距离过短时不生成针迹

    steps = 1  #默认只需要跳一次
    if max_units > 0 and dist > max_units:
        steps = int(math.ceil(dist / max_units))  #距离过大时拆成多段跳针

    added = 0  #统计本次新增的针数

    for step in range(1, steps + 1):  #通过上面算的分段结果，来决定循环几次
        nx = last_x + (tx - last_x) * (step / steps) #这里是公式，中间是目标坐标。值看坐标
        ny = last_y + (ty - last_y) * (step / steps)
        pattern.add_stitch_absolute(pyembroidery.STITCH, nx, ny) #下针，移动到位置了
        added += 1  #累计针数

    return tx, ty, added  #返回更新后的位置和新增针数


#跳针到目标位置
def add_jump_limited(pattern, last_x, last_y, tx, ty, max_units):
    dist = math.hypot(tx - last_x, ty - last_y)  #计算当前位置到目标点的距离，勾股定理
    if dist <= 1e-6:
        return last_x, last_y, 0  #距离过短时不生成跳针

    steps = 1  #默认只需要跳一次
    if max_units > 0 and dist > max_units: #距离过大时拆成多段跳针
        steps = int(math.ceil(dist / max_units)) #向上取整，但要在范围内

    added = 0

    for step in range(1, steps + 1): #通过上面算的分段结果，来决定循环几次
        nx = last_x + (tx - last_x) * (step / steps) #这里是公式，中间是目标坐标。值看坐标
        ny = last_y + (ty - last_y) * (step / steps)
        pattern.add_stitch_absolute(pyembroidery.JUMP, nx, ny)  #跳针
        added += 1  #累计跳针数

    return tx, ty, added  #返回更新后的位置和新增跳针数


#生成刺绣预览图
def check_preview(pattern, canvas_size=DEFAULT_PREVIEW_SIZE):
    preview = np.ones((canvas_size[1], canvas_size[0]), dtype=np.uint8) * 255  #创建白底预览图
    stitches = pattern.stitches  #读取图案中的全部针迹
    if not stitches:
        return preview #无针迹返回空白浏览

    xs = [x for x, _, cmd in stitches if cmd == pyembroidery.STITCH]  #收集所有真实落针的x坐标，横杠是不需要所以不看
    ys = [y for _, y, cmd in stitches if cmd == pyembroidery.STITCH]
    if not xs:
        return preview

    min_x, max_x = min(xs), max(xs)  #找最上下左右的坐标
    min_y, max_y = min(ys), max(ys)
    range_x = max_x - min_x or 1  #计算图像横向占了多宽，或者为0就为1
    range_y = max_y - min_y or 1
    margin = PREVIEW_MARGIN  #给预览图四周保留边距

    #把刺绣坐标转换成像素坐标
    def to_px(sx, sy): #原始坐标剪最小坐标，会得到位置
        px = int((sx - min_x) / range_x * (canvas_size[0] - margin * 2) + margin)  #把 x 坐标映射到画布像素
        py = int((sy - min_y) / range_y * (canvas_size[1] - margin * 2) + margin)
        return px, py  #返回像素坐标

    #逐对检查相邻针迹并绘制真实落针线段
    for i in range(len(stitches) - 1):
        s1 = stitches[i]  #当前针迹，下一个，取相邻的
        s2 = stitches[i + 1]  
        if s1[2] == pyembroidery.STITCH and s2[2] == pyembroidery.STITCH: #连续的两个坐标下针了才连接起来
            pt1 = to_px(s1[0], s1[1]) #刺绣坐标变成像素坐标
            pt2 = to_px(s2[0], s2[1])  
            cv2.line(preview, pt1, pt2, 0, 1)  #在预览图上画出黑色，像素为一的线段

    return preview  #返回绘制完成的预览图
