#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从葡萄膜炎病例 Excel (科林/视微) 中补充欧宝/欧堡/optos 图像。

输入：
- Excel: /data2/xuhanyang/dataset/截图病例汇总/葡萄膜炎除重后名单（全）11.23(2).xlsx
  sheet: “科林” 与 “视微”
- 关键列（尽量兼容现有表头）：
    patient_name, patient_id, patient_folder, patient_path, visit_date, optos_date

路径查找（与 extract_uv_images 的查找方式一致）：
- 基础路径: /share/kongzitai/ophthalmology/E:/<year>
- 月份子目录命名可能为 "1"、"2"、"3"、"123"、"1-3" 等，优先用 optos_date 的月份匹配，其次遍历所有月份。
- 患者目录: <month_dir>/<patient_id>*   （patient_id 来自 patient_path 末段或 patient_id 列）
- 日期目录: <patient_dir>/<optos_date>
- 欧宝目录: 日期目录下名称包含任一关键字 ["欧宝", "欧堡", "optos", "激光广角眼底照相", "广角"]

输出：
- /data2/xuhanyang/dataset/截图文件汇总/葡萄膜炎病例图像提取/<姓名>_<patient_folder>_<visit_date>/欧宝
  （重名文件自动加后缀 _1, _2, ...）
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

EXCEL_PATH = Path("/data2/xuhanyang/dataset/截图病例汇总/葡萄膜炎除重后名单（全）11.23(2).xlsx")
SHEETS = ["科林", "视微"]
OUTPUT_BASE = Path("/data2/xuhanyang/dataset/截图文件汇总/葡萄膜炎病例图像提取")

OB_KEYWORDS = ["欧宝", "欧堡", "optos", "激光广角眼底照相", "广角"]
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


def parse_patient_folder(patient_folder: str) -> Tuple[Optional[str], Optional[str]]:
    """从 patient_folder 字符串解析患者编号与姓名。例: '02036873 陈康炎 男 1973-11-11'"""
    parts = str(patient_folder).strip().split()
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None


def parse_visit_date(date_str: str) -> Tuple[Optional[str], str]:
    """提取 YYYY-MM-DD 以及眼别标签（单眼/双眼/右眼/左眼）"""
    if not isinstance(date_str, str):
        date_str = str(date_str)
    eye_tag = "双眼" if "双眼" in date_str else ("单眼" if "单眼" in date_str else ("右眼" if "右眼" in date_str else ("左眼" if "左眼" in date_str else "")))
    m = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
    return (m.group(1) if m else None), eye_tag


def month_matches(folder_name: str, target_month: Optional[int]) -> bool:
    """匹配月份子目录名称（支持 '1', '123', '1-3', '10-12' 等）"""
    if target_month is None:
        return True
    name = folder_name
    if name == str(target_month):
        return True
    if name.isdigit() and str(target_month) in name:
        return True
    if "-" in name or "--" in name:
        parts = re.split(r"-+", name)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            start_m, end_m = int(parts[0]), int(parts[1])
            if start_m <= end_m:
                return start_m <= target_month <= end_m
            return target_month >= start_m or target_month <= end_m
    return False


def find_optos_folder(patient_id: str, optos_date: str) -> Optional[Path]:
    """在原始路径中定位欧宝目录"""
    if not patient_id or not optos_date:
        return None
    year = optos_date[:4]
    base_root = Path(f"/share/kongzitai/ophthalmology/E:/{year}")
    if not base_root.exists():
        return None

    # 目标月份
    try:
        from datetime import datetime as _dt
        target_month = _dt.strptime(optos_date, "%Y-%m-%d").month
    except Exception:
        target_month = None

    # 收集月份目录并排序：先匹配月份，再其它
    month_dirs = []
    try:
        month_dirs = [d for d in base_root.iterdir() if d.is_dir()]
    except PermissionError:
        return None

    ordered_months: List[Path] = []
    if target_month:
        for mdir in month_dirs:
            if month_matches(mdir.name, target_month):
                ordered_months.append(mdir)
        for mdir in month_dirs:
            if mdir not in ordered_months:
                ordered_months.append(mdir)
    else:
        ordered_months = month_dirs

    for mdir in ordered_months:
        patient_dirs = list(mdir.glob(f"{patient_id}*"))
        for pdir in patient_dirs:
            date_dir = pdir / optos_date
            if not date_dir.exists():
                continue
            try:
                for child in date_dir.iterdir():
                    if child.is_dir():
                        name_lower = child.name.lower()
                        if any(k in name_lower for k in [k.lower() for k in OB_KEYWORDS]):
                            return child
            except PermissionError:
                continue
    return None


