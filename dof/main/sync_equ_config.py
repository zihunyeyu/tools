"""
Sync Equ Config - 装备配置同步工具（统一版）

合并功能：
- v4: 严格路径验证（--strict-only模式）
- v5: 像素级图标匹配（默认模式）

功能：
1. 从 PVF equ 文件同步数据到 avatar_config.json
2. 支持像素级图标对比匹配（非标准路径）
3. 支持严格路径验证模式
4. 自动跳过包含 [expand ani] 的装备
5. 过滤英文+数字模式的名称

用法:
    python main/sync_equ_config.py 
        --standard-npk-dir "E:\...\中国大陆-魔界"
        --pvf-npk-dir "D:\...\ImagePacks2"
        [--strict-only] [--rebuild-cache] [--dry-run]
"""

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.mappings import get_job_key, get_part, get_job_for_matcher
from modules.common_utils import (
    setup_logging, init_pvf_api, backup_file,
    load_json, save_json, ProgressTracker, StatsCollector
)
from modules.avatar_extractor import AvatarExtractor
from modules.icon_matcher import IconMatcher
from config import STANDARD_NPK_DIR, PVF_NPK_DIR

logger = logging.getLogger(__name__)


# ============ 常量定义 ============

# equ 装备类型 -> 部位
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

# 严格验证：标准职业目录白名单
VALID_JOB_FOLDERS = {
    'swordman', 'fighter', 'atfighter', 'gunner', 'atgunner',
    'mage', 'atmage', 'priest', 'thief'
}

# 严格验证：icon路径正则
STRICT_ICON_PATTERN = re.compile(
    r'^item/avatar/([a-zA-Z]+)/[a-zA-Z]+_a(?:cap|coat|hair|face|neck|pants|belt|shoes|skin|body)\.img$',
    re.IGNORECASE
)


# ============ 工具函数 ============

def is_english_number_only(name: str) -> bool:
    """检查 name 是否仅为英文+数字组合"""
    if not name or not name.strip():
        return True
    return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name.strip()))


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


def extract_hide_equipment(content: str) -> List[str]:
    """从 equ 内容提取 [hide equipment] 中的部位列表"""
    hide_parts = []
    match = re.search(
        r'\[hide equipment\](.*?)\[/hide equipment\]',
        content, re.DOTALL | re.IGNORECASE
    )
    if match:
        for equ_type_match in re.finditer(r'`([^`]+)`', match.group(1)):
            equ_type = equ_type_match.group(1).strip()
            part = EQU_TYPE_TO_PART.get(equ_type)
            if part and part not in hide_parts:
                hide_parts.append(part)
    return hide_parts


def has_expand_ani(content: str) -> bool:
    """检查 equ 内容是否包含 [expand ani] 标签"""
    return bool(re.search(r'\[expand ani\]', content, re.IGNORECASE))


