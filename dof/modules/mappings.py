"""
Unified Mappings - 统一映射表

集中管理项目中所有职业、部位、装备类型的映射关系
"""

from typing import Dict, Tuple

# ============ 职业映射 ============

# 职业缩写 -> (编码, 路径前缀, 装备名)
JobConfig = Tuple[int, str, str]
JOB_MAP: Dict[str, JobConfig] = {
    'sm': (1, 'swordman/', 'swordman'),
    'ft': (2, 'fighter/', 'fighter'),
    'fm': (3, 'fighter/at_', 'at fighter'),
    'gn': (4, 'gunner/', 'gunner'),
    'gg': (5, 'gunner/at_', 'at gunner'),
    'mg': (6, 'mage/', 'mage'),
    'mm': (7, 'mage/at_', 'at mage'),
    'pr': (8, 'priest/', 'priest'),
    'th': (9, 'thief/', 'thief')
}

# 完整职业名 -> avatar_config job_key
JOB_KEY_MAP = {
    'swordman_male': 'swordman_male',
    'fighter_female': 'fighter_female',
    'fighter_male': 'fighter_male',
    'gunner_male': 'gunner_male',
    'gunner_female': 'gunner_female',
    'mage_female': 'mage_female',
    'mage_male': 'mage_male',
    'priest_male': 'priest_male',
    'thief_female': 'thief_female',
}

# equ career -> avatar_config job_key
CAREER_MAP = {
    'swordman': 'swordman_male',
    'fighter': 'fighter_female',
    'at fighter': 'fighter_male',
    'gunner': 'gunner_male',
    'at gunner': 'gunner_female',
    'mage': 'mage_female',
    'at mage': 'mage_male',
    'priest': 'priest_male',
    'thief': 'thief_female',
}

# 反向映射：avatar_config job_key -> 缩写
JOB_KEY_MAP_REVERSE = {
    'swordman_male': 'sm',
    'fighter_female': 'ft',
    'fighter_male': 'fm',
    'gunner_male': 'gn',
    'gunner_female': 'gg',
    'mage_female': 'mg',
    'mage_male': 'mm',
    'priest_male': 'pr',
    'thief_female': 'th',
}

# [usable job] -> 基础职业映射（只包含常规职业）
USABLE_JOB_TO_BASE = {
    '[swordman]': 'swordman',
    '[fighter]': 'fighter',
    '[gunner]': 'gunner',
    '[mage]': 'mage',
    '[priest]': 'priest',
    '[thief]': 'thief',
}

# 需要跳过的特殊职业标签
SKIP_USABLE_JOBS = {'[creator mage]', '[demonic swordman]'}

# 基础职业 + 路径特征 -> 完整职业
BASE_JOB_TO_FULL = {
    ('swordman', False): 'swordman_male',
    ('swordman', True): 'swordman_male',
    ('fighter', False): 'fighter_female',
    ('fighter', True): 'fighter_male',
    ('gunner', False): 'gunner_male',
    ('gunner', True): 'gunner_female',
    ('mage', False): 'mage_female',
    ('mage', True): 'mage_male',
    ('priest', False): 'priest_male',
    ('priest', True): 'priest_male',
    ('thief', False): 'thief_female',
    ('thief', True): 'thief_female',
}

# 路径关键字 -> 职业映射（备用）
PATH_TO_JOB = {
    'swordman': 'swordman_male',
    'fighter/at_': 'fighter_male',
    'fighter/': 'fighter_female',
    'gunner/at_': 'gunner_female',
    'gunner/': 'gunner_male',
    'mage/at_': 'mage_male',
    'mage/': 'mage_female',
    'priest': 'priest_male',
    'thief': 'thief_female',
}


# ============ 部位映射 ============

# 部位名称 -> 编码
PartConfig = Tuple[int, str]
PART_CODE_MAP: Dict[str, PartConfig] = {
    'coat': (0, 'coat'),
    'pants': (1, 'pants'),
    'neck': (2, 'breast'),
    'belt': (3, 'waist'),
    'shoes': (4, 'shoes'),
    'cap': (5, 'hat'),
    'hair': (6, 'hair'),
    'face': (7, 'face'),
    'skin': (8, 'skin'),
}

# 部位名称 -> 装备类型名称
PART_EQU_TYPE_MAP: Dict[str, str] = {
    'belt': 'waist',
    'cap': 'hat',
    'coat': 'coat',
    'face': 'face',
    'hair': 'hair',
    'neck': 'breast',
    'pants': 'pants',
    'shoes': 'shoes',
    'skin': 'skin',
}

# [equipment type] -> 部位名映射
EQU_TYPE_TO_PART = {
    '[coat avatar]': 'coat',
    '[pants avatar]': 'pants',
    '[waist avatar]': 'belt',
    '[breast avatar]': 'neck',
    '[shoes avatar]': 'shoes',
    '[hat avatar]': 'cap',
    '[hair avatar]': 'hair',
    '[face avatar]': 'face',
    '[skin avatar]': 'skin',
}

# 装扮表部位 -> TSV equipment type
PART_TO_EQUIP_TYPE = {
    'cap': 'hat',
    'hair': 'hair',
    'face': 'face',
    'neck': 'breast',
    'coat': 'coat',
    'pants': 'pants',
    'belt': 'waist',
    'shoes': 'shoes',
    'skin': 'skin',
}


# ============ 图标映射 ============

# avatar_config job_key -> IconMatcher job
JOB_TO_MATCHER_JOB = {
    'swordman_male': 'swordman',
    'fighter_female': 'fighter',
    'fighter_male': 'atfighter',
    'gunner_male': 'gunner',
    'gunner_female': 'atgunner',
    'mage_female': 'mage',
    'mage_male': 'atmage',
    'priest_male': 'priest',
    'thief_female': 'thief',
}

# IconMatcher job -> avatar_config job_key
MATCHER_JOB_TO_JOB_KEY = {v: k for k, v in JOB_TO_MATCHER_JOB.items()}


# ============ 便利函数 ============

def get_job_key(career: str) -> str:
    """将 equ career 转换为 avatar_config job_key"""
    return CAREER_MAP.get(career.lower().strip())


def get_part(equipment_type: str) -> str:
    """将 equipment_type 转换为 avatar_config part"""
    eq_type = equipment_type.lower()
    eq_type = eq_type.replace('[', '').replace(']', '').replace('avatar', '').strip()
    return PART_EQU_TYPE_MAP.get(eq_type, eq_type)


def get_job_for_matcher(job_key: str) -> str:
    """将 avatar_config job_key 转换为 IconMatcher 使用的 job"""
    return JOB_TO_MATCHER_JOB.get(job_key)
