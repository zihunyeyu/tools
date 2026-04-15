#!/usr/bin/env python3
"""
智能卡牌文本替换工具 - 针对 Arkham Horror LCG 等桌游优化

特点:
1. 基于卡牌固定布局的精确区域定位
2. 更智能的文本匹配算法
3. 更好的字体渲染和样式保持
4. 支持标题、副标题、效果文本等不同区域的差异化处理

使用方法:
    # 单张处理
    python smart_card_replacer.py --cn ./chinese_card.jpg --en ./english_card.png --output ./result.png
    
    # 批量处理
    python smart_card_replacer.py --batch --cn-dir ./chinese_cards/ --en-dir ./english_cards/ --output-dir ./output/
"""

import argparse
import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Tuple, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


class TextType(Enum):
    """文本类型枚举"""
    TITLE = "title"           # 卡牌标题
    SUBTITLE = "subtitle"     # 副标题/类型
    TRAITS = "traits"         # 特性标签
    COST = "cost"             # 费用/等级
    TEXT = "text"             # 主要效果文本
    FLAVOR = "flavor"         # 风味文本
    ARTIST = "artist"         # 画师信息
    VICTORY = "victory"       # 胜利点数


@dataclass
class TextRegion:
    """文本区域数据类"""
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    text: str
    confidence: float
    text_type: TextType = TextType.TEXT
    
    @property
    def center(self) -> Tuple[int, int]:
        x, y, w, h = self.bbox
        return (x + w // 2, y + h // 2)
    
    @property
    def area(self) -> int:
        x, y, w, h = self.bbox
        return w * h


class CardLayoutAnalyzer:
    """
    卡牌布局分析器
    分析卡牌的固定布局结构
    """
    
    # Arkham Horror LCG 典型布局比例 (相对于卡牌尺寸)
    # 这些值可以根据实际卡牌调整
    LAYOUT_ZONES = {
        'title': {'y_range': (0.02, 0.12), 'x_range': (0.15, 0.85)},
        'cost': {'y_range': (0.02, 0.12), 'x_range': (0.02, 0.15)},
        'subtitle': {'y_range': (0.55, 0.65), 'x_range': (0.10, 0.90)},
        'traits': {'y_range': (0.60, 0.68), 'x_range': (0.10, 0.90)},
        'text': {'y_range': (0.65, 0.90), 'x_range': (0.08, 0.92)},
        'victory': {'y_range': (0.90, 0.98), 'x_range': (0.70, 0.95)},
        'artist': {'y_range': (0.92, 0.99), 'x_range': (0.05, 0.40)},
    }
    
    def __init__(self, image_width: int, image_height: int):
        self.width = image_width
        self.height = image_height
    
    def get_zone_bbox(self, zone_name: str) -> Tuple[int, int, int, int]:
        """获取区域的边界框"""
        zone = self.LAYOUT_ZONES.get(zone_name, {})
        y_range = zone.get('y_range', (0, 1))
        x_range = zone.get('x_range', (0, 1))
        
        x1 = int(x_range[0] * self.width)
        y1 = int(y_range[0] * self.height)
        x2 = int(x_range[1] * self.width)
        y2 = int(y_range[1] * self.height)
        
        return (x1, y1, x2 - x1, y2 - y1)
    
    def classify_region(self, region: TextRegion) -> TextType:
        """根据位置分类文本区域"""
        cx, cy = region.center
        
        # 转换为相对坐标
        rx = cx / self.width
        ry = cy / self.height
        
        # 根据位置判断类型
        if 0.02 <= ry <= 0.12 and 0.02 <= rx <= 0.15:
            return TextType.COST
        elif 0.02 <= ry <= 0.12 and rx > 0.15:
            return TextType.TITLE
        elif 0.55 <= ry <= 0.65:
            return TextType.SUBTITLE
        elif 0.60 <= ry <= 0.68:
            return TextType.TRAITS
        elif 0.90 <= ry <= 0.98 and rx > 0.70:
            return TextType.VICTORY
        elif 0.92 <= ry <= 0.99 and rx < 0.40:
            return TextType.ARTIST
        elif 0.65 <= ry <= 0.90:
            # 判断是否是风味文本（通常斜体，可能包含引号）
            if '」' in region.text or '"' in region.text or region.text.count('\n') > 1:
                return TextType.FLAVOR
            return TextType.TEXT
        
        return TextType.TEXT
    
    def is_in_zone(self, region: TextRegion, zone_name: str) -> bool:
        """检查区域是否在指定区域内"""
        cx, cy = region.center
        zone = self.LAYOUT_ZONES.get(zone_name, {})
        y_range = zone.get('y_range', (0, 1))
        x_range = zone.get('x_range', (0, 1))
        
        ry = cy / self.height
        rx = cx / self.width
        
        return (y_range[0] <= ry <= y_range[1] and 
                x_range[0] <= rx <= x_range[1])


class AdvancedOCR:
    """
    高级 OCR 类，支持更好的文本检测
    """
    
    def __init__(self, lang: str = 'ch'):
        try:
            from paddleocr import PaddleOCR
        except ImportError:
            raise ImportError("需要安装 PaddleOCR: pip install paddleocr")
        
        self.ocr = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            show_log=False,
            use_gpu=False
        )
    
    def detect(self, image_path: str) -> List[TextRegion]:
        """检测图像中的文本"""
        result = self.ocr.ocr(image_path, cls=True)
        
        regions = []
        if result and result[0]:
            for line in result[0]:
                if line:
                    bbox_points = line[0]
                    text = line[1][0]
                    confidence = line[1][1]
                    
                    # 计算边界框
                    xs = [p[0] for p in bbox_points]
                    ys = [p[1] for p in bbox_points]
                    x, y = int(min(xs)), int(min(ys))
                    w, h = int(max(xs) - x), int(max(ys) - y)
                    
                    regions.append(TextRegion(
                        bbox=(x, y, w, h),
                        text=text,
                        confidence=confidence
                    ))
        
        return regions


