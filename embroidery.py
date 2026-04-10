import cv2
import numpy as np  
import pyembroidery  
import base64  
import math  

DEFAULT_PREVIEW_SIZE = (400, 400)
PREVIEW_MARGIN = 20
MAX_STITCHES_CANNY = 80000
MAX_STITCHES_LINE_RASTER = 120000

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
    threshold1=50,
    threshold2=150,
    contrast_boost=1.8,
    min_stitch_mm=0.8,
    max_stitch_mm=6.0,
    mm_per_pixel=0.1,
    max_jump_mm=8.0,
):
    print("Building Canny embroidery pattern...")  #输出当前处理模式
    max_stitches = MAX_STITCHES_CANNY  #最大针数上限

    gray = _prepare_gray_image(img, scale=scale, contrast_boost=contrast_boost)  #预处理灰度图
    long_side = max(gray.shape[1], gray.shape[0])  #取灰度图长边
    ksize = max(3, int(long_side / 200) * 2 + 1)  #动态生成奇数高斯核
    blurred = cv2.GaussianBlur(gray, (ksize, ksize), 0)  #高斯模糊

    edges = cv2.Canny(blurred, threshold1, threshold2)  #执行边缘检测
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)  #从边缘图提取轮廓
    contours = [c for c in contours if len(c) >= 2 and cv2.contourArea(c) >= 2.0]  #过滤掉无效小轮廓

    scale_factor, min_units, max_units, max_jump_units = _resolve_stitch_units(
        mm_per_pixel,
        min_stitch_mm,
        max_stitch_mm,
        max_jump_mm,
    )

    pattern, stats = _build_pattern_from_segments(
        _collect_canny_segments(contours, scale_factor),  #把轮廓转换成路径列表
        min_units=min_units,  #最小针长
        max_units=max_units,  #最大针长
        max_jump_units=max_jump_units,  #最大跳针长度
        max_stitches=max_stitches,  #最大允许针数
    )

    if stats["stitch_count"] >= max_stitches:
        print(f"Warning: hit Canny stitch cap of {max_stitches}.")  #达到针数上限时输出警告

    print(
        "Canny pattern:",  #模式标签
        f"stitches={stats['stitch_count']}",  #输出总针数
        f"jumps={stats['jump_count']}",  #输出跳针数
        f"trims={stats['trim_count']}",  #输出剪线数
    )
    return pattern  #返回生成好的刺绣图案

#raster模式
def photo_to_raster_embroidery(
    img,
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
):
    print("Building Raster embroidery pattern...")  
    max_stitches = MAX_STITCHES_LINE_RASTER  #最大针数上限

    gray = _prepare_gray_image(img, scale=scale, contrast_boost=contrast_boost)  #预处理灰度图

    scale_factor, min_units, max_units, max_jump_units = _resolve_stitch_units(
        mm_per_pixel,
        min_stitch_mm,
        max_stitch_mm,
        max_jump_mm,
    )

    pattern, stats = _build_pattern_from_segments(
        _collect_raster_segments(
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

#line模式
def photo_to_line_embroidery(
    img,
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
    print("Building Line embroidery pattern...")  
    max_stitches = MAX_STITCHES_LINE_RASTER  #最大针数上限

    gray = _prepare_gray_image(img, scale=scale, contrast_boost=contrast_boost)  

    scale_factor, min_units, max_units, max_jump_units = _resolve_stitch_units(
        mm_per_pixel,
        min_stitch_mm,
        max_stitch_mm,
        max_jump_mm,
    )

    pattern, stats = _build_pattern_from_segments(
        _collect_line_segments(
            gray,  
            scale_factor,  
            min_spacing,  
            max_spacing,  
            white_threshold,  
        ),
        min_units=min_units,  
        max_units=max_units,  
        max_jump_units=max_jump_units,  
        max_stitches=max_stitches,  
    )

    if stats["stitch_count"] >= max_stitches:
        print(f"Warning: hit Line stitch cap of {max_stitches}.")  

    print(
        "Line pattern:",  
        f"stitches={stats['stitch_count']}", 
        f"jumps={stats['jump_count']}",  
        f"trims={stats['trim_count']}",  
    )
    return pattern

#把刺绣图案渲染成预览
def pattern_to_data_url(pattern, canvas_size=DEFAULT_PREVIEW_SIZE):
    preview = _check_preview(pattern, canvas_size=canvas_size)  #先生成灰度预览图
    _, buffer = cv2.imencode(".png", preview)  
    img_b64 = base64.b64encode(buffer).decode("utf-8")  
    return f"data:image/png;base64,{img_b64}"  

#检查刺绣文件是否有真实落针，有就能导出给用户
def pattern_has_stitches(pattern):
    for x, y, cmd in pattern.stitches: #遍历图案中的全部针迹记录
        if cmd == pyembroidery.STITCH: #只要发现真实落针命令，就说明图案不是空的
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
        "design_width_mm": 0.0,  #设计宽度
        "design_height_mm": 0.0,  #设计高度
        "design_area_mm2": 0.0,  #设计面积
        "stitch_density_per_mm2": 0.0,  #每平方毫米的针迹密度
    }

    prev_x = 0.0  #上一针的x,y
    prev_y = 0.0  
    prev_cmd = None  #上一条针迹命令
    stitch_points = []  #用于统计设计尺寸的真实落针点

    for x, y, cmd in pattern.stitches: #逐条遍历图案中的针迹命令
        if cmd == pyembroidery.TRIM: #剪线命令只累计次数，不参与距离统计
            metrics["trim_count"] += 1  #记录一次剪线
            prev_cmd = cmd  #更新上一条命令
            continue  

        if cmd not in (pyembroidery.STITCH, pyembroidery.JUMP): #只处理真实落针和跳针，其他命令跳过
            prev_cmd = cmd  #仍然更新状态，跳过不相关命令
            continue  

        dist_mm = math.hypot(x - prev_x, y - prev_y) / 10.0  #计算当前点与上一点之间的距离，勾股定理

        if cmd == pyembroidery.STITCH:  #如果是正常落针，则统计落针数和最大针长
            metrics["stitch_count"] += 1  #落针计数加一
            metrics["max_stitch_length_mm"] = max(metrics["max_stitch_length_mm"], dist_mm)  #更新最长针长
            stitch_points.append((x, y))  #保存落针点

        else:
            metrics["jump_count"] += 1  #跳针计数加一
            metrics["max_jump_length_mm"] = max(metrics["max_jump_length_mm"], dist_mm)  #更新最长跳针
            
            if prev_cmd != pyembroidery.TRIM: #只有上一条不是剪线时，才统计未剪线跳针长度
                metrics["max_untrimmed_jump_length_mm"] = max(
                    metrics["max_untrimmed_jump_length_mm"],  #更新跳针长度
                    dist_mm,  #因为没有剪线，所以记录最长一次有多长
                )

        prev_x, prev_y = x, y  #更新上一针坐标,命令
        prev_cmd = cmd  

    #只有存在真实落针时，才计算设计尺寸和密度
    if stitch_points:
        xs = [x for x, _ in stitch_points]  #提取所有落针点的x,y坐标，列表推导式
        ys = [y for _, y in stitch_points]  
        metrics["design_width_mm"] = (max(xs) - min(xs)) / 10.0  #得到图像的宽，高
        metrics["design_height_mm"] = (max(ys) - min(ys)) / 10.0  
        metrics["design_area_mm2"] = metrics["design_width_mm"] * metrics["design_height_mm"]  #计算面积
        
        if metrics["design_area_mm2"] > 1e-6: #面积大于0时，计算针迹密度
            metrics["stitch_density_per_mm2"] = (
                metrics["stitch_count"] / metrics["design_area_mm2"]  #用总针数除以总面积
            ) #为了防止面积过小

    return metrics  #返回完整指标结果

def _prepare_gray_image(img, scale, contrast_boost):
    #如果缩放比例不是 1，就先按比例调整尺寸
    if scale != 1.0:
        height, width = img.shape[:2]  #读取原图高宽
        new_width = max(1, int(round(width * scale)))  #计算缩放后的宽，高
        new_height = max(1, int(round(height * scale)))  
        img = cv2.resize(img, (new_width, new_height))  #执行缩放

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  #转成灰度图
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))  #增强对比度
    gray = clahe.apply(gray)  #提升局部对比度
    gray = cv2.convertScaleAbs(gray, alpha=contrast_boost, beta=-50)  #再做一次整体对比度增强

    low_p = np.percentile(gray, 5)  #取 5% 分位值作为低端裁剪点
    high_p = np.percentile(gray, 95)  #取 95% 分位值作为高端裁剪点
    
    if high_p > low_p: ##如果分位范围有效，则重新拉伸灰度分布
        gray = np.clip(
            (gray.astype(np.float32) - low_p) / (high_p - low_p) * 255,  #把中间区间映射到 0 到 255
            0,  #下限裁剪到0，上限为255
            255,  
        ).astype(np.uint8)  #转回灰度图

    return gray  #返回预处理后的灰度图

