#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从海德堡DR工作表中提取OCT和FFA图像
优先海德堡OCT，其次科林和视微OCT
"""

import os
import sys
from pathlib import Path
import pandas as pd
from datetime import datetime
import fitz  # PyMuPDF
from PIL import Image
import io
import re
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed

CPU_COUNT = os.cpu_count() or 1
DEFAULT_WORKERS = max(1, min(24, CPU_COUNT))
CONFIGURED_WORKERS = os.environ.get('CSC_WORKERS')
try:
    CSC_WORKERS = int(CONFIGURED_WORKERS) if CONFIGURED_WORKERS else DEFAULT_WORKERS
except ValueError:
    CSC_WORKERS = DEFAULT_WORKERS
CSC_WORKERS = max(1, CSC_WORKERS)

# 导入FFA提取功能
sys.path.append('/data2/xuhanyang/眼科大模型')
from extract_ffa_only import extract_ffa_images_from_pdf

def parse_patient_folder(folder_str):
    """
    解析patient_folder字符串
    例如: "01426429 孙哲英 女 1972-01-07"
    返回: (patient_id, patient_name)
    """
    parts = str(folder_str).strip().split()
    if len(parts) >= 2:
        patient_id = parts[0]
        patient_name = parts[1]
        return patient_id, patient_name
    return None, None

def parse_visit_date(date_str):
    """
    解析就诊日期
    例如: "2024-07-03 双眼" -> ("2024-07-03", "双眼")
    """
    date_str = str(date_str).strip()
    
    # 提取眼别（单眼/双眼）
    eye_type = "单眼" if "单眼" in date_str else ("双眼" if "双眼" in date_str else "")
    
    # 提取日期部分
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
    if date_match:
        date_part = date_match.group(1)
        return date_part, eye_type
    
    return None, eye_type

def find_exam_folders(base_path, patient_folder, visit_date, exam_keyword):
    """
    查找所有匹配的检查文件夹(支持多个文件夹,如血流模式和普通模式)
    
    Args:
        base_path: 基础路径 (例如: /share/kongzitai/ophthalmology/E:/2024)
        patient_folder: 患者文件夹字符串 (例如: "01426429 孙哲英 女 1972-01-07")
        visit_date: 就诊日期 (例如: "2024-07-03")
        exam_keyword: 检查关键词 (例如: "海德堡", "造影", "科林")
    
    Returns:
        匹配的文件夹路径列表
    """
    patient_id, patient_name = parse_patient_folder(patient_folder)
    if not patient_id:
        return []
    
    # 构建患者路径 (在疾病专属目录下)
    year = visit_date[:4]
    
    # 糖尿病性视网膜病变数据路径(按年份区分)
    possible_bases = [
        f'/share/kongzitai/ophthalmology/E:/{year}-糖尿病性视网膜病变',
    ]
    
    found_folders = []
    
    for base in possible_bases:
        base_path = Path(base)
        if not base_path.exists():
            continue
        
        # 直接在base下查找患者文件夹
        patient_folders = list(base_path.glob(f'{patient_id}*'))
        
        if not patient_folders:
            continue
        
        # 在患者文件夹下查找日期文件夹
        for patient_path in patient_folders:
            date_folder = patient_path / visit_date
            if not date_folder.exists():
                continue
            
            # 在日期文件夹下查找所有匹配的检查文件夹
            try:
                for item in date_folder.iterdir():
                    if item.is_dir() and exam_keyword in item.name:
                        found_folders.append(item)
            except PermissionError:
                continue
        
        # 如果在当前base路径下找到了文件夹,就不再搜索其他base路径(避免重复)
        if found_folders:
            break
    
    return found_folders

def find_exam_folder(base_path, patient_folder, visit_date, exam_keyword):
    """
    查找指定检查的文件夹(返回第一个匹配的,用于FFA等单一检查)
    
    Args:
        base_path: 基础路径 (例如: /share/kongzitai/ophthalmology/E:/2024)
        patient_folder: 患者文件夹字符串 (例如: "01426429 孙哲英 女 1972-01-07")
        visit_date: 就诊日期 (例如: "2024-07-03")
        exam_keyword: 检查关键词 (例如: "海德堡", "造影", "科林")
    
    Returns:
        文件夹路径或None
    """
    folders = find_exam_folders(base_path, patient_folder, visit_date, exam_keyword)
    return folders[0] if folders else None

def find_nearest_date_oct_folders(patient_folder, visit_date, oct_keywords=['海德堡', '科林', '视微', 'OCT']):
    """
    查找最近日期的OCT文件夹(当指定日期找不到时使用)
    
    Args:
        patient_folder: 患者文件夹字符串
        visit_date: 目标就诊日期
        oct_keywords: OCT关键词列表
    
    Returns:
        (found_folders, actual_date, oct_type) 或 ([], None, None)
    """
    from datetime import datetime
    
    patient_id, patient_name = parse_patient_folder(patient_folder)
    if not patient_id:
        return [], None, None, None
    
    year = visit_date[:4]
    possible_bases = [
        f'/share/kongzitai/ophthalmology/E:/{year}-糖尿病性视网膜病变',
    ]
    
    # 解析目标日期
    try:
        target_date = datetime.strptime(visit_date, '%Y-%m-%d')
    except:
        return [], None, None, None
    
    # 收集所有可用的日期及其OCT文件夹
    available_dates = []  # [(date_obj, date_str, oct_folders, oct_type), ...]
    
    for base in possible_bases:
        base_path = Path(base)
        if not base_path.exists():
            continue
        
        patient_folders = list(base_path.glob(f'{patient_id}*'))
        if not patient_folders:
            continue
        
        for patient_path in patient_folders:
            # 遍历患者文件夹下的所有日期文件夹
            try:
                for date_folder in patient_path.iterdir():
                    if not date_folder.is_dir():
                        continue
                    
                    # 尝试解析日期
                    date_str = date_folder.name
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    except:
                        continue
                    
                    # 查找该日期下的OCT文件夹
                    for oct_keyword in oct_keywords:
                        oct_folders = []
                        for item in date_folder.iterdir():
                            if item.is_dir() and oct_keyword in item.name:
                                oct_folders.append(item)
                        
                        if oct_folders:
                            available_dates.append((date_obj, date_str, oct_folders, oct_keyword))
                            break  # 找到一种OCT类型就够了
            except PermissionError:
                continue
        
        if available_dates:
            break  # 找到数据就不再搜索其他base
    
    if not available_dates:
        return [], None, None, None
    
    # 按日期与目标日期的距离排序
    available_dates.sort(key=lambda x: abs((x[0] - target_date).days))
    
    # 返回最近的一个
    nearest = available_dates[0]
    days_diff = abs((nearest[0] - target_date).days)
    
    return nearest[2], nearest[1], nearest[3], days_diff

# 全局OCR reader(复用以提高性能)
_ocr_reader = None

def get_ocr_reader(use_gpu=True):
    """获取或创建OCR reader(单例模式)"""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        import torch
        # 检查GPU是否可用
        gpu_available = torch.cuda.is_available() and use_gpu
        _ocr_reader = easyocr.Reader(['en'], gpu=gpu_available, verbose=False)
    return _ocr_reader

def detect_eye_from_oct_image(pil_image, use_gpu=True, try_extended_region=False):
    """
    使用OCR从OCT图像右上角识别眼别
    
    Args:
        pil_image: PIL图像对象
        use_gpu: 是否使用GPU加速
        try_extended_region: 是否尝试扩大搜索区域(仅在首次失败时使用)
    
    Returns:
        眼别标识字符串 "_OD", "_OS" 或 ""
    """
    try:
        import tempfile
        from PIL import ImageEnhance
        
        width, height = pil_image.size
        reader = get_ocr_reader(use_gpu=use_gpu)
        
        # 定义多个检测区域(按优先级排序)
        detection_regions = [
            # 1. 最右上角小区域 (专门针对像您图片中那种右上角标记)
            (int(width * 0.92), 0, width, int(height * 0.08), "right_corner"),
            # 2. 标准右上角区域
            (int(width * 0.80), 0, width, int(height * 0.12), "standard"),
        ]
        
        # 如果允许扩展搜索,添加更大的区域
        if try_extended_region:
            detection_regions.extend([
                # 3. 扩大右上角区域
                (int(width * 0.70), 0, width, int(height * 0.20), "extended"),
                # 4. 整个顶部区域
                (0, 0, width, int(height * 0.15), "full_top"),
            ])
        
        # 尝试每个检测区域
        for x1, y1, x2, y2, region_name in detection_regions:
            try:
                # 裁剪区域
                region = pil_image.crop((x1, y1, x2, y2))
                
                # 增强对比度以提高OCR准确率
                enhancer = ImageEnhance.Contrast(region)
                region = enhancer.enhance(2.0)  # 增强对比度2倍
                
                # 保存临时文件用于OCR
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    region.save(tmp.name)
                    tmp_path = tmp.name
                
                # OCR识别
                results = reader.readtext(tmp_path)
                Path(tmp_path).unlink()
                
                # 合并所有识别的文本
                text = ' '.join([result[1].upper() for result in results])
                
                # 检测OD/OS (处理OCR可能的错误)
                # 常见OCR错误: 0S->OS, 0D->OD, QS->OS, QD->OD
                text = text.replace('0S', 'OS').replace('0D', 'OD')
                text = text.replace('QS', 'OS').replace('QD', 'OD')
                
                has_od = 'OD' in text or 'RIGHT' in text
                has_os = 'OS' in text or 'LEFT' in text
                
                if has_od and not has_os:
                    return "_OD"
                elif has_os and not has_od:
                    return "_OS"
                elif has_od and has_os:
                    # 如果同时检测到OD和OS,选择先出现的
                    od_pos = text.find('OD') if 'OD' in text else (text.find('RIGHT') if 'RIGHT' in text else float('inf'))
                    os_pos = text.find('OS') if 'OS' in text else (text.find('LEFT') if 'LEFT' in text else float('inf'))
                    return "_OD" if od_pos < os_pos else "_OS"
                
            except Exception as e:
                continue  # 如果某个区域失败,尝试下一个
        
    except Exception as e:
        pass
    
    return ""

def detect_eye_from_pdf_page(page, use_gpu=False):
    """
    通过渲染PDF页面并OCR识别右上角的眼别标记
    
    Args:
        page: PyMuPDF页面对象
        use_gpu: 是否使用GPU进行OCR
    
    Returns:
        眼别标识字符串 "_OD", "_OS" 或 ""
    """
    try:
        import tempfile
        
        # 渲染页面为图像 (2倍分辨率以提高OCR准确率)
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        
        # 转换为PIL图像
        page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        width, height = page_img.size
        
        # 裁剪右上角区域 (90%-100%宽度, 0-8%高度)
        right_top = page_img.crop((int(width * 0.90), 0, width, int(height * 0.08)))
        
        # 保存临时文件用于OCR
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            right_top.save(tmp.name)
            tmp_path = tmp.name
        
        # OCR识别
        reader = get_ocr_reader(use_gpu=use_gpu)
        results = reader.readtext(tmp_path)
        Path(tmp_path).unlink()
        
        # 合并所有识别的文本
        text = ' '.join([result[1].upper() for result in results])
        
        # 检测OD/OS (处理OCR可能的错误)
        text = text.replace('0S', 'OS').replace('0D', 'OD')
        text = text.replace('QS', 'OS').replace('QD', 'OD')
        
        has_od = 'OD' in text or 'RIGHT' in text
        has_os = 'OS' in text or 'LEFT' in text
        
        if has_od and not has_os:
            return "_OD"
        elif has_os and not has_od:
            return "_OS"
        elif has_od and has_os:
            od_pos = text.find('OD') if 'OD' in text else (text.find('RIGHT') if 'RIGHT' in text else float('inf'))
            os_pos = text.find('OS') if 'OS' in text else (text.find('LEFT') if 'LEFT' in text else float('inf'))
            return "_OD" if od_pos < os_pos else "_OS"
        
    except Exception as e:
        pass
    
    return ""

def extract_oct_images_from_pdf(pdf_path, output_dir, start_index=1, folder_prefix="", use_gpu_ocr=False, cached_eye_label=None, pdf_index=1):
    """
    从OCT PDF中提取图像,识别眼别和标签
    
    Args:
        pdf_path: PDF文件路径
        output_dir: 输出目录
        start_index: 起始图像编号(用于避免多个PDF文件名冲突)
        folder_prefix: 文件夹前缀(用于区分不同OCT类型,如"血流模式")
        use_gpu_ocr: 是否使用GPU进行OCR(多进程环境下建议False)
        cached_eye_label: 预先识别的眼别标识(如果提供,跳过OCR步骤以加速)
    
    Returns:
        提取的图像数量
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        doc = fitz.open(pdf_path)
        total_images = start_index - 1  # 从start_index-1开始,这样第一张图是start_index
        
        # PDF级别的眼别缓存(同一个PDF中的所有图片通常是同一只眼睛)
        pdf_eye_label = cached_eye_label if cached_eye_label else None
        
        # 优化: 不再一上来就渲染PDF,而是先尝试从提取的图像识别
        # 只有当提取的图像都无法识别时,才渲染PDF第一页(作为最后手段)
        tried_pdf_page_render = False
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            # 提取页面文本和图像位置信息
            text_dict = page.get_text("dict")
            
            # 提取所有文本块及其位置（用于匹配图像标签）
            text_blocks = []
            for block in text_dict["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            text_content = span["text"].strip()
                            if text_content:
                                bbox = span["bbox"]
                                text_blocks.append({
                                    'text': text_content,
                                    'x': bbox[0],
                                    'y': bbox[1]
                                })
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]
                
                try:
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    width, height = pil_image.size
                    
                    # 过滤小图（标题图和logo）
                    # OCT图像通常至少有300x300像素
                    if width < 300 or height < 300:
                        continue
                    
                    total_images += 1
                    
                    # 优先使用PDF级别缓存的眼别(同一PDF的图片通常是同一只眼睛)
                    if pdf_eye_label:
                        eye_label = pdf_eye_label
                    else:
                        # 第一次尝试: 对提取的图像进行标准OCR识别(快!)
                        eye_label = detect_eye_from_oct_image(pil_image, use_gpu=use_gpu_ocr, try_extended_region=False)
                        
                        if not eye_label:
                            # 第二次尝试: 使用扩大区域的OCR
                            eye_label = detect_eye_from_oct_image(pil_image, use_gpu=use_gpu_ocr, try_extended_region=True)
                        
                        if not eye_label:
                            # 第三次尝试: 从PDF文本识别
                            if page_num == 0:  # 只在第一页尝试
                                page_text = page.get_text()
                                has_od = 'OD' in page_text or '右眼' in page_text
                                has_os = 'OS' in page_text or '左眼' in page_text
                                if has_od and not has_os:
                                    eye_label = "_OD"
                                elif has_os and not has_od:
                                    eye_label = "_OS"
                        
                        if not eye_label and not tried_pdf_page_render and page_num == 0:
                            # 第四次尝试(最后手段): 渲染PDF第一页进行OCR识别(慢!)
                            # 只在所有图像OCR都失败且是第一页时才尝试
                            eye_label = detect_eye_from_pdf_page(doc[0], use_gpu=use_gpu_ocr)
                            tried_pdf_page_render = True
                        
                        # 成功识别到眼别后,缓存结果供后续图片使用
                        if eye_label:
                            pdf_eye_label = eye_label
                        # 如果当前图片仍未识别出眼别,继续尝试下一张图片
                        # (不缓存,继续OCR后续图片)
                    
                    # 获取图像位置
                    img_rects = page.get_image_rects(xref)
                    
                    # 查找最近的文本标签
                    label = ""
                    if img_rects and text_blocks:
                        img_rect = img_rects[0]
                        img_x = img_rect.x0
                        img_y = img_rect.y0
                        min_distance = float('inf')
                        
                        for tb in text_blocks:
                            y_distance = abs(tb['y'] - img_y)
                            x_distance = abs(tb['x'] - img_x)
                            
                            # 优先查找图像上方和左侧的标签
                            if y_distance < 80:  # 扩大Y轴搜索范围
                                if x_distance < min_distance:
                                    min_distance = x_distance
                                    label = tb['text']
                    
                    # 生成简短文件名: 眼别_文件夹前缀_位置
                    # OCT图像命名为: 眼别_文件夹前缀_位置 (如 OD_血流模式_main, OS_main)
                    eye_str = eye_label.strip('_') if eye_label else 'unknown'
                    
                    # 简短文件名
                    prefix_str = f"{folder_prefix}_" if folder_prefix else ""
                    pdf_str = f"pdf{pdf_index}_"  # 添加PDF编号
                    if len(image_list) > 1:
                        # 多图时加序号
                        output_name = f"{eye_str}_{prefix_str}{pdf_str}img{total_images}.{image_ext}"
                    else:
                        # 单图命名为 眼别_前缀_PDF编号_main
                        output_name = f"{eye_str}_{prefix_str}{pdf_str}main.{image_ext}"
                    
                    output_path = output_dir / output_name
                    pil_image.save(output_path)
                    
                except Exception as e:
                    print(f"    警告: 图像 {img_index + 1} 保存失败 - {e}")
        
        doc.close()
        return total_images
        
    except Exception as e:
        print(f"    错误: 无法处理PDF - {e}")
        return 0

