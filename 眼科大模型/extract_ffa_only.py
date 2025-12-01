#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从PDF文件中提取图像，自动区分FFA和ICGA，只保留FFA图像
"""

import sys
import io
import re
from collections import defaultdict
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image
import numpy as np

def analyze_pdf_info(pdf_path, brightness_threshold=80):
    """
    分析PDF的类型（FFA/ICGA/IR）和眼别（OD/OS）
    
    优先使用PDF文本内容判断，如果失败则使用图像亮度判断
    
    Args:
        pdf_path: PDF文件路径
        brightness_threshold: 亮度阈值（备用方法）
    
    Returns:
        dict: {'type': str, 'eye': str, 'has_ir': bool, 'has_ffa': bool} 或 None
        type: 'FFA', 'ICGA', 'IR', 'FFA+IR', 'MIXED'
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[0]
        
        # 方法1：从PDF文本内容判断（最准确）
        text = page.get_text()
        text_upper = text.upper()
        
        # 统计各类图像标签出现次数
        fa_count = text_upper.count('FA ')
        fa_count += text_upper.count('FA\n')
        fa_count += text_upper.count('FA:')
        fa_count += text_upper.count('FA\t')
        
        icga_count = text_upper.count('ICGA')
        
        # IR图像标识
        ir_count = text_upper.count('IR ')
        ir_count += text_upper.count('IR\n')
        ir_count += text_upper.count('INFRARED')
        
        # 判断眼别（OD=右眼，OS=左眼）
        right_keywords_upper = ['OD', 'RIGHT EYE SELECTED', 'RIGHT EYE']
        left_keywords_upper = ['OS', 'LEFT EYE SELECTED', 'LEFT EYE']
        chinese_right_keywords = ['右眼']
        chinese_left_keywords = ['左眼']
        
        right_positions = []
        left_positions = []
        
        for kw in right_keywords_upper:
            pos = text_upper.find(kw)
            while pos != -1:
                right_positions.append(pos)
                pos = text_upper.find(kw, pos + len(kw))
        
        for kw in left_keywords_upper:
            pos = text_upper.find(kw)
            while pos != -1:
                left_positions.append(pos)
                pos = text_upper.find(kw, pos + len(kw))
        
        for kw in chinese_right_keywords:
            pos = text.find(kw)
            while pos != -1:
                right_positions.append(pos)
                pos = text.find(kw, pos + len(kw))
        
        for kw in chinese_left_keywords:
            pos = text.find(kw)
            while pos != -1:
                left_positions.append(pos)
                pos = text.find(kw, pos + len(kw))
        
        has_od = bool(right_positions)
        has_os = bool(left_positions)
        
        if has_od and not has_os:
            eye = "右眼(OD)"
        elif has_os and not has_od:
            eye = "左眼(OS)"
        elif has_od and has_os:
            # 两者都有，看哪个先出现
            od_pos = min(right_positions)
            os_pos = min(left_positions)
            eye = "右眼(OD)" if od_pos < os_pos else "左眼(OS)"
        else:
            eye = "未知"
        
        eye_selected_detected = ('RIGHT EYE SELECTED' in text_upper) or ('LEFT EYE SELECTED' in text_upper)
        
        # 判断PDF类型
        has_ffa = fa_count > 0
        has_icga = icga_count > 0
        has_ir = ir_count > 0
        
        if has_ffa or has_icga or has_ir:
            doc.close()
            
            # 确定主要类型
            if has_icga and icga_count > fa_count:
                pdf_type = 'ICGA'
            elif has_ffa and has_ir:
                pdf_type = 'FFA+IR'
            elif has_ffa:
                pdf_type = 'FFA'
            elif has_ir:
                pdf_type = 'IR'
            else:
                pdf_type = 'MIXED'
            
            return {
                'type': pdf_type,
                'eye': eye,
                'has_ffa': has_ffa,
                'has_icga': has_icga,
                'has_ir': has_ir,
                'fa_count': fa_count,
                'icga_count': icga_count,
                'ir_count': ir_count,
                'eye_selected_label': eye_selected_detected
            }
        
        # 方法2：如果文本判断失败，使用图像亮度作为备用方法
        image_list = page.get_images()
        
        if len(image_list) < 3:
            doc.close()
            return None  # 无法判断
        
        # 提取第3张图像（通常是第一张医学图像，前两张是标题）
        xref = image_list[2][0]
        base_image = doc.extract_image(xref)
        image_bytes = base_image["image"]
        
        # 转换为PIL图像并计算亮度
        pil_image = Image.open(io.BytesIO(image_bytes))
        arr = np.array(pil_image)
        mean_brightness = arr.mean()
        
        doc.close()
        
        # FFA图像通常较暗（使用备用方法时无法判断眼别）
        is_ffa = mean_brightness < brightness_threshold
        return {
            'type': 'FFA' if is_ffa else 'UNKNOWN',
            'eye': "未知",
            'has_ffa': is_ffa,
            'has_icga': False,
            'has_ir': False,
            'eye_selected_label': eye_selected_detected
        }
        
    except Exception as e:
        print(f"  警告: 无法分析PDF - {e}")
        return None

