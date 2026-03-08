"""
Avatar Data Extractor for PVF - PVF Avatar 数据提取器

基于 avatar_extractor 模块的封装，提供命令行接口和简化的使用方式。
"""

import logging
from pathlib import Path
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import EQUIPMENT_TAGS_TSV
from modules.avatar_extractor import AvatarExtractor

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pvf_parser.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def extract_avatar_data(
    output_file: Optional[Path] = None,
    lst_file_path: str = "equipment/equipment.lst"
) -> bool:
    """
    提取 PVF 中的 avatar 数据
    
    Args:
        output_file: 输出 TSV 文件路径，默认为 EQUIPMENT_TAGS_TSV
        lst_file_path: equipment.lst 文件路径
        
    Returns:
        True 如果成功
        
    Example:
        >>> extract_avatar_data()
        >>> extract_avatar_data(Path("output/avatar_data.tsv"))
    """
    output_file = output_file or EQUIPMENT_TAGS_TSV
    
    logger.info(f"开始提取 avatar 数据，输出到: {output_file}")
    
    extractor = AvatarExtractor()
    
    # 1. 解析 lst
    if not extractor.parse_equipment_lst(lst_file_path):
        logger.error("解析 lst 失败")
        return False
    
    # 2. 批量提取
    extractor.extract_all()
    
    # 3. 保存结果
    extractor.save_to_tsv(output_file)
    
    # 4. 打印统计
    stats = extractor.get_stats()
    logger.info(
        f"\n提取完成:\n"
        f"  总计: {stats['total_files']}\n"
        f"  成功: {stats['parsed_files']}\n"
        f"  失败: {stats['failed_files']}\n"
        f"  成功率: {stats['success_rate']}\n"
        f"  耗时: {stats['elapsed_time']}"
    )
    
    return True


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='PVF Avatar 数据提取器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 默认提取并输出到默认路径
  python avatar_data_extractor_pvf.py
  
  # 指定输出文件
  python avatar_data_extractor_pvf.py -o output/avatar_data.tsv
  
  # 指定 lst 文件路径
  python avatar_data_extractor_pvf.py --lst equipment/equipment.lst
        """
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=str(EQUIPMENT_TAGS_TSV),
        help=f'输出 TSV 文件路径 (默认: {EQUIPMENT_TAGS_TSV})'
    )
    
    parser.add_argument(
        '--lst',
        type=str,
        default="equipment/equipment.lst",
        help='equipment.lst 文件路径 (默认: equipment/equipment.lst)'
    )
    
    parser.add_argument(
        '--json',
        type=str,
        default=None,
        help='额外输出 JSON 文件路径 (可选)'
    )
    
    args = parser.parse_args()
    
    output_path = Path(args.output)
    
    # 创建提取器
    extractor = AvatarExtractor()
    
    # 执行提取流程
    success = extractor.run(output_file=output_path)
    
    # 如果指定了 JSON 输出，额外保存
    if success and args.json:
        json_path = Path(args.json)
        extractor.save_to_json(json_path)
    
    if success:
        print("\n✓ Avatar 数据提取完成")
        return 0
    else:
        print("\n✗ Avatar 数据提取失败")
        return 1


if __name__ == "__main__":
    exit(main())