def collect_images(src_dir: Path) -> List[Path]:
    if not src_dir or not src_dir.exists():
        return []
    imgs = []
    for item in sorted(src_dir.iterdir()):
        if item.is_file() and item.suffix.lower() in IMG_EXTS:
            imgs.append(item)
    return imgs


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


def build_case_folder_name(patient_name: str, patient_folder: str, visit_date: Optional[str]) -> str:
    eye_part = patient_folder or ""
    eye_part = re.sub(r'[<>:"/\\\\|?*]', '_', eye_part).strip()
    return f"{patient_name}_{eye_part}_{visit_date or 'unknown'}"


def load_rows() -> List[Dict]:
    rows: List[Dict] = []
    if not EXCEL_PATH.exists():
        print(f"错误: Excel 不存在 - {EXCEL_PATH}")
        return rows
    for sheet in SHEETS:
        try:
            df = pd.read_excel(EXCEL_PATH, sheet_name=sheet, engine="openpyxl")
        except Exception as e:
            print(f"警告: 读取 {sheet} 失败: {e}")
            continue
        for _, row in df.iterrows():
            rows.append(row.to_dict())
    return rows


def process_row(row: Dict) -> Tuple[str, Optional[str]]:
    """
    返回 (病例目录名, 错误信息或 None)；成功则错误为 None
    """
    patient_name = str(row.get("patient_name", "")).strip()
    patient_folder = str(row.get("patient_folder", "")).strip()
    visit_date_raw = str(row.get("visit_date", "")).strip()
    optos_date_raw = str(row.get("optos_date", "")).strip()
    patient_path = row.get("patient_path", None)
    patient_id_col = str(row.get("patient_id", "")).strip()

    visit_date, eye_type = parse_visit_date(visit_date_raw)
    optos_date, _ = parse_visit_date(optos_date_raw)

    if not patient_name:
        return "", "缺少患者姓名"
    if not optos_date:
        return "", "缺少 optos_date"

    # patient_id 优先从 patient_path 解析
    patient_id = None
    if isinstance(patient_path, str) and patient_path:
        last_part = Path(patient_path).name
        patient_id, _ = parse_patient_folder(last_part)
    if not patient_id and patient_id_col:
        patient_id = patient_id_col
    if not patient_id:
        return "", "缺少患者编号"

    case_folder = build_case_folder_name(patient_name, patient_folder, visit_date or optos_date)
    case_dir = OUTPUT_BASE / case_folder
    ob_dir = case_dir / "欧宝"

    # 查找欧宝源目录
    ob_src = find_optos_folder(patient_id, optos_date)
    if not ob_src:
        return case_folder, "未找到欧宝目录"

    images = collect_images(ob_src)
    if not images:
        return case_folder, "欧宝目录中无图像"

    copied = copy_images(images, ob_dir)
    return case_folder, None if copied > 0 else "复制失败"


def main():
    rows = load_rows()
    if not rows:
        return
    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    success = 0
    skipped = 0
    errors: List[str] = []

    print(f"共加载 {len(rows)} 条记录，开始提取欧宝图像...")
    for idx, row in enumerate(rows, 1):
        case_name, err = process_row(row)
        if err:
            print(f"[跳过] {case_name or '未知病例'} -> {err}")
            skipped += 1
            errors.append(f"{case_name or '未知病例'}: {err}")
        else:
            print(f"[完成] {case_name} 欧宝复制完成")
            success += 1

    print(f"\n处理完成：成功 {success}，失败/缺失 {skipped}")
    if errors:
        print("问题列表：")
        for e in errors:
            print(f" - {e}")


if __name__ == "__main__":
    main()


