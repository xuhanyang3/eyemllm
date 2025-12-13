#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为 CSC 病例目录补充“欧宝/欧堡/optos”图像。

逻辑：
1) 读取 2023/2024/2025 的 CSC Excel（科林、视微两个 sheet），
   建立 (姓名, 日期) -> patient_folder 映射（patient_folder 含患者编号）。
2) 根据病例目录名的姓名与日期，在原始数据路径
   /share/kongzitai/ophthalmology/E:/<年>-中心性浆液性脉络膜视网膜病变
   下找到对应患者编号目录及日期目录，搜索包含欧宝关键字的子目录。
3) 复制其中的 JPG/PNG/BMP 等图片到病例目录下新建的“欧宝”文件夹。
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd

# 目标病例根目录（已有 OCT/FFA 的提取结果）
TARGET_ROOT = Path("/data2/xuhanyang/dataset/截图文件汇总/CSC病例图像提取")

# Excel 列表（含科林、视微两个 sheet）
EXCEL_FILES = [
    Path("/data2/xuhanyang/dataset/截图病例汇总/导出 2023-中心性浆液性脉络膜视网膜病变-单双眼.xlsx"),
    Path("/data2/xuhanyang/dataset/截图病例汇总/导出2024-中心性浆液性脉络膜视网膜病变-单双眼.xlsx"),
    Path("/data2/xuhanyang/dataset/截图病例汇总/导出2025-中心性浆液性脉络膜视网膜病变-new.xlsx"),
]
SHEETS = ["科林", "视微"]

OB_KEYWORDS = ["欧宝", "欧堡", "optos", "激光广角眼底照相", "广角"]
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


# ----------------- 工具函数 ----------------- #
def parse_case_folder(folder_name: str) -> Tuple[str, str]:
    """
    从病例目录名提取 (姓名, 日期)
    例: '石金林_双眼_2024-03-24' -> ('石金林', '2024-03-24')
    """
    parts = folder_name.split("_")
    if len(parts) < 2:
        return folder_name, ""
    date = parts[-1]
    eye_tag = parts[-2] if len(parts) >= 2 else ""
    name_parts = parts[:-1]
    if eye_tag in ("双眼", "单眼", "右眼", "左眼"):
        name_parts = parts[:-2]
    name = "_".join(name_parts).strip("_")
    return name, date


def parse_patient_folder(patient_folder: str) -> Tuple[Optional[str], Optional[str]]:
    """
    从 patient_folder 字符串解析出患者编号和姓名。
    例: '15918565 刘小勇 男 1982-11-06' -> ('15918565', '刘小勇')
    """
    parts = str(patient_folder).strip().split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None


def extract_date(text: str) -> Optional[str]:
    """从文本中提取 YYYY-MM-DD 格式日期"""
    if not isinstance(text, str):
        text = str(text)
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    return m.group(1) if m else None


def load_case_mapping() -> Dict[Tuple[str, str], str]:
    """
    读取 Excel，建立 (姓名, 日期) -> patient_folder 的映射。
    """
    mapping: Dict[Tuple[str, str], str] = {}
    candidate_cols = ["patient_folder", "患者文件夹", "患者信息", "患者", "患者编号"]
    date_cols = ["日期", "就诊日期", "visit_date", "VisitDate"]

    for excel_path in EXCEL_FILES:
        if not excel_path.exists():
            print(f"警告: Excel 不存在，跳过: {excel_path}")
            continue
        for sheet in SHEETS:
            try:
                df = pd.read_excel(excel_path, sheet_name=sheet, engine="openpyxl")
            except Exception as e:
                print(f"警告: 读取 {excel_path.name} sheet={sheet} 失败: {e}")
                continue

            # 找到 patient_folder 列
            pf_col = next((c for c in candidate_cols if c in df.columns), None)
            if pf_col is None:
                print(f"警告: {excel_path.name} sheet={sheet} 未找到患者列，跳过")
                continue

            # 找到日期列
            date_col = next((c for c in date_cols if c in df.columns), None)
            if date_col is None:
                print(f"警告: {excel_path.name} sheet={sheet} 未找到日期列，跳过")
                continue

            for _, row in df.iterrows():
                patient_folder = str(row.get(pf_col, "")).strip()
                visit_date = extract_date(str(row.get(date_col, "")))
                if not patient_folder or not visit_date:
                    continue
                _, name = parse_patient_folder(patient_folder)
                if not name:
                    continue
                key = (name, visit_date)
                # 只保留首个命中，后续同名同日忽略
                if key not in mapping:
                    mapping[key] = patient_folder

    return mapping


def find_ob_folder(patient_folder: str, visit_date: str) -> Optional[Path]:
    """
    在原始数据路径下定位欧宝目录。
    """
    patient_id, _ = parse_patient_folder(patient_folder)
    if not patient_id or not visit_date:
        return None
    year = visit_date[:4]
    base = Path(f"/share/kongzitai/ophthalmology/E:/{year}-中心性浆液性脉络膜视网膜病变")
    if not base.exists():
        return None

    patient_dirs = sorted(base.glob(f"{patient_id}*"))
    for pdir in patient_dirs:
        date_dir = pdir / visit_date
        if not date_dir.exists():
            continue
        try:
            for child in sorted(date_dir.iterdir()):
                if child.is_dir():
                    name_lower = child.name.lower()
                    if any(k in name_lower for k in [k.lower() for k in OB_KEYWORDS]):
                        return child
        except PermissionError:
            continue
    return None


def collect_images(src_dir: Path) -> List[Path]:
    images = []
    if not src_dir or not src_dir.exists():
        return images
    for item in sorted(src_dir.iterdir()):
        if item.is_file() and item.suffix.lower() in IMG_EXTS:
            images.append(item)
    return images


def copy_images(images: List[Path], dst_dir: Path) -> int:
    dst_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for img in images:
        target = dst_dir / img.name
        idx = 1
        while target.exists():
            target = dst_dir / f"{img.stem}_{idx}{img.suffix}"
            idx += 1
        shutil.copy2(img, target)
        count += 1
    return count


# ----------------- 主流程 ----------------- #
def main():
    mapping = load_case_mapping()
    if not mapping:
        print("未能从 Excel 建立映射，退出。")
        return

    if not TARGET_ROOT.exists():
        print(f"目标目录不存在: {TARGET_ROOT}")
        return

    case_dirs = [d for d in TARGET_ROOT.iterdir() if d.is_dir()]
    print(f"共找到 {len(case_dirs)} 个病例目录，开始补充欧宝图像...")

    success = 0
    missing = 0

    for case_dir in sorted(case_dirs):
        name, date = parse_case_folder(case_dir.name)
        key = (name, date)
        ob_dst = case_dir / "欧宝"

        if key not in mapping:
            print(f"[跳过] {case_dir.name} 无匹配的患者信息")
            missing += 1
            continue

        patient_folder = mapping[key]
        ob_src = find_ob_folder(patient_folder, date)
        if not ob_src:
            print(f"[无欧宝] {case_dir.name} 未找到欧宝目录 (patient={patient_folder}, date={date})")
            missing += 1
            continue

        images = collect_images(ob_src)
        if not images:
            print(f"[无图像] {case_dir.name} 欧宝目录为空: {ob_src}")
            missing += 1
            continue

        copied = copy_images(images, ob_dst)
        print(f"[完成] {case_dir.name} 复制 {copied} 张至 {ob_dst}")
        success += 1

    print(f"\n处理完成: 成功 {success} 个，缺失/无图 {missing} 个，共 {len(case_dirs)} 个病例。")


if __name__ == "__main__":
    main()