def process_single_case(row, oct_type, output_base_dir, year):
    """
    处理单个病例
    
    Args:
        row: DataFrame的一行数据
        oct_type: OCT类型 ("海德堡", "科林" 或 "视微")
        output_base_dir: 输出基础目录
        year: 年份
    
    Returns:
        处理结果字典
    """
    result = {
        'patient_name': '',
        'patient_folder': '',
        'visit_date': '',
        'eye_type': '',
        'oct_extracted': 0,
        'ffa_extracted': 0,
        'oct_found': False,
        'ffa_found': False,
        'oct_path': '',
        'ffa_path': '',
        'errors': []
    }
    
    # 解析patient_folder
    patient_folder = row['patient_folder']
    patient_id, patient_name = parse_patient_folder(patient_folder)
    result['patient_name'] = patient_name
    result['patient_folder'] = patient_folder
    
    if not patient_id or not patient_name:
        result['errors'].append('无法解析患者ID或姓名')
        return result
    
    # 解析就诊日期和眼别
    visit_date_str = str(row['visit_date'])
    visit_date, eye_type = parse_visit_date(visit_date_str)
    result['visit_date'] = visit_date
    result['eye_type'] = eye_type
    
    if not visit_date:
        result['errors'].append('无法解析就诊日期')
        return result
    
    # 检查是否需要提取血流模式OCT
    # 规则: visit_date列中包含"在血流模式中"字样
    need_blood_flow = False
    if '血流' in visit_date_str or '血流模式' in visit_date_str:
        need_blood_flow = True
        result['errors'].append(f'visit_date标记了"在血流模式中",将提取血流模式OCT')
    
    # 创建输出文件夹: 姓名_眼别_日期
    folder_name = f"{patient_name}_{eye_type}_{visit_date}"
    case_output_dir = Path(output_base_dir) / folder_name
    case_output_dir.mkdir(parents=True, exist_ok=True)
    
    # OCT和FFA子文件夹
    oct_output_dir = case_output_dir / "OCT"
    ffa_output_dir = case_output_dir / "FFA"
    
    # 智能查找OCT文件夹的策略:
    # 1. 先找指定类型(海德堡/科林/视微)的指定日期
    # 2. 找不到就找其他OCT类型的指定日期
    # 3. 还找不到就找最近日期的任意OCT类型
    
    all_oct_folders = find_exam_folders(None, patient_folder, visit_date, oct_type)
    actual_oct_type = oct_type
    actual_oct_date = visit_date
    
    # 策略2: 如果指定类型未找到,尝试其他OCT类型(同一日期)
    if not all_oct_folders:
        other_oct_types = ['海德堡', '科林', '视微', 'OCT', 'Oct', 'oct']
        for other_type in other_oct_types:
            if other_type != oct_type:  # 跳过已经尝试过的类型
                all_oct_folders = find_exam_folders(None, patient_folder, visit_date, other_type)
                if all_oct_folders:
                    actual_oct_type = other_type
                    result['errors'].append(f'未找到{oct_type}OCT,使用{actual_oct_type}OCT代替')
                    break
    
    # 策略3: 如果指定日期找不到任何OCT,查找最近日期的OCT
    if not all_oct_folders:
        nearest_folders, nearest_date, nearest_type, days_diff = find_nearest_date_oct_folders(
            patient_folder, visit_date
        )
        if nearest_folders:
            all_oct_folders = nearest_folders
            actual_oct_type = nearest_type
            actual_oct_date = nearest_date
            result['errors'].append(f'当天未找到OCT,使用最近日期的OCT: {nearest_date} ({days_diff}天差距, {nearest_type})')
    
    # 根据need_blood_flow标记过滤OCT文件夹
    oct_folders = []
    normal_folders = []  # 普通OCT文件夹
    blood_flow_folders = []  # 血流模式OCT文件夹
    
    if all_oct_folders:
        for folder in all_oct_folders:
            folder_name = folder.name
            is_blood_flow_folder = "血流" in folder_name or "OCTA" in folder_name or "Angio" in folder_name.lower()
            
            if is_blood_flow_folder:
                blood_flow_folders.append(folder)
            else:
                normal_folders.append(folder)
        
        # 提取策略:
        # 1. 优先提取普通OCT文件夹
        # 2. 如果标记了血流模式,额外提取血流模式文件夹
        # 3. 如果没有普通OCT但有血流模式,也可以提取血流模式(兜底策略)
        
        if normal_folders:
            # 有普通OCT,总是提取
            oct_folders.extend(normal_folders)
            # 如果标记了需要血流模式,也提取血流模式
            if need_blood_flow and blood_flow_folders:
                oct_folders.extend(blood_flow_folders)
        elif blood_flow_folders:
            # 没有普通OCT,但有血流模式 → 提取血流模式(兜底)
            oct_folders.extend(blood_flow_folders)
            result['errors'].append(f'当天未找到普通OCT,使用血流模式OCT代替')
    
    if oct_folders:
        result['oct_found'] = True
        result['oct_path'] = ', '.join([str(f) for f in oct_folders])
        if len(oct_folders) > 1:
            result['errors'].append(f'找到{len(oct_folders)}个OCT文件夹,全部提取')
        # 只有在有普通OCT但跳过血流模式时才提示
        if normal_folders and blood_flow_folders and not need_blood_flow:
            result['errors'].append(f'跳过{len(blood_flow_folders)}个血流模式文件夹(未标记)')
        
        # 提取OCT图像（从所有匹配的文件夹中的PDF）
        image_counter = 1  # 全局图像计数器
        
        # 预先分析所有文件夹的类型
        folder_types = []
        has_blood_flow = any("血流" in f.name for f in oct_folders)
        has_octa = any("OCTA" in f.name or "Angio" in f.name.lower() for f in oct_folders)
        
        for oct_folder in oct_folders:
            # 提取文件夹关键信息作为前缀
            folder_name = oct_folder.name
            folder_prefix = ""
            
            if "血流" in folder_name:
                folder_prefix = "血流模式"
            elif "OCTA" in folder_name or "Angio" in folder_name.lower():
                folder_prefix = "OCTA"
            # 如果只有2个文件夹,一个是血流/OCTA,另一个就标记为"普通"
            elif len(oct_folders) == 2 and (has_blood_flow or has_octa):
                folder_prefix = "普通"
            # 如果有多个文件夹都没有特殊标识,用序号区分
            elif len(oct_folders) > 1:
                folder_idx = oct_folders.index(oct_folder) + 1
                folder_prefix = f"folder{folder_idx}"
            
            # 同时搜索小写.pdf和大写.PDF
            oct_pdfs = sorted(list(oct_folder.rglob('*.pdf')) + list(oct_folder.rglob('*.PDF')))
            if oct_pdfs:
                for pdf_idx, pdf in enumerate(oct_pdfs, 1):
                    # 多进程环境下禁用GPU OCR,避免资源竞争
                    # 传递PDF编号,方便识别同一PDF的图片
                    num_images = extract_oct_images_from_pdf(pdf, oct_output_dir, start_index=image_counter, folder_prefix=folder_prefix, use_gpu_ocr=False, pdf_index=pdf_idx)
                    result['oct_extracted'] += num_images
                    image_counter += num_images  # 更新计数器
        
        if result['oct_extracted'] == 0:
            result['errors'].append('OCT文件夹中未找到PDF文件')
    else:
        result['errors'].append(f'未找到任何类型的OCT文件夹')
    
    # 查找FFA文件夹
    ffa_folder = find_exam_folder(None, patient_folder, visit_date, '造影')
    if ffa_folder:
        result['ffa_found'] = True
        result['ffa_path'] = str(ffa_folder)
        
        # 提取FFA图像（使用已有的FFA提取工具）
        # 同时搜索小写.pdf和大写.PDF
        ffa_pdfs = list(ffa_folder.rglob('*.pdf')) + list(ffa_folder.rglob('*.PDF'))
        if ffa_pdfs:
            for idx, pdf in enumerate(ffa_pdfs, 1):  # 传入pdf编号
                extract_result = extract_ffa_images_from_pdf(pdf, ffa_output_dir, pdf_index=idx)
                if extract_result['status'] == 'success':
                    result['ffa_extracted'] += extract_result['num_images']
                elif extract_result['status'] == 'skipped':
                    result['errors'].append(f"FFA PDF被跳过: {extract_result['message']}")
        else:
            result['errors'].append('造影文件夹中未找到PDF文件')
    else:
        result['errors'].append('未找到造影文件夹')
    
    # 如果没有提取到任何图像，删除空文件夹
    if result['oct_extracted'] == 0 and oct_output_dir.exists():
        shutil.rmtree(oct_output_dir)
    if result['ffa_extracted'] == 0 and ffa_output_dir.exists():
        shutil.rmtree(ffa_output_dir)
    if result['oct_extracted'] == 0 and result['ffa_extracted'] == 0:
        if case_output_dir.exists():
            shutil.rmtree(case_output_dir)
    
    return result