def is_fa_icga_combined_image(pil_image, pdf_info=None):
    """
    检测图像是否是FA+ICGA组合图像（左右拼接）
    
    Args:
        pil_image: PIL图像对象
        pdf_info: PDF信息字典（可选，用于辅助判断）
    
    Returns:
        bool: 如果是组合图像返回True
    """
    width, height = pil_image.size
    
    # 判断标准1: 宽度大约是高度的2倍（比例在1.8-2.2之间）
    aspect_ratio = width / height if height > 0 else 0
    is_combined_by_size = 1.8 <= aspect_ratio <= 2.2
    
    # 判断标准2: PDF信息显示同时有FA和ICGA，且出现次数相同（或接近）
    is_combined_by_pdf_info = False
    if pdf_info:
        has_ffa = pdf_info.get('has_ffa', False)
        has_icga = pdf_info.get('has_icga', False)
        fa_count = pdf_info.get('fa_count', 0)
        icga_count = pdf_info.get('icga_count', 0)
        
        # 只有当FA和ICGA都存在，且出现次数相同（或接近，允许±1的容差）时，才认为是组合图像
        if has_ffa and has_icga and fa_count > 0 and icga_count > 0:
            # 允许±1的容差，因为可能有计数误差
            count_diff = abs(fa_count - icga_count)
            is_combined_by_pdf_info = count_diff <= 1
    
    # 判断标准3: 宽度足够大（通常组合图像宽度>1000）
    is_large_enough = width >= 1000
    
    return (is_combined_by_size or is_combined_by_pdf_info) and is_large_enough

