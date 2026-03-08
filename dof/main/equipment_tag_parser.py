"""
Equipment Tag Parser - 装备标签解析器

从 PVF 中批量解析所有类型的装备文件（avatar, weapon, armor, accessory, creature等）
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    PVF_API_HOST, PVF_API_PORT, PVF_API_TIMEOUT,
    BATCH_SIZE, MAX_WORKERS,
    EQUIPMENT_TAGS_TSV
)
from modules.pvf_api_client import PvfUtilityApi, PvfApiError
from modules.equ_parser import EquParser, EquData

logger = logging.getLogger(__name__)


@dataclass
class EquipmentTagInfo:
    """装备标签信息（精简版）"""
    code: str
    path: str
    equ_type: str  # avatar, weapon, armor, accessory, creature, other
    career: str    # 职业或分类
    
    # 核心标签
    name: str = ""
    equipment_type: str = ""  # coat, sword, ring, creature 等
    rarity: int = 0
    level: int = 0
    
    # 变体信息（用于avatar）
    variation: str = ""
    layers: str = ""  # 图层列表
    
    @classmethod
    def from_equ_data(cls, code: str, path: str, data: EquData) -> 'EquipmentTagInfo':
        """从 EquData 创建标签信息"""
        # 提取职业/分类
        parts = path.split('/')
        if 'character' in path and len(parts) >= 3:
            career = parts[2]  # swordman, fighter, etc.
            if 'at_avatar' in path or '/at_' in path:
                career = 'at_' + career
        elif 'creature' in path:
            career = 'creature'
        elif 'common' in path:
            career = 'common'
        else:
            career = parts[1] if len(parts) > 1 else 'other'
        
        # 构建变体字符串
        variation_parts = []
        layer_names = []
        for job in data.animation_jobs:
            variation_parts.append(f"{job.variation.code}\t{job.variation.index}")
            for layer in job.layer_variations:
                if layer.layer_name:
                    layer_names.append(layer.layer_name)
        
        return cls(
            code=code,
            path=path,
            equ_type=data.equ_type,
            career=career,
            name=data.name,
            equipment_type=data.equipment_type,
            rarity=data.rarity,
            level=data.minimum_level,
            variation='_'.join(variation_parts),
            layers=','.join(layer_names)
        )


@dataclass
class ParseStats:
    """解析统计信息"""
    total_files: int = 0
    parsed_files: int = 0
    failed_files: int = 0
    start_time: float = field(default_factory=time.time)
    
    # 分类统计
    by_type: Dict[str, int] = field(default_factory=dict)
    
    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time
    
    @property
    def success_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.stats.parsed_files / self.total_files) * 100


class EquipmentTagParser:
    """装备标签解析器 - 全类型支持"""
    
    # 默认排除 aura（光环）
    EXCLUDE_KEYWORDS = ['/aura/']
    
    def __init__(
        self,
        api: Optional[PvfUtilityApi] = None,
        batch_size: int = BATCH_SIZE,
        max_workers: int = MAX_WORKERS,
        include_types: Optional[Set[str]] = None  # None=所有类型, {'avatar', 'weapon'}=仅指定类型
    ):
        self.api = api or PvfUtilityApi(PVF_API_HOST, PVF_API_PORT, PVF_API_TIMEOUT)
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.include_types = include_types  # 过滤类型
        
        self.code_path_mapping: Dict[str, str] = {}
        self.parsed_data: Dict[str, EquData] = {}
        self.stats = ParseStats()
    
    def parse_equipment_lst(
        self, 
        lst_path: str = "equipment/equipment.lst",
        filter_types: Optional[Set[str]] = None
    ) -> bool:
        """
        解析 equipment.lst 文件
        
        Args:
            lst_path: lst 文件路径
            filter_types: 过滤特定类型 {'avatar', 'weapon', 'armor', 'accessory', 'creature'}
        """
        logger.info(f"解析 lst 文件: {lst_path}")
        if filter_types:
            logger.info(f"过滤类型: {filter_types}")
        
        try:
            contents = self.api.get_file_contents([lst_path])
            if lst_path not in contents:
                logger.error("lst 文件内容为空")
                return False
            
            lst_content = contents[lst_path]
        except PvfApiError as e:
            logger.error(f"获取 lst 文件失败: {e}")
            return False
        
        lines = lst_content.split('\r\n')
        logger.info(f"lst 总行数: {len(lines)}")
        
        for line in lines:
            clean_line = line.strip()
            if not clean_line:
                continue
            
            parts = clean_line.split('\t')
            if len(parts) < 2:
                continue
            
            equ_code = parts[0].strip()
            equ_path = parts[1].strip().replace('`', '')
            full_path = f"equipment/{equ_path}"
            
            if not equ_code.isdigit():
                continue
            
            # 排除 aura
            if any(ex in full_path for ex in self.EXCLUDE_KEYWORDS):
                continue
            
            # 类型过滤（基于路径）
            if filter_types:
                matched = False
                if 'avatar' in filter_types and '/avatar/' in full_path:
                    matched = True
                elif 'weapon' in filter_types and '/weapon/' in full_path:
                    matched = True
                elif 'armor' in filter_types and any(x in full_path for x in ['/coat/', '/pants/', '/shoulder/', '/belt/', '/shoes/']) and '/avatar/' not in full_path:
                    matched = True
                elif 'accessory' in filter_types and any(x in full_path for x in ['/ring/', '/necklace/', '/wrist/', '/support/', '/amulet/', '/magic stone/', '/earring/']):
                    matched = True
                elif 'creature' in filter_types and ('creature' in full_path or '/pet/' in full_path):
                    matched = True
                
                if not matched:
                    continue
            
            self.code_path_mapping[equ_code] = full_path
        
        self.stats.total_files = len(self.code_path_mapping)
        logger.info(f"有效装备: {self.stats.total_files} 条")
        
        # 显示样本
        if self.code_path_mapping:
            sample = list(self.code_path_mapping.items())[:3]
            logger.debug(f"样本: {sample}")
        
        return self.stats.total_files > 0
    
    def _process_batch(self, batch_items: List[Tuple[str, str]]) -> Dict[str, EquData]:
        """处理单个批次"""
        paths = [p for _, p in batch_items]
        results: Dict[str, EquData] = {}
        
        try:
            contents = self.api.get_file_contents(paths)
            
            for code, path in batch_items:
                if path in contents:
                    try:
                        data = EquParser.parse_full(contents[path])
                        results[path] = data
                        self.stats.parsed_files += 1
                        
                        # 更新类型统计
                        eq_type = data.equ_type
                        self.stats.by_type[eq_type] = self.stats.by_type.get(eq_type, 0) + 1
                        
                    except Exception as e:
                        logger.warning(f"解析 {path} 失败: {e}")
                        results[path] = EquData()
                        self.stats.failed_files += 1
                else:
                    results[path] = EquData()
                    self.stats.failed_files += 1
        except PvfApiError as e:
            logger.error(f"批量获取失败: {e}")
            for _, path in batch_items:
                results[path] = EquData()
                self.stats.failed_files += 1
        
        return results
    
    def parse_all(self) -> Dict[str, EquData]:
        """解析所有装备文件"""
        items = list(self.code_path_mapping.items())
        total = len(items)
        batches = [
            items[i:i + self.batch_size]
            for i in range(0, total, self.batch_size)
        ]
        
        logger.info(f"开始解析 {total} 个文件（{len(batches)} 批次，{self.max_workers} 线程）")
        
        all_results: Dict[str, EquData] = {}
        processed = 0
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._process_batch, b): i for i, b in enumerate(batches)}
            
            for future in as_completed(futures):
                batch_result = future.result()
                all_results.update(batch_result)
                processed += 1
                
                if processed % 10 == 0 or processed == len(batches):
                    logger.info(f"进度: {processed}/{len(batches)} ({processed/len(batches)*100:.1f}%)")
        
        self.parsed_data = all_results
        return all_results
    
    def get_equipment_info(self, code: str) -> Optional[EquipmentTagInfo]:
        """获取单个装备信息"""
        if code not in self.code_path_mapping:
            return None
        
        path = self.code_path_mapping[code]
        data = self.parsed_data.get(path)
        
        if not data:
            return None
        
        return EquipmentTagInfo.from_equ_data(code, path, data)
    
    def analyze_by_type(self) -> Dict[str, int]:
        """按装备类型统计"""
        return dict(self.stats.by_type)
    
    def analyze_by_equipment_type(self) -> Dict[str, int]:
        """按具体装备类型统计"""
        type_count: Dict[str, int] = {}
        for path, data in self.parsed_data.items():
            eq_type = data.equipment_type or "unknown"
            type_count[eq_type] = type_count.get(eq_type, 0) + 1
        return type_count
    
    def analyze_by_career(self) -> Dict[str, int]:
        """按职业/分类统计"""
        career_count: Dict[str, int] = {}
        for path, data in self.parsed_data.items():
            parts = path.split('/')
            if 'character' in path and len(parts) >= 3:
                career = parts[2]
                if 'at_avatar' in path or '/at_' in path:
                    career = 'at_' + career
            elif 'creature' in path:
                career = 'creature'
            elif 'common' in path:
                career = 'common'
            else:
                career = parts[1] if len(parts) > 1 else 'other'
            
            career_count[career] = career_count.get(career, 0) + 1
        
        return career_count
    
    def find_by_layer(self, layer_name: str) -> List[Tuple[str, str]]:
        """按图层名称查找装备"""
        results = []
        for path, data in self.parsed_data.items():
            found = False
            for job in data.animation_jobs:
                for layer in job.layer_variations:
                    if layer.layer_name == layer_name:
                        found = True
                        break
                if found:
                    break
            
            if found:
                for code, p in self.code_path_mapping.items():
                    if p == path:
                        results.append((code, path))
                        break
        return results
    
    def find_by_rarity(self, rarity: int) -> List[Tuple[str, str, str]]:
        """按稀有度查找装备"""
        results = []
        for path, data in self.parsed_data.items():
            if data.rarity == rarity:
                for code, p in self.code_path_mapping.items():
                    if p == path:
                        results.append((code, path, data.name))
                        break
        return results
    
    def save_to_tsv(self, output: Path = EQUIPMENT_TAGS_TSV) -> Path:
        """保存结果到 TSV"""
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        lines = ["文件代码\t文件路径\t类型\t职业\t装备类型\t稀有度\t等级\t名称\t变体\t图层\n"]
        
        for code in sorted(self.code_path_mapping.keys(), key=int):
            path = self.code_path_mapping[code]
            data = self.parsed_data.get(path)
            
            if data:
                info = EquipmentTagInfo.from_equ_data(code, path, data)
                lines.append(
                    f"{code}\t{info.career}\t{info.equ_type}\t{info.equipment_type}\t"
                    f"{info.rarity}\t{info.level}\t{info.name}\t{info.variation}\t{info.layers}\n"
                )
            else:
                lines.append(f"{code}\t\t\t\t\t\t\t\t\n")
        
        with open(output, 'w', encoding='utf-8', newline='') as f:
            f.writelines(lines)
        
        logger.info(f"TSV 已保存: {output} ({len(lines)-1} 条)")
        return output
    
    def print_analysis(self):
        """打印分析报告"""
        print("\n" + "="*60)
        print("装备标签分析")
        print("="*60)
        
        # 按大类统计
        type_stats = self.analyze_by_type()
        print("\n按装备大类统计:")
        for eq_type, count in sorted(type_stats.items(), key=lambda x: -x[1]):
            print(f"  {eq_type}: {count}")
        
        # 按具体装备类型统计
        equip_type_stats = self.analyze_by_equipment_type()
        print("\n按装备类型统计 (Top 15):")
        for eq_type, count in sorted(equip_type_stats.items(), key=lambda x: -x[1])[:15]:
            print(f"  {eq_type}: {count}")
        
        # 按职业统计
        career_stats = self.analyze_by_career()
        print("\n按职业/分类统计:")
        for career, count in sorted(career_stats.items(), key=lambda x: -x[1]):
            print(f"  {career}: {count}")
    
    def run(
        self, 
        output: Path = EQUIPMENT_TAGS_TSV,
        filter_types: Optional[Set[str]] = None,
        analyze: bool = True
    ) -> bool:
        """
        执行完整流程
        
        Args:
            output: 输出文件路径
            filter_types: 过滤类型 {'avatar', 'weapon', 'armor', 'accessory', 'creature'}
            analyze: 是否打印分析报告
        """
        try:
            if not self.parse_equipment_lst(filter_types=filter_types):
                return False
            
            self.parse_all()
            self.save_to_tsv(output)
            
            if analyze:
                self.print_analysis()
            
            logger.info(
                f"完成: 总计={self.stats.total_files}, "
                f"成功={self.stats.parsed_files}, "
                f"失败={self.stats.failed_files}, "
                f"成功率={(self.stats.parsed_files/self.stats.total_files*100):.1f}%, "
                f"耗时={self.stats.elapsed_time:.2f}s"
            )
            return True
            
        except Exception as e:
            logger.error(f"流程异常: {e}")
            return False


def main():
    """主入口 - 默认只解析 avatar 时装装备（保持扩展前功能）"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='装备标签解析器 - 默认解析时装(avatar)，支持扩展到其他类型',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 默认：只解析时装（avatar）
  python equipment_tag_parser.py
  
  # 解析所有类型
  python equipment_tag_parser.py --all
  
  # 只解析武器
  python equipment_tag_parser.py --types weapon
  
  # 解析武器和防具
  python equipment_tag_parser.py --types weapon,armor
  
  # 解析饰品和宠物装备
  python equipment_tag_parser.py --types accessory,creature
        """
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='解析所有装备类型（默认只解析 avatar）'
    )
    
    parser.add_argument(
        '--types',
        type=str,
        default='',
        help='过滤类型，逗号分隔: avatar,weapon,armor,accessory,creature'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=str,
        default=str(EQUIPMENT_TAGS_TSV),
        help='输出文件路径'
    )
    
    args = parser.parse_args()
    
    # 确定类型过滤
    # 默认只解析 avatar（保持扩展前功能）
    # --all 参数解析所有类型
    # --types 参数指定特定类型
    if args.all:
        filter_types = None  # 所有类型
    elif args.types:
        filter_types = set(t.strip() for t in args.types.split(',') if t.strip())
    else:
        filter_types = {'avatar'}  # 默认只解析 avatar
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    tag_parser = EquipmentTagParser()
    success = tag_parser.run(
        output=Path(args.output),
        filter_types=filter_types,
        analyze=True
    )
    
    print("\n✓ 解析完成" if success else "\n✗ 解析失败")
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
