#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export presence matrix into an Excel file (单眼/双眼 分开统计).
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from typing import List

import pandas as pd

DEFAULT_ROOT = "/share/kongzitai/ophthalmology/E:"
MATRIX_OUT_DIR = "/data2/xuhanyang/眼科大模型"

# 要处理的疾病列表
DISEASES = [
    "2023-中心性浆液性脉络膜视网膜病变",
    "2023-年龄相关性黄斑变性",
    "2023-糖尿病性视网膜病变",
    "2023-视网膜静脉阻塞"
]


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


def parse_patient_name_from_folder(folder_basename: str) -> str:
    parts = folder_basename.split()
    return parts[1] if len(parts) >= 2 else ""


# ---------- 扫描目录 ----------
def collect_exam_records(root_dir: str) -> List[ExamRecord]:
    records: List[ExamRecord] = []
    if not os.path.isdir(root_dir):
        return records

    for pf in sorted(os.listdir(root_dir)):
        pf_path = os.path.join(root_dir, pf)
        if not os.path.isdir(pf_path):
            continue
        try:
            visits = [v for v in os.listdir(pf_path) if os.path.isdir(os.path.join(pf_path, v))]
        except Exception:
            continue
        for vd in sorted(visits):
            vd_path = os.path.join(pf_path, vd)
            try:
                exams = [e for e in os.listdir(vd_path) if os.path.isdir(os.path.join(vd_path, e))]
            except Exception:
                continue
            for ex in sorted(exams):
                ex_path = os.path.join(vd_path, ex)
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
                    )
                )
    return records


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
        + [f"{oct}(单眼)" for oct in OCT_SUBTYPES]
        + [f"{oct}(双眼)" for oct in OCT_SUBTYPES]
        + [f"{fund}(单眼)" for fund in FUNDUS_SUBTYPES]
        + [f"{fund}(双眼)" for fund in FUNDUS_SUBTYPES]
    )

    rows = []
    zero = {c: 0 for c in columns}
    for pf, pn, vd in index_keys:
        row = zero.copy()
        row.update({"patient_folder": pf, "patient_i_name": pn, "visit_date": vd})
        rows.append(row)
    key_to_row = {(r["patient_folder"], r["patient_i_name"], r["visit_date"]): r for r in rows}

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
        elif r.major_category == "OCT" and r.sub_category in OCT_SUBTYPES:
            row[f"{r.sub_category}({eye})"] = 1
        elif r.major_category == "眼底拍照" and r.sub_category in FUNDUS_SUBTYPES:
            row[f"{r.sub_category}({eye})"] = 1

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
    parser = argparse.ArgumentParser(description="Export exam presence matrix (单眼/双眼)")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="Root directory to scan")
    parser.add_argument("--out_dir", default=MATRIX_OUT_DIR, help="Output directory for Excel files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    
    print("="*70)
    print("批量处理多个疾病类别")
    print("="*70)
    print()
    
    # 循环处理每个疾病
    for disease in DISEASES:
        disease_path = os.path.join(args.root, disease)
        
        # 检查目录是否存在
        if not os.path.isdir(disease_path):
            print(f"⚠️  跳过 {disease}: 目录不存在")
            print(f"   路径: {disease_path}")
            print()
            continue
        
        print(f"正在处理: {disease}")
        print(f"  路径: {disease_path}")
        
        # 收集数据
        records = collect_exam_records(disease_path)
        print(f"  找到 {len(records)} 条检查记录")
        
        if len(records) == 0:
            print(f"  ⚠️  无数据，跳过")
            print()
            continue
        
        # 构建矩阵
        df_matrix = build_presence_matrix(records)
        
        # 生成输出文件名
        output_filename = f"{disease}-单双眼.xlsx"
        output_path = os.path.join(args.out_dir, output_filename)
        
        # 导出
        export_to_excel(df_matrix, output_path)
        print(f"  ✓ 已保存: {output_path}")
        print(f"  行数: {len(df_matrix)}")
        print()
    
    print("="*70)
    print("全部完成！")
    print("="*70)


if __name__ == "__main__":
    main()

#source /usr/share/anaconda3/etc/profile.d/conda.sh
#conda activate /data2/xuhanyang/venvs/oph-conda
#python /data2/xuhanyang/眼科大模型/ffa_export.py 
#中心性浆液性脉络膜视网膜病变  年龄相关性黄斑变性  糖尿病性视网膜病变  视网膜静脉阻塞