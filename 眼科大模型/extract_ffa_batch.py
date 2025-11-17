#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量并行提取FFA图像（使用多进程加速）
"""

import sys
from pathlib import Path
from multiprocessing import Pool, cpu_count
from tqdm import tqdm
import time
from extract_ffa_only import extract_ffa_images_from_pdf

def process_single_pdf(args):
    """处理单个PDF（用于多进程）"""
    pdf_path, output_dir = args
    try:
        result = extract_ffa_images_from_pdf(pdf_path, output_dir)
        return {
            'pdf': pdf_path.name,
            'status': result['status'],
            'num_images': result.get('num_images', 0),
            'eye': result.get('eye', ''),
            'type': result.get('type', '')
        }
    except Exception as e:
        return {
            'pdf': pdf_path.name,
            'status': 'error',
            'error': str(e)
        }

def batch_extract_ffa(input_dir, output_dir, num_workers=None):
    """
    批量并行提取FFA图像
    
    Args:
        input_dir: 输入目录（递归搜索所有PDF）
        output_dir: 输出目录
        num_workers: 并行进程数（默认为CPU核心数）
    """
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    
    if num_workers is None:
        num_workers = cpu_count()
    
    print("="*70)
    print("批量FFA图像提取工具（多进程加速）")
    print("="*70)
    print()
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print(f"并行进程数: {num_workers}")
    print()
    
    # 递归查找所有PDF文件
    print("正在扫描PDF文件...")
    pdf_files = list(input_dir.rglob('*.pdf'))
    
    if not pdf_files:
        print("错误: 未找到PDF文件")
        return
    
    print(f"找到 {len(pdf_files)} 个PDF文件")
    print()
    
    # 准备任务参数
    tasks = [(pdf, output_dir) for pdf in pdf_files]
    
    # 多进程处理
    start_time = time.time()
    
    with Pool(num_workers) as pool:
        results = list(tqdm(
            pool.imap(process_single_pdf, tasks),
            total=len(tasks),
            desc="处理进度",
            unit="PDF"
        ))
    
    elapsed = time.time() - start_time
    
    # 统计结果
    success_count = sum(1 for r in results if r['status'] == 'success')
    skipped_count = sum(1 for r in results if r['status'] == 'skipped')
    error_count = sum(1 for r in results if r['status'] == 'error')
    total_images = sum(r.get('num_images', 0) for r in results)
    
    print()
    print("="*70)
    print("处理完成")
    print("="*70)
    print(f"总计: {len(pdf_files)} 个PDF")
    print(f"  成功: {success_count} 个")
    print(f"  跳过: {skipped_count} 个（ICGA等）")
    print(f"  错误: {error_count} 个")
    print(f"提取图像: {total_images} 张")
    print(f"总耗时: {elapsed:.1f} 秒 ({elapsed/60:.1f} 分钟)")
    print(f"平均速度: {elapsed/len(pdf_files):.2f} 秒/PDF")
    print(f"加速比: {len(pdf_files)*7.9/elapsed:.1f}x")
    print(f"输出目录: {output_dir}")
    print("="*70)
    
    # 保存详细报告
    report_path = output_dir / "extraction_report.txt"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("FFA图像提取报告\n")
        f.write("="*70 + "\n\n")
        f.write(f"处理时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"总耗时: {elapsed:.1f} 秒\n")
        f.write(f"成功: {success_count} | 跳过: {skipped_count} | 错误: {error_count}\n")
        f.write(f"提取图像: {total_images} 张\n\n")
        
        f.write("详细结果:\n")
        f.write("-"*70 + "\n")
        for r in results:
            status_symbol = "✓" if r['status'] == 'success' else ("✗" if r['status'] == 'skipped' else "⚠")
            f.write(f"{status_symbol} {r['pdf']}")
            if r['status'] == 'success':
                f.write(f" - {r['eye']} - {r['num_images']}张")
            elif r['status'] == 'error':
                f.write(f" - 错误: {r.get('error', '未知')}")
            f.write("\n")
    
    print(f"\n详细报告已保存: {report_path}")

def main():
    if len(sys.argv) < 3:
        print("用法:")
        print("  python extract_ffa_batch.py <输入目录> <输出目录> [进程数]")
        print()
        print("示例:")
        print("  python extract_ffa_batch.py /path/to/pdfs/ /path/to/output/")
        print("  python extract_ffa_batch.py /path/to/pdfs/ /path/to/output/ 8")
        sys.exit(1)
    
    input_dir = sys.argv[1]
    output_dir = sys.argv[2]
    num_workers = int(sys.argv[3]) if len(sys.argv) > 3 else None
    
    batch_extract_ffa(input_dir, output_dir, num_workers)

if __name__ == '__main__':
    main()

