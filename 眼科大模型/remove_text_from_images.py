#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量去除图像左上角文字的脚本

提供三种处理方法:
1. 简单裁剪 (推荐)
2. 图像修复 (Inpainting)
3. 智能检测+裁剪

使用方法:
python remove_text_from_images.py --input_dir /path/to/images --output_dir /path/to/output --method crop
"""

import argparse
import os
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image
import numpy as np
from tqdm import tqdm


# ==================== 方法1: 简单裁剪 (推荐) ====================
def crop_top_left(image: Image.Image, crop_size: Tuple[int, int] = (100, 100)) -> Image.Image:
    """
    裁剪掉左上角的区域
    
    Args:
        image: PIL Image对象
        crop_size: (x_offset, y_offset) 要裁掉的左上角尺寸
    
    Returns:
        裁剪后的图像
    """
    width, height = image.size
    x_offset, y_offset = crop_size
    
    # 裁剪区域: (left, top, right, bottom)
    cropped = image.crop((x_offset, y_offset, width, height))
    return cropped


def crop_edges(image: Image.Image, 
               top: int = 0, 
               left: int = 0, 
               right: int = 0, 
               bottom: int = 0) -> Image.Image:
    """
    裁剪图像的四边
    
    Args:
        image: PIL Image对象
        top, left, right, bottom: 各边要裁掉的像素数
    
    Returns:
        裁剪后的图像
    """
    width, height = image.size
    cropped = image.crop((left, top, width - right, height - bottom))
    return cropped


# ==================== 方法: Padding到正方形 (推荐用于多模态训练) ====================
def pad_to_square(image: Image.Image, 
                  target_size: Optional[int] = None,
                  fill_color: tuple = (0, 0, 0)) -> Image.Image:
    """
    将图像padding到正方形，保持宽高比
    
    推荐用于多模态大模型训练（如LLaVA、Qwen-VL等）
    
    Args:
        image: PIL Image对象
        target_size: 目标正方形尺寸（如448），None表示以长边为准
        fill_color: padding的颜色，默认黑色(0,0,0)
    
    Returns:
        Padding后的正方形图像
    """
    from PIL import ImageOps
    
    width, height = image.size
    
    if target_size is None:
        # 以长边为准
        target_size = max(width, height)
    else:
        # 先缩放到目标尺寸（保持宽高比）
        image.thumbnail((target_size, target_size), Image.Resampling.LANCZOS)
    
    # Padding到正方形
    padded = ImageOps.pad(image, (target_size, target_size), 
                          method=Image.Resampling.LANCZOS,
                          color=fill_color,
                          centering=(0.5, 0.5))
    
    return padded


def center_crop_to_square(image: Image.Image) -> Image.Image:
    """
    中心裁剪为正方形（取短边为边长）
    
    Args:
        image: PIL Image对象
    
    Returns:
        正方形图像
    """
    width, height = image.size
    size = min(width, height)
    
    left = (width - size) // 2
    top = (height - size) // 2
    right = left + size
    bottom = top + size
    
    return image.crop((left, top, right, bottom))


# ==================== 方法2: 图像修复 ====================
def inpaint_text_region(image: Image.Image, mask_region: Tuple[int, int, int, int]) -> Image.Image:
    """
    使用图像修复技术填充文字区域
    
    注意: 需要安装 opencv-python (cv2)
    
    Args:
        image: PIL Image对象
        mask_region: (x1, y1, x2, y2) 要修复的区域
    
    Returns:
        修复后的图像
    """
    try:
        import cv2
    except ImportError:
        print("警告: 图像修复功能需要安装 opencv-python")
        print("运行: pip install opencv-python")
        return image
    
    # 转换为numpy数组
    img_array = np.array(image)
    
    # 创建mask (白色=需要修复的区域)
    mask = np.zeros(img_array.shape[:2], dtype=np.uint8)
    x1, y1, x2, y2 = mask_region
    mask[y1:y2, x1:x2] = 255
    
    # 使用Telea算法进行修复
    result = cv2.inpaint(img_array, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    
    return Image.fromarray(result)


# ==================== 方法3: 智能检测 ====================
def detect_text_region(image: Image.Image, 
                       top_ratio: float = 0.1, 
                       left_ratio: float = 0.1) -> Optional[Tuple[int, int, int, int]]:
    """
    检测左上角是否有文字区域
    
    使用简单的亮度对比检测
    
    Args:
        image: PIL Image对象
        top_ratio, left_ratio: 检测区域占图像的比例
    
    Returns:
        如果检测到文字，返回 (x1, y1, x2, y2)，否则返回 None
    """
    width, height = image.size
    check_w = int(width * left_ratio)
    check_h = int(height * top_ratio)
    
    # 提取左上角区域
    corner = image.crop((0, 0, check_w, check_h))
    corner_array = np.array(corner)
    
    # 提取中心区域作为对比
    center_x, center_y = width // 2, height // 2
    center = image.crop((
        center_x - check_w // 2, 
        center_y - check_h // 2,
        center_x + check_w // 2, 
        center_y + check_h // 2
    ))
    center_array = np.array(center)
    
    # 计算亮度标准差（文字区域通常有较大的亮度变化）
    if len(corner_array.shape) == 3:
        corner_std = corner_array.std()
        center_std = center_array.std()
    else:
        corner_std = corner_array.std()
        center_std = center_array.std()
    
    # 如果左上角的标准差明显大于中心区域，可能有文字
    if corner_std > center_std * 1.2:
        return (0, 0, check_w, check_h)
    
    return None


# ==================== 批量处理 ====================
def process_directory(input_dir: str,
                     output_dir: str,
                     method: str = "crop",
                     crop_size: Tuple[int, int] = (100, 100),
                     target_size: Optional[int] = None,
                     preserve_structure: bool = True,
                     extensions: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".tif", ".tiff")):
    """
    批量处理目录下的所有图像
    
    Args:
        input_dir: 输入目录
        output_dir: 输出目录
        method: 处理方法 ("crop", "pad_square", "center_crop_square", "crop_edges", "inpaint", "smart")
        crop_size: 裁剪尺寸 (x, y) - 用于crop/crop_edges方法
        target_size: 目标正方形尺寸 - 用于pad_square方法
        preserve_structure: 是否保留目录结构
        extensions: 要处理的文件扩展名
    """
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # 收集所有图像文件
    image_files = []
    for ext in extensions:
        image_files.extend(input_path.rglob(f"*{ext}"))
        image_files.extend(input_path.rglob(f"*{ext.upper()}"))
    
    print(f"找到 {len(image_files)} 个图像文件")
    print(f"处理方法: {method}")
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print()
    
    processed = 0
    skipped = 0
    errors = 0
    
    for img_file in tqdm(image_files, desc="处理图像"):
        try:
            # 读取图像
            img = Image.open(img_file)
            
            # 根据方法处理
            if method == "crop":
                # 简单裁剪
                processed_img = crop_top_left(img, crop_size)
            
            elif method == "crop_edges":
                # 裁剪边缘（顶部和左侧）
                top, left = crop_size
                processed_img = crop_edges(img, top=top, left=left)
            
            elif method == "pad_square":
                # Padding到正方形（推荐用于多模态训练）
                processed_img = pad_to_square(img, target_size=target_size)
            
            elif method == "center_crop_square":
                # 中心裁剪为正方形
                processed_img = center_crop_to_square(img)
            
            elif method == "crop_and_pad":
                # 先去除文字，再padding到正方形（推荐完整流程）
                temp_img = crop_top_left(img, crop_size)
                processed_img = pad_to_square(temp_img, target_size=target_size)
            
            elif method == "inpaint":
                # 图像修复
                mask_region = (0, 0, crop_size[0], crop_size[1])
                processed_img = inpaint_text_region(img, mask_region)
            
            elif method == "smart":
                # 智能检测
                text_region = detect_text_region(img)
                if text_region:
                    x1, y1, x2, y2 = text_region
                    processed_img = crop_top_left(img, (x2, y2))
                else:
                    # 没有检测到文字，保持原样
                    processed_img = img
            
            else:
                print(f"未知方法: {method}")
                return
            
            # 确定输出路径
            if preserve_structure:
                rel_path = img_file.relative_to(input_path)
                out_file = output_path / rel_path
                out_file.parent.mkdir(parents=True, exist_ok=True)
            else:
                out_file = output_path / img_file.name
            
            # 保存
            processed_img.save(out_file, quality=95)
            processed += 1
            
        except Exception as e:
            print(f"\n错误: {img_file}")
            print(f"  {e}")
            errors += 1
    
    print()
    print("="*70)
    print("处理完成!")
    print(f"  成功: {processed}")
    print(f"  跳过: {skipped}")
    print(f"  错误: {errors}")
    print("="*70)


# ==================== 命令行接口 ====================
def parse_args():
    parser = argparse.ArgumentParser(
        description="批量去除图像左上角文字 & 转换为正方形（多模态训练）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:

1. 简单裁剪（去除文字）:
   python remove_text_from_images.py -i /path/to/images -o /path/to/output -m crop --crop_x 100 --crop_y 100

2. Padding到正方形（多模态训练推荐）⭐:
   python remove_text_from_images.py -i /path/to/images -o /path/to/output -m pad_square --target_size 448

3. 先去文字再padding（完整流程，最推荐）⭐⭐⭐:
   python remove_text_from_images.py -i /path/to/images -o /path/to/output -m crop_and_pad --crop_x 100 --crop_y 100 --target_size 448

4. 中心裁剪为正方形:
   python remove_text_from_images.py -i /path/to/images -o /path/to/output -m center_crop_square

5. 只裁顶部:
   python remove_text_from_images.py -i /path/to/images -o /path/to/output -m crop_edges --crop_x 0 --crop_y 100

6. 图像修复:
   python remove_text_from_images.py -i /path/to/images -o /path/to/output -m inpaint --crop_x 100 --crop_y 100

7. 智能检测:
   python remove_text_from_images.py -i /path/to/images -o /path/to/output -m smart
        """
    )
    
    parser.add_argument("-i", "--input_dir", required=True, help="输入目录")
    parser.add_argument("-o", "--output_dir", required=True, help="输出目录")
    parser.add_argument("-m", "--method", default="crop", 
                       choices=["crop", "crop_edges", "pad_square", "center_crop_square", 
                               "crop_and_pad", "inpaint", "smart"],
                       help="处理方法")
    parser.add_argument("--crop_x", type=int, default=100, 
                       help="裁剪X方向（左侧）的像素数")
    parser.add_argument("--crop_y", type=int, default=100, 
                       help="裁剪Y方向（顶部）的像素数")
    parser.add_argument("--target_size", type=int, default=None,
                       help="目标正方形尺寸（如448），用于pad_square和crop_and_pad方法")
    parser.add_argument("--no_preserve_structure", action="store_true",
                       help="不保留目录结构，所有图像输出到同一目录")
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    crop_size = (args.crop_x, args.crop_y)
    preserve_structure = not args.no_preserve_structure
    
    process_directory(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        method=args.method,
        crop_size=crop_size,
        target_size=args.target_size,
        preserve_structure=preserve_structure
    )


if __name__ == "__main__":
    main()

