#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
删除FFA文件夹中的IR图像
"""

import os
from pathlib import Path
from collections import defaultdict

def is_ir_image(filename):
    """
    检测图像是否是IR图像（红外图像）
    
    Args:
        filename: 文件名
    
    Returns:
        bool: 如果是IR图像返回True
    """
    text_to_check = filename.upper()
    ir_keywords = ['IR', 'INFRARED', '红外']
    return any(keyword in text_to_check for keyword in ir_keywords)

def find_and_remove_ir_images(base_dir, dry_run=True):
    """
    查找并删除FFA文件夹中的IR图像
    
    Args:
        base_dir: 基础目录路径
        dry_run: 如果为True，只列出要删除的文件，不实际删除
    """
    base_path = Path(base_dir)
    
    if not base_path.exists():
        print(f"错误: 目录不存在 - {base_path}")
        return
    
    print("="*70)
    print("删除FFA文件夹中的IR图像")
    print("="*70)
    print(f"检查目录: {base_path}")
    print(f"模式: {'预览模式（不会实际删除）' if dry_run else '删除模式（将实际删除文件）'}")
    print()
    
    # 统计信息
    stats = {
        'total_cases': 0,
        'cases_with_ir': 0,
        'total_ir_images': 0,
        'deleted_files': []
    }
    
    # 遍历所有病例文件夹
    case_dirs = sorted([d for d in base_path.iterdir() if d.is_dir()])
    
    print(f"找到 {len(case_dirs)} 个病例文件夹\n")
    
    for case_dir in case_dirs:
        stats['total_cases'] += 1
        case_name = case_dir.name
        ffa_dir = case_dir / "FFA"
        
        if not ffa_dir.exists():
            continue
        
        # 支持的图像格式
        image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'}
        
        ir_files = []
        
        # 查找所有IR图像
        for img_file in ffa_dir.iterdir():
            if not img_file.is_file():
                continue
            
            if img_file.suffix.lower() not in image_exts:
                continue
            
            if is_ir_image(img_file.name):
                ir_files.append(img_file)
        
        if ir_files:
            stats['cases_with_ir'] += 1
            stats['total_ir_images'] += len(ir_files)
            
            print(f"病例: {case_name}")
            print(f"  找到 {len(ir_files)} 张IR图像:")
            
            for ir_file in ir_files:
                print(f"    - {ir_file.name}")
                
                if not dry_run:
                    try:
                        ir_file.unlink()
                        print(f"      ✓ 已删除")
                    except Exception as e:
                        print(f"      ✗ 删除失败: {e}")
                
                stats['deleted_files'].append({
                    'case': case_name,
                    'file': ir_file.name,
                    'path': str(ir_file)
                })
            print()
    
    # 打印统计结果
    print("="*70)
    print("处理结果统计")
    print("="*70)
    print(f"总病例数: {stats['total_cases']}")
    print(f"包含IR图像的病例: {stats['cases_with_ir']}")
    print(f"IR图像总数: {stats['total_ir_images']}")
    
    if not dry_run:
        print(f"已删除文件数: {len(stats['deleted_files'])}")
    else:
        print(f"将删除文件数: {len(stats['deleted_files'])}")
    print()
    
    # 保存详细报告
    report_name = "FFA_IR删除报告_预览.txt" if dry_run else "FFA_IR删除报告.txt"
    report_path = base_path / report_name
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("="*70 + "\n")
        f.write("FFA文件夹IR图像删除报告\n")
        f.write("="*70 + "\n\n")
        f.write(f"检查目录: {base_path}\n")
        f.write(f"模式: {'预览模式（未实际删除）' if dry_run else '删除模式（已实际删除）'}\n\n")
        
        f.write("统计信息:\n")
        f.write("-"*70 + "\n")
        f.write(f"总病例数: {stats['total_cases']}\n")
        f.write(f"包含IR图像的病例: {stats['cases_with_ir']}\n")
        f.write(f"IR图像总数: {stats['total_ir_images']}\n")
        if not dry_run:
            f.write(f"已删除文件数: {len(stats['deleted_files'])}\n")
        else:
            f.write(f"将删除文件数: {len(stats['deleted_files'])}\n")
        f.write("\n")
        
        if stats['deleted_files']:
            f.write("="*70 + "\n")
            f.write("删除的文件列表\n")
            f.write("="*70 + "\n\n")
            for item in stats['deleted_files']:
                f.write(f"病例: {item['case']}\n")
                f.write(f"  文件: {item['file']}\n")
                f.write(f"  路径: {item['path']}\n")
                f.write("\n")
    
    print(f"详细报告已保存到: {report_path}")
    print("="*70)
    
    return stats

def main():
    """主函数"""
    import sys
    
    # 默认检查目录
    base_dir = "/data2/xuhanyang/dataset/截图文件汇总/葡萄膜炎病例图像提取"
    
    if len(sys.argv) > 1:
        base_dir = sys.argv[1]
    
    # 默认使用预览模式
    dry_run = True
    if len(sys.argv) > 2 and sys.argv[2].lower() in ['--delete', '-d', 'delete']:
        # 确认删除
        print("警告: 您即将删除IR图像文件！")
        print("这将永久删除文件，无法恢复。")
        confirm = input("请输入 'yes' 确认删除: ")
        if confirm.lower() == 'yes':
            dry_run = False
        else:
            print("已取消删除操作")
            return
    
    stats = find_and_remove_ir_images(base_dir, dry_run=dry_run)
    
    if dry_run:
        print("\n提示: 这是预览模式，文件未被删除。")
        print("要实际删除文件，请运行:")
        print(f"  python {sys.argv[0]} {base_dir} --delete")

if __name__ == '__main__':
    main()

