#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查葡萄膜炎患者是否有欧堡图像
删除Excel中没有欧堡图像的患者记录，生成新的Excel文件
修复版本：正确处理没有标题行的sheet
"""

import os
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta
import re
from openpyxl import load_workbook

def parse_path_info(path_str):
    """
    解析路径字符串，提取患者ID、姓名和日期
    例如: /data4/zhouhaoze/2024/789/13227234 刘富娣 女 1964-12-22/2024-07-09/眼底荧光造影（FFA）(双眼)
    返回: (患者文件夹, 日期)
    """
    # 替换路径前缀
    path_str = path_str.replace('/data4/zhouhaoze', '/data4/kongzitai/ophthalmology/E:')
    
    # 提取日期部分 (格式: YYYY-MM-DD)
    date_match = re.search(r'/(\d{4}-\d{2}-\d{2})/', path_str)
    if not date_match:
        return None, None
    
    exam_date_str = date_match.group(1)
    exam_date = datetime.strptime(exam_date_str, '%Y-%m-%d')
    
    # 获取日期前的部分（患者文件夹）
    patient_folder = path_str.split(f'/{exam_date_str}/')[0]
    
    return patient_folder, exam_date

def find_optos_folder(patient_folder, exam_date, search_weeks=1):
    """
    在患者文件夹下查找欧堡图像文件夹
    
    Args:
        patient_folder: 患者文件夹路径
        exam_date: 检查日期
        search_weeks: 前后搜索的周数
    
    Returns:
        找到的欧堡文件夹路径，如果未找到返回None
    """
    patient_path = Path(patient_folder)
    
    if not patient_path.exists():
        return None
    
    # 生成需要搜索的日期范围
    dates_to_search = []
    
    # 检查原日期
    dates_to_search.append(exam_date)
    
    # 添加前后两周的日期
    for days in range(1, search_weeks * 7 + 1):
        dates_to_search.append(exam_date + timedelta(days=days))
        dates_to_search.append(exam_date - timedelta(days=days))
    
    # 搜索每个日期
    for date in dates_to_search:
        date_str = date.strftime('%Y-%m-%d')
        date_folder = patient_path / date_str
        
        if not date_folder.exists():
            continue
        
        # 在日期文件夹下查找包含"欧堡"的文件夹
        try:
            for item in date_folder.iterdir():
                if item.is_dir() and '欧堡' in item.name:
                    return str(item)
        except Exception as e:
            continue
    
    return None

def filter_uveitis_patients(excel_path, output_path):
    """
    检查葡萄膜炎患者是否有欧堡图像，删除没有的患者记录
    
    Args:
        excel_path: 原始Excel文件路径
        output_path: 输出Excel文件路径
    """
    # 葡萄膜炎相关的sheet
    uveitis_sheets = ['葡萄膜炎10.1', '葡萄膜炎10.2', '葡萄膜炎10.3', '葡萄膜炎10.5']
    
    print("="*70)
    print("开始处理Excel文件，删除没有欧堡图像的葡萄膜炎患者记录")
    print("="*70)
    
    # 读取原始Excel文件
    xls = pd.ExcelFile(excel_path)
    
    # 创建一个字典来存储所有sheet的数据
    sheets_data = {}
    
    # 统计信息
    total_stats = {
        'total_patients': 0,
        'patients_with_optos': 0,
        'patients_without_optos': 0,
        'deleted_patients': []
    }
    
    # 处理每个sheet
    for sheet_name in xls.sheet_names:
        print(f"\n处理 sheet: {sheet_name}")
        
        # 如果不是葡萄膜炎相关的sheet，使用默认方式读取
        if sheet_name not in uveitis_sheets:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            sheets_data[sheet_name] = df
            print(f"  非葡萄膜炎sheet，保留所有数据 (共 {len(df)} 行)")
            continue
        
        # 葡萄膜炎sheet没有标题行，使用header=None读取
        df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        
        # 处理葡萄膜炎sheet
        if len(df.columns) < 4:
            print(f"  警告: {sheet_name} 列数不足，保留原数据")
            sheets_data[sheet_name] = df
            continue
        
        # 第1列是路径，第4列是姓名（索引从0开始，所以是0和3）
        path_col_idx = 0
        name_col_idx = 3
        
        batch = sheet_name.replace('葡萄膜炎', '')
        
        # 创建一个列表来存储要保留的行索引
        rows_to_keep = []
        
        for idx, row in df.iterrows():
            path_str = str(row[path_col_idx])
            patient_name = str(row[name_col_idx])
            
            # 检查是否为空（包括空格、NaN等）
            is_path_empty = pd.isna(row[path_col_idx]) or path_str == 'nan' or path_str.strip() == ''
            is_name_empty = pd.isna(row[name_col_idx]) or patient_name == 'nan' or patient_name.strip() == ''
            
            if is_path_empty or is_name_empty:
                # 路径或姓名为空，跳过该行（不保留）
                print(f"  跳过空数据: 行{idx}, 路径=\"{path_str[:30]}...\", 姓名=\"{patient_name}\"")
                continue
            
            total_stats['total_patients'] += 1
            patient_name = patient_name.strip()
            
            # 解析路径
            patient_folder, exam_date = parse_path_info(path_str)
            
            if not patient_folder or not exam_date:
                # 无法解析路径，保留该行
                rows_to_keep.append(idx)
                print(f"  无法解析路径，保留: {patient_name}")
                continue
            
            # 查找欧堡图像
            optos_folder = find_optos_folder(patient_folder, exam_date)
            
            if optos_folder:
                total_stats['patients_with_optos'] += 1
                rows_to_keep.append(idx)
            else:
                total_stats['patients_without_optos'] += 1
                total_stats['deleted_patients'].append(f"{patient_name}_{batch}")
                print(f"  删除（无欧堡）: {patient_name} (日期: {exam_date.strftime('%Y-%m-%d')})")
        
        # 保留有欧堡图像的行
        filtered_df = df.loc[rows_to_keep].reset_index(drop=True)
        sheets_data[sheet_name] = filtered_df
        
        print(f"  {sheet_name}: 原有 {len(df)} 行，保留 {len(filtered_df)} 行，删除 {len(df) - len(filtered_df)} 行")
    
    # 将所有sheet写入新的Excel文件
    print(f"\n正在保存到新文件: {output_path}")
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for sheet_name, df in sheets_data.items():
            # 葡萄膜炎sheet写入时不要列名
            if sheet_name in uveitis_sheets:
                df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)
            else:
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    # 打印统计结果
    print("\n" + "="*70)
    print("处理完成！统计结果:")
    print("="*70)
    print(f"总计检查患者数: {total_stats['total_patients']}")
    print(f"有欧堡图像: {total_stats['patients_with_optos']} 人")
    print(f"无欧堡图像: {total_stats['patients_without_optos']} 人")
    print(f"已从Excel删除: {total_stats['patients_without_optos']} 条记录")
    
    # 保存详细报告
    report_path = Path(output_path).parent / f"{Path(output_path).stem}_删除记录报告.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("Excel文件筛选报告 - 删除无欧堡图像的葡萄膜炎患者\n")
        f.write("="*70 + "\n\n")
        f.write(f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"原始文件: {excel_path}\n")
        f.write(f"新文件: {output_path}\n\n")
        f.write(f"总计检查患者数: {total_stats['total_patients']}\n")
        f.write(f"有欧堡图像: {total_stats['patients_with_optos']} 人\n")
        f.write(f"无欧堡图像: {total_stats['patients_without_optos']} 人\n")
        f.write(f"已从Excel删除: {total_stats['patients_without_optos']} 条记录\n\n")
        
        if total_stats['deleted_patients']:
            f.write("删除的患者列表:\n")
            for i, patient in enumerate(total_stats['deleted_patients'], 1):
                f.write(f"  {i}. {patient}\n")
        
        f.write("\n" + "="*70 + "\n")
    
    print(f"\n详细报告已保存到: {report_path}")
    print("="*70)
    
    return total_stats

def main():
    excel_path = "/data2/xuhanyang/dataset/沈俊慧/归总_修正.xlsx"
    output_path = "/data2/xuhanyang/dataset/沈俊慧/归总_有欧堡图像_修正版.xlsx"
    
    print("="*70)
    print("Excel文件筛选工具 - 删除无欧堡图像的葡萄膜炎患者（修正版）")
    print("="*70)
    print(f"原始文件: {excel_path}")
    print(f"输出文件: {output_path}")
    print("="*70)
    
    if not os.path.exists(excel_path):
        print(f"错误: Excel文件不存在: {excel_path}")
        return
    
    result = filter_uveitis_patients(excel_path, output_path)
    
    print(f"\n✓ 完成！新的Excel文件已保存到: {output_path}")
    print(f"✓ 原始文件保留在: {excel_path}")

if __name__ == "__main__":
    main()

