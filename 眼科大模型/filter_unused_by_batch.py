#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
过滤未使用图片报告：根据批次前缀匹配Excel sheet，移除在对应sheet中出现的患者
例如：10-1-1 对应 Excel 中的 10.1（正常10.1 或 葡萄膜炎10.1）
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
          "正常/王幼玲L_000.tif" -> "王幼玲"
          "正常/翁小琴R正常_000.tif" -> "翁小琴"
    """
    # 移除路径和扩展名
    name = Path(filename).stem
    
    # 移除子目录前缀（如"正常/"、"CSC/"等）
    if '/' in name:
        name = name.split('/')[-1]
    
    # 移除"正常"、"异常"等后缀（在L/R之前或之后）
    name = re.sub(r'正常', '', name)
    name = re.sub(r'异常', '', name)
    
    # 移除左右眼标识和序号
    # 匹配模式：姓名 + (L|R) + _数字 或 姓名 + (L|R)
    name = re.sub(r'[LR]\d*_?\d*$', '', name)
    name = re.sub(r'[LR]$', '', name)
    name = re.sub(r'_\d+$', '', name)
    
    return name.strip()

def batch_to_sheet_prefix(batch_name):
    """
    将批次名转换为Excel sheet前缀
    例如: "10-1-1" -> "10.1"
          "10-2-1" -> "10.2"
          "10-7-1" -> "10.7"
    """
    # 提取前两部分，如 "10-1-1" -> "10.1"
    parts = batch_name.split('-')
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return None

def get_patients_from_sheet(excel_path, sheet_name):
    """
    从Excel sheet中提取患者姓名
    返回: set of patient names
    """
    patients = set()
    
    try:
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        
        # 根据sheet类型确定患者姓名所在的列
        # 正常10.7: 第2列（索引1）
        # 葡萄膜炎10.1/10.2/10.3/10.5: 第4列（索引3）
        # 其他类型可能需要调整
        
        if '正常' in sheet_name:
            # 正常表：患者姓名在第2列（索引1）
            col_idx = 1
        elif '葡萄膜炎' in sheet_name:
            # 葡萄膜炎表：患者姓名在第4列（索引3）
            col_idx = 3
        else:
            # 其他类型（DR、RVO、AMD、CSC等）：尝试第2列
            col_idx = 1
        
        for idx, row in df.iterrows():
            if len(row) > col_idx:
                patient_name = row.iloc[col_idx]
                if pd.notna(patient_name) and patient_name:
                    patient_name = str(patient_name).strip()
                    if patient_name:
                        patients.add(patient_name)
    
    except Exception as e:
        print(f"      读取sheet {sheet_name} 失败: {e}")
    
    return patients

def get_patients_by_batch(excel_path):
    """
    从Excel文件中按批次前缀组织患者列表
    返回: {
        '10.1': set of patient names (来自所有包含10.1的sheet),
        '10.2': set of patient names,
        ...
    }
    """
    batch_patients = {}
    
    try:
        xls = pd.ExcelFile(excel_path)
        print(f"  读取文件: {os.path.basename(excel_path)}")
        
        for sheet_name in xls.sheet_names:
            # 跳过空sheet
            if sheet_name == 'Sheet12' or not sheet_name:
                continue
            
            # 提取sheet中的批次前缀（如 "正常10.7" -> "10.7"）
            # 匹配模式：任意字符 + 数字.数字
            match = re.search(r'(\d+\.\d+)', sheet_name)
            if match:
                batch_prefix = match.group(1)
                
                if batch_prefix not in batch_patients:
                    batch_patients[batch_prefix] = set()
                
                print(f"    读取表: {sheet_name} (批次: {batch_prefix})")
                patients = get_patients_from_sheet(excel_path, sheet_name)
                batch_patients[batch_prefix].update(patients)
                print(f"      找到 {len(patients)} 个患者姓名")
    
    except Exception as e:
        print(f"  读取Excel文件失败: {e}")
    
    return batch_patients

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

def filter_unused_images(unused_images, batch_patients):
    """
    根据批次前缀匹配Excel sheet，过滤未使用图片列表
    返回: (过滤后的列表, 被移除的文件列表)
    """
    filtered = {}
    removed = {}
    
    for batch_name, files in unused_images.items():
        filtered[batch_name] = []
        removed[batch_name] = []
        
        # 获取批次对应的sheet前缀
        sheet_prefix = batch_to_sheet_prefix(batch_name)
        
        if not sheet_prefix:
            print(f"    警告: 无法解析批次名 {batch_name}，跳过")
            filtered[batch_name] = files  # 保留所有文件
            continue
        
        # 获取该批次前缀对应的所有患者
        patients_in_sheet = batch_patients.get(sheet_prefix, set())
        
        if not patients_in_sheet:
            print(f"    批次 {batch_name} (对应 {sheet_prefix}): 未找到对应的Excel sheet，保留所有文件")
            filtered[batch_name] = files
            continue
        
        print(f"    批次 {batch_name} (对应 {sheet_prefix}): 找到 {len(patients_in_sheet)} 个患者")
        
        for filename in files:
            patient_name = extract_patient_name_from_filename(filename)
            
            # 检查是否在对应sheet的患者列表中
            if patient_name in patients_in_sheet:
                removed[batch_name].append(filename)
            else:
                filtered[batch_name].append(filename)
    
    return filtered, removed

def generate_filtered_report(original_report, filtered_images, removed_images, batch_patients, output_path):
    """
    生成过滤后的报告
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        # 写入新的报告头部
        f.write("="*70 + "\n")
        f.write("数据集重组特殊情况详细报告（已按批次过滤）\n")
        f.write("="*70 + "\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Excel文件: 归总_修正.xlsx\n")
        f.write("="*70 + "\n")
        
        f.write("\n【重要说明】\n")
        f.write("  • 本报告已从\"未使用图片\"列表中移除在对应批次Excel sheet中出现的患者\n")
        f.write("  • 批次前缀对应关系：10-1-1 对应 Excel 中的 10.1（正常10.1 或 葡萄膜炎10.1）\n")
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
        f.write("四、原始目录中未被使用的图片（已按批次过滤）\n")
        f.write("="*70 + "\n")
        
        total_filtered = sum(len(v) for v in filtered_images.values())
        total_removed = sum(len(v) for v in removed_images.values())
        
        f.write(f"\n总计: {total_filtered}个图片文件未被使用（已移除{total_removed}个在对应Excel sheet中出现的患者图片）\n")
        f.write("说明: 这些图片存在于原始目录中，但未被Excel记录，因此未被纳入重组数据集\n")
        f.write("      已从列表中移除在对应批次Excel sheet中出现的患者图片\n")
        f.write("      批次前缀对应关系：10-1-1 对应 Excel 中的 10.1\n")
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
        f.write(f"已移除（在对应Excel sheet中出现）: {total_removed}\n")
        if 'total_source_images' in original_report['stats'] and 'file_count' in original_report['stats']:
            total = original_report['stats']['total_source_images']
            used = original_report['stats']['file_count']
            f.write(f"使用率: {used}/{total} = {used/total*100:.1f}%\n\n")
        
        f.write("按批次统计:\n")
        for batch_name in sorted(filtered_images.keys()):
            images = filtered_images[batch_name]
            if images:
                sheet_prefix = batch_to_sheet_prefix(batch_name)
                f.write(f"\n{batch_name} (对应 {sheet_prefix}, {len(images)}个文件):\n")
                for i, img in enumerate(images, 1):
                    f.write(f"  {i}. {img}\n")
        
        # 添加被移除的文件信息
        if removed_images and any(removed_images.values()):
            f.write("\n" + "="*70 + "\n")
            f.write("已移除的图片（在对应Excel sheet中出现）\n")
            f.write("="*70 + "\n")
            f.write(f"\n总计: {total_removed}个文件\n")
            f.write("说明: 这些图片对应的患者在对应批次的Excel sheet中出现，已从未使用列表中移除\n\n")
            f.write("按批次统计:\n")
            for batch_name in sorted(removed_images.keys()):
                images = removed_images[batch_name]
                if images:
                    sheet_prefix = batch_to_sheet_prefix(batch_name)
                    f.write(f"\n{batch_name} (对应 {sheet_prefix}, {len(images)}个文件):\n")
                    for i, img in enumerate(images, 1):
                        f.write(f"  {i}. {img}\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("报告结束\n")
        f.write("="*70 + "\n")

def main():
    excel_path = "/data2/xuhanyang/dataset/沈俊慧/归总_修正.xlsx"
    report_path = "/data2/xuhanyang/dataset/沈俊慧_Excel重组数据集_v3/特殊情况报告_20251123_024221.txt"
    output_dir = "/data2/xuhanyang/dataset/沈俊慧_Excel重组数据集_v3"
    
    print("="*70)
    print("过滤未使用图片报告（按批次匹配Excel sheet）")
    print("="*70)
    
    # 1. 从Excel文件中按批次前缀组织患者列表
    print("\n1. 从Excel文件中提取患者（按批次前缀组织）...")
    batch_patients = get_patients_by_batch(excel_path)
    print(f"\n   找到 {len(batch_patients)} 个批次前缀:")
    for prefix, patients in sorted(batch_patients.items()):
        print(f"     {prefix}: {len(patients)} 个患者")
    
    # 2. 解析报告文件
    print("\n2. 解析报告文件...")
    original_report = parse_report_file(report_path)
    print(f"   找到 {len(original_report['unused_images'])} 个批次的未使用图片")
    
    # 3. 过滤未使用图片
    print("\n3. 过滤未使用图片列表（按批次匹配）...")
    filtered_images, removed_images = filter_unused_images(
        original_report['unused_images'], 
        batch_patients
    )
    
    total_filtered = sum(len(v) for v in filtered_images.values())
    total_removed = sum(len(v) for v in removed_images.values())
    print(f"\n   过滤前: {sum(len(v) for v in original_report['unused_images'].values())} 个文件")
    print(f"   过滤后: {total_filtered} 个文件")
    print(f"   已移除: {total_removed} 个文件")
    
    # 4. 生成新报告
    print("\n4. 生成过滤后的报告...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(output_dir) / f"特殊情况报告_按批次过滤_{timestamp}.txt"
    
    generate_filtered_report(
        original_report,
        filtered_images,
        removed_images,
        batch_patients,
        output_path
    )
    
    print(f"\n✅ 过滤后的报告已保存到: {output_path}")
    print("="*70)

if __name__ == "__main__":
    main()

