#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量提取OCT图像中的日期和元数据信息
使用EasyOCR进行文字识别
"""

import os
import re
from pathlib import Path
from PIL import Image
import pandas as pd
from datetime import datetime
import numpy as np
import easyocr
from tqdm import tqdm

def extract_bottom_region(image_path, bottom_pixels=80):
    """
    提取图像底部区域（包含日期等元数据）
    """
    img = Image.open(image_path)
    width, height = img.size
    
    # 提取底部区域
    bottom_region = img.crop((0, height - bottom_pixels, width, height))
    return bottom_region

def parse_date_from_text(text):
    """
    从OCR识别的文字中提取日期
    支持多种日期格式
    """
    # 常见日期格式
    date_patterns = [
        r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})',  # 2024/1/15 或 2024-01-15
        r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})',  # 15/1/2024 或 01-15-2024
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                groups = match.groups()
                if len(groups[0]) == 4:  # YYYY/MM/DD
                    year, month, day = groups
                else:  # DD/MM/YYYY or MM/DD/YYYY
                    # 假设是 MM/DD/YYYY 格式（美式）
                    month, day, year = groups
                
                # 验证日期有效性
                date_obj = datetime(int(year), int(month), int(day))
                return date_obj.strftime('%Y-%m-%d')
            except ValueError:
                continue
    
    return None

def extract_eye_label(text):
    """
    从文字中提取眼别标识
    """
    text_upper = text.upper()
    
    if 'OS' in text_upper or 'O.S' in text_upper:
        return 'L'  # OS = Left eye
    elif 'OD' in text_upper or 'O.D' in text_upper:
        return 'R'  # OD = Right eye
    elif 'OU' in text_upper or 'O.U' in text_upper:
        return 'B'  # OU = Both eyes
    
    return None

def extract_quality_score(text):
    """
    从文字中提取图像质量评分
    """
    # 查找 Q: XX 或 Q:XX 格式
    match = re.search(r'Q:\s*(\d+)', text)
    if match:
        return int(match.group(1))
    return None

def process_single_image(image_path, reader):
    """
    处理单张图像，提取元数据
    """
    try:
        # 提取底部区域
        bottom_region = extract_bottom_region(image_path)
        
        # 转换为灰度以提高OCR准确率
        bottom_region_gray = bottom_region.convert('L')
        
        # 转换为numpy数组（EasyOCR要求）
        bottom_array = np.array(bottom_region_gray)
        
        # 使用EasyOCR识别文字
        # 注意：第一次运行会下载模型，需要一些时间
        result = reader.readtext(bottom_array, detail=0)
        
        # 合并所有识别的文字
        full_text = ' '.join(result)
        
        # 提取信息
        date_str = parse_date_from_text(full_text)
        eye_label = extract_eye_label(full_text)
        quality_score = extract_quality_score(full_text)
        
        return {
            'success': True,
            'date': date_str,
            'eye': eye_label,
            'quality': quality_score,
            'raw_text': full_text
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def batch_extract_metadata(dataset_path, output_csv):
    """
    批量提取数据集中所有OCT图像的元数据
    """
    print("="*70)
    print("批量提取OCT图像元数据")
    print("="*70)
    print()
    
    # 初始化EasyOCR（仅英文和数字，更快）
    print("初始化OCR引擎...")
    print("(第一次运行会下载模型文件，请稍候...)")
    reader = easyocr.Reader(['en'], gpu=False)
    print("✓ OCR引擎初始化完成\n")
    
    # 收集所有TIFF图像
    dataset_path = Path(dataset_path)
    diseases = ['葡萄膜炎', '正常', 'DR', 'AMD', 'CSC', 'RVO']
    
    all_images = []
    for disease in diseases:
        disease_path = dataset_path / disease
        if not disease_path.exists():
            continue
        
        for patient_folder in disease_path.iterdir():
            if not patient_folder.is_dir():
                continue
            
            oct_folder = patient_folder / 'OCT'
            if not oct_folder.exists():
                continue
            
            for img_file in oct_folder.glob("*.tif"):
                all_images.append({
                    'path': str(img_file),
                    'disease': disease,
                    'patient_folder': patient_folder.name,
                    'filename': img_file.name
                })
    
    print(f"找到 {len(all_images)} 张OCT图像\n")
    
    # 批量处理
    results = []
    for img_info in tqdm(all_images, desc="提取元数据"):
        metadata = process_single_image(img_info['path'], reader)
        
        result = {
            'image_path': img_info['path'],
            'disease': img_info['disease'],
            'patient_folder': img_info['patient_folder'],
            'filename': img_info['filename'],
            'extracted_date': metadata.get('date'),
            'extracted_eye': metadata.get('eye'),
            'quality_score': metadata.get('quality'),
            'ocr_text': metadata.get('raw_text', ''),
            'success': metadata.get('success', False),
            'error': metadata.get('error', '')
        }
        results.append(result)
    
    # 保存结果
    df = pd.DataFrame(results)
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    
    # 统计报告
    print("\n" + "="*70)
    print("提取结果统计")
    print("="*70)
    
    success_count = df['success'].sum()
    total_count = len(df)
    
    print(f"总图像数: {total_count}")
    print(f"成功提取: {success_count} ({success_count/total_count*100:.1f}%)")
    print(f"提取失败: {total_count - success_count}")
    print()
    
    # 日期提取统计
    date_count = df['extracted_date'].notna().sum()
    print(f"成功提取日期: {date_count} ({date_count/total_count*100:.1f}%)")
    
    # 眼别提取统计
    eye_count = df['extracted_eye'].notna().sum()
    print(f"成功提取眼别: {eye_count} ({eye_count/total_count*100:.1f}%)")
    
    # 质量评分提取统计
    quality_count = df['quality_score'].notna().sum()
    print(f"成功提取质量评分: {quality_count} ({quality_count/total_count*100:.1f}%)")
    
    print()
    print(f"结果已保存到: {output_csv}")
    print("="*70)
    
    return df

def main():
    """
    主函数
    """
    dataset_path = "/data2/xuhanyang/dataset/沈俊慧_Excel重组数据集_v2"
    output_csv = "/data2/xuhanyang/dataset/oct_metadata_extracted.csv"
    
    print("\n注意:")
    print("  • 第一次运行会下载EasyOCR模型（约100MB）")
    print("  • 处理1849张图像预计需要30-60分钟")
    print("  • 可以随时中断(Ctrl+C)，已处理的结果会保存")
    print()
    
    input("按Enter键开始处理...")
    
    try:
        df = batch_extract_metadata(dataset_path, output_csv)
        
        # 显示一些示例结果
        print("\n前10条结果示例:")
        print(df[['filename', 'extracted_date', 'extracted_eye', 'quality_score']].head(10))
        
    except KeyboardInterrupt:
        print("\n\n用户中断处理")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

