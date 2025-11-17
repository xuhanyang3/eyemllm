#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export presence matrix by year (按年份统计，合并月份数据，去重).
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import List, Set, Tuple
from pathlib import Path

import pandas as pd

DEFAULT_ROOT = "/share/kongzitai/ophthalmology/E:"
MATRIX_OUT_DIR = "/data2/xuhanyang/眼科大模型/年度数据"

# 要处理的年份
YEARS = ["2019", "2020", "2021", "2022", "2023", "2024", "2025"]


# ---------- 工具函数 ----------
def is_b_scan(name: str) -> bool:
    lower = name.lower()
    return ("b超" in name) or ("b-scan" in lower) or ("眼部b超" in name) or ("ab超" in name)


def read_text_file_with_best_effort(file_path: str) -> str:
    for enc in ("utf-8", "gb18030", "gbk", "ansi"):
        try:
            with open(file_path, "r", encoding=enc, errors="ignore") as f:
                return f.read().strip()
        except Exception:
            continue
    try:
        with open(file_path, "rb") as f:
            return f.read().decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def normalize_for_match(s: str) -> str:
    return s.replace("（", "(").replace("）", ")").replace(" ", "").lower()


# ---------- 分类函数 ----------
def classify_exam(exam_name: str) -> tuple[str, str, str]:
    """
    返回 (major, sub, eye_type)
    eye_type: 单眼 | 双眼 | ""
    """
    name = exam_name.strip()
    lower = name.lower()
    norm = normalize_for_match(name)

    # 1. 单/双眼
    eye_type = ""
    if "单眼" in name:
        eye_type = "单眼"
    elif "双眼" in name:
        eye_type = "双眼"

    # 2. B超
    if is_b_scan(name):
        return "B超", "B超", eye_type

    # 3. 造影
    if any(k in lower for k in ("ffa", "荧光造影", "眼底荧光造影", "icg", "吲哚青")):
        return "造影", "眼底荧光造影", eye_type

    # 4. OCT 子类
    oct_sub = [
        "海德堡OCT 血流模式",
        "海德堡OCT",
        "视微OCT 血流模式",
        "视微OCT",
        "科林OCT 血流模式",
        "科林OCT",
        "图湃OCT 血流模式",
        "图湃OCT",
        "蔡司OCT",
    ]
    for sub in oct_sub:
        if normalize_for_match(sub) in norm:
            return "OCT", sub, eye_type
    if "oct" in lower:
        return "OCT", "OCT", eye_type

    # 5. 眼底拍照
    zeiss_var = ["激光广角眼底照相（蔡司真彩）", "激光广角眼底照相(蔡司真彩)", "蔡司真彩"]
    for v in zeiss_var:
        if normalize_for_match(v) in norm:
            return "眼底拍照", "激光广角眼底照相（蔡司真彩）", eye_type
    # 欧堡检查：同时支持"欧堡"和"欧宝"（早期错别字）
    if "欧堡" in name or "欧宝" in name:
        return "眼底拍照", "激光广角眼底照相检查(欧堡)", eye_type
    for v in ["激光广角眼底照相检查(欧堡)", "激光广角眼底照相检查（欧堡）", 
              "激光广角眼底照相检查(欧宝)", "激光广角眼底照相检查（欧宝）", "optos"]:
        if normalize_for_match(v) in norm:
            return "眼底拍照", "激光广角眼底照相检查(欧堡)", eye_type
    for v in ["眼底照相", "眼底彩照", "fundusphoto"]:
        if normalize_for_match(v) in norm:
            return "眼底拍照", "眼底照相", eye_type

    return "其他", "", eye_type


# ---------- 数据结构 ----------
@dataclass
class ExamRecord:
    diagnosis: str
    detect_dir: str
    patient_folder: str
    patient_i_name: str
    visit_date: str
    detect_ty: str
    major_category: str
    sub_category: str
    eye_type: str
    txt_count: int
    txt_filenames: str
    txt_1: str
    txt_2: str
    txt_3: str
    txt_4: str
    month_folder: str  # 新增：记录来源月份文件夹


