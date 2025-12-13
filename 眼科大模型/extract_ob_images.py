#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 DR 提取结果目录为每个病例补充欧宝图像：
1) 读取提取报告，解析每个病例对应的原始 OCT / FFA 路径
2) 根据病例文件夹名中的日期，在原始日期目录下搜索包含“欧宝/optos”关键字的文件夹
3) 复制其中的 jpg/jpeg/png 图像到病例目录下新建的“欧宝”文件夹（与 FFA、OCT 并列）

默认路径：
    提取报告: /data2/xuhanyang/dataset/截图文件汇总/DR病例图像提取/提取报告.txt
    目标目录: /data2/xuhanyang/dataset/海德堡DR病例图像提取
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple

# 默认：使用“截图文件汇总/DR病例图像提取”这批病例
REPORT_PATH = Path("/data2/xuhanyang/dataset/截图文件汇总/DR病例图像提取/提取报告.txt")
TARGET_ROOT = Path("/data2/xuhanyang/dataset/截图文件汇总/DR病例图像提取")

# 关键词用于匹配欧宝目录（欧宝/欧堡/optos 等）
OB_KEYWORDS = ["欧宝", "欧堡", "optos"]
# 支持的图像扩展名
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def parse_report(report_path: Path) -> Dict[Tuple[str, str], Dict[str, List[Path]]]:
    """
    解析提取报告，返回映射： (姓名, 日期) -> {'oct': [Path...], 'ffa': [Path...]}
    """
    mapping: Dict[Tuple[str, str], Dict[str, List[Path]]] = {}
    if not report_path.exists():
        print(f"错误: 提取报告不存在: {report_path}")
        return mapping

    name_date_re = re.compile(r"^\s*\d+\.\s*(.+?)\s*-\s*(\d{4}-\d{2}-\d{2})")
    oct_re = re.compile(r"^\s*OCT路径:\s*(.+)")
    ffa_re = re.compile(r"^\s*FFA路径:\s*(.+)")

    current_key = None
    with report_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = name_date_re.match(line)
            if m:
                name = m.group(1).strip()
                date = m.group(2).strip()
                current_key = (name, date)
                if current_key not in mapping:
                    mapping[current_key] = {"oct": [], "ffa": []}
                continue

            if current_key is None:
                continue

            m_oct = oct_re.match(line)
            if m_oct:
                paths = [p.strip() for p in m_oct.group(1).split(",")]
                for p in paths:
                    if p:
                        mapping[current_key]["oct"].append(Path(p))
                continue

            m_ffa = ffa_re.match(line)
            if m_ffa:
                paths = [p.strip() for p in m_ffa.group(1).split(",")]
                for p in paths:
                    if p:
                        mapping[current_key]["ffa"].append(Path(p))
                continue

    return mapping


def parse_case_folder(folder_name: str) -> Tuple[str, str]:
    """
    从病例文件夹名提取 (姓名, 日期)
    例: '洪慕祥_双眼_2025-06-16' -> ('洪慕祥', '2025-06-16')
    """
    parts = folder_name.split("_")
    if len(parts) < 2:
        return folder_name, ""
    date = parts[-1]
    eye_tag = parts[-2] if len(parts) >= 2 else ""
    name_parts = parts[:-1]
    # 如果倒数第二段是眼别标签，去掉
    if eye_tag in ("双眼", "单眼", "右眼", "左眼"):
        name_parts = parts[:-2]
    name = "_".join(name_parts).strip("_")
    return name, date


def find_ob_folder(date_root: Path) -> Path:
    """
    在日期目录下寻找包含欧宝关键字的子目录，返回第一个命中路径；找不到返回 None
    """
    if not date_root.exists():
        return None
    for child in sorted(date_root.iterdir()):
        if child.is_dir():
            name_upper = child.name.lower()
            if any(k in name_upper for k in OB_KEYWORDS):
                return child
    return None


def collect_images(src_dir: Path) -> List[Path]:
    """收集目录下的所有图片文件（非递归）"""
    images = []
    if not src_dir or not src_dir.exists():
        return images
    for item in sorted(src_dir.iterdir()):
        if item.is_file() and item.suffix.lower() in IMG_EXTS:
            images.append(item)
    return images


def copy_images(images: List[Path], dst_dir: Path):
    """将图片复制到目标目录，避免重名覆盖"""
    dst_dir.mkdir(parents=True, exist_ok=True)
    for img in images:
        target = dst_dir / img.name
        counter = 1
        while target.exists():
            target = dst_dir / f"{img.stem}_{counter}{img.suffix}"
            counter += 1
        shutil.copy2(img, target)


def main():
    report_map = parse_report(REPORT_PATH)
    if not report_map:
        print("未能从报告解析到病例信息，退出。")
        return

    if not TARGET_ROOT.exists():
        print(f"目标目录不存在: {TARGET_ROOT}")
        return

    case_dirs = [d for d in TARGET_ROOT.iterdir() if d.is_dir()]
    print(f"共找到 {len(case_dirs)} 个病例目录，开始处理欧宝图像...")

    success = 0
    missing = 0
    for case_dir in sorted(case_dirs):
        name, date = parse_case_folder(case_dir.name)
        key = (name, date)
        ob_dst = case_dir / "欧宝"

        if key not in report_map:
            print(f"[跳过] {case_dir.name} 未在报告中找到匹配项")
            missing += 1
            continue

        paths_info = report_map[key]
        source_paths = paths_info.get("oct") or paths_info.get("ffa") or []
        if not source_paths:
            print(f"[跳过] {case_dir.name} 在报告中无 OCT/FFA 路径")
            missing += 1
            continue

        # 取第一条路径的日期目录
        date_root = source_paths[0].parent if source_paths else None
        if not date_root or not date_root.exists():
            print(f"[跳过] {case_dir.name} 源日期目录不存在: {date_root}")
            missing += 1
            continue

        ob_folder = find_ob_folder(date_root)
        if not ob_folder:
            print(f"[无欧宝] {case_dir.name} 在 {date_root} 下未找到欧宝目录")
            missing += 1
            continue

        images = collect_images(ob_folder)
        if not images:
            print(f"[无图像] {case_dir.name} 欧宝目录中未发现图片: {ob_folder}")
            missing += 1
            continue

        copy_images(images, ob_dst)
        print(f"[完成] {case_dir.name} 复制 {len(images)} 张至 {ob_dst}")
        success += 1

    print(f"\n处理完成: 成功 {success} 个，缺失/无图 {missing} 个，共 {len(case_dirs)} 个病例。")


if __name__ == "__main__":
    main()


