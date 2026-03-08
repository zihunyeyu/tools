"""
TSV Validator - TSV 装备标签数据验证模块

验证装备标签数据是否存在于 TSV 文件中。
"""

import csv
from pathlib import Path
from typing import Tuple, Dict, Set, Optional


class EquipmentTagValidator:
    """装备标签验证器，用于检查记录是否存在于 TSV 文件中"""
    
    def __init__(self, tsv_path: Optional[Path] = None):
        """
        初始化验证器
        
        Args:
            tsv_path: TSV 文件路径，默认为当前目录下的 complete_equipment_tags.tsv
        """
        self.tsv_path = tsv_path or Path("output/complete_equipment_tags.tsv")
        self._data: Set[Tuple[str, str, str]] = set()
        self._loaded = False
    
    def load(self) -> None:
        """加载 TSV 文件数据"""
        if self._loaded:
            return
            
        if not self.tsv_path.exists():
            raise FileNotFoundError(f"TSV 文件不存在: {self.tsv_path}")

        
        try:
            with open(self.tsv_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    key = (
                        row.get('job', '').strip(),
                        row.get('equipment type', '').strip(),
                        row.get('variation', '').strip(),
                    )
                    self._data.add(key)
            self._loaded = True
        except Exception as e:
            raise RuntimeError(f"加载 TSV 文件失败: {e}")
    
    def verify(self, item: Tuple[str, str, str]) -> bool:
        """
        验证记录是否存在于 TSV 中
        
        Args:
            item: (文件路径, 装备类型, 变体信息) 三元组
            
        Returns:
            True 如果记录存在，否则 False
        """
        if not self._loaded:
            self.load()
            
        path, equip_type, variation = item
        # 处理 variation 中的制表符
        normalized_variation = '_'.join(variation.strip().split('\t'))
        check_key = (path.strip(), equip_type.strip(), normalized_variation)
        return check_key in self._data
    
    def verify_batch(self, items: list[Tuple[str, str, str]]) -> Dict[Tuple[str, str, str], bool]:
        """
        批量验证记录
        
        Args:
            items: 待验证的记录列表
            
        Returns:
            记录到验证结果的字典映射
        """
        print(f"正在批量验证 {len(items)} 条记录...")
        print(items[0])
        return {item: self.verify(item) for item in items}
    
    def reload(self) -> None:
        """重新加载 TSV 文件"""
        self._data.clear()
        self._loaded = False
        self.load()


# 全局验证器实例（懒加载）
_validator: Optional[EquipmentTagValidator] = None


def get_validator(tsv_path: Optional[Path] = None) -> EquipmentTagValidator:
    """获取全局验证器实例"""
    global _validator
    if _validator is None or tsv_path is not None:
        _validator = EquipmentTagValidator(tsv_path)
    return _validator


def verify_tsv_records(item: Tuple[str, str, str]) -> bool:
    """
    验证单条记录（兼容旧接口）
    
    Args:
        item: (文件路径, 装备类型, 变体信息) 三元组
        
    Returns:
        True 如果记录存在，否则 False
    """
    return get_validator().verify(item)



