"""
试衣间常量配置模块
集中管理所有常量、映射关系和配置
"""

from typing import Dict, List, Tuple

# =============================================================================
# 图层优先级配置
# =============================================================================
LAYER_DICT: Dict[str, int] = {
    "coat_f": 2850, "neck_f": 2840, "face_f": 2830, "cap_f": 2810,
    "belt_e": 2800, "neck_e": 2780, "neck_ef": 2751, "face_g": 2750,
    "face_a": 2700, "cap_c": 2500, "hair_c": 2400, "coat_c": 2300,
    "neck_g": 2251, "neck_cf": 2201, "neck_c": 2200, "cap_g": 2125,
    "cap_a": 2100, "hair_a": 2000, "neck_xf": 1980, "neck_x": 1975,
    "neck_z": 1963, "coat_x": 1960, "belt_f": 1952, "belt_g": 1951,
    "belt_c": 1950, "belt_c1": 1949, "face_c": 1925, "neck_a": 1900,
    "coat_g": 1850, "coat_a": 1800, "belt_a": 1700, "pants_f": 1651,
    "pants_c": 1650, "shoes_f": 1601, "shoes_c": 1600, "pants_g": 1501,
    "pants_a": 1500, "shoes_g": 1450, "shoes_a": 1400, "pants_b": 1300,
    "shoes_h": 1201, "shoes_b": 1200, "shoes_d": 1190, "pants_h": 1151,
    "pants_d": 1150, "belt_b": 1100, "neck_bf": 1050, "neck_b": 1000,
    "coat_h": 925, "coat_b": 900, "belt_h": 851, "belt_d": 850,
    "belt_d1": 849, "hair_b": 800, "cap_h": 750, "cap_b": 700,
    "neck_df": 650, "neck_d": 600, "neck_h": 550, "coat_d": 500,
    "hair_d": 400, "cap_d": 300, "neck_kf": 291, "neck_k": 290,
    "face_h": 270, "face_b": 100, "hair_f1": 20,
}

# =============================================================================
# 职业配置
# =============================================================================
JOB_CONFIG: Dict[str, Dict[str, str]] = {
    "swordman_male": {"name": "鬼剑士(男)", "folder": "swordman", "code": "sm"},
    "fighter_female": {"name": "格斗家(女)", "folder": "fighter", "code": "ft"},
    "fighter_male": {"name": "格斗家(男)", "folder": "fighter_at", "code": "fm"},
    "gunner_male": {"name": "神枪手(男)", "folder": "gunner", "code": "gn"},
    "gunner_female": {"name": "神枪手(女)", "folder": "gunner_at", "code": "gg"},
    "mage_female": {"name": "魔法师(女)", "folder": "mage", "code": "mg"},
    "mage_male": {"name": "魔法师(男)", "folder": "mage_at", "code": "mm"},
    "priest_male": {"name": "圣职者(男)", "folder": "priest", "code": "pr"},
    "thief_female": {"name": "暗夜使者", "folder": "thief", "code": "th"},
}

# 职业代码到配置的反向映射
JOB_CODE_MAP: Dict[str, Dict[str, str]] = {
    cfg["code"]: {"key": k, **cfg}
    for k, cfg in JOB_CONFIG.items()
}

# =============================================================================
# 部位配置
# =============================================================================
PARTS: List[str] = ["cap", "hair", "face", "neck", "coat", "pants", "belt", "shoes", "skin"]

# 图层绘制顺序（从下到上）
LAYER_ORDER: List[str] = ["skin", "pants", "coat", "belt", "neck", "shoes", "hair", "face", "cap"]

# UI 显示名称
PART_NAMES: Dict[str, str] = {
    "cap": "帽子", "hair": "头发", "face": "脸部",
    "neck": "胸部", "coat": "上衣", "belt": "腰带",
    "pants": "裤子", "shoes": "鞋子", "skin": "皮肤",
}

# 中文部位名（用于装扮表）
CN_PART_NAMES: Dict[str, str] = {
    "cap": "头饰", "hair": "头发", "face": "脸部",
    "neck": "胸部", "coat": "上衣", "belt": "腰带",
    "pants": "裤子", "shoes": "鞋子", "skin": "皮肤",
}

# =============================================================================
# 动画配置
# =============================================================================
# 动作类型映射
ACTION_TYPES: Dict[str, str] = {
    "待机": "stand",
    "走路": "walk", 
    "跑步": "run",
    "攻击": "attack",
}

# 默认动画帧延迟（毫秒）
DEFAULT_FRAME_DELAY = 150

# =============================================================================
# UI 配置
# =============================================================================
# 图标模式配置
ICON_LAYOUT_CONFIG = {
    "8x8": {
        "items_per_page": 64,
        "item_size": 72,
        "thumb_size": 56,
        "cols": 8,
    },
    "4x4": {
        "items_per_page": 16,
        "item_size": 144,
        "thumb_size": 112,
        "cols": 4,
    },
}

# 缓存配置
CACHE_CONFIG = {
    "memory_cache_size": 500,  # 内存缓存大小
    "disk_cache_size": 2000,   # 磁盘缓存大小
    "thumbnail_size": (56, 56),
    "preview_size": (80, 80),
    "icon_size": (56, 56),
}

# =============================================================================
# 文件路径配置
# =============================================================================
# 配置文件名
SUIT_CONFIG_FILE = "avatar_config.json"
CACHE_META_FILE = "dressing_room_cache.json"

# NPK 相关
NPK_CACHE_FILE = "npk_cache.json"
ICON_NPK_SUFFIX = "_icon"

# =============================================================================
# 图层处理配置
# =============================================================================
def get_layer_priority(part: str, layer: str) -> int:
    """获取图层优先级，值越小越在下层"""
    key = f"{part}_a" if layer == "default" else f"{part}_{layer}"
    return LAYER_DICT.get(key, 0 if part == "skin" else 3000)


def is_f_layer(layer_name: str) -> bool:
    """判断图层名是否为f层（发光层）"""
    if not layer_name:
        return False
    return layer_name.endswith('f')
