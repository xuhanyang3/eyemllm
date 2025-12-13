#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从指定目录提取OCT图像
基于 extract_uv_images.py 修改而来，用于处理特定目录
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import fitz  # PyMuPDF
from PIL import Image
import io
import re

# 导入OCR和OCT提取功能
sys.path.append('/data2/xuhanyang/眼科大模型')
from extract_uv_images import (
    get_ocr_reader,
    detect_eye_from_oct_image,
    detect_eye_from_pdf_page,
    extract_oct_images_from_pdf
)


def find_oct_pdfs(input_dir):
    """
    在指定目录下查找所有OCT相关的PDF文件
    查找包含以下关键字的文件夹：科林、视微、海德堡、OCT
    """
    input_path = Path(input_dir)
    if not input_path.exists():
        print(f"错误: 输入目录不存在 - {input_dir}")
        return []
    
    oct_keywords = ['科林', '视微', '海德堡', 'OCT', 'Oct', 'oct']
    found_pdfs = []
    
    # 查找包含OCT关键字的文件夹
    for item in input_path.iterdir():
        if not item.is_dir():
            continue
        
        folder_name = item.name
        is_oct_folder = any(keyword in folder_name for keyword in oct_keywords)
        
        if is_oct_folder:
            # 在该文件夹下查找PDF文件
            pdfs = list(item.rglob('*.pdf')) + list(item.rglob('*.PDF'))
            if pdfs:
                found_pdfs.extend(pdfs)
                print(f"  找到OCT文件夹: {folder_name} ({len(pdfs)}个PDF)")
    
    # 如果没找到OCT文件夹，直接在输入目录下查找PDF
    if not found_pdfs:
        pdfs = list(input_path.rglob('*.pdf')) + list(input_path.rglob('*.PDF'))
        if pdfs:
            found_pdfs.extend(pdfs)
            print(f"  在根目录下找到 {len(pdfs)} 个PDF文件")
    
    return sorted(found_pdfs)


def extract_oct_from_directory(input_dir, output_dir):
    """
    从指定目录提取OCT图像到输出目录
    
    Args:
        input_dir: 输入目录路径
        output_dir: 输出目录路径
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    print("="*70)
    print("OCT图像提取工具 - 指定目录模式")
    print("="*70)
    print(f"输入目录: {input_path}")
    print(f"输出目录: {output_path}")
    print("="*70)
    print()
    
    if not input_path.exists():
        print(f"错误: 输入目录不存在 - {input_path}")
        return
    
    # 创建输出目录
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 查找所有OCT PDF文件
    print("正在查找OCT PDF文件...")
    oct_pdfs = find_oct_pdfs(input_path)
    
    if not oct_pdfs:
        print("未找到任何OCT PDF文件")
        return
    
    print(f"\n找到 {len(oct_pdfs)} 个PDF文件，开始提取...\n")
    
    # 提取图像
    total_images = 0
    image_counter = 1
    
    for pdf_idx, pdf_path in enumerate(oct_pdfs, 1):
        print(f"[{pdf_idx}/{len(oct_pdfs)}] 处理: {pdf_path.name}")
        
        # 确定文件夹前缀（如果有多个OCT文件夹）
        folder_prefix = ""
        parent_folder = pdf_path.parent.name
        if "血流" in parent_folder:
            folder_prefix = "血流模式"
        elif "OCTA" in parent_folder or "Angio" in parent_folder.lower():
            folder_prefix = "OCTA"
        
        # 提取图像（OCR reader会在第一次调用时自动初始化）
        num_images = extract_oct_images_from_pdf(
            pdf_path,
            output_path,
            start_index=image_counter,
            folder_prefix=folder_prefix,
            use_gpu_ocr=False,
            pdf_index=pdf_idx
        )
        
        if num_images > 0:
            total_images += num_images
            image_counter += num_images
            print(f"  ✓ 提取 {num_images} 张图像")
        else:
            print(f"  ✗ 未提取到图像")
        print()
    
    print("="*70)
    print("提取完成")
    print("="*70)
    print(f"处理PDF文件数: {len(oct_pdfs)}")
    print(f"提取图像总数: {total_images} 张")
    print(f"输出目录: {output_path}")
    print("="*70)


def main():
    """主函数"""
    # 强制使用CPU模式（避免GPU内存问题）
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    
    # 指定的输入和输出路径
    input_dir = "/share/kongzitai/ophthalmology/E:/2021/9--10/13656545 王永华 男 1965-06-18/2021-09-27"
    output_dir = "/data2/xuhanyang/dataset/文件汇总（筛选后）/葡萄膜炎病例图像提取 1已改/王永华_双眼_2021-09-20（少左眼OCT)/OCT1"
    
    extract_oct_from_directory(input_dir, output_dir)


if __name__ == '__main__':
    main()

