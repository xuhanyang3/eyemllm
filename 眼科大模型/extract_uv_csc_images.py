#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从葡萄膜炎病例中提取OCT和FFA图像
基于 extract_uv_images.py 修改而来:
- 数据根目录: /share/kongzitai/ophthalmology/E:/<year>
- 使用 Excel: dataset/截图病例汇总/海德堡OCT11-28汇总.xlsx
- 处理 sheet: "UV CSC找不到名单"
- OCT/FFA 日期分别来自: oct_date / ffa_date 列
- 如果 oct_type 中包含 "误标科林血流模式", 优先从血流模式文件夹下读取OCT
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
DEFAULT_WORKERS = max(1, min(8, CPU_COUNT))  # 使用8个进程
CONFIGURED_WORKERS = os.environ.get('UV_WORKERS')
try:
    UV_WORKERS = int(CONFIGURED_WORKERS) if CONFIGURED_WORKERS else DEFAULT_WORKERS
except ValueError:
    UV_WORKERS = DEFAULT_WORKERS
UV_WORKERS = max(1, UV_WORKERS)

# 导入FFA提取功能
sys.path.append('/data2/xuhanyang/眼科大模型')
from extract_ffa_only import extract_ffa_images_from_pdf


def parse_patient_folder(folder_str):
    """
    解析patient_folder字符串
    例如: "02036873 陈康炎 男 1973-11-11"
    返回: (patient_id, patient_name, eye_info)
    eye_info: 从folder_str中提取的眼睛信息 ("单眼" 或 "双眼")
    """
    parts = str(folder_str).strip().split()
    patient_id = None
    patient_name = None
    eye_info = ""
    
    if len(parts) >= 2:
        patient_id = parts[0]
        patient_name = parts[1]
    
    # 从folder_str中提取眼睛信息（单眼/双眼）
    folder_str = str(folder_str)
    if '双眼' in folder_str:
        eye_info = "双眼"
    elif '单眼' in folder_str:
        eye_info = "单眼"
    
    return patient_id, patient_name, eye_info


def parse_visit_date(date_str):
    """
    解析就诊/检查日期字段
    例如:
        "2024-12-14 单眼" -> ("2024-12-14", "单眼")
        "2019-01-07 排版4" -> ("2019-01-07", "")
    """
    date_str = str(date_str).strip()

    # 提取眼别（单眼/双眼），如果没有就返回空字符串
    eye_type = "单眼" if "单眼" in date_str else ("双眼" if "双眼" in date_str else "")

    # 提取日期部分
    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
    if date_match:
        date_part = date_match.group(1)
        return date_part, eye_type

    return None, eye_type


