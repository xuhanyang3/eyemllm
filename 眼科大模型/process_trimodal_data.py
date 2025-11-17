#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
处理三模态齐全病例数据：
1. 从各年份数据中去除葡萄膜炎病例
2. 将去重后的各年份数据合并成一个表
"""

import os
import pandas as pd
from pathlib import Path
from datetime import datetime

# 配置路径
UVEITIS_EXCEL = "/data2/xuhanyang/dataset/沈俊慧/归总_修正.xlsx"
INPUT_DIR = "/data2/xuhanyang/眼科大模型/三模态齐全病例"
OUTPUT_DIR = "/data2/xuhanyang/眼科大模型/三模态齐全病例_去重后"

def load_uveitis_cases():
    """
    从归总_修正.xlsx中读取所有葡萄膜炎病例
    返回: set of (patient_folder, visit_date) tuples
    """
    print("正在读取葡萄膜炎病例数据...")
    
    uveitis_cases = set()
    
    # 葡萄膜炎相关的sheets
    uveitis_sheets = [
        "葡萄膜炎10.1",
        "葡萄膜炎10.2", 
        "葡萄膜炎10.3",
        "葡萄膜炎10.5"
    ]
    
    try:
        xls = pd.ExcelFile(UVEITIS_EXCEL)
        
        for sheet_name in uveitis_sheets:
            if sheet_name not in xls.sheet_names:
                print(f"  警告: 未找到sheet {sheet_name}")
                continue
            
            # 葡萄膜炎sheets没有表头
            df = pd.read_excel(UVEITIS_EXCEL, sheet_name=sheet_name, header=None)
            
            for idx, row in df.iterrows():
                # 列1: patient_folder, 列4: visit_date
                if len(row) > 4:
                    patient_folder = row.iloc[1]  # 第2列
                    visit_date = row.iloc[4]      # 第5列
                    
                    if pd.notna(patient_folder) and pd.notna(visit_date):
                        patient_folder = str(patient_folder).strip()
                        
                        # 解析日期
                        try:
                            if isinstance(visit_date, pd.Timestamp):
                                date_str = visit_date.strftime("%Y-%m-%d")
                            else:
                                date_str = str(visit_date)[:10]
                            
                            uveitis_cases.add((patient_folder, date_str))
                        except:
                            continue
        
        print(f"  共找到 {len(uveitis_cases)} 个唯一的葡萄膜炎病例")
        return uveitis_cases
    
    except Exception as e:
        print(f"  错误: 读取葡萄膜炎数据失败 - {e}")
        return set()


def remove_uveitis_from_file(input_file, uveitis_cases):
    """
    从单个年份文件中去除葡萄膜炎病例
    """
    year = Path(input_file).stem.split('年')[0]
    print(f"\n处理 {year}年 数据...")
    
    try:
        # 读取原始数据
        df = pd.read_excel(input_file)
        original_count = len(df)
        print(f"  原始病例数: {original_count}")
        
        # 标记需要删除的行
        to_remove = []
        for idx, row in df.iterrows():
            patient_folder = str(row['patient_folder']).strip()
            visit_date = str(row['visit_date'])[:10]
            
            if (patient_folder, visit_date) in uveitis_cases:
                to_remove.append(idx)
        
        # 删除葡萄膜炎病例
        df_cleaned = df.drop(to_remove)
        removed_count = len(to_remove)
        remaining_count = len(df_cleaned)
        
        print(f"  去除葡萄膜炎病例: {removed_count}")
        print(f"  剩余病例数: {remaining_count}")
        
        return df_cleaned, {
            'year': year,
            'original': original_count,
            'removed': removed_count,
            'remaining': remaining_count
        }
    
    except Exception as e:
        print(f"  错误: 处理失败 - {e}")
        return None, None


def merge_all_years(cleaned_dfs):
    """
    合并所有年份的数据
    """
    print("\n合并所有年份数据...")
    
    # 合并所有DataFrame
    merged_df = pd.concat(cleaned_dfs, ignore_index=True)
    
    # 按年份和就诊日期排序
    merged_df = merged_df.sort_values(['visit_date', 'patient_id']).reset_index(drop=True)
    
    print(f"  合并后总病例数: {len(merged_df)}")
    
    return merged_df


def main():
    """
    主函数
    """
    print("="*70)
    print("三模态齐全病例数据处理")
    print("="*70)
    
    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # 1. 读取葡萄膜炎病例
    uveitis_cases = load_uveitis_cases()
    
    if not uveitis_cases:
        print("\n错误: 未能读取葡萄膜炎病例数据")
        return
    
    # 2. 处理各年份文件
    years = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]
    cleaned_dfs = []
    stats = []
    
    for year in years:
        input_file = Path(INPUT_DIR) / f"{year}年_三模态齐全病例.xlsx"
        
        if not input_file.exists():
            print(f"\n警告: {year}年数据文件不存在")
            continue
        
        # 去除葡萄膜炎病例
        df_cleaned, stat = remove_uveitis_from_file(input_file, uveitis_cases)
        
        if df_cleaned is not None:
            # 保存去重后的年度文件
            output_file = Path(OUTPUT_DIR) / f"{year}年_三模态齐全病例.xlsx"
            df_cleaned.to_excel(output_file, index=False)
            print(f"  ✓ 已保存: {output_file}")
            
            cleaned_dfs.append(df_cleaned)
            stats.append(stat)
    
    if not cleaned_dfs:
        print("\n错误: 没有成功处理任何年份的数据")
        return
    
    # 3. 合并所有年份
    merged_df = merge_all_years(cleaned_dfs)
    
    # 保存合并后的文件
    merged_file = Path(OUTPUT_DIR) / "三模态齐全病例_合并.xlsx"
    merged_df.to_excel(merged_file, index=False)
    print(f"  ✓ 已保存合并文件: {merged_file}")
    
    # 4. 生成统计报告
    print("\n" + "="*70)
    print("处理统计:")
    print("="*70)
    
    stats_df = pd.DataFrame(stats)
    print(stats_df.to_string(index=False))
    
    print(f"\n总计:")
    print(f"  原始病例总数: {stats_df['original'].sum()}")
    print(f"  去除病例总数: {stats_df['removed'].sum()}")
    print(f"  剩余病例总数: {stats_df['remaining'].sum()}")
    
    # 保存统计信息
    stats_file = Path(OUTPUT_DIR) / "去重统计.xlsx"
    stats_df.to_excel(stats_file, index=False)
    print(f"\n✓ 统计信息已保存: {stats_file}")
    
    # 5. 生成详细报告
    report_file = Path(OUTPUT_DIR) / "去重报告.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("三模态齐全病例去重报告\n")
        f.write("="*70 + "\n")
        f.write(f"生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"葡萄膜炎病例数: {len(uveitis_cases)}\n")
        f.write("\n")
        
        f.write("各年度处理情况:\n")
        f.write("-"*70 + "\n")
        for stat in stats:
            f.write(f"{stat['year']}年:\n")
            f.write(f"  原始病例数: {stat['original']}\n")
            f.write(f"  去除病例数: {stat['removed']}\n")
            f.write(f"  剩余病例数: {stat['remaining']}\n")
            f.write(f"  去除比例: {stat['removed']/stat['original']*100:.2f}%\n")
            f.write("\n")
        
        f.write("="*70 + "\n")
        f.write("总计:\n")
        f.write(f"  原始病例总数: {stats_df['original'].sum()}\n")
        f.write(f"  去除病例总数: {stats_df['removed'].sum()}\n")
        f.write(f"  剩余病例总数: {stats_df['remaining'].sum()}\n")
        f.write(f"  总去除比例: {stats_df['removed'].sum()/stats_df['original'].sum()*100:.2f}%\n")
        f.write("="*70 + "\n")
    
    print(f"✓ 详细报告已保存: {report_file}")
    
    print("\n" + "="*70)
    print("处理完成!")
    print(f"输出目录: {OUTPUT_DIR}")
    print("="*70)


if __name__ == "__main__":
    main()

