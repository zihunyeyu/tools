"""
图像处理工具模块
提供图像处理、混合、格式转换等功能
"""

from typing import Optional, Tuple
import numpy as np
from PIL import Image, ImageTk


def remove_black_background(img: Image.Image, threshold: int = 20) -> Image.Image:
    """
    去除图像的黑色背景
    将接近黑色的像素设为透明
    
    Args:
        img: 输入图像
        threshold: 颜色阈值，低于此值视为黑色
    
    Returns:
        去黑底后的图像
    """
    img = img.convert("RGBA")
    
    # 使用 NumPy 进行像素操作（避免 getdata() 弃用警告）
    arr = np.array(img)
    
    # 创建黑色像素掩码：R、G、B 都小于阈值的像素
    black_mask = (
        (arr[:, :, 0] < threshold) & 
        (arr[:, :, 1] < threshold) & 
        (arr[:, :, 2] < threshold)
    )
    
    # 将黑色像素设为透明
    arr[black_mask] = [0, 0, 0, 0]
    
    return Image.fromarray(arr)


def linear_dodge_blend(base: Image.Image, blend: Image.Image) -> Image.Image:
    """
    线性减淡（Linear Dodge/Add）混合模式 - NumPy优化版
    公式: Result = min(Base + Blend, 255)
    等同于Photoshop的Linear Dodge（Add）
    
    Args:
        base: 基础图像
        blend: 混合图像
    
    Returns:
        混合后的图像
    """
    # 确保尺寸一致
    if base.size != blend.size:
        new_size = (max(base.width, blend.width), max(base.height, blend.height))
        base_canvas = Image.new("RGBA", new_size, (0, 0, 0, 0))
        blend_canvas = Image.new("RGBA", new_size, (0, 0, 0, 0))
        base_canvas.paste(base, (0, 0), base)
        blend_canvas.paste(blend, (0, 0), blend)
        base, blend = base_canvas, blend_canvas
    
    # 使用 NumPy 实现线性减淡（比 ImageChops.add 更快）
    base_arr = np.array(base.convert("RGBA"), dtype=np.uint16)
    blend_arr = np.array(blend.convert("RGBA"), dtype=np.uint16)
    
    # 线性减淡: Result = min(Base + Blend, 255)
    result_arr = np.minimum(base_arr + blend_arr, 255).astype(np.uint8)
    
    return Image.fromarray(result_arr)


def blend_f_layer(base: Image.Image, blend: Image.Image, black_threshold: int = 30) -> Image.Image:
    """
    f层混合：去黑底 + 线性减淡 合并优化版
    
    一次性完成两个操作，避免两次像素遍历：
    1. 去黑底：将 blend 中接近黑色的像素视为透明
    2. 线性减淡：Result = min(Base + Blend, 255)
    
    Args:
        base: 基础图像
        blend: f层图像（待去黑底并混合）
        black_threshold: 黑色阈值，低于此值视为黑色
    
    Returns:
        混合后的图像
    """
    # 确保尺寸一致
    if base.size != blend.size:
        new_size = (max(base.width, blend.width), max(base.height, blend.height))
        base_canvas = Image.new("RGBA", new_size, (0, 0, 0, 0))
        blend_canvas = Image.new("RGBA", new_size, (0, 0, 0, 0))
        base_canvas.paste(base, (0, 0), base)
        blend_canvas.paste(blend, (0, 0), blend)
        base, blend = base_canvas, blend_canvas
    
    # 转为 NumPy 数组
    base_arr = np.array(base.convert("RGBA"), dtype=np.uint16)
    blend_arr = np.array(blend.convert("RGBA"), dtype=np.uint16)
    
    # 创建黑色像素掩码（去黑底）
    black_mask = (
        (blend_arr[:, :, 0] < black_threshold) & 
        (blend_arr[:, :, 1] < black_threshold) & 
        (blend_arr[:, :, 2] < black_threshold)
    )
    
    # 线性减淡: Result = min(Base + Blend, 255)
    result_arr = np.minimum(base_arr + blend_arr, 255)
    
    # 黑色像素保持 base 原样（去黑底效果）
    result_arr[black_mask] = base_arr[black_mask]
    
    return Image.fromarray(result_arr.astype(np.uint8))


def is_f_layer(layer_name: str) -> bool:
    """
    判断图层名是否为f层（发光层）
    
    f层命名规则:
    - 以f结尾，如: cap_f, coat_f
    - 包含f后缀，如: neck_cf, coat_bf
    - 匹配模式: *_f 或 *cf
    
    Args:
        layer_name: 图层名称
    
    Returns:
        是否为f层
    """
    if not layer_name:
        return False
    # 以f结尾的图层名，如 cap_f, coat_f, neck_cf, body_f 等
    return layer_name.endswith('f')


def resize_image_preserve_aspect(
    img: Image.Image, 
    max_size: Tuple[int, int], 
    resample: int = Image.Resampling.LANCZOS
) -> Image.Image:
    """
    按比例缩放图像，保持宽高比
    
    Args:
        img: 输入图像
        max_size: 最大尺寸 (width, height)
        resample: 重采样算法
    
    Returns:
        缩放后的图像
    """
    img.thumbnail(max_size, resample)
    return img


def create_placeholder_image(size: Tuple[int, int], color: Tuple[int, ...] = (200, 200, 200, 128)) -> Image.Image:
    """创建占位图像"""
    return Image.new("RGBA", size, color)