def find_exam_folders(base_path, patient_id, visit_date, exam_keyword):
    """
    查找所有匹配的检查文件夹(支持多个文件夹,如血流模式和普通模式)

    与 DR 版本的差异:
    - 数据路径为 /share/kongzitai/ophthalmology/E:/<year>/<month_folder>/<patient>...
      不再带 "-糖尿病性视网膜病变" 后缀
    
    查找策略:
    1. 先根据visit_date的月份，找到对应的月份文件夹
    2. 如果找不到，再依次查找其他月份文件夹
    """
    found_folders = []
    # 情况1: 如果提供了 patient_path，先尝试在该路径下查找
    # 但如果找不到，还是要根据日期的月份在正确的月份文件夹下查找
    if base_path:
        patient_root = Path(str(base_path))
        if patient_root.exists() and visit_date:
            date_folder = patient_root / visit_date
            if date_folder.exists():
                try:
                    for item in date_folder.iterdir():
                        if item.is_dir() and exam_keyword in item.name:
                            found_folders.append(item)
                except PermissionError:
                    pass
            # 如果找到了，直接返回
            if found_folders:
                return found_folders
        # 如果patient_path下找不到，继续用情况2的逻辑（根据日期月份查找）

    # 情况2: 根据日期月份+patient_id 方式搜索（无论是否有patient_path，如果情况1失败都会执行这里）
    if not patient_id or not visit_date:
        return []

    year = visit_date[:4]
    
    # 从日期中提取月份
    try:
        date_obj = datetime.strptime(visit_date, '%Y-%m-%d')
        target_month = date_obj.month
    except:
        target_month = None

    possible_bases = [
        f'/share/kongzitai/ophthalmology/E:/{year}',
    ]

    for base in possible_bases:
        year_root = Path(base)
        if not year_root.exists():
            continue

        # 获取所有月份文件夹
        month_folders = []
        try:
            for item in year_root.iterdir():
                if item.is_dir():
                    month_folders.append(item)
        except PermissionError:
            continue
        
        if not month_folders:
            continue
        
        # 根据月份构建查找顺序：先找目标月份，再找其他月份
        search_order = []
        if target_month:
            # 先添加匹配目标月份的文件夹
            for month_folder in month_folders:
                month_name = month_folder.name
                month_match = False
                
                # 方法1: 直接匹配单个数字，如 "1", "2", "3"
                if month_name == str(target_month):
                    month_match = True
                
                # 方法2: 匹配连在一起的数字，如 "123" 表示1、2、3月，"456" 表示4、5、6月
                elif month_name.isdigit():
                    if str(target_month) in month_name:
                        month_match = True
                
                # 方法3: 匹配范围格式，如 "1-2", "1--2", "1-3", "10-12", "10--12"
                elif '-' in month_name or '--' in month_name:
                    # 提取范围的两个数字
                    range_parts = re.split(r'-+', month_name)
                    if len(range_parts) >= 2:
                        try:
                            start_month = int(range_parts[0])
                            end_month = int(range_parts[1])
                            # 检查目标月份是否在范围内（考虑跨年情况）
                            if start_month <= end_month:
                                # 正常范围，如 1-3, 4-6, 10-12
                                if start_month <= target_month <= end_month:
                                    month_match = True
                            else:
                                # 跨年范围，如 12-1 (12月到1月)
                                if target_month >= start_month or target_month <= end_month:
                                    month_match = True
                        except ValueError:
                            pass
                
                if month_match and month_folder not in search_order:
                    search_order.append(month_folder)
            
            # 再添加其他月份文件夹
            for month_folder in month_folders:
                if month_folder not in search_order:
                    search_order.append(month_folder)
        else:
            # 如果无法解析月份，按原始顺序搜索
            search_order = month_folders

        # 按顺序搜索月份文件夹
        for month_folder in search_order:
            # 在该月份文件夹下查找患者文件夹，使用patient_id
            patient_folders = list(month_folder.glob(f'{patient_id}*'))
            
            for patient_path in patient_folders:
                date_folder = patient_path / visit_date
                if not date_folder.exists():
                    continue

                try:
                    for item in date_folder.iterdir():
                        if item.is_dir() and exam_keyword in item.name:
                            found_folders.append(item)
                except PermissionError:
                    continue

            # 如果找到了，就不再搜索其他月份
            if found_folders:
                break

        if found_folders:
            break

    return found_folders


def find_exam_folder(base_path, patient_id, visit_date, exam_keyword):
    """返回第一个匹配的检查文件夹(用于FFA等单一检查)"""
    folders = find_exam_folders(base_path, patient_id, visit_date, exam_keyword)
    return folders[0] if folders else None


def find_nearest_date_oct_folders(patient_id, visit_date, oct_keywords=None):
    """
    查找最近日期的OCT文件夹(当指定日期找不到时使用)
    """
    from datetime import datetime as _dt

    if oct_keywords is None:
        oct_keywords = ['科林', '视微', '海德堡', 'OCT']

    if not patient_id or not visit_date:
        return [], None, None, None

    year = visit_date[:4]
    possible_bases = [
        f'/share/kongzitai/ophthalmology/E:/{year}',
    ]

    try:
        target_date = _dt.strptime(visit_date, '%Y-%m-%d')
    except Exception:
        return [], None, None, None

    available_dates = []  # [(date_obj, date_str, oct_folders, oct_type), ...]

    for base in possible_bases:
        base_path = Path(base)
        if not base_path.exists():
            continue

        # 同样考虑月份子目录: 年份/月份段/患者文件夹
        # 获取所有月份文件夹
        month_folders = []
        try:
            for item in base_path.iterdir():
                if item.is_dir():
                    month_folders.append(item)
        except PermissionError:
            continue
        
        # 在所有月份文件夹下查找患者
        for month_folder in month_folders:
            patient_folders = list(month_folder.glob(f'{patient_id}*'))
            if not patient_folders:
                continue

            for patient_path in patient_folders:
                try:
                    for date_folder in patient_path.iterdir():
                        if not date_folder.is_dir():
                            continue

                        date_str = date_folder.name
                        try:
                            date_obj = _dt.strptime(date_str, '%Y-%m-%d')
                        except Exception:
                            continue

                        for oct_keyword in oct_keywords:
                            oct_folders = []
                            for item in date_folder.iterdir():
                                if item.is_dir() and oct_keyword in item.name:
                                    oct_folders.append(item)

                            if oct_folders:
                                available_dates.append((date_obj, date_str, oct_folders, oct_keyword))
                                break
                except PermissionError:
                    continue

        if available_dates:
            break

    if not available_dates:
        return [], None, None, None

    available_dates.sort(key=lambda x: abs((x[0] - target_date).days))
    nearest = available_dates[0]
    days_diff = abs((nearest[0] - target_date).days)
    return nearest[2], nearest[1], nearest[3], days_diff


