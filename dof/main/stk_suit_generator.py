"""
STK Suit Generator - STK套装生成器

从PVF的etc/newcashshop.etc文件中读取[package]标签下的商城礼包列表，
提取其中的时装装备，按职业分组生成套装配置。

处理流程：
1. 读取etc/newcashshop.etc的[package]标签，获取商城礼包stk代码列表
2. 根据stk代码从stackable.lst获取stk文件路径
3. 解析每个stk的[package data]获取equ代码列表
4. 对每个equ代码：
   - 从equipment.lst获取equ文件路径
   - 读取equ文件内容
   - 解析[equipment type]获取部位
   - 解析[variation]获取variation_code和suffix
   - 从[usable job]推断职业
5. 检查职业一致性（单职业保留，多职业跳过）
6. 过滤部件过少的礼包（排除skin后<3件）
7. 生成套装配置（stk_name作为套装名）

输出格式（类似avatar_config.json）：
{
  "swordman_male": {
    "suits": [
      {
        "name": "春节礼包",
        "items": {"cap": "4000", "coat": "5000", ...}
      }
    ]
  }
}
"""

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.pvf_api_client import PvfUtilityApi
from modules.mappings import (
    USABLE_JOB_TO_BASE, SKIP_USABLE_JOBS, BASE_JOB_TO_FULL,
    EQU_TYPE_TO_PART
)
from modules.common_utils import setup_logging, init_pvf_api, save_json
from config import PVF_API_HOST, PVF_API_PORT

logger = logging.getLogger(__name__)


@dataclass
class ParsedEqu:
    """解析后的装备信息"""
    code: str
    part: str
    variation: str  # 如 "4000"
    job: str


@dataclass
class SuitInfo:
    """套装信息"""
    name: str
    items: Dict[str, str]  # part -> variation
    job: str


@dataclass
class Stats:
    """统计信息"""
    total_stk: int = 0
    success: int = 0
    multi_job: int = 0
    no_avatar: int = 0
    too_few_parts: int = 0
    parse_error: int = 0
    
    def print_summary(self):
        """打印统计"""
        logger.info("=" * 50)
        logger.info("处理统计:")
        logger.info(f"  总stk数: {self.total_stk}")
        logger.info(f"  成功转换: {self.success}")
        logger.info(f"  多职业跳过: {self.multi_job}")
        logger.info(f"  无时装跳过: {self.no_avatar}")
        logger.info(f"  部件过少跳过(<3): {self.too_few_parts}")
        logger.info(f"  解析错误: {self.parse_error}")
        logger.info("=" * 50)


