#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
删除非标准规格（非768x496和1264x496）的OCT图像
"""

from pathlib import Path
from PIL import Image
from tqdm import tqdm
import argparse

def remove_nonstandard_oct(base_dir, target_sizes=[(768, 496), (1264, 496)], dry_run=False):
    """删除非标准规格的OCT图像"""
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"错误: 目录不存在 - {base_dir}")
        return {}
    
    # 统计信息
    stats = {
        'total_images': 0,
        'kept_images': 0,
        'removed_images': 0,
        'removed_files': []
    }
    
    # 支持的图像格式
    image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', 
                  '.JPG', '.JPEG', '.PNG', '.BMP', '.TIF', '.TIFF'}
    
    case_folders = sorted([d for d in base_path.iterdir() if d.is_dir() and not d.name.startswith('.')])
    
    print(f"正在检查 {len(case_folders)} 个病例文件夹...")
    print(f"目标规格: {target_sizes}")
    print(f"模式: {'预览模式（不实际删除）' if dry_run else '删除模式'}")
    print("="*70)
    
    for case_folder in tqdm(case_folders, desc="处理病例"):
        oct_dir = case_folder / 'OCT'
        
        if not oct_dir.exists():
            continue
        
        # 遍历OCT文件夹中的所有图像
        for img_file in oct_dir.iterdir():
            if img_file.is_file() and img_file.suffix in image_exts:
                stats['total_images'] += 1
                try:
                    img = Image.open(img_file)
                    size = img.size  # (width, height)
                    
                    if size in target_sizes:
                        stats['kept_images'] += 1
                    else:
                        stats['removed_images'] += 1
                        stats['removed_files'].append({
                            'case': case_folder.name,
                            'file': img_file.name,
                            'path': str(img_file),
                            'size': f"{size[0]}x{size[1]}"
                        })
                        
                        if not dry_run:
                            img_file.unlink()
                            print(f"  删除: {case_folder.name}/OCT/{img_file.name} (规格: {size[0]}x{size[1]})")
                except Exception as e:
                    print(f"  警告: 无法读取 {img_file.name} - {e}")
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="删除非标准规格（非768x496和1264x496）的OCT图像")
    parser.add_argument("--input", "-i", default="/data2/xuhanyang/dataset/海德堡葡萄膜炎图像提取",
                        help="输入目录路径")
    parser.add_argument("--dry-run", action="store_true",
                        help="预览模式，不实际删除文件")
    
    args = parser.parse_args()
    
    # 目标规格
    target_sizes = [(768, 496), (1264, 496)]
    
    stats = remove_nonstandard_oct(args.input, target_sizes, args.dry_run)
    
    # 打印统计信息
    print("\n" + "="*70)
    print("处理统计:")
    print("="*70)
    print(f"总图像数: {stats['total_images']} 张")
    print(f"保留图像数: {stats['kept_images']} 张")
    print(f"{'将删除' if args.dry_run else '已删除'}图像数: {stats['removed_images']} 张")
    
    if stats['removed_files']:
        print(f"\n{'将删除' if args.dry_run else '已删除'}的图像列表:")
        print("-"*70)
        for item in stats['removed_files']:
            print(f"  {item['case']}/OCT/{item['file']} (规格: {item['size']})")
        
        # 保存到文件
        report_path = Path(args.input) / "删除的非标准OCT图像报告.txt"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("="*70 + "\n")
            f.write("删除的非标准OCT图像报告\n")
            f.write("="*70 + "\n\n")
            f.write(f"目标规格: {target_sizes}\n")
            f.write(f"总图像数: {stats['total_images']} 张\n")
            f.write(f"保留图像数: {stats['kept_images']} 张\n")
            f.write(f"删除图像数: {stats['removed_images']} 张\n\n")
            f.write("删除的图像列表:\n")
            f.write("-"*70 + "\n")
            for item in stats['removed_files']:
                f.write(f"{item['path']} (规格: {item['size']})\n")
        print(f"\n详细报告已保存: {report_path}")
    
    return 0

if __name__ == '__main__':
    exit(main())