# ---------------- OCR & OCT PDF 提取，与原脚本保持一致 ----------------

_ocr_reader = None


def get_ocr_reader(use_gpu=True):
    """获取或创建OCR reader(单例模式)"""
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        import torch
        gpu_available = torch.cuda.is_available() and use_gpu
        _ocr_reader = easyocr.Reader(['en'], gpu=gpu_available, verbose=False)
    return _ocr_reader


def detect_eye_from_oct_image(pil_image, use_gpu=True, try_extended_region=False):
    """与 extract_csc_images.py 中实现一致，略"""
    try:
        import tempfile
        from PIL import ImageEnhance

        width, height = pil_image.size
        reader = get_ocr_reader(use_gpu=use_gpu)

        detection_regions = [
            (int(width * 0.92), 0, width, int(height * 0.08), "right_corner"),
            (int(width * 0.80), 0, width, int(height * 0.12), "standard"),
        ]
        if try_extended_region:
            detection_regions.extend([
                (int(width * 0.70), 0, width, int(height * 0.20), "extended"),
                (0, 0, width, int(height * 0.15), "full_top"),
            ])

        for x1, y1, x2, y2, region_name in detection_regions:
            try:
                region = pil_image.crop((x1, y1, x2, y2))
                enhancer = ImageEnhance.Contrast(region)
                region = enhancer.enhance(2.0)

                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                    region.save(tmp.name)
                    tmp_path = tmp.name

                results = reader.readtext(tmp_path)
                Path(tmp_path).unlink()

                text = ' '.join([result[1].upper() for result in results])
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
            except Exception:
                continue
    except Exception:
        pass
    return ""


def detect_eye_from_pdf_page(page, use_gpu=False):
    """从PDF页面右上角识别眼别，保持与原实现一致"""
    try:
        import tempfile

        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        page_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        width, height = page_img.size
        right_top = page_img.crop((int(width * 0.90), 0, width, int(height * 0.08)))

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            right_top.save(tmp.name)
            tmp_path = tmp.name

        reader = get_ocr_reader(use_gpu=use_gpu)
        results = reader.readtext(tmp_path)
        Path(tmp_path).unlink()

        text = ' '.join([result[1].upper() for result in results])
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
    except Exception:
        pass
    return ""


