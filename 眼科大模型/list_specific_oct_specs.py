#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
列出指定规格的OCT图像路径
"""

from pathlib import Path
from PIL import Image
from tqdm import tqdm

def find_specific_specs(base_dir, target_specs):
    """查找指定规格的OCT图像"""
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"错误: 目录不存在 - {base_dir}")
        return {}
    
    # 统计规格: (width, height) -> [文件路径列表]
    spec_dict = {}
    for spec in target_specs:
        spec_dict[spec] = []
    
    # 支持的图像格式
    image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', 
                  '.JPG', '.JPEG', '.PNG', '.BMP', '.TIF', '.TIFF'}
    
    case_folders = sorted([d for d in base_path.iterdir() if d.is_dir() and not d.name.startswith('.')])
    
    print(f"正在检查 {len(case_folders)} 个病例文件夹...")
    print(f"目标规格: {target_specs}")
    print("="*70)
    
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
                    
                    if size in target_specs:
                        spec_dict[size].append(img_file)
                except Exception as e:
                    # 如果无法读取图像，跳过
                    continue
    
    return spec_dict

def main():
    """主函数"""
    base_dir = '/data2/xuhanyang/dataset/海德堡葡萄膜炎图像提取'
    
    # 目标规格
    target_specs = [(768, 768), (768, 496)]
    
    spec_dict = find_specific_specs(base_dir, target_specs)
    
    print("\n" + "="*70)
    print("查找结果:")
    print("="*70)
    
    for spec in target_specs:
        files = spec_dict[spec]
        print(f"\n规格 {spec[0]}x{spec[1]}: 共 {len(files)} 张")
        print("-"*70)
        
        if files:
            for img_path in files:
                # 获取相对路径
                rel_path = img_path.relative_to(Path(base_dir))
                print(f"  {rel_path}")
        else:
            print("  未找到该规格的图像")
    
    # 生成详细报告
    report_path = Path('/data2/xuhanyang/眼科大模型/特定规格OCT图像路径列表.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("特定规格OCT图像路径列表\n")
        f.write("="*70 + "\n\n")
        f.write(f"检查目录: {base_dir}\n")
        f.write(f"目标规格: {target_specs}\n\n")
        
        for spec in target_specs:
            files = spec_dict[spec]
            f.write(f"\n规格 {spec[0]}x{spec[1]}: 共 {len(files)} 张\n")
            f.write("-"*70 + "\n")
            
            if files:
                for img_path in files:
                    rel_path = img_path.relative_to(Path(base_dir))
                    f.write(f"{rel_path}\n")
            else:
                f.write("未找到该规格的图像\n")
    
    print(f"\n详细报告已保存: {report_path}")

if __name__ == '__main__':
    main()

