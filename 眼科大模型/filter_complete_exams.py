#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
筛选同时具有"欧堡"、"FFA"、"OCT"三种检查的病例
按年份统计，时间范围前后两周
"""

import os
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple
from collections import defaultdict

DEFAULT_ROOT = "/share/kongzitai/ophthalmology/E:"
OUTPUT_DIR = "/data2/xuhanyang/眼科大模型/三模态齐全病例"
YEARS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]


def get_exam_dates_for_patient(patient_path: Path) -> Dict[str, List]:
    """
    获取患者的所有检查日期及检查类型
    返回: {exam_type: [(date, info_dict), ...]}
    info_dict包含额外信息，如OCT类型、FFA报告等
    """
    exam_dates = defaultdict(list)
    
    if not patient_path.exists():
        return exam_dates
    
    try:
        # 遍历日期文件夹
        for date_folder in patient_path.iterdir():
            if not date_folder.is_dir():
                continue
            
            # 解析日期
            date_str = date_folder.name
            try:
                exam_date = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                continue
            
            # 检查该日期下的检查项目
            try:
                for exam_folder in date_folder.iterdir():
                    if not exam_folder.is_dir():
                        continue
                    
                    exam_name = exam_folder.name
                    exam_name_lower = exam_name.lower()
                    
                    # 判断检查类型
                    # 欧堡检查：支持"欧堡"、"欧宝"、"optos"，但排除"海德堡OCT"
                    is_optos = False
                    if 'optos' in exam_name_lower:
                        is_optos = True
                    elif ('欧堡' in exam_name or '欧宝' in exam_name) and 'oct' not in exam_name_lower:
                        is_optos = True
                    elif '广角眼底照相' in exam_name and ('欧堡' in exam_name or '欧宝' in exam_name):
                        is_optos = True
                    
                    if is_optos:
                        exam_dates['欧堡'].append((exam_date, {}))
                    
                    # FFA检查
                    if 'ffa' in exam_name_lower or '荧光造影' in exam_name:
                        # 读取FFA报告
                        ffa_report = ""
                        try:
                            txt_files = list(exam_folder.glob("*.txt"))
                            report_texts = []
                            for txt_file in txt_files:
                                try:
                                    with open(txt_file, 'r', encoding='utf-8') as f:
                                        content = f.read().strip()
                                        if content:
                                            report_texts.append(content)
                                except:
                                    pass
                            if report_texts:
                                ffa_report = "\n\n".join(report_texts)
                        except:
                            pass
                        
                        exam_dates['FFA'].append((exam_date, {'report': ffa_report}))
                    
                    # OCT检查：只支持海德堡、科林、视微
                    if 'oct' in exam_name_lower:
                        # 检查是否是支持的OCT类型
                        oct_type = ""
                        if '海德堡' in exam_name or 'heidelberg' in exam_name_lower:
                            oct_type = "海德堡"
                        elif '科林' in exam_name or 'kowa' in exam_name_lower:
                            oct_type = "科林"
                        elif '视微' in exam_name or 'optovue' in exam_name_lower:
                            oct_type = "视微"
                        
                        if oct_type:
                            exam_dates['OCT'].append((exam_date, {'type': oct_type}))
            except Exception:
                continue
    
    except Exception:
        pass
    
    return exam_dates


def check_complete_exams(exam_dates: Dict[str, List[datetime]], 
                        time_window_days: int = 7) -> Tuple[bool, Dict[str, datetime]]:
    """
    检查是否在时间窗口内同时具有三种检查
    
    Args:
        exam_dates: 各类检查的日期列表
        time_window_days: 时间窗口（天数）
    
    Returns:
        (是否齐全, {exam_type: 选中的日期})
    """
    # 检查是否所有三种检查都存在
    required_exams = ['欧堡', 'FFA', 'OCT']
    for exam_type in required_exams:
        if exam_type not in exam_dates or len(exam_dates[exam_type]) == 0:
            return False, {}
    
    # 尝试找到一个时间窗口内的组合
    # 以FFA的日期为基准
    for ffa_date in exam_dates['FFA']:
        window_start = ffa_date - timedelta(days=time_window_days)
        window_end = ffa_date + timedelta(days=time_window_days)
        
        # 在窗口内查找OCT
        oct_in_window = [d for d in exam_dates['OCT'] 
                        if window_start <= d <= window_end]
        
        # 在窗口内查找欧堡
        optos_in_window = [d for d in exam_dates['欧堡'] 
                          if window_start <= d <= window_end]
        
        if oct_in_window and optos_in_window:
            # 找到了符合条件的组合，选择最接近FFA日期的
            selected_oct = min(oct_in_window, key=lambda d: abs((d - ffa_date).days))
            selected_optos = min(optos_in_window, key=lambda d: abs((d - ffa_date).days))
            
            return True, {
                'FFA': ffa_date,
                'OCT': selected_oct,
                '欧堡': selected_optos
            }
    
    return False, {}


def find_all_complete_exams(exam_dates: Dict[str, List], 
                            time_window_days: int = 7) -> List[Dict]:
    """
    查找所有符合条件的三模态组合（支持同一患者多次就诊）
    
    Args:
        exam_dates: 各类检查的日期列表，格式为 {exam_type: [(date, info_dict), ...]}
        time_window_days: 时间窗口（天数）
    
    Returns:
        所有符合条件的组合列表: [{exam_type: 日期, 'oct_type': OCT类型, 'ffa_report': FFA报告}, ...]
    """
    all_combinations = []
    
    # 检查是否所有三种检查都存在
    required_exams = ['欧堡', 'FFA', 'OCT']
    for exam_type in required_exams:
        if exam_type not in exam_dates or len(exam_dates[exam_type]) == 0:
            return all_combinations
    
    # 以FFA的日期为基准，找出所有符合条件的组合
    for ffa_item in exam_dates['FFA']:
        ffa_date, ffa_info = ffa_item
        window_start = ffa_date - timedelta(days=time_window_days)
        window_end = ffa_date + timedelta(days=time_window_days)
        
        # 在窗口内查找OCT
        oct_in_window = [(d, info) for d, info in exam_dates['OCT'] 
                        if window_start <= d <= window_end]
        
        # 在窗口内查找欧堡
        optos_in_window = [(d, info) for d, info in exam_dates['欧堡'] 
                          if window_start <= d <= window_end]
        
        if oct_in_window and optos_in_window:
            # 找到了符合条件的组合，选择最接近FFA日期的
            selected_oct = min(oct_in_window, key=lambda item: abs((item[0] - ffa_date).days))
            selected_optos = min(optos_in_window, key=lambda item: abs((item[0] - ffa_date).days))
            
            all_combinations.append({
                'FFA': ffa_date,
                'OCT': selected_oct[0],
                '欧堡': selected_optos[0],
                'oct_type': selected_oct[1].get('type', ''),
                'ffa_report': ffa_info.get('report', '')
            })
    
    return all_combinations


def scan_year_directory(year_path: Path) -> List[Dict]:
    """
    扫描年份目录，找出所有三模态齐全的病例
    改进版：支持跨月份文件夹数据合并
    """
    complete_cases = []
    
    if not year_path.exists():
        return complete_cases
    
    # 获取所有月份文件夹
    try:
        month_folders = [f for f in year_path.iterdir() if f.is_dir()]
    except Exception:
        return complete_cases
    
    print(f"    第一步：收集所有患者的检查数据...")
    
    # 第一步：收集所有患者的所有检查数据（跨所有月份文件夹）
    all_patient_data = defaultdict(lambda: {
        'exam_dates': defaultdict(list),
        'patient_name': '',
        'patient_folder': '',
        'patient_path': '',
        'month_folders': []
    })
    
    total_patient_folders = 0
    
    for month_folder in month_folders:
        try:
            patient_folders = [f for f in month_folder.iterdir() if f.is_dir()]
        except Exception:
            continue
        
        for patient_folder in patient_folders:
            total_patient_folders += 1
            
            # 解析患者信息
            patient_folder_name = patient_folder.name
            parts = patient_folder_name.split()
            
            if len(parts) < 4:
                continue
            
            patient_id = parts[0]
            patient_name = parts[1]
            
            # 获取该患者在这个文件夹中的所有检查日期
            exam_dates = get_exam_dates_for_patient(patient_folder)
            
            # 合并到患者的总数据中
            for exam_type, dates in exam_dates.items():
                all_patient_data[patient_id]['exam_dates'][exam_type].extend(dates)
            
            # 记录患者基本信息（使用最后一次遇到的）
            all_patient_data[patient_id]['patient_name'] = patient_name
            all_patient_data[patient_id]['patient_folder'] = patient_folder_name
            all_patient_data[patient_id]['patient_path'] = str(patient_folder)
            all_patient_data[patient_id]['month_folders'].append(month_folder.name)
    
    print(f"    共扫描 {total_patient_folders} 个患者文件夹")
    print(f"    去重后唯一患者数: {len(all_patient_data)}")
    print()
    print(f"    第二步：检查每个患者的三模态是否齐全...")
    
    # 第二步：检查每个患者的三模态是否齐全
    # 改进：支持同一患者的多次就诊记录
    processed_visits = set()  # 去重：同一患者同一就诊日期只记录一次
    
    for patient_id, patient_info in all_patient_data.items():
        exam_dates = patient_info['exam_dates']
        
        # 去重检查日期（同一天可能在多个月份文件夹中都有记录）
        for exam_type in exam_dates:
            # 对于 (date, info_dict) 元组列表，按日期去重
            # 使用字典来保留每个唯一日期的第一个 info_dict
            unique_dates = {}
            for date, info in exam_dates[exam_type]:
                if date not in unique_dates:
                    unique_dates[date] = info
            # 转换回排序的列表
            exam_dates[exam_type] = sorted([(d, unique_dates[d]) for d in unique_dates.keys()])
        
        # 查找所有符合条件的三模态组合（支持多次就诊）
        all_combinations = find_all_complete_exams(exam_dates, time_window_days=7)
        
        # 为每个符合条件的组合创建一条记录
        for selected_dates in all_combinations:
            # 使用FFA日期作为主要就诊日期
            visit_date = selected_dates['FFA'].strftime('%Y-%m-%d')
            
            # 去重key：同一患者、同一就诊日期只记录一次
            dedup_key = (patient_id, visit_date)
            if dedup_key in processed_visits:
                continue
            
            processed_visits.add(dedup_key)
            
            # 记录病例信息
            case_info = {
                'patient_id': patient_id,
                'patient_name': patient_info['patient_name'],
                'patient_folder': patient_info['patient_folder'],
                'visit_date': visit_date,
                'ffa_date': selected_dates['FFA'].strftime('%Y-%m-%d'),
                'oct_date': selected_dates['OCT'].strftime('%Y-%m-%d'),
                'optos_date': selected_dates['欧堡'].strftime('%Y-%m-%d'),
                'oct_type': selected_dates.get('oct_type', ''),  # OCT类型
                'ffa_report': selected_dates.get('ffa_report', ''),  # FFA报告
                'time_span_days': max(
                    abs((selected_dates['FFA'] - selected_dates['OCT']).days),
                    abs((selected_dates['FFA'] - selected_dates['欧堡']).days),
                    abs((selected_dates['OCT'] - selected_dates['欧堡']).days)
                ),
                'patient_path': patient_info['patient_path'],
                'month_folder': ', '.join(sorted(set(patient_info['month_folders'])))
            }
            
            complete_cases.append(case_info)
    
    print(f"    找到三模态齐全病例: {len(complete_cases)} 例")
    print()
    
    return complete_cases


def process_all_years():
    """
    处理所有年份
    """
    print("="*70)
    print("筛选三模态齐全病例（欧堡 + FFA + OCT）")
    print("时间窗口: 以FFA为基准，前后7天")
    print("="*70)
    print()
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    all_years_summary = []
    
    for year in YEARS:
        year_path = Path(DEFAULT_ROOT) / year
        
        if not year_path.exists():
            print(f"⚠️  {year}年: 目录不存在")
            print()
            continue
        
        print(f"正在处理: {year}年")
        print(f"  路径: {year_path}")
        
        # 扫描该年份
        complete_cases = scan_year_directory(year_path)
        
        print(f"  结果: 找到 {len(complete_cases)} 个三模态齐全的病例")
        
        if len(complete_cases) == 0:
            print(f"  ⚠️  无符合条件的病例")
            print()
            continue
        
        # 创建DataFrame
        df = pd.DataFrame(complete_cases)
        
        # 按就诊日期排序
        df = df.sort_values(['visit_date', 'patient_id']).reset_index(drop=True)
        
        # 保存Excel
        output_file = Path(OUTPUT_DIR) / f"{year}年_三模态齐全病例.xlsx"
        
        with pd.ExcelWriter(output_file, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='病例列表')
            
            # 添加统计信息sheet
            stats_data = {
                '统计项': [
                    '总病例数',
                    '平均时间跨度（天）',
                    '最大时间跨度（天）',
                    '最小时间跨度（天）',
                    '同一天完成三项检查的病例数'
                ],
                '数值': [
                    len(df),
                    df['time_span_days'].mean(),
                    df['time_span_days'].max(),
                    df['time_span_days'].min(),
                    (df['time_span_days'] == 0).sum()
                ]
            }
            stats_df = pd.DataFrame(stats_data)
            stats_df.to_excel(writer, index=False, sheet_name='统计信息')
        
        print(f"  ✓ 已保存: {output_file}")
        
        # 汇总信息
        all_years_summary.append({
            'year': year,
            'total_cases': len(df),
            'avg_time_span': df['time_span_days'].mean(),
            'same_day_cases': (df['time_span_days'] == 0).sum()
        })
        
        print()
    
    # 生成总体汇总报告
    if all_years_summary:
        summary_df = pd.DataFrame(all_years_summary)
        summary_file = Path(OUTPUT_DIR) / "各年度汇总统计.xlsx"
        
        with pd.ExcelWriter(summary_file, engine='xlsxwriter') as writer:
            summary_df.to_excel(writer, index=False, sheet_name='年度汇总')
        
        print("="*70)
        print("各年度汇总:")
        print("="*70)
        print(summary_df.to_string(index=False))
        print()
        print(f"总计病例数: {summary_df['total_cases'].sum()}")
        print(f"汇总文件已保存: {summary_file}")
    
    print()
    print("="*70)
    print("全部完成！")
    print(f"输出目录: {OUTPUT_DIR}")
    print("="*70)


if __name__ == "__main__":
    process_all_years()

