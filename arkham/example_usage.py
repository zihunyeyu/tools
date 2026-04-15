#!/usr/bin/env python3
"""
卡牌文本替换工具使用示例

这个脚本演示了如何程序化地使用卡牌文本替换功能
"""

import os
from pathlib import Path

# 导入替换工具
from smart_card_replacer import process_card, batch_process


def example_single_card():
    """示例1: 处理单张卡牌"""
    
    # 配置路径
    chinese_card = "./my_cards/chinese/01001.jpg"  # 中文卡图（拍照）
    english_card = "./my_cards/english/01001.png"  # 英文卡图（清晰）
    output_card = "./output/01001_cn.png"          # 输出路径
    
    # 确保目录存在
    os.makedirs(os.path.dirname(output_card), exist_ok=True)
    
    # 检查文件是否存在
    if not os.path.exists(chinese_card):
        print(f"错误: 中文卡图不存在: {chinese_card}")
        print("请确保路径正确，或修改示例中的路径")
        return
    
    if not os.path.exists(english_card):
        print(f"错误: 英文卡图不存在: {english_card}")
        print("请确保路径正确，或修改示例中的路径")
        return
    
    # 处理卡牌
    print("=" * 50)
    print("示例1: 处理单张卡牌")
    print("=" * 50)
    
    try:
        result_path = process_card(
            cn_path=chinese_card,
            en_path=english_card,
            output_path=output_card,
            debug=True  # 输出调试信息
        )
        print(f"\n成功! 输出文件: {result_path}")
    except Exception as e:
        print(f"处理失败: {e}")


def example_batch_processing():
    """示例2: 批量处理"""
    
    # 配置目录
    chinese_dir = "./my_cards/chinese"   # 中文卡图目录
    english_dir = "./my_cards/english"   # 英文卡图目录
    output_dir = "./output"              # 输出目录
    
    # 检查目录是否存在
    if not os.path.exists(chinese_dir):
        print(f"错误: 中文卡图目录不存在: {chinese_dir}")
        print("请确保目录正确，或修改示例中的路径")
        return
    
    if not os.path.exists(english_dir):
        print(f"错误: 英文卡图目录不存在: {english_dir}")
        print("请确保目录正确，或修改示例中的路径")
        return
    
    # 批量处理
    print("=" * 50)
    print("示例2: 批量处理卡牌")
    print("=" * 50)
    
    batch_process(
        cn_dir=chinese_dir,
        en_dir=english_dir,
        output_dir=output_dir,
        debug=False  # 不输出详细调试信息
    )


def example_custom_processing():
    """示例3: 自定义处理流程"""
    
    from smart_card_replacer import (
        AdvancedOCR, CardLayoutAnalyzer, smart_match_regions,
        advanced_inpaint, smart_draw_text, detect_region_color
    )
    from PIL import Image
    
    print("=" * 50)
    print("示例3: 自定义处理流程")
    print("=" * 50)
    
    # 1. 加载图像
    cn_path = "./my_cards/chinese/01001.jpg"
    en_path = "./my_cards/english/01001.png"
    
    if not os.path.exists(cn_path) or not os.path.exists(en_path):
        print("示例文件不存在，跳过此示例")
        return
    
    img_cn = Image.open(cn_path).convert('RGB')
    img_en = Image.open(en_path).convert('RGB')
    
    # 2. 创建 OCR 实例
    ocr = AdvancedOCR('ch')
    
    # 3. 检测文本
    print("检测文本...")
    regions = ocr.detect(cn_path)
    
    # 4. 打印检测到的文本
    print(f"\n检测到 {len(regions)} 个文本区域:")
    for i, region in enumerate(regions, 1):
        print(f"  [{i}] {region.text[:30]}... "
              f"(位置: {region.bbox}, 置信度: {region.confidence:.2f})")
    
    # 5. 可以在这里添加自定义逻辑...
    # 例如：只处理特定区域、过滤某些文本等


def create_example_structure():
    """创建示例目录结构"""
    
    dirs = [
        "./my_cards/chinese",
        "./my_cards/english",
        "./output",
        "./debug"
    ]
    
    print("=" * 50)
    print("创建示例目录结构")
    print("=" * 50)
    
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"  创建目录: {d}")
    
    print("\n目录结构:")
    print("  ./my_cards/")
    print("    ├── chinese/    # 放置中文卡图（拍照/扫描）")
    print("    └── english/    # 放置英文卡图（清晰）")
    print("  ./output/         # 输出目录")
    print("  ./debug/          # 调试信息目录")
    
    print("\n请按上述结构放置卡牌图片，然后运行示例脚本")


def main():
    """主函数"""
    
    import sys
    
    print("卡牌文本替换工具 - 使用示例")
    print("=" * 50)
    print()
    print("可用示例:")
    print("  1. 处理单张卡牌")
    print("  2. 批量处理卡牌")
    print("  3. 自定义处理流程")
    print("  4. 创建示例目录结构")
    print()
    
    if len(sys.argv) > 1:
        choice = sys.argv[1]
    else:
        choice = input("请选择示例 (1-4): ").strip()
    
    if choice == '1':
        example_single_card()
    elif choice == '2':
        example_batch_processing()
    elif choice == '3':
        example_custom_processing()
    elif choice == '4':
        create_example_structure()
    else:
        print("无效选择")
        print()
        print("命令行用法:")
        print("  python example_usage.py 1  # 单张处理")
        print("  python example_usage.py 2  # 批量处理")


if __name__ == "__main__":
    main()