def _resolve_stitch_units(mm_per_pixel, min_stitch_mm, max_stitch_mm, max_jump_mm):
    scale_factor = mm_per_pixel * 10.0
    min_units = max(1.0, min_stitch_mm * 10.0)
    max_units = max(min_units, max_stitch_mm * 10.0)
    max_jump_units = max(max_units, max_jump_mm * 10.0)
    return scale_factor, min_units, max_units, max_jump_units

def _collect_canny_segments(contours, scale_factor):
    segments = []  #保存Canny转出的路径
    for contour in contours: #遍历每一条轮廓
        points = [
            (point[0][0] * scale_factor, point[0][1] * scale_factor)  #把像素坐标缩放成刺绣单位
            for point in contour  #处理当前轮廓里的每个点
        ]
        if len(points) >= 2: #至少需要两个点才能构成路径
            segments.append(points)
    return segments  #返回全部轮廓路径

def _collect_raster_segments(gray, scale_factor, row_spacing, min_stitch, max_stitch, white_threshold):
    segments = []  #保存raster模式提取出的路径
    height, width = gray.shape  #读取灰度图尺寸

    for y in range(0, height, row_spacing): #按给定行间距逐行扫描图像
        is_reverse = (y // row_spacing) % 2 != 0  #使用蛇形扫描减少空跑
        x_values = list(range(width - 1, -1, -1) if is_reverse else range(width))  #根据方向生成扫描顺序
        current_segment = []  #当前连续深色段
        i = 0  #手动控制索引，便于按stitch_gap跳步

        while i < len(x_values): #扫描当前行上的采样点
            x = x_values[i]  #当前采样点 x 坐标
            pixel = int(gray[y, x])  #当前像素灰度值

            #足够亮的像素视为背景，当前段结束
            if pixel >= white_threshold:
                if current_segment:
                    segments.append(current_segment)  #保存当前路径段
                    current_segment = []  #清空缓存
                i += 1  #背景区只前进一步
                continue  #继续扫描下一点

            current_segment.append((x * scale_factor, y * scale_factor))  #把当前点加入路径
            tone = pixel / 255.0  #把灰度映射到 0 到 1
            stitch_gap = int(min_stitch + tone * (max_stitch - min_stitch))  #根据亮度动态决定步长
            i += max(stitch_gap, 1)  #至少前进 1，防止死循环

        #当前行结束后，如果还有未提交路径则保存
        if current_segment:
            segments.append(current_segment)

    return segments  #返回全部路径

def _collect_line_segments(gray, scale_factor, min_spacing, max_spacing, white_threshold):
    segments = []  #保存line提取出的路径
    height, width = gray.shape  #读取灰度图尺寸
    y = 0  #从第一行开始扫描
    row_index = 0  #记录扫描行序号，用于交替方向

    #逐行或按跳步扫描，直到图像底部
    while y < height:
        row_brightness = float(np.mean(gray[y, :]))  #计算当前行平均亮度
        if row_brightness >= white_threshold:
            y += max_spacing  #亮背景区域快速跳过
            row_index += 1  #行序号同步递增，并继续下一行
            continue  

        tone = min(max(row_brightness / max(white_threshold, 1), 0.0), 1.0)  #把亮度归一化到 0 到 1
        next_spacing = int(min_spacing + tone * (max_spacing - min_spacing))  #计算下一次扫描的行距
        next_spacing = max(next_spacing, min_spacing)  #保证不小于最小行距

        x_values = range(width) if row_index % 2 == 0 else range(width - 1, -1, -1)  #使用蛇形扫描
        current_segment = []  #当前连续线段

        #扫描当前行上的全部像素
        for x in x_values:
            pixel = int(gray[y, x])  #当前像素灰度值
            if pixel >= white_threshold:
                if current_segment:
                    segments.append(current_segment)  #当前线段结束，加入结果
                    current_segment = []  #清空缓存
                continue  #背景像素跳过

            current_segment.append((x * scale_factor, y * scale_factor))  #深色像素加入当前线段

        #当前行结束后，如有残余线段则保存
        if current_segment:
            segments.append(current_segment)

        y += next_spacing  #跳到下一条扫描行
        row_index += 1  #行序号加一

    return segments  #返回全部线稿路径

def _build_pattern_from_segments(
    segments,
    *,
    min_units,
    max_units,
    max_jump_units,
    max_stitches,
):
    valid_segments = []  #保存过滤后的有效路径
    
    for segment in segments: #逐段清洗输入路径
        normalized = _normalize_segment(segment, min_units)  #去重并过滤过短路径
        if normalized is not None:
            valid_segments.append(normalized)

    if not valid_segments: #如果没有有效路径，则返回空图案
        empty_pattern = pyembroidery.EmbPattern()  
        empty_pattern.add_command(pyembroidery.END)  
        return empty_pattern, {
            "stitch_count": 0,  
            "jump_count": 0,  
            "trim_count": 0,  
        }

    centered_segments = _center_segments(valid_segments)  #先把路径整体居中
    ordered_segments = _order_segments_nearest(centered_segments)  #再按最近邻顺序排列
    return _write_segments_to_pattern(
        ordered_segments,  #传入排好序的路径
        min_units=min_units,  
        max_units=max_units,  
        max_jump_units=max_jump_units,  
        max_stitches=max_stitches,  
    )

def _normalize_segment(points, min_path_length):
    normalized = []  #保存去重后的路径点
    
    for x, y in points:#逐点清洗路径
        point = (float(x), float(y))  #统一转成浮点坐标
        if not normalized:
            normalized.append(point)  #第一个点直接保留，并继续下一个点
            continue  
        last_x, last_y = normalized[-1]  #取出上一个保留点
        
        if math.hypot(point[0] - last_x, point[1] - last_y) > 1e-6: #只有和上一个点有明显距离时，才保留当前点
            normalized.append(point)

    if len(normalized) < 2: #去重后如果点数不足，则路径无效
        return None
    
    if _segment_path_length(normalized) < min_path_length: #如果整段路径过短，也视为无效
        return None
    return normalized  #返回清洗后的有效路径

def _segment_path_length(points):

    if len(points) < 2: #少于两个点时，不构成有效路径
        return 0.0
    return sum(
        math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1])  #计算相邻两点的距离
        for i in range(1, len(points))  #从第二个点开始累加
    )

