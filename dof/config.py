"""
项目配置文件
集中管理所有路径、映射关系和常量
"""

from pathlib import Path
from typing import Dict, Tuple, Set

# ==================== 基础路径配置 ====================
# 使用 Path 对象，支持跨平台
BASE_DIR = Path(__file__).parent

AVATAR_TABLE_BASE_PATH = r'D:\DOF\output\Avatar'

# NPK 文件路径
NPK_INPUT_DIR = Path(r"D:\DOF\AVATAR\com")
NPK_BASE_DIR = Path(r"D:\DOF\output\Download\中国大陆-天界")


NPK_COMPILE_DIR = Path(r"D:\DOF\AVATAR\o")


NPK_OUTPUT_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\deduplicated_npk")

NPK_KR_DIR = Path(r"D:\BaiduNetdiskDownload\ImagePacks2\\")
NPK_JP_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\output\Download\日本-正式服\\")
NPK_NA_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\output\Download\北美地区-正式服\\")

# ==================== 图标匹配配置 ====================
# 标准NPK目录（包含 sprite_item_avatar_xxx.NPK 的目录）
STANDARD_NPK_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\output\Download\中国大陆-魔界")

# PVF NPK目录（PVF对应的NPK文件目录）
PVF_NPK_DIR = Path(r"E:\DOF\Clients\DNF\ImagePacks2")

# 数据文件路径
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

AVATAR_DATA_JSON = BASE_DIR / "output/avatar_data.json"

# 装扮表路径配置
AVATAR_TABLE_DIR = Path(r"E:\DOF\Tools\blackcat.6.12\files\table\res\table\table.bin")

# 装扮表文件名映射（职业代码 -> 文件名，不含扩展名）
AVATAR_TABLE_FILES = {
    'sm': '鬼剑士(男)装扮表',
    'ft': '格斗家(女)装扮表',
    'fm': '格斗家(男)装扮表',
    'gn': '神枪手(男)装扮表',
    'gg': '神枪手(女)装扮表',
    'mg': '魔法师(女)装扮表',
    'mm': '魔法师(男)装扮表',
    'pr': '圣职者(男)装扮表',
    'th': '暗夜使者装扮表',
}
EQUIPMENT_TAGS_TSV = BASE_DIR / "output/complete_equipment_tags.tsv"
EQUIPMENT_LST = BASE_DIR / "output/equ.lst"
SHOP_ETC = BASE_DIR / "output/shop.etc"

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
    'neck': (2, 'breast'),
    'belt': (3, 'waist'),
    'shoes': (4, 'shoes'),
    'cap': (5, 'hat'),
    'hair': (6, 'hair'),
    'face': (7, 'face'),
    'skin': (8, 'skin'),
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
    'shoes': 'shoes',
    'skin': 'skin',
}

PARTS: Tuple[str, ...] = tuple(PART_CODE_MAP.keys())

# ==================== 装备路径模板 ====================
EQU_PATH_TEMPLATE = "`equipment/character/{job}avatar/{part}/{code}.equ`"

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

# ==================== 图层层级配置 ====================
LAYER_DICT = {
    'coat_f': 2850, 'neck_f': 2840, 'face_f': 2830, 'cap_f': 2810,
    'belt_e': 2800, 'neck_e': 2780, 'neck_ef': 2751, 'face_g': 2750,
    'face_a': 2700, 'cap_c': 2500, 'hair_c': 2400, 'coat_c': 2300,
    'neck_g': 2251, 'neck_cf': 2201, 'neck_c': 2200, 'cap_g': 2125,
    'cap_a': 2100, 'hair_a': 2000, 'neck_xf': 1980, 'neck_x': 1975,
    'neck_z': 1963, 'coat_x': 1960, 'belt_f': 1952, 'belt_g': 1951,
    'belt_c': 1950, 'belt_c1': 1949, 'face_c': 1925, 'neck_a': 1900,
    'coat_g': 1850, 'coat_a': 1800, 'belt_a': 1700, 'pants_f': 1651,
    'pants_c': 1650, 'shoes_f': 1601, 'shoes_c': 1600, 'pants_g': 1501,
    'pants_a': 1500, 'shoes_g': 1450, 'shoes_a': 1400, 'pants_b': 1300,
    'shoes_h': 1201, 'shoes_b': 1200, 'shoes_d': 1190, 'pants_h': 1151,
    'pants_d': 1150, 'belt_b': 1100, 'neck_bf': 1050, 'neck_b': 1000,
    'coat_h': 925, 'coat_b': 900, 'belt_h': 851, 'belt_d': 850,
    'belt_d1': 849, 'hair_b': 800, 'cap_h': 750, 'cap_b': 700,
    'neck_df': 650, 'neck_d': 600, 'neck_h': 550, 'coat_d': 500,
    'hair_d': 400, 'cap_d': 300, 'neck_kf': 291, 'neck_k': 290,
    'face_h': 270, 'face_b': 100, 'hair_f1': 20
}

# ==================== 正则表达式模式 ====================
MIXED_STRING_PATTERN = r'^([a-zA-Z]+)(\d+)(.+)$'
EQUIP_TYPE_PATTERN = r'\[equipment type\]\s*\n\s*`?([^`\t\r\n]+)`?\s*(\d+)?'
VARIATION_PATTERN = r'\[variation\]\s*\n\s*([^\r\n]+)'

# ==================== Equ 文件生成配置 ====================
EQU_GENERATION_CONFIG = {
    "write_equ_to_local": False,   # 是否将 equ 文件写入本地目录
    "import_to_pvf": True,       # 是否将 equ 文件导入到 PVF
    "equ_output_dir": BASE_DIR / "equipment",  # equ 文件输出目录
}
