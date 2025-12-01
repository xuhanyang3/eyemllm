#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能分割OCT图像中的各个子图
"""

from PIL import Image, ImageDraw
import numpy as np
from pathlib import Path
import cv2

def find_image_regions(img_array, min_area=10000, edge_margin=20):
    """
    通过边缘检测和轮廓识别找到图像中的主要区域
    
    Args:
        img_array: numpy数组图像
        min_area: 最小区域面积
        edge_margin: 边缘裁剪的边距
    
    Returns:
        区域列表 [(x, y, w, h), ...]
    """
    # 转换为灰度图
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array
    
    # 使用Otsu阈值分割
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 形态学操作,连接临近区域
    kernel = np.ones((5, 5), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    
    # 查找轮廓
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # 提取边界框
    regions = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        
        # 过滤太小的区域
        if area < min_area:
            continue
        
        # 添加边距
        x = max(0, x - edge_margin)
        y = max(0, y - edge_margin)
        w = min(gray.shape[1] - x, w + 2 * edge_margin)
        h = min(gray.shape[0] - y, h + 2 * edge_margin)
        
        regions.append((x, y, w, h))
    
    return regions

def split_oct_image_smart(image_path, output_dir, base_name):
    """
    智能分割OCT图像
    
    Args:
        image_path: 输入图像路径
        output_dir: 输出目录
        base_name: 基础文件名
    
    Returns:
        分割出的子图数量
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取图像
    img = Image.open(image_path)
    img_array = np.array(img)
    
    # 检测图像区域
    regions = find_image_regions(img_array, min_area=15000)
    
    # 按位置排序(从上到下,从左到右)
    regions = sorted(regions, key=lambda r: (r[1], r[0]))
    
    saved_count = 0
    
    for idx, (x, y, w, h) in enumerate(regions, 1):
        # 裁剪区域
        cropped = img.crop((x, y, x + w, y + h))
        
        # 保存
        output_path = output_dir / f"{base_name}_region{idx}_{w}x{h}.png"
        cropped.save(output_path)
        saved_count += 1
        
        print(f"  保存区域 {idx}: {w}x{h} at ({x}, {y})")
    
    return saved_count

def detect_eye_label_from_filename(filename):
    """
    从原始PDF文件名或所在文件夹中检测眼别
    
    Args:
        filename: 文件路径或文件名
    
    Returns:
        眼别标识字符串 "_OD", "_OS" 或 ""
    """
    filename_str = str(filename).upper()
    parent_folder = str(Path(filename).parent)
    
    # 检查文件夹名称中的标识
    if '单眼' in parent_folder or '双眼' in parent_folder:
        # 从文件夹层级向上查找病例名称
        parts = str(filename).split('/')
        for part in parts:
            if 'OD' in part.upper() or '右眼' in part:
                return "_OD"
            elif 'OS' in part.upper() or '左眼' in part:
                return "_OS"
    
    # 如果文件夹名没有明确标识,暂时返回空
    # 可以后续通过读取对应的PDF文本来识别
    return ""

def detect_eye_label_from_image_ocr(img):
    """
    使用OCR从图像右上角识别眼别标识
    
    Args:
        img: PIL图像对象
    
    Returns:
        眼别标识字符串 "_OD", "_OS" 或 ""
    """
    try:
        import easyocr
        
        width, height = img.size
        
        # 裁剪右上角区域 (右上角15%的区域)
        right_top_region = img.crop((int(width * 0.80), 0, width, int(height * 0.12)))
        
        # 保存临时文件用于OCR
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            right_top_region.save(tmp.name)
            tmp_path = tmp.name
        
        # 使用EasyOCR识别
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        results = reader.readtext(tmp_path)
        
        # 删除临时文件
        Path(tmp_path).unlink()
        
        # 合并所有识别的文本
        text = ' '.join([result[1].upper() for result in results])
        
        # 检测OD/OS (处理OCR可能的错误,如0S识别为OS)
        text = text.replace('0S', 'OS').replace('0D', 'OD')
        
        has_od = 'OD' in text or 'RIGHT' in text
        has_os = 'OS' in text or 'LEFT' in text
        
        if has_od and not has_os:
            return "_OD"
        elif has_os and not has_od:
            return "_OS"
        elif has_od and has_os:
            # 都有,看哪个先出现
            od_pos = text.find('OD') if 'OD' in text else (text.find('RIGHT') if 'RIGHT' in text else float('inf'))
            os_pos = text.find('OS') if 'OS' in text else (text.find('LEFT') if 'LEFT' in text else float('inf'))
            return "_OD" if od_pos < os_pos else "_OS"
            
    except Exception as e:
        # OCR失败,静默返回空
        pass
    
    return ""