def _center_segments(segments):
    
    if not segments: #没有路径时直接返回空列表
        return []

    xs = [x for segment in segments for x, _ in segment]  #收集所有点的x,y
    ys = [y for segment in segments for _, y in segment] 
    center_x = (min(xs) + max(xs)) / 2.0  #计算整体中心x,y
    center_y = (min(ys) + max(ys)) / 2.0  

    return [
        [(x - center_x, y - center_y) for x, y in segment]  #把每段路径平移到中心附近
        for segment in segments  #对全部路径逐段处理
    ]

#使用最近邻算法对路径段进行排序，减少跳针距离
def _order_segments_nearest(segments):
   
    if len(segments) <= 1:
        return segments

    remaining = [list(segment) for segment in segments]  #复制一份待处理路径
    ordered = []  #保存排序后的结果
    current_x = 0.0  #当前针头x,y
    current_y = 0.0  

    #只要还有未处理路径，就不断选择最近的一段
    while remaining:
        best_index = 0  #当前最优路径索引
        best_distance = None  #当前最短距离
        best_reversed = False  #当前最优路径是否需要反转

        #遍历所有剩余路径，寻找最近端点
        for index, segment in enumerate(remaining):
            start_x, start_y = segment[0]  #当前路径起点和终点
            end_x, end_y = segment[-1]  

            dist_to_start = math.hypot(start_x - current_x, start_y - current_y)  #到起点的距离
            dist_to_end = math.hypot(end_x - current_x, end_y - current_y)  #到终点的距离

            if best_distance is None or dist_to_start < best_distance:
                best_index = index
                best_distance = dist_to_start
                best_reversed = False

            if dist_to_end < best_distance: #如果终点更近，则改用反向缝制
                best_index = index 
                best_distance = dist_to_end
                best_reversed = True

        next_segment = remaining.pop(best_index)  #取出最优路径
        if best_reversed:
            next_segment = list(reversed(next_segment))  #反转路径方向
        ordered.append(next_segment)  #追加到结果
        current_x, current_y = next_segment[-1]  #更新当前针头位置

    return ordered  #返回排序后的路径列表

