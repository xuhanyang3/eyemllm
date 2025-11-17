#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查葡萄膜炎患者是否有欧堡图像
如果没有，则从数据集中删除该患者
"""
import os
import shutil
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta
import re

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

def check_uveitis_patients(excel_path, dataset_dir):
    """
    检查葡萄膜炎患者是否有欧堡图像，并删除没有的患者
    
    Args:
        excel_path: Excel文件路径
        dataset_dir: 数据集目录
    """
    xls = pd.ExcelFile(excel_path)
    
    # 葡萄膜炎相关的sheet
    uveitis_sheets = ['葡萄膜炎10.1', '葡萄膜炎10.2', '葡萄膜炎10.3', '葡萄膜炎10.5']
    
    print("="*70)
    print("检查葡萄膜炎患者的欧堡图像")
    print("="*70)
    
    total_patients = 0
    patients_with_optos = 0
    patients_without_optos = 0
    deleted_folders = []
    
    for sheet_name in uveitis_sheets:
        if sheet_name not in xls.sheet_names:
            continue
        
        print(f"\n处理 {sheet_name}...")
        
        df = pd.read_excel(excel_path, sheet_name=sheet_name)
        
        # 第一列是路径
        if len(df.columns) < 4:
            print(f"  警告: {sheet_name} 列数不足，跳过")
            continue
        
        path_col = df.columns[0]
        name_col = df.columns[3]  # 患者姓名在第4列
        
        batch = sheet_name.replace('葡萄膜炎', '')
        
        for idx, row in df.iterrows():
            path_str = str(row[path_col])
            patient_name = str(row[name_col])
            
            if pd.isna(path_str) or pd.isna(patient_name) or path_str == 'nan':
                continue
            
            total_patients += 1
            patient_name = patient_name.strip()
            
            # 解析路径
            patient_folder, exam_date = parse_path_info(path_str)
            
            if not patient_folder or not exam_date:
                print(f"  无法解析路径: {path_str[:80]}...")
                continue
            
            # 查找欧堡图像
            optos_folder = find_optos_folder(patient_folder, exam_date)
            
            if optos_folder:
                patients_with_optos += 1
                if total_patients % 50 == 0:
                    print(f"  已检查 {total_patients} 位患者...")
            else:
                patients_without_optos += 1
                print(f"  未找到欧堡: {patient_name} (日期: {exam_date.strftime('%Y-%m-%d')})")
                
                # 删除数据集中的患者文件夹
                patient_folder_name = f"{patient_name}_{batch}"
                patient_dataset_folder = Path(dataset_dir) / "葡萄膜炎" / patient_folder_name
                
                if patient_dataset_folder.exists():
                    try:
                        shutil.rmtree(patient_dataset_folder)
                        deleted_folders.append(patient_folder_name)
                        print(f"    已删除: {patient_dataset_folder}")
                    except Exception as e:
                        print(f"    删除失败: {e}")
    
    # 打印统计结果
    print("\n" + "="*70)
    print("检查完成！统计结果:")
    print("="*70)
    print(f"总计检查患者数: {total_patients}")
    print(f"有欧堡图像: {patients_with_optos} 人")
    print(f"无欧堡图像: {patients_without_optos} 人")
    print(f"已删除文件夹数: {len(deleted_folders)} 个")
    
    if deleted_folders:
        print("\n删除的患者文件夹:")
        for i, folder in enumerate(deleted_folders, 1):
            print(f"  {i}. {folder}")
    
    print("="*70)
    
    return {
        'total': total_patients,
        'with_optos': patients_with_optos,
        'without_optos': patients_without_optos,
        'deleted': len(deleted_folders),
        'deleted_list': deleted_folders
    }

def main():
    excel_path = "/data2/xuhanyang/dataset/沈俊慧/归总.xlsx"
    dataset_dir = "/data2/xuhanyang/dataset/沈俊慧_Excel重组数据集_v3"
    
    print("="*70)
    print("葡萄膜炎患者欧堡图像检查工具")
    print("="*70)
    print(f"Excel文件: {excel_path}")
    print(f"数据集目录: {dataset_dir}")
    print("="*70)
    
    if not os.path.exists(excel_path):
        print(f"错误: Excel文件不存在: {excel_path}")
        return
    
    if not os.path.exists(dataset_dir):
        print(f"错误: 数据集目录不存在: {dataset_dir}")
        return
    
    result = check_uveitis_patients(excel_path, dataset_dir)
    
    # 保存结果报告
    report_path = Path(dataset_dir) / "欧堡图像检查报告.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("葡萄膜炎患者欧堡图像检查报告\n")
        f.write("="*70 + "\n\n")
        f.write(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"总计检查患者数: {result['total']}\n")
        f.write(f"有欧堡图像: {result['with_optos']} 人\n")
        f.write(f"无欧堡图像: {result['without_optos']} 人\n")
        f.write(f"已删除数据: {result['deleted']} 条\n\n")
        
        if result['deleted_list']:
            f.write("删除的患者列表:\n")
            for i, folder in enumerate(result['deleted_list'], 1):
                f.write(f"  {i}. {folder}\n")
        
        f.write("\n" + "="*70 + "\n")
    
    print(f"\n报告已保存到: {report_path}")

if __name__ == "__main__":
    main()

