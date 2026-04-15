#!/usr/bin/env python3
"""
卡牌文本替换工具
功能：识别中文卡图中的文字，替换到清晰的英文卡图对应位置

使用方法:
    python card_text_replacer.py --cn ./chinese_card.jpg --en ./english_card.png --output ./result.png
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import argparse
import os
from pathlib import Path
from typing import List, Tuple, Dict, Optional


def detect_text_regions(image_path: str, lang: str = 'ch') -> List[Dict]:
    """
    检测图像中的文本区域
    返回: [{"bbox": [(x1,y1), (x2,y2), (x3,y3), (x4,y4)], "text": "...", "confidence": 0.9}, ...]
    """
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print("[错误] 需要安装 PaddleOCR: pip install paddleocr")
        print("建议安装: pip install paddleocr -i https://pypi.tuna.tsinghua.edu.cn/simple")
        raise
    
    # 初始化 PaddleOCR (中文+英文)
    ocr = PaddleOCR(
        use_angle_cls=True,
        lang='ch',  # 中文模型也支持英文
        show_log=False,
        use_gpu=False
    )
    
    # 执行 OCR
    result = ocr.ocr(image_path, cls=True)
    
    text_regions = []
    if result and result[0]:
        for line in result[0]:
            if line:
                bbox = line[0]  # 四个角点坐标
                text = line[1][0]  # 识别的文本
                confidence = line[1][1]  # 置信度
                text_regions.append({
                    "bbox": bbox,
                    "text": text,
                    "confidence": confidence
                })
    
    return text_regions


def detect_english_regions(image_path: str) -> List[Dict]:
    """
    检测英文卡图中的文本区域
    """
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print("[错误] 需要安装 PaddleOCR: pip install paddleocr")
        raise
    
    ocr = PaddleOCR(
        use_angle_cls=True,
        lang='en',
        show_log=False,
        use_gpu=False
    )
    
    result = ocr.ocr(image_path, cls=True)
    
    text_regions = []
    if result and result[0]:
        for line in result[0]:
            if line:
                bbox = line[0]
                text = line[1][0]
                confidence = line[1][1]
                text_regions.append({
                    "bbox": bbox,
                    "text": text,
                    "confidence": confidence
                })
    
    return text_regions


def get_region_center(bbox: List[Tuple]) -> Tuple[int, int]:
    """计算文本区域的中心点"""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))


def get_region_bbox_rect(bbox: List[Tuple]) -> Tuple[int, int, int, int]:
    """获取文本区域的边界框 (x, y, w, h)"""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    x_min, x_max = int(min(xs)), int(max(xs))
    y_min, y_max = int(min(ys)), int(max(ys))
    return (x_min, y_min, x_max - x_min, y_max - y_min)


def match_regions(cn_regions: List[Dict], en_regions: List[Dict], 
                  img_cn_size: Tuple, img_en_size: Tuple) -> List[Tuple[Dict, Dict]]:
    """
    匹配中文和英文的文本区域
    基于相对位置进行匹配
    
    返回: [(cn_region, en_region), ...] 的匹配对列表
    """
    matches = []
    
    # 计算缩放比例
    scale_x = img_en_size[0] / img_cn_size[0]
    scale_y = img_en_size[1] / img_cn_size[1]
    
    # 对于每个中文区域，找到最匹配的英文区域
    for cn_reg in cn_regions:
        cn_center = get_region_center(cn_reg['bbox'])
        cn_center_scaled = (cn_center[0] * scale_x, cn_center[1] * scale_y)
        
        best_match = None
        best_distance = float('inf')
        
        for en_reg in en_regions:
            en_center = get_region_center(en_reg['bbox'])
            # 计算距离
            distance = np.sqrt(
                (cn_center_scaled[0] - en_center[0])**2 + 
                (cn_center_scaled[1] - en_center[1])**2
            )
            
            if distance < best_distance:
                best_distance = distance
                best_match = en_reg
        
        # 只添加距离足够近的匹配
        threshold = min(img_en_size) * 0.15  # 15% 图像尺寸作为阈值
        if best_match and best_distance < threshold:
            matches.append((cn_reg, best_match))
    
    return matches


def inpaint_region(image: Image.Image, bbox: Tuple[int, int, int, int], 
                   fill_color: Optional[Tuple] = None) -> Image.Image:
    """
    使用 OpenCV 的图像修复(inpainting)来清除原文本区域
    
    bbox: (x, y, w, h)
    """
    # 转换为 OpenCV 格式
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    
    x, y, w, h = bbox
    # 扩大一点区域以确保清除完整
    margin = 3
    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(img_cv.shape[1], x + w + margin)
    y2 = min(img_cv.shape[0], y + h + margin)
    
    # 创建掩码
    mask = np.zeros(img_cv.shape[:2], dtype=np.uint8)
    mask[y1:y2, x1:x2] = 255
    
    # 使用 Telea 算法进行图像修复
    inpainted = cv2.inpaint(img_cv, mask, 3, cv2.INPAINT_TELEA)
    
    # 转换回 PIL
    return Image.fromarray(cv2.cvtColor(inpainted, cv2.COLOR_BGR2RGB))


def estimate_font_size(text: str, bbox: Tuple[int, int, int, int], 
                       image_width: int) -> int:
    """
    根据区域大小估算字体大小
    """
    x, y, w, h = bbox
    # 基于高度估算字体大小
    estimated_size = int(h * 0.7)
    # 考虑文本长度进行调整
    if len(text) > 10:
        estimated_size = min(estimated_size, int(w / len(text) * 1.5))
    
    return max(10, min(estimated_size, 72))  # 限制在 10-72 之间


def find_best_font(font_size: int) -> ImageFont.FreeTypeFont:
    """
    寻找合适的中文字体
    """
    # 常见的中文字体路径
    font_paths = [
        # Linux
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # macOS
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        # Windows
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/arial.ttf",
        # 项目本地
        "./fonts/NotoSansCJK-Regular.ttc",
        "./fonts/simhei.ttf",
    ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, font_size)
            except:
                continue
    
    # 回退到默认字体
    return ImageFont.load_default()


def draw_text_on_image(image: Image.Image, text: str, 
                       bbox: Tuple[int, int, int, int],
                       text_color: Tuple = (0, 0, 0)) -> Image.Image:
    """
    在指定区域绘制中文文本
    
    bbox: (x, y, w, h)
    """
    draw = ImageDraw.Draw(image)
    x, y, w, h = bbox
    
    # 估算字体大小
    font_size = estimate_font_size(text, bbox, image.width)
    font = find_best_font(font_size)
    
    # 计算文本位置（居中）
    try:
        bbox_text = draw.textbbox((0, 0), text, font=font)
        text_w = bbox_text[2] - bbox_text[0]
        text_h = bbox_text[3] - bbox_text[1]
    except:
        text_w, text_h = draw.textsize(text, font=font)
    
    # 居中放置
    text_x = x + (w - text_w) // 2
    text_y = y + (h - text_h) // 2
    
    # 绘制文本（带描边以提高可读性）
    stroke_color = (255, 255, 255) if text_color == (0, 0, 0) else (0, 0, 0)
    
    # 先画描边
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            if dx != 0 or dy != 0:
                draw.text((text_x + dx, text_y + dy), text, font=font, fill=stroke_color)
    
    # 画主文本
    draw.text((text_x, text_y), text, font=font, fill=text_color)
    
    return image


def auto_detect_text_color(image: Image.Image, bbox: Tuple[int, int, int, int]) -> Tuple:
    """
    自动检测文本区域的颜色
    """
    x, y, w, h = bbox
    # 提取区域
    region = image.crop((x, y, x+w, y+h))
    region_array = np.array(region)
    
    # 计算平均颜色
    mean_color = np.mean(region_array, axis=(0, 1))
    
    # 判断是深色还是浅色文本
    brightness = np.mean(mean_color)
    if brightness > 128:
        return (0, 0, 0)  # 黑色
    else:
        return (255, 255, 255)  # 白色


def replace_text_on_card(cn_image_path: str, en_image_path: str, 
                         output_path: str, debug: bool = False):
    """
    主函数：将中文卡图的文字替换到英文卡图
    
    Args:
        cn_image_path: 中文卡图路径（拍照/扫描的）
        en_image_path: 英文卡图路径（清晰的）
        output_path: 输出路径
        debug: 是否输出调试信息
    """
    print(f"=" * 60)
    print(f"卡牌文本替换工具")
    print(f"=" * 60)
    print(f"中文卡图: {cn_image_path}")
    print(f"英文卡图: {en_image_path}")
    print(f"输出路径: {output_path}")
    print()
    
    # 1. 加载图像
    print("[1/5] 加载图像...")
    img_cn = Image.open(cn_image_path).convert('RGB')
    img_en = Image.open(en_image_path).convert('RGB')
    
    # 确保尺寸一致（以英文卡图为基准）
    if img_cn.size != img_en.size:
        print(f"    调整中文卡图尺寸: {img_cn.size} -> {img_en.size}")
        img_cn_resized = img_cn.resize(img_en.size, Image.Resampling.LANCZOS)
    else:
        img_cn_resized = img_cn
    
    # 2. 检测中文文本区域
    print("[2/5] 检测中文文本...")
    cn_regions = detect_text_regions(cn_image_path, 'ch')
    print(f"    发现 {len(cn_regions)} 个中文文本区域")
    
    if debug:
        for i, reg in enumerate(cn_regions[:10]):
            print(f"    [{i+1}] {reg['text'][:20]}... (置信度: {reg['confidence']:.2f})")
    
    # 3. 检测英文文本区域
    print("[3/5] 检测英文文本...")
    en_regions = detect_english_regions(en_image_path)
    print(f"    发现 {len(en_regions)} 个英文文本区域")
    
    # 4. 匹配区域
    print("[4/5] 匹配文本区域...")
    matches = match_regions(cn_regions, en_regions, img_cn_resized.size, img_en.size)
    print(f"    匹配到 {len(matches)} 对文本区域")
    
    # 5. 执行替换
    print("[5/5] 执行文本替换...")
    result_image = img_en.copy()
    
    for i, (cn_reg, en_reg) in enumerate(matches):
        cn_text = cn_reg['text']
        en_bbox = get_region_bbox_rect(en_reg['bbox'])
        
        # 检测文本颜色
        text_color = auto_detect_text_color(result_image, en_bbox)
        
        # 使用图像修复清除原文本
        result_image = inpaint_region(result_image, en_bbox)
        
        # 绘制中文文本
        result_image = draw_text_on_image(result_image, cn_text, en_bbox, text_color)
        
        if debug and i < 5:
            print(f"    [{i+1}] 替换: '{cn_text[:30]}...' -> 区域 {en_bbox}")
    
    # 保存结果
    result_image.save(output_path, 'PNG', quality=95)
    print(f"\n[完成] 结果已保存: {output_path}")
    
    return output_path


def batch_process(cn_dir: str, en_dir: str, output_dir: str):
    """
    批量处理卡牌
    
    命名约定:
        - 中文卡图: 01001.jpg, 01002.jpg, ...
        - 英文卡图: 01001.png, 01002.png, ...
    """
    cn_dir = Path(cn_dir)
    en_dir = Path(en_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 获取所有中文卡图
    cn_files = sorted(cn_dir.glob('*'))
    
    for cn_file in cn_files:
        if cn_file.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.webp']:
            continue
        
        # 查找对应的英文卡图
        en_file = en_dir / (cn_file.stem + '.png')
        if not en_file.exists():
            en_file = en_dir / (cn_file.stem + '.jpg')
        
        if en_file.exists():
            output_file = output_dir / (cn_file.stem + '_cn.png')
            try:
                replace_text_on_card(str(cn_file), str(en_file), str(output_file))
            except Exception as e:
                print(f"[错误] 处理 {cn_file.name} 失败: {e}")
        else:
            print(f"[跳过] 未找到对应的英文卡图: {cn_file.name}")


def main():
    parser = argparse.ArgumentParser(description='卡牌文本替换工具')
    parser.add_argument('--cn', type=str, help='中文卡图路径')
    parser.add_argument('--en', type=str, help='英文卡图路径')
    parser.add_argument('--output', type=str, help='输出路径')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    
    # 批量处理参数
    parser.add_argument('--batch', action='store_true', help='批量处理模式')
    parser.add_argument('--cn-dir', type=str, help='中文卡图目录')
    parser.add_argument('--en-dir', type=str, help='英文卡图目录')
    parser.add_argument('--output-dir', type=str, default='./output', help='输出目录')
    
    args = parser.parse_args()
    
    # 检查依赖
    try:
        import paddleocr
        import cv2
        import numpy
        from PIL import Image
    except ImportError as e:
        print("[错误] 缺少依赖，请安装:")
        print("  pip install paddleocr opencv-python numpy pillow")
        return
    
    if args.batch:
        # 批量处理
        if not args.cn_dir or not args.en_dir:
            print("[错误] 批量处理需要 --cn-dir 和 --en-dir 参数")
            return
        batch_process(args.cn_dir, args.en_dir, args.output_dir)
    else:
        # 单张处理
        if not args.cn or not args.en or not args.output:
            print("[错误] 单张处理需要 --cn, --en, --output 参数")
            print("\n示例:")
            print(f"  python {__file__} --cn ./chinese.jpg --en ./english.png --output ./result.png")
            return
        
        replace_text_on_card(args.cn, args.en, args.output, args.debug)


if __name__ == "__main__":
    main()
