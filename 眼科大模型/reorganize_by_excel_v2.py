#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据归总.xlsx文件重组数据集（改进版）
解决问题：
1. 正常10.7表格前21行和后面行的列结构不同
2. 只从对应疾病文件夹中查找图片
3. 其他疾病类别可以跨批次查找（但必须同类别）
4. 检测重复和未找到的情况
"""

import os
import shutil
from pathlib import Path
import pandas as pd
from collections import defaultdict
import re
from datetime import datetime

def find_patient_images_in_disease_folder(patient_name, search_dirs, disease_name):
    """
    在指定目录的特定疾病子文件夹中查找患者的所有图片
    
    Args:
        patient_name: 患者姓名
        search_dirs: 要搜索的目录列表
        disease_name: 疾病名称（如"正常"、"DR"等）
    
    Returns:
        list: 找到的图片文件路径列表
    """
    if isinstance(search_dirs, str):
        search_dirs = [search_dirs]
    
    images = []
    
    for search_dir in search_dirs:
        search_path = Path(search_dir)
        if not search_path.exists():
            continue
        
        # 检查是否有疾病子文件夹
        disease_folder = search_path / disease_name
        if disease_folder.exists() and disease_folder.is_dir():
            # 只在疾病文件夹中搜索
            for file in disease_folder.iterdir():
                if file.is_file() and file.suffix.lower() in ['.tif', '.tiff', '.jpg', '.jpeg', '.png']:
                    if patient_name in file.name:
                        images.append(file)
        else:
            # 如果没有疾病子文件夹，直接在根目录搜索（葡萄膜炎的情况）
            for file in search_path.iterdir():
                if file.is_file() and file.suffix.lower() in ['.tif', '.tiff', '.jpg', '.jpeg', '.png']:
                    if patient_name in file.name:
                        images.append(file)
    
    return images

def get_all_disease_folders(base_dir, disease_name):
    """
    获取某个疾病在所有批次中的文件夹路径
    
    Args:
        base_dir: 基础目录
        disease_name: 疾病名称
    
    Returns:
        list: 所有批次的文件夹路径
    """
    base_path = Path(base_dir) / "沈俊慧"
    all_dirs = []
    
    # 遍历所有沈俊慧10-X-Y文件夹
    for folder in sorted(base_path.glob("沈俊慧10-*")):
        if folder.is_dir():
            disease_folder = folder / disease_name
            if disease_folder.exists():
                all_dirs.append(str(folder))
    
    return all_dirs

def get_unique_filename(target_file):
    """
    如果文件已存在，返回一个带序号的唯一文件名
    """
    if not target_file.exists():
        return target_file
    
    base_name = target_file.stem
    extension = target_file.suffix
    parent = target_file.parent
    counter = 1
    
    while True:
        new_name = f"{base_name}_v{counter}{extension}"
        new_file = parent / new_name
        if not new_file.exists():
            return new_file
        counter += 1

def reorganize_by_excel(excel_path, source_base_dir, target_dir):
    """
    根据Excel文件重组数据集
    """
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)
    
    # Sheet到源文件夹和疾病类别的映射
    sheet_mapping = {
        "DR10.8": {
            "disease": "DR",
            "source_dirs": [
                f"{source_base_dir}/沈俊慧/沈俊慧10-8-1",
                f"{source_base_dir}/沈俊慧/沈俊慧10-8-2"
            ],
            "batch": "10.8"
        },
        "RVO10.7": {
            "disease": "RVO",
            "source_dirs": [
                f"{source_base_dir}/沈俊慧/沈俊慧10-7-1",
                f"{source_base_dir}/沈俊慧/沈俊慧10-7-2"
            ],
            "batch": "10.7"
        },
        "AMD10.7": {
            "disease": "AMD",
            "source_dirs": [
                f"{source_base_dir}/沈俊慧/沈俊慧10-7-1",
                f"{source_base_dir}/沈俊慧/沈俊慧10-7-2"
            ],
            "batch": "10.7"
        },
        "CSC10.7": {
            "disease": "CSC",
            "source_dirs": [
                f"{source_base_dir}/沈俊慧/沈俊慧10-7-1",
                f"{source_base_dir}/沈俊慧/沈俊慧10-7-2"
            ],
            "batch": "10.7"
        },
        "正常10.7": {
            "disease": "正常",
            "source_dirs": [
                f"{source_base_dir}/沈俊慧/沈俊慧10-7-1",
                f"{source_base_dir}/沈俊慧/沈俊慧10-7-2"
            ],
            "batch": "10.7"
        },
        "葡萄膜炎10.1": {
            "disease": "葡萄膜炎",
            "source_dirs": [
                f"{source_base_dir}/沈俊慧/沈俊慧10-1-1",
                f"{source_base_dir}/沈俊慧/沈俊慧10-1-2"
            ],
            "batch": "10.1"
        },
        "葡萄膜炎10.2": {
            "disease": "葡萄膜炎",
            "source_dirs": [
                f"{source_base_dir}/沈俊慧/沈俊慧10-2-1",
                f"{source_base_dir}/沈俊慧/沈俊慧10-2-2"
            ],
            "batch": "10.2"
        },
        "葡萄膜炎10.3": {
            "disease": "葡萄膜炎",
            "source_dirs": [
                f"{source_base_dir}/沈俊慧/沈俊慧10-3-1",
                f"{source_base_dir}/沈俊慧/沈俊慧10-3-2"
            ],
            "batch": "10.3"
        },
        "葡萄膜炎10.5": {
            "disease": "葡萄膜炎",
            "source_dirs": [
                f"{source_base_dir}/沈俊慧/沈俊慧10-5-1",
                f"{source_base_dir}/沈俊慧/沈俊慧10-5-2"
            ],
            "batch": "10.5"
        },
    }
    
    # 统计信息
    stats = defaultdict(lambda: defaultdict(int))
    not_found_patients = defaultdict(list)
    cross_batch_found = defaultdict(list)  # 跨批次找到的患者
    duplicate_in_sheet = defaultdict(list)  # sheet中重复的患者
    file_count = 0
    patient_count = 0
    
    # 跟踪所有被复制的图片
    copied_images = set()
    
    # 读取Excel文件
    xls = pd.ExcelFile(excel_path)
    
    print("="*70)
    print("开始根据归总.xlsx重组数据集（改进版）")
    print("="*70)
    
    # 遍历每个sheet
    for sheet_name in xls.sheet_names:
        if sheet_name == "Sheet12":
            continue
        
        if sheet_name not in sheet_mapping:
            print(f"\n跳过未配置的sheet: {sheet_name}")
            continue
        
        print(f"\n处理 {sheet_name}...")
        
        try:
            # 葡萄膜炎sheets没有表头，其他sheets有表头
            if '葡萄膜炎' in sheet_name:
                # 葡萄膜炎：无表头，第一行就是数据
                df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
            elif sheet_name == '正常10.7':
                # 正常10.7：第一行是无效表头（Unnamed），需要跳过，从第二行开始读取
                df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, skiprows=1)
            else:
                # 其他疾病：有表头，第一行是列名
                df = pd.read_excel(excel_path, sheet_name=sheet_name, header=0)
        except Exception as e:
            print(f"  读取失败: {e}")
            continue
        
        disease_info = sheet_mapping[sheet_name]
        disease = disease_info["disease"]
        source_dirs = disease_info["source_dirs"]
        batch = disease_info.get("batch", "")
        
        # 收集所有患者姓名和日期的组合，用于检测重复
        patient_date_pairs = []
        for idx, row in df.iterrows():
            patient_name = None
            visit_date = None
            
            # 根据是否有表头，使用不同的方式提取数据
            if '葡萄膜炎' in sheet_name:
                # 葡萄膜炎：无表头，使用列索引
                # 列1: patient_folder, 列3: patient_name, 列4: visit_date
                if len(row) > 3:
                    patient_name = row.iloc[3]  # 第4列是患者姓名
                    if len(row) > 4:
                        visit_date = row.iloc[4]  # 第5列是就诊日期
            elif sheet_name == '正常10.7':
                # 正常10.7：混合结构，前20行和后面行不同
                # 通过非空列数判断：前20行只有3列，后面行有12列
                non_null_count = row.notna().sum()
                if non_null_count <= 3:
                    # 前20行：列0: patient_folder, 列1: patient_name, 列2: visit_date（含备注）
                    if len(row) > 1:
                        patient_name = row.iloc[1]  # 第2列是患者姓名
                        if len(row) > 2:
                            visit_date = row.iloc[2]  # 第3列是就诊日期（含备注）
                else:
                    # 后面行：列1: patient_folder, 列3: patient_name, 列4: visit_date
                    if len(row) > 3:
                        patient_name = row.iloc[3]  # 第4列是患者姓名
                        if len(row) > 4:
                            visit_date = row.iloc[4]  # 第5列是就诊日期
            else:
                # 其他疾病：有表头，使用列名
                patient_name = row.get('patient_i_name')
                visit_date = row.get('visit_date')
            
            if pd.isna(patient_name) or not patient_name:
                continue
            
            patient_name = str(patient_name).strip()
            
            # 处理日期
            date_str = ""
            if pd.notna(visit_date):
                try:
                    if isinstance(visit_date, pd.Timestamp):
                        date_str = visit_date.strftime("%Y-%m-%d")
                    elif isinstance(visit_date, str):
                        try:
                            parsed_date = pd.to_datetime(visit_date)
                            date_str = parsed_date.strftime("%Y-%m-%d")
                        except:
                            date_str = str(visit_date)[:10]
                except:
                    date_str = ""
            
            patient_date_pairs.append(f"{patient_name}_{date_str}" if date_str else patient_name)
        
        # 检测sheet中的重复（同一患者同一日期）
        pair_counts = {}
        for pair in patient_date_pairs:
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
        
        for pair, count in pair_counts.items():
            if count > 1:
                duplicate_in_sheet[sheet_name].append(f"{pair} (出现{count}次)")
        
        # 跟踪已处理的患者行号（只在同一sheet内避免重复）
        processed_rows = {}
        
        # 处理每个患者
        for idx, row in df.iterrows():
            patient_name = None
            visit_date = None
            
            # 根据是否有表头，使用不同的方式提取数据
            if '葡萄膜炎' in sheet_name:
                # 葡萄膜炎：无表头，使用列索引
                # 列1: patient_folder, 列3: patient_name, 列4: visit_date
                if len(row) > 3:
                    patient_name = row.iloc[3]  # 第4列是患者姓名
                    if len(row) > 4:
                        visit_date = row.iloc[4]  # 第5列是就诊日期
            elif sheet_name == '正常10.7':
                # 正常10.7：混合结构，前20行和后面行不同
                # 通过非空列数判断：前20行只有3列，后面行有12列
                non_null_count = row.notna().sum()
                if non_null_count <= 3:
                    # 前20行：列0: patient_folder, 列1: patient_name, 列2: visit_date（含备注）
                    if len(row) > 1:
                        patient_name = row.iloc[1]  # 第2列是患者姓名
                        if len(row) > 2:
                            visit_date = row.iloc[2]  # 第3列是就诊日期（含备注）
                else:
                    # 后面行：列1: patient_folder, 列3: patient_name, 列4: visit_date
                    if len(row) > 3:
                        patient_name = row.iloc[3]  # 第4列是患者姓名
                        if len(row) > 4:
                            visit_date = row.iloc[4]  # 第5列是就诊日期
            else:
                # 其他疾病：有表头，使用列名
                patient_name = row.get('patient_i_name')
                visit_date = row.get('visit_date')
            
            if pd.isna(patient_name) or not patient_name:
                continue
            
            patient_name = str(patient_name).strip()
            
            # 处理日期
            date_str = ""
            if pd.notna(visit_date):
                try:
                    if isinstance(visit_date, pd.Timestamp):
                        date_str = visit_date.strftime("%Y%m%d")
                    elif isinstance(visit_date, str):
                        # 尝试解析字符串日期
                        try:
                            parsed_date = pd.to_datetime(visit_date)
                            date_str = parsed_date.strftime("%Y%m%d")
                        except:
                            # 如果解析失败，使用原始字符串的前10个字符
                            date_str = str(visit_date)[:10].replace('-', '').replace('/', '')
                except:
                    date_str = ""
            
            # 创建患者文件夹名：患者姓名_日期 或 患者姓名_批次号（如果没有日期）
            if date_str:
                patient_folder_name = f"{patient_name}_{date_str}"
            elif batch:
                patient_folder_name = f"{patient_name}_{batch}"
            else:
                patient_folder_name = patient_name
            
            # 使用患者姓名+日期作为唯一标识，同一患者同一日期才算重复
            unique_key = f"{patient_name}_{date_str}" if date_str else patient_name
            
            # 只在同一sheet内检查重复（同一批次同一患者同一日期）
            if unique_key in processed_rows:
                # 同一批次内同一日期重复，跳过
                continue
            
            processed_rows[unique_key] = idx
            
            # 先在对应批次的疾病文件夹中查找
            images = find_patient_images_in_disease_folder(patient_name, source_dirs, disease)
            
            found_from_other_batch = False
            # 如果没找到，尝试在其他批次的同疾病文件夹中查找（包括葡萄膜炎）
            if not images:
                all_disease_dirs = get_all_disease_folders(source_base_dir, disease)
                for other_dir in all_disease_dirs:
                    if other_dir not in source_dirs:
                        other_images = find_patient_images_in_disease_folder(patient_name, [other_dir], disease)
                        if other_images:
                            images = other_images
                            found_from_other_batch = True
                            other_batch = Path(other_dir).name.replace("沈俊慧", "")
                            cross_batch_found[sheet_name].append(f"{patient_name} (在{other_batch}找到)")
                            break
            
            if not images:
                not_found_patients[sheet_name].append(patient_name)
                continue
            
            # 创建目标路径
            patient_target_dir = target_path / disease / patient_folder_name / "OCT"
            patient_target_dir.mkdir(parents=True, exist_ok=True)
            
            # 复制图片
            copied_count = 0
            for img_path in images:
                target_file = patient_target_dir / img_path.name
                final_target = get_unique_filename(target_file)
                
                try:
                    shutil.copy2(img_path, final_target)
                    copied_count += 1
                    file_count += 1
                    # 记录已复制的图片（使用绝对路径）
                    copied_images.add(str(img_path.absolute()))
                except Exception as e:
                    print(f"    复制失败 {img_path.name}: {e}")
            
            if copied_count > 0:
                stats[disease][patient_folder_name] += copied_count
                patient_count += 1
            
            if patient_count % 50 == 0:
                print(f"  已处理 {patient_count} 位患者，{file_count} 个文件...")
    
    # 扫描原始目录，找出未被使用的图片
    print("\n扫描原始目录，检查未使用的图片...")
    unused_images = defaultdict(list)  # 按批次分组
    total_source_images = 0
    
    base_path = Path(source_base_dir) / "沈俊慧"
    for folder in sorted(base_path.glob("沈俊慧10-*")):
        if folder.is_dir():
            batch_name = folder.name.replace("沈俊慧", "")
            # 递归查找所有图片文件
            for img_file in folder.rglob("*"):
                if img_file.is_file() and img_file.suffix.lower() in ['.tif', '.tiff', '.jpg', '.jpeg', '.png']:
                    total_source_images += 1
                    img_path_str = str(img_file.absolute())
                    if img_path_str not in copied_images:
                        unused_images[batch_name].append(str(img_file.relative_to(folder)))
    
    # 打印统计信息
    print("\n" + "="*70)
    print("数据重组完成！统计信息:")
    print("="*70)
    
    for disease in sorted(stats.keys()):
        num_patients = len(stats[disease])
        num_images = sum(stats[disease].values())
        print(f"\n【{disease}】")
        print(f"  患者数量: {num_patients}")
        print(f"  图片数量: {num_images}")
    
    print(f"\n总计:")
    print(f"  疾病类别数: {len(stats)}")
    print(f"  患者总数: {len([p for patients in stats.values() for p in patients])}")
    print(f"  已使用图片: {file_count}")
    print(f"  原始图片总数: {total_source_images}")
    total_unused = sum(len(v) for v in unused_images.values())
    print(f"  未使用图片: {total_unused}")
    if total_unused > 0:
        print(f"  使用率: {file_count/total_source_images*100:.1f}%")
    
    # 打印各种特殊情况
    print("\n" + "="*70)
    print("特殊情况报告:")
    print("="*70)
    print("\n说明：")
    print("  • 同一患者在不同日期就诊视为不同病例（正常情况）")
    print("  • 只有同一患者在同一日期重复出现才被视为数据重复")
    print("  • 文件夹命名：患者姓名_日期（YYYYMMDD）")
    
    # 1. Sheet中重复的患者（同一批次内的真正重复）
    if duplicate_in_sheet:
        print("\n【1. 同一日期重复的患者（数据重复，已自动去重）】")
        total_dup = sum(len(v) for v in duplicate_in_sheet.values())
        print(f"说明: 这些患者在同一日期重复出现，属于数据录入重复")
        print(f"     程序已自动去重，每个患者每个日期只保存一次")
        print(f"总计: {total_dup}个患者")
        for sheet_name in sorted(duplicate_in_sheet.keys()):
            duplicates = duplicate_in_sheet[sheet_name]
            if duplicates:
                print(f"\n{sheet_name} ({len(duplicates)}个):")
                for i, dup in enumerate(duplicates, 1):
                    print(f"  {i}. {dup}")
    else:
        print("\n【1. 同一日期重复的患者】: 无")
    
    # 2. 跨批次找到的患者
    if cross_batch_found:
        print("\n【2. 跨批次找到图片的患者（图片在其他批次）】")
        print(f"说明: 这些患者在Excel中记录在某批次，但图片在其他批次文件夹中找到")
        print(f"     可能是数据组织或归档的问题")
        total_cross = 0
        for sheet_name in sorted(cross_batch_found.keys()):
            patients = cross_batch_found[sheet_name]
            if patients:
                total_cross += len(patients)
                print(f"\n{sheet_name} ({len(patients)}人):")
                for i, patient in enumerate(patients, 1):
                    print(f"  {i}. {patient}")
        print(f"\n跨批次找到总数: {total_cross}")
    else:
        print("\n【2. 跨批次找到图片的患者】: 无")
    
    # 3. 未找到图片的患者
    if not_found_patients:
        print("\n【3. 未找到图片的患者（需要人工检查）】")
        print(f"说明: Excel中记录了这些患者，但在所有批次中都未找到对应图片")
        print(f"     可能原因：患者姓名不匹配、图片缺失、或归档位置不正确")
        total_not_found = 0
        for sheet_name in sorted(not_found_patients.keys()):
            patients = not_found_patients[sheet_name]
            if patients:
                total_not_found += len(patients)
                print(f"\n{sheet_name} ({len(patients)}人):")
                for i, patient in enumerate(patients, 1):
                    print(f"  {i}. {patient}")
        print(f"\n未找到图片总数: {total_not_found}")
    else:
        print("\n【3. 未找到图片的患者】: 无")
    
    # 4. 未被使用的图片
    if unused_images:
        print("\n【4. 原始目录中未被使用的图片】")
        total_unused = sum(len(v) for v in unused_images.values())
        print(f"说明: 这些图片存在于原始目录中，但未被Excel记录，因此未被纳入重组数据集")
        print(f"     可能原因：患者未在Excel中登记、图片命名不规范、或非目标疾病的图片")
        print(f"总计: {total_unused}个图片文件")
        print(f"使用率: {file_count}/{total_source_images} = {file_count/total_source_images*100:.1f}%")
        print(f"\n按批次统计:")
        for batch_name in sorted(unused_images.keys()):
            images = unused_images[batch_name]
            if images:
                print(f"  {batch_name}: {len(images)}个文件")
    else:
        print("\n【4. 未被使用的图片】: 无，所有图片都已使用")
    
    print(f"\n目标目录: {target_path}")
    print("="*70)
    
    # 生成详细的特殊情况报告文件（添加时间戳避免覆盖）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = target_path / f"特殊情况报告_{timestamp}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("数据集重组特殊情况详细报告\n")
        f.write("="*70 + "\n")
        f.write(f"生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Excel文件: 归总_修正.xlsx\n")
        f.write("="*70 + "\n")
        
        f.write("\n【重要说明】\n")
        f.write("  • 同一患者在不同日期就诊视为不同病例（正常情况，不去重）\n")
        f.write("  • 只有同一患者在同一日期重复出现才被视为数据重复（已去重）\n")
        f.write("  • 患者文件夹命名格式：患者姓名_日期（YYYYMMDD）\n")
        f.write("  • 如果没有日期信息，使用：患者姓名_批次号\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("一、同一日期重复的患者（数据录入重复）\n")
        f.write("="*70 + "\n")
        if duplicate_in_sheet:
            total_dup = sum(len(v) for v in duplicate_in_sheet.values())
            f.write(f"\n总计: {total_dup}个患者在同一日期重复出现\n")
            f.write("说明: 这些患者在同一日期的Excel中重复出现，属于数据录入重复\n")
            f.write("      程序已自动去重，每个患者每个日期只保存一次图片\n\n")
            for sheet_name in sorted(duplicate_in_sheet.keys()):
                duplicates = duplicate_in_sheet[sheet_name]
                if duplicates:
                    f.write(f"\n{sheet_name}:\n")
                    for i, dup in enumerate(duplicates, 1):
                        f.write(f"  {i}. {dup}\n")
        else:
            f.write("\n无同一日期重复的患者\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("二、跨批次找到图片的患者\n")
        f.write("="*70 + "\n")
        if cross_batch_found:
            total_cross = sum(len(v) for v in cross_batch_found.values())
            f.write(f"\n总计: {total_cross}人的图片在其他批次找到\n")
            f.write("说明: 这些患者在Excel中记录在某批次，但图片在其他批次文件夹中找到\n")
            f.write("      可能是数据组织或归档的问题，已自动从其他批次复制图片\n\n")
            for sheet_name in sorted(cross_batch_found.keys()):
                patients = cross_batch_found[sheet_name]
                if patients:
                    f.write(f"\n{sheet_name}:\n")
                    for i, patient in enumerate(patients, 1):
                        f.write(f"  {i}. {patient}\n")
        else:
            f.write("\n无跨批次情况\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("三、未找到图片的患者（需要人工检查）\n")
        f.write("="*70 + "\n")
        if not_found_patients:
            total_not_found = sum(len(v) for v in not_found_patients.values())
            f.write(f"\n总计: {total_not_found}人未找到图片\n")
            f.write("说明: Excel中记录了这些患者，但在所有批次中都未找到对应图片\n")
            f.write("可能原因:\n")
            f.write("  1. 患者姓名拼写不匹配\n")
            f.write("  2. 图片文件确实缺失\n")
            f.write("  3. 图片归档在其他位置\n")
            f.write("  4. 图片文件名格式与患者姓名不对应\n\n")
            for sheet_name in sorted(not_found_patients.keys()):
                patients = not_found_patients[sheet_name]
                if patients:
                    f.write(f"\n{sheet_name}:\n")
                    for i, patient in enumerate(patients, 1):
                        f.write(f"  {i}. {patient}\n")
        else:
            f.write("\n所有患者都找到了图片\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("四、原始目录中未被使用的图片\n")
        f.write("="*70 + "\n")
        if unused_images:
            total_unused = sum(len(v) for v in unused_images.values())
            f.write(f"\n总计: {total_unused}个图片文件未被使用\n")
            f.write("说明: 这些图片存在于原始目录中，但未被Excel记录，因此未被纳入重组数据集\n")
            f.write("可能原因:\n")
            f.write("  1. 患者未在Excel中登记\n")
            f.write("  2. 图片文件命名不规范，无法匹配患者姓名\n")
            f.write("  3. 非目标疾病的图片\n")
            f.write("  4. 测试或临时文件\n\n")
            f.write(f"原始图片总数: {total_source_images}\n")
            f.write(f"已使用图片: {file_count}\n")
            f.write(f"未使用图片: {total_unused}\n")
            f.write(f"使用率: {file_count/total_source_images*100:.1f}%\n\n")
            f.write("按批次统计:\n")
            for batch_name in sorted(unused_images.keys()):
                images = unused_images[batch_name]
                if images:
                    f.write(f"\n{batch_name} ({len(images)}个文件):\n")
                    # 列出所有文件，不省略
                    for i, img in enumerate(images, 1):
                        f.write(f"  {i}. {img}\n")
        else:
            f.write("\n所有原始图片都已被使用\n")
        
        f.write("\n" + "="*70 + "\n")
        f.write("报告结束\n")
        f.write("="*70 + "\n")
    
    print(f"\n✅ 特殊情况详细报告已保存到: {report_file}")

def main():
    excel_path = "/data2/xuhanyang/dataset/沈俊慧/归总_修正.xlsx"
    source_base_dir = "/data2/xuhanyang/dataset"
    target_dir = "/data2/xuhanyang/dataset/沈俊慧_Excel重组数据集_v4"
    
    print("="*70)
    print("基于归总_修正.xlsx的数据集重组工具（改进版）")
    print("="*70)
    print(f"Excel文件: {excel_path}")
    print(f"源目录: {source_base_dir}")
    print(f"目标目录: {target_dir}")
    print("="*70)
    
    if not os.path.exists(excel_path):
        print(f"错误: Excel文件不存在: {excel_path}")
        return
    
    reorganize_by_excel(excel_path, source_base_dir, target_dir)

if __name__ == "__main__":
    main()

