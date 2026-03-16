"""
从 PVF equ 文件同步数据到 avatar_config.json (v5 - 图标对比匹配)

功能：
1. 从 PVF 读取时装 equ 文件
2. 对于非标准路径的 icon，使用像素级对比找到标准 NPK 中的对应帧
3. 提取 name、hide parts 信息
4. 自动备份并更新 avatar_config.json

标准NPK路径示例:
    E:\\DOF\\Tools\\blackcat.6.12\\output\\Download\\中国大陆-魔界

PVF NPK路径示例:
    D:\\BaiduNetdiskDownload\\ImagePacks2

用法:
    python sync_equ_to_config_v5.py 
        --standard-npk-dir "E:\\...\\中国大陆-魔界"
        --pvf-npk-dir "D:\\...\\ImagePacks2"
        [--config PATH] [--backup-dir PATH] [--dry-run]
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
from modules.icon_matcher import IconMatcher
from config import PVF_API_HOST, PVF_API_PORT, STANDARD_NPK_DIR, PVF_NPK_DIR

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

# 标准职业目录白名单（小写）
VALID_JOB_FOLDERS = {
    'swordman', 'fighter', 'atfighter', 'gunner', 'atgunner',
    'mage', 'atmage', 'priest', 'thief'
}


# 严格的路径格式验证正则表达式
# 格式: item/avatar/{职业目录}/{前缀}_a{部位}.img
STRICT_ICON_PATH_PATTERN = re.compile(
    r'^item/avatar/([a-zA-Z]+)/[a-zA-Z]+_a(?:cap|coat|hair|face|neck|pants|belt|shoes|skin|body)\.img$',
    re.IGNORECASE
)


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
    """从 equ 内容提取 [icon] 的路径和 frame"""
    match = re.search(r'\[icon\]\s*\n\s*`([^`]*)`\s+(\d+)', content)
    if match:
        return match.group(1).strip(), int(match.group(2))
    return "", 0


def is_valid_icon_path_strict(icon_path: str) -> bool:
    """
    严格验证 icon 路径格式
    必须符合: item/avatar/{标准职业目录}/{前缀}_a{部位}.img
    """
    if not icon_path:
        return False
    
    match = STRICT_ICON_PATH_PATTERN.match(icon_path)
    if not match:
        return False
    
    job_folder = match.group(1).lower()
    return job_folder in VALID_JOB_FOLDERS


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


def has_expand_ani(content: str) -> bool:
    """检查 equ 内容是否包含 [expand ani] 标签"""
    return bool(re.search(r'\[expand ani\]', content, re.IGNORECASE))


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


def get_job_for_matcher(job_key: str) -> Optional[str]:
    """
    将 avatar_config job_key 转换为 IconMatcher 使用的 job
    
    例如: 'fighter_male' -> 'atfighter'
    """
    reverse_map = {
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
    return reverse_map.get(job_key)


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


def update_config_item(
    item: Dict,
    name: str,
    frame: int,
    hide_parts: List[str],
    icon_path_valid: bool,
    name_is_english_only: bool = False,
    frame_from_icon_match: bool = False
):
    """
    更新配置 item
    
    Args:
        frame_from_icon_match: frame 是否来自图标匹配（vs 直接读取）
    """
    updates = []
    
    # 更新 name（除非是英文+数字组合）
    if name and not name_is_english_only:
        old_name = item.get('name', '')
        if old_name != name:
            item['name'] = name
            updates.append(f"name: '{old_name}' -> '{name}'")
    elif name_is_english_only:
        updates.append(f"name: 未更新 (英文+数字组合)")
    
    # 更新 frame
    if frame >= 0:
        old_frame = item.get('frame', -1)
        source = "图标匹配" if frame_from_icon_match else "equ文件"
        if old_frame != frame:
            item['frame'] = frame
            updates.append(f"frame: {old_frame} -> {frame} (来自{source})")
    
    # 始终更新 hide_parts
    if hide_parts is not None:
        old_hide = item.get('hide_parts', [])
        if set(old_hide) != set(hide_parts):
            item['hide_parts'] = hide_parts
            updates.append(f"hide_parts: {old_hide} -> {hide_parts}")
    
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


def process_all_equ(
    extractor: AvatarExtractor,
    config: Dict,
    icon_matcher: Optional[IconMatcher] = None
) -> Tuple[int, int, int, int]:
    """
    处理所有 equ 文件
    
    Returns:
        (处理数, 标准路径数, 图标匹配数, 更新数)
    """
    processed = 0
    standard_path_count = 0
    icon_match_count = 0
    updated = 0
    
    for path, avatar_data in extractor.avatar_data.items():
        processed += 1
        
        content = extractor.file_content_cache.get(path, "")
        if not content:
            continue
        
        # 跳过包含 [expand ani] 的 equ 文件
        if has_expand_ani(content):
            logger.debug(f"跳过 [expand ani] 装备: {path}")
            continue
        
        # 提取 name
        name = extract_name(content)
        if not name:
            continue
        
        # 检查 name 是否为英文+数字组合
        name_is_english_only = is_english_number_only(name)
        
        # 提取 icon 信息
        icon_path, frame = extract_icon_info(content)
        
        # 验证 icon 路径
        icon_path_valid = is_valid_icon_path_strict(icon_path)
        frame_from_icon_match = False
        
        if icon_path_valid:
            # 标准路径，直接使用 equ 中的 frame
            standard_path_count += 1
        elif icon_matcher:
            # 非标准路径，尝试图标匹配
            job_key = get_job_key(avatar_data.career)
            part = get_part(avatar_data.equipment_type)
            matcher_job = get_job_for_matcher(job_key) if job_key else None
            
            if matcher_job and icon_path and frame >= 0:
                matched_frame = icon_matcher.find_matching_frame(
                    job=matcher_job,
                    part=part,
                    pvf_img=icon_path,
                    pvf_frame=frame
                )
                if matched_frame is not None:
                    frame = matched_frame
                    icon_match_count += 1
                    frame_from_icon_match = True
                    logger.info(f"图标匹配成功: {path} -> {job_key}/{part} frame {matched_frame}")
                else:
                    logger.warning(f"图标匹配失败: {path} (icon: {icon_path}#{frame})")
                    # 保留原始 frame，但标记为无效
                    frame = -1
            else:
                frame = -1
        else:
            # 没有 icon_matcher，非标准路径不更新 frame
            frame = -1
        
        # 提取 hide_parts
        hide_parts = extract_hide_equipment(content)
        
        # 映射职业和部位
        job_key = get_job_key(avatar_data.career)
        part = get_part(avatar_data.equipment_type)
        var_code, suffix = parse_variation(avatar_data.variation)
        
        if not job_key:
            continue
        
        # 查找配置中的对应项
        result = find_config_item(config, job_key, part, var_code, suffix)
        
        if result:
            code_str, item = result
            
            updates = update_config_item(
                item, name, frame, hide_parts,
                icon_path_valid, name_is_english_only,
                frame_from_icon_match
            )
            if updates:
                for update in updates:
                    logger.info(f"  [{path}] {update}")
                updated += 1
        else:
            logger.debug(f"未找到匹配配置: {job_key}/{part}/({var_code}, {suffix})")
    
    return processed, standard_path_count, icon_match_count, updated


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='从 PVF equ 文件同步数据到 avatar_config.json (v5 - 图标对比匹配)'
    )
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
    
    # 图标匹配相关参数（可选，默认使用config.py中的配置）
    parser.add_argument('--standard-npk-dir', type=Path, default=STANDARD_NPK_DIR,
                        help='标准NPK目录路径（默认使用config.py中的STANDARD_NPK_DIR）')
    parser.add_argument('--pvf-npk-dir', type=Path, default=PVF_NPK_DIR,
                        help='PVF NPK目录路径（默认使用config.py中的PVF_NPK_DIR）')
    parser.add_argument('--skip-icon-match', action='store_true',
                        help='跳过图标匹配（仅使用标准路径）')
    parser.add_argument('--rebuild-cache', action='store_true',
                        help='强制重建标准图标缓存')
    
    args = parser.parse_args()
    
    # 加载配置
    logger.info(f"加载配置: {args.config}")
    config = load_config(args.config)
    logger.info(f"配置加载完成: {len(config)} 个职业")
    
    # 创建备份
    if not args.no_backup and not args.dry_run:
        backup_config(args.config, args.backup_dir)
    
    # 初始化图标匹配器
    icon_matcher = None
    if not args.skip_icon_match:
        logger.info("初始化图标匹配器...")
        icon_matcher = IconMatcher(
            standard_npk_dir=args.standard_npk_dir,
            pvf_npk_dir=args.pvf_npk_dir
        )
        
        # 构建标准图标缓存
        logger.info("构建标准图标缓存...")
        icon_matcher.build_standard_cache(force_rebuild=args.rebuild_cache)
        
        # 构建PVF NPK映射
        logger.info("构建PVF NPK映射...")
        icon_matcher.build_pvf_npk_map()
    
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
    try:
        processed, standard_count, match_count, updated = process_all_equ(
            extractor, config, icon_matcher
        )
    finally:
        # 确保释放资源
        if icon_matcher:
            icon_matcher.close()
    
    logger.info(f"\n完成:")
    logger.info(f"  处理文件: {processed}")
    logger.info(f"  标准路径: {standard_count}")
    logger.info(f"  图标匹配: {match_count}")
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
