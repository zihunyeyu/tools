"""
Suit Deduplicator - 套装去重器

处理逻辑：
1. 按部位重复删除：保留第一个，删除后续部位重复的
2. 同名套装加后缀：对同名套装从第一个开始加 [款式X] 后缀，只出现一次的不加

只在各个职业单个文件内部处理，不跨文件比较。
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import Counter

logger = logging.getLogger(__name__)


@dataclass
class Suit:
    """套装数据类"""
    name: str
    cap: int
    hair: int
    face: int
    neck: int
    coat: int
    pants: int
    belt: int
    shoes: int
    skin: int
    line_number: int = 0
    
    def get_parts_tuple(self) -> Tuple[int, ...]:
        """获取部位代码元组，用于比较"""
        return (self.cap, self.hair, self.face, self.neck, 
                self.coat, self.pants, self.belt, self.shoes, self.skin)
    
    def to_line(self) -> str:
        """转换为文件行格式"""
        return f"{self.name},{self.cap},{self.hair},{self.face},{self.neck}," \
               f"{self.coat},{self.pants},{self.belt},{self.shoes},{self.skin}"


@dataclass
class FileProcessResult:
    """单个文件的处理结果"""
    source_file: str
    original_count: int
    after_dedup_count: int  # 部位去重后
    final_count: int  # 最终数量（应该和after_dedup_count相同）
    deleted_count: int  # 删除的部位重复数量
    renamed_count: int  # 改名的套装数量（出现多次的套装总数）
    suits: List[Suit] = field(default_factory=list)


class SuitDeduplicator:
    """套装去重器"""
    
    def __init__(self):
        self.file_results: List[FileProcessResult] = []
    
    def parse_suit_line(self, line: str, line_number: int = 0) -> Optional[Suit]:
        """解析套装行，格式: 套装名称,cap,hair,face,neck,coat,pants,belt,shoes,skin"""
        line = line.strip()
        if not line or line.startswith('['):
            return None
        
        parts = line.split(',')
        if len(parts) < 10:
            return None
        
        try:
            name = parts[0].strip()
            if not name or name == '默认套装':
                return None
            
            return Suit(
                name=name,
                cap=int(parts[1]) if parts[1] != '-1' else -1,
                hair=int(parts[2]) if parts[2] != '-1' else -1,
                face=int(parts[3]) if parts[3] != '-1' else -1,
                neck=int(parts[4]) if parts[4] != '-1' else -1,
                coat=int(parts[5]) if parts[5] != '-1' else -1,
                pants=int(parts[6]) if parts[6] != '-1' else -1,
                belt=int(parts[7]) if parts[7] != '-1' else -1,
                shoes=int(parts[8]) if parts[8] != '-1' else -1,
                skin=int(parts[9]) if parts[9] != '-1' else -1,
                line_number=line_number
            )
        except (ValueError, IndexError):
            return None
    
    def deduplicate_by_parts(self, suits: List[Suit]) -> Tuple[List[Suit], int]:
        """
        按部位重复去重，保留第一个，删除后续重复的
        
        Returns:
            (去重后的列表, 删除的数量)
        """
        seen_parts: Dict[Tuple[int, ...], bool] = {}
        unique_suits: List[Suit] = []
        deleted = 0
        
        for suit in suits:
            parts_tuple = suit.get_parts_tuple()
            if parts_tuple in seen_parts:
                # 部位重复，跳过（删除）
                deleted += 1
                logger.debug(f"删除部位重复: {suit.name} (行{suit.line_number})")
            else:
                # 保留
                seen_parts[parts_tuple] = True
                unique_suits.append(suit)
        
        return unique_suits, deleted
    
    def rename_duplicate_names(self, suits: List[Suit]) -> Tuple[List[Suit], int]:
        """
        对同名套装从第一个开始加 [款式X] 后缀
        只出现一次的不加后缀
        
        Returns:
            (处理后的列表, 改名的数量)
        """
        # 统计每个名字的出现次数
        name_counts = Counter(suit.name for suit in suits)
        
        # 记录每个名字当前处理到第几个
        name_indices: Dict[str, int] = {}
        
        renamed_count = 0
        processed_suits: List[Suit] = []
        
        for suit in suits:
            name = suit.name
            if name_counts[name] > 1:
                # 出现多次，需要加后缀
                if name not in name_indices:
                    name_indices[name] = 1
                else:
                    name_indices[name] += 1
                
                # 添加后缀 [款式X]
                suit.name = f"{name}[款式{name_indices[name]}]"
                renamed_count += 1
            # 如果只出现一次，保持原名
            processed_suits.append(suit)
        
        return processed_suits, renamed_count
    
    def process_file(self, file_path: Path) -> FileProcessResult:
        """处理单个文件"""
        suits: List[Suit] = []
        
        try:
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                lines = f.readlines()
            
            in_suit_section = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                
                if stripped == '[suit]':
                    in_suit_section = True
                    continue
                
                if in_suit_section and stripped.startswith('[') and stripped != '[suit]':
                    in_suit_section = False
                    continue
                
                if in_suit_section:
                    suit = self.parse_suit_line(line, line_number=i + 1)
                    if suit:
                        suits.append(suit)
            
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            return FileProcessResult(
                source_file=file_path.name,
                original_count=0,
                after_dedup_count=0,
                final_count=0,
                deleted_count=0,
                renamed_count=0
            )
        
        original_count = len(suits)
        
        # 第一步：按部位去重（删除）
        suits_after_dedup, deleted_count = self.deduplicate_by_parts(suits)
        after_dedup_count = len(suits_after_dedup)
        
        # 第二步：同名套装加后缀
        final_suits, renamed_count = self.rename_duplicate_names(suits_after_dedup)
        final_count = len(final_suits)
        
        result = FileProcessResult(
            source_file=file_path.name,
            original_count=original_count,
            after_dedup_count=after_dedup_count,
            final_count=final_count,
            deleted_count=deleted_count,
            renamed_count=renamed_count,
            suits=final_suits
        )
        
        logger.info(f"{file_path.name}: 原始 {original_count} 个, "
                   f"删除 {deleted_count} 个, 改名 {renamed_count} 个, 最终 {final_count} 个")
        return result
    
    def process_directory(self, directory: Path, pattern: str = "*装扮表.txt") -> int:
        """处理目录下的所有文件"""
        if not directory.exists():
            logger.error(f"目录不存在: {directory}")
            return 0
        
        self.file_results.clear()
        files = list(directory.glob(pattern))
        
        for file_path in files:
            result = self.process_file(file_path)
            self.file_results.append(result)
        
        return len(files)
    
    def export_results(self, output_dir: Path, input_dir: Path):
        """导出处理结果到文件，保留原文件的其他内容"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for result in self.file_results:
            if result.original_count == 0:
                continue
            
            # 读取原文件
            input_path = input_dir / result.source_file
            try:
                with open(input_path, 'r', encoding='gbk', errors='ignore') as f:
                    lines = f.readlines()
            except Exception as e:
                logger.error(f"读取原文件失败 {input_path}: {e}")
                continue
            
            # 构建新的 [suit] 内容
            new_suit_lines = [suit.to_line() for suit in result.suits]
            
            # 替换原文件中的 [suit] 部分
            output_lines = []
            in_suit_section = False
            
            for line in lines:
                stripped = line.strip()
                
                # 检测 [suit] section 开始
                if stripped == '[suit]':
                    in_suit_section = True
                    output_lines.append(line)  # 保留 [suit] 标签行
                    # 插入新的套装数据
                    for suit_line in new_suit_lines:
                        output_lines.append(suit_line + '\n')
                    continue
                
                # 检测 [suit] section 结束（遇到下一个 [xxx]）
                if in_suit_section and stripped.startswith('[') and stripped != '[suit]':
                    in_suit_section = False
                    output_lines.append(line)
                    continue
                
                # 在 [suit] section 内，跳过原数据（已替换）
                if in_suit_section:
                    continue
                
                # 其他行直接保留
                output_lines.append(line)
            
            # 写入文件
            output_path = output_dir / result.source_file
            with open(output_path, 'w', encoding='gbk') as f:
                f.writelines(output_lines)
            
            logger.info(f"已导出: {output_path}")
    
    def get_summary(self) -> str:
        """获取处理汇总报告"""
        if not self.file_results:
            return "没有处理任何文件"
        
        lines = ["=" * 70, "套装去重汇总", "=" * 70]
        lines.append(f"{'文件名':<25} {'原始':>8} {'删除':>8} {'改名':>8} {'最终':>8}")
        lines.append("-" * 70)
        
        total_original = 0
        total_deleted = 0
        total_renamed = 0
        total_final = 0
        
        for result in sorted(self.file_results, key=lambda x: x.source_file):
            if result.original_count == 0:
                continue
            lines.append(f"{result.source_file:<25} {result.original_count:>8} "
                        f"{result.deleted_count:>8} {result.renamed_count:>8} {result.final_count:>8}")
            total_original += result.original_count
            total_deleted += result.deleted_count
            total_renamed += result.renamed_count
            total_final += result.final_count
        
        lines.append("-" * 70)
        lines.append(f"{'合计':<25} {total_original:>8} {total_deleted:>8} {total_renamed:>8} {total_final:>8}")
        lines.append("=" * 70)
        lines.append("")
        lines.append("说明:")
        lines.append("  1. 删除: 部位代码完全相同的重复套装（保留第一个）")
        lines.append("  2. 改名: 同名套装从第一个开始添加 [款式X] 后缀（出现多次的才加）")
        
        return "\n".join(lines)
    
    def get_details(self) -> str:
        """获取详细处理信息"""
        lines = ["=" * 70, "详细处理信息", "=" * 70]
        
        for result in self.file_results:
            if result.original_count == 0:
                continue
            
            lines.append(f"\n【{result.source_file}】")
            lines.append(f"  原始: {result.original_count} 个")
            lines.append(f"  删除: {result.deleted_count} 个（部位重复）")
            lines.append(f"  改名: {result.renamed_count} 个")
            lines.append(f"  最终: {result.final_count} 个")
        
        return "\n".join(lines)


def main():
    """主函数 - 命令行入口"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description='装扮表套装去重工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
处理逻辑:
  1. 按部位重复删除：保留第一个，删除后续部位重复的
  2. 同名套装加后缀：对同名套装从第一个开始加 [款式X] 后缀
     只出现一次的套装不加后缀

示例:
  python deduplicate_suits.py
  python deduplicate_suits.py -d "D:/DOF/output/Avatar"
  python deduplicate_suits.py -d "D:/DOF/output/Avatar" -o "D:/DOF/output/Avatar_Clean"
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