def smart_match_regions(cn_regions: List[TextRegion], 
                        en_regions: List[TextRegion],
                        layout_cn: CardLayoutAnalyzer,
                        layout_en: CardLayoutAnalyzer) -> List[Tuple[TextRegion, TextRegion]]:
    """
    智能匹配中文和英文文本区域
    
    策略:
    1. 首先基于布局类型匹配
    2. 然后基于相对位置进行精细匹配
    3. 对未匹配的区域使用距离匹配
    """
    matches = []
    used_en_indices = set()
    
    # 为所有区域分类
    for cn_reg in cn_regions:
        cn_reg.text_type = layout_cn.classify_region(cn_reg)
    for en_reg in en_regions:
        en_reg.text_type = layout_en.classify_region(en_reg)
    
    # 第一步：按类型精确匹配
    for cn_reg in cn_regions:
        best_match = None
        best_score = -1
        
        for i, en_reg in enumerate(en_regions):
            if i in used_en_indices:
                continue
            
            # 类型匹配检查
            if cn_reg.text_type != en_reg.text_type:
                continue
            
            # 计算相似度分数
            score = calculate_match_score(cn_reg, en_reg, layout_cn, layout_en)
            
            if score > best_score:
                best_score = score
                best_match = (i, en_reg)
        
        if best_match and best_score > 0.5:
            used_en_indices.add(best_match[0])
            matches.append((cn_reg, best_match[1]))
    
    # 第二步：为未匹配的中文区域寻找最佳匹配
    matched_cn = set(id(m[0]) for m in matches)
    for cn_reg in cn_regions:
        if id(cn_reg) in matched_cn:
            continue
        
        best_match = None
        best_distance = float('inf')
        
        cn_center = cn_reg.center
        cn_rel_x = cn_center[0] / layout_cn.width
        cn_rel_y = cn_center[1] / layout_cn.height
        
        for i, en_reg in enumerate(en_regions):
            if i in used_en_indices:
                continue
            
            en_center = en_reg.center
            en_rel_x = en_center[0] / layout_en.width
            en_rel_y = en_center[1] / layout_en.height
            
            # 计算相对距离
            distance = np.sqrt((cn_rel_x - en_rel_x)**2 + (cn_rel_y - en_rel_y)**2)
            
            if distance < best_distance:
                best_distance = distance
                best_match = (i, en_reg)
        
        # 只有当距离足够近时才匹配
        if best_match and best_distance < 0.30:  # 30% 图像尺寸，放宽阈值
            used_en_indices.add(best_match[0])
            matches.append((cn_reg, best_match[1]))
    
    return matches


def calculate_match_score(cn_reg: TextRegion, en_reg: TextRegion,
                          layout_cn: CardLayoutAnalyzer,
                          layout_en: CardLayoutAnalyzer) -> float:
    """
    计算两个区域的匹配分数
    """
    # 相对位置相似度
    cn_center = cn_reg.center
    en_center = en_reg.center
    
    cn_rel_x = cn_center[0] / layout_cn.width
    cn_rel_y = cn_center[1] / layout_cn.height
    en_rel_x = en_center[0] / layout_en.width
    en_rel_y = en_center[1] / layout_en.height
    
    position_score = 1.0 - np.sqrt((cn_rel_x - en_rel_x)**2 + (cn_rel_y - en_rel_y)**2)
    
    # 大小相似度
    cn_area = cn_reg.area / (layout_cn.width * layout_cn.height)
    en_area = en_reg.area / (layout_en.width * layout_en.height)
    size_score = 1.0 - min(abs(cn_area - en_area) / max(cn_area, en_area, 0.001), 1.0)
    
    # 综合分数
    return position_score * 0.7 + size_score * 0.3


def advanced_inpaint(image: Image.Image, bbox: Tuple[int, int, int, int],
                     method: str = 'telea') -> Image.Image:
    """
    高级图像修复
    
    Args:
        method: 'telea', 'ns', 或 'gaussian'
    """
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    
    x, y, w, h = bbox
    margin = 5
    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(img_cv.shape[1], x + w + margin)
    y2 = min(img_cv.shape[0], y + h + margin)
    
    # 创建掩码
    mask = np.zeros(img_cv.shape[:2], dtype=np.uint8)
    mask[y1:y2, x1:x2] = 255
    
    if method == 'telea':
        result = cv2.inpaint(img_cv, mask, 5, cv2.INPAINT_TELEA)
    elif method == 'ns':
        result = cv2.inpaint(img_cv, mask, 5, cv2.INPAINT_NS)
    else:
        # 使用高斯模糊作为简单修复
        roi = img_cv[y1:y2, x1:x2]
        roi = cv2.GaussianBlur(roi, (15, 15), 0)
        result = img_cv.copy()
        result[y1:y2, x1:x2] = roi
    
    return Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))