def auto_crop_content(img_array, margin=5):
    """
    自动裁剪图像,去除上下左右的空白/文字/黑边区域,只保留OCT扫描内容
    
    改进策略:
    1. OCT扫描区域通常是暗色的(平均亮度 50-120)
    2. 文字和边框区域通常是亮色的(平均亮度>150)
    3. 纯黑边区域平均亮度很低(<45)
    4. 从四边向内找到第一个有效OCT内容区域
    
    Args:
        img_array: numpy数组图像
        margin: 保留的边距(像素)
    
    Returns:
        (top_crop, bottom_crop, left_crop, right_crop): 需要裁剪的上下左右像素数
    """
    # 转换为灰度图
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array
    
    height, width = gray.shape
    
    # 计算每行和每列的平均亮度
    row_mean = np.mean(gray, axis=1)
    col_mean = np.mean(gray, axis=0)
    
    # 改进的亮度阈值:
    # - 纯黑边: <45 (需要去除)
    # - OCT内容: 45-150 (保留)
    # - 文字/标尺: >150 (需要去除)
    black_edge_threshold = 45  # 纯黑边阈值
    bright_text_threshold = 150  # 亮色文字阈值
    
    # 从顶部找第一个有效OCT内容行
    top_crop = 0
    for i in range(height):
        if black_edge_threshold <= row_mean[i] < bright_text_threshold:
            top_crop = max(0, i - margin)
            break
    
    # 从底部找最后一个有效OCT内容行
    bottom_crop = height
    for i in range(height-1, -1, -1):
        if black_edge_threshold <= row_mean[i] < bright_text_threshold:
            bottom_crop = min(height, i + margin + 1)
            break
    
    # 从左侧找第一个有效OCT内容列
    left_crop = 0
    for i in range(width):
        if black_edge_threshold <= col_mean[i] < bright_text_threshold:
            left_crop = max(0, i - margin)
            break
    
    # 从右侧找最后一个有效OCT内容列
    # 改进策略:先找主体内容,然后检测右侧是否有渐变的黑边或亮色边框
    right_crop = width
    
    # 计算中间核心区域(30%-70%)的典型亮度作为参考
    core_start = int(width * 0.3)
    core_end = int(width * 0.7)
    core_brightness = np.median(col_mean[core_start:core_end])
    
    # 策略1: 从右向左找,遇到亮色边框(>150)就跳过
    # 策略2: 遇到暗边(<core_brightness*0.65)就跳过
    # 策略3: 需要找到稳定的正常亮度区域
    
    low_threshold = core_brightness * 0.75  # 提高到75%,更接近主体亮度
    high_threshold = bright_text_threshold
    
    # 从右向左扫描,需要连续找到多列正常亮度才算稳定边界
    consecutive_normal = 0
    required_consecutive = 3  # 需要连续3列正常亮度
    
    for i in range(width-1, -1, -1):
        current_brightness = col_mean[i]
        
        # 判断当前列是否正常
        is_normal = (low_threshold <= current_brightness < high_threshold)
        
        if is_normal:
            consecutive_normal += 1
            if consecutive_normal >= required_consecutive:
                # 找到连续3列正常亮度,设置边界
                right_crop = i + consecutive_normal
                break
        else:
            consecutive_normal = 0
    
    return top_crop, bottom_crop, left_crop, right_crop

# OCT图像标准格式的固定裁剪坐标
# 只对规格3、4、8进行分割,其他规格保持原样
# 坐标说明: 只提取右侧纯OCT扫描图像,去除左侧缩略图、白色分隔线、文字和边框
OCT_CROP_PRESETS = {
    (1588, 939): {  # 旧规格(也对应规格7)
        'main_top': (573, 50, 1532, 454),
        'main_bottom': (576, 494, 1532, 898),
    },
    (1588, 981): {  # 规格5 (葡萄膜炎新增)
        'main_top': (600, 50, 1535, 475),
        'main_bottom': (600, 515, 1535, 940),
    },
    (1648, 939): {  # 规格4 (已手动验证,上下左边界不同)
        'main_top': (573, 50, 1592, 454),
        'main_bottom': (576, 494, 1589, 889),
    },
    (1648, 979): {  # 规格6
        'main_top': (598, 50, 1592, 474),
        'main_bottom': (598, 514, 1592, 938),
    },
    (1031, 610): {  # 规格22 (葡萄膜炎新增)
        'main_top': (374, 33, 993, 295),
        'main_bottom': (374, 321, 993, 583),
    },
}

def split_oct_image_grid(image_path, output_dir, base_name, layout='auto', auto_crop=False):
    """
    按网格分割OCT图像(适用于规则排列的子图)
    
    优先使用固定坐标裁剪(适用于标准格式),如果不匹配则回退到自动检测
    
    Args:
        image_path: 输入图像路径
        output_dir: 输出目录
        base_name: 基础文件名
        layout: 布局方式 'auto' 或 (rows, cols)
    
    Returns:
        分割出的子图数量
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取图像
    img = Image.open(image_path)
    width, height = img.size
    
    # 从文件名中提取眼别和文件夹前缀
    filename = image_path.name
    base_output_prefix = base_name  # 确保保留原始文件名中的 pdf/img 信息
    folder_prefix = ""
    
    if '_main' in filename or '_img' in filename:
        if filename.startswith('OD_'):
            eye_label = "_OD"
            parts = filename.split('_')
            if len(parts) > 2:
                folder_prefix = parts[1]
        elif filename.startswith('OS_'):
            eye_label = "_OS"
            parts = filename.split('_')
            if len(parts) > 2:
                folder_prefix = parts[1]
        else:
            eye_label = ""
    else:
        eye_label = detect_eye_label_from_image_ocr(img)
    
    if eye_label:
        print(f"  眼别: {eye_label.strip('_')}")
    else:
        print(f"  未检测到眼别信息")
    
    saved_count = 0
    eye_str = eye_label.strip('_') if eye_label else 'unknown'
    prefix_str = f"{folder_prefix}_" if folder_prefix else ""
    
    # ===== 优先使用固定坐标裁剪 =====
    if (width, height) in OCT_CROP_PRESETS:
        print(f"  ✓ 使用预设裁剪坐标 ({width}x{height})")
        coords = OCT_CROP_PRESETS[(width, height)]
        
        # 只保存右侧的纯OCT图像(上下两部分)
        # 保存右上OCT图
        top_part = img.crop(coords['main_top'])
        output_path = output_dir / f"{base_output_prefix}_OCT_top.png"
        top_part.save(output_path)
        saved_count += 1
        print(f"  保存右上OCT图: {top_part.size[0]}x{top_part.size[1]}")
        
        # 保存右下OCT图
        bottom_part = img.crop(coords['main_bottom'])
        output_path = output_dir / f"{base_output_prefix}_OCT_bottom.png"
        bottom_part.save(output_path)
        saved_count += 1
        print(f"  保存右下OCT图: {bottom_part.size[0]}x{bottom_part.size[1]}")
        
        return saved_count
    
    # ===== 回退到自动检测 =====
    print(f"  ⊙ 未匹配预设,使用自动检测")
    
    # 简单策略:将图像分为左(35%)和右(65%)
    left_width = int(width * 0.35)
    
    # 保存左侧部分
    left_part = img.crop((0, 0, left_width, height))
    output_path = output_dir / f"{base_output_prefix}_left.png"
    left_part.save(output_path)
    saved_count += 1
    print(f"  保存左侧缩略图区域: {left_width}x{height}")
    
    # 分析右侧部分
    right_part = img.crop((left_width, 0, width, height))
    right_array = np.array(right_part)
    
    # 检测水平分割线
    gray = cv2.cvtColor(right_array, cv2.COLOR_RGB2GRAY) if len(right_array.shape) == 3 else right_array
    row_means = gray.mean(axis=1)
    diff = np.abs(np.diff(row_means))
    threshold = np.percentile(diff, 90)
    split_points = np.where(diff > threshold)[0]
    
    if len(split_points) > 0:
        mid_y = height // 2
        split_candidates = split_points[np.abs(split_points - mid_y) < height * 0.2]
        
        if len(split_candidates) > 0:
            split_y = split_candidates[np.argmin(np.abs(split_candidates - mid_y))]
            
            # 保存上半部分
            top_part = img.crop((left_width, 0, width, split_y))
            
            if auto_crop:
                top_array = np.array(top_part)
                top_crop, bottom_crop, left_crop, right_crop = auto_crop_content(top_array)
                if top_crop > 0 or bottom_crop < top_array.shape[0] or left_crop > 0 or right_crop < top_array.shape[1]:
                    top_part = Image.fromarray(top_array[top_crop:bottom_crop, left_crop:right_crop])
                    print(f"  自动裁剪上部图像: 上{top_crop}px 下{top_array.shape[0]-bottom_crop}px 左{left_crop}px 右{top_array.shape[1]-right_crop}px")
            
            output_path = output_dir / f"{base_output_prefix}_main_top.png"
            top_part.save(output_path)
            saved_count += 1
            print(f"  保存右侧上部主图: {top_part.size[0]}x{top_part.size[1]}")
            
            # 保存下半部分
            bottom_part = img.crop((left_width, split_y, width, height))
            
            if auto_crop:
                bottom_array = np.array(bottom_part)
                top_crop, bottom_crop, left_crop, right_crop = auto_crop_content(bottom_array)
                if top_crop > 0 or bottom_crop < bottom_array.shape[0] or left_crop > 0 or right_crop < bottom_array.shape[1]:
                    bottom_part = Image.fromarray(bottom_array[top_crop:bottom_crop, left_crop:right_crop])
                    print(f"  自动裁剪下部图像: 上{top_crop}px 下{bottom_array.shape[0]-bottom_crop}px 左{left_crop}px 右{bottom_array.shape[1]-right_crop}px")
            
            output_path = output_dir / f"{base_output_prefix}_main_bottom.png"
            bottom_part.save(output_path)
            saved_count += 1
            print(f"  保存右侧下部主图: {bottom_part.size[0]}x{bottom_part.size[1]}")
        else:
            # 没有找到分割点,保存整个右侧
            output_path = output_dir / f"{base_output_prefix}_main.png"
            right_part.save(output_path)
            saved_count += 1
            print(f"  保存右侧完整主图: {width-left_width}x{height}")
    else:
        # 没有找到分割点,保存整个右侧
        output_path = output_dir / f"{base_output_prefix}_main.png"
        right_part.save(output_path)
        saved_count += 1
        print(f"  保存右侧完整主图: {width-left_width}x{height}")
    
    return saved_count

def is_composite_image(image_path, size_threshold=0.4):
    """
    判断图像是否为需要分割的复合图像
    
    只处理需要裁剪的规格(沿用旧的三种 + 新增四种):
    - 旧规格: 1588×939、1648×939、1648×979
    - 新规格: 1588×981、1588×939、1648×979、1031×610
    (尺寸相同的沿用同一套裁剪坐标)
    
    Args:
        image_path: 图像路径
        size_threshold: 左侧区域占比阈值(已废弃)
    
    Returns:
        (是否需要分割, 原因说明)
    """
    try:
        img = Image.open(image_path)
        width, height = img.size
        
        target_specs = {
            (1588, 981): "规格5",
            (1648, 979): "规格6",
            (1588, 939): "规格7",
            (1648, 939): "规格4",
            (1031, 610): "规格22",
        }
        
        if (width, height) in target_specs:
            spec_name = target_specs[(width, height)]
            return True, f"匹配{spec_name} ({width}×{height}),需要分割"
        else:
            return False, f"规格{width}×{height}不需要分割,保持原样"
        
    except Exception as e:
        return False, f"检测失败: {e}"

def convert_image_to_png(image_path):
    """
    将任意格式图像转换为PNG，返回新的PNG路径
    """
    image_path = Path(image_path)
    if image_path.suffix.lower() == '.png':
        return image_path

    parent = image_path.parent
    base_name = image_path.stem if image_path.suffix else image_path.name
    png_path = parent / f"{base_name}.png"

    if png_path.exists():
        # 已经存在同名PNG, 视为已转换, 只需删除原始文件
        print(f"  发现已有PNG: {png_path.name} (跳过转换)")
        try:
            image_path.unlink()
            print(f"  删除原始文件: {image_path.name}")
        except Exception as unlink_err:
            print(f"  ✗ 删除原始文件失败: {image_path} - {unlink_err}")
        return png_path

    try:
        with Image.open(image_path) as img:
            rgb_img = img.convert('RGB')
            rgb_img.save(png_path, format='PNG')
        print(f"  转换为PNG: {image_path.name} -> {png_path.name}")
        try:
            image_path.unlink()
            print(f"  删除原始文件: {image_path.name}")
        except Exception as unlink_err:
            print(f"  ✗ 删除原始文件失败: {image_path} - {unlink_err}")
        return png_path
    except Exception as e:
        print(f"  ✗ 转换PNG失败: {image_path} - {e}")
        return None


def process_oct_folder(oct_folder):
    """
    处理OCT文件夹中的所有图像
    
    Args:
        oct_folder: OCT文件夹路径
    """
    oct_folder = Path(oct_folder)
    
    if not oct_folder.exists():
        print(f"错误: 文件夹不存在 - {oct_folder}")
        return
    
    # 将非PNG图像先转换为PNG
    raw_image_files = []
    for ext in ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.tif', '*.tiff']:
        raw_image_files.extend(oct_folder.glob(ext))

    converted_pngs = []
    for img_file in raw_image_files:
        if any(x in img_file.name for x in ['_main_top', '_main_bottom', '_left', '_region']):
            continue
        png_path = convert_image_to_png(img_file)
        if png_path:
            converted_pngs.append(png_path)

    # 使用转换后的PNG进行分割（排除已分割标记）
    image_files = [f for f in converted_pngs
                   if not any(x in f.name for x in ['_main_top', '_main_bottom', '_left', '_region'])]
    
    if not image_files:
        print(f"警告: 未找到PNG图像 - {oct_folder}")
        return
    
    print(f"\n处理文件夹: {oct_folder}")
    print(f"找到 {len(image_files)} 个图像文件")
    print("="*70)
    
    split_count = 0
    skip_count = 0
    
    for img_file in image_files:
        print(f"\n处理: {img_file.name}")
        base_name = img_file.stem
        
        try:
            # 智能判断是否需要分割
            need_split, reason = is_composite_image(img_file)
            
            if need_split:
                print(f"  ✓ 需要分割: {reason}")
                # 直接输出到OCT文件夹(不使用split子文件夹)
                count = split_oct_image_grid(img_file, oct_folder, base_name)
                print(f"  ✓ 成功分割为 {count} 个子图")
                split_count += 1
            else:
                print(f"  ⊘ 跳过分割: {reason}")
                skip_count += 1
                
        except Exception as e:
            print(f"  ✗ 错误: {e}")
            skip_count += 1
    
    print(f"\n{'='*70}")
    print(f"处理完成: 分割 {split_count} 个, 跳过 {skip_count} 个")
    print(f"{'='*70}")

def main():
    """主函数:递归处理所有病例OCT文件夹"""
    import sys
    from pathlib import Path

    if len(sys.argv) > 1:
        # 递归模式：对于传入的base目录，递归寻找所有*/OCT文件夹
        base_dir = Path(sys.argv[1])
        if not base_dir.exists():
            print(f"错误: 基础目录不存在 - {base_dir}")
            return
        # 查找所有*/OCT文件夹
        oct_folders = sorted(base_dir.glob("*/OCT"))
        print(f"找到{len(oct_folders)}个病例OCT文件夹（递归模式）")
        for idx, oct_folder in enumerate(oct_folders, 1):
            print(f"\n[{idx}/{len(oct_folders)}]")
            process_oct_folder(oct_folder)
        print("\n" + "="*70)
        print("全部完成!")
        print("="*70)
    else:
        # 默认CSC模式
        base_dir = Path("/data2/xuhanyang/dataset/CSC病例图像提取")
        if not base_dir.exists():
            print(f"错误: 基础目录不存在 - {base_dir}")
            return
        oct_folders = sorted(base_dir.glob("*/OCT"))
        print(f"找到{len(oct_folders)}个CSC病例OCT文件夹")
        for idx, oct_folder in enumerate(oct_folders, 1):
            print(f"\n[{idx}/{len(oct_folders)}]")
            process_oct_folder(oct_folder)
        print("\n" + "="*70)
        print("全部完成!")
        print("="*70)

if __name__ == '__main__':
    main()
