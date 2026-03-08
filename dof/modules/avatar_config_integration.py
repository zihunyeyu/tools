"""
Avatar Config Integration - avatar_config.json 整合模块

在原配置文件基础上，叠加 avatar_config.json 的 name 和套装信息。

使用示例:
    from modules.avatar_config_integration import HybridAvatarTableLoader
    
    loader = HybridAvatarTableLoader()
    name, icon_index, found = loader.get_name_and_icon('sm', 'cap', 4000)
    suit_name = loader.get_suit_name('sm', 'cap', 4000)
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 职业键映射：原系统缩写 -> 新配置键名
JOB_KEY_MAP = {
    'sm': 'swordman_male',
    'ft': 'fighter_female',
    'fm': 'fighter_male',
    'gn': 'gunner_male',
    'gg': 'gunner_female',
    'mg': 'mage_female',
    'mm': 'mage_male',
    'pr': 'priest_male',
    'th': 'thief_female',
}

# 反向映射
JOB_KEY_MAP_REVERSE = {v: k for k, v in JOB_KEY_MAP.items()}

# 部位中文名映射
PART_NAMES_CN = {
    'cap': '头饰',
    'hair': '发型',
    'face': '面部',
    'neck': '胸部',
    'coat': '上衣',
    'pants': '下装',
    'belt': '腰带',
    'shoes': '鞋子',
    'skin': '皮肤',
    'body': '皮肤',
}


@dataclass
class AvatarInfo:
    """装扮信息数据类（兼容原 AvatarTableLoader）"""
    code: int
    part: str
    icon_index: int
    name: str
    suit_name: Optional[str] = None
    source: str = 'unknown'  # 'config', 'txt', 'derived'
    
    def __repr__(self):
        return (f"AvatarInfo(code={self.code}, part='{self.part}', "
                f"icon_index={self.icon_index}, name='{self.name}', "
                f"suit_name='{self.suit_name}', source='{self.source}')")


class AvatarConfigIntegration:
    """
    avatar_config.json 整合器
    
    负责加载新配置文件并构建快速查询索引。
    """
    
    def __init__(self, config_path: Path = Path('avatar_config.json')):
        self.config_path = config_path
        self.config_data = self._load_config()
        self._index: Dict[Tuple[str, str, int], AvatarInfo] = self._build_index()
        logger.info(f"AvatarConfigIntegration: 已加载 {len(self._index)} 条记录")
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        if not self.config_path.exists():
            logger.warning(f"配置文件不存在: {self.config_path}")
            return {}
        try:
            with open(self.config_path, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    
    def _build_index(self) -> Dict[Tuple[str, str, int], AvatarInfo]:
        """
        构建查询索引
        
        键: (job_abbr, part, full_code)
        例如: ('sm', 'cap', 4000)
        """
        index = {}
        
        for new_job_key, job_data in self.config_data.items():
            job_abbr = JOB_KEY_MAP_REVERSE.get(new_job_key)
            if not job_abbr:
                logger.debug(f"未知职业键: {new_job_key}")
                continue
            
            for suit in job_data.get('suits', []):
                suit_name = suit.get('name', '')
                items = suit.get('items', {})
                
                for part, code_str in items.items():
                    try:
                        full_code = int(code_str)
                        
                        # 推导装备名
                        name = self._derive_name(suit_name, part)
                        
                        # 推导 icon_index（后两位）
                        icon_index = full_code % 100
                        
                        # 构建键
                        key = (job_abbr, part, full_code)
                        
                        index[key] = AvatarInfo(
                            code=full_code,
                            part=part,
                            icon_index=icon_index,
                            name=name,
                            suit_name=suit_name,
                            source='config'
                        )
                    except ValueError:
                        logger.warning(f"无效的编码: {code_str}")
                        continue
        
        return index
    
    def _derive_name(self, suit_name: str, part: str) -> str:
        """
        推导装备名
        
        示例:
        - 套装: "08国庆-[款式1]", 部位: "cap"
        - 结果: "08国庆-头饰"
        """
        # 简化套装名，去掉 [款式X] 后缀
        base_name = re.sub(r'\[款式\d+\]', '', suit_name).rstrip('-')
        part_cn = PART_NAMES_CN.get(part, part)
        return f"{base_name}-{part_cn}"
    
    def lookup(self, job: str, part: str, code: int) -> Optional[AvatarInfo]:
        """
        查询装备信息
        
        Args:
            job: 职业缩写 (sm, ft, fm...)
            part: 部位 (cap, coat...)
            code: 完整编码 (如 4000)
        
        Returns:
            AvatarInfo 对象，找不到返回 None
        """
        # 处理 body/skin 别名
        if part == 'body':
            part = 'skin'
        
        key = (job, part, code)
        return self._index.get(key)
    
    def get_name(self, job: str, part: str, code: int) -> Optional[str]:
        """获取装备名"""
        info = self.lookup(job, part, code)
        return info.name if info else None
    
    def get_suit_name(self, job: str, part: str, code: int) -> Optional[str]:
        """获取套装名"""
        info = self.lookup(job, part, code)
        return info.suit_name if info else None
    
    def get_icon_index(self, job: str, part: str, code: int) -> Optional[int]:
        """获取图标索引"""
        info = self.lookup(job, part, code)
        return info.icon_index if info else None
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        job_counts = {}
        for job, part, code in self._index.keys():
            job_counts[job] = job_counts.get(job, 0) + 1
        
        return {
            'total_records': len(self._index),
            'job_counts': job_counts,
            'jobs': list(job_counts.keys()),
        }


class HybridAvatarTableLoader:
    """
    混合装扮表加载器
    
    优先使用 avatar_config.json，找不到时 fallback 到 TXT 装扮表。
    
    与原 AvatarTableLoader 接口兼容，可直接替换使用。
    """
    
    def __init__(self, 
                 txt_base_path: Optional[str] = None,
                 config_path: Path = Path('avatar_config.json'),
                 prefer_config: bool = True):
        """
        初始化混合加载器
        
        Args:
            txt_base_path: TXT 装扮表目录路径，None 则使用 config 中的路径
            config_path: avatar_config.json 路径
            prefer_config: 是否优先使用新配置
        """
        self.prefer_config = prefer_config
        
        # 新配置集成
        self._config = AvatarConfigIntegration(config_path)
        
        # 原 TXT 加载器（用于 fallback）
        self._txt_loader = None
        if txt_base_path:
            try:
                from modules.avatar_table_loader import AvatarTableLoader
                self._txt_loader = AvatarTableLoader(txt_base_path)
                logger.info("HybridAvatarTableLoader: TXT 装扮表加载器已初始化")
            except Exception as e:
                logger.warning(f"初始化 TXT 加载器失败: {e}")
    
    def lookup(self, job: str, part: str, code: int) -> Optional[AvatarInfo]:
        """
        查询装备信息（兼容原接口）
        
        查询顺序:
        1. avatar_config.json（如果 prefer_config=True）
        2. TXT 装扮表
        """
        # 处理 body/skin 别名
        part_key = part if part != 'body' else 'skin'
        
        if self.prefer_config:
            # 先查新配置
            info = self._config.lookup(job, part_key, code)
            if info:
                return info
        
        # fallback 到 TXT
        if self._txt_loader:
            from modules.avatar_table_loader import AvatarInfo as TxtAvatarInfo
            txt_info = self._txt_loader.lookup(job, part_key, code)
            if txt_info:
                return AvatarInfo(
                    code=txt_info.code,
                    part=txt_info.part,
                    icon_index=txt_info.icon_index,
                    name=txt_info.name,
                    suit_name=txt_info.suit_name,
                    source='txt'
                )
        
        return None
    
    def get_name(self, job: str, part: str, code: int) -> Optional[str]:
        """获取装备名（兼容原接口）"""
        info = self.lookup(job, part, code)
        return info.name if info else None
    
    def get_icon_index(self, job: str, part: str, code: int) -> Optional[int]:
        """获取图标索引（兼容原接口）"""
        info = self.lookup(job, part, code)
        return info.icon_index if info else None
    
    def get_suit_name(self, job: str, part: str, code: int) -> Optional[str]:
        """获取套装名（兼容原接口）"""
        info = self.lookup(job, part, code)
        return info.suit_name if info else None
    
    def generate_equ_name(self, job: str, part: str, avatar_code: int, suffix: int) -> Tuple[str, int, bool]:
        """
        生成 equ 的 name 和 icon_index（兼容原 generate_equ_name 函数）
        
        Returns:
            (name, icon_index, found)
        """
        from modules.avatar_table_loader import construct_code
        code = construct_code(avatar_code, suffix)
        
        info = self.lookup(job, part, code)
        if info:
            return info.name, info.icon_index, True
        
        # 默认格式
        default_name = f"{job}_{part}_{code}"
        return default_name, 0, False
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        config_stats = self._config.get_stats()
        return {
            'config_records': config_stats['total_records'],
            'config_jobs': config_stats['jobs'],
            'txt_loader_available': self._txt_loader is not None,
            'prefer_config': self.prefer_config,
        }


# 便捷函数：与原 generate_equ_name 函数签名一致
def generate_equ_name(
    job: str,
    part: str,
    avatar_code: int,
    suffix: int,
    loader: HybridAvatarTableLoader
) -> Tuple[str, int, bool]:
    """
    生成 equ 的 name 标签内容（兼容原函数）
    
    Args:
        job: 职业代码
        part: 部位代码
        avatar_code: avatar 变体代码
        suffix: 后缀索引
        loader: HybridAvatarTableLoader 实例
    
    Returns:
        (name, icon_index, found)
    """
    return loader.generate_equ_name(job, part, avatar_code, suffix)


# 全局单例（可选，用于简化使用）
_default_loader: Optional[HybridAvatarTableLoader] = None


def get_default_loader() -> HybridAvatarTableLoader:
    """获取默认加载器实例（懒加载）"""
    global _default_loader
    if _default_loader is None:
        from config import AVATAR_TABLE_BASE_PATH
        _default_loader = HybridAvatarTableLoader(AVATAR_TABLE_BASE_PATH)
    return _default_loader


def init_default_loader(txt_base_path: str, config_path: Path = Path('avatar_config.json')):
    """初始化默认加载器"""
    global _default_loader
    _default_loader = HybridAvatarTableLoader(txt_base_path, config_path)