def _process_case_worker(idx, row_dict, oct_type, output_base_dir_str, year):
    """
    进程池工作入口，接收序列化后的行数据
    """
    row_data = dict(row_dict)
    output_dir = Path(output_base_dir_str)
    result = process_single_case(row_data, oct_type, output_dir, year)
    return idx, result

def process_excel_file(excel_path, sheet_name, output_base_dir):
    """
    处理单个Excel文件中指定sheet
    
    Args:
        excel_path: Excel文件路径
        sheet_name: sheet名称 (例如: "海德堡DR")
        output_base_dir: 输出基础目录
    """
    excel_path = Path(excel_path)
    year_match = re.search(r'(\d{4})', excel_path.name)
    year = year_match.group(1) if year_match else 'unknown'
    
    print(f"\n{'='*70}")
    print(f"处理文件: {excel_path.name}")
    print(f"工作表: {sheet_name}")
    print(f"年份: {year}")
    print(f"{'='*70}\n")
    
    # 读取指定sheet
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, engine='openpyxl')
    except Exception as e:
        print(f"错误: 无法读取sheet '{sheet_name}' - {e}")
        return []
    
    print(f"找到 {len(df)} 个病例\n")
    
    results = [None] * len(df)
    total_cases = len(df)
    worker_count = min(CSC_WORKERS, total_cases) if total_cases else 1
    if worker_count > 1:
        print(f"使用并行进程数: {worker_count}\n")
    else:
        print("使用单进程顺序处理\n")

    def log_case_result(case_idx, result):
        print(f"[{case_idx+1}/{total_cases}] 患者: {result['patient_name']}")
        print(f"  日期: {result['visit_date']} ({result['eye_type']})")
        print(f"  OCT: {'✓' if result['oct_found'] else '✗'} ({result['oct_extracted']}张)")
        print(f"  FFA: {'✓' if result['ffa_found'] else '✗'} ({result['ffa_extracted']}张)")
        if result['errors']:
            print("  ⚠ 问题:")
            for error in result['errors']:
                print(f"    - {error}")
        print()

    rows_payload = [(idx, df.iloc[idx].to_dict()) for idx in range(total_cases)]

    if worker_count == 1:
        for idx, row_dict in rows_payload:
            # 优先使用海德堡OCT，其次科林和视微
            result = process_single_case(row_dict, "海德堡", output_base_dir, year)
            results[idx] = result
            log_case_result(idx, result)
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            future_to_idx = {
                executor.submit(
                    _process_case_worker,
                    idx,
                    row_dict,
                    "海德堡",  # 优先使用海德堡OCT
                    str(output_base_dir),
                    year
                ): idx
                for idx, row_dict in rows_payload
            }

            for future in as_completed(future_to_idx):
                case_idx, result = future.result()
                results[case_idx] = result
                log_case_result(case_idx, result)

    return results

