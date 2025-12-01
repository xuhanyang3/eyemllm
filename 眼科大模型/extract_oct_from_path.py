#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从指定路径提取OCT图像
支持海德堡OCT
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
        pdf_index: PDF文件编号(用于区分不同PDF文件)
    
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

def extract_oct_images_from_path(input_path, output_dir):
    """
    从指定路径提取OCT图像
    
    Args:
        input_path: 输入路径
        output_dir: 输出目录
    
    Returns:
        处理结果字典
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    result = {
        'input_path': str(input_path),
        'output_dir': str(output_dir),
        'total_images': 0,
        'pdf_count': 0,
        'errors': []
    }
    
    # 从路径中解析患者信息
    # 例如: /share/kongzitai/ophthalmology/E:/2024-中心性浆液性脉络膜视网膜病变/16498974 洪学娥 女 1965-12-07/2024-03-22/海德堡OCT(双眼) 3001B房间
    path_parts = input_path.parts
    
    # 查找患者信息部分
    patient_info = None
    visit_date = None
    
    for part in path_parts:
        # 检查是否是患者信息 (格式: ID 姓名 性别 出生日期)
        if re.match(r'^\d+.*\d{4}-\d{2}-\d{2}', part):
            patient_info = part
        # 检查是否是就诊日期 (格式: YYYY-MM-DD)
        elif re.match(r'^\d{4}-\d{2}-\d{2}$', part):
            visit_date = part
    
    if patient_info:
        # 解析患者信息
        parts = patient_info.split()
        if len(parts) >= 2:
            patient_id = parts[0]
            patient_name = parts[1]
            
            # 创建患者专用输出目录
            if visit_date:
                patient_dir = output_dir / f"{patient_name}_{visit_date}"
            else:
                patient_dir = output_dir / patient_name
            
            oct_dir = patient_dir / "OCT"
            oct_dir.mkdir(parents=True, exist_ok=True)
            
            result['patient_name'] = patient_name
            result['patient_id'] = patient_id
            result['visit_date'] = visit_date
            result['oct_dir'] = str(oct_dir)
        else:
            result['errors'].append(f"无法解析患者信息: {patient_info}")
            oct_dir = output_dir
    else:
        # 如果找不到患者信息，使用输出目录
        oct_dir = output_dir
        result['errors'].append("无法从路径中解析患者信息")
    
    print(f"处理路径: {input_path}")
    if patient_info:
        print(f"患者信息: {patient_info}")
    if visit_date:
        print(f"就诊日期: {visit_date}")
    
    # 查找所有PDF文件
    pdf_files = list(input_path.glob('*.pdf')) + list(input_path.glob('*.PDF'))
    
    if not pdf_files:
        result['errors'].append("未找到PDF文件")
        return result
    
    print(f"找到 {len(pdf_files)} 个PDF文件")
    
    # 处理每个PDF文件
    image_counter = 1
    for pdf_idx, pdf_file in enumerate(pdf_files, 1):
        print(f"  处理PDF {pdf_idx}/{len(pdf_files)}: {pdf_file.name}")
        
        # 提取文件夹关键信息作为前缀
        folder_name = input_path.name
        folder_prefix = ""
        
        if "血流" in folder_name:
            folder_prefix = "血流模式"
        elif "OCTA" in folder_name or "Angio" in folder_name.lower():
            folder_prefix = "OCTA"
        elif "海德堡" in folder_name:
            folder_prefix = "海德堡"
        
        # 提取图像
        num_images = extract_oct_images_from_pdf(
            pdf_file, 
            oct_dir, 
            start_index=image_counter, 
            folder_prefix=folder_prefix, 
            use_gpu_ocr=False, 
            pdf_index=pdf_idx
        )
        
        # 计算实际提取的图像数量（从start_index开始计算）
        actual_images = num_images - (image_counter - 1)
        result['total_images'] += actual_images
        image_counter = num_images + 1
        result['pdf_count'] += 1
        
        print(f"    提取了 {actual_images} 张图像")
    
    return result

def main():
    """主函数"""
    # 输入路径
    input_path = '/share/kongzitai/ophthalmology/E:/2024-中心性浆液性脉络膜视网膜病变/16498974 洪学娥 女 1965-12-07/2024-03-22/海德堡OCT(双眼) 3001B房间'
    
    # 输出目录
    output_dir = '/data2/xuhanyang/dataset/提取的OCT图像'
    
    print("="*70)
    print("OCT图像提取工具")
    print("="*70)
    print(f"输入路径: {input_path}")
    print(f"输出目录: {output_dir}")
    print("="*70)
    
    # 提取OCT图像
    result = extract_oct_images_from_path(input_path, output_dir)
    
    # 显示结果
    print("\n" + "="*70)
    print("提取完成 - 结果统计")
    print("="*70)
    print(f"输入路径: {result['input_path']}")
    print(f"输出目录: {result['output_dir']}")
    print(f"处理的PDF文件数: {result['pdf_count']}")
    print(f"提取的图像总数: {result['total_images']}")
    
    if 'patient_name' in result:
        print(f"患者姓名: {result['patient_name']}")
    if 'patient_id' in result:
        print(f"患者ID: {result['patient_id']}")
    if 'visit_date' in result:
        print(f"就诊日期: {result['visit_date']}")
    
    if result['errors']:
        print("\n错误/警告:")
        for error in result['errors']:
            print(f"  - {error}")
    
    # 保存详细报告
    report_path = Path(output_dir) / "提取报告.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("OCT图像提取报告\n")
        f.write("="*70 + "\n\n")
        f.write(f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"输入路径: {result['input_path']}\n")
        f.write(f"输出目录: {result['output_dir']}\n\n")
        
        f.write(f"处理的PDF文件数: {result['pdf_count']}\n")
        f.write(f"提取的图像总数: {result['total_images']}\n")
        
        if 'patient_name' in result:
            f.write(f"患者姓名: {result['patient_name']}\n")
        if 'patient_id' in result:
            f.write(f"患者ID: {result['patient_id']}\n")
        if 'visit_date' in result:
            f.write(f"就诊日期: {result['visit_date']}\n")
        
        if result['errors']:
            f.write("\n错误/警告:\n")
            for error in result['errors']:
                f.write(f"  - {error}\n")
    
    print(f"\n详细报告已保存: {report_path}")
    print("="*70)

if __name__ == '__main__':
    main()