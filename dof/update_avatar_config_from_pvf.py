"""
从 PVF 读取 equ 时装文件，更新 avatar_config.json

功能：
1. 从 PVF 读取 equ 时装文件
2. 筛选出 name 标签不是"英文+数字"组合的 equ 文件
3. 提取 name、图标信息（frame）
4. 更新到对应的 avatar_config.json 中

使用方法：
    python update_avatar_config_from_pvf.py
"""

import json
import re
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Set
from dataclasses import dataclass

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


# 职业映射：从 equ 文件路径中的职业名 -> avatar_config.json 中的职业键
CAREER_TO_JOB_KEY = {
    'swordman': 'swordman_male',
    'fighter': 'fighter_female',  # 需要进一步区分男女
    'at fighter': 'fighter_male',
    'gunner': 'gunner_male',
    'at gunner': 'gunner_female',
    'mage': 'mage_female',
    'at mage': 'mage_male',
    'priest': 'priest_male',
    'thief': 'thief_female',
}

# 部位映射：从 equ 文件中的 equipment_type -> avatar_config.json 中的部位
EQUIP_TYPE_TO_PART = {
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


@dataclass
class EquFileInfo:
    """equ 文件信息"""
    code: str
    path: str
    career: str
    part: str
    name: str
    frame: int
    variation: Tuple[int, int]  # (variation_code, suffix)
    is_valid_name: bool  # True 如果 name 不是英文+数字组合


def is_english_number_pattern(name: str) -> bool:
    """
    检查 name 是否为英文+数字组合
    
    例如：
    - "cap1230" -> True
    - "hat456" -> True
    - "白色末日使者肩饰" -> False
    - "Red Dragon Coat" -> False
    """
    if not name:
        return True  # 空字符串视为符合模式（跳过）
    
    # 去除首尾空格和特殊字符
    name = name.strip()
    
    # 纯英文+数字的组合（允许下划线）
    pattern = r'^[a-zA-Z_][a-zA-Z0-9_]*$'
    return bool(re.match(pattern, name))


def extract_name_from_equ(content: str) -> str:
    """
    从 equ 文件内容中提取 [name] 标签的值
    
    Args:
        content: equ 文件内容
    
    Returns:
        name 值，找不到返回空字符串
    """
    # 匹配 [name]\n\t`值`
    pattern = r'\[name\]\s*\n\s*`([^`]*)`'
    match = re.search(pattern, content)
    if match:
        return match.group(1).strip()
    return ""


def extract_icon_frame_from_equ(content: str) -> int:
    """
    从 equ 文件内容中提取 [icon] 标签的 frame 值
    
    Args:
        content: equ 文件内容
    
    Returns:
        frame 值（整数），找不到返回 0
    """
    # 匹配 [icon]\n\t`路径`\t数字
    pattern = r'\[icon\]\s*\n\s*`[^`]*`\s+(\d+)'
    match = re.search(pattern, content)
    if match:
        return int(match.group(1))
    return 0


def parse_variation(variation_str: str) -> Tuple[int, int]:
    """
    解析 variation 字符串
    
    格式通常为 "code\tsuffix" 或 "code_suffix"
    
    Returns:
        (variation_code, suffix)
    """
    # 尝试按制表符分割
    parts = variation_str.replace('_', '\t').split('\t')
    if len(parts) >= 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    
    # 如果是单个数字
    try:
        code = int(variation_str)
        if code < 100:
            return code, 0
        else:
            return code // 100, code % 100
    except ValueError:
        pass
    
    return 0, 0


def get_part_from_equipment_type(equipment_type: str) -> str:
    """
    从 equipment_type 获取 avatar_config.json 中的部位
    
    Args:
        equipment_type: 如 "hat", "coat" 等
    
    Returns:
        部位名称，如 "cap", "coat" 等
    """
    # 清理字符串
    equipment_type = equipment_type.lower().replace('[', '').replace(']', '').replace('avatar', '').strip()
    
    return EQUIP_TYPE_TO_PART.get(equipment_type, equipment_type)


def get_job_key_from_career(career: str) -> Optional[str]:
    """
    从 career 获取 avatar_config.json 中的职业键
    
    Args:
        career: 如 "swordman", "at fighter" 等
    
    Returns:
        职业键，如 "swordman_male" 等
    """
    career = career.lower().strip()
    return CAREER_TO_JOB_KEY.get(career)


def load_avatar_config(config_path: Path) -> Dict:
    """加载 avatar_config.json"""
    if not config_path.exists():
        logger.error(f"配置文件不存在: {config_path}")
        return {}
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return {}


def save_avatar_config(config_path: Path, config: Dict):
    """保存 avatar_config.json"""
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info(f"配置文件已保存: {config_path}")
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")


def find_item_in_config(config: Dict, job_key: str, part: str, variation_code: int, suffix: int) -> Optional[Tuple[str, Dict]]:
    """
    在配置中查找对应的 item
    
    Args:
        config: 配置字典
        job_key: 职业键
        part: 部位
        variation_code: 变体代码
        suffix: 后缀
    
    Returns:
        (full_code_str, item_dict) 或 None
    """
    if job_key not in config:
        return None
    
    job_data = config[job_key]
    items = job_data.get('items', {})
    
    if part not in items:
        return None
    
    part_items = items[part]
    
    # 构建完整的 code 字符串（如 "10203"）
    full_code_str = f"{variation_code}{suffix:02d}"
    
    if full_code_str in part_items:
        return full_code_str, part_items[full_code_str]
    
    # 尝试其他格式（如无前导零）
    for code_str in part_items.keys():
        try:
            code_int = int(code_str)
            expected_int = int(full_code_str)
            if code_int == expected_int:
                return code_str, part_items[code_str]
        except ValueError:
            continue
    
    return None


def update_config_item(item: Dict, name: str, frame: int):
    """
    更新配置中的 item
    
    Args:
        item: 配置中的 item 字典
        name: 新的 name
        frame: 新的 frame
    """
    # 只更新 name 和 frame，保留其他字段
    if name:
        old_name = item.get('name', '')
        item['name'] = name
        if old_name != name:
            logger.info(f"  更新 name: '{old_name}' -> '{name}'")
    
    if frame >= 0:  # frame 可以是 0
        old_frame = item.get('frame', -1)
        item['frame'] = frame
        if old_frame != frame:
            logger.info(f"  更新 frame: {old_frame} -> {frame}")


def process_equ_files(
    extractor: AvatarExtractor,
    config: Dict,
    config_path: Path
) -> Tuple[int, int]:
    """
    处理 equ 文件并更新配置
    
    Args:
        extractor: AvatarExtractor 实例
        config: 配置字典
        config_path: 配置文件路径
    
    Returns:
        (处理的文件数, 更新的文件数)
    """
    processed = 0
    updated = 0
    
    # 遍历所有提取的 avatar 数据
    for path, avatar_data in extractor.avatar_data.items():
        processed += 1
        
        # 获取 equ 文件内容
        content = extractor.file_content_cache.get(path, "")
        if not content:
            logger.debug(f"跳过 {path}: 无内容")
            continue
        
        # 提取 name
        name = extract_name_from_equ(content)
        if not name:
            logger.debug(f"跳过 {path}: 无 name")
            continue
        
        # 检查 name 是否为英文+数字组合
        if is_english_number_pattern(name):
            logger.debug(f"跳过 {path}: name 符合英文+数字模式 '{name}'")
            continue
        
        # 提取 frame
        frame = extract_icon_frame_from_equ(content)
        
        # 获取职业和部位
        job_key = get_job_key_from_career(avatar_data.career)
        part = get_part_from_equipment_type(avatar_data.equipment_type)
        variation = parse_variation(avatar_data.variation)
        
        if not job_key:
            logger.warning(f"跳过 {path}: 未知职业 '{avatar_data.career}'")
            continue
        
        logger.info(f"\n处理: {path}")
        logger.info(f"  code: {avatar_data.code}")
        logger.info(f"  career: {avatar_data.career} -> {job_key}")
        logger.info(f"  equipment_type: {avatar_data.equipment_type} -> {part}")
        logger.info(f"  variation: {avatar_data.variation} -> {variation}")
        logger.info(f"  name: '{name}'")
        logger.info(f"  frame: {frame}")
        
        # 在配置中查找对应的 item
        result = find_item_in_config(config, job_key, part, variation[0], variation[1])
        
        if result:
            code_str, item = result
            logger.info(f"  找到对应 item: {code_str}")
            update_config_item(item, name, frame)
            updated += 1
        else:
            logger.warning(f"  未找到对应 item: {job_key}/{part}/{variation}")
    
    return processed, updated


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='从 PVF 更新 avatar_config.json')
    parser.add_argument('--config', type=Path, default=Path('avatar_config.json'),
                        help='avatar_config.json 路径')
    parser.add_argument('--host', default=PVF_API_HOST,
                        help='PVF API 主机')
    parser.add_argument('--port', type=int, default=PVF_API_PORT,
                        help='PVF API 端口')
    parser.add_argument('--dry-run', action='store_true',
                        help='试运行，不保存修改')
    
    args = parser.parse_args()
    
    # 加载配置
    logger.info(f"加载配置文件: {args.config}")
    config = load_avatar_config(args.config)
    if not config:
        return 1
    
    logger.info(f"配置加载完成，包含 {len(config)} 个职业")
    
    # 创建提取器
    logger.info(f"连接 PVF API: {args.host}:{args.port}")
    extractor = AvatarExtractor(host=args.host, port=args.port)
    
    # 解析 equipment.lst
    logger.info("解析 equipment.lst...")
    if not extractor.parse_equipment_lst():
        logger.error("解析 lst 失败")
        return 1
    
    # 批量提取 equ 文件内容
    logger.info("提取 equ 文件内容...")
    extractor.extract_all()
    
    # 处理并更新配置
    logger.info("\n处理 equ 文件并更新配置...")
    processed, updated = process_equ_files(extractor, config, args.config)
    
    logger.info(f"\n处理完成:")
    logger.info(f"  处理的文件数: {processed}")
    logger.info(f"  更新的 item 数: {updated}")
    
    # 保存配置
    if not args.dry_run and updated > 0:
        logger.info(f"\n保存配置到: {args.config}")
        save_avatar_config(args.config, config)
    elif args.dry_run:
        logger.info("\n试运行模式，不保存修改")
    else:
        logger.info("\n没有需要更新的内容")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
