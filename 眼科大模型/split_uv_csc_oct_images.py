#!/usr/bin/env python3
"""
批量处理UV_CSC找不到名单图像提取中的OCT图像，只保留右侧非正方形部分
"""

import os
import cv2
import numpy as np
import argparse
from pathlib import Path

def split_oct_image(img_path):
    """
    分割OCT图像，只保留右侧非正方形部分，直接替换原文件
    
    参数:
        img_path: 图像路径（将直接覆盖）
        
    返回:
        success: 是否成功处理
        msg: 处理结果消息
        skipped: 是否被跳过（宽度不大于高度两倍）
    """
    try:
        # 读取图像
        img = cv2.imread(img_path)
        if img is None:
            return False, f"无法读取图像: {img_path}", False
            
        height, width = img.shape[:2]
        
        # 检查图像是否需要分割（宽度应大于高度的两倍）
        if width <= height * 2:
            return False, f"图像被跳过（宽度{width}不大于高度{height}的两倍）: {os.path.basename(img_path)}", True
        
        # 计算分割点（左侧正方形部分的宽度等于高度）
        split_point = height
        
        # 提取右侧部分（从split_point到图像末尾）
        right_part = img[:, split_point:width]
        
        # 直接覆盖原文件
        cv2.imwrite(img_path, right_part)
        
        return True, f"成功处理: {os.path.basename(img_path)}", False
        
    except Exception as e:
        return False, f"处理图像时出错: {str(e)}", False

def process_oct_images(input_root_dir, dry_run=False):
    """
    批量处理OCT图像，直接在原目录下替换
    
    参数:
        input_root_dir: 输入根目录
        dry_run: 是否只显示将要处理的文件而不实际处理
        
    返回:
        stats: 处理统计信息
    """
    stats = {
        "total_cases": 0,
        "processed_cases": 0,
        "total_images": 0,
        "processed_images": 0,
        "skipped_images": 0,
        "failed_images": 0,
        "errors": [],
        "skipped_files": []  # 记录被跳过的文件
    }
    
    # 遍历所有患者文件夹
    for patient_dir in os.listdir(input_root_dir):
        patient_path = os.path.join(input_root_dir, patient_dir)
        
        # 跳过非目录文件
        if not os.path.isdir(patient_path):
            continue
            
        # 检查是否有OCT子目录
        oct_dir = os.path.join(patient_path, "OCT")
        if not os.path.exists(oct_dir):
            continue
            
        stats["total_cases"] += 1
        
        # 处理OCT图像
        oct_images = [f for f in os.listdir(oct_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if not oct_images:
            continue
            
        stats["processed_cases"] += 1
        stats["total_images"] += len(oct_images)
        
        print(f"\n处理患者: {patient_dir} ({len(oct_images)} 张OCT图像)")
        
        for img_file in oct_images:
            img_path = os.path.join(oct_dir, img_file)
            
            if dry_run:
                # 在dry_run模式下，我们无法检查图像尺寸，所以假设所有图像都会被处理
                print(f"  将处理: {img_file}")
                stats["processed_images"] += 1
                continue
                
            success, msg, skipped = split_oct_image(img_path)
            
            if success:
                print(f"  ✓ {msg}")
                stats["processed_images"] += 1
            elif skipped:
                print(f"  - {msg}")
                stats["skipped_images"] += 1
                # 记录被跳过的文件
                stats["skipped_files"].append({
                    "patient": patient_dir,
                    "file": img_file,
                    "path": img_path,
                    "reason": msg
                })
            else:
                print(f"  ✗ {msg}")
                stats["failed_images"] += 1
                stats["errors"].append(msg)
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="批量处理UV_CSC找不到名单图像提取中的OCT图像，只保留右侧非正方形部分（直接替换原文件）")
    parser.add_argument("--input", "-i", default="/data2/xuhanyang/dataset/UV_CSC找不到名单图像提取",
                        help="输入目录路径（将直接在此目录下修改OCT图像）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只显示将要处理的文件而不实际处理")
    
    args = parser.parse_args()
    
    # 确保输入目录存在
    if not os.path.exists(args.input):
        print(f"错误: 输入目录不存在: {args.input}")
        return 1
    
    # 处理OCT图像
    print(f"开始处理OCT图像...")
    print(f"处理目录: {args.input}")
    print(f"模式: {'预览模式（不实际修改）' if args.dry_run else '直接替换原文件'}")
    print("="*70)
    
    stats = process_oct_images(args.input, args.dry_run)
    
    # 打印统计信息
    print("\n" + "="*70)
    print("处理统计:")
    print("="*70)
    print(f"  总患者数: {stats['total_cases']}")
    print(f"  有OCT图像的患者数: {stats['processed_cases']}")
    print(f"  总OCT图像数: {stats['total_images']}")
    print(f"  成功处理的图像数: {stats['processed_images']}")
    print(f"  跳过的图像数: {stats['skipped_images']}")
    print(f"  处理失败的图像数: {stats['failed_images']}")
    
    # 显示被跳过的文件
    if stats['skipped_files'] and not args.dry_run:
        print("\n被跳过的图像（宽度不大于高度两倍）:")
        for skipped in stats['skipped_files']:
            print(f"  - 患者: {skipped['patient']}, 文件: {skipped['file']}")
            print(f"    原因: {skipped['reason']}")
    
    if stats['errors'] and not args.dry_run:
        print("\n错误详情:")
        for error in stats['errors'][:10]:  # 只显示前10个错误
            print(f"  - {error}")
        if len(stats['errors']) > 10:
            print(f"  ... 还有 {len(stats['errors']) - 10} 个错误")
    
    # 将被跳过的文件列表保存到文件中
    if stats['skipped_files'] and not args.dry_run:
        skipped_files_path = os.path.join(args.input, "skipped_files.txt")
        with open(skipped_files_path, 'w', encoding='utf-8') as f:
            f.write("被跳过的图像文件列表（宽度不大于高度两倍）:\n\n")
            for skipped in stats['skipped_files']:
                f.write(f"患者: {skipped['patient']}\n")
                f.write(f"文件: {skipped['file']}\n")
                f.write(f"路径: {skipped['path']}\n")
                f.write(f"原因: {skipped['reason']}\n\n")
        print(f"\n被跳过的文件列表已保存到: {skipped_files_path}")
    
    return 0

if __name__ == "__main__":
    exit(main())