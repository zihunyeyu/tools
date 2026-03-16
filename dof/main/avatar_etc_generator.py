"""
Avatar ETC Generator - 时装商城配置生成器

从本地 equ.lst 文件读取 avatar equ 列表，按照职业、部位、时装的 variation 顺序，
参考 etc/newcashshop.etc 的 [avatar] 标签格式生成配置。

输出格式:
    {index}\t{equ code}\t3\t0\t0\t-1\t-1\t{equ code}\t4\t0\t0\t-1\n\r

排序规则:
    1. 职业 (按PART_CODE_MAP顺序)
    2. 部位 (按职业内部位顺序)
    3. variation (数值从小到大)

索引从1000000开始递增
"""

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.pvf_api_client import PvfUtilityApi
from modules.mappings import (
    USABLE_JOB_TO_BASE, SKIP_USABLE_JOBS, BASE_JOB_TO_FULL,
    EQU_TYPE_TO_PART, PART_CODE_MAP
)
from modules.common_utils import setup_logging, init_pvf_api
from config import PVF_API_HOST, PVF_API_PORT

# 配置日志
setup_logging()
logger = logging.getLogger(__name__)


@dataclass
class AvatarEqu:
    """时装装备信息"""
    code: str           # equ代码
    part: str           # 部位
    variation: int      # variation_code * 100 + suffix
    job: str            # 完整职业名 (如 swordman_male)
    variation_tuple: Tuple[int, int]  # (variation_code, suffix)