def is_valid_icon_path_strict(icon_path: str) -> bool:
    """严格验证 icon 路径格式"""
    if not icon_path:
        return False
    match = STRICT_ICON_PATTERN.match(icon_path)
    if not match:
        return False
    return match.group(1).lower() in VALID_JOB_FOLDERS


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
        return (full // 100, full % 100) if full >= 100 else (full, 0)
    except ValueError:
        pass
    
    return (0, 0)


def find_config_item(
    config: Dict,
    job_key: str,
    part: str,
    code: int,
    suffix: int
) -> Optional[Tuple[str, Dict]]:
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


# ============ 主处理类 ============

class EquConfigSyncer:
    """装备配置同步器"""
    
    def __init__(
        self,
        config: Dict,
        icon_matcher: Optional[IconMatcher] = None,
        strict_only: bool = False
    ):
        """
        初始化同步器
        
        Args:
            config: avatar_config配置
            icon_matcher: 图标匹配器（strict_only=False时需要）
            strict_only: 是否仅使用严格路径验证（不启用图标匹配）
        """
        self.config = config
        self.icon_matcher = icon_matcher
        self.strict_only = strict_only
        self.stats = StatsCollector()
    
    def process_all(
        self,
        extractor: AvatarExtractor,
        progress_interval: int = 100
    ) -> int:
        """
        处理所有 equ 文件
        
        Returns:
            更新的item数量
        """
        total = len(extractor.avatar_data)
        tracker = ProgressTracker(total, progress_interval)
        updated = 0
        
        logger.info(f"开始处理 {total} 个 equ 文件...")
        
        for path, avatar_data in extractor.avatar_data.items():
            self.stats.increment('processed')
            tracker.update()
            
            content = extractor.file_content_cache.get(path, "")
            if not content:
                continue
            
            # 跳过 [expand ani]
            if has_expand_ani(content):
                self.stats.increment('skipped_expand_ani')
                logger.debug(f"跳过 [expand ani]: {path}")
                continue
            
            # 提取信息
            name = extract_name(content)
            if not name:
                continue
            
            name_is_english = is_english_number_only(name)
            icon_path, frame = extract_icon_info(content)
            hide_parts = extract_hide_equipment(content)
            
            # 处理 frame
            icon_path_valid = is_valid_icon_path_strict(icon_path)
            frame_from_match = False
            
            if icon_path_valid:
                self.stats.increment('standard_path')
            elif not self.strict_only and self.icon_matcher:
                # 尝试图标匹配
                job_key = get_job_key(avatar_data.career)
                part = get_part(avatar_data.equipment_type)
                matcher_job = get_job_for_matcher(job_key) if job_key else None
                
                if matcher_job and icon_path and frame >= 0:
                    matched = self.icon_matcher.find_matching_frame(
                        job=matcher_job, part=part,
                        pvf_img=icon_path, pvf_frame=frame
                    )
                    if matched is not None:
                        frame = matched
                        frame_from_match = True
                        self.stats.increment('icon_matched')
                    else:
                        self.stats.increment('icon_match_failed')
                        frame = -1
                else:
                    frame = -1
            else:
                # strict_only模式或非标准路径但没有matcher
                frame = -1
            
            # 更新配置
            job_key = get_job_key(avatar_data.career)
            part = get_part(avatar_data.equipment_type)
            var_code, suffix = parse_variation(avatar_data.variation)
            
            if not job_key:
                continue
            
            result = find_config_item(self.config, job_key, part, var_code, suffix)
            if result:
                code_str, item = result
                updates = self._update_item(
                    item, name, frame, hide_parts,
                    name_is_english, frame_from_match
                )
                if updates:
                    updated += 1
        
        tracker.finish()
        return updated
    
    def _update_item(
        self,
        item: Dict,
        name: str,
        frame: int,
        hide_parts: List[str],
        name_is_english: bool,
        frame_from_match: bool
    ) -> List[str]:
        """更新单个item"""
        updates = []
        
        # 更新 name
        if name and not name_is_english:
            old = item.get('name', '')
            if old != name:
                item['name'] = name
                updates.append(f"name: '{old}' -> '{name}'")
        
        # 更新 frame
        if frame >= 0:
            old = item.get('frame', -1)
            if old != frame:
                item['frame'] = frame
                source = "图标匹配" if frame_from_match else "equ文件"
                updates.append(f"frame: {old} -> {frame} ({source})")
        
        # 更新 hide_parts
        if hide_parts is not None:
            old = item.get('hide_parts', [])
            if set(old) != set(hide_parts):
                item['hide_parts'] = hide_parts
                updates.append(f"hide_parts: {old} -> {hide_parts}")
        
        for update in updates:
            logger.info(f"  {update}")
        
        return updates


# ============ 主函数 ============

def main():
    parser = argparse.ArgumentParser(
        description='从 PVF equ 文件同步数据到 avatar_config.json'
    )
    parser.add_argument('--config', type=Path, default=Path('avatar_config.json'),
                        help='avatar_config.json 路径')
    parser.add_argument('--backup-dir', type=Path, default=None,
                        help='备份目录')
    parser.add_argument('--host', default='localhost',
                        help='PVF API 主机')
    parser.add_argument('--port', type=int, default=27000,
                        help='PVF API 端口')
    parser.add_argument('--dry-run', action='store_true',
                        help='试运行，不保存修改')
    parser.add_argument('--no-backup', action='store_true',
                        help='不创建备份')
    
    # 模式选择
    parser.add_argument('--strict-only', action='store_true',
                        help='仅使用严格路径验证，不启用图标匹配（v4模式）')
    
    # 图标匹配参数
    parser.add_argument('--standard-npk-dir', type=Path, default=STANDARD_NPK_DIR,
                        help='标准NPK目录路径')
    parser.add_argument('--pvf-npk-dir', type=Path, default=PVF_NPK_DIR,
                        help='PVF NPK目录路径')
    parser.add_argument('--rebuild-cache', action='store_true',
                        help='强制重建标准图标缓存')
    
    args = parser.parse_args()
    
    # 设置日志
    setup_logging()
    
    # 加载配置
    logger.info(f"加载配置: {args.config}")
    config = load_json(args.config)
    
    # 创建备份
    if not args.no_backup and not args.dry_run:
        backup_file(args.config, args.backup_dir)
    
    # 初始化图标匹配器（如果不是strict-only模式）
    icon_matcher = None
    if not args.strict_only:
        if not args.standard_npk_dir or not args.pvf_npk_dir:
            logger.error("图标匹配模式需要 --standard-npk-dir 和 --pvf-npk-dir")
            return 1
        
        logger.info("初始化图标匹配器...")
        icon_matcher = IconMatcher(
            standard_npk_dir=args.standard_npk_dir,
            pvf_npk_dir=args.pvf_npk_dir
        )
        logger.info("构建标准图标缓存...")
        icon_matcher.build_standard_cache(force_rebuild=args.rebuild_cache)
        logger.info("构建PVF NPK映射...")
        icon_matcher.build_pvf_npk_map()
    else:
        logger.info("使用严格路径验证模式（不启用图标匹配）")
    
    # 创建同步器
    syncer = EquConfigSyncer(config, icon_matcher, args.strict_only)
    
    # 创建提取器
    logger.info(f"连接 PVF API: {args.host}:{args.port}")
    extractor = AvatarExtractor(host=args.host, port=args.port)
    
    logger.info("解析 equipment.lst...")
    if not extractor.parse_equipment_lst():
        logger.error("解析失败")
        return 1
    
    logger.info("提取 equ 文件...")
    extractor.extract_all()
    
    # 处理
    logger.info("\n处理 equ 文件...")
    try:
        updated = syncer.process_all(extractor)
    finally:
        if icon_matcher:
            icon_matcher.close()
    
    # 打印统计
    logger.info(f"\n处理完成:")
    logger.info(f"  处理文件: {syncer.stats.get('processed')}")
    logger.info(f"  标准路径: {syncer.stats.get('standard_path')}")
    if not args.strict_only:
        logger.info(f"  图标匹配: {syncer.stats.get('icon_matched')}")
        logger.info(f"  匹配失败: {syncer.stats.get('icon_match_failed')}")
    logger.info(f"  跳过[expand ani]: {syncer.stats.get('skipped_expand_ani')}")
    logger.info(f"  更新 items: {updated}")
    
    # 保存
    if not args.dry_run and updated > 0:
        save_json(args.config, config)
    elif args.dry_run:
        logger.info("[试运行] 未保存修改")
    else:
        logger.info("无更新")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
