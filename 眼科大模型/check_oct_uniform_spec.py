#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查OCT图像是否都属于同一种规格
"""

from pathlib import Path
from PIL import Image
from tqdm import tqdm
from collections import Counter

def check_oct_specs(base_dir):
    """检查OCT图像规格"""
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"错误: 目录不存在 - {base_dir}")
        return {}
    
    # 统计规格: (width, height) -> 数量
    spec_counter = Counter()
    
    # 支持的图像格式
    image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', 
                  '.JPG', '.JPEG', '.PNG', '.BMP', '.TIF', '.TIFF'}
    
    case_folders = sorted([d for d in base_path.iterdir() if d.is_dir() and not d.name.startswith('.')])
    
    print(f"正在检查 {len(case_folders)} 个病例文件夹...")
    print("="*70)
    
    total_images = 0
    error_count = 0
    
    for case_folder in tqdm(case_folders, desc="处理病例"):
        oct_dir = case_folder / 'OCT'
        
        if not oct_dir.exists():
            continue
        
        # 遍历OCT文件夹中的所有图像
        for img_file in oct_dir.iterdir():
            if img_file.is_file() and img_file.suffix in image_exts:
                total_images += 1
                try:
                    img = Image.open(img_file)
                    size = img.size  # (width, height)
                    spec_counter[size] += 1
                except Exception as e:
                    error_count += 1
                    print(f"  警告: 无法读取 {case_folder.name}/OCT/{img_file.name} - {e}")
    
    return spec_counter, total_images, error_count

def main():
    """主函数"""
    base_dir = '/data2/xuhanyang/dataset/海德堡葡萄膜炎图像提取'
    
    spec_counter, total_images, error_count = check_oct_specs(base_dir)
    
    print("\n" + "="*70)
    print("检查结果:")
    print("="*70)
    print(f"总图像数: {total_images} 张")
    print(f"读取错误: {error_count} 张")
    print(f"发现规格种类: {len(spec_counter)} 种\n")
    
    if len(spec_counter) == 1:
        spec, count = spec_counter.most_common(1)[0]
        print(f"✓ 所有OCT图像都属于同一种规格: {spec[0]}x{spec[1]}")
        print(f"  共 {count} 张图像")
    else:
        print(f"✗ 发现 {len(spec_counter)} 种不同的规格:")
        print("-"*70)
        
        # 按数量排序
        sorted_specs = sorted(spec_counter.items(), key=lambda x: x[1], reverse=True)
        
        for spec, count in sorted_specs:
            percentage = count / total_images * 100 if total_images > 0 else 0
            print(f"  规格 {spec[0]}x{spec[1]}: {count} 张 ({percentage:.1f}%)")
        
        # 找出主要规格
        main_spec, main_count = sorted_specs[0]
        main_percentage = main_count / total_images * 100 if total_images > 0 else 0
        
        print(f"\n主要规格: {main_spec[0]}x{main_spec[1]} ({main_percentage:.1f}%)")
        
        if main_percentage >= 95:
            print("  → 超过95%的图像属于同一规格，可以认为是基本统一")
        elif main_percentage >= 80:
            print("  → 超过80%的图像属于同一规格，但存在少量其他规格")
        else:
            print("  → 规格分布较分散，建议统一处理")
    
    # 生成详细报告
    report_path = Path('/data2/xuhanyang/眼科大模型/OCT规格统一性检查报告.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("OCT图像规格统一性检查报告\n")
        f.write("="*70 + "\n\n")
        f.write(f"检查目录: {base_dir}\n")
        f.write(f"总图像数: {total_images} 张\n")
        f.write(f"读取错误: {error_count} 张\n")
        f.write(f"发现规格种类: {len(spec_counter)} 种\n\n")
        
        if len(spec_counter) == 1:
            spec, count = spec_counter.most_common(1)[0]
            f.write(f"✓ 所有OCT图像都属于同一种规格: {spec[0]}x{spec[1]}\n")
            f.write(f"  共 {count} 张图像\n")
        else:
            f.write(f"✗ 发现 {len(spec_counter)} 种不同的规格:\n")
            f.write("-"*70 + "\n")
            
            sorted_specs = sorted(spec_counter.items(), key=lambda x: x[1], reverse=True)
            
            for spec, count in sorted_specs:
                percentage = count / total_images * 100 if total_images > 0 else 0
                f.write(f"规格 {spec[0]}x{spec[1]}: {count} 张 ({percentage:.1f}%)\n")
    
    print(f"\n详细报告已保存: {report_path}")

if __name__ == '__main__':
    main()