def crop_fa_from_combined_image(pil_image):
    """
    从FA+ICGA组合图像中裁剪出左边的FA部分
    
    Args:
        pil_image: PIL图像对象（组合图像）
    
    Returns:
        PIL图像对象（FA部分）
    """
    width, height = pil_image.size
    # 裁剪左边一半（FA部分）
    left_half = pil_image.crop((0, 0, width // 2, height))
    return left_half

def extract_ffa_images_from_pdf(pdf_path, output_dir, brightness_threshold=80, extract_ir=False, pdf_index=1):
    """
    从PDF提取图像，如果是FFA则保存，可选择是否提取IR
    新增参数：pdf_index 用于在文件名中区分不同PDF
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    
    # 分析PDF类型和眼别
    pdf_info = analyze_pdf_info(pdf_path, brightness_threshold)
    
    if pdf_info is None:
        return {'status': 'error', 'message': '无法判断PDF类型'}
    
    # 判断是否需要跳过
    pdf_type = pdf_info['type']
    
    # 跳过ICGA
    if pdf_type == 'ICGA':
        return {
            'status': 'skipped', 
            'type': 'ICGA', 
            'eye': pdf_info['eye'],
            'message': '跳过ICGA图像'
        }
    
    # 跳过纯IR（如果不提取IR）
    if pdf_type == 'IR' and not extract_ir:
        return {
            'status': 'skipped',
            'type': 'IR',
            'eye': pdf_info['eye'],
            'message': '跳过IR图像'
        }
    
    # 如果没有FFA内容，跳过
    if (not pdf_info['has_ffa'] and
        not (extract_ir and pdf_info['has_ir']) and
        not pdf_info.get('eye_selected_label')):
        return {
            'status': 'skipped',
            'type': pdf_type,
            'eye': pdf_info['eye'],
            'message': f'跳过{pdf_type}图像'
        }
    
    # 提取图像
    output_dir.mkdir(parents=True, exist_ok=True)
    
    doc = fitz.open(pdf_path)
    
    images_info = []
    total_images = 0
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images()
        page_mid_x = page.rect.width / 2
        
        text_dict = page.get_text("dict")
        timestamp_entries = []
        eye_by_column = defaultdict(lambda: {"eye": "未知", "strength": "weak"})
        strong_right_keywords = ["RIGHT EYE SELECTED", "RIGHT EYE"]
        strong_left_keywords = ["LEFT EYE SELECTED", "LEFT EYE"]
        label_blocks = []
        
        for block in text_dict.get("blocks", []):
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text_content = span["text"].strip()
                    if not text_content:
                        continue
                    bbox = span["bbox"]
                    text_upper = text_content.upper()
                    
                    if "TIMESTAMP" in text_upper or re.search(r"\(\d{2}:\d{2}\.\d{3}\)", text_content):
                        timestamp_entries.append({
                            "text": text_content,
                            "x": bbox[0],
                            "y": bbox[1]
                        })
                    if any(keyword in text_upper for keyword in ["FA", "IR", "ICGA"]):
                        label_blocks.append({
                            "text": text_content,
                            "x": bbox[0],
                            "y": bbox[1]
                        })
                    column_num = 1 if bbox[0] < page_mid_x else 2

                    def update_eye(column, eye_label, strength):
                        current = eye_by_column[column]
                        if strength == "strong" or current["strength"] != "strong":
                            eye_by_column[column] = {"eye": eye_label, "strength": strength}

                    if any(keyword in text_upper for keyword in strong_right_keywords):
                        update_eye(column_num, "右眼(OD)", "strong")
                    elif text_content.strip().upper() == "OD" or "右眼" in text_content:
                        update_eye(column_num, "右眼(OD)", "weak")

                    if any(keyword in text_upper for keyword in strong_left_keywords):
                        update_eye(column_num, "左眼(OS)", "strong")
                    elif text_content.strip().upper() == "OS" or "左眼" in text_content:
                        update_eye(column_num, "左眼(OS)", "weak")
        
        def normalize_eye(s):
            if s == "右眼(OD)":
                return "OD"
            if s == "左眼(OS)":
                return "OS"
            return "unknown"
        
        # 如果整份PDF只有单眼信息，且列级没有强标记，则保持与整份一致

        pdf_eye_norm = normalize_eye(pdf_info['eye'])
        if pdf_eye_norm in ("OD", "OS"):
            has_strong_conflict = any(
                info["strength"] == "strong" and normalize_eye(info["eye"]) not in ("unknown", pdf_eye_norm)
                for info in eye_by_column.values()
            )
            if not has_strong_conflict:
                default_eye_label = "右眼(OD)" if pdf_eye_norm == "OD" else "左眼(OS)"
                for col in (1, 2):
                    if eye_by_column[col]["strength"] != "strong":
                        eye_by_column[col] = {"eye": default_eye_label, "strength": "default"}
        else:
            # 如果列仍未知，回退到整份PDF的眼别
            if pdf_info['eye'] in ("右眼(OD)", "左眼(OS)"):
                default_eye_label = pdf_info['eye']
                for col in (1, 2):
                    if eye_by_column[col]["eye"] == "未知":
                        eye_by_column[col] = {"eye": default_eye_label, "strength": "default"}
        
        stripes_by_column = defaultdict(list)
        standard_candidates = []
        
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            try:
                pil_image = Image.open(io.BytesIO(image_bytes))
                width, height = pil_image.size
                
                img_rects = page.get_image_rects(xref)
                if not img_rects:
                    continue
                
                # 针对包含列选择标签的PDF，放宽尺寸阈值
                min_width = 300
                min_height = 300
                if pdf_info.get('eye_selected_label'):
                    min_width = 200
                    min_height = 180
                
                is_stripe_candidate = width > 1000 and height < 120
                
                for img_rect in img_rects:
                    column_num = 1 if (img_rect.x0 + img_rect.x1) / 2 < page_mid_x else 2
                    
                    if is_stripe_candidate:
                        stripes_by_column[column_num].append({
                            "rect": img_rect,
                            "pil_image": pil_image,
                            "ext": image_ext
                        })
                    elif width >= min_width and height >= min_height:
                        standard_candidates.append({
                            "rect": img_rect,
                            "pil_image": pil_image,
                            "ext": image_ext,
                            "column": column_num
                        })
            except Exception as e:
                print(f"  警告: 图像 {img_index + 1} 读取失败 - {e}")
        
        # 若不存在条带数据，则退回保存标准图像
        has_stripes = any(rect_list for rect_list in stripes_by_column.values())
        if not has_stripes:
            for candidate in standard_candidates:
                pil_image = candidate["pil_image"]
                width, height = pil_image.size
                label = ""
                rect = candidate["rect"]
                
                if label_blocks:
                    img_x = rect.x0
                    img_y = rect.y0
                    min_distance = float('inf')
                    for lb in label_blocks:
                        y_distance = abs(lb['y'] - img_y)
                        x_distance = abs(lb['x'] - img_x)
                        if y_distance < 60 and x_distance < min_distance:
                            min_distance = x_distance
                            label = lb['text']
                
                label_clean = ""
                if label:
                    label_clean = label.replace(" ", "_").replace("°", "deg").replace("[", "").replace("]", "")
                    label_clean = re.sub(r'[^\w\-_\.\:]', '_', label_clean)
                
                eye_str = normalize_eye(eye_by_column[candidate["column"]]["eye"])
                
                # 检测是否是FA+ICGA组合图像，如果是则裁剪左边FA部分
                is_combined = False
                if is_fa_icga_combined_image(pil_image, pdf_info):
                    pil_image = crop_fa_from_combined_image(pil_image)
                    width, height = pil_image.size  # 更新尺寸
                    is_combined = True
                    # 在文件名中添加FA标识
                    if label_clean:
                        if 'FA' not in label_clean.upper():
                            label_clean = f"FA_{label_clean}"
                    else:
                        label_clean = "FA"
                
                # 新的命名——干净只从眼别开始，如 OD_pdf1_col2_img1_....
                # 如果是从组合图像裁剪的，添加combine标识
                combine_suffix = "_combine" if is_combined else ""
                if label_clean:
                    output_name = f"{eye_str}_pdf{pdf_index}_page{page_num+1}_{label_clean}{combine_suffix}.{candidate['ext']}"
                else:
                    next_index = total_images + 1
                    output_name = f"{eye_str}_pdf{pdf_index}_page{page_num+1}_img{next_index}{combine_suffix}.{candidate['ext']}"
                
                output_path = output_dir / output_name
                pil_image.save(output_path)
                
                total_images += 1
                images_info.append({
                    'filename': output_name,
                    'label': label,
                    'width': width,
                    'height': height,
                    'format': candidate['ext']
                })
        
        # 处理条带型图像：按列、按高度排序后切分区域并从PDF中裁剪
        for col_num, rect_list in stripes_by_column.items():
            if not rect_list:
                continue
            rect_list_sorted = sorted(rect_list, key=lambda item: item["rect"].y0)
            
            groups = []
            current_group = [rect_list_sorted[0]]
            for prev_item, item in zip(rect_list_sorted, rect_list_sorted[1:]):
                if item["rect"].y0 - prev_item["rect"].y0 > 10:
                    groups.append(current_group)
                    current_group = [item]
                else:
                    current_group.append(item)
            groups.append(current_group)
            
            for idx_in_col, group in enumerate(groups, start=1):
                min_x = min(entry["rect"].x0 for entry in group)
                max_x = max(entry["rect"].x1 for entry in group)
                min_y = min(entry["rect"].y0 for entry in group)
                max_y = max(entry["rect"].y1 for entry in group)
                
                clip_rect = fitz.Rect(min_x, min_y, max_x, max_y)
                pad = 1.5
                clip_rect.x0 = max(page.rect.x0, clip_rect.x0 - pad)
                clip_rect.y0 = max(page.rect.y0, clip_rect.y0 - pad)
                clip_rect.x1 = min(page.rect.x1, clip_rect.x1 + pad)
                clip_rect.y1 = min(page.rect.y1, clip_rect.y1 + pad)
                
                clip_width = clip_rect.width
                zoom = max(2.0, min(4.0, 1000.0 / clip_width))
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip_rect, alpha=False)
                pix_bytes = pix.tobytes("png")
                pil_image = Image.open(io.BytesIO(pix_bytes))
                
                # 检测是否是FA+ICGA组合图像，如果是则裁剪左边FA部分
                is_combined = False
                if is_fa_icga_combined_image(pil_image, pdf_info):
                    pil_image = crop_fa_from_combined_image(pil_image)
                    is_combined = True
                
                # 查找最近的时间戳
                closest_timestamp = "no-time"
                min_time_distance = float('inf')
                group_center_y = (min_y + max_y) / 2
                for ts in timestamp_entries:
                    ts_col = 1 if ts['x'] < page_mid_x else 2
                    if ts_col != col_num:
                        continue
                    dist = abs(ts['y'] - group_center_y)
                    if dist < min_time_distance:
                        min_time_distance = dist
                        match = re.search(r"\((\d{2}:\d{2}\.\d{3})\)", ts["text"])
                        if match:
                            closest_timestamp = match.group(1).replace(':', '-')
                
                eye_str = normalize_eye(eye_by_column[col_num]["eye"])
                # 新的命名，如果是从组合图像裁剪的，添加combine标识
                combine_suffix = "_combine" if is_combined else ""
                output_name = (
                    f"{eye_str}_pdf{pdf_index}_page{page_num+1}_col{col_num}_img{idx_in_col}_{closest_timestamp}{combine_suffix}.png"
                )

                output_path = output_dir / output_name
                pil_image.save(output_path)
                
                total_images += 1
                images_info.append({
                    'filename': output_name,
                    'label': f"col{col_num}_img{idx_in_col}",
                    'width': pil_image.width,
                    'height': pil_image.height,
                    'format': 'png'
                })
    
    doc.close()
    
    return {
        'status': 'success',
        'type': pdf_type,
        'eye': pdf_info['eye'],
        'num_images': total_images,
        'images': images_info,
        'has_ffa': pdf_info['has_ffa'],
        'has_ir': pdf_info.get('has_ir', False)
    }

def process_directory(input_dir, output_dir, brightness_threshold=80):
    """
    处理目录中的所有PDF文件
    
    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        brightness_threshold: 亮度阈值
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    
    if not input_dir.exists():
        print(f"错误: 输入目录不存在 - {input_dir}")
        return
    
    pdf_files = list(input_dir.glob('*.pdf'))
    
    if not pdf_files:
        print(f"警告: 在 {input_dir} 中未找到PDF文件")
        return
    
    print("="*70)
    print(f"FFA图像提取工具（自动跳过ICGA）")
    print("="*70)
    print()
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print(f"亮度阈值: {brightness_threshold}")
    print(f"找到 {len(pdf_files)} 个PDF文件")
    print()
    print("="*70)
    print()
    
    ffa_count = 0
    icga_count = 0
    error_count = 0
    total_ffa_images = 0
    
    for pdf_file in pdf_files:
        print(f"处理: {pdf_file.name}")
        
        result = extract_ffa_images_from_pdf(pdf_file, output_dir, brightness_threshold)
        
        if result['status'] == 'success':
            eye_info = f" - {result['eye']}" if result.get('eye') != "未知" else ""
            print(f"  ✓ FFA{eye_info} - 提取 {result['num_images']} 张图像")
            ffa_count += 1
            total_ffa_images += result['num_images']
        elif result['status'] == 'skipped':
            eye_info = f" - {result['eye']}" if result.get('eye') != "未知" else ""
            print(f"  ✗ ICGA{eye_info} - 已跳过")
            icga_count += 1
        else:
            print(f"  ⚠ 错误: {result.get('message', '未知错误')}")
            error_count += 1
        print()
    
    print("="*70)
    print("处理完成")
    print("="*70)
    print(f"FFA文件: {ffa_count} 个 (提取 {total_ffa_images} 张图像)")
    print(f"ICGA文件: {icga_count} 个 (已跳过)")
    print(f"错误: {error_count} 个")
    print(f"输出目录: {output_dir}")
    print("="*70)

def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  单个PDF: python extract_ffa_only.py <PDF文件> [输出目录] [亮度阈值]")
        print("  目录:   python extract_ffa_only.py <输入目录> [输出目录] [亮度阈值]")
        print()
        print("参数:")
        print("  PDF文件/输入目录: PDF文件路径或包含PDF的目录")
        print("  输出目录: 可选，默认为 输入名_ffa_only")
        print("  亮度阈值: 可选，默认为80（低于此值判断为FFA）")
        print()
        print("示例:")
        print("  python extract_ffa_only.py report.pdf")
        print("  python extract_ffa_only.py /path/to/pdfs/ /path/to/output/")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    
    # 默认输出目录
    if len(sys.argv) > 2:
        output_dir = Path(sys.argv[2])
    else:
        if input_path.is_file():
            output_dir = input_path.parent / f"{input_path.stem}_ffa_only"
        else:
            output_dir = input_path.parent / f"{input_path.name}_ffa_only"
    
    # 亮度阈值
    brightness_threshold = int(sys.argv[3]) if len(sys.argv) > 3 else 80
    
    if not input_path.exists():
        print(f"错误: 路径不存在 - {input_path}")
        sys.exit(1)
    
    if input_path.is_file():
        # 处理单个PDF
        print("="*70)
        print(f"FFA图像提取工具（自动跳过ICGA）")
        print("="*70)
        print()
        print(f"PDF文件: {input_path}")
        print(f"输出目录: {output_dir}")
        print(f"亮度阈值: {brightness_threshold}")
        print()
        
        result = extract_ffa_images_from_pdf(input_path, output_dir, brightness_threshold)
        
        if result['status'] == 'success':
            eye_info = f" - {result['eye']}" if result.get('eye') != "未知" else ""
            print(f"✓ FFA{eye_info} - 成功提取 {result['num_images']} 张图像")
        elif result['status'] == 'skipped':
            eye_info = f" - {result['eye']}" if result.get('eye') != "未知" else ""
            print(f"✗ ICGA{eye_info} - 已跳过")
        else:
            print(f"⚠ 错误: {result.get('message', '未知错误')}")
        
        print()
        print(f"输出目录: {output_dir}")
        print("="*70)
        
    else:
        # 处理目录
        process_directory(input_path, output_dir, brightness_threshold)

if __name__ == '__main__':
    main()