def extract_oct_images_from_pdf(pdf_path, output_dir, start_index=1, folder_prefix="", use_gpu_ocr=False,
                                cached_eye_label=None, pdf_index=1):
    """
    从OCT PDF中提取图像,识别眼别和标签
    逻辑与 extract_csc_images.py 中实现基本一致，只是文件名前缀略有不同
    """
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        doc = fitz.open(pdf_path)
        total_images = start_index - 1
        pdf_eye_label = cached_eye_label if cached_eye_label else None
        tried_pdf_page_render = False

        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()

            text_dict = page.get_text("dict")
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

                    if width < 300 or height < 300:
                        continue

                    total_images += 1

                    if pdf_eye_label:
                        eye_label = pdf_eye_label
                    else:
                        eye_label = detect_eye_from_oct_image(pil_image, use_gpu=use_gpu_ocr, try_extended_region=False)
                        if not eye_label:
                            eye_label = detect_eye_from_oct_image(pil_image, use_gpu=use_gpu_ocr, try_extended_region=True)

                        if not eye_label and page_num == 0:
                            page_text = page.get_text()
                            has_od = 'OD' in page_text or '右眼' in page_text
                            has_os = 'OS' in page_text or '左眼' in page_text
                            if has_od and not has_os:
                                eye_label = "_OD"
                            elif has_os and not has_od:
                                eye_label = "_OS"

                        if not eye_label and not tried_pdf_page_render and page_num == 0:
                            eye_label = detect_eye_from_pdf_page(doc[0], use_gpu=use_gpu_ocr)
                            tried_pdf_page_render = True

                        if eye_label:
                            pdf_eye_label = eye_label

                    # 文件命名
                    eye_str = eye_label.strip('_') if eye_label else 'unknown'
                    prefix_str = f"{folder_prefix}_" if folder_prefix else ""
                    pdf_str = f"pdf{pdf_index}_"
                    if len(image_list) > 1:
                        output_name = f"{eye_str}_{prefix_str}{pdf_str}img{total_images}.{image_ext}"
                    else:
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
    处理单个葡萄膜炎病例 (科林 / 视微)
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

    # 患者姓名: 直接使用Excel中的 patient_name 列(保证与信息表一致)
    patient_name = str(row.get('patient_name', '')).strip()
    result['patient_name'] = patient_name

    # patient_folder 字段是眼别信息，用于文件夹命名
    patient_folder = str(row.get('patient_folder', '')).strip()
    result['patient_folder'] = patient_folder

    # patient_path: 真正的磁盘路径 (优先用于查找检查文件夹)
    patient_path = row.get('patient_path', None)
    
    # patient_id: 优先从patient_path解析（因为路径中的ID格式更准确，可能有前导0）
    # 如果patient_path不存在，再从patient_id列读取
    patient_id = None
    if isinstance(patient_path, str) and patient_path:
        # 从patient_path中提取patient_id（路径格式：.../08888298 陈美娟 女 1955-08-09）
        last_part = Path(patient_path).name
        patient_id, _, _ = parse_patient_folder(last_part)
    
    # 如果从patient_path解析失败，使用Excel的patient_id列
    if not patient_id:
        patient_id_str = str(row.get('patient_id', '')).strip()
        if patient_id_str:
            patient_id = patient_id_str

    if not patient_name:
        result['errors'].append('无法解析患者姓名')
        return result

    # 解析就诊日期和眼别(用于输出文件夹命名)
    visit_date_str = str(row.get('visit_date', ''))
    visit_date, eye_type = parse_visit_date(visit_date_str)
    result['visit_date'] = visit_date or ''
    result['eye_type'] = eye_type

    # OCT / FFA 各自的检查日期
    oct_date_raw = row.get('oct_date', '')
    ffa_date_raw = row.get('ffa_date', '')
    oct_date, _ = parse_visit_date(oct_date_raw)
    ffa_date, _ = parse_visit_date(ffa_date_raw)

    if not oct_date:
        # 回落到就诊日期
        oct_date = visit_date
        result['errors'].append('无法解析OCT日期, 使用visit_date代替')
    if not ffa_date:
        ffa_date = visit_date
        result['errors'].append('无法解析FFA日期, 使用visit_date代替')

    if not oct_date and not ffa_date:
        result['errors'].append('无法解析任何日期')
        return result

    # oct_type 字段, 判断是否"误标科林血流模式"或包含"脉络膜"
    oct_type_cell = str(row.get('oct_type', oct_type))
    force_blood_flow_only = '误标科林血流模式' in oct_type_cell
    skip_oct_extraction = '脉络膜' in oct_type_cell  # 如果包含"脉络膜"，跳过OCT图像提取但保留文件夹

    # 直接使用patient_folder列的内容作为文件夹命名的一部分
    # 处理文件夹名中不允许的字符（替换为下划线）
    eye_part = patient_folder if patient_folder else ""
    # 替换文件夹名中不允许的字符
    eye_part = re.sub(r'[<>:"/\\|?*]', '_', eye_part)  # 替换Windows/Linux不允许的字符
    eye_part = eye_part.strip()  # 去除首尾空格
    
    # 创建输出文件夹: 姓名_patient_folder内容_日期(就诊日期)
    folder_name = f"{patient_name}_{eye_part}_{visit_date or 'unknown'}"
    case_output_dir = Path(output_base_dir) / folder_name
    case_output_dir.mkdir(parents=True, exist_ok=True)

    oct_output_dir = case_output_dir / "OCT"
    ffa_output_dir = case_output_dir / "FFA"

    # ---------------- 查找 & 提取 OCT ----------------
    # 优先查找顺序：1. 海德堡OCT，2. 其他OCT设备
    # 根据oct_type列判断是否需要查找血流模式文件夹
    
    # 首先检查oct_type列是否提到血流模式
    oct_type_cell = str(row.get('oct_type', ''))
    contains_blood_flow = '血流' in oct_type_cell
    
    # 定义OCT查找优先级
    oct_priority = ['海德堡', '科林', '视微', 'OCT']
    
    # 如果oct_type提到血流模式，则优先查找血流模式文件夹
    if contains_blood_flow:
        # 优先查找海德堡血流模式，然后是其他设备的血流模式
        oct_priority_with_blood_flow = []
        for oct_type in oct_priority:
            # 先尝试查找普通OCT
            all_oct_folders = find_exam_folders(patient_path, patient_id, oct_date, oct_type)
            normal_folders = []
            blood_flow_folders = []
            
            if all_oct_folders:
                for folder in all_oct_folders:
                    folder_name_fs = folder.name
                    is_blood_flow_folder = ("血流" in folder_name_fs) or ("OCTA" in folder_name_fs) or ("Angio" in folder_name_fs.lower())
                    if is_blood_flow_folder:
                        blood_flow_folders.append(folder)
                    else:
                        normal_folders.append(folder)
            
            # 如果找到血流模式文件夹，优先使用
            if blood_flow_folders:
                oct_folders = blood_flow_folders
                actual_oct_type = f"{oct_type}(血流模式)"
                break
            # 如果只有普通文件夹，也使用
            elif normal_folders:
                oct_folders = normal_folders
                actual_oct_type = oct_type
                break
        else:
            # 如果所有设备类型都没找到，尝试其他查找方式
            oct_folders = []
            actual_oct_type = oct_type
    else:
        # 如果oct_type没有提到血流模式，优先查找非血流模式的海德堡OCT
        oct_folders = []
        actual_oct_type = oct_type
        
        # 按优先级查找OCT
        for oct_type in oct_priority:
            all_oct_folders = find_exam_folders(patient_path, patient_id, oct_date, oct_type)
            normal_folders = []
            blood_flow_folders = []
            
            if all_oct_folders:
                for folder in all_oct_folders:
                    folder_name_fs = folder.name
                    is_blood_flow_folder = ("血流" in folder_name_fs) or ("OCTA" in folder_name_fs) or ("Angio" in folder_name_fs.lower())
                    if is_blood_flow_folder:
                        blood_flow_folders.append(folder)
                    else:
                        normal_folders.append(folder)
            
            # 优先使用非血流模式文件夹
            if normal_folders:
                oct_folders = normal_folders
                actual_oct_type = oct_type
                break
            # 如果只有血流模式文件夹，也使用
            elif blood_flow_folders:
                oct_folders = blood_flow_folders
                actual_oct_type = f"{oct_type}(血流模式)"
                break
        
        # 如果按优先级没找到，使用原始逻辑
        if not oct_folders:
            all_oct_folders = find_exam_folders(patient_path, patient_id, oct_date, oct_type)
            normal_folders = []
            blood_flow_folders = []
            
            if all_oct_folders:
                for folder in all_oct_folders:
                    folder_name_fs = folder.name
                    is_blood_flow_folder = ("血流" in folder_name_fs) or ("OCTA" in folder_name_fs) or ("Angio" in folder_name_fs.lower())
                    if is_blood_flow_folder:
                        blood_flow_folders.append(folder)
                    else:
                        normal_folders.append(folder)
                
                # 正常策略: 优先普通OCT
                if normal_folders:
                    oct_folders = normal_folders
                elif blood_flow_folders:
                    oct_folders = blood_flow_folders
    
    # 如果还是没找到，尝试其他OCT关键字
    if not oct_folders:
        other_oct_types = ['海德堡', '科林', '视微', 'OCT', 'Oct', 'oct']
        for other_type in other_oct_types:
            if other_type != oct_type:
                all_oct_folders = find_exam_folders(patient_path, patient_id, oct_date, other_type)
                if all_oct_folders:
                    oct_folders = all_oct_folders
                    actual_oct_type = other_type
                    result['errors'].append(f'未找到{oct_type}OCT, 使用{actual_oct_type}OCT代替')
                    break

    # 如果指定日期没找到，尝试最近日期
    if not oct_folders and oct_date:
        nearest_folders, nearest_date, nearest_type, days_diff = find_nearest_date_oct_folders(
            patient_id, oct_date
        )
        if nearest_folders:
            oct_folders = nearest_folders
            actual_oct_type = nearest_type
            actual_oct_date = nearest_date
            result['errors'].append(f'指定日期未找到OCT, 使用最近日期的OCT: {nearest_date} ({days_diff}天差距, {nearest_type})')

    if oct_folders:
        result['oct_found'] = True
        result['oct_path'] = ', '.join([str(f) for f in oct_folders])
        if len(oct_folders) > 1:
            result['errors'].append(f'找到{len(oct_folders)}个OCT文件夹, 全部提取')

        # 如果oct_type包含"脉络膜"，跳过图像提取但保留文件夹
        if skip_oct_extraction:
            result['errors'].append('oct_type包含"脉络膜", 跳过OCT图像提取, 仅创建OCT文件夹')
            # 确保OCT文件夹存在
            oct_output_dir.mkdir(parents=True, exist_ok=True)
        else:
            # 正常提取OCT图像
            image_counter = 1
            has_blood_flow = any("血流" in f.name or "OCTA" in f.name or "Angio" in f.name.lower() for f in oct_folders)

            for oct_folder in oct_folders:
                folder_name_fs = oct_folder.name
                folder_prefix = ""

                if "血流" in folder_name_fs:
                    folder_prefix = "血流模式"
                elif "OCTA" in folder_name_fs or "Angio" in folder_name_fs.lower():
                    folder_prefix = "OCTA"
                elif len(oct_folders) == 2 and has_blood_flow:
                    folder_prefix = "普通"
                elif len(oct_folders) > 1:
                    folder_idx = oct_folders.index(oct_folder) + 1
                    folder_prefix = f"folder{folder_idx}"

                oct_pdfs = sorted(list(oct_folder.rglob('*.pdf')) + list(oct_folder.rglob('*.PDF')))
                if oct_pdfs:
                    for pdf_idx, pdf in enumerate(oct_pdfs, 1):
                        num_images = extract_oct_images_from_pdf(
                            pdf,
                            oct_output_dir,
                            start_index=image_counter,
                            folder_prefix=folder_prefix,
                            use_gpu_ocr=False,
                            pdf_index=pdf_idx
                        )
                        result['oct_extracted'] += num_images
                        image_counter += num_images
                else:
                    result['errors'].append('OCT文件夹中未找到PDF文件')
    else:
        result['errors'].append('未找到任何OCT文件夹')

    # ---------------- 查找 & 提取 FFA ----------------
    if ffa_date:
        ffa_folder = find_exam_folder(patient_path, patient_id, ffa_date, '造影')
    else:
        ffa_folder = None

    if ffa_folder:
        result['ffa_path'] = str(ffa_folder)

        # 首先尝试查找PDF文件
        ffa_pdfs = list(ffa_folder.rglob('*.pdf')) + list(ffa_folder.rglob('*.PDF'))
        if ffa_pdfs:
            result['ffa_found'] = True
            for idx, pdf in enumerate(ffa_pdfs, 1):
                extract_result = extract_ffa_images_from_pdf(pdf, ffa_output_dir, pdf_index=idx)
                if extract_result['status'] == 'success':
                    result['ffa_extracted'] += extract_result['num_images']
                elif extract_result['status'] == 'skipped':
                    result['errors'].append(f"FFA PDF被跳过: {extract_result['message']}")
        else:
            # 如果没有PDF文件，尝试查找直接的图像文件
            image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff']
            image_files = []
            
            for ext in image_extensions:
                image_files.extend(ffa_folder.glob(f'*{ext}'))
                image_files.extend(ffa_folder.glob(f'*{ext.upper()}'))
            
            if image_files:
                result['ffa_found'] = True
                ffa_output_dir.mkdir(parents=True, exist_ok=True)
                
                # 复制图像文件
                for img_file in sorted(image_files):
                    try:
                        dest_path = ffa_output_dir / img_file.name
                        shutil.copy2(img_file, dest_path)
                        result['ffa_extracted'] += 1
                    except Exception as e:
                        result['errors'].append(f"复制FFA图像失败: {img_file.name} - {e}")
                
                result['errors'].append(f'FFA文件夹中未找到PDF文件，但找到{len(image_files)}个图像文件并已复制')
            else:
                result['errors'].append('造影文件夹中未找到PDF文件或图像文件')
                result['ffa_found'] = False
    else:
        result['errors'].append('未找到造影文件夹')
        result['ffa_found'] = False

    # 如果没有提取到任何图像，删除空文件夹
    # 但如果是因为"脉络膜"而跳过提取，保留OCT文件夹
    if result['oct_extracted'] == 0 and oct_output_dir.exists() and not skip_oct_extraction:
        shutil.rmtree(oct_output_dir)
    if result['ffa_extracted'] == 0 and ffa_output_dir.exists():
        shutil.rmtree(ffa_output_dir)
    # 如果OCT和FFA都没有提取到图像，且不是因为"脉络膜"而保留OCT文件夹，则删除整个病例文件夹
    if result['oct_extracted'] == 0 and result['ffa_extracted'] == 0:
        if not (skip_oct_extraction and oct_output_dir.exists()):
            if case_output_dir.exists():
                shutil.rmtree(case_output_dir)

    return result