def parse_patient_name_from_folder(folder_basename: str) -> str:
    parts = folder_basename.split()
    return parts[1] if len(parts) >= 2 else ""


# ---------- 扫描目录 ----------
def collect_exam_records_for_year(year_dir: str) -> Tuple[List[ExamRecord], Set[Tuple]]:
    """
    收集一个年份目录下所有月份文件夹的检查记录
    返回: (记录列表, 去重用的key集合)
    """
    records: List[ExamRecord] = []
    seen_keys: Set[Tuple] = set()  # 用于去重: (patient_folder, visit_date, detect_ty)
    
    if not os.path.isdir(year_dir):
        return records, seen_keys

    # 获取所有月份文件夹
    try:
        month_folders = sorted([f for f in os.listdir(year_dir) if os.path.isdir(os.path.join(year_dir, f))])
    except Exception:
        return records, seen_keys

    print(f"  找到月份文件夹: {', '.join(month_folders)}")

    for month_folder in month_folders:
        month_path = os.path.join(year_dir, month_folder)
        print(f"    处理月份: {month_folder}", end=" ... ")
        
        month_records = 0
        duplicates = 0
        
        # 遍历患者文件夹
        try:
            patient_folders = [pf for pf in os.listdir(month_path) if os.path.isdir(os.path.join(month_path, pf))]
        except Exception:
            print("错误")
            continue

        for pf in patient_folders:
            pf_path = os.path.join(month_path, pf)
            try:
                visits = [v for v in os.listdir(pf_path) if os.path.isdir(os.path.join(pf_path, v))]
            except Exception:
                continue
            
            for vd in visits:
                vd_path = os.path.join(pf_path, vd)
                try:
                    exams = [e for e in os.listdir(vd_path) if os.path.isdir(os.path.join(vd_path, e))]
                except Exception:
                    continue
                
                for ex in exams:
                    ex_path = os.path.join(vd_path, ex)
                    
                    # 生成去重key
                    dedup_key = (pf, vd, ex)
                    
                    # 检查是否已存在
                    if dedup_key in seen_keys:
                        duplicates += 1
                        continue
                    
                    seen_keys.add(dedup_key)
                    
                    try:
                        txts = [f for f in os.listdir(ex_path) if f.lower().endswith(".txt")]
                    except Exception:
                        txts = []
                    
                    major, sub, eye = classify_exam(ex)
                    txts_sorted = sorted(txts)
                    txt_cont = [read_text_file_with_best_effort(os.path.join(ex_path, f)) for f in txts_sorted]
                    padded = (txt_cont + [""] * 4)[:4]
                    
                    records.append(
                        ExamRecord(
                            diagnosis="",
                            detect_dir=ex_path,
                            patient_folder=pf,
                            patient_i_name=parse_patient_name_from_folder(pf),
                            visit_date=vd,
                            detect_ty=ex,
                            major_category=major,
                            sub_category=sub,
                            eye_type=eye,
                            txt_count=len(txts_sorted),
                            txt_filenames=";".join(txts_sorted),
                            txt_1=padded[0],
                            txt_2=padded[1],
                            txt_3=padded[2],
                            txt_4=padded[3],
                            month_folder=month_folder,
                        )
                    )
                    month_records += 1
        
        print(f"新增 {month_records} 条, 去重 {duplicates} 条")
    
    return records, seen_keys


# ---------- 构造矩阵 ----------
OCT_SUBTYPES = [
    "海德堡OCT",
    "海德堡OCT 血流模式",
    "视微OCT",
    "视微OCT 血流模式",
    "科林OCT",
    "科林OCT 血流模式",
    "图湃OCT",
    "图湃OCT 血流模式",
    "蔡司OCT",
]

FUNDUS_SUBTYPES = [
    "激光广角眼底照相（蔡司真彩）",
    "激光广角眼底照相检查(欧堡)",
    "眼底照相",
]