def main():
    """主函数"""
    # 输入和输出目录
    input_dir = Path('/data2/xuhanyang/dataset/截图病例汇总')
    # 使用新的输出目录，避免覆盖旧结果
    output_base_dir = Path('/data2/xuhanyang/dataset/海德堡DR病例图像提取')
    
    # Excel文件
    excel_file = '海德堡OCT11-28汇总.xlsx'
    
    # 工作表名称
    sheet_name = '海德堡DR'
    
    print("="*70)
    print("海德堡DR - OCT和FFA图像提取工具")
    print("="*70)
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_base_dir}")
    print("="*70)
    
    all_results = []
    
    excel_path = input_dir / excel_file
    
    if not excel_path.exists():
        print(f"\n错误: 文件不存在 - {excel_path}")
        return
    
    results = process_excel_file(excel_path, sheet_name, output_base_dir)
    all_results.extend(results)
    
    # 生成汇总报告
    print("\n" + "="*70)
    print("处理完成 - 汇总统计")
    print("="*70)
    
    total_cases = len(all_results)
    oct_found = sum(1 for r in all_results if r['oct_found'])
    ffa_found = sum(1 for r in all_results if r['ffa_found'])
    total_oct_images = sum(r['oct_extracted'] for r in all_results)
    total_ffa_images = sum(r['ffa_extracted'] for r in all_results)
    cases_with_errors = sum(1 for r in all_results if r['errors'])
    
    if total_cases > 0:
        print(f"总病例数: {total_cases}")
        print(f"找到OCT: {oct_found} ({oct_found/total_cases*100:.1f}%)")
        print(f"找到FFA: {ffa_found} ({ffa_found/total_cases*100:.1f}%)")
    else:
        print("总病例数: 0")
        print("找到OCT: 0 (0.0%)")
        print("找到FFA: 0 (0.0%)")
    print(f"提取OCT图像: {total_oct_images} 张")
    print(f"提取FFA图像: {total_ffa_images} 张")
    print(f"有问题的病例: {cases_with_errors}")
    
    # 保存详细报告
    report_path = output_base_dir / "提取报告.txt"
    output_base_dir.mkdir(parents=True, exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("海德堡DR - 图像提取报告\n")
        f.write("="*70 + "\n\n")
        f.write(f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"输出目录: {output_base_dir}\n\n")
        
        f.write(f"总病例数: {total_cases}\n")
        f.write(f"找到OCT: {oct_found} ({oct_found/total_cases*100:.1f}%)\n")
        f.write(f"找到FFA: {ffa_found} ({ffa_found/total_cases*100:.1f}%)\n")
        f.write(f"提取OCT图像: {total_oct_images} 张\n")
        f.write(f"提取FFA图像: {total_ffa_images} 张\n")
        f.write(f"有问题的病例: {cases_with_errors}\n\n")
        
        f.write("="*70 + "\n")
        f.write("详细病例列表\n")
        f.write("="*70 + "\n\n")
        
        for i, r in enumerate(all_results, 1):
            f.write(f"{i}. {r['patient_name']} - {r['visit_date']} ({r['eye_type']})\n")
            f.write(f"   OCT: {'✓' if r['oct_found'] else '✗'} ({r['oct_extracted']}张)\n")
            f.write(f"   FFA: {'✓' if r['ffa_found'] else '✗'} ({r['ffa_extracted']}张)\n")
            
            if r['errors']:
                f.write(f"   问题:\n")
                for error in r['errors']:
                    f.write(f"     - {error}\n")
            
            if r['oct_path']:
                f.write(f"   OCT路径: {r['oct_path']}\n")
            if r['ffa_path']:
                f.write(f"   FFA路径: {r['ffa_path']}\n")
            
            f.write("\n")
    
    print(f"\n详细报告已保存: {report_path}")
    print("="*70)

if __name__ == '__main__':
    main()