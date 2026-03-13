"""
从 PVF equ 文件同步数据到 avatar_config.json (v2 - 带 icon 路径验证)

功能：
1. 从 PVF 读取时装 equ 文件
2. 筛选 name 不是"英文+数字"组合的文件
3. 提取 name、icon frame、hide parts、icon 路径信息
4. 验证 icon 路径是否与部位匹配，不匹配则使用标准路径
5. 自动备份并更新 avatar_config.json

用法：
    python sync_equ_to_config_v2.py [--config PATH] [--backup-dir PATH] [--dry-run]
"""

import json
import re
import shutil
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent))

from modules.avatar_extractor import AvatarExtractor
from config import PVF_API_HOST, PVF_API_PORT

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 职业映射：equ career -> avatar_config job_key
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

# 装备类型映射：equ type -> avatar_config part
EQUIP_TYPE_MAP = {
    'hat': 'cap',
    'hair': 'hair',
    'face': 'face',
    'breast': 'neck',
    'coat': 'coat',
    'pants': 'pants',
    'waist': 'belt',
    'shoes': 'shoes',
    'skin': 'skin',
}

# equ 装备类型 -> 部位（用于 hide_parts 反向映射）
EQU_TYPE_TO_PART = {
    '[hat avatar]': 'cap',
    '[hair avatar]': 'hair',
    '[face avatar]': 'face',
    '[breast avatar]': 'neck',
    '[coat avatar]': 'coat',
    '[pants avatar]': 'pants',
    '[waist avatar]': 'belt',
    '[shoes avatar]': 'shoes',
    '[skin avatar]': 'skin',
}

# 武器 icon 路径特征（不匹配时装）
WEAPON_ICON_PATTERNS = [
    r'item/new_equipment/\d+_weapon/',
    r'item/equipment/weapon/',
    r'/wp/',
    r'/sswd/',  # swordman sword
    r'/swd/',
    r'/katana/',
    r'/club/',
    r'/lswd/',
    r'/bld/',
    r'/axe/',
    r'/knuckle/',
]

# 职业到 icon 路径的映射
JOB_ICON_MAP = {
    'sm': ('swordman', 'sm'),
    'ft': ('fighter', 'ft'),
    'fm': ('atfighter', 'fm'),
    'gn': ('gunner', 'gn'),
    'gg': ('atgunner', 'gg'),
    'mg': ('mage', 'mg'),
    'mm': ('atmage', 'mm'),
    'pr': ('priest', 'pr'),
    'th': ('thief', 'tf'),
}

# 部位到 icon 文件名的映射
PART_ICON_MAP = {
    'cap': 'acap',
    'hair': 'ahair',
    'face': 'aface',
    'neck': 'aneck',
    'coat': 'acoat',
    'pants': 'apants',
    'belt': 'abelt',
    'shoes': 'ashoes',
    'skin': 'abody',
}


@dataclass
class EquInfo:
    """从 equ 文件提取的信息"""
    code: str
    path: str
    career: str
    part: str
    name: str
    frame: int
    icon_path: str          # 新增：icon 路径
    icon_path_valid: bool   # 新增：路径是否有效
    variation: Tuple[int, int]
    hide_parts: List[str]


def is_english_number_only(name: str) -> bool:
    """检查 name 是否仅为英文+数字组合"""
    if not name or not name.strip():
        return True
    name = name.strip()
    pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*$'
    return bool(re.match(pattern, name))


def extract_name(content: str) -> str:
    """从 equ 内容提取 [name]"""
    match = re.search(r'\[name\]\s*\n\s*`([^`]*)`', content)
    return match.group(1).strip() if match else ""


def extract_icon_info(content: str) -> Tuple[str, int]:
    """
    从 equ 内容提取 [icon] 的路径和 frame
    
    Returns:
        (icon_path, frame)
    """
    match = re.search(r'\[icon\]\s*\n\s*`([^`]*)`\s+(\d+)', content)
    if match:
        return match.group(1).strip(), int(match.group(2))
    return "", 0


def is_valid_avatar_icon_path(icon_path: str) -> bool:
    """
    检查 icon 路径是否是有效的时装路径
    
    Returns:
        True 如果是有效的时装 icon 路径
    """
    if not icon_path:
        return False
    
    icon_path_lower = icon_path.lower()
    
    # 检查是否是武器路径
    for pattern in WEAPON_ICON_PATTERNS:
        if re.search(pattern, icon_path_lower):
            return False
    
    # 检查是否在 item/avatar/ 目录下
    return 'item/avatar/' in icon_path_lower


def generate_correct_icon_path(job_name: str, part: str) -> str:
    """
    生成正确的时装 icon 路径
    
    Args:
        job_name: 职业缩写，如 'sm', 'ft'
        part: 部位，如 'cap', 'coat'
    
    Returns:
        正确的 icon 路径
    """
    job_path, job_prefix = JOB_ICON_MAP.get(job_name, (job_name, job_name))
    part_icon = PART_ICON_MAP.get(part, f'a{part}')
    return f"item/avatar/{job_path}/{job_prefix}_{part_icon}.img"


def extract_hide_equipment(content: str) -> List[str]:
    """从 equ 内容提取 [hide equipment] 中的部位列表"""
    hide_parts = []
    
    match = re.search(
        r'\[hide equipment\](.*?)\[/hide equipment\]',
        content,
        re.DOTALL | re.IGNORECASE
    )
    
    if match:
        section = match.group(1)
        for equ_type_match in re.finditer(r'`([^`]+)`', section):
            equ_type = equ_type_match.group(1).strip()
            part = EQU_TYPE_TO_PART.get(equ_type)
            if part and part not in hide_parts:
                hide_parts.append(part)
    
    return hide_parts


def parse_variation(variation_str: str) -> Tuple[int, int]:
    """解析 variation 字符串为 (code, suffix)"""
    if not variation_str:
        return (0, 0)
    
    parts = variation_str.replace('\t', '_').split('_')
    
    if len(parts) >= 2:
        try:
            return (int(parts[0]), int(parts[1]))
        except ValueError:
            pass
    
    try:
        full = int(variation_str)
        if full < 100:
            return (full, 0)
        else:
            return (full // 100, full % 100)
    except ValueError:
        pass
    
    return (0, 0)


def get_job_key(career: str) -> Optional[str]:
    """将 equ career 转换为 avatar_config job_key"""
    return CAREER_MAP.get(career.lower().strip())


def get_part(equipment_type: str) -> str:
    """将 equipment_type 转换为 avatar_config part"""
    eq_type = equipment_type.lower()
    eq_type = eq_type.replace('[', '').replace(']', '').replace('avatar', '').strip()
    return EQUIP_TYPE_MAP.get(eq_type, eq_type)


def find_config_item(config: Dict, job_key: str, part: str, code: int, suffix: int) -> Optional[Tuple[str, Dict]]:
    """在 avatar_config.json 中查找对应的 item"""
    if job_key not in config:
        return None
    
    items = config[job_key].get('items', {})
    if part not in items:
        return None
    
    part_items = items[part]
    search_code = f"{code}{suffix:02d}"
    
    if search_code in part_items:
        return (search_code, part_items[search_code])
    
    for code_str, item in part_items.items():
        try:
            if int(code_str) == int(search_code):
                return (code_str, item)
        except ValueError:
            continue
    
    return None


def backup_config(config_path: Path, backup_dir: Optional[Path] = None) -> Path:
    """创建配置文件备份"""
    if backup_dir is None:
        backup_dir = config_path.parent / 'backups'
    
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = backup_dir / f"avatar_config_backup_{timestamp}.json"
    
    shutil.copy2(config_path, backup_path)
    logger.info(f"已创建备份: {backup_path}")
    
    return backup_path


def update_config_item(item: Dict, name: str, frame: int, hide_parts: List[str], icon_path: str):
    """更新配置 item"""
    updates = []
    
    if name:
        old_name = item.get('name', '')
        if old_name != name:
            item['name'] = name
            updates.append(f"name: '{old_name}' -> '{name}'")
    
    if frame >= 0:
        old_frame = item.get('frame', -1)
        if old_frame != frame:
            item['frame'] = frame
            updates.append(f"frame: {old_frame} -> {frame}")
    
    if hide_parts is not None:
        old_hide = item.get('hide_parts', [])
        if set(old_hide) != set(hide_parts):
            item['hide_parts'] = hide_parts
            updates.append(f"hide_parts: {old_hide} -> {hide_parts}")
    
    # 可选：保存 icon_path 用于调试
    if icon_path:
        old_icon = item.get('icon_path', '')
        if old_icon != icon_path:
            item['icon_path'] = icon_path  # 可选字段，用于调试
            updates.append(f"icon_path: '{old_icon}' -> '{icon_path}'")
    
    return updates


def load_config(path: Path) -> Dict:
    """加载配置文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_config(path: Path, config: Dict):
    """保存配置文件"""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    logger.info(f"配置已保存: {path}")


def process_all_equ(extractor: AvatarExtractor, config: Dict) -> Tuple[int, int]:
    """处理所有 equ 文件"""
    processed = 0
    updated = 0
    invalid_icon_count = 0
    
    for path, avatar_data in extractor.avatar_data.items():
        processed += 1
        
        content = extractor.file_content_cache.get(path, "")
        if not content:
            continue
        
        # 提取 name
        name = extract_name(content)
        if not name:
            continue
        
        # 筛选：跳过英文+数字的 name
        if is_english_number_only(name):
            logger.debug(f"跳过 [{name}]: 符合英文+数字模式")
            continue
        
        # 提取 icon 信息（路径和 frame）
        icon_path, frame = extract_icon_info(content)
        
        # 验证 icon 路径
        icon_path_valid = is_valid_avatar_icon_path(icon_path)
        if not icon_path_valid:
            invalid_icon_count += 1
            logger.warning(f"Icon 路径无效: {icon_path}")
        
        # 提取 hide_parts
        hide_parts = extract_hide_equipment(content)
        
        # 映射职业和部位
        job_name = None
        for abbr, full_key in CAREER_MAP.items():
            if full_key == get_job_key(avatar_data.career):
                # 反向查找职业缩写
                for a, f in CAREER_MAP.items():
                    if f == get_job_key(avatar_data.career):
                        job_name = a.replace('at ', '').replace(' ', '')
                        if 'at ' in a:
                            job_name = 'at' + job_name
                        break
                break
        
        # 简化：直接使用职业缩写映射
        career_lower = avatar_data.career.lower().strip()
        job_abbr_map = {
            'swordman': 'sm',
            'fighter': 'ft',
            'at fighter': 'fm',
            'gunner': 'gn',
            'at gunner': 'gg',
            'mage': 'mg',
            'at mage': 'mm',
            'priest': 'pr',
            'thief': 'th',
        }
        job_name = job_abbr_map.get(career_lower, 'sm')
        
        job_key = get_job_key(avatar_data.career)
        part = get_part(avatar_data.equipment_type)
        var_code, suffix = parse_variation(avatar_data.variation)
        
        if not job_key:
            logger.warning(f"未知职业: {avatar_data.career}")
            continue
        
        # 生成正确的 icon 路径
        correct_icon_path = generate_correct_icon_path(job_name, part)
        
        logger.info(f"\n处理: {path}")
        logger.info(f"  职业: {avatar_data.career} -> {job_key}")
        logger.info(f"  部位: {avatar_data.equipment_type} -> {part}")
        logger.info(f"  Variation: {avatar_data.variation} -> ({var_code}, {suffix})")
        logger.info(f"  Name: {name}")
        logger.info(f"  Frame: {frame}")
        logger.info(f"  Icon 路径: {icon_path}")
        logger.info(f"  Icon 有效: {'✓' if icon_path_valid else '✗ (将使用: ' + correct_icon_path + ')'}")
        logger.info(f"  Hide parts: {hide_parts}")
        
        # 查找配置中的对应项
        result = find_config_item(config, job_key, part, var_code, suffix)
        
        if result:
            code_str, item = result
            logger.info(f"  找到匹配: {job_key}/{part}/{code_str}")
            
            # 使用正确的 icon 路径（如果原路径无效）
            final_icon_path = icon_path if icon_path_valid else correct_icon_path
            
            updates = update_config_item(item, name, frame, hide_parts, final_icon_path)
            if updates:
                for update in updates:
                    logger.info(f"    更新: {update}")
                updated += 1
            else:
                logger.info(f"    无变化")
        else:
            logger.warning(f"  未找到匹配: {job_key}/{part}/({var_code}, {suffix})")
    
    if invalid_icon_count > 0:
        logger.warning(f"\n共有 {invalid_icon_count} 个文件的 icon 路径无效，已使用标准路径代替")
    
    return processed, updated


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='从 PVF equ 文件同步数据到 avatar_config.json (v2)')
    parser.add_argument('--config', type=Path, default=Path('avatar_config.json'),
                        help='avatar_config.json 路径')
    parser.add_argument('--backup-dir', type=Path, default=None,
                        help='备份目录')
    parser.add_argument('--host', default=PVF_API_HOST,
                        help='PVF API 主机')
    parser.add_argument('--port', type=int, default=PVF_API_PORT,
                        help='PVF API 端口')
    parser.add_argument('--dry-run', action='store_true',
                        help='试运行，不保存修改')
    parser.add_argument('--no-backup', action='store_true',
                        help='不创建备份')
    
    args = parser.parse_args()
    
    # 加载配置
    logger.info(f"加载配置: {args.config}")
    config = load_config(args.config)
    logger.info(f"配置加载完成: {len(config)} 个职业")
    
    # 创建备份
    if not args.no_backup and not args.dry_run:
        backup_config(args.config, args.backup_dir)
    
    # 创建提取器
    logger.info(f"连接 PVF API: {args.host}:{args.port}")
    extractor = AvatarExtractor(host=args.host, port=args.port)
    
    # 解析 lst
    logger.info("解析 equipment.lst...")
    if not extractor.parse_equipment_lst():
        logger.error("解析失败")
        return 1
    
    # 提取 equ 文件
    logger.info("提取 equ 文件...")
    extractor.extract_all()
    
    # 处理并更新
    logger.info("\n处理 equ 文件...")
    processed, updated = process_all_equ(extractor, config)
    
    logger.info(f"\n完成:")
    logger.info(f"  处理文件: {processed}")
    logger.info(f"  更新 items: {updated}")
    
    # 保存
    if not args.dry_run and updated > 0:
        save_config(args.config, config)
    elif args.dry_run:
        logger.info("[试运行] 未保存修改")
    else:
        logger.info("无更新")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