def _write_segments_to_pattern(
    segments,
    *,
    min_units,
    max_units,
    max_jump_units,
    max_stitches,
):
    pattern = pyembroidery.EmbPattern()  #创建新刺绣
    stitch_count = 0  
    jump_count = 0  
    trim_count = 0  
    current_x = 0.0  #当前针头的x,y
    current_y = 0.0  

    for index, segment in enumerate(segments): #按顺序把每一段路径写入图案
        
        if stitch_count >= max_stitches: #达到针数上限后停止继续写入
            break

        start_x, start_y = segment[0]  #当前路径段起点
        travel_dist = math.hypot(start_x - current_x, start_y - current_y)  #计算到起点的移动距离

        if index > 0 and travel_dist > max_jump_units: #跨段移动过长时，先插入一次剪线
            pattern.add_command(pyembroidery.TRIM) 
            trim_count += 1  #记录剪线次数

        current_x, current_y, added_jumps = _add_jump_limited(
            pattern,  #当前图案对象
            current_x,  
            current_y,  
            start_x,  
            start_y,  
            max_jump_units,  
        )
        jump_count += added_jumps  #累加跳针数

        for tx, ty in segment[1:]: #从第二个点开始，把路径段写成真实落针
            if stitch_count >= max_stitches:
                break
            current_x, current_y, added = _add_stitch_limited(
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
    }

#在限制针长的前提下添加一个或多个stitch命令，返回更新后的位置和新增针数
def _add_stitch_limited(pattern, last_x, last_y, tx, ty, min_units, max_units):
    
    dist = math.hypot(tx - last_x, ty - last_y)  #计算当前位置到目标点的距离
    if dist < min_units:
        return last_x, last_y, 0  #距离过短时不生成针迹

    steps = 1  #默认只需要生成 1 针
    if max_units > 0 and dist > max_units:
        steps = int(math.ceil(dist / max_units))  #距离过长时拆成多针插值

    added = 0  #统计本次新增的针数
    
    for step in range(1, steps + 1):#按等距插值方式补针
        nx = last_x + (tx - last_x) * (step / steps)  #计算插值点x,y
        ny = last_y + (ty - last_y) * (step / steps)  
        pattern.add_stitch_absolute(pyembroidery.STITCH, nx, ny)  #写入一条绝对坐标落针
        added += 1  #累计针数

    return tx, ty, added  #返回更新后的位置和新增针数

#在限制跳针长度的前提下添加一个或多个jump命令
def _add_jump_limited(pattern, last_x, last_y, tx, ty, max_units):
    
    dist = math.hypot(tx - last_x, ty - last_y)  #计算当前位置到目标点的距离
    if dist <= 1e-6:
        return last_x, last_y, 0  #几乎没有位移时直接跳过

    steps = 1  #默认只需要跳一次
    if max_units > 0 and dist > max_units:
        steps = int(math.ceil(dist / max_units))  #距离过大时拆成多段跳针

    added = 0
    
    for step in range(1, steps + 1): #按等距插值方式分段移动，计算插值点x,y
        nx = last_x + (tx - last_x) * (step / steps)  
        ny = last_y + (ty - last_y) * (step / steps)  
        pattern.add_stitch_absolute(pyembroidery.JUMP, nx, ny)  #写入一条绝对坐标跳针
        added += 1  #累计跳针数

    return tx, ty, added  #返回更新后的位置和新增跳针数

#生成刺绣预览图
def _check_preview(pattern, canvas_size=DEFAULT_PREVIEW_SIZE):
    
    preview = np.ones((canvas_size[1], canvas_size[0]), dtype=np.uint8) * 255  #创建白底预览图
    stitches = pattern.stitches  #读取图案中的全部针迹
    if not stitches:
        return preview

    xs = [x for x, _, cmd in stitches if cmd == pyembroidery.STITCH]  #收集所有真实落针的x坐标
    ys = [y for _, y, cmd in stitches if cmd == pyembroidery.STITCH]  
    if not xs:
        return preview

    min_x, max_x = min(xs), max(xs)  #计算x方向边界
    min_y, max_y = min(ys), max(ys)  
    range_x = max_x - min_x or 1  #计算x方向跨度，避免除零
    range_y = max_y - min_y or 1  
    margin = PREVIEW_MARGIN  #给预览图四周保留边距

    def to_px(sx, sy):
        px = int((sx - min_x) / range_x * (canvas_size[0] - margin * 2) + margin)  #把 x 坐标映射到画布像素
        py = int((sy - min_y) / range_y * (canvas_size[1] - margin * 2) + margin)  
        return px, py  #返回像素坐标

    #逐对检查相邻针迹并绘制真实落针线段
    for i in range(len(stitches) - 1):
        s1 = stitches[i]  #当前针迹
        s2 = stitches[i + 1]  #下一条针迹
        if s1[2] == pyembroidery.STITCH and s2[2] == pyembroidery.STITCH:
            pt1 = to_px(s1[0], s1[1])  #把起点映射到像素坐标
            pt2 = to_px(s2[0], s2[1])  #把终点映射到像素坐标
            cv2.line(preview, pt1, pt2, 0, 1)  #在预览图上画出黑色线段

    return preview  #返回绘制完成的预览图
