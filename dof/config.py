"""
项目配置文件
集中管理所有路径、映射关系和常量
"""

from pathlib import Path
from typing import Dict, Tuple, Set

# ==================== 基础路径配置 ====================
# 使用 Path 对象，支持跨平台
BASE_DIR = Path(__file__).parent

# NPK 文件路径
NPK_INPUT_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\NPK")
NPK_BASE_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\base")
NPK_COMPILE_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\compiles")
NPK_OUTPUT_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\deduplicated_npk")
NPK_KR_DIR = Path(r"D:\BaiduNetdiskDownload\ImagePacks2\\")
NPK_JP_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\output\Download\日本-正式服\\")
NPK_NA_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\output\Download\北美地区-正式服\\")

# 数据文件路径
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

AVATAR_DATA_JSON = BASE_DIR / "avatar_data.json"
EQUIPMENT_TAGS_TSV = BASE_DIR / "complete_equipment_tags.tsv"
EQUIPMENT_LST = BASE_DIR / "equ.lst"

# PVF API 配置
PVF_API_HOST = "localhost"
PVF_API_PORT = 27000
PVF_API_TIMEOUT = 30

# ==================== 职业配置 ====================
# 职业映射：缩写 -> (编码, 路径前缀, 装备名)
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



# 职业缩写列表
JOB_ABBREVIATIONS: Tuple[str, ...] = tuple(JOB_MAP.keys())
JOB_FULL_NAMES: Tuple[str, ...] = (
    'swordman', 'gunner_at', 'gunner', 'fighter', 
    'fighter_at', 'mage', 'mage_at', 'priest', 'thief'
)

# ==================== 部位配置 ====================
# 部位映射：名称 -> 编码
PartConfig = Tuple[int, str]
PART_CODE_MAP: Dict[str, PartConfig] = {
    'coat': (0, 'coat'),
    'pants': (1, 'pants'),
    'belt': (2, 'waist'),
    'neck': (3, 'breast'),
    'shoes': (4, 'shoes'),
    'cap': (5, 'hat'),
    'hair': (6, 'hair'),
    'face': (7, 'face'),
    'skin': (8, 'body'),
}

# 部位名称映射：内部名称 -> 装备类型名称
PART_EQU_TYPE_MAP: Dict[str, str] = {
    'belt': 'waist',
    'cap': 'hat',
    'coat': 'coat',
    'face': 'face',
    'hair': 'hair',
    'neck': 'breast',
    'pants': 'pants',
    'shoes': 'shoes'
}

PARTS: Tuple[str, ...] = tuple(PART_CODE_MAP.keys())

# ==================== 装备路径模板 ====================
EQU_PATH_TEMPLATE = "`character/{job}avatar/{part}/{code}.equ`"

# ==================== NPK 处理配置 ====================
NPK_CONFIG = {
    "deduplicate_by": "name",  # 去重维度：name/md5
    "sort_npk_by_name": True,
    "ignore_case_sort": True,
    "keep_first": False,
    "exclude_suffixes": [".log", ".tmp", ".txt"],
}

# ==================== 日志配置 ====================
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE = BASE_DIR / "logs"
LOG_FILE.mkdir(exist_ok=True)
LOG_FILE = LOG_FILE / "app.log"

# ==================== 批处理配置 ====================
BATCH_SIZE = 15
MAX_WORKERS = 3
MAX_RETRIES = 2

# ==================== 正则表达式模式 ====================
# 混合字符串拆分：字母+数字+剩余部分
MIXED_STRING_PATTERN = r'^([a-zA-Z]+)(\d+)(.+)$'

# 装备类型和变体提取
EQUIP_TYPE_PATTERN = r'\[equipment type\]\s*\n\s*`?([^`\t\r\n]+)`?\s*(\d+)?'
VARIATION_PATTERN = r'\[variation\]\s*\n\s*([^\r\n]+)'