class AvatarEtcGenerator:
    """时装商城配置生成器"""
    
    # 默认本地 equ.lst 路径
    DEFAULT_EQU_LST_PATH = Path(r'C:\Users\10704\PycharmProjects\tools\dof\output\equ.lst')
    
    # 部位排序权重 (按PART_CODE_MAP中的顺序)
    PART_ORDER = {name: idx for idx, (name, _) in enumerate([
        ('coat', (0, 'coat')),
        ('pants', (1, 'pants')),
        ('neck', (2, 'breast')),
        ('belt', (3, 'waist')),
        ('shoes', (4, 'shoes')),
        ('cap', (5, 'hat')),
        ('hair', (6, 'hair')),
        ('face', (7, 'face')),
        ('skin', (8, 'skin')),
    ])}
    
    # 职业排序顺序
    JOB_ORDER = {
        'swordman_male': 0,
        'fighter_female': 1,
        'fighter_male': 2,
        'gunner_male': 3,
        'gunner_female': 4,
        'mage_female': 5,
        'mage_male': 6,
        'priest_male': 7,
        'thief_female': 8,
    }
    
    def __init__(self, pvf_api: PvfUtilityApi, equ_lst_path: Optional[Path] = None):
        self._pvf_api = pvf_api
        self._equ_lst_path = equ_lst_path or self.DEFAULT_EQU_LST_PATH
        self._equipment_lst: Dict[str, str] = {}
        self._avatar_equs: List[AvatarEqu] = []
    
    def load_equ_lst_from_file(self):
        """从本地 equ.lst 文件加载"""
        logger.info(f"加载本地 equ.lst: {self._equ_lst_path}")
        
        if not self._equ_lst_path.exists():
            logger.error(f"文件不存在: {self._equ_lst_path}")
            raise FileNotFoundError(f"equ.lst 文件不存在: {self._equ_lst_path}")
        
        try:
            with open(self._equ_lst_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 解析格式: code + tab + path
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        code = parts[0].strip()
                        path = parts[1].strip().strip('`')  # 去掉反引号
                        
                        # 只保留 avatar 相关的 equ
                        if 'avatar' in path.lower() and path.endswith('.equ'):
                            # 构建完整的 PVF 路径
                            full_path = f"equipment/{path}"
                            self._equipment_lst[code] = full_path
            
            logger.info(f"共 {len(self._equipment_lst)} 个 avatar equ")
            
        except Exception as e:
            logger.error(f"加载 equ.lst 失败: {e}")
            raise
    
    def parse_equipment_type(self, content: str) -> Optional[str]:
        """解析 [equipment type] 获取部位"""
        match = re.search(r'\[equipment type\]\s*\r?\n\s*`([^`]+)`', content)
        if match:
            equ_type = match.group(1).strip()
            return EQU_TYPE_TO_PART.get(equ_type)
        return None
    
    def parse_variation(self, content: str) -> Optional[Tuple[int, int]]:
        """解析 [variation] 获取(code, suffix)"""
        match = re.search(r'\[variation\]\s*\r?\n\s*(\d+)\s+(\d+)', content)
        if match:
            return int(match.group(1)), int(match.group(2))
        return None
    
    def parse_usable_job(self, content: str) -> Optional[str]:
        """从 [usable job] 解析基础职业"""
        match = re.search(r'\[usable job\](.*?)\[/usable job\]', content, re.DOTALL)
        if not match:
            return None
        
        section = match.group(1)
        jobs = re.findall(r'`([^`]+)`', section)
        
        # 过滤掉特殊职业，只保留基础职业
        base_jobs = []
        for job in jobs:
            job = job.strip()
            if job in SKIP_USABLE_JOBS:
                continue
            if job in USABLE_JOB_TO_BASE:
                base_jobs.append(USABLE_JOB_TO_BASE[job])
        
        # 返回第一个基础职业（如果有）
        if base_jobs:
            return base_jobs[0]
        return None
    
    def infer_job(self, content: str, equ_path: str) -> Optional[str]:
        """推断完整职业名"""
        # 方法1: 从 usable job 推断基础职业
        base_job = self.parse_usable_job(content)
        
        # 方法2: 从路径特征推断性别
        is_male = '/at_' not in equ_path.lower()
        
        if base_job:
            return BASE_JOB_TO_FULL.get((base_job, is_male))
        
        # 方法3: 从路径直接推断
        path_lower = equ_path.lower()
        if 'swordman' in path_lower:
            return 'swordman_male'
        elif 'fighter/at_' in path_lower:
            return 'fighter_male'
        elif 'fighter' in path_lower:
            return 'fighter_female'
        elif 'gunner/at_' in path_lower:
            return 'gunner_female'
        elif 'gunner' in path_lower:
            return 'gunner_male'
        elif 'mage/at_' in path_lower:
            return 'mage_male'
        elif 'mage' in path_lower:
            return 'mage_female'
        elif 'priest' in path_lower:
            return 'priest_male'
        elif 'thief' in path_lower:
            return 'thief_female'
        
        return None
    
    def parse_equ(self, equ_code: str, equ_path: str) -> Optional[AvatarEqu]:
        """解析单个 equ 文件"""
        try:
            content = self._pvf_api.get_file_content(equ_path)
        except Exception as e:
            logger.warning(f"读取 equ 失败 {equ_code}: {e}")
            return None
        
        # 检查是否为 avatar
        if "[avatar" not in content.lower():
            return None
        
        # 解析部位
        part = self.parse_equipment_type(content)
        if not part:
            return None
        
        # 解析 variation
        var_tuple = self.parse_variation(content)
        if not var_tuple:
            return None
        
        var_code, suffix = var_tuple
        variation = var_code * 100 + suffix
        
        # 推断职业
        job = self.infer_job(content, equ_path)
        if not job:
            return None
        
        return AvatarEqu(
            code=equ_code,
            part=part,
            variation=variation,
            job=job,
            variation_tuple=var_tuple
        )
    
    def scan_all_avatar_equs(self):
        """扫描所有 avatar equ 文件"""
        logger.info("开始扫描所有 avatar equ...")
        
        total = len(self._equipment_lst)
        success = 0
        skipped = 0
        
        for idx, (code, path) in enumerate(self._equipment_lst.items(), 1):
            equ = self.parse_equ(code, path)
            if equ:
                self._avatar_equs.append(equ)
                success += 1
            else:
                skipped += 1
            
            if idx % 1000 == 0:
                logger.info(f"进度: {idx}/{total}, 成功: {success}, 跳过: {skipped}")
        
        logger.info(f"扫描完成: 总计 {total}, 成功 {success}, 跳过 {skipped}")
        logger.info(f"共收集 {len(self._avatar_equs)} 个 avatar equ")
    
    def sort_avatar_equs(self):
        """按职业、部位、variation 排序"""
        logger.info("开始排序...")
        
        def sort_key(equ: AvatarEqu) -> tuple:
            job_order = self.JOB_ORDER.get(equ.job, 999)
            part_order = self.PART_ORDER.get(equ.part, 999)
            return (job_order, part_order, equ.variation)
        
        self._avatar_equs.sort(key=sort_key)
        logger.info("排序完成")
    
    def generate_etc_content(self, start_index: int = 1000000) -> str:
        """
        生成 etc 文件内容
        
        格式: {index}\t{equ code}\t3\t0\t0\t-1\t-1\t{equ code}\t4\t0\t0\t-1\n\r
        """
        logger.info(f"生成 etc 内容，起始索引: {start_index}")
        
        lines = []
        lines.append("[avatar]")
        
        for idx, equ in enumerate(self._avatar_equs, start=start_index):
            # 格式: index equ_code 3 0 0 -1 -1 equ_code 4 0 0 -1
            line = f"{idx}\t{equ.code}\t3\t0\t0\t-1\t-1\t{equ.code}\t4\t0\t0\t-1"
            lines.append(line)
        
        lines.append("[/avatar]")
        
        # 使用 Windows 换行符
        content = "\n\r".join(lines)
        return content
    
    def generate(self, output_path: Path, start_index: int = 1000000) -> Dict[str, any]:
        """
        主生成流程
        
        Args:
            output_path: 输出文件路径
            start_index: 起始索引，默认1000000
            
        Returns:
            统计信息
        """
        # 1. 从本地文件加载 equ.lst
        self.load_equ_lst_from_file()
        
        # 2. 扫描所有 avatar equ
        self.scan_all_avatar_equs()
        
        # 3. 排序
        self.sort_avatar_equs()
        
        # 4. 生成 etc 内容
        content = self.generate_etc_content(start_index)
        
        # 5. 写入文件
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        
        logger.info(f"已写入 {len(self._avatar_equs)} 条记录到 {output_path}")
        
        # 返回统计
        job_stats: Dict[str, int] = {}
        part_stats: Dict[str, int] = {}
        for equ in self._avatar_equs:
            job_stats[equ.job] = job_stats.get(equ.job, 0) + 1
            part_stats[equ.part] = part_stats.get(equ.part, 0) + 1
        
        return {
            "total": len(self._avatar_equs),
            "output_file": str(output_path),
            "start_index": start_index,
            "end_index": start_index + len(self._avatar_equs) - 1,
            "job_stats": job_stats,
            "part_stats": part_stats
        }


def main():
    """主入口"""
    # ==================== 配置区域 ====================
    # 输入文件路径（本地 equ.lst）
    EQU_LST_PATH = Path(r'C:\Users\10704\PycharmProjects\tools\dof\output\equ.lst')
    
    # 输出文件路径
    OUTPUT_PATH = Path('output/newcashshop_avatar.etc')
    START_INDEX = 1000000  # 起始索引
    
    # PVF API配置（用于读取 equ 文件内容）
    PVF_HOST = PVF_API_HOST
    PVF_PORT = PVF_API_PORT
    # ==================================================
    
    logger.info("=" * 60)
    logger.info("Avatar ETC Generator - 时装商城配置生成器")
    logger.info("=" * 60)
    logger.info(f"输入文件: {EQU_LST_PATH}")
    logger.info(f"输出路径: {OUTPUT_PATH}")
    logger.info(f"起始索引: {START_INDEX}")
    
    try:
        # 初始化PVF API（用于读取 equ 文件内容）
        logger.info(f"连接PVF API: {PVF_HOST}:{PVF_PORT}")
        pvf_api = init_pvf_api(PVF_HOST, PVF_PORT)
        
        # 创建生成器
        generator = AvatarEtcGenerator(pvf_api, equ_lst_path=EQU_LST_PATH)
        
        # 执行生成
        stats = generator.generate(
            output_path=OUTPUT_PATH,
            start_index=START_INDEX
        )
        
        # 输出统计
        logger.info("=" * 60)
        logger.info("生成完成!")
        logger.info("=" * 60)
        logger.info(f"总计: {stats['total']} 个avatar")
        logger.info(f"索引范围: {stats['start_index']} - {stats['end_index']}")
        logger.info(f"输出文件: {stats['output_file']}")
        
        logger.info("\n职业分布:")
        for job, count in sorted(stats['job_stats'].items()):
            logger.info(f"  {job}: {count}")
        
        logger.info("\n部位分布:")
        for part, count in sorted(stats['part_stats'].items()):
            logger.info(f"  {part}: {count}")
        
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"生成失败: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
