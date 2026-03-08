#!/usr/bin/env python3
"""
装扮表套装去重工具 - 入口脚本

处理逻辑：
1. 按部位重复删除：保留第一个，删除后续部位重复的
2. 同名套装加后缀：对同名套装从第一个开始加 [款式X] 后缀
   只出现一次的套装不加后缀

只在各个职业单个文件内部处理，不跨文件比较。

用法:
    python deduplicate_suits.py
    python deduplicate_suits.py -d "D:/DOF/output/Avatar"
    python deduplicate_suits.py -d "D:/DOF/output/Avatar" -o "D:/DOF/output/Avatar_Clean"
    python deduplicate_suits.py --details
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from modules.suit_deduplicator import SuitDeduplicator


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='装扮表套装去重工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
处理逻辑:
  1. 按部位重复删除：保留第一个，删除后续部位重复的
  2. 同名套装加后缀：对同名套装从第一个开始加 [款式X] 后缀
     只出现一次的套装不加后缀

示例:
  # 使用默认路径
  python deduplicate_suits.py
  
  # 指定输入目录
  python deduplicate_suits.py -d "D:/DOF/output/Avatar"
  
  # 指定输入和输出目录
  python deduplicate_suits.py -d "D:/DOF/output/Avatar" -o "D:/DOF/output/Avatar_Clean"
  
  # 显示详细处理信息
  python deduplicate_suits.py --details
        """
    )
    
    parser.add_argument('-d', '--directory', type=str,
                        help='装扮表所在目录 (默认: config.AVATAR_TABLE_BASE_PATH)')
    parser.add_argument('-o', '--output', type=str,
                        help='输出目录 (默认: 输入目录下的 Deduplicated 子目录)')
    parser.add_argument('--details', action='store_true',
                        help='显示详细处理信息')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='显示详细日志')
    
    args = parser.parse_args()
    
    # 设置日志
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 确定输入目录
    if args.directory:
        input_dir = Path(args.directory)
    else:
        try:
            from config import AVATAR_TABLE_BASE_PATH
            input_dir = Path(AVATAR_TABLE_BASE_PATH)
        except ImportError:
            print("错误: 请指定 -d 参数，或者确保 config.py 存在")
            sys.exit(1)
    
    # 确定输出目录
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = input_dir / "Deduplicated"
    
    print("=" * 70)
    print("装扮表套装去重工具")
    print("=" * 70)
    print(f"输入目录: {input_dir}")
    print(f"输出目录: {output_dir}")
    print("处理逻辑:")
    print("  1. 删除部位重复的套装（保留第一个）")
    print("  2. 同名套装加 [款式X] 后缀（从第一个开始，只出现一次的不加）")
    print("-" * 70)
    
    # 创建去重器并执行
    deduplicator = SuitDeduplicator()
    file_count = deduplicator.process_directory(input_dir)
    
    if file_count == 0:
        print("错误: 没有找到任何装扮表文件")
        sys.exit(1)
    
    # 显示汇总
    print()
    print(deduplicator.get_summary())
    
    # 显示详细信息
    if args.details:
        print()
        print(deduplicator.get_details())
    
    # 导出结果
    print()
    print("正在导出处理后的文件...")
    deduplicator.export_results(output_dir, input_dir)
    
    print()
    print("=" * 70)
    print("处理完成!")
    print(f"结果已保存到: {output_dir}")
    print("=" * 70)


if __name__ == '__main__':
    main()