def _process_case_worker(idx, row_dict, oct_type, output_base_dir_str, year):
    """
    工作者进程入口, 接收纯dict数据并调用process_single_case
    """
    row_data = dict(row_dict)
    output_dir = Path(output_base_dir_str)
    result = process_single_case(row_data, oct_type, output_dir, year)
    return idx, result


def process_excel_sheet(excel_path, sheet_name, output_base_dir):
    """
    处理葡萄膜炎Excel中的单个 sheet (科林 / 视微)
    """
    excel_path = Path(excel_path)
    year_match = re.search(r'(\d{4})', excel_path.name)
    year = year_match.group(1) if year_match else 'unknown'

    print(f"\n{'='*70}")
    print(f"处理文件: {excel_path.name}")
    print(f"Sheet: {sheet_name}")
    print(f"年份: {year} (仅用于报告, 实际路径按各行日期解析)")
    print(f"{'='*70}\n")

    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, engine='openpyxl')
    except Exception as e:
        print(f"错误: 无法读取sheet '{sheet_name}' - {e}")
        return []

    total_cases = len(df)
    print(f"找到 {total_cases} 个病例\n")

    if total_cases == 0:
        return []

    worker_count = min(UV_WORKERS, total_cases)
    if worker_count > 1:
        print(f"使用并行进程数: {worker_count}\n")
    else:
        print("使用单进程顺序处理\n")

    results = [None] * total_cases

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
            result = process_single_case(row_dict, sheet_name, output_base_dir, year)
            results[idx] = result
            log_case_result(idx, result)
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            future_to_idx = {
                executor.submit(
                    _process_case_worker,
                    idx,
                    row_dict,
                    sheet_name,
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
    """主函数: 从葡萄膜炎Excel中提取OCT和FFA"""
    input_excel = Path('/data2/xuhanyang/dataset/截图病例汇总/海德堡OCT11-28汇总.xlsx')
    output_base_dir = Path('/data2/xuhanyang/dataset/UV_CSC找不到名单图像提取')

    sheets = ['UV CSC找不到名单']

    print("="*70)
    print("UV CSC找不到名单 - OCT和FFA图像提取工具")
    print("="*70)
    print(f"Excel文件: {input_excel}")
    print(f"处理Sheet: {', '.join(sheets)}")
    print(f"输出目录: {output_base_dir}")
    print("="*70)

    if not input_excel.exists():
        print(f"错误: Excel文件不存在 - {input_excel}")
        return

    all_results = []
    for sheet in sheets:
        results = process_excel_sheet(input_excel, sheet, output_base_dir)
        all_results.extend(results)

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
    output_base_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_base_dir / "提取报告_UV_CSC找不到名单.txt"

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("UV CSC找不到名单 - 图像提取报告\n")
        f.write("="*70 + "\n\n")
        f.write(f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Excel文件: {input_excel}\n")
        f.write(f"输出目录: {output_base_dir}\n\n")

        f.write(f"总病例数: {total_cases}\n")
        f.write(f"找到OCT: {oct_found} ({(oct_found/total_cases*100 if total_cases else 0):.1f}%)\n")
        f.write(f"找到FFA: {ffa_found} ({(ffa_found/total_cases*100 if total_cases else 0):.1f}%)\n")
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
                f.write("   问题:\n")
                for e in r['errors']:
                    f.write(f"     - {e}\n")
            if r['oct_path']:
                f.write(f"   OCT路径: {r['oct_path']}\n")
            if r['ffa_path']:
                f.write(f"   FFA路径: {r['ffa_path']}\n")
            f.write("\n")

    print(f"\n详细报告已保存: {report_path}")
    print("="*70)


if __name__ == '__main__':
    main()