"""
Suit Merger - 套装合并工具

将生成的套装文件(stk_suits.json)合并到avatar_config.json中。

合并规则：
1. 先备份avatar_config.json源文件
2. 比较套装时排除skin和weapon部位
3. 新套装与现有套装比较时装部位差异数：
   - 差异部位数 >= 2：视为新套装，添加
   - 差异部位数 < 2：视为重复，跳过
4. 新套装添加到对应职业的suits列表中
5. 保留原始avatar_config.json的metadata等结构
"""

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.common_utils import (
    setup_logging, backup_file, load_json, save_json
)

logger = logging.getLogger(__name__)


# 参与比较的部位（排除skin和weapon）
COMPARABLE_PARTS = {'cap', 'hair', 'face', 'neck', 'coat', 'pants', 'belt', 'shoes'}

# 最小差异部位数
MIN_DIFF_PARTS = 3


@dataclass
class MergeResult:
    """合并结果统计"""
    total_new: int = 0
    skipped_duplicate: int = 0
    added: int = 0
    errors: int = 0
    by_job: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    def record(self, job: str, action: str):
        if job not in self.by_job:
            self.by_job[job] = {"new": 0, "skipped": 0}
        if action == "added":
            self.by_job[job]["new"] += 1
        elif action == "skipped":
            self.by_job[job]["skipped"] += 1
    
    def print_summary(self):
        logger.info("=" * 60)
        logger.info("合并完成统计:")
        logger.info(f"  新增套装: {self.added}")
        logger.info(f"  跳过重复: {self.skipped_duplicate}")
        logger.info(f"  处理错误: {self.errors}")
        logger.info("各职业详情:")
        for job, stats in sorted(self.by_job.items()):
            logger.info(f"  {job}: 新增 {stats['new']}, 跳过 {stats['skipped']}")
        logger.info("=" * 60)


