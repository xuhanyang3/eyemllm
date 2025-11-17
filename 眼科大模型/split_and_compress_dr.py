#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将DR病例图像提取文件夹分成多个部分进行压缩，每个压缩包小于1GB
"""

import os
import subprocess
from pathlib import Path
from collections import defaultdict

def get_folder_size(folder_path):
    """获取文件夹大小（字节）"""
    total = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            try:
                total += os.path.getsize(filepath)
            except OSError:
                pass
    return total

def split_and_compress(source_dir, output_dir, max_size_gb=1.0):
    """
    将源目录分成多个部分并压缩
    
    Args:
        source_dir: 源目录路径
        output_dir: 输出目录路径
        max_size_gb: 每个压缩包最大大小（GB）
    """
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    max_size_bytes = max_size_gb * 1024 * 1024 * 1024  # 转换为字节
    
    # 获取所有病例文件夹
    case_folders = sorted([d for d in source_dir.iterdir() if d.is_dir()])
    
    print(f"找到 {len(case_folders)} 个病例文件夹")
    print(f"目标：每个压缩包小于 {max_size_gb}GB")
    print("="*70)
    
    # 计算每个文件夹的大小
    print("\n正在计算文件夹大小...")
    folder_sizes = {}
    for folder in case_folders:
        size = get_folder_size(folder)
        folder_sizes[folder] = size
        print(f"  {folder.name}: {size / (1024*1024):.2f} MB")
    
    # 分组：贪心算法，尽量填满每个组
    groups = []
    current_group = []
    current_size = 0
    
    for folder in case_folders:
        folder_size = folder_sizes[folder]
        
        # 如果单个文件夹就超过限制，单独成组
        if folder_size > max_size_bytes:
            if current_group:
                groups.append(current_group)
                current_group = []
                current_size = 0
            groups.append([folder])
            print(f"\n警告: {folder.name} 大小 {folder_size/(1024*1024*1024):.2f}GB 超过限制，单独压缩")
            continue
        
        # 如果加入当前组会超过限制，开始新组
        if current_size + folder_size > max_size_bytes and current_group:
            groups.append(current_group)
            current_group = [folder]
            current_size = folder_size
        else:
            current_group.append(folder)
            current_size += folder_size
    
    if current_group:
        groups.append(current_group)
    
    print(f"\n分成 {len(groups)} 个压缩包")
    print("="*70)
    
    # 压缩每个组
    for idx, group in enumerate(groups, 1):
        group_size_mb = sum(folder_sizes[f] for f in group) / (1024 * 1024)
        print(f"\n[{idx}/{len(groups)}] 压缩组 {idx} ({len(group)} 个文件夹, {group_size_mb:.2f} MB)")
        
        # 压缩：直接压缩，不复制文件
        archive_name = f"DR病例图像提取_part{idx:02d}.tar.gz"
        archive_path = output_dir / archive_name
        
        print(f"  压缩到: {archive_path}")
        
        # 构建tar命令，包含所有文件夹的相对路径
        folder_names = [f.name for f in group]
        cmd = [
            'tar', '-czf', str(archive_path),
            '-C', str(source_dir)
        ] + folder_names
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  错误: {result.stderr}")
        else:
            archive_size = archive_path.stat().st_size / (1024 * 1024 * 1024)
            print(f"  ✓ 完成: {archive_size:.2f} GB")
    
    print("\n" + "="*70)
    print("全部完成！")
    print("="*70)
    
    # 显示所有压缩包信息
    print("\n生成的压缩包:")
    for idx in range(1, len(groups) + 1):
        archive_name = f"DR病例图像提取_part{idx:02d}.tar.gz"
        archive_path = output_dir / archive_name
        if archive_path.exists():
            size_gb = archive_path.stat().st_size / (1024 * 1024 * 1024)
            print(f"  {archive_name}: {size_gb:.2f} GB")

if __name__ == '__main__':
    import sys
    if len(sys.argv) == 3:
        # 命令行指定源目录和输出目录
        source_dir = Path(sys.argv[1])
        output_dir = Path(sys.argv[2])
    else:
        # 默认CSC代码
        source_dir = Path('/data2/xuhanyang/dataset/DR病例图像提取')
        output_dir = Path('/data2/xuhanyang/dataset/DR病例图像提取_压缩包')

    split_and_compress(source_dir, output_dir, max_size_gb=1.0)

