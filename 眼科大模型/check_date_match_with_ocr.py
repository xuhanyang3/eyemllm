#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查重组数据集中文件夹日期和图片OCR识别日期的匹配情况
基于extract_oct_dates.py的OCR识别功能
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
from collections import defaultdict

# 数据集根目录
DATASET_ROOT = "/data2/xuhanyang/dataset/沈俊慧_Excel重组数据集_v3"
DISEASES = ["葡萄膜炎", "正常", "CSC", "AMD", "RVO", "DR"]


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
        r'(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})',  # 2024/1/15 或 2024-01-15 或 2024.1.15
        r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})',  # 15/1/2024 或 01-15-2024
    ]
    
    for pattern in date_patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            try:
                groups = match.groups()
                if len(groups[0]) == 4:  # YYYY/MM/DD
                    year, month, day = groups
                else:  # DD/MM/YYYY or MM/DD/YYYY
                    # 假设是 MM/DD/YYYY 格式（美式）
                    month, day, year = groups
                
                # 验证日期有效性
                date_obj = datetime(int(year), int(month), int(day))
                return date_obj.strftime('%Y-%m-%d'), date_obj
            except ValueError:
                continue
    
    return None, None


def extract_folder_date(folder_name):
    """
    从文件夹名提取日期
    格式: 患者姓名_20231016 (YYYYMMDD)
    """
    parts = folder_name.split('_')
    if len(parts) < 2:
        return None, None
    
    date_str = parts[-1]
    
    # YYYYMMDD (8位数字)
    if re.match(r'^\d{8}$', date_str):
        try:
            date_obj = datetime.strptime(date_str, '%Y%m%d')
            return date_obj.strftime('%Y-%m-%d'), date_obj
        except:
            return None, None
    
    # 批次号如 10.7
    if re.match(r'^\d+\.\d+$', date_str):
        return date_str, 'batch'
    
    return None, None


def compare_dates(folder_date_obj, image_date_obj):
    """
    比较文件夹日期和图片日期
    返回: (状态, 描述, 天数差异)
    """
    if not folder_date_obj or not image_date_obj:
        return 'unknown', '无法比较', None
    
    if folder_date_obj == 'batch' or image_date_obj == 'batch':
        return 'batch', '批次号文件夹', None
    
    # 计算天数差异
    diff_days = abs((folder_date_obj - image_date_obj).days)
    
    if diff_days == 0:
        return 'match', '✓ 完全匹配', 0
    elif diff_days <= 7:
        return 'close', f'✓ 相近（{diff_days}天）', diff_days
    elif diff_days <= 30:
        return 'possible', f'△ 较近（{diff_days}天）', diff_days
    else:
        return 'mismatch', f'✗ 不匹配（{diff_days}天）', diff_days


def process_dataset():
    """
    处理整个数据集
    """
    print("="*80)
    print("检查文件夹日期与图片OCR日期的匹配情况")
    print("="*80)
    print()
    
    # 初始化EasyOCR
    print("初始化OCR引擎...")
    print("(第一次运行会下载模型文件，请稍候...)")
    reader = easyocr.Reader(['en'], gpu=True)
    print("✓ OCR引擎初始化完成\n")
    
    # 收集所有患者文件夹
    all_patients = []
    for disease in DISEASES:
        disease_path = Path(DATASET_ROOT) / disease
        if not disease_path.exists():
            continue
        
        for patient_folder in disease_path.iterdir():
            if not patient_folder.is_dir():
                continue
            
            oct_folder = patient_folder / 'OCT'
            if not oct_folder.exists():
                continue
            
            # 获取第一张TIF图片
            tif_files = list(oct_folder.glob("*.tif"))
            if not tif_files:
                continue
            
            all_patients.append({
                'disease': disease,
                'patient_folder': patient_folder.name,
                'first_image': str(tif_files[0]),
                'image_count': len(tif_files)
            })
    
    print(f"找到 {len(all_patients)} 个患者文件夹\n")
    print("开始处理...\n")
    
    # 处理每个患者
    results = []
    for patient_info in tqdm(all_patients, desc="检查日期匹配"):
        # 提取文件夹日期
        folder_date_str, folder_date_obj = extract_folder_date(patient_info['patient_folder'])
        
        # 提取图片日期
        try:
            bottom_region = extract_bottom_region(patient_info['first_image'])
            bottom_region_gray = bottom_region.convert('L')
            bottom_array = np.array(bottom_region_gray)
            
            # OCR识别
            ocr_result = reader.readtext(bottom_array, detail=0)
            full_text = ' '.join(ocr_result)
            
            # 解析日期
            image_date_str, image_date_obj = parse_date_from_text(full_text)
            
            # 比较日期
            status, status_desc, diff_days = compare_dates(folder_date_obj, image_date_obj)
            
            results.append({
                'disease': patient_info['disease'],
                'patient_folder': patient_info['patient_folder'],
                'folder_date': folder_date_str if folder_date_str else 'N/A',
                'image_date': image_date_str if image_date_str else 'N/A',
                'ocr_text': full_text[:100],  # 限制长度
                'status': status,
                'status_desc': status_desc,
                'diff_days': diff_days,
                'image_count': patient_info['image_count']
            })
            
        except Exception as e:
            results.append({
                'disease': patient_info['disease'],
                'patient_folder': patient_info['patient_folder'],
                'folder_date': folder_date_str if folder_date_str else 'N/A',
                'image_date': 'ERROR',
                'ocr_text': str(e),
                'status': 'error',
                'status_desc': f'处理错误: {str(e)[:50]}',
                'diff_days': None,
                'image_count': patient_info['image_count']
            })
    
    return results