class SuitMerger:
    """套装合并器"""
    
    def __init__(self, avatar_config_path: Path, new_suits_path: Path):
        self.avatar_config_path = Path(avatar_config_path)
        self.new_suits_path = Path(new_suits_path)
        self.backup_path: Optional[Path] = None
        
        self.avatar_config: Dict = {}
        self.new_suits: Dict[str, List[Dict]] = {}
        self.result = MergeResult()
    
    def load_files(self) -> bool:
        """加载两个配置文件"""
        try:
            self.avatar_config = load_json(self.avatar_config_path)
            logger.info(f"已加载: {self.avatar_config_path}")
            
            raw_data = load_json(self.new_suits_path)
            self.new_suits = self._parse_suits_format(raw_data)
            
            total = sum(len(s) for s in self.new_suits.values())
            logger.info(f"已加载新套装: {total} 套，{len(self.new_suits)} 个职业")
            return True
        except Exception as e:
            logger.error(f"加载文件失败: {e}")
            return False
    
    def _parse_suits_format(self, data: Dict) -> Dict[str, List[Dict]]:
        """解析套装数据为统一格式"""
        result = {}
        
        # 检查是否是按职业分组的格式
        is_job_grouped = any(
            isinstance(v, dict) and "suits" in v 
            for v in data.values()
        )
        
        if is_job_grouped:
            for job, job_data in data.items():
                if isinstance(job_data, dict) and "suits" in job_data:
                    result[job] = job_data["suits"]
                elif isinstance(job_data, list):
                    result[job] = job_data
        elif "suits" in data:
            result["unknown"] = data["suits"]
        else:
            for key, value in data.items():
                if isinstance(value, list):
                    result[key] = value
        
        return result
    
    def extract_comparable_items(self, items: Dict[str, str]) -> Dict[str, str]:
        """提取用于比较的部位信息"""
        return {
            part: variation
            for part, variation in items.items()
            if part in COMPARABLE_PARTS
        }
    
    def count_differences(self, items1: Dict[str, str], items2: Dict[str, str]) -> int:
        """
        计算两个套装的部位差异数
        - 部位只在一个套装中存在 → 算1个差异
        - 部位都有但variation不同 → 算1个差异
        """
        parts1 = set(items1.keys()) & COMPARABLE_PARTS
        parts2 = set(items2.keys()) & COMPARABLE_PARTS
        all_parts = parts1 | parts2
        
        diff_count = 0
        for part in all_parts:
            var1 = items1.get(part)
            var2 = items2.get(part)
            
            if var1 is None or var2 is None:
                diff_count += 1
            elif var1 != var2:
                diff_count += 1
        
        return diff_count
    
    def is_duplicate(self, job: str, new_suit: Dict) -> Tuple[bool, str]:
        """
        检查新套装是否与现有套装重复
        差异部位数 < MIN_DIFF_PARTS 视为重复
        """
        job_data = self.avatar_config.get(job)
        if not job_data or "suits" not in job_data:
            return False, "无现有套装"
        
        existing_suits = job_data["suits"]
        new_items = self.extract_comparable_items(new_suit.get("items", {}))
        
        if not new_items:
            return True, "无可比较部位"
        
        for existing in existing_suits:
            existing_items = self.extract_comparable_items(existing.get("items", {}))
            diff_count = self.count_differences(new_items, existing_items)
            
            if diff_count < MIN_DIFF_PARTS:
                reason = f"与'{existing['name']}'差异仅{diff_count}个部位(<{MIN_DIFF_PARTS})"
                return True, reason
        
        return False, f"差异≥{MIN_DIFF_PARTS}个部位"
    
    def merge_suits_for_job(self, job: str, new_suits: List[Dict]) -> int:
        """合并单个职业的套装"""
        added_count = 0
        
        if job not in self.avatar_config:
            self.avatar_config[job] = {"suits": []}
        
        if "suits" not in self.avatar_config[job]:
            self.avatar_config[job]["suits"] = []
        
        existing_count = len(self.avatar_config[job]["suits"])
        logger.info(f"处理 {job}: 现有 {existing_count} 套，待合并 {len(new_suits)} 套")
        
        for new_suit in new_suits:
            suit_name = new_suit.get("name", "未命名")
            self.result.total_new += 1
            
            try:
                is_dup, reason = self.is_duplicate(job, new_suit)
                if is_dup:
                    logger.info(f"  跳过: {suit_name} ({reason})")
                    self.result.skipped_duplicate += 1
                    self.result.record(job, "skipped")
                    continue
                
                self.avatar_config[job]["suits"].append(new_suit)
                logger.info(f"  新增: {suit_name}")
                added_count += 1
                self.result.added += 1
                self.result.record(job, "added")
            except Exception as e:
                logger.error(f"  处理失败 {suit_name}: {e}")
                self.result.errors += 1
        
        return added_count
    
    def merge_all(self) -> bool:
        """执行合并操作"""
        logger.info("=" * 60)
        logger.info("开始合并套装...")
        logger.info("=" * 60)
        
        for job, suits in sorted(self.new_suits.items()):
            if suits:
                self.merge_suits_for_job(job, suits)
        
        return True
    
    def run(self) -> bool:
        """执行完整合并流程"""
        backup_file(self.avatar_config_path)
        
        if not self.load_files():
            return False
        
        if not self.merge_all():
            return False
        
        save_json(self.avatar_config_path, self.avatar_config)
        self.result.print_summary()
        
        return True


def main():
    AVATAR_CONFIG_PATH = Path(__file__).parent.parent / "avatar_config.json"
    NEW_SUITS_PATH = Path(__file__).parent.parent / "output" / "stk_suits.json"
    
    setup_logging()
    logger.info("Suit Merger - 套装合并工具")
    
    if not AVATAR_CONFIG_PATH.exists():
        logger.error(f"找不到: {AVATAR_CONFIG_PATH}")
        sys.exit(1)
    
    if not NEW_SUITS_PATH.exists():
        logger.error(f"找不到: {NEW_SUITS_PATH}")
        sys.exit(1)
    
    merger = SuitMerger(AVATAR_CONFIG_PATH, NEW_SUITS_PATH)
    
    if merger.run():
        logger.info("合并完成！")
    else:
        logger.error("合并失败！")
        sys.exit(1)


if __name__ == "__main__":
    main()
