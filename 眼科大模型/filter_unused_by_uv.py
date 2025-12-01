#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
过滤未使用图片报告：移除在葡萄膜炎表中出现的患者
"""

import os
import pandas as pd
from pathlib import Path
from datetime import datetime
import re

def extract_patient_name_from_filename(filename):
    """
    从文件名中提取患者姓名
    例如: "周幼芳L_000.tif" -> "周幼芳"
    """
    # 移除路径和扩展名
    name = Path(filename).stem
    
    # 移除左右眼标识和序号
    # 匹配模式：姓名 + (L|R) + _数字 或 姓名 + (L|R)
    name = re.sub(r'[LR]\d*_?\d*$', '', name)
    name = re.sub(r'[LR]$', '', name)
    name = re.sub(r'_\d+$', '', name)
    
    return name.strip()

def get_uvetis_patients(excel_paths):
    """
    从Excel文件中提取所有葡萄膜炎表中的患者姓名
    可以接受单个文件路径或文件路径列表
    """
    uvetis_patients = set()
    
    # 如果输入是字符串，转换为列表
    if isinstance(excel_paths, str):
        excel_paths = [excel_paths]
    
    for excel_path in excel_paths:
        try:
            xls = pd.ExcelFile(excel_path)
            print(f"  读取文件: {os.path.basename(excel_path)}")
            
            for sheet_name in xls.sheet_names:
                if '葡萄膜炎' in sheet_name:
                    print(f"    读取表: {sheet_name}")
                    try:
                        # 葡萄膜炎表没有表头，第一行就是数据
                        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
                        
                        count = 0
                        for idx, row in df.iterrows():
                            # 列3（索引3）是患者姓名
                            if len(row) > 3:
                                patient_name = row.iloc[3]
                                if pd.notna(patient_name) and patient_name:
                                    patient_name = str(patient_name).strip()
                                    if patient_name:
                                        uvetis_patients.add(patient_name)
                                        count += 1
                        print(f"      找到 {count} 个患者姓名")
                    except Exception as e:
                        print(f"      读取失败: {e}")
                        continue
        
        except Exception as e:
            print(f"  读取Excel文件失败 {excel_path}: {e}")
            continue
    
    return uvetis_patients

def parse_report_file(report_path):
    """
    解析报告文件，提取未使用图片列表
    返回: {
        'header': 报告头部信息,
        'section1': 第一部分内容,
        'section2': 第二部分内容,
        'section3': 第三部分内容,
        'unused_images': {
            'batch_name': [文件列表]
        },
        'stats': {
            'total_source_images': ...,
            'file_count': ...,
            'total_unused': ...
        }
    }
    """
    with open(report_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    result = {
        'header': [],
        'section1': [],
        'section2': [],
        'section3': [],
        'unused_images': {},
        'stats': {}
    }
    
    current_section = 'header'
    current_batch = None
    in_unused_section = False
    in_batch_list = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 检测各部分
        if '一、同一日期重复的患者' in line:
            current_section = 'section1'
            in_unused_section = False
        elif '二、跨批次找到图片的患者' in line:
            current_section = 'section2'
            in_unused_section = False
        elif '三、未找到图片的患者' in line:
            current_section = 'section3'
            in_unused_section = False
        elif '四、原始目录中未被使用的图片' in line:
            in_unused_section = True
            in_batch_list = False
        elif in_unused_section:
            # 提取统计信息
            if '原始图片总数:' in line:
                match = re.search(r'原始图片总数:\s*(\d+)', line)
                if match:
                    result['stats']['total_source_images'] = int(match.group(1))
            elif '已使用图片:' in line:
                match = re.search(r'已使用图片:\s*(\d+)', line)
                if match:
                    result['stats']['file_count'] = int(match.group(1))
            elif '未使用图片:' in line:
                match = re.search(r'未使用图片:\s*(\d+)', line)
                if match:
                    result['stats']['total_unused'] = int(match.group(1))
            elif '按批次统计:' in line:
                in_batch_list = True
            elif in_batch_list:
                # 检测批次名称
                batch_match = re.match(r'^(\d+-\d+-\d+)\s*\((\d+)个文件\):', line.strip())
                if batch_match:
                    current_batch = batch_match.group(1)
                    result['unused_images'][current_batch] = []
                # 检测文件列表项
                elif current_batch and re.match(r'^\s*\d+\.\s+(.+)$', line.strip()):
                    file_match = re.match(r'^\s*\d+\.\s+(.+)$', line.strip())
                    if file_match:
                        filename = file_match.group(1).strip()
                        result['unused_images'][current_batch].append(filename)
        
        # 保存各部分内容
        if current_section == 'header':
            result['header'].append(line)
        elif current_section == 'section1':
            result['section1'].append(line)
        elif current_section == 'section2':
            result['section2'].append(line)
        elif current_section == 'section3':
            result['section3'].append(line)
        
        i += 1
    
    return result

def filter_unused_images(unused_images, uvetis_patients):
    """
    过滤未使用图片列表，移除在葡萄膜炎表中出现的患者
    返回: (过滤后的列表, 被移除的文件列表)
    """
    filtered = {}
    removed = {}
    
    for batch_name, files in unused_images.items():
        filtered[batch_name] = []
        removed[batch_name] = []
        
        for filename in files:
            patient_name = extract_patient_name_from_filename(filename)
            
            # 检查是否在葡萄膜炎患者列表中
            if patient_name in uvetis_patients:
                removed[batch_name].append(filename)
            else:
                filtered[batch_name].append(filename)
    
    return filtered, removed

def generate_filtered_report(original_report, filtered_images, removed_images, uvetis_patients, output_path):
    """
    生成过滤后的报告
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        # 写入新的报告头部
        f.write("="*70 + "\n")
        f.write("数据集重组特殊情况详细报告（已过滤葡萄膜炎患者）\n")
        f.write("="*70 + "\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Excel文件: 归总_有欧堡图像_修正版.xlsx\n")
        f.write("="*70 + "\n")
        
        f.write("\n【重要说明】\n")
        f.write("  • 本报告已从\"未使用图片\"列表中移除在葡萄膜炎表中出现的患者\n")
        f.write("  • 同一患者在不同日期就诊视为不同病例（正常情况，不去重）\n")
        f.write("  • 只有同一患者在同一日期重复出现才被视为数据重复（已去重）\n")
        f.write("  • 患者文件夹命名格式：患者姓名_日期（YYYYMMDD）\n")
        f.write("  • 如果没有日期信息，使用：患者姓名_批次号\n")
        
        # 读取原始报告文件，提取前三个部分
        original_report_path = "/data2/xuhanyang/dataset/沈俊慧_Excel重组数据集_v3/特殊情况报告_20251123_024221.txt"
        with open(original_report_path, 'r', encoding='utf-8') as orig_f:
            lines = orig_f.readlines()
        
        # 找到第四部分的开始位置
        fourth_section_start = None
        for i, line in enumerate(lines):
            if '四、原始目录中未被使用的图片' in line and '已过滤' not in line:
                fourth_section_start = i
                break
        
        # 写入原始报告的前三个部分
        if fourth_section_start:
            for line in lines[:fourth_section_start]:
                f.write(line)
        
        # 写入第四部分（过滤后的未使用图片）
        f.write("\n" + "="*70 + "\n")
        f.write("四、原始目录中未被使用的图片（已过滤葡萄膜炎患者）\n")
        f.write("="*70 + "\n")
        
        total_filtered = sum(len(v) for v in filtered_images.values())
        total_removed = sum(len(v) for v in removed_images.values())
        
        f.write(f"\n总计: {total_filtered}个图片文件未被使用（已移除{total_removed}个葡萄膜炎患者的图片）\n")
        f.write("说明: 这些图片存在于原始目录中，但未被Excel记录，因此未被纳入重组数据集\n")
        f.write("      已从列表中移除在葡萄膜炎表中出现的患者图片\n")
        f.write("可能原因:\n")
        f.write("  1. 患者未在Excel中登记\n")
        f.write("  2. 图片文件命名不规范，无法匹配患者姓名\n")
        f.write("  3. 非目标疾病的图片\n")
        f.write("  4. 测试或临时文件\n\n")
        
        if 'total_source_images' in original_report['stats']:
            f.write(f"原始图片总数: {original_report['stats']['total_source_images']}\n")
        if 'file_count' in original_report['stats']:
            f.write(f"已使用图片: {original_report['stats']['file_count']}\n")
        f.write(f"未使用图片（过滤后）: {total_filtered}\n")
        f.write(f"已移除（葡萄膜炎患者）: {total_removed}\n")
        if 'total_source_images' in original_report['stats'] and 'file_count' in original_report['stats']:
            total = original_report['stats']['total_source_images']
            used = original_report['stats']['file_count']
            f.write(f"使用率: {used}/{total} = {used/total*100:.1f}%\n\n")
        
        f.write("按批次统计:\n")
        for batch_name in sorted(filtered_images.keys()):
            images = filtered_images[batch_name]
            if images:
                f.write(f"\n{batch_name} ({len(images)}个文件):\n")
                for i, img in enumerate(images, 1):
                    f.write(f"  {i}. {img}\n")
        
        # 添加被移除的文件信息
        if removed_images and any(removed_images.values()):
            f.write("\n" + "="*70 + "\n")
            f.write("已移除的图片（葡萄膜炎患者）\n")
            f.write("="*70 + "\n")
            f.write(f"\n总计: {total_removed}个文件\n")
            f.write("说明: 这些图片对应的患者在葡萄膜炎表中出现，已从未使用列表中移除\n\n")
            f.write("按批次统计:\n")
            for batch_name in sorted(removed_images.keys()):
                images = removed_images[batch_name]
                if images:
                    f.write(f"\n{batch_name} ({len(images)}个文件):\n")
                    for i, img in enumerate(images, 1):
                        f.write(f"  {i}. {img}\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("报告结束\n")
        f.write("="*70 + "\n")

def main():
    # 使用包含完整数据的Excel文件
    excel_paths = [
        "/data2/xuhanyang/dataset/沈俊慧/归总_修正.xlsx",
        "/data2/xuhanyang/dataset/沈俊慧/归总_有欧堡图像_修正版.xlsx"
    ]
    report_path = "/data2/xuhanyang/dataset/沈俊慧_Excel重组数据集_v3/特殊情况报告_20251123_024221.txt"
    output_dir = "/data2/xuhanyang/dataset/沈俊慧_Excel重组数据集_v3"
    
    print("="*70)
    print("过滤未使用图片报告（移除葡萄膜炎患者）")
    print("="*70)
    
    # 1. 提取葡萄膜炎患者列表
    print("\n1. 从Excel文件中提取葡萄膜炎患者...")
    uvetis_patients = get_uvetis_patients(excel_paths)
    print(f"\n   总计找到 {len(uvetis_patients)} 个唯一葡萄膜炎患者")
    
    # 2. 解析报告文件
    print("\n2. 解析报告文件...")
    original_report = parse_report_file(report_path)
    print(f"   找到 {len(original_report['unused_images'])} 个批次的未使用图片")
    
    # 3. 过滤未使用图片
    print("\n3. 过滤未使用图片列表...")
    filtered_images, removed_images = filter_unused_images(
        original_report['unused_images'], 
        uvetis_patients
    )
    
    total_filtered = sum(len(v) for v in filtered_images.values())
    total_removed = sum(len(v) for v in removed_images.values())
    print(f"   过滤前: {sum(len(v) for v in original_report['unused_images'].values())} 个文件")
    print(f"   过滤后: {total_filtered} 个文件")
    print(f"   已移除: {total_removed} 个文件")
    
    # 4. 生成新报告
    print("\n4. 生成过滤后的报告...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"特殊情况报告_过滤葡萄膜炎_{timestamp}.txt"
    
    generate_filtered_report(
        original_report,
        filtered_images,
        removed_images,
        uvetis_patients,
        output_path
    )
    
    print(f"\n✅ 过滤后的报告已保存到: {output_path}")
    print("="*70)

if __name__ == "__main__":
    main()

