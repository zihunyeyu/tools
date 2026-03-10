#!/usr/bin/env python3
"""
配置文件格式迁移脚本
将旧的 avatar_config.json 格式（包含 icon_type 字段）转换为新格式（移除 icon_type）
"""

import json
import shutil
from pathlib import Path
from datetime import datetime


def migrate_config_file(config_path: str):
    """迁移配置文件到新格式"""
    config_path = Path(config_path)
    
    if not config_path.exists():
        print(f"[ERROR] 配置文件不存在: {config_path}")
        return False
    
    # 创建备份
    backup_name = f"avatar_config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    backup_path = config_path.parent / backup_name
    shutil.copy2(config_path, backup_path)
    print(f"[INFO] 已创建备份: {backup_path}")
    
    # 读取配置
    print(f"[INFO] 正在读取配置文件...")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 部位顺序（用于遍历）
    part_order = [
        "cap", "hair", "face", "neck", "coat", 
        "pants", "belt", "shoes", "skin", "weapon"
    ]
    
    migrated_count = 0
    removed_icon_type_count = 0
    
    # 遍历每个职业的配置
    for job_key, job_config in config.items():
        if not isinstance(job_config, dict):
            continue
        
        print(f"[INFO] 正在处理职业: {job_key}")
        
        # 处理 items
        items = job_config.get("items", {})
        for part in part_order:
            part_items = items.get(part, {})
            if not isinstance(part_items, dict):
                continue
            
            for code, item in list(part_items.items()):
                if not isinstance(item, dict):
                    continue
                
                # 1. 移除 icon_type 字段
                if "icon_type" in item:
                    del item["icon_type"]
                    removed_icon_type_count += 1
                
                # 2. 确保 hide_parts 存在且为列表
                if "hide_parts" not in item or item.get("hide_parts") is None:
                    item["hide_parts"] = []
                    migrated_count += 1
                
                # 3. 确保 frame 字段存在
                if "frame" not in item:
                    # 如果没有 frame，尝试从 icon_frame 迁移
                    if "icon_frame" in item:
                        item["frame"] = item.pop("icon_frame")
                        migrated_count += 1
                    else:
                        # 默认设置为 -1（无图标）
                        item["frame"] = -1
                        migrated_count += 1
                
                # 4. 处理 custom_icons 合并到 items 的情况
                # 如果 item 有 img 字段但没有 frame，设置默认 frame
                if "img" in item and item.get("frame", -1) == -1:
                    # 有 img 但 frame 为 -1，可能是迁移残留，设置为 0
                    item["frame"] = 0
                    migrated_count += 1
        
        # 5. 移除旧的 custom_icons 字段（如果存在）
        if "custom_icons" in job_config:
            # 将 custom_icons 合并到 items 中
            custom_icons = job_config.pop("custom_icons")
            for part, icons in custom_icons.items():
                if part not in items:
                    items[part] = {}
                for code, icon_config in icons.items():
                    if isinstance(icon_config, dict):
                        frame = icon_config.get("frame", 0)
                        img = icon_config.get("img")
                        if frame >= 0 and img:
                            # 获取现有配置或创建新的
                            existing = items.get(part, {}).get(code, {})
                            if isinstance(existing, dict):
                                name = existing.get("name", f"时装{code}")
                                hide_parts = existing.get("hide_parts") or []
                            else:
                                name = str(existing) if existing else f"时装{code}"
                                hide_parts = []
                            
                            items[part][code] = {
                                "name": name,
                                "frame": frame,
                                "img": img,
                                "hide_parts": hide_parts if isinstance(hide_parts, list) else []
                            }
                            migrated_count += 1
            print(f"[INFO] 已合并 custom_icons 到 items: {job_key}")
        
        # 6. 更新元数据
        if "metadata" not in job_config:
            job_config["metadata"] = {}
        job_config["metadata"]["_migrated"] = True
        job_config["metadata"]["_version"] = "2.0"
        job_config["metadata"]["_migrated_at"] = datetime.now().isoformat()
    
    # 保存新配置
    print(f"[INFO] 正在保存新格式配置...")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"[INFO] 迁移完成!")
    print(f"  - 移除 icon_type 字段: {removed_icon_type_count} 项")
    print(f"  - 其他迁移操作: {migrated_count} 项")
    print(f"  - 备份文件: {backup_path}")
    
    return True


if __name__ == "__main__":
    config_file = Path(__file__).parent / "avatar_config.json"
    migrate_config_file(config_file)