class StkSuitGenerator:
    """STK套装生成器"""
    
    STACKABLE_LST_PATH = "stackable/stackable.lst"
    EQUIPMENT_LST_PATH = "equipment/equipment.lst"
    NEWCASHSHOP_ETC_PATH = "etc/newcashshop.etc"
    # 参与比较的部位（排除skin）
    COMPARABLE_PARTS = {'cap', 'hair', 'face', 'neck', 'coat', 'pants', 'belt', 'shoes'}
    # 最小部件数（排除skin）
    MIN_PARTS = 3
    
    def __init__(self, pvf_api: PvfUtilityApi):
        self._pvf_api = pvf_api
        
        # LST缓存
        self._stackable_lst: Dict[str, str] = {}
        self._equipment_lst: Dict[str, str] = {}
        
        # 商城package stk代码列表
        self._package_stk_codes: List[str] = []
        
        # EQU解析缓存
        self._equ_cache: Dict[str, Optional[ParsedEqu]] = {}
        
        # 统计
        self.stats = Stats()
    
    def load_stackable_lst(self) -> None:
        """加载stackable.lst"""
        logger.info(f"加载 {self.STACKABLE_LST_PATH}...")
        lst_info = self._pvf_api.get_lst_file_info(self.STACKABLE_LST_PATH)
        
        for code_str, info in lst_info.items():
            if isinstance(info, dict) and 'FullPath' in info:
                self._stackable_lst[code_str] = info['FullPath']
            elif isinstance(info, str):
                self._stackable_lst[code_str] = info
        
        logger.info(f"共 {len(self._stackable_lst)} 个stk")
    
    def load_equipment_lst(self) -> None:
        """加载equipment.lst"""
        logger.info(f"加载 {self.EQUIPMENT_LST_PATH}...")
        lst_info = self._pvf_api.get_lst_file_info(self.EQUIPMENT_LST_PATH)
        
        for code_str, info in lst_info.items():
            if isinstance(info, dict) and 'FullPath' in info:
                self._equipment_lst[code_str] = info['FullPath']
            elif isinstance(info, str):
                self._equipment_lst[code_str] = info
        
        logger.info(f"共 {len(self._equipment_lst)} 个equ")
    
    def load_newcashshop_packages(self) -> List[str]:
        """
        从etc/newcashshop.etc读取[package]标签下的stk代码列表
        
        格式: <index>\t<stk_code>\t<col3>\t<col4>\t<col5>\t`name`\t...
        例如: 5044\t10000268\t0\t0\t5000\t`时尚达人4 圣职者`\t0\t0\t-1\t-1
        
        Returns:
            stk_code列表
        """
        logger.info(f"加载 {self.NEWCASHSHOP_ETC_PATH} 的 [package] 标签...")
        
        try:
            content = self._pvf_api.get_file_content(self.NEWCASHSHOP_ETC_PATH)
        except Exception as e:
            logger.error(f"读取 {self.NEWCASHSHOP_ETC_PATH} 失败: {e}")
            return []
        
        # 解析[package]标签
        pattern = r'\[package\]\s*\r?\n(.*?)\r?\n\s*\[/package\]'
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            logger.warning(f"未找到 [package] 标签")
            return []
        
        package_section = match.group(1)
        stk_codes = []
        
        for line in package_section.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('['):
                continue
            
            # 分割列
            parts = line.split('\t')
            if len(parts) >= 2:
                # 第2列是stk_code
                stk_code = parts[1].strip()
                if stk_code and stk_code.isdigit():
                    stk_codes.append(stk_code)
        
        logger.info(f"共 {len(stk_codes)} 个商城礼包stk")
        return stk_codes
    
    def parse_stk_name(self, content: str) -> str:
        """解析stk的[name]"""
        match = re.search(r'\[name\]\s*\r?\n\s*`([^`]*)`', content)
        return match.group(1).strip() if match else ""
    
    def parse_package_data(self, content: str) -> List[str]:
        """解析[package data]获取equ代码列表"""
        pattern = r'\[package data\]\s*\r?\n(.*?)\r?\n\s*\[/package data\]'
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return []
        
        codes = []
        for line in match.group(1).strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if parts and parts[0].strip():
                code = parts[0].strip()
                if code not in codes:
                    codes.append(code)
        return codes
    
    def parse_usable_jobs(self, content: str) -> List[str]:
        """解析[usable job]标签"""
        pattern = r'\[usable job\]\s*\r?\n(.*?)\r?\n\s*\[/usable job\]'
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return []
        
        jobs = []
        for line in match.group(1).strip().split('\n'):
            m = re.search(r'`([^`]+)`', line.strip())
            if m:
                jobs.append(m.group(1))
        return jobs
    
    def infer_job(self, equ_content: str, equ_path: str) -> Optional[str]:
        """
        根据[usable job]和路径推断职业
        跳过特殊职业: creator mage, demonic swordman
        """
        usable_jobs = self.parse_usable_jobs(equ_content)
        if not usable_jobs:
            return None
        
        # 过滤特殊职业
        filtered = [j for j in usable_jobs if j not in SKIP_USABLE_JOBS]
        if not filtered:
            return None
        
        # 获取基础职业
        base_job = None
        for job in filtered:
            base_job = USABLE_JOB_TO_BASE.get(job)
            if base_job:
                break
        
        if not base_job:
            return None
        
        # 检查路径是否含at_
        has_at = '/at' in equ_path.lower() or 'at_' in equ_path.lower()
        
        return BASE_JOB_TO_FULL.get((base_job, has_at))
    
    def parse_equipment_type(self, content: str) -> Optional[str]:
        """解析[equipment type]获取部位"""
        match = re.search(r'\[equipment type\]\s*\r?\n\s*`([^`]+)`', content)
        if match:
            equ_type = match.group(1).strip().lower()
            return EQU_TYPE_TO_PART.get(equ_type)
        return None
    
    def parse_variation(self, content: str) -> Optional[Tuple[int, int]]:
        """解析[variation]获取(code, suffix)"""
        match = re.search(r'\[variation\]\s*\r?\n\s*(\d+)\s+(\d+)', content)
        if match:
            return int(match.group(1)), int(match.group(2))
        return None
    
    def parse_equ(self, equ_code: str) -> Optional[ParsedEqu]:
        """解析单个equ文件"""
        if equ_code in self._equ_cache:
            return self._equ_cache[equ_code]
        
        equ_path = self._equipment_lst.get(equ_code)
        if not equ_path:
            self._equ_cache[equ_code] = None
            return None
        
        try:
            content = self._pvf_api.get_file_content(equ_path)
        except Exception:
            self._equ_cache[equ_code] = None
            return None
        
        # 检查是否为avatar
        if "[avatar" not in content.lower():
            self._equ_cache[equ_code] = None
            return None
        
        # 解析部位
        part = self.parse_equipment_type(content)
        if not part:
            self._equ_cache[equ_code] = None
            return None
        
        # 解析variation
        var_tuple = self.parse_variation(content)
        if not var_tuple:
            self._equ_cache[equ_code] = None
            return None
        
        var_code, suffix = var_tuple
        variation_str = f"{var_code * 100 + suffix}"
        
        # 推断职业
        job = self.infer_job(content, equ_path)
        if not job:
            self._equ_cache[equ_code] = None
            return None
        
        result = ParsedEqu(
            code=equ_code,
            part=part,
            variation=variation_str,
            job=job
        )
        self._equ_cache[equ_code] = result
        return result
    
    def process_stk(self, stk_code: str) -> Optional[SuitInfo]:
        """处理单个stk礼包"""
        stk_path = self._stackable_lst.get(stk_code)
        if not stk_path:
            return None
        
        try:
            content = self._pvf_api.get_file_content(stk_path)
        except Exception:
            return None
        
        suit_name = self.parse_stk_name(content) or f"礼包_{stk_code}"
        equ_codes = self.parse_package_data(content)
        
        if not equ_codes:
            self.stats.no_avatar += 1
            return None
        
        # 解析所有equ
        parsed_equs = []
        jobs: Set[str] = set()
        
        for equ_code in equ_codes:
            parsed = self.parse_equ(equ_code)
            if parsed:
                parsed_equs.append(parsed)
                jobs.add(parsed.job)
        
        if not parsed_equs:
            self.stats.no_avatar += 1
            return None
        
        # 检查职业一致性
        if len(jobs) > 1:
            self.stats.multi_job += 1
            return None
        
        job = jobs.pop()
        
        # 构建items
        items = {}
        for equ in parsed_equs:
            if equ.part not in items:
                items[equ.part] = equ.variation
        
        # 检查部件数量（排除skin）
        non_skin = [p for p in items.keys() if p != 'skin']
        if len(non_skin) < self.MIN_PARTS:
            self.stats.too_few_parts += 1
            return None
        
        self.stats.success += 1
        return SuitInfo(name=suit_name, items=items, job=job)
    
    def generate(self, progress_interval: int = 100) -> Dict[str, Dict]:
        """生成所有套装配置（只处理newcashshop.etc中[package]标签下的stk）"""
        results: Dict[str, List[SuitInfo]] = {}
        
        # 只处理package中的stk代码
        total = len(self._package_stk_codes)
        logger.info(f"开始处理 {total} 个商城礼包stk...")
        
        for idx, stk_code in enumerate(self._package_stk_codes, 1):
            self.stats.total_stk += 1
            
            # 检查stk是否在stackable.lst中
            if stk_code not in self._stackable_lst:
                logger.debug(f"stk {stk_code} 不在stackable.lst中，跳过")
                continue
            
            try:
                suit = self.process_stk(stk_code)
                if suit:
                    if suit.job not in results:
                        results[suit.job] = []
                    results[suit.job].append(suit)
                
                if idx % progress_interval == 0:
                    logger.info(f"进度: {idx}/{total} ({idx/total*100:.1f}%), 成功: {self.stats.success}")
            except Exception as e:
                logger.debug(f"处理stk {stk_code} 出错: {e}")
                self.stats.parse_error += 1
        
        # 转换为输出格式
        output = {}
        for job, suits in results.items():
            output[job] = {
                "suits": [{"name": s.name, "items": s.items} for s in suits]
            }
        
        return output


