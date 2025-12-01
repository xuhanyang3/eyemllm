#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
压缩数据集文件夹工具
支持单文件压缩或分割成多个小于指定大小的压缩包
"""

import os
import sys
import tarfile
from pathlib import Path
from argparse import ArgumentParser


def get_dir_size(path):
    """计算目录总大小（字节）"""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total += os.path.getsize(filepath)
    return total


def compress_single(source_dir, output_file):
    """压缩整个文件夹为单个tar.gz文件"""
    print(f"正在压缩 {source_dir} 到 {output_file}...")
    with tarfile.open(output_file, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))
    size_mb = os.path.getsize(output_file) / (1024 * 1024)
    print(f"✓ 压缩完成: {output_file} ({size_mb:.2f} MB)")


def compress_split(source_dir, output_dir, max_size_gb=1.0):
    """将文件夹分割压缩成多个小于指定大小的tar.gz文件"""
    max_size_bytes = max_size_gb * 1024 * 1024 * 1024
    
    # 获取所有文件和子目录
    all_items = []
    source_path = Path(source_dir)
    base_name = source_path.name
    
    # 收集所有文件
    for root, dirs, files in os.walk(source_dir):
        for file in files:
            file_path = Path(root) / file
            rel_path = file_path.relative_to(source_dir)
            file_size = file_path.stat().st_size
            all_items.append((file_path, rel_path, file_size))
    
    # 按子目录分组（保持目录结构）
    items_by_subdir = {}
    for file_path, rel_path, file_size in all_items:
        # 获取第一级子目录（相对于source_dir）
        parts = rel_path.parts
        if len(parts) > 1:
            subdir = parts[0]
        else:
            subdir = "root"
        
        if subdir not in items_by_subdir:
            items_by_subdir[subdir] = []
        items_by_subdir[subdir].append((file_path, rel_path, file_size))
    
    # 计算每个子目录的大小
    subdir_sizes = {}
    for subdir, items in items_by_subdir.items():
        subdir_sizes[subdir] = sum(size for _, _, size in items)
    
    # 按大小排序子目录
    sorted_subdirs = sorted(subdir_sizes.items(), key=lambda x: x[1], reverse=True)
    
    # 分组到压缩包中
    current_group = []
    current_size = 0
    archive_num = 1
    
    for subdir, subdir_size in sorted_subdirs:
        if subdir_size > max_size_bytes:
            # 如果单个子目录就超过限制，需要进一步分割
            print(f"警告: 子目录 {subdir} 大小 ({subdir_size / (1024**3):.2f} GB) 超过限制，将单独压缩")
            output_file = output_dir / f"{base_name}_part{archive_num:03d}.tar.gz"
            with tarfile.open(output_file, "w:gz") as tar:
                for file_path, rel_path, _ in items_by_subdir[subdir]:
                    tar.add(file_path, arcname=str(Path(base_name) / rel_path))
            size_mb = os.path.getsize(output_file) / (1024 * 1024)
            print(f"✓ 压缩完成: {output_file.name} ({size_mb:.2f} MB)")
            archive_num += 1
        else:
            # 尝试添加到当前组
            if current_size + subdir_size <= max_size_bytes:
                current_group.append(subdir)
                current_size += subdir_size
            else:
                # 保存当前组
                if current_group:
                    output_file = output_dir / f"{base_name}_part{archive_num:03d}.tar.gz"
                    with tarfile.open(output_file, "w:gz") as tar:
                        for subdir_name in current_group:
                            for file_path, rel_path, _ in items_by_subdir[subdir_name]:
                                tar.add(file_path, arcname=str(Path(base_name) / rel_path))
                    size_mb = os.path.getsize(output_file) / (1024 * 1024)
                    print(f"✓ 压缩完成: {output_file.name} ({size_mb:.2f} MB)")
                    archive_num += 1
                
                # 开始新组
                current_group = [subdir]
                current_size = subdir_size
    
    # 保存最后一组
    if current_group:
        output_file = output_dir / f"{base_name}_part{archive_num:03d}.tar.gz"
        with tarfile.open(output_file, "w:gz") as tar:
            for subdir_name in current_group:
                for file_path, rel_path, _ in items_by_subdir[subdir_name]:
                    tar.add(file_path, arcname=str(Path(base_name) / rel_path))
        size_mb = os.path.getsize(output_file) / (1024 * 1024)
        print(f"✓ 压缩完成: {output_file.name} ({size_mb:.2f} MB)")


def main():
    parser = ArgumentParser(description="压缩数据集文件夹工具")
    parser.add_argument('source_dir', type=str,
                        help='要压缩的源目录')
    parser.add_argument('--output_dir', type=str, default="/data2/xuhanyang/dataset/dr压缩包",
                        help='输出压缩包的目录（默认为dr压缩包文件夹）')
    parser.add_argument('--max_size_gb', type=float, default=1.0,
                        help='每个压缩包的最大大小（GB），默认为1.0。如果源目录压缩后小于此值，则生成单个压缩包')
    parser.add_argument('--force_split', action='store_true',
                        help='强制分割成多个压缩包，即使总大小小于限制')
    
    args = parser.parse_args()
    
    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        print(f"错误: 源目录不存在 - {source_dir}")
        return
    
    # 确定输出目录
    output_dir = Path(args.output_dir)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 计算源目录大小
    print(f"正在计算目录大小...")
    source_size = get_dir_size(source_dir)
    source_size_gb = source_size / (1024 ** 3)
    print(f"源目录大小: {source_size_gb:.2f} GB")
    
    # 决定压缩方式
    base_name = source_dir.name
    max_size_bytes = args.max_size_gb * 1024 * 1024 * 1024
    
    # 估算压缩后大小（通常压缩率在30-50%）
    estimated_compressed = source_size * 0.4
    
    if not args.force_split and estimated_compressed <= max_size_bytes:
        # 单个压缩包
        output_file = output_dir / f"{base_name}.tar.gz"
        compress_single(source_dir, output_file)
    else:
        # 分割压缩
        print(f"将分割成多个小于 {args.max_size_gb} GB 的压缩包...")
        compress_split(source_dir, output_dir, args.max_size_gb)
    
    print("\n压缩完成！")


if __name__ == "__main__":
    main()


