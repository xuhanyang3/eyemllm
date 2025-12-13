#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查OCT图像规格，统计每种规格的数量，并列出少数规格的路径
"""

from pathlib import Path
from collections import defaultdict
from PIL import Image
from tqdm import tqdm

def check_oct_specs(base_dir):
    """检查基础目录下所有OCT图像的规格"""
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"错误: 目录不存在 - {base_dir}")
        return {}
    
    # 统计规格: (width, height) -> [文件路径列表]
    spec_dict = defaultdict(list)
    
    # 支持的图像格式
    image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', 
                  '.JPG', '.JPEG', '.PNG', '.BMP', '.TIF', '.TIFF'}
    
    case_folders = [d for d in base_path.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    print(f"正在检查 {len(case_folders)} 个病例文件夹...")
    
    for case_folder in tqdm(case_folders, desc="处理病例"):
        oct_dir = case_folder / 'OCT'
        
        if not oct_dir.exists():
            continue
        
        # 遍历OCT文件夹中的所有图像
        for img_file in oct_dir.iterdir():
            if img_file.is_file() and img_file.suffix in image_exts:
                try:
                    img = Image.open(img_file)
                    size = img.size  # (width, height)
                    spec_dict[size].append(img_file)
                except Exception as e:
                    # 如果无法读取图像，跳过
                    continue
    
    return spec_dict

def main():
    """主函数"""
    directories = [
        '/data2/xuhanyang/dataset/UV_CSC找不到名单图像提取',
        '/data2/xuhanyang/dataset/海德堡葡萄膜炎图像提取'
    ]
    
    all_specs = {}
    
    for base_dir in directories:
        print("="*70)
        print(f"检查目录: {base_dir}")
        print("="*70)
        
        spec_dict = check_oct_specs(base_dir)
        all_specs[base_dir] = spec_dict
        
        # 按数量排序
        sorted_specs = sorted(spec_dict.items(), key=lambda x: len(x[1]), reverse=True)
        
        print(f"\n发现 {len(sorted_specs)} 种不同的规格:")
        print("-"*70)
        
        for size, files in sorted_specs:
            print(f"规格 {size[0]}x{size[1]}: {len(files)} 张")
        
        # 找出少数规格（数量少于总数的5%或少于10张）
        total_images = sum(len(files) for files in spec_dict.values())
        threshold = max(10, total_images * 0.05)  # 至少10张或总数的5%
        
        minority_specs = [(size, files) for size, files in sorted_specs if len(files) < threshold]
        
        if minority_specs:
            print(f"\n⚠ 发现 {len(minority_specs)} 种少数规格（少于 {int(threshold)} 张）:")
            print("-"*70)
            
            for size, files in minority_specs:
                print(f"\n规格 {size[0]}x{size[1]}: {len(files)} 张")
                print(f"  路径列表（前20个）:")
                for img_path in files[:20]:
                    # 获取相对路径
                    rel_path = img_path.relative_to(Path(base_dir))
                    print(f"    - {rel_path}")
                if len(files) > 20:
                    print(f"    ... 还有 {len(files) - 20} 个文件")
        else:
            print("\n✓ 所有规格的图像数量都较多，没有明显的少数规格")
        
        print()
    
    # 生成详细报告
    report_path = Path('/data2/xuhanyang/眼科大模型/OCT图像规格检查报告.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("OCT图像规格检查报告\n")
        f.write("="*70 + "\n\n")
        
        for base_dir, spec_dict in all_specs.items():
            f.write(f"目录: {base_dir}\n")
            f.write("-"*70 + "\n")
            
            sorted_specs = sorted(spec_dict.items(), key=lambda x: len(x[1]), reverse=True)
            total_images = sum(len(files) for files in spec_dict.values())
            threshold = max(10, total_images * 0.05)
            
            f.write(f"\n总图像数: {total_images} 张\n")
            f.write(f"规格种类: {len(sorted_specs)} 种\n")
            f.write(f"少数规格阈值: 少于 {int(threshold)} 张\n\n")
            
            f.write("所有规格统计:\n")
            for size, files in sorted_specs:
                percentage = len(files) / total_images * 100 if total_images > 0 else 0
                f.write(f"  {size[0]}x{size[1]}: {len(files)} 张 ({percentage:.1f}%)\n")
            
            minority_specs = [(size, files) for size, files in sorted_specs if len(files) < threshold]
            
            if minority_specs:
                f.write(f"\n少数规格详情（{len(minority_specs)} 种）:\n")
                for size, files in minority_specs:
                    f.write(f"\n规格 {size[0]}x{size[1]}: {len(files)} 张\n")
                    for img_path in files:
                        rel_path = img_path.relative_to(Path(base_dir))
                        f.write(f"  {rel_path}\n")
            else:
                f.write("\n✓ 未发现少数规格\n")
            
            f.write("\n" + "="*70 + "\n\n")
    
    print(f"详细报告已保存: {report_path}")

if __name__ == '__main__':
    main()