def main():
    """主程序"""
    PVF_API_HOST = "localhost"
    PVF_API_PORT = 27000
    OUTPUT_PATH = Path(__file__).parent.parent / "output" / "stk_suits.json"
    PROGRESS_INTERVAL = 100
    
    setup_logging()
    logger.info("STK Suit Generator - 开始运行")
    logger.info("从 etc/newcashshop.etc [package] 读取商城礼包列表")
    
    try:
        pvf_api = init_pvf_api(PVF_API_HOST, PVF_API_PORT)
        generator = StkSuitGenerator(pvf_api)
        
        # 加载所有必要的LST文件
        generator.load_stackable_lst()
        generator.load_equipment_lst()
        
        # 从newcashshop.etc读取package标签下的stk列表
        generator._package_stk_codes = generator.load_newcashshop_packages()
        
        if not generator._package_stk_codes:
            logger.warning("未找到任何商城礼包stk，退出")
            sys.exit(0)
        
        data = generator.generate(progress_interval=PROGRESS_INTERVAL)
        
        if data:
            save_json(OUTPUT_PATH, data)
            for job, info in data.items():
                logger.info(f"  {job}: {len(info['suits'])} 套")
        else:
            logger.warning("没有生成任何套装数据")
        
        generator.stats.print_summary()
        logger.info("处理完成！")
        
    except Exception as e:
        logger.error(f"程序失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