def build_presence_matrix(records: List[ExamRecord]) -> pd.DataFrame:
    index_keys = sorted({(r.patient_folder, r.patient_i_name, r.visit_date) for r in records})

    def make_col(base: str) -> List[str]:
        return [f"{base}(单眼)", f"{base}(双眼)"]

    columns = (
        ["patient_folder", "patient_i_name", "visit_date"]
        + make_col("B超")
        + make_col("造影")
        + ["造影报告"]  # 新增：造影分析和诊断合并为一列
        + [f"{oct}(单眼)" for oct in OCT_SUBTYPES]
        + [f"{oct}(双眼)" for oct in OCT_SUBTYPES]
        + [f"{fund}(单眼)" for fund in FUNDUS_SUBTYPES]
        + [f"{fund}(双眼)" for fund in FUNDUS_SUBTYPES]
    )

    rows = []
    zero = {c: 0 if c not in ["造影报告"] else "" for c in columns}
    for pf, pn, vd in index_keys:
        row = zero.copy()
        row.update({"patient_folder": pf, "patient_i_name": pn, "visit_date": vd})
        rows.append(row)
    key_to_row = {(r["patient_folder"], r["patient_i_name"], r["visit_date"]): r for r in rows}

    # 用于收集同一患者同一就诊日期的所有造影报告
    ffa_reports = {}  # key: (patient_folder, patient_i_name, visit_date), value: list of reports
    
    for r in records:
        key = (r.patient_folder, r.patient_i_name, r.visit_date)
        row = key_to_row.get(key)
        if row is None:
            continue
        eye = r.eye_type or "双眼"  # 未标注默认算双眼
        if r.major_category == "B超":
            row[f"B超({eye})"] = 1
        elif r.major_category == "造影":
            row[f"造影({eye})"] = 1
            # 收集造影报告内容
            report_texts = []
            for txt in [r.txt_1, r.txt_2, r.txt_3, r.txt_4]:
                if txt.strip():
                    report_texts.append(txt.strip())
            if report_texts:
                if key not in ffa_reports:
                    ffa_reports[key] = []
                ffa_reports[key].extend(report_texts)
        elif r.major_category == "OCT" and r.sub_category in OCT_SUBTYPES:
            row[f"{r.sub_category}({eye})"] = 1
        elif r.major_category == "眼底拍照" and r.sub_category in FUNDUS_SUBTYPES:
            row[f"{r.sub_category}({eye})"] = 1
    
    # 填充造影报告列（多个txt用空行隔开）
    for key, reports in ffa_reports.items():
        row = key_to_row.get(key)
        if row is not None:
            row["造影报告"] = "\n\n".join(reports)  # 用双换行符隔开不同的txt

    return (
        pd.DataFrame(rows, columns=columns)
        .sort_values(["patient_folder", "visit_date"])
        .reset_index(drop=True)
    )


# ---------- 导出 ----------
def export_to_excel(df: pd.DataFrame, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False)


# ---------- CLI ----------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export exam presence matrix by year (去重)")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="Root directory to scan")
    parser.add_argument("--out_dir", default=MATRIX_OUT_DIR, help="Output directory for Excel files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    print("="*70)
    print("按年份统计检查数据（合并月份，自动去重）")
    print("="*70)
    print()
    
    # 循环处理每个年份
    for year in YEARS:
        year_path = os.path.join(args.root, year)
        
        # 检查目录是否存在
        if not os.path.isdir(year_path):
            print(f"⚠️  跳过 {year}: 目录不存在")
            print(f"   路径: {year_path}")
            print()
            continue
        
        print(f"正在处理: {year}年")
        print(f"  路径: {year_path}")
        
        # 收集数据（跨月份，自动去重）
        records, seen_keys = collect_exam_records_for_year(year_path)
        print(f"  总计: {len(records)} 条检查记录（已去重）")
        
        if len(records) == 0:
            print(f"  ⚠️  无数据，跳过")
            print()
            continue
        
        # 构建矩阵
        df_matrix = build_presence_matrix(records)
        
        # 生成输出文件名
        output_filename = f"{year}年度数据-单双眼.xlsx"
        output_path = os.path.join(args.out_dir, output_filename)
        
        # 导出
        export_to_excel(df_matrix, output_path)
        print(f"  ✓ 已保存: {output_path}")
        print(f"  患者-就诊数: {len(df_matrix)}")
        print()
    
    print("="*70)
    print("全部完成！")
    print("="*70)


if __name__ == "__main__":
    main()