def smart_draw_text(image: Image.Image, text: str, 
                    bbox: Tuple[int, int, int, int],
                    text_type: TextType,
                    text_color: Optional[Tuple] = None) -> Image.Image:
    """
    智能绘制文本，根据不同类型使用不同样式
    """
    if text_color is None:
        text_color = (0, 0, 0)
    
    x, y, w, h = bbox
    draw = ImageDraw.Draw(image)
    
    # 根据文本类型选择字体和样式
    if text_type == TextType.TITLE:
        font_size = min(int(h * 0.8), int(w / max(len(text), 1) * 1.5))
        font_size = max(16, min(font_size, 48))
    elif text_type == TextType.COST:
        font_size = min(int(h * 0.85), 36)
    elif text_type == TextType.TRAITS:
        font_size = min(int(h * 0.7), 20)
    elif text_type == TextType.FLAVOR:
        font_size = min(int(h * 0.6), 16)
    else:
        font_size = min(int(h * 0.7), int(w / max(len(text), 1) * 1.2))
        font_size = max(10, min(font_size, 24))
    
    font = find_best_font(font_size, text_type)
    
    # 处理多行文本
    lines = text.split('\n')
    if len(lines) == 1 and len(text) > w / font_size * 1.5:
        # 自动换行
        lines = wrap_text(text, w, font, draw)
    
    # 计算总高度
    line_height = font_size * 1.2
    total_height = len(lines) * line_height
    
    # 起始 Y 位置（垂直居中）
    start_y = y + (h - total_height) // 2
    
    # 绘制每一行
    for i, line in enumerate(lines):
        try:
            bbox_text = draw.textbbox((0, 0), line, font=font)
            text_w = bbox_text[2] - bbox_text[0]
        except:
            text_w, _ = draw.textsize(line, font=font)
        
        text_x = x + (w - text_w) // 2
        text_y = start_y + i * line_height
        
        # 添加描边效果
        stroke_color = (255, 255, 255) if sum(text_color) < 384 else (0, 0, 0)
        stroke_width = 1 if text_type != TextType.TITLE else 2
        
        for dx in range(-stroke_width, stroke_width + 1):
            for dy in range(-stroke_width, stroke_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((text_x + dx, text_y + dy), line, font=font, fill=stroke_color)
        
        draw.text((text_x, text_y), line, font=font, fill=text_color)
    
    return image


def wrap_text(text: str, max_width: int, font: ImageFont.FreeTypeFont, 
              draw: ImageDraw.Draw) -> List[str]:
    """自动换行"""
    words = text
    lines = []
    current_line = ""
    
    for char in words:
        test_line = current_line + char
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
        except:
            width, _ = draw.textsize(test_line, font=font)
        
        if width <= max_width * 0.9:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = char
    
    if current_line:
        lines.append(current_line)
    
    return lines if lines else [text]


def find_best_font(font_size: int, text_type: TextType = TextType.TEXT) -> ImageFont.FreeTypeFont:
    """寻找最合适的字体"""
    
    # 根据文本类型选择不同字体
    if text_type == TextType.TITLE:
        font_paths = [
            "C:/Windows/Fonts/simhei.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
    elif text_type == TextType.FLAVOR:
        # 风味文本可以使用楷体或斜体
        font_paths = [
            "C:/Windows/Fonts/simkai.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        ]
    else:
        font_paths = [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simsun.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, font_size)
            except:
                continue
    
    return ImageFont.load_default()


def detect_region_color(image: Image.Image, bbox: Tuple[int, int, int, int],
                        sample_margin: int = 3) -> Tuple:
    """
    检测文本区域的典型颜色
    在区域边缘采样，避免纯文本颜色
    """
    x, y, w, h = bbox
    
    # 采样几个边缘点
    samples = []
    
    # 上边缘
    if y > sample_margin:
        samples.append((x + w//2, y - sample_margin))
    
    # 下边缘
    if y + h + sample_margin < image.height:
        samples.append((x + w//2, y + h + sample_margin))
    
    # 左边缘
    if x > sample_margin:
        samples.append((x - sample_margin, y + h//2))
    
    # 右边缘
    if x + w + sample_margin < image.width:
        samples.append((x + w + sample_margin, y + h//2))
    
    if not samples:
        return (0, 0, 0)
    
    # 计算平均颜色
    pixels = [image.getpixel((sx, sy)) for sx, sy in samples if 0 <= sx < image.width and 0 <= sy < image.height]
    if not pixels:
        return (0, 0, 0)
    
    avg_color = tuple(int(sum(c[i] for c in pixels) / len(pixels)) for i in range(3))
    
    # 根据背景亮度决定文本颜色
    brightness = sum(avg_color) / 3
    if brightness > 200:
        return (0, 0, 0)  # 浅色背景 -> 黑色文本
    elif brightness < 55:
        return (255, 255, 255)  # 深色背景 -> 白色文本
    else:
        return (0, 0, 0)  # 默认黑色


def process_card(cn_path: str, en_path: str, output_path: str,
                 debug: bool = False, save_debug: Optional[str] = None):
    """
    处理单张卡牌
    """
    print(f"\n处理: {Path(cn_path).name}")
    print(f"  中文: {cn_path}")
    print(f"  英文: {en_path}")
    
    # 1. 加载图像
    img_cn = Image.open(cn_path).convert('RGB')
    img_en = Image.open(en_path).convert('RGB')
    
    # 统一尺寸
    if img_cn.size != img_en.size:
        print(f"  调整尺寸: {img_cn.size} -> {img_en.size}")
        img_cn = img_cn.resize(img_en.size, Image.Resampling.LANCZOS)
    
    # 2. 创建布局分析器
    layout_cn = CardLayoutAnalyzer(img_cn.width, img_cn.height)
    layout_en = CardLayoutAnalyzer(img_en.width, img_en.height)
    
    # 3. OCR 检测
    print("  检测中文文本...")
    ocr_cn = AdvancedOCR('ch')
    cn_regions = ocr_cn.detect(cn_path)
    
    print("  检测英文文本...")
    ocr_en = AdvancedOCR('en')
    en_regions = ocr_en.detect(en_path)
    
    print(f"  发现: {len(cn_regions)} 个中文区域, {len(en_regions)} 个英文区域")
    
    # 4. 智能匹配
    print("  匹配文本区域...")
    matches = smart_match_regions(cn_regions, en_regions, layout_cn, layout_en)
    print(f"  成功匹配: {len(matches)} 对")
    
    # 5. 执行替换
    result = img_en.copy()
    
    for cn_reg, en_reg in matches:
        # 清除原文本
        result = advanced_inpaint(result, en_reg.bbox, 'telea')
        
        # 检测文本颜色
        text_color = detect_region_color(result, en_reg.bbox)
        
        # 绘制中文文本
        result = smart_draw_text(result, cn_reg.text, en_reg.bbox, 
                                 cn_reg.text_type, text_color)
    
    # 保存结果
    result.save(output_path, 'PNG', quality=95)
    print(f"  输出: {output_path}")
    
    # 保存调试信息
    if debug or save_debug:
        debug_info = {
            'file': Path(cn_path).name,
            'matches': len(matches),
            'regions': [
                {
                    'cn_text': cn_reg.text,
                    'type': cn_reg.text_type.value,
                    'en_bbox': en_reg.bbox
                }
                for cn_reg, en_reg in matches
            ]
        }
        
        if save_debug:
            debug_path = Path(save_debug) / f"{Path(cn_path).stem}_debug.json"
            debug_path.write_text(json.dumps(debug_info, ensure_ascii=False, indent=2))
    
    return output_path


def batch_process(cn_dir: str, en_dir: str, output_dir: str, 
                 debug: bool = False):
    """
    批量处理卡牌
    """
    cn_dir = Path(cn_dir)
    en_dir = Path(en_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 支持的中英文卡牌命名对应
    cn_files = sorted(cn_dir.glob('*.jpg')) + sorted(cn_dir.glob('*.png')) + sorted(cn_dir.glob('*.jpeg'))
    
    print(f"\n批量处理:")
    print(f"  中文目录: {cn_dir}")
    print(f"  英文目录: {en_dir}")
    print(f"  输出目录: {output_dir}")
    print(f"  找到 {len(cn_files)} 张中文卡图")
    print()
    
    success = 0
    failed = 0
    
    for cn_file in cn_files:
        # 尝试多种命名方式查找对应英文卡图
        en_candidates = [
            en_dir / (cn_file.stem + '.png'),
            en_dir / (cn_file.stem + '.jpg'),
            en_dir / cn_file.name,
        ]
        
        # 尝试去掉中文特定的后缀
        stem_clean = re.sub(r'[_-]cn$', '', cn_file.stem, flags=re.IGNORECASE)
        en_candidates.extend([
            en_dir / (stem_clean + '.png'),
            en_dir / (stem_clean + '.jpg'),
        ])
        
        en_file = None
        for candidate in en_candidates:
            if candidate.exists():
                en_file = candidate
                break
        
        if en_file:
            output_file = output_dir / (cn_file.stem + '_replaced.png')
            try:
                process_card(str(cn_file), str(en_file), str(output_file), debug)
                success += 1
            except Exception as e:
                print(f"  [错误] {cn_file.name}: {e}")
                failed += 1
        else:
            print(f"  [跳过] 未找到对应英文卡图: {cn_file.name}")
            failed += 1
    
    print(f"\n处理完成: 成功 {success}, 失败 {failed}")


def main():
    parser = argparse.ArgumentParser(description='智能卡牌文本替换工具')
    parser.add_argument('--cn', type=str, help='中文卡图路径')
    parser.add_argument('--en', type=str, help='英文卡图路径')
    parser.add_argument('--output', type=str, help='输出路径')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    parser.add_argument('--save-debug', type=str, help='保存调试信息的目录')
    
    parser.add_argument('--batch', action='store_true', help='批量处理')
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
        print(f"[错误] 缺少依赖: {e}")
        print("请安装: pip install paddleocr opencv-python numpy pillow")
        return
    
    if args.batch:
        if not args.cn_dir or not args.en_dir:
            print("[错误] 批量处理需要 --cn-dir 和 --en-dir 参数")
            return
        batch_process(args.cn_dir, args.en_dir, args.output_dir, args.debug)
    else:
        if not args.cn or not args.en or not args.output:
            print("[错误] 需要 --cn, --en, --output 参数")
            print("\n示例:")
            print(f"  python {__file__} --cn ./chinese.jpg --en ./english.png --output ./result.png")
            return
        
        process_card(args.cn, args.en, args.output, args.debug, args.save_debug)


if __name__ == "__main__":
    main()