def generate_report(results):
    """
    生成检查报告
    """
    df = pd.DataFrame(results)
    
    print("\n" + "="*80)
    print("检查结果统计")
    print("="*80)
    print()
    
    # 统计各状态数量
    status_counts = df['status'].value_counts()
    
    status_names = {
        'match': '✓ 完全匹配（同一天）',
        'close': '✓ 相近匹配（7天内）',
        'possible': '△ 可能匹配（8-30天）',
        'mismatch': '✗ 不匹配（超过30天）',
        'batch': '- 批次号文件夹',
        'unknown': '? 无法识别日期',
        'error': '✗ 处理错误'
    }
    
    print("【总体统计】")
    for status in ['match', 'close', 'possible', 'mismatch', 'batch', 'unknown', 'error']:
        count = status_counts.get(status, 0)
        if count > 0:
            percentage = count / len(df) * 100
            print(f"  {status_names.get(status, status)}: {count} 个 ({percentage:.1f}%)")
    
    print()
    print("="*80)
    print()
    
    # 按疾病类别统计
    print("【分类别统计】")
    for disease in DISEASES:
        disease_data = df[df['disease'] == disease]
        if len(disease_data) == 0:
            continue
        
        print(f"\n{disease}（共 {len(disease_data)} 个患者）:")
        for status in ['match', 'close', 'possible', 'mismatch']:
            count = (disease_data['status'] == status).sum()
            if count > 0:
                print(f"  {status_names[status]}: {count}")
    
    print()
    print("="*80)
    print()
    
    # 详细列表
    print("【详细检查结果】")
    print()
    
    for disease in DISEASES:
        disease_data = df[df['disease'] == disease]
        if len(disease_data) == 0:
            continue
        
        print(f"\n{'='*80}")
        print(f"{disease}（共 {len(disease_data)} 个患者）")
        print('='*80)
        
        for status in ['match', 'close', 'possible', 'mismatch', 'batch', 'unknown', 'error']:
            status_data = disease_data[disease_data['status'] == status]
            if len(status_data) == 0:
                continue
            
            print(f"\n  {status_names.get(status, status)}（{len(status_data)}个）:")
            
            for idx, row in status_data.iterrows():
                line = f"    • {row['patient_folder']}"
                line += f" | 文件夹: {row['folder_date']}"
                line += f" | 图片: {row['image_date']}"
                if row['diff_days'] is not None:
                    line += f" | 差异: {row['diff_days']}天"
                print(line)
                
                # 如果是错误或无法识别，显示OCR文本
                if status in ['error', 'unknown'] and row['ocr_text']:
                    print(f"       OCR文本: {row['ocr_text']}")
    
    print()
    print("="*80)
    
    # 保存结果
    output_txt = Path(DATASET_ROOT) / "日期匹配OCR检查报告.txt"
    output_csv = Path(DATASET_ROOT) / "日期匹配OCR检查详细数据.csv"
    
    # 保存文本报告
    with open(output_txt, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("文件夹日期与图片OCR日期匹配检查报告\n")
        f.write("="*80 + "\n")
        f.write(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"总患者数: {len(df)}\n")
        f.write("="*80 + "\n\n")
        
        f.write("【总体统计】\n")
        for status in ['match', 'close', 'possible', 'mismatch', 'batch', 'unknown', 'error']:
            count = status_counts.get(status, 0)
            if count > 0:
                percentage = count / len(df) * 100
                f.write(f"  {status_names.get(status, status)}: {count} 个 ({percentage:.1f}%)\n")
        
        f.write("\n" + "="*80 + "\n\n")
        
        # 详细结果
        for disease in DISEASES:
            disease_data = df[df['disease'] == disease]
            if len(disease_data) == 0:
                continue
            
            f.write(f"\n{'='*80}\n")
            f.write(f"{disease}（共 {len(disease_data)} 个患者）\n")
            f.write('='*80 + "\n")
            
            for status in ['match', 'close', 'possible', 'mismatch', 'batch', 'unknown', 'error']:
                status_data = disease_data[disease_data['status'] == status]
                if len(status_data) == 0:
                    continue
                
                f.write(f"\n  {status_names.get(status, status)}（{len(status_data)}个）:\n")
                
                for idx, row in status_data.iterrows():
                    line = f"    • {row['patient_folder']}"
                    line += f" | 文件夹: {row['folder_date']}"
                    line += f" | 图片: {row['image_date']}"
                    if row['diff_days'] is not None:
                        line += f" | 差异: {row['diff_days']}天"
                    f.write(line + "\n")
        
        f.write("\n" + "="*80 + "\n")
        f.write("报告结束\n")
        f.write("="*80 + "\n")
    
    # 保存CSV
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    
    print(f"\n✅ 报告已保存:")
    print(f"   文本报告: {output_txt}")
    print(f"   详细数据: {output_csv}")
    print()


def main():
    """
    主函数
    """
    print("\n注意:")
    print("  • 第一次运行会下载EasyOCR模型（约100MB）")
    print("  • 处理476个患者预计需要20-40分钟")
    print("  • 可以随时中断(Ctrl+C)，建议让它运行完成")
    print()
    
    input("按Enter键开始处理...")
    
    try:
        results = process_dataset()
        generate_report(results)
        
        print("\n✓ 处理完成！")
        
    except KeyboardInterrupt:
        print("\n\n⚠ 用户中断处理")
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

