"""DNF Dressing Room - DNF试衣间 (Optimized)

功能：根据选择的职业、性别和部位装备，拼合成完整人物并展示动作。

Usage:
    python dressing_room_optimized.py
"""

import copy
import json
import os
import random
import re
import threading
import time
import tkinter as tk
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Generic, List, Optional, Tuple, TypeVar

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk

from pydoftools.npk import NPK
from pydoftools.npk.img.image import ImageLink


# =============================================================================
# 全局配置常量
# =============================================================================


class AppConfig:
    """应用配置常量 - 集中管理所有配置参数"""

    # 缓存大小配置
    class Cache:
        ICON_MEMORY = 500  # IconLoader 内存缓存
        ICON_PHOTO = 300  # IconLoader PhotoImage缓存
        F_LAYER = 200  # f层处理结果缓存
        G_LAYER = 200  # g层处理结果缓存
        H_LAYER = 200  # h层处理结果缓存
        FRAME = 300  # 全帧预缓存
        PHOTO = 300  # 预览PhotoImage缓存
        THUMBNAIL = 800  # 缩略图PIL缓存
        THUMBNAIL_PHOTO = 1000  # 缩略图PhotoImage缓存
        ICON_STATUS = 2000  # 图标状态缓存
        CLEANUP_RATIO = 0.1  # 缓存清理比例

    # 图像处理配置
    class Image:
        BLACK_THRESHOLD = 20  # 去黑底阈值
        F_LAYER_THRESHOLD = 30  # f层混合阈值
        G_LAYER_ALPHA = 0.25  # g层默认透明度
        H_LAYER_ALPHA = 0.25  # h层默认透明度
        CANVAS_WIDTH = 600
        CANVAS_HEIGHT = 700
        PREVIEW_WIDTH = 500
        PREVIEW_HEIGHT = 600

    # UI配置
    class UI:
        ITEMS_PER_PAGE = 64  # 默认8x8布局
        MAX_PRECACHE_FRAMES = 120  # 最多预缓存帧数
        THEME_DEFAULT = "light"

    # 文件路径
    class Path:
        CACHE_FILE = "dressing_room_cache.json"
        ICON_CACHE_DIR = "icon_cache"
        NPK_DEFAULT = r"D:\DOF\AVATAR\com"


# =============================================================================
# 新增：统一的 LRU 缓存管理器
# =============================================================================

T = TypeVar("T")


class LRUCache(Generic[T]):
    """线程安全的 LRU 缓存管理器

    特性:
    - 线程安全（使用 RLock）
    - 自动清理（当达到容量上限时清理最旧的条目）
    - 统计信息（命中率等）
    """

    def __init__(self, max_size: int, cleanup_ratio: float = 0.2, name: str = "Cache"):
        self.max_size = max_size
        self.cleanup_ratio = cleanup_ratio
        self.name = name
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key) -> Optional[T]:
        """获取缓存值，如果不存在返回 None"""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def put(self, key, value: T) -> None:
        """存入缓存"""
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = value
                return

            if len(self._cache) >= self.max_size:
                cleanup_count = max(1, int(self.max_size * self.cleanup_ratio))
                for _ in range(cleanup_count):
                    if self._cache:
                        self._cache.popitem(last=False)

            self._cache[key] = value

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    def __contains__(self, key) -> bool:
        """检查键是否在缓存中"""
        with self._lock:
            return key in self._cache

    def __len__(self) -> int:
        """返回缓存大小"""
        with self._lock:
            return len(self._cache)

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0
            return {
                "name": self.name,
                "size": len(self._cache),
                "max_size": self.max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.2%}",
            }

    def keys(self):
        """返回缓存中的所有键（用于批量清理）"""
        with self._lock:
            return list(self._cache.keys())

    def __delitem__(self, key):
        """支持 del cache[key] 语法"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def __setitem__(self, key, value):
        """支持 cache[key] = value 语法"""
        self.put(key, value)

    def __getitem__(self, key):
        """支持 cache[key] 语法"""
        result = self.get(key)
        if result is None:
            raise KeyError(key)
        return result


# =============================================================================
# 新增：批量元数据更新管理器
# =============================================================================


class BatchMetaUpdater:
    """批量元数据更新管理器 - 减少 IO 开销"""

    def __init__(self, save_callback, delay: float = 5.0):
        self.save_callback = save_callback
        self.delay = delay
        self._pending_updates = set()
        self._dirty = False
        self._timer = None
        self._lock = threading.Lock()

    def add_update(self, key: str):
        """添加待更新的键"""
        with self._lock:
            self._pending_updates.add(key)
            self._dirty = True

            if self._timer:
                self._timer.cancel()

            self._timer = threading.Timer(self.delay, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self):
        """执行批量保存"""
        with self._lock:
            if not self._dirty or not self._pending_updates:
                return
            updates = self._pending_updates.copy()
            self._pending_updates.clear()
            self._dirty = False

        try:
            self.save_callback(updates)
        except Exception as e:
            print(f"[BatchMetaUpdater] 保存失败: {e}")

    def flush_sync(self):
        """同步立即保存"""
        self._flush()


# =============================================================================
# 新增：统一的缓存管理器（管理多种类型的缓存）
# =============================================================================


class CacheManager:
    """统一缓存管理器 - 管理应用中的多种缓存

    整合原有的分散缓存:
    - f_layer_cache: f层处理结果缓存
    - frame_cache: 全帧预缓存
    - photo_cache: PhotoImage缓存
    - thumbnail_cache: 缩略图PIL缓存
    - thumbnail_photo_cache: 缩略图PhotoImage缓存
    - icon_status_cache: 图标状态缓存
    """

    def __init__(self):
        self._caches: Dict[str, LRUCache] = {}
        self._init_caches()

    def _init_caches(self):
        """初始化所有缓存"""
        self._caches["f_layer"] = LRUCache[Image.Image](
            max_size=AppConfig.Cache.F_LAYER,
            cleanup_ratio=AppConfig.Cache.CLEANUP_RATIO,
            name="F_Layer_Cache",
        )
        self._caches["g_layer"] = LRUCache[Image.Image](
            max_size=AppConfig.Cache.G_LAYER,
            cleanup_ratio=AppConfig.Cache.CLEANUP_RATIO,
            name="G_Layer_Cache",
        )
        self._caches["h_layer"] = LRUCache[Image.Image](
            max_size=AppConfig.Cache.H_LAYER,
            cleanup_ratio=AppConfig.Cache.CLEANUP_RATIO,
            name="H_Layer_Cache",
        )
        self._caches["frame"] = LRUCache[Image.Image](
            max_size=AppConfig.Cache.FRAME,
            cleanup_ratio=AppConfig.Cache.CLEANUP_RATIO,
            name="Frame_Cache",
        )
        self._caches["photo"] = LRUCache[ImageTk.PhotoImage](
            max_size=AppConfig.Cache.PHOTO,
            cleanup_ratio=AppConfig.Cache.CLEANUP_RATIO,
            name="Photo_Cache",
        )
        self._caches["thumbnail"] = LRUCache[Image.Image](
            max_size=AppConfig.Cache.THUMBNAIL,
            cleanup_ratio=AppConfig.Cache.CLEANUP_RATIO,
            name="Thumbnail_Cache",
        )
        self._caches["thumbnail_photo"] = LRUCache[ImageTk.PhotoImage](
            max_size=AppConfig.Cache.THUMBNAIL_PHOTO,
            cleanup_ratio=AppConfig.Cache.CLEANUP_RATIO,
            name="Thumbnail_Photo_Cache",
        )
        self._caches["icon_status"] = LRUCache[str](
            max_size=AppConfig.Cache.ICON_STATUS,
            cleanup_ratio=AppConfig.Cache.CLEANUP_RATIO,
            name="Icon_Status_Cache",
        )

    def get(self, cache_name: str, key):
        """获取指定缓存的值"""
        cache = self._caches.get(cache_name)
        return cache.get(key) if cache else None

    def put(self, cache_name: str, key, value) -> None:
        """存入指定缓存"""
        cache = self._caches.get(cache_name)
        if cache:
            cache.put(key, value)

    def clear(self, cache_name: str = None) -> None:
        """清空指定缓存，或清空所有缓存"""
        if cache_name:
            cache = self._caches.get(cache_name)
            if cache:
                cache.clear()
        else:
            for cache in self._caches.values():
                cache.clear()

    def clear_all(self) -> None:
        """清空所有缓存"""
        self.clear()

    def get_stats(self) -> dict:
        """获取所有缓存的统计信息"""
        return {name: cache.get_stats() for name, cache in self._caches.items()}

    def __getitem__(self, cache_name: str) -> Optional[LRUCache]:
        """通过索引访问缓存"""
        return self._caches.get(cache_name)

    # 便捷属性访问
    @property
    def f_layer(self) -> LRUCache:
        return self._caches["f_layer"]

    @property
    def frame(self) -> LRUCache:
        return self._caches["frame"]

    @property
    def photo(self) -> LRUCache:
        return self._caches["photo"]

    @property
    def thumbnail(self) -> LRUCache:
        return self._caches["thumbnail"]

    @property
    def thumbnail_photo(self) -> LRUCache:
        return self._caches["thumbnail_photo"]

    @property
    def icon_status(self) -> LRUCache:
        return self._caches["icon_status"]

    @property
    def g_layer(self) -> LRUCache:
        return self._caches["g_layer"]

    @property
    def h_layer(self) -> LRUCache:
        return self._caches["h_layer"]


# =============================================================================
# 新增：使用 lru_cache 优化的工具函数
# =============================================================================


@lru_cache(maxsize=256)
def _is_f_layer_cached(layer_name: str) -> bool:
    """判断图层名是否为f层（发光层）- 带缓存

    匹配LAYER_DICT中所有f层模式:
    - {part}_f     : coat_f, neck_f, face_f, cap_f, pants_f, shoes_f, belt_f
    - {part}_cf    : neck_cf
    - {part}_xf    : neck_xf
    - {part}_bf    : neck_bf
    - {part}_df    : neck_df
    - {part}_kf    : neck_kf
    - {part}_ef    : neck_ef, belt_ef
    - {part}_f1    : hair_f1
    - weapon_{x}1  : weapon_c1, weapon_a1, weapon_e1, weapon_x1, weapon_b1, weapon_d1

    注意: layer_name 是完整图层名，如 weapon_c1, coat_f 等
    """

    if not layer_name:
        return False
    # 排除g层和h层
    if layer_name.endswith("_g") or layer_name.endswith("_h"):
        return False
    # 标准f层判断: 以"f"结尾或包含"_f"
    if layer_name.endswith("f") or "_f" in layer_name:
        return True
    # 武器特殊f层: weapon_c1, weapon_a1, weapon_e1, weapon_x1, weapon_b1, weapon_d1
    if re.match(r"weapon_[caexbd]1$", layer_name):
        return True
    return False


@lru_cache(maxsize=256)
def _get_layer_priority_cached(layer_name: str) -> int:
    """获取图层优先级 - 带缓存"""
    return LAYER_DICT.get(layer_name, 3000)


@lru_cache(maxsize=256)
def _is_g_layer_cached(layer_name: str) -> bool:
    """判断图层名是否为g层（半透明阴影层）- 带缓存

    匹配所有g层:
    - "g" (简写形式)
    - face_g, neck_g, cap_g, belt_g, coat_g, pants_g, shoes_g (完整形式)
    """
    if not layer_name:
        return False
    return layer_name == "g" or layer_name.endswith("_g")


@lru_cache(maxsize=256)
def _is_h_layer_cached(layer_name: str) -> bool:
    """判断图层名是否为h层（深层阴影层）- 带缓存

    匹配所有h层:
    - "h" (简写形式)
    - shoes_h, pants_h, coat_h, belt_h, cap_h, neck_h, face_h (完整形式)
    """
    if not layer_name:
        return False
    return layer_name == "h" or layer_name.endswith("_h")


# 图层层级配置（原config.py中的配置内嵌）
LAYER_DICT = {
    "coat_f": 2850,
    "neck_f": 2840,
    "face_f": 2830,
    "cap_f": 2810,
    "belt_e": 2800,
    "neck_e": 2780,
    "neck_ef": 2751,
    "face_g": 2750,
    "face_a": 2700,
    "weapon_c2": 2792,
    "weapon_c1": 2791,
    "weapon_c": 2790,
    "cap_c": 2500,
    "hair_c": 2400,
    "coat_c": 2300,
    "neck_g": 2251,
    "neck_cf": 2201,
    "neck_c": 2200,
    "weapon_a2": 2152,
    "weapon_a1": 2151,
    "weapon_a": 2150,
    "cap_g": 2125,
    "cap_a": 2100,
    "hair_a": 2000,
    "weapon_e2": 1992,
    "weapon_e1": 1991,
    "weapon_e": 1990,
    "neck_xf": 1980,
    "neck_x": 1975,
    "neck_z": 1963,
    "coat_x": 1960,
    "belt_f": 1952,
    "belt_g": 1951,
    "belt_c": 1950,
    "belt_c1": 1949,
    "face_c": 1925,
    "neck_a": 1900,
    "coat_g": 1850,
    "coat_a": 1800,
    "belt_a": 1700,
    "pants_f": 1651,
    "pants_c": 1650,
    "shoes_f": 1601,
    "shoes_c": 1600,
    "pants_g": 1501,
    "pants_a": 1500,
    "shoes_g": 1450,
    "shoes_a": 1400,
    "weapon_x2": 1352,
    "weapon_x1": 1351,
    "weapon_x": 1350,
    "pants_b": 1300,
    "shoes_h": 1201,
    "shoes_b": 1200,
    "shoes_d": 1190,
    "pants_h": 1151,
    "pants_d": 1150,
    "belt_b": 1100,
    "neck_bf": 1050,
    "neck_b": 1000,
    "coat_h": 925,
    "coat_b": 900,
    "belt_h": 851,
    "belt_d": 850,
    "belt_d1": 849,
    "hair_b": 800,
    "cap_h": 750,
    "cap_b": 700,
    "weapon_b2": 652,
    "weapon_b1": 651,
    "weapon_b": 650,
    "neck_df": 620,
    "neck_d": 600,
    "neck_h": 550,
    "coat_d": 500,
    "hair_d": 400,
    "cap_d": 300,
    "neck_kf": 291,
    "neck_k": 290,
    "face_h": 270,
    "weapon_d2": 202,
    "weapon_d1": 201,
    "weapon_d": 200,
    "face_b": 100,
    "hair_f1": 20,
}


def is_f_layer(layer_name: str) -> bool:
    """判断图层名是否为f层（发光层）- 使用缓存优化"""
    return _is_f_layer_cached(layer_name)


def is_g_layer(layer_name: str) -> bool:
    """判断图层名是否为g层（半透明阴影层）- 使用缓存优化"""
    return _is_g_layer_cached(layer_name)


def is_h_layer(layer_name: str) -> bool:
    """判断图层名是否为h层（深层阴影层）- 使用缓存优化"""
    return _is_h_layer_cached(layer_name)


def get_layer_priority(layer_name: str) -> int:
    """获取图层优先级 - 使用缓存优化"""
    return _get_layer_priority_cached(layer_name)


# =============================================================================
# 常量配置
# =============================================================================

# 职业配置
JOB_CONFIG = {
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

PARTS = [
    "cap",
    "hair",
    "face",
    "neck",
    "coat",
    "pants",
    "belt",
    "shoes",
    "skin",
    "weapon",
]

# 图层绘制顺序（从下到上）
LAYER_ORDER = [
    "skin",
    "pants",
    "coat",
    "belt",
    "neck",
    "shoes",
    "hair",
    "face",
    "cap",
    "weapon",
]

# 时装预览帧号配置（各职业生成缩略图时使用的帧号，默认为0）
# 格式: {job_key: frame_index}
THUMBNAIL_FRAME_CONFIG = {
    "thief_female": 12,  # 暗夜使者使用第12帧
    # 其他职业可以在这里添加，如:
    "swordman_male": 90,
    "fighter_female": 5,
    "fighter_male": 12,
    "gunner_male": 18,
    "gunner_female": 23,
    "mage_female": 10,
    "mage_male": 10,
    "priest_male": 120,
}


def get_thumbnail_frame(job_key: str) -> int:
    """获取指定职业生成缩略图时使用的帧号"""
    return THUMBNAIL_FRAME_CONFIG.get(job_key, 0)


# UI 常量
PART_NAMES = {
    "cap": "帽子",
    "hair": "头发",
    "face": "脸部",
    "neck": "胸部",
    "coat": "上衣",
    "belt": "腰带",
    "pants": "裤子",
    "shoes": "鞋子",
    "skin": "皮肤",
    "weapon": "武器",
}

# 中文部位名映射（用于装扮表）
CN_PART_NAMES = {
    "cap": "头饰",
    "hair": "头发",
    "face": "脸部",
    "neck": "胸部",
    "coat": "上衣",
    "belt": "腰带",
    "pants": "裤子",
    "shoes": "鞋子",
    "skin": "皮肤",
    "weapon": "武器",
}

# 武器类型映射（鬼剑士示例，可根据需要扩展）
WEAPON_TYPES = {
    "swordman_male": {
        "beamswd": "光剑",
        "katana": "太刀",
        "sswd": "短剑",
        "club": "钝器",
        "lswd": "巨剑",
        "boneswd": "骨剑",
        "gemswd": "宝石剑",
        "lgswd": "长巨剑",
        "lkatana": "长太刀",
        "mswd": "魔法剑",
    },
    "swordman_female": {
        "beamswd": "光剑",
        "katana": "太刀",
        "sswd": "短剑",
        "club": "钝器",
        "lswd": "巨剑",
        "boneswd": "骨剑",
        "gemswd": "宝石剑",
        "lgswd": "长巨剑",
        "lkatana": "长太刀",
        "mswd": "魔法剑",
    },
    "fighter_female": {
        "knuckle": "手套",
        "gauntlet": "臂铠",
        "claw": "爪",
        "boxglove": "拳套",
        "arm": "臂铠(arm)",
        "boneclaw": "骨爪",
        "glove": "布手套",
        "tonfa": "东方棍",
    },
    "fighter_male": {
        "knuckle": "手套",
        "gauntlet": "臂铠",
        "claw": "爪",
        "boxglove": "拳套",
        "arm": "臂铠(arm)",
        "boneclaw": "骨爪",
        "glove": "布手套",
        "tonfa": "东方棍",
    },
    "gunner_male": {
        "rev": "左轮",
        "auto": "自动手枪",
        "musket": "步枪",
        "hcan": "手炮",
        "bowgun": "弩",
    },
    "gunner_female": {
        "rev": "左轮",
        "auto": "自动手枪",
        "musket": "步枪",
        "hcan": "手炮",
        "bowgun": "弩",
    },
    "mage_female": {
        "staff": "法杖",
        "rod": "魔杖",
        "spear": "矛",
        "pole": "棍棒",
        "broom": "扫把",  # 女法师特有
    },
    "mage_male": {
        "staff": "法杖",
        "rod": "魔杖",
        "spear": "矛",
        "pole": "棍棒",
        # 男法师没有扫把
    },
    "priest_male": {
        "cross": "十字架",
        "rosary": "念珠",
        "totem": "图腾",
        "scythe": "镰刀",
        "axe": "战斧",
    },
    "priest_female": {
        # 女圣职者与男圣职者共用同一套武器NPK
        "cross": "十字架",
        "rosary": "念珠",
        "totem": "图腾",
        "scythe": "镰刀",
        "axe": "战斧",
    },
    "thief_female": {
        "dagger": "匕首",
        "twinswd": "双剑",
        "wand": "手杖",
        "chakraweapon": "苦无",
    },
    "thief_male": {
        # 男暗夜使者与女暗夜使者共用同一套武器NPK
        "dagger": "匕首",
        "twinswd": "双剑",
        "wand": "手杖",
        "chakraweapon": "苦无",
    },
}


# =============================================================================
# 主题配置
# =============================================================================


class ThemeManager:
    """主题管理器 - 支持多主题切换"""

    # 预定义主题
    THEMES = {
        "light": {
            "name": "浅色主题",
            # 主窗口背景
            "bg_primary": "#f0f0f0",
            "bg_secondary": "#ffffff",
            "bg_tertiary": "#e0e0e0",
            "bg_canvas": "#404040",
            "bg_canvas_custom": "#f5f5f5",
            # 文本颜色
            "fg_primary": "#333333",
            "fg_secondary": "#666666",
            "fg_tertiary": "#999999",
            "item_code_normal": "#afb7c0",
            # 强调色
            "accent_primary": "#4a90d9",
            "accent_secondary": "#66cc66",
            "accent_warning": "#ff9966",
            "accent_danger": "#ff6b6b",
            "accent_success": "#28a745",
            # 边框颜色
            "border_primary": "#cccccc",
            "border_secondary": "#999999",
            "border_highlight": "#4a90d9",
            # 部件状态色
            "button_bg": "#f0f0f0",
            "button_fg": "#333333",
            "button_active_bg": "#4a90d9",
            "button_active_fg": "#ffffff",
            "entry_bg": "#ffffff",
            "entry_fg": "#333333",
            "listbox_bg": "#ffffff",
            "listbox_fg": "#333333",
            "listbox_select_bg": "#4a90d9",
            "listbox_select_fg": "#ffffff",
            # 网格和图标
            "grid_bg": "#404040",
            "grid_item_border_normal": "#999999",
            "grid_item_border_selected": "#00aa00",
            "grid_item_bg": "#ffffff",
            "grid_item_bg_highlight": "#e6ffe6",
            # 文本标签
            "label_info": "#0066cc",
            "label_success": "#006600",
            "label_warning": "#cc6600",
            "label_error": "#cc0000",
            "label_normal": "#0066cc",
            "label_hidden": "#ff6600",
            "label_missing": "#cc0000",
            "label_empty": "#999999",
            # 标签页
            "tab_selected_bg": "#4a90d9",
            "tab_selected_fg": "#ff8800",
            "tab_active_bg": "#e0e0e0",
            "tab_active_fg": "#000000",
        },
        "dark": {
            "name": "夜间模式",
            # 主窗口背景
            "bg_primary": "#2d2d2d",
            "bg_secondary": "#1e1e1e",
            "bg_tertiary": "#3d3d3d",
            "bg_canvas": "#1a1a1a",
            "bg_canvas_custom": "#252525",
            # 文本颜色
            "fg_primary": "#e0e0e0",
            "fg_secondary": "#b0b0b0",
            "fg_tertiary": "#808080",
            "item_code_normal": "#eefefe",
            # 强调色
            "accent_primary": "#5ba0e9",
            "accent_secondary": "#77dd77",
            "accent_warning": "#ffaa77",
            "accent_danger": "#ff7b7b",
            "accent_success": "#39b85f",
            # 边框颜色
            "border_primary": "#555555",
            "border_secondary": "#777777",
            "border_highlight": "#5ba0e9",
            # 部件状态色
            "button_bg": "#3d3d3d",
            "button_fg": "#e0e0e0",
            "button_active_bg": "#5ba0e9",
            "button_active_fg": "#ffffff",
            "entry_bg": "#2d2d2d",
            "entry_fg": "#e0e0e0",
            "listbox_bg": "#2d2d2d",
            "listbox_fg": "#e0e0e0",
            "listbox_select_bg": "#5ba0e9",
            "listbox_select_fg": "#ffffff",
            # 网格和图标
            "grid_bg": "#1a1a1a",
            "grid_item_border_normal": "#666666",
            "grid_item_border_selected": "#4caf50",
            "grid_item_bg": "#2d2d2d",
            "grid_item_bg_highlight": "#1b3a1b",
            # 文本标签
            "label_info": "#6bb3ff",
            "label_success": "#77dd77",
            "label_warning": "#ffaa77",
            "label_error": "#ff6b6b",
            "label_normal": "#6bb3ff",
            "label_hidden": "#ffaa77",
            "label_missing": "#ff6b6b",
            "label_empty": "#808080",
            # 标签页
            "tab_selected_bg": "#5ba0e9",
            "tab_selected_fg": "#ffaa44",
            "tab_active_bg": "#4a4a4a",
            "tab_active_fg": "#e0e0e0",
        },
        "blue": {
            "name": "海洋蓝",
            # 主窗口背景
            "bg_primary": "#e8f4fc",
            "bg_secondary": "#f0f8ff",
            "bg_tertiary": "#d0e8f5",
            "bg_canvas": "#1a3a52",
            "bg_canvas_custom": "#e0f0f8",
            # 文本颜色
            "fg_primary": "#1a3a52",
            "fg_secondary": "#4a6a82",
            "fg_tertiary": "#7a9ab2",
            "item_code_normal": "#afb7c0",
            # 强调色
            "accent_primary": "#2196f3",
            "accent_secondary": "#03a9f4",
            "accent_warning": "#ff9800",
            "accent_danger": "#f44336",
            "accent_success": "#4caf50",
            # 边框颜色
            "border_primary": "#b0d4e8",
            "border_secondary": "#90c4d8",
            "border_highlight": "#2196f3",
            # 部件状态色
            "button_bg": "#d0e8f5",
            "button_fg": "#1a3a52",
            "button_active_bg": "#2196f3",
            "button_active_fg": "#ffffff",
            "entry_bg": "#ffffff",
            "entry_fg": "#1a3a52",
            "listbox_bg": "#f0f8ff",
            "listbox_fg": "#1a3a52",
            "listbox_select_bg": "#2196f3",
            "listbox_select_fg": "#ffffff",
            # 网格和图标
            "grid_bg": "#1a3a52",
            "grid_item_border_normal": "#90c4d8",
            "grid_item_border_selected": "#4caf50",
            "grid_item_bg": "#f0f8ff",
            "grid_item_bg_highlight": "#e0f7e0",
            # 文本标签
            "label_info": "#1976d2",
            "label_success": "#388e3c",
            "label_warning": "#f57c00",
            "label_error": "#d32f2f",
            "label_normal": "#1976d2",
            "label_hidden": "#f57c00",
            "label_missing": "#d32f2f",
            "label_empty": "#7a9ab2",
            # 标签页
            "tab_selected_bg": "#2196f3",
            "tab_selected_fg": "#ff6f00",
            "tab_active_bg": "#b3e5fc",
            "tab_active_fg": "#1a3a52",
        },
        "green": {
            "name": "护眼绿",
            # 主窗口背景
            "bg_primary": "#f0f5e8",
            "bg_secondary": "#f5faf0",
            "bg_tertiary": "#e0e8d5",
            "bg_canvas": "#2d3a25",
            "bg_canvas_custom": "#e8f0e0",
            # 文本颜色
            "fg_primary": "#2d3a25",
            "fg_secondary": "#5a6a4a",
            "fg_tertiary": "#8a9a7a",
            "item_code_normal": "#afb7c0",
            # 强调色
            "accent_primary": "#4caf50",
            "accent_secondary": "#8bc34a",
            "accent_warning": "#ff9800",
            "accent_danger": "#e91e63",
            "accent_success": "#2e7d32",
            # 边框颜色
            "border_primary": "#c5d5b0",
            "border_secondary": "#a5c090",
            "border_highlight": "#4caf50",
            # 部件状态色
            "button_bg": "#d5e0c8",
            "button_fg": "#2d3a25",
            "button_active_bg": "#4caf50",
            "button_active_fg": "#ffffff",
            "entry_bg": "#ffffff",
            "entry_fg": "#2d3a25",
            "listbox_bg": "#f5faf0",
            "listbox_fg": "#2d3a25",
            "listbox_select_bg": "#4caf50",
            "listbox_select_fg": "#ffffff",
            # 网格和图标
            "grid_bg": "#2d3a25",
            "grid_item_border_normal": "#a5c090",
            "grid_item_border_selected": "#2e7d32",
            "grid_item_bg": "#f5faf0",
            "grid_item_bg_highlight": "#e0f5d0",
            # 文本标签
            "label_info": "#388e3c",
            "label_success": "#2e7d32",
            "label_warning": "#f57c00",
            "label_error": "#c62828",
            "label_normal": "#388e3c",
            "label_hidden": "#ff8f00",
            "label_missing": "#c62828",
            "label_empty": "#8a9a7a",
            # 标签页
            "tab_selected_bg": "#4caf50",
            "tab_selected_fg": "#ff8f00",
            "tab_active_bg": "#c8e6c9",
            "tab_active_fg": "#2d3a25",
        },
    }

    def __init__(self, theme_name: str = "light"):
        self.current_theme_name = theme_name
        self.colors = self.THEMES.get(theme_name, self.THEMES["light"])

    def get(self, key: str, default: str = None) -> str:
        """获取颜色值"""
        return self.colors.get(key, default or self.colors.get("fg_primary", "#333333"))

    def get_color(self, key: str, default: str = None) -> str:
        """获取颜色值（同get）"""
        return self.get(key, default)

    def set_theme(self, theme_name: str) -> bool:
        """切换主题"""
        if theme_name in self.THEMES:
            self.current_theme_name = theme_name
            self.colors = self.THEMES[theme_name]
            return True
        return False

    def get_theme_names(self) -> List[Tuple[str, str]]:
        """获取所有主题名称列表 [(key, name), ...]"""
        return [(key, theme["name"]) for key, theme in self.THEMES.items()]

    def current_theme(self) -> str:
        """获取当前主题名称"""
        return self.current_theme_name


# =============================================================================
# 工具函数
# =============================================================================


def log_error(msg: str, e: Exception = None):
    """简化的错误日志输出"""
    if e:
        print(f"[ERROR] {msg}: {e}")
    else:
        print(f"[ERROR] {msg}")


def read_text_file(
    file_path: Path, encodings: Tuple[str, ...] = ("utf-8", "gbk", "gb18030")
) -> List[str]:
    """读取文本文件，自动尝试多种编码"""
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"Cannot decode file: {file_path}")


def write_text_file(
    file_path: Path, lines: List[str], encodings: Tuple[str, ...] = ("utf-8", "gbk")
) -> bool:
    """写入文本文件，失败时尝试备用编码"""
    for encoding in encodings:
        try:
            with open(file_path, "w", encoding=encoding) as f:
                f.writelines(lines)
            return True
        except Exception as e:
            print(f"Error writing with {encoding}: {e}")
            continue
    return False


def resolve_image_link(img, sprite, max_depth: int = 10) -> Optional[object]:
    """解析 ImageLink，返回最终 sprite 对象"""
    visited = set()
    depth = 0
    while isinstance(sprite, ImageLink) and depth < max_depth:
        idx = sprite.index
        if idx in visited or idx >= len(img.images):
            return None
        visited.add(idx)
        sprite = img.image_by_index(idx)
        depth += 1
    return None if isinstance(sprite, ImageLink) else sprite


def convert_sprite_to_image(
    img, sprite, palette_index: int = 0
) -> Optional[Image.Image]:
    """将 sprite 转换为 PIL Image

    支持 IMGv4、IMGv5 和 IMGv6 格式：
    - IMGv4: 直接访问 sprite.data，使用 color_board
    - IMGv5: 使用 img.build(sprite) 解压 Zlib 压缩数据
    - IMGv6: 支持多个调色板 (color_boards)，根据 palette_index 选择
    """
    # 对于 IMGv6 多调色板且需要非默认调色板的情况
    # 跳过 img.build() 快捷方式，强制使用手动调色板处理
    has_multiple_palettes = (
        hasattr(img, "color_boards") and img.color_boards and len(img.color_boards) > 1
    )

    if not has_multiple_palettes or palette_index == 0:
        # 只有当没有多调色板或使用默认调色板时，才尝试 img.build()
        try:
            pil_img = img.build(sprite)
            if pil_img is not None:
                return pil_img
        except Exception:
            pass

    # 回退到直接数据处理（适用于 IMGv4 或 IMGv6 多调色板非默认情况）
    try:
        data = sprite.data
        if not data:
            return None
    except Exception:
        return None

    from pydoftools.npk.img.image.format.convertor import FormatConvertor
    from pydoftools.utils.image import load_raw

    expected_size = sprite.w * sprite.h

    if len(data) == expected_size:
        # 调色板模式
        colors = None
        if hasattr(img, "color_board") and img.color_board:
            colors = img.color_board.colors
        elif hasattr(img, "color_boards") and img.color_boards:
            colors = (
                img.color_boards[palette_index].colors
                if palette_index < len(img.color_boards)
                else img.color_boards[0].colors
            )

        if colors:
            raw = FormatConvertor.to_raw_indexes(data, colors)
            return load_raw(raw, sprite.w, sprite.h)
        return None
    else:
        # 直接颜色格式
        raw = FormatConvertor.to_raw(data, sprite.format)
        return load_raw(raw, sprite.w, sprite.h)


def remove_black_background(img: Image.Image, threshold: int = 20) -> Image.Image:
    """
    去除图像的黑色背景
    将接近黑色的像素设为透明

    Args:
        img: 输入图像
        threshold: 颜色阈值，低于此值视为黑色

    Returns:
        去黑底后的图像
    """
    img = img.convert("RGBA")

    # 使用 NumPy 进行像素操作（避免 getdata() 弃用警告）
    arr = np.array(img)

    # 创建黑色像素掩码：R、G、B 都小于阈值的像素
    black_mask = (
        (arr[:, :, 0] < threshold)
        & (arr[:, :, 1] < threshold)
        & (arr[:, :, 2] < threshold)
    )

    # 将黑色像素设为透明
    arr[black_mask] = [0, 0, 0, 0]

    return Image.fromarray(arr)


def linear_dodge_blend(base: Image.Image, blend: Image.Image) -> Image.Image:
    """
    线性减淡（Linear Dodge/Add）混合模式 - NumPy优化版
    公式: Result = min(Base + Blend, 255)
    等同于Photoshop的Linear Dodge（Add）

    Args:
        base: 基础图像
        blend: 混合图像

    Returns:
        混合后的图像
    """
    # 确保尺寸一致
    if base.size != blend.size:
        new_size = (max(base.width, blend.width), max(base.height, blend.height))
        base_canvas = Image.new("RGBA", new_size, (0, 0, 0, 0))
        blend_canvas = Image.new("RGBA", new_size, (0, 0, 0, 0))
        base_canvas.paste(base, (0, 0), base)
        blend_canvas.paste(blend, (0, 0), blend)
        base, blend = base_canvas, blend_canvas

    # 使用 NumPy 实现线性减淡（比 ImageChops.add 更快）
    base_arr = np.array(base.convert("RGBA"), dtype=np.uint16)
    blend_arr = np.array(blend.convert("RGBA"), dtype=np.uint16)

    # 线性减淡: Result = min(Base + Blend, 255)
    result_arr = np.minimum(base_arr + blend_arr, 255).astype(np.uint8)

    return Image.fromarray(result_arr)


def apply_f_layer_process(img: Image.Image, black_threshold: int = 30) -> Image.Image:
    """
    f层单独处理：去黑底

    只去除黑色背景，保持原RGB值不变。
    用于f层单独处理后再叠加到画布上。

    Args:
        img: 输入图像
        black_threshold: 黑色阈值，低于此值的像素视为黑色

    Returns:
        处理后的图像（去黑底，但RGB值不变）
    """
    bg_color = (0, 0, 0)
    gamma = 2.2
    img = img.convert("RGBA")
    data = np.array(img, dtype=np.float32) / 255.0  # 归一化到 0~1

    # 分离通道
    r, g, b, a = data[..., 0], data[..., 1], data[..., 2], data[..., 3]

    # Gamma 校正计算亮度
    r_gamma = np.power(r, gamma)
    g_gamma = np.power(g, gamma)
    b_gamma = np.power(b, gamma)

    # 取最大通道值作为亮度
    brightness_gamma = np.maximum.reduce([r_gamma, g_gamma, b_gamma])

    # 反 Gamma 得到感知亮度
    brightness = np.power(brightness_gamma, 1.0 / gamma)

    # 更新 Alpha 通道（去黑底）
    data[..., 3] = brightness

    # 创建背景图层（归一化）
    bg = np.zeros_like(data)
    bg[..., 0:3] = np.array(bg_color) / 255.0
    bg[..., 3] = 1.0

    # 线性减淡合成（RGB 部分）
    result_rgb = np.minimum(1.0, data[..., 0:3] + bg[..., 0:3])

    # 保留去黑底后的 Alpha
    result_alpha = np.clip(brightness, 0.0, 1.0)

    # 合并结果
    result = np.dstack((result_rgb, result_alpha))

    # 转回 0~255 并保存
    result_img = (result * 255).astype(np.uint8)
    return Image.fromarray(result_img)


def blend_f_layer(
    base: Image.Image, blend: Image.Image, black_threshold: int = 30
) -> Image.Image:
    """
    f层混合：去黑底 + 线性减淡（旧版，保留用于兼容）

    处理流程（基于分析结果）：
    1. 转为 ARGB8888 (RGBA) 格式
    2. 去黑底：亮度 < black_threshold 的像素 Alpha 设为 0
    3. 线性减淡：Result = Base + Blend
       非黑像素保持原 RGB 值（因为底色为黑时，线性减淡 = 原色）

    Args:
        base: 基础图像
        blend: f层图像（待去黑底并混合）
        black_threshold: 黑色阈值，低于此值的像素视为黑色，默认 30

    Returns:
        混合后的图像
    """
    # 确保尺寸一致
    if base.size != blend.size:
        new_size = (max(base.width, blend.width), max(base.height, blend.height))
        base_canvas = Image.new("RGBA", new_size, (0, 0, 0, 0))
        blend_canvas = Image.new("RGBA", new_size, (0, 0, 0, 0))
        base_canvas.paste(base, (0, 0), base)
        blend_canvas.paste(blend, (0, 0), blend)
        base, blend = base_canvas, blend_canvas

    # 第一步：转为 ARGB8888 (RGBA) 格式
    base_rgba = base.convert("RGBA")
    blend_rgba = blend.convert("RGBA")

    # 转为 NumPy 数组
    base_arr = np.array(base_rgba, dtype=np.float32)
    blend_arr = np.array(blend_rgba, dtype=np.float32)

    # 第二步：去黑底处理
    # 使用亮度（RGB 最大值）判断黑色像素
    # 这能更好地处理深蓝色调等深色区域
    brightness = np.max(blend_arr[:, :, :3], axis=2)
    black_mask = brightness < black_threshold

    # 黑色像素设为透明（RGBA = [0,0,0,0]）
    blend_arr[black_mask] = [0, 0, 0, 0]

    # 第三步：线性减淡混合
    # 公式：Result = Base + Blend
    # 将像素值归一化到 0-1 范围进行计算
    base_norm = base_arr / 255.0
    blend_norm = blend_arr / 255.0

    # 线性减淡：Base + Blend
    result_rgb = base_norm[:, :, :3] + blend_norm[:, :, :3]
    result_rgb = np.clip(result_rgb, 0, 1)

    # Alpha 通道取最大值
    result_alpha = np.maximum(base_norm[:, :, 3], blend_norm[:, :, 3])

    # 合并结果并转回 uint8
    result_arr = np.concatenate([result_rgb, result_alpha[:, :, np.newaxis]], axis=2)
    result_arr = (result_arr * 255).astype(np.uint8)

    return Image.fromarray(result_arr)


# 注意: is_f_layer, is_g_layer, is_h_layer 函数已使用 lru_cache 优化，定义在文件顶部


def blend_layer_with_opacity(
    base: Image.Image, blend: Image.Image, opacity_pct: int = 0
) -> Image.Image:
    """
    将图层以指定不透明度混合到基础图像上 - 类似Photoshop的图层不透明度

    范围: -100% ~ 100%
    - 0%: 保持原样（100%不透明度，完全覆盖）
    - -100%: 完全透明（0%不透明度，只显示base）
    - 中间值: 半透明混合

    公式:
    - opacity = (opacity_pct + 100) / 100  # 转换为 0~2
    - Src = Blend * opacity（预乘Alpha）
    - Result = Src + Base * (1 - Src_Alpha)

    Args:
        base: 基础图像（下方已渲染的内容）
        blend: 待混合的图层图像
        opacity_pct: 不透明度调节值 (-100 ~ 100)

    Returns:
        混合后的图像
    """
    # 将 -100~100 转换为 0~1 的opacity值
    # -100% -> 0.0 (完全透明)
    # 0% -> 1.0 (原样)
    opacity = (opacity_pct + 100) / 100.0
    opacity = np.clip(opacity, 0.0, 1.0)

    if opacity >= 0.99:
        # 接近原样，直接覆盖（但保留base的透明区域）
        base_arr = np.array(base, dtype=np.float32)
        blend_arr = np.array(blend, dtype=np.float32)

        # 标准Alpha混合（blend覆盖base）
        base_alpha = base_arr[:, :, 3:4] / 255.0
        blend_alpha = blend_arr[:, :, 3:4] / 255.0

        out_alpha = blend_alpha + base_alpha * (1 - blend_alpha)
        out_alpha_safe = np.where(out_alpha > 0, out_alpha, 1)

        out_rgb = (
            blend_arr[:, :, :3] * blend_alpha
            + base_arr[:, :, :3] * base_alpha * (1 - blend_alpha)
        ) / out_alpha_safe

        result_arr = np.concatenate([out_rgb, out_alpha * 255], axis=2)
        result_arr = np.clip(result_arr, 0, 255).astype(np.uint8)
        return Image.fromarray(result_arr)

    if opacity <= 0.01:
        # 接近完全透明，返回base
        return base

    # 转为NumPy数组
    base_arr = np.array(base, dtype=np.float32)
    blend_arr = np.array(blend, dtype=np.float32)

    # 调整blend图层的不透明度（预乘Alpha）
    blend_arr[:, :, :3] = blend_arr[:, :, :3] * opacity
    blend_arr[:, :, 3] = blend_arr[:, :, 3] * opacity

    # 提取Alpha通道（归一化到0-1）
    base_alpha = base_arr[:, :, 3:4] / 255.0
    blend_alpha = blend_arr[:, :, 3:4] / 255.0

    # 标准Alpha混合
    out_alpha = blend_alpha + base_alpha * (1 - blend_alpha)
    out_alpha_safe = np.where(out_alpha > 0, out_alpha, 1)

    out_rgb = (
        blend_arr[:, :, :3] * blend_alpha
        + base_arr[:, :, :3] * base_alpha * (1 - blend_alpha)
    ) / out_alpha_safe

    result_arr = np.concatenate([out_rgb, out_alpha * 255], axis=2)
    result_arr = np.clip(result_arr, 0, 255).astype(np.uint8)

    return Image.fromarray(result_arr)


def get_layer_priority(part: str, layer: str) -> int:
    """获取图层优先级，值越小越在下层

    注意: layer 现在是完整图层名，如 weapon_b, coat_c, cap_f 等
    对于 skin 部位，layer 可能是简写如 a, b, c
    """
    if not layer or layer == "default":
        # 默认图层使用 {part}_a
        key = f"{part}_a"
    elif layer.startswith(part + "_"):
        # layer 已经是完整名称（如 weapon_b, coat_c）
        key = layer
    else:
        # layer 是简写（如 a, b, c），需要拼接
        key = f"{part}_{layer}"
    return LAYER_DICT.get(key, 0 if part == "skin" else 3000)


# =============================================================================
# 数据加载类
# =============================================================================


class DressingRoomLoader:
    """试衣间数据加载器"""

    def __init__(self, base_path: str = r"D:\DOF\AVATAR\com"):
        self.base_path = Path(base_path)
        self.current_job: Optional[str] = None
        self.loaded_npks: Dict[str, NPK] = {}
        # 各部位可用选项 {part: [(display_code, img_index, version, palette_index, layer_indices), ...]}
        self.part_options: Dict[str, List[Tuple]] = {}
        # 默认皮肤(code 0)的最大帧数，用于限制帧切换范围
        self.max_frame: int = 300

    def get_npk_filename(
        self, job_key: str, part: str, weapon_type: str = "beamswd"
    ) -> str:
        """根据职业key、部位生成NPK文件名"""
        folder = JOB_CONFIG.get(job_key, {}).get("folder", job_key)

        # 武器部位使用不同的命名规则
        # 注意：男女法师等职业有各自独立的武器NPK文件
        # 例如：mage_equipment_weapon_*.npk (女) vs mage_atequipment_weapon_*.npk (男)
        if part == "weapon":
            if "_at" in folder:
                job_clean = folder.replace("_at", "")
                return (
                    f"sprite_character_{job_clean}_atequipment_weapon_{weapon_type}.npk"
                )
            return f"sprite_character_{folder}_equipment_weapon_{weapon_type}.npk"

        # 时装部位使用 avatar 命名规则
        if "_at" in folder:
            job_clean = folder.replace("_at", "")
            return f"sprite_character_{job_clean}_atequipment_avatar_{part}.npk"
        return f"sprite_character_{folder}_equipment_avatar_{part}.npk"

    def load_job(self, job_key: str) -> bool:
        """加载指定职业的所有部位NPK"""
        self.current_job = job_key
        
        weapon_type = list(WEAPON_TYPES[job_key].keys())[0] if job_key in WEAPON_TYPES else "beamswd"
        
        self.current_weapon_type = weapon_type
        self.loaded_npks.clear()
        self.part_options.clear()

        success_count = 0
        for part in PARTS:
            npk_path = self.base_path / self.get_npk_filename(
                job_key, part, weapon_type
            )
            if npk_path.exists():
                try:
                    with open(npk_path, "rb") as f:
                        npk = NPK.open(f)
                        npk.load_all()
                        self.loaded_npks[part] = npk
                        success_count += 1
                except Exception as e:
                    print(f"Error loading {npk_path.name}: {e}")

        if success_count > 0:
            self._process_part_options()
        return success_count > 0

    def _process_part_options(self):
        """处理所有部位的选项"""
        for part, npk in self.loaded_npks.items():
            layer_groups = {}  # {base_code: {full_layer_name: img_index}}
            code_to_layers = {}  # {base_code: [full_layer_names]}

            for i, img_file in enumerate(npk.files):
                try:
                    name = img_file.name.lower()

                    # 过滤掉 (tn) 前缀
                    name = re.sub(r"\(tn\)", "", name)

                    # 匹配文件名: katana0300b.img 或 sprite_xxx_coat0300a.img
                    # 对于时装: _([a-z]+)(\d+)([a-z0-9]+)?\.img$ 匹配 _coat0300a.img
                    # 对于武器: ([a-z]+)(\d+)([a-z0-9]*)\.img$ 匹配 katana0300b.img
                    match = re.search(r"_?([a-z]+)(\d+)([a-z0-9]*)\.img$", name)
                    if not match:
                        continue

                    base_code = int(match.group(2))
                    layer_suffix = match.group(3) if match.group(3) else "a"

                    # 构建完整的图层名，包含部位前缀，避免不同部位的同名图层冲突
                    # 例如: weapon_b, coat_c
                    full_layer = (
                        f"{part}_{layer_suffix}" if part != "skin" else layer_suffix
                    )

                    if base_code not in layer_groups:
                        layer_groups[base_code] = {}
                        code_to_layers[base_code] = []

                    layer_groups[base_code][full_layer] = i
                    if full_layer not in code_to_layers[base_code]:
                        code_to_layers[base_code].append(full_layer)
                except:
                    pass

            # 预处理：识别所有 IMGv6 多调色板文件及其展开的代码范围
            # 这样可以让多调色板展开优先于独立文件
            multi_palette_ranges = {}  # {base_code: palette_count}
            code_to_main_base = {}  # {display_code: main_base_code} 用于追踪哪个代码被哪个多调色板展开
            
            for base_code in sorted(layer_groups.keys()):
                layers = layer_groups[base_code]
                main_layer = (
                    f"{part}_a"
                    if f"{part}_a" in layers
                    else ("default" if "default" in layers else list(layers.keys())[0])
                )
                main_idx = layers[main_layer]

                try:
                    img = npk.files[main_idx].to_img()
                    if img.version == 6 and hasattr(img, "color_boards") and img.color_boards:
                        palette_count = len(img.color_boards)
                        if palette_count > 1:
                            multi_palette_ranges[base_code] = palette_count
                            # 标记这个文件要展开的所有代码
                            for p_idx in range(palette_count):
                                display_code = base_code + p_idx
                                code_to_main_base[display_code] = base_code
                except:
                    pass

            # 处理每个图层组，展开调色板并关联附加图层
            code_to_option = {}
            processed_codes = set()  # 避免重复处理

            for base_code in sorted(layer_groups.keys()):
                if base_code in processed_codes:
                    continue

                # 检查这个代码是否被其他多调色板文件展开占用了
                # 如果是，跳过这个独立文件，让多调色板展开优先
                if base_code in code_to_main_base and base_code not in multi_palette_ranges:
                    # 这个代码是其他多调色板展开的，跳过独立文件
                    continue

                layers = layer_groups[base_code]
                main_layer = (
                    f"{part}_a"
                    if f"{part}_a" in layers
                    else ("default" if "default" in layers else list(layers.keys())[0])
                )
                main_idx = layers[main_layer]

                try:
                    img = npk.files[main_idx].to_img()
                    version = img.version

                    palette_count = 0
                    if version == 6 and hasattr(img, "color_boards"):
                        palette_count = len(img.color_boards)
                    elif version == 4 and hasattr(img, "color_board"):
                        palette_count = 1

                    if palette_count > 1:
                        # IMGv6 多调色板: 展开为多个 code
                        for p_idx in range(palette_count):
                            display_code = base_code + p_idx
                            if display_code in processed_codes:
                                continue
                            processed_codes.add(display_code)

                            # 收集该 display_code 的所有图层
                            # 1. 基础图层（来自 base_code）
                            merged_layers = dict(layers)

                            # 2. 附加图层（来自 display_code 自己的文件，如 3802d1）
                            # 注意：只有当 display_code 不是被当前多调色板展开占用的，
                            # 或者是被其他多调色板占用的，才合并图层
                            if display_code in layer_groups:
                                # 如果这个代码被其他多调色板展开占用了，不合并其图层
                                # 因为那是另一个基础文件
                                if display_code not in code_to_main_base or code_to_main_base[display_code] == base_code:
                                    for layer_name, img_idx in layer_groups[display_code].items():
                                        merged_layers[layer_name] = img_idx

                            code_to_option[str(display_code)] = (
                                str(display_code),
                                main_idx,
                                version,
                                p_idx,
                                merged_layers,
                            )
                    else:
                        # 单调色板
                        if base_code not in processed_codes:
                            processed_codes.add(base_code)
                            code_to_option[str(base_code)] = (
                                str(base_code),
                                main_idx,
                                version,
                                0,
                                layers.copy(),
                            )
                except:
                    # 如果解析失败，直接添加该 code
                    if base_code not in processed_codes:
                        processed_codes.add(base_code)
                        code_to_option[str(base_code)] = (
                            str(base_code),
                            (
                                layers.get(f"{part}_a", list(layers.values())[0])
                                if layers
                                else 0
                            ),
                            4,
                            0,
                            layers.copy(),
                        )

            self.part_options[part] = [
                code_to_option[c] for c in sorted(code_to_option.keys(), key=int)
            ]

        # 计算默认皮肤(code 0)的最大帧数
        self._calc_max_frame()

    def _calc_max_frame(self):
        """计算默认皮肤(code 0)的最大帧数"""
        try:
            if "skin" in self.part_options and self.part_options["skin"]:
                for option in self.part_options["skin"]:
                    if option[0] == "0":  # code 0 是默认皮肤
                        _, main_img_index, _, _, _ = option
                        if "skin" in self.loaded_npks:
                            npk = self.loaded_npks["skin"]
                            if main_img_index < len(npk.files):
                                img = npk.files[main_img_index].to_img()
                                self.max_frame = len(img.images) - 1
                                print(f"[Loader] 默认皮肤最大帧数: {self.max_frame}")
                                return
        except Exception as e:
            print(f"[Loader] 计算最大帧数失败: {e}")
        self.max_frame = 300  # 默认 fallback

    def get_sprite_image(
        self, part: str, img_index: int, sprite_index: int = 0, palette_index: int = 0
    ) -> Optional[Image.Image]:
        """获取指定部位的Sprite图像"""
        if part not in self.loaded_npks:
            return None

        npk = self.loaded_npks[part]
        if img_index >= len(npk.files):
            return None

        try:
            img = npk.files[img_index].to_img()
            if not img.images:
                return None

            sprite_index = min(sprite_index, len(img.images) - 1)
            sprite = resolve_image_link(img, img.image_by_index(sprite_index))
            if sprite is None:
                return None

            return convert_sprite_to_image(img, sprite, palette_index)
        except Exception as e:
            print(f"Error getting sprite: {e}")
            return None

    def get_merged_sprite_with_offset(
        self,
        part: str,
        option_idx: int,
        sprite_index: int = 0,
        frame_domain: Tuple[int, int] = (500, 500),
        process_f_layers: bool = True,
        process_g_layers: bool = True,
        process_h_layers: bool = True,
        g_layer_opacity: int = 0,
        h_layer_opacity: int = 0,
    ) -> Optional[Tuple[Image.Image, int, int]]:
        """
        合并所有图层获取部位图像

        Args:
            part: 部位名称
            option_idx: 装扮选项索引
            sprite_index: 帧索引
            frame_domain: 画布尺寸
            process_f_layers: 是否处理f层（去黑底+线性减淡）
            process_g_layers: 是否处理g层
            process_h_layers: 是否处理h层
            g_layer_opacity: g层不透明度调节 (-100~100, 0=原样, -100=完全透明)
            h_layer_opacity: h层不透明度调节 (-100~100, 0=原样, -100=完全透明)
        """
        if part not in self.loaded_npks or part not in self.part_options:
            return None

        options = self.part_options[part]
        if option_idx >= len(options):
            return None

        try:
            option = options[option_idx]
            _, main_img_index, _, palette_index, layer_indices = (
                option if len(option) >= 5 else (*option[:4], {"default": option[1]})
            )

            npk = self.loaded_npks[part]
            sorted_layers = sorted(
                layer_indices.keys(), key=lambda l: get_layer_priority(part, l)
            )

            domain_w, domain_h = frame_domain
            canvas = Image.new("RGBA", (domain_w, domain_h), (0, 0, 0, 0))
            base_x, base_y = 0, 0

            for layer in sorted_layers:
                img_index = layer_indices[layer]
                if img_index >= len(npk.files):
                    continue

                img = npk.files[img_index].to_img()
                if not img.images:
                    continue

                frame_idx = min(sprite_index, len(img.images) - 1)
                sprite = resolve_image_link(img, img.image_by_index(frame_idx))

                if sprite is None or (sprite.w <= 1 and sprite.h <= 1):
                    continue

                layer_img = convert_sprite_to_image(img, sprite, palette_index)
                if layer_img is None:
                    continue

                sprite_x, sprite_y = getattr(sprite, "x", 0), getattr(sprite, "y", 0)
                if base_x == 0 and base_y == 0:
                    base_x, base_y = sprite_x, sprite_y

                # 检查是否为f层并处理
                if process_f_layers and is_f_layer(layer):
                    # f层: 单独去黑底后叠加（不与其他f层互相作为base）
                    # 去黑底处理（透明背景）
                    processed = apply_f_layer_process(layer_img, black_threshold=50)
                    # 直接叠加到画布（使用Alpha混合）
                    canvas.paste(processed, (sprite_x, sprite_y), processed)
                elif process_g_layers and is_g_layer(layer):
                    # g层: 应用不透明度混合（类似PS图层不透明度）
                    crop_box = (
                        sprite_x,
                        sprite_y,
                        sprite_x + layer_img.width,
                        sprite_y + layer_img.height,
                    )
                    base_region = canvas.crop(crop_box)
                    blended = blend_layer_with_opacity(
                        base_region, layer_img, opacity_pct=g_layer_opacity
                    )
                    canvas.paste(blended, (sprite_x, sprite_y), blended)
                elif process_h_layers and is_h_layer(layer):
                    # h层: 应用不透明度混合（类似PS图层不透明度）
                    crop_box = (
                        sprite_x,
                        sprite_y,
                        sprite_x + layer_img.width,
                        sprite_y + layer_img.height,
                    )
                    base_region = canvas.crop(crop_box)
                    blended = blend_layer_with_opacity(
                        base_region, layer_img, opacity_pct=h_layer_opacity
                    )
                    canvas.paste(blended, (sprite_x, sprite_y), blended)
                else:
                    # 普通层: 直接粘贴
                    canvas.paste(layer_img, (sprite_x, sprite_y), layer_img)

            bbox = canvas.getbbox()
            if bbox:
                return canvas.crop(bbox), bbox[0], bbox[1]
            return None
        except Exception as e:
            print(f"Error merging sprite: {e}")
            return None

    def get_layer_sprite(
        self,
        part: str,
        option_idx: int,
        layer: str,
        sprite_index: int = 0,
        frame_domain: Tuple[int, int] = (500, 500),
    ) -> Optional[Image.Image]:
        """获取指定部位的单个图层图像"""
        if part not in self.loaded_npks or part not in self.part_options:
            return None

        options = self.part_options[part]
        if option_idx >= len(options) or len(options[option_idx]) < 5:
            return None

        try:
            _, _, _, palette_index, layer_indices = options[option_idx]
            if layer not in layer_indices:
                return None

            img_index = layer_indices[layer]
            npk = self.loaded_npks[part]

            if img_index >= len(npk.files):
                return None

            img = npk.files[img_index].to_img()
            if not img.images:
                return None

            frame_idx = min(sprite_index, len(img.images) - 1)
            sprite = resolve_image_link(img, img.image_by_index(frame_idx))

            if sprite is None or (sprite.w <= 1 and sprite.h <= 1):
                return None

            layer_img = convert_sprite_to_image(img, sprite, palette_index)
            if layer_img is None:
                return None

            domain_w, domain_h = frame_domain
            canvas = Image.new("RGBA", (domain_w, domain_h), (0, 0, 0, 0))
            canvas.paste(
                layer_img, (getattr(sprite, "x", 0), getattr(sprite, "y", 0)), layer_img
            )
            return canvas
        except Exception as e:
            print(f"Error getting layer sprite: {e}")
            return None

    def get_sprite_layer_info(
        self, part: str, option_idx: int
    ) -> Tuple[int, List[str]]:
        """获取指定装扮的图层信息"""
        if part not in self.loaded_npks or part not in self.part_options:
            return 0, []

        options = self.part_options[part]
        if option_idx >= len(options) or len(options[option_idx]) < 5:
            return 1, ["default"]

        try:
            _, _, _, _, layer_indices = options[option_idx]
            layers = sorted(layer_indices.keys())
            return len(layers), layers
        except Exception:
            return 0, []

    def generate_thumbnail(
        self,
        part: str,
        option_idx: int,
        size: Tuple[int, int] = (56, 56),
        job_key: str = None,
    ) -> Optional[Image.Image]:
        """生成缩略图 - 合并该装扮的所有图层

        Args:
            part: 部位名称
            option_idx: 装扮选项索引
            size: 缩略图尺寸
            job_key: 职业key，用于获取该职业的预览帧号配置
        """
        if part not in self.part_options:
            return None

        options = self.part_options[part]
        if option_idx >= len(options):
            return None

        try:
            option = options[option_idx]
            # 获取所有图层信息
            if len(option) >= 5:
                _, main_img_index, _, palette_index, layer_indices = option
            else:
                # 旧格式兼容
                _, main_img_index = option[:2]
                palette_index = 0
                layer_indices = {"default": main_img_index}

            npk = self.loaded_npks[part]

            # 按优先级排序所有图层
            sorted_layers = sorted(
                layer_indices.keys(), key=lambda l: get_layer_priority(part, l)
            )

            # 获取该职业的预览帧号（默认0）
            frame_idx = get_thumbnail_frame(job_key) if job_key else 0

            # 第一步：收集所有图层的信息，计算边界
            layer_data = []  # [(layer, layer_img, sprite_x, sprite_y), ...]
            min_x, min_y = float("inf"), float("inf")
            max_x, max_y = float("-inf"), float("-inf")

            for layer in sorted_layers:
                img_index = layer_indices[layer]
                if img_index >= len(npk.files):
                    continue

                img = npk.files[img_index].to_img()
                if not img.images:
                    continue

                sprite_idx = min(frame_idx, len(img.images) - 1)
                sprite = resolve_image_link(img, img.image_by_index(sprite_idx))
                if sprite is None or (sprite.w <= 1 and sprite.h <= 1):
                    continue

                layer_img = convert_sprite_to_image(img, sprite, palette_index)
                if layer_img is None:
                    continue

                sprite_x = getattr(sprite, "x", 0)
                sprite_y = getattr(sprite, "y", 0)

                layer_data.append((layer, layer_img, sprite_x, sprite_y))

                # 更新边界
                min_x = min(min_x, sprite_x)
                min_y = min(min_y, sprite_y)
                max_x = max(max_x, sprite_x + layer_img.width)
                max_y = max(max_y, sprite_y + layer_img.height)

            if not layer_data:
                return None

            # 计算画布尺寸（确保至少为1x1）
            canvas_width = max(1, max_x - min_x)
            canvas_height = max(1, max_y - min_y)

            # 创建画布，尺寸为所有图层的最大边界
            canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))

            # 第二步：绘制所有图层到画布（根据边界偏移位置）
            for layer, layer_img, sprite_x, sprite_y in layer_data:
                # 根据边界偏移位置
                draw_x = sprite_x - min_x
                draw_y = sprite_y - min_y

                # 检查是否为f层并处理
                if is_f_layer(layer):
                    # f层：单独去黑底后叠加
                    processed = apply_f_layer_process(layer_img, black_threshold=50)
                    canvas.paste(processed, (draw_x, draw_y), processed)
                else:
                    # 普通层: 简单的alpha混合
                    canvas.paste(layer_img, (draw_x, draw_y), layer_img)

            # 缩放为缩略图
            canvas.thumbnail(size, Image.Resampling.BILINEAR)
            return canvas

        except Exception as e:
            pass
        return None


# =============================================================================
# 套装加载器
# =============================================================================


class SuitLoader:
    """装扮套装加载器"""

    JOB_TO_FILE = {
        "swordman_male": "鬼剑士(男)",
        "fighter_female": "格斗家(女)",
        "fighter_male": "格斗家(男)",
        "gunner_male": "神枪手(男)",
        "gunner_female": "神枪手(女)",
        "mage_female": "魔法师(女)",
        "mage_male": "魔法师(男)",
        "priest_male": "圣职者(男)",
        "thief_female": "暗夜使者",
    }

    JOB_TO_ICON_NPK = {
        "swordman_male": "sprite_item_avatar_swordman",
        "fighter_female": "sprite_item_avatar_fighter",
        "fighter_male": "sprite_item_avatar_atfighter",
        "gunner_male": "sprite_item_avatar_gunner",
        "gunner_female": "sprite_item_avatar_atgunner",
        "mage_female": "sprite_item_avatar_mage",
        "mage_male": "sprite_item_avatar_atmage",
        "priest_male": "sprite_item_avatar_priest",
        "thief_female": "sprite_item_avatar_thief",
    }

    PART_ORDER = [
        "cap",
        "hair",
        "face",
        "neck",
        "coat",
        "pants",
        "belt",
        "shoes",
        "skin",
        "weapon",
    ]

    PART_SECTION_MAP = {
        "cap": "avatar,cap",
        "hair": "avatar,hair",
        "face": "avatar,face",
        "neck": "avatar,neck",
        "coat": "avatar,coat",
        "belt": "avatar,belt",
        "pants": "avatar,pants",
        "shoes": "avatar,shoes",
        "skin": "avatar,body",
        "weapon": "avatar,weapon",
    }

    CN_PART_MAP = {
        "头饰": "cap",
        "头发": "hair",
        "发型": "hair",  # 别名
        "脸部": "face",
        "面部": "face",  # 别名
        "胸部": "neck",
        "上衣": "coat",
        "腰带": "belt",
        "裤子": "pants",
        "下装": "pants",  # 别名
        "鞋子": "shoes",
        "皮肤": "skin",
        "武器": "weapon",
    }

    JOB_ICON_PREFIX = {
        "swordman_male": "sm",
        "fighter_female": "ft",
        "fighter_male": "fm",
        "gunner_male": "gn",
        "gunner_female": "gg",
        "mage_female": "mg",
        "mage_male": "mm",
        "priest_male": "pr",
        "thief_female": "th",
    }

    def __init__(self, avatar_path: str = None):
        if avatar_path is None:
            avatar_path = Path(__file__).parent
        self.avatar_path = Path(avatar_path)
        self.json_path = self.avatar_path / "avatar_config.json"

        # 确保目录和配置文件存在
        self._ensure_config_exists()

        self.suits: Dict[str, List[Dict]] = {}
        self.item_names: Dict[str, Dict[str, Dict[str, str]]] = {}
        self.icon_frames: Dict[str, Dict[str, Dict[str, int]]] = {}
        # 自定义图标映射: {job_key: {part: {code: {"img": "...", "frame": 0}}}}
        self.custom_icons: Dict[str, Dict[str, Dict[str, Dict]]] = {}
        # 配置数据缓存
        self._config_data: Dict[str, Dict] = {}

    def _ensure_config_exists(self):
        """确保配置目录和文件存在，不存在则创建"""
        try:
            # 创建目录（如果不存在）
            self.avatar_path.mkdir(parents=True, exist_ok=True)

            # 创建空配置文件（如果不存在）
            if not self.json_path.exists():
                empty_config = {}
                with open(self.json_path, "w", encoding="utf-8") as f:
                    json.dump(empty_config, f, ensure_ascii=False, indent=2)
                print(f"[INFO] 创建空配置文件: {self.json_path}")
        except Exception as e:
            print(f"[WARN] 创建配置目录/文件失败: {e}")

    def _load_or_convert_config(self, job_key: str) -> Optional[Dict]:
        """加载JSON配置（支持自动迁移）"""
        # 检查内存缓存
        if job_key in self._config_data:
            return self._config_data[job_key]

        config = None

        # 尝试加载JSON
        if self.json_path.exists():
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    all_config = json.load(f)
                    if job_key in all_config:
                        config = all_config[job_key]
            except Exception as e:
                print(f"[WARN] 加载JSON配置失败: {e}")

        # 自动迁移旧版配置（传入job_key确保能保存）
        if config is not None:
            config = self._migrate_config(config, job_key)
            self._config_data[job_key] = config

        return config

    def _migrate_config(self, config: Dict, job_key: Optional[str] = None) -> Dict:
        """迁移旧版配置到新版统一格式

        Args:
            config: 配置字典
            job_key: 职业key，如果提供则保存迁移后的配置

        迁移内容：
        1. 不自动添加icon_type，保留原样（无icon_type表示无图标）
        2. frame=-1表示明确无图标
        3. hide_parts默认为[]
        4. 将custom_icons合并到items中，标记icon_type="custom"
        5. 统一frame字段名（支持icon_frame和frame）
        """
        if config.get("_migrated"):
            return config

        try:
            print(f"[INFO] 正在迁移配置到新版格式...")
            migrated_count = 0

            # 1. 迁移items，处理无图标状态
            for part in self.PART_ORDER:
                part_items = config.get("items", {}).get(part, {})
                for code, item in list(part_items.items()):
                    if isinstance(item, dict):
                        # 确保hide_parts存在且为列表（不是None）
                        if "hide_parts" not in item or item.get("hide_parts") is None:
                            item["hide_parts"] = []
                            migrated_count += 1

                        # 统一frame字段
                        if "icon_frame" in item and "frame" not in item:
                            item["frame"] = item.pop("icon_frame")
                            migrated_count += 1
                        elif "frame" not in item:
                            # 没有frame字段时，设为-1表示无图标
                            item["frame"] = -1
                            migrated_count += 1

                        # 如果frame为-1，删除icon_type（表示无图标）
                        if item.get("frame") == -1 and "icon_type" in item:
                            del item["icon_type"]
                            migrated_count += 1
                    else:
                        # 兼容旧格式（字符串）-> 视为无图标
                        part_items[code] = {
                            "name": str(item),
                            "frame": -1,  # -1表示无图标
                            "hide_parts": [],
                            # 不设置icon_type，表示无图标
                        }
                        migrated_count += 1

            # 2. 将custom_icons合并到items
            if "custom_icons" in config:
                for part, icons in config["custom_icons"].items():
                    for code, icon_config in icons.items():
                        # 获取现有item或创建新的
                        existing = config["items"].get(part, {}).get(code, {})
                        # 只有当有有效frame时才设置icon_type
                        frame = icon_config.get("frame", 0)
                        if frame >= 0:
                            config["items"].setdefault(part, {})[code] = {
                                "name": existing.get("name", f"时装{code}"),
                                "frame": frame,
                                "img": icon_config.get("img"),
                                "icon_type": "custom",
                                "hide_parts": existing.get("hide_parts") or [],
                            }
                        else:
                            # 自定义图标但frame为-1，视为无图标
                            config["items"].setdefault(part, {})[code] = {
                                "name": existing.get("name", f"时装{code}"),
                                "frame": -1,
                                "hide_parts": existing.get("hide_parts") or [],
                            }
                # 删除旧的custom_icons字段
                del config["custom_icons"]
                print(f"[INFO] 已迁移旧版custom_icons到统一items格式")

            # 标记已迁移
            config["_migrated"] = True

            # 保存迁移后的配置
            if job_key:
                if self._save_config(job_key, config):
                    print(f"[INFO] 配置迁移完成，已保存 ({migrated_count} 项更新)")
                else:
                    print(f"[WARN] 配置迁移完成，但保存失败")
            else:
                print(f"[INFO] 配置迁移完成 ({migrated_count} 项更新)")

        except Exception as e:
            print(f"[WARN] 配置迁移失败: {e}")
            import traceback

            traceback.print_exc()

        return config

    def _save_config(self, job_key: str, config: Dict) -> bool:
        """保存配置到JSON文件"""
        try:
            all_config = {}
            if self.json_path.exists():
                with open(self.json_path, "r", encoding="utf-8") as f:
                    all_config = json.load(f)

            all_config[job_key] = config

            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(all_config, f, ensure_ascii=False, indent=2)
            
            # 清除内存缓存，确保下次加载时读取最新数据
            if job_key in self._config_data:
                del self._config_data[job_key]
            
            return True
        except Exception as e:
            print(f"[ERROR] 保存JSON配置失败: {e}")
            import traceback

            traceback.print_exc()
            return False

    def load_suits_for_job(self, job_key: str) -> bool:
        """加载指定职业的套装数据（使用统一items格式）"""
        self.suits[job_key] = []
        self.item_names[job_key] = {}
        self.icon_frames[job_key] = {part: {} for part in self.PART_ORDER}
        self.custom_icons[job_key] = {}

        config = self._load_or_convert_config(job_key)
        if not config:
            return False

        try:
            # 加载套装
            self.suits[job_key] = config.get("suits", [])

            # 加载物品信息（统一格式）
            items = config.get("items", {})
            for part in self.PART_ORDER:
                self.item_names[job_key][part] = {}
                part_items = items.get(part, {})
                for code, info in part_items.items():
                    if isinstance(info, dict):
                        # 1. 名称总是读取
                        self.item_names[job_key][part][code] = info.get("name", "")

                        # 2. 判断是否真的有图标
                        icon_type = info.get("icon_type")
                        frame = info.get("frame")

                        # 有图标的条件：有icon_type 且 frame不为None且不为-1
                        has_icon = (
                            icon_type is not None  # 有icon_type字段
                            and frame is not None  # 有frame字段
                            and frame != -1  # frame不是-1
                        )

                        if has_icon:
                            if icon_type == "custom":
                                # 自定义图标
                                if job_key not in self.custom_icons:
                                    self.custom_icons[job_key] = {}
                                if part not in self.custom_icons[job_key]:
                                    self.custom_icons[job_key][part] = {}
                                self.custom_icons[job_key][part][code] = {
                                    "img": info.get("img"),
                                    "frame": frame,
                                }
                            else:
                                # 标准图标
                                self.icon_frames[job_key][part][code] = frame
                        # else: 无图标，不加入icon_frames和custom_icons
                    else:
                        # 兼容旧格式（字符串）-> 视为无图标，只读名称
                        self.item_names[job_key][part][code] = str(info)

            return True
        except Exception as e:
            print(f"[ERROR] 加载套装数据失败: {e}")
            return False

    def get_item_config(self, job_key: str, part: str, code: str) -> Optional[Dict]:
        """获取时装完整配置（统一格式）"""
        config = self._load_or_convert_config(job_key)
        if not config:
            return None
        return config.get("items", {}).get(part, {}).get(code)

    def update_item_hide_parts(
        self, job_key: str, part: str, code: str, hide_parts: List[str]
    ) -> bool:
        """更新时装的隐藏部位配置"""
        config = self._load_or_convert_config(job_key)
        if not config:
            return False

        try:
            if part in config.get("items", {}) and code in config["items"][part]:
                config["items"][part][code]["hide_parts"] = hide_parts
                return self._save_config(job_key, config)
            return False
        except Exception as e:
            print(f"[ERROR] 更新隐藏部位失败: {e}")
            return False

    def get_custom_icon(self, job_key: str, part: str, code: str) -> Optional[Dict]:
        """获取自定义图标配置"""
        return self.custom_icons.get(job_key, {}).get(part, {}).get(code)

    def add_custom_icon(self, job_key: str, part: str, code: str, img: str, frame: int):
        """添加自定义图标配置（使用统一items格式）"""
        # 更新内存缓存（保持兼容性）
        if job_key not in self.custom_icons:
            self.custom_icons[job_key] = {}
        if part not in self.custom_icons[job_key]:
            self.custom_icons[job_key][part] = {}

        self.custom_icons[job_key][part][code] = {"img": img, "frame": frame}

        # 更新配置并保存（使用统一items格式）
        config = self._load_or_convert_config(job_key)
        if config:
            # 保留现有item的配置（如hide_parts）
            existing = config.get("items", {}).get(part, {}).get(code, {})
            # 安全获取hide_parts，确保不为None
            hide_parts = existing.get("hide_parts") or []
            if not isinstance(hide_parts, list):
                hide_parts = []
            name = existing.get("name", f"时装{code}")

            # 更新为统一格式
            config["items"].setdefault(part, {})[code] = {
                "name": name,
                "frame": frame,
                "img": img,
                "icon_type": "custom",
                "hide_parts": hide_parts,
            }
            self._save_config(job_key, config)

    def has_custom_icon(self, job_key: str, part: str, code: str) -> bool:
        """检查是否有自定义图标"""
        return code in self.custom_icons.get(job_key, {}).get(part, {})

    def remove_custom_icon(self, job_key: str, part: str, code: str) -> bool:
        """删除自定义图标配置"""
        if job_key not in self.custom_icons:
            return False
        if part not in self.custom_icons[job_key]:
            return False
        if code not in self.custom_icons[job_key][part]:
            return False

        # 从内存中删除
        del self.custom_icons[job_key][part][code]

        # 更新配置并保存
        config = self._config_data.get(job_key, {})
        if "custom_icons" in config and part in config["custom_icons"]:
            if code in config["custom_icons"][part]:
                del config["custom_icons"][part][code]
                # 清理空字典
                if not config["custom_icons"][part]:
                    del config["custom_icons"][part]
                if not config["custom_icons"]:
                    del config["custom_icons"]
            self._save_config(job_key, config)
        return True

    def _parse_icon_frame(self, icon_marker: str) -> Optional[int]:
        """解析图标标识获取帧索引，如 '头饰2' -> 2"""
        if not icon_marker:
            return None
        for cn_name in self.CN_PART_MAP.keys():
            if icon_marker.startswith(cn_name):
                try:
                    return int(icon_marker[len(cn_name) :])
                except ValueError:
                    return None
        return None

    def get_suits(self, job_key: str) -> List[Dict]:
        return self.suits.get(job_key, [])

    def delete_suit(self, job_key: str, suit_name: str) -> bool:
        """删除指定套装

        Args:
            job_key: 职业key
            suit_name: 套装名称

        Returns:
            是否删除成功
        """
        config = self._load_or_convert_config(job_key)
        if not config:
            return False

        try:
            suits = config.get("suits", [])
            # 查找并删除指定套装
            for i, suit in enumerate(suits):
                if suit.get("name") == suit_name:
                    suits.pop(i)

                    # 保存配置
                    if self._save_config(job_key, config):
                        # 更新内存缓存
                        self.suits[job_key] = suits
                        print(f"[INFO] 已删除套装: {suit_name}")
                        return True
                    else:
                        print(f"[ERROR] 删除套装后保存配置失败: {suit_name}")
                        return False

            # 未找到套装
            print(f"[WARN] 未找到要删除的套装: {suit_name}")
            return False

        except Exception as e:
            print(f"[ERROR] 删除套装失败: {e}")
            import traceback

            traceback.print_exc()
            return False

    def rename_suit(self, job_key: str, old_name: str, new_name: str) -> bool:
        """重命名套装
        
        Args:
            job_key: 职业key
            old_name: 原套装名称
            new_name: 新套装名称
            
        Returns:
            是否重命名成功
        """
        config = self._load_or_convert_config(job_key)
        if not config:
            return False

        try:
            suits = config.get("suits", [])
            
            # 查找并修改套装名称
            for suit in suits:
                if suit.get("name") == old_name:
                    suit["name"] = new_name
                    
                    # 保存配置
                    if self._save_config(job_key, config):
                        # 更新内存缓存
                        self.suits[job_key] = suits
                        print(f"[INFO] 已重命名套装: {old_name} → {new_name}")
                        return True
                    else:
                        print(f"[ERROR] 重命名套装后保存配置失败: {old_name} → {new_name}")
                        return False
            
            # 未找到套装
            print(f"[WARN] 未找到要重命名的套装: {old_name}")
            return False
            
        except Exception as e:
            print(f"[ERROR] 重命名套装失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_suits_for_item(self, job_key: str, part: str, code: str) -> List[Dict]:
        """获取包含指定时装的套装列表

        Returns:
            包含该时装的套装列表
        """
        suits = self.suits.get(job_key, [])
        return [s for s in suits if s.get("items", {}).get(part) == code]

    def add_or_update_suit(
        self, job_key: str, suit_name: str, part: str, code: str
    ) -> Tuple[bool, Optional[Dict]]:
        """添加或更新套装中的时装

        Args:
            job_key: 职业key
            suit_name: 套装名称
            part: 部位
            code: 时装代码

        Returns:
            (成功, 被替换的时装信息或None)
            被替换的时装信息: {"code": str, "name": str}
        """
        config = self._load_or_convert_config(job_key)
        if not config:
            return False, None

        try:
            # 确保suits结构存在
            if "suits" not in config:
                config["suits"] = []

            # 查找或创建套装
            suit = None
            for s in config["suits"]:
                if s.get("name") == suit_name:
                    suit = s
                    break

            replaced = None
            if suit is None:
                # 创建新套装，只包含当前部位（不补齐-1）
                suit = {"name": suit_name, "items": {part: code}}
                config["suits"].append(suit)
            else:
                # 检查是否有已存在的时装
                old_code = suit["items"].get(part)
                if old_code and old_code != "-1" and old_code != code:
                    old_name = self.get_item_name(job_key, part, old_code)
                    replaced = {"code": old_code, "name": old_name or f"时装{old_code}"}

                # 更新时装
                suit["items"][part] = code

            # 保存配置
            if self._save_config(job_key, config):
                # 更新内存缓存
                self.suits[job_key] = config["suits"]
                return True, replaced
            return False, None

        except Exception as e:
            print(f"[ERROR] 更新套装失败: {e}")
            return False, None

    def get_item_name(self, job_key: str, part: str, code: str) -> Optional[str]:
        return self.item_names.get(job_key, {}).get(part, {}).get(code)

    def get_icon_frame(self, job_key: str, part: str, code: str) -> Optional[int]:
        """获取图标帧号 - 无图标时返回None

        无图标的条件：
        - 没有icon_type字段
        - frame为None
        - frame为-1
        """
        # 先检查完整配置
        config = self._load_or_convert_config(job_key)
        if config:
            item = config.get("items", {}).get(part, {}).get(code)
            if isinstance(item, dict):
                icon_type = item.get("icon_type")
                frame = item.get("frame")

                # 无图标的条件
                if icon_type is None or frame is None or frame == -1:
                    return None

                # 有图标，返回frame
                return frame

        # 兼容旧逻辑：检查内存缓存
        standard_frame = self.icon_frames.get(job_key, {}).get(part, {}).get(code)
        if standard_frame is not None and standard_frame != -1:
            return standard_frame

        custom = self.get_custom_icon(job_key, part, code)
        if custom:
            custom_frame = custom.get("frame")
            if custom_frame is not None and custom_frame != -1:
                return custom_frame

        return None

    def get_icon_source(
        self, job_key: str, part: str, code: str
    ) -> Tuple[str, Optional[int]]:
        """获取图标来源信息
        返回: ("standard", frame) 或 ("custom", frame) 或 ("none", None)

        注意：当没有icon_type或frame为-1时，返回("none", None)表示无图标
        """
        # 先检查完整配置，确认是否有icon_type
        config = self._load_or_convert_config(job_key)
        if config:
            item = config.get("items", {}).get(part, {}).get(code)
            if isinstance(item, dict):
                icon_type = item.get("icon_type")
                frame = item.get("frame")

                # 无图标的条件：没有icon_type 或 frame为None 或 frame为-1
                if icon_type is None or frame is None or frame == -1:
                    return ("none", None)

                # 有图标
                if icon_type == "custom":
                    return ("custom", frame)
                else:
                    return ("standard", frame)

        # 兼容旧逻辑：检查内存缓存
        standard_frame = self.icon_frames.get(job_key, {}).get(part, {}).get(code)
        if standard_frame is not None and standard_frame != -1:
            return ("standard", standard_frame)

        custom = self.get_custom_icon(job_key, part, code)
        if custom:
            custom_frame = custom.get("frame")
            if custom_frame is not None and custom_frame != -1:
                return ("custom", custom_frame)

        return ("none", None)

    def get_icon_npk_name(self, job_key: str) -> Optional[str]:
        return self.JOB_TO_ICON_NPK.get(job_key)

    def get_icon_img_name(self, job_key: str, part: str) -> Optional[str]:
        prefix = self.JOB_ICON_PREFIX.get(job_key)
        if not prefix:
            return None

        # 武器部位使用不同的图标路径
        if part == "weapon":
            # 武器图标在 weapon 目录下
            npk_key = self.JOB_TO_ICON_NPK.get(job_key, "").replace(
                "sprite_item_avatar_", ""
            )
            return f"sprite/item/weapon/{npk_key}/{prefix}_aweapon.img"

        part_abbr = {
            "cap": "acap",
            "hair": "ahair",
            "face": "aface",
            "neck": "aneck",
            "coat": "acoat",
            "belt": "abelt",
            "pants": "apants",
            "shoes": "ashoes",
            "skin": "abody",  # NPK中实际叫 abody 而非 askin
        }.get(part, part)
        npk_key = self.JOB_TO_ICON_NPK.get(job_key, "").replace(
            "sprite_item_avatar_", ""
        )
        # print(f"Getting icon image name for job '{job_key}', part '{part}': npk_key='{npk_key}'")
        return f"sprite/item/avatar/{npk_key}/{prefix}_{part_abbr}.img"

    def add_or_update_item(
        self,
        job_key: str,
        part: str,
        code: str,
        icon_marker: str,
        name: str,
        hide_parts: Optional[List[str]] = None,
    ) -> bool:
        """添加或更新时装信息到JSON配置（支持隐藏部位）

        Args:
            icon_marker: 图标标识（如"头饰2"），为空或无效时表示无图标
            hide_parts: 要隐藏的部位列表，如 ["cap", "coat"]
        """
        # 加载配置
        config = self._load_or_convert_config(job_key)
        if not config:
            print(f"[ERROR] 无法加载配置: {job_key}")
            return False

        try:
            # 解析图标标识获取帧号
            frame = self._parse_icon_frame(icon_marker)

            # 判断是否有有效图标
            has_icon = frame is not None and frame >= 0

            # 确保items结构存在
            if "items" not in config:
                config["items"] = {}
            if part not in config["items"]:
                config["items"][part] = {}

            # 保留现有配置（如hide_parts）
            existing = config["items"][part].get(code, {})
            if hide_parts is not None:
                existing_hide_parts = hide_parts
            else:
                # 安全获取hide_parts，确保不为None
                existing_hide_parts = existing.get("hide_parts") or []
                if not isinstance(existing_hide_parts, list):
                    existing_hide_parts = []

            # 构建保存的数据
            item_data = {
                "name": name,
                "hide_parts": existing_hide_parts,
            }

            if has_icon:
                # 有图标时添加图标相关字段
                item_data["icon_type"] = "standard"
                item_data["frame"] = frame
            else:
                # 无图标时：不设置icon_type，frame设为-1
                item_data["frame"] = -1
                # 不添加icon_type字段

            # 更新或添加物品信息
            config["items"][part][code] = item_data

            # 保存配置
            if not self._save_config(job_key, config):
                print(f"[ERROR] 保存JSON配置失败")
                return False

            # 更新内存数据
            self.item_names.setdefault(job_key, {}).setdefault(part, {})[code] = name
            if has_icon and frame is not None:
                self.icon_frames.setdefault(job_key, {}).setdefault(part, {})[
                    code
                ] = frame
            else:
                # 无图标时，从icon_frames中移除（如果存在）
                if job_key in self.icon_frames and part in self.icon_frames.get(
                    job_key, {}
                ):
                    self.icon_frames[job_key][part].pop(code, None)

            print(
                f"[DEBUG] 已保存到JSON: {job_key}/{part}/{code} -> 帧号={frame if has_icon else '无图标'}, 名称={name}"
            )
            return True
        except Exception as e:
            print(f"[ERROR] 保存失败: {e}")
            import traceback

            traceback.print_exc()
            return False

    def save_item_without_icon(
        self,
        job_key: str,
        part: str,
        code: str,
        name: str,
        hide_parts: Optional[List[str]] = None,
    ) -> bool:
        """保存时装信息（无图标）

        Args:
            hide_parts: 要隐藏的部位列表，默认为空列表
        """
        config = self._load_or_convert_config(job_key)
        if not config:
            print(f"[ERROR] 无法加载配置: {job_key}")
            return False

        try:
            # 确保items结构存在
            if "items" not in config:
                config["items"] = {}
            if part not in config["items"]:
                config["items"][part] = {}

            # 获取现有配置
            existing = config["items"][part].get(code, {})

            # 确保hide_parts是列表
            if hide_parts is None:
                hide_parts = existing.get("hide_parts") or []
            if not isinstance(hide_parts, list):
                hide_parts = []

            # 构建无图标的数据
            item_data = {
                "name": name,
                "frame": -1,  # -1表示无图标
                "hide_parts": hide_parts,
                # 不设置icon_type，表示无图标
            }

            # 更新或添加物品信息
            config["items"][part][code] = item_data

            # 如果之前有自定义图标配置，删除它
            if job_key in self.custom_icons and part in self.custom_icons.get(
                job_key, {}
            ):
                if code in self.custom_icons[job_key][part]:
                    del self.custom_icons[job_key][part][code]

            # 从icon_frames中移除（如果存在）
            if job_key in self.icon_frames and part in self.icon_frames.get(
                job_key, {}
            ):
                self.icon_frames[job_key][part].pop(code, None)

            # 保存配置
            if not self._save_config(job_key, config):
                print(f"[ERROR] 保存JSON配置失败")
                return False

            # 更新内存数据
            self.item_names.setdefault(job_key, {}).setdefault(part, {})[code] = name

            print(f"[DEBUG] 已保存无图标时装: {job_key}/{part}/{code}, 名称={name}")
            return True
        except Exception as e:
            print(f"[ERROR] 保存无图标时装失败: {e}")
            import traceback

            traceback.print_exc()
            return False

    def delete_item(self, job_key: str, part: str, code: str) -> bool:
        """从JSON配置中删除时装记录"""
        # 加载配置
        config = self._load_or_convert_config(job_key)
        if not config:
            return False

        try:
            # 检查是否存在该记录
            if "items" not in config:
                return True
            if part not in config["items"]:
                return True
            if code not in config["items"][part]:
                return True

            # 删除记录
            del config["items"][part][code]

            # 保存配置
            if not self._save_config(job_key, config):
                print(f"[ERROR] 保存JSON配置失败")
                return False

            # 更新内存数据
            self.item_names.get(job_key, {}).get(part, {}).pop(code, None)
            self.icon_frames.get(job_key, {}).get(part, {}).pop(code, None)

            print(f"[DEBUG] 已从JSON删除: {job_key}/{part}/{code}")
            return True
        except Exception as e:
            print(f"[ERROR] 删除失败: {e}")
            import traceback

            traceback.print_exc()
            return False


# =============================================================================
# 图标加载器
# =============================================================================


class IconLoader:
    """时装图标加载器 - 支持分层索引和动态加载（带LRU缓存）"""

    # 缓存配置常量
    MAX_MEMORY_CACHE = 500  # 最大内存缓存数量
    CACHE_VERSION = "1.0"  # 缓存版本，用于缓存失效

    def __init__(self, npk_base_path: str = r"NPK"):
        self.npk_base_path = Path(npk_base_path)
        self.npk_ext_path = self.npk_base_path / "extension"
        self.loaded_icon_npks: Dict[str, NPK] = {}

        # 使用新的 LRUCache 替代原来的字典 + 锁
        self.icon_cache = LRUCache[Image.Image](max_size=500, name="PIL_Image_Cache")
        self._photoimage_cache = LRUCache[ImageTk.PhotoImage](
            max_size=300, name="PhotoImage_Cache"
        )

        self._cache_hits = 0
        self._disk_hits = 0
        self._npk_hits = 0
        self._photoimage_hits = 0

        # 磁盘缓存目录
        self.cache_dir = Path(__file__).parent / "icon_cache"
        self.cache_dir.mkdir(exist_ok=True)
        self._cache_meta_path = self.cache_dir / "cache_meta.json"
        self._cache_meta = self._load_cache_meta()

        # 批量元数据更新器 - 减少 IO 开销
        self._meta_updater = BatchMetaUpdater(self._batch_save_meta, delay=5.0)

        # 元数据和内存缓存锁
        self._cache_lock = threading.Lock()
        self._memory_cache_lock = threading.Lock()
        self._photoimage_cache_lock = threading.Lock()

        # NPK加载锁
        self._npk_load_lock = threading.Lock()

        # 索引帧缓存
        self._frame_link_cache: Dict[str, int] = {}
        self._frame_cache_lock = threading.Lock()
        self._frame_cache_dirty = False  # 标记是否有未保存的修改

        # IMG索引
        self.img_index: Dict[str, Dict] = {}
        self.standard_npks: Set[str] = set()
        self._index_built = False

    def _get_cache_path(self, npk_name: str, img_name: str, frame_index: int) -> Path:
        """获取缓存文件路径 - 使用哈希避免路径冲突"""
        # 使用组合键的哈希创建目录结构，避免同名IMG冲突
        import hashlib

        key = f"{npk_name}:{img_name}"
        hash_val = hashlib.md5(key.encode()).hexdigest()[:8]
        safe_img_name = img_name.replace("/", "_").replace("\\", "_")[:50]  # 限制长度

        cache_subdir = self.cache_dir / f"{npk_name[:30]}_{hash_val}" / safe_img_name
        cache_subdir.mkdir(parents=True, exist_ok=True)
        return cache_subdir / f"{frame_index}.png"

    def _load_cache_meta(self) -> Dict:
        """加载缓存元数据"""
        if self._cache_meta_path.exists():
            try:
                with open(self._cache_meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    # 检查版本
                    if meta.get("version") == self.CACHE_VERSION:
                        return meta
            except Exception:
                pass
        return {"version": self.CACHE_VERSION, "items": {}}

    def _save_cache_meta(self):
        """保存缓存元数据"""
        try:
            with self._cache_lock:
                # 在锁内复制，确保不会被其他线程修改
                meta_copy = copy.deepcopy(self._cache_meta)
            with open(self._cache_meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_copy, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Cache] 保存元数据失败: {e}")

    def _update_cache_meta(self, cache_key: str):
        """更新缓存项访问时间"""
        from time import time

        with self._cache_lock:
            self._cache_meta["items"][cache_key] = {
                "last_access": int(time()),
                "access_count": self._cache_meta["items"]
                .get(cache_key, {})
                .get("access_count", 0)
                + 1,
            }
            should_save = len(self._cache_meta["items"]) % 100 == 0
        # 在锁外保存，避免持有锁期间进行IO操作
        if should_save:
            self._save_cache_meta()

    def _add_to_memory_cache(self, cache_key: tuple, img: Image.Image):
        """添加图片到内存缓存（LRU策略）"""
        # 使用新的 LRUCache
        self.icon_cache.put(cache_key, img)

    def _get_from_memory_cache(self, cache_key: tuple) -> Optional[Image.Image]:
        """从内存缓存获取图片（更新LRU顺序）"""
        return self.icon_cache.get(cache_key)

    def _batch_save_meta(self, keys: set):
        """批量保存元数据"""
        for key in keys:
            self._cache_meta["items"][key] = {
                "last_access": int(time.time()),
            }
        self._save_cache_meta()
        print(f"[Cache] 批量保存 {len(keys)} 条元数据")

    def _scan_extension_npks(self):
        """扫描扩展目录中的非标准NPK并添加到索引"""
        print(f"[DEBUG] 扫描扩展目录: {self.npk_ext_path}")
        ext_npks = []
        if self.npk_ext_path.exists():
            ext_npks = (
                list(self.npk_ext_path.glob("*.NPK"))
                + list(self.npk_ext_path.glob("*.npk"))
                + list(self.npk_ext_path.glob("*.Npk"))
            )
            print(f"[DEBUG] 找到 {len(ext_npks)} 个扩展NPK文件")
        else:
            print(f"[WARN] 扩展目录不存在: {self.npk_ext_path}")

        ext_img_count = 0
        for npk_path in ext_npks:
            npk_name = npk_path.stem

            try:
                with open(npk_path, "rb") as f:
                    npk = NPK.open(f)

                    for img_file in npk.files:
                        img_name = img_file.name

                        # 扩展NPK内的IMG是非标准的，添加到索引
                        self.img_index[img_name] = {
                            "npk": npk_name,
                            "npk_path": str(npk_path),
                            "loaded": False,
                            "file": None,
                            "is_standard": False,
                        }
                        ext_img_count += 1

            except Exception as e:
                print(f"[WARN] 索引扩展NPK失败 {npk_name}: {e}")

        print(f"[DEBUG] 索引了 {ext_img_count} 个扩展IMG")
        non_standard_count = sum(
            1 for info in self.img_index.values() if not info["is_standard"]
        )
        print(f"[INFO] 非标准IMG总数: {non_standard_count}")

    def _index_standard_npks(self):
        """索引标准NPK文件中的IMG（使用已加载的standard_npks列表）"""
        print(f"[INFO] 索引标准NPK中的IMG...")

        for npk_name in self.standard_npks:
            # 查找NPK文件（支持多种大小写）
            npk_path = None
            for ext in [".NPK", ".npk", ".Npk"]:
                candidate = self.npk_base_path / (npk_name + ext)
                if candidate.exists():
                    npk_path = candidate
                    break

            if not npk_path:
                print(f"[WARN] 找不到NPK文件: {npk_name}")
                continue

            try:
                with open(npk_path, "rb") as f:
                    npk = NPK.open(f)

                    for img_file in npk.files:
                        img_name = img_file.name

                        # 标准NPK内的所有IMG都视为标准IMG
                        self.img_index[img_name] = {
                            "npk": npk_name,
                            "loaded": False,
                            "file": None,
                            "is_standard": True,
                        }

            except Exception as e:
                print(f"[WARN] 索引标准NPK失败 {npk_name}: {e}")

        print(
            f"[INFO] 标准NPK索引完成: {sum(1 for info in self.img_index.values() if info['is_standard'])} 个标准IMG"
        )

    def build_img_index(self):
        """构建IMG索引，将当前目录下所有NPK视为标准NPK"""
        if self._index_built:
            return

        # 尝试加载已保存的标准NPK列表
        if self.load_standard_npks():
            # 如果加载成功，仍然需要索引标准NPK的IMG
            print(f"[INFO] 使用缓存的标准NPK列表: {len(self.standard_npks)} 个")
            self._index_standard_npks()
            # 扫描扩展目录（因为扩展NPK可能变化）
            self._scan_extension_npks()
            self._index_built = True
            return

        # 扫描所有NPK文件
        npk_files = (
            list(self.npk_base_path.glob("*.NPK"))
            + list(self.npk_base_path.glob("*.npk"))
            + list(self.npk_base_path.glob("*.Npk"))
        )

        # 收集所有NPK文件名作为标准NPK
        self.standard_npks = {npk_path.stem for npk_path in npk_files}
        print(f"[INFO] 标准NPK列表: {len(self.standard_npks)} 个")
        for npk_name in sorted(self.standard_npks)[:10]:  # 只显示前10个
            print(f"  - {npk_name}")
        if len(self.standard_npks) > 10:
            print(f"  ... 还有 {len(self.standard_npks) - 10} 个")

        # 1. 索引标准NPK
        for npk_path in npk_files:
            npk_name = npk_path.stem

            try:
                # 只读取NPK头部信息，不加载全部内容
                with open(npk_path, "rb") as f:
                    npk = NPK.open(f)

                    for img_file in npk.files:
                        img_name = img_file.name

                        # 标准NPK内的所有IMG都视为标准IMG
                        self.img_index[img_name] = {
                            "npk": npk_name,
                            "loaded": False,
                            "file": None,
                            "is_standard": True,  # 标准NPK内的IMG都是标准的
                        }

            except Exception as e:
                print(f"[WARN] 索引标准NPK失败 {npk_name}: {e}")

        # 2. 索引扩展NPK（非标准）
        self._scan_extension_npks()

        self._index_built = True
        non_standard_count = sum(
            1 for info in self.img_index.values() if not info["is_standard"]
        )
        print(f"[INFO] IMG索引构建完成: 总计 {len(self.img_index)} 个IMG")
        print(
            f"[INFO] 标准IMG数量: {sum(1 for info in self.img_index.values() if info['is_standard'])}"
        )
        print(f"[INFO] 非标准IMG数量: {non_standard_count}")

        if non_standard_count == 0:
            print(
                f"[INFO] 提示: 将NPK文件放入 {self.npk_ext_path} 目录可作为非标准图标使用"
            )

        # 保存标准NPK列表
        self.save_standard_npks()

    def load_icon_npk(self, npk_name: str) -> bool:
        """加载指定NPK文件（支持标准和扩展目录）- 线程安全"""
        # 快速检查（无锁）
        if npk_name in self.loaded_icon_npks:
            return True

        # 加锁防止重复加载
        with self._npk_load_lock:
            # 双重检查
            if npk_name in self.loaded_icon_npks:
                return True

            # 先尝试标准目录
            npk_path = self.npk_base_path / f"{npk_name}.NPK"
            if not npk_path.exists():
                npk_path = self.npk_base_path / f"{npk_name}.npk"
            if not npk_path.exists():
                npk_path = self.npk_base_path / f"{npk_name}.Npk"

            # 再尝试扩展目录
            if not npk_path.exists() and self.npk_ext_path.exists():
                npk_path = self.npk_ext_path / f"{npk_name}.NPK"
                if not npk_path.exists():
                    npk_path = self.npk_ext_path / f"{npk_name}.npk"
                if not npk_path.exists():
                    npk_path = self.npk_ext_path / f"{npk_name}.Npk"

            if not npk_path.exists():
                return False

            try:
                with open(npk_path, "rb") as f:
                    npk = NPK.open(f)
                    npk.load_all()
                    self.loaded_icon_npks[npk_name] = npk

                    # 更新索引
                    for img_file in npk.files:
                        img_name = img_file.name
                        if img_name in self.img_index:
                            self.img_index[img_name]["loaded"] = True
                            self.img_index[img_name]["file"] = img_file

                    return True
            except Exception as e:
                print(f"[ERROR] 加载NPK失败 {npk_name}: {e}")
                return False

    def unload_npk(self, npk_name: str):
        """卸载指定NPK释放内存 - 线程安全"""
        with self._npk_load_lock:
            if npk_name in self.loaded_icon_npks:
                del self.loaded_icon_npks[npk_name]
                # 更新索引
                for img_name, info in self.img_index.items():
                    if info["npk"] == npk_name:
                        info["loaded"] = False
                        info["file"] = None

    def get_img_info(self, img_name: str) -> Optional[Dict]:
        """获取IMG信息"""
        return self.img_index.get(img_name)

    def get_icon(
        self,
        npk_name: str,
        img_name: str,
        frame_index: int,
        size: Tuple[int, int] = (56, 56),
    ) -> Optional[Image.Image]:
        """获取指定图标 - 优先从磁盘缓存加载（带LRU缓存）"""
        # 使用包含尺寸的缓存键，避免重复resize
        cache_key = (npk_name, img_name, frame_index, size)

        # 1. 内存缓存 (LRU) - 已经是指定尺寸的
        img = self._get_from_memory_cache(cache_key)
        if img is not None:
            self._cache_hits += 1
            return img

        # 2. 检查原始尺寸缓存（从NPK或磁盘加载的原始图）
        raw_cache_key = (npk_name, img_name, frame_index)
        raw_img = self._get_from_memory_cache(raw_cache_key)
        if raw_img is not None:
            # 有原始图，resize后存入尺寸缓存
            resized = raw_img.resize(size, Image.Resampling.BILINEAR)
            self._add_to_memory_cache(cache_key, resized)
            self._cache_hits += 1
            return resized

        # 3. 磁盘缓存
        cache_path = self._get_cache_path(npk_name, img_name, frame_index)
        if cache_path.exists():
            try:
                pil_img = Image.open(cache_path)
                # 检查磁盘缓存图尺寸是否匹配
                if pil_img.size == size:
                    # 尺寸匹配，直接使用
                    self._add_to_memory_cache(cache_key, pil_img)
                    self._meta_updater.add_update(
                        f"{npk_name}:{img_name}:{frame_index}"
                    )
                    self._disk_hits += 1
                    return pil_img
                else:
                    # 尺寸不匹配，需要resize
                    pil_img = pil_img.convert("RGBA")
                    self._add_to_memory_cache(raw_cache_key, pil_img)
                    resized = pil_img.resize(size, Image.Resampling.BILINEAR)
                    self._add_to_memory_cache(cache_key, resized)
                    self._meta_updater.add_update(
                        f"{npk_name}:{img_name}:{frame_index}"
                    )
                    self._disk_hits += 1
                    return resized
            except Exception:
                cache_path.unlink(missing_ok=True)

        # 4. 从 NPK 加载
        if not self.load_icon_npk(npk_name):
            return None

        npk = self.loaded_icon_npks.get(npk_name)
        if not npk:
            return None

        img_file = next((f for f in npk.files if img_name in f.name), None)
        if not img_file:
            return None

        try:
            img = img_file.to_img()
            if frame_index >= len(img.images):
                return None

            pil_img = img.build(img.images[frame_index])

            # 保存原始图到缓存
            self._add_to_memory_cache(raw_cache_key, pil_img)
            self._npk_hits += 1
            self._save_to_cache(cache_path, pil_img, npk_name, img_name, frame_index)

            # resize并返回
            return pil_img.resize(size, Image.Resampling.BILINEAR)
        except Exception as e:
            print(f"[ERROR] 构建图标失败: {e}")
            return None

    def get_icon_by_img_path(
        self,
        img_path: str,
        frame_index: int,
        size: Tuple[int, int] = (56, 56),
    ) -> Optional[Image.Image]:
        """通过IMG路径获取图标 - 使用索引系统自动加载NPK"""
        if not self._index_built:
            print("[WARN] IMG索引未构建，请先调用 build_img_index()")
            return None

        img_info = self.img_index.get(img_path)
        if not img_info:
            print(f"[WARN] IMG未在索引中找到: {img_path}")
            return None

        npk_name = img_info["npk"]

        # 动态加载NPK（如果未加载）
        if not img_info["loaded"]:
            if not self.load_icon_npk(npk_name):
                return None

        # 使用缓存的img_file对象
        img_file = self.img_index[img_path].get("file")
        if not img_file:
            return None

        cache_key = (npk_name, img_path, frame_index)

        # 1. 内存缓存 (LRU)
        img = self._get_from_memory_cache(cache_key)
        if img is not None:
            self._cache_hits += 1
            return img.resize(size, Image.Resampling.BILINEAR)

        # 2. 磁盘缓存
        cache_path = self._get_cache_path(npk_name, img_path, frame_index)
        if cache_path.exists():
            try:
                pil_img = Image.open(cache_path).convert("RGBA")
                self._add_to_memory_cache(cache_key, pil_img)
                self._meta_updater.add_update(f"{npk_name}:{img_path}:{frame_index}")
                self._disk_hits += 1
                return pil_img.resize(size, Image.Resampling.BILINEAR)
            except Exception:
                cache_path.unlink(missing_ok=True)

        # 3. 从NPK加载
        try:
            img = img_file.to_img()
            if frame_index >= len(img.images):
                return None

            pil_img = img.build(img.images[frame_index])

            self._add_to_memory_cache(cache_key, pil_img)
            self._npk_hits += 1
            self._save_to_cache(cache_path, pil_img, npk_name, img_path, frame_index)

            return pil_img.resize(size, Image.Resampling.BILINEAR)
        except Exception as e:
            print(f"[ERROR] 构建图标失败: {e}")
            return None

    def _save_to_cache(
        self,
        cache_path: Path,
        img: Image.Image,
        npk_name: str = "",
        img_path: str = "",
        frame: int = 0,
    ):
        """保存图标到磁盘缓存（优化压缩）"""
        try:
            # 使用最佳压缩保存PNG
            img.save(cache_path, "PNG", optimize=True, compress_level=6)
            # 使用批量更新器更新元数据
            if npk_name and img_path:
                self._meta_updater.add_update(f"{npk_name}:{img_path}:{frame}")
        except Exception as e:
            print(f"[Cache] 保存失败: {e}")

    def preload_icons(
        self, npk_name: str, img_name: str, total_frames: int, callback=None
    ) -> int:
        """预加载并缓存所有图标帧，返回缓存数量"""
        cached_count = 0
        for frame_idx in range(total_frames):
            cache_path = self._get_cache_path(npk_name, img_name, frame_idx)
            if not cache_path.exists():
                icon = self.get_icon(npk_name, img_name, frame_idx, (56, 56))
                if icon:
                    cached_count += 1
            if callback and frame_idx % 10 == 0:
                callback(frame_idx, total_frames)
        # 预加载完成后保存元数据
        self._save_cache_meta()
        # 保存可能积压的索引帧缓存
        self.save_frame_cache_if_dirty()
        return cached_count

    def get_icon_photo(
        self,
        npk_name: str,
        img_name: str,
        frame_index: int,
        size: Tuple[int, int] = (56, 56),
    ) -> Optional[ImageTk.PhotoImage]:
        """获取指定图标的 PhotoImage - 带PhotoImage缓存（最快）

        优先从PhotoImage缓存获取，避免重复的 PIL->PhotoImage 转换
        """
        cache_key = (npk_name, img_name, frame_index, size)

        # 1. 检查 PhotoImage 缓存（最快，直接可用）
        with self._photoimage_cache_lock:
            if cache_key in self._photoimage_cache:
                # 移动到末尾（最新使用）
                photo = self._photoimage_cache.pop(cache_key)
                self._photoimage_cache[cache_key] = photo
                self._photoimage_hits += 1
                return photo

        # 2. 获取 PIL Image（从内存/磁盘/NPK）
        pil_img = self.get_icon(npk_name, img_name, frame_index, size)
        if pil_img is None:
            return None

        # 3. 转换为 PhotoImage 并存入缓存
        photo = ImageTk.PhotoImage(pil_img)

        with self._photoimage_cache_lock:
            # 缓存满时清理最早的10%
            if len(self._photoimage_cache) >= self._photoimage_cache_max_size:
                keys_to_remove = list(self._photoimage_cache.keys())[
                    : self._photoimage_cache_max_size // 10
                ]
                for key in keys_to_remove:
                    del self._photoimage_cache[key]

            self._photoimage_cache[cache_key] = photo

        return photo

    def get_cache_stats(self) -> dict:
        """获取缓存统计信息 - 线程安全"""
        # 计算磁盘缓存大小
        disk_size_mb = 0
        cache_files = list(self.cache_dir.rglob("*.png"))
        try:
            disk_size_mb = sum(f.stat().st_size for f in cache_files) / (1024 * 1024)
        except:
            pass

        # 加锁读取内存缓存大小
        with self._memory_cache_lock:
            memory_cache_size = len(self.icon_cache)

        # 加锁读取PhotoImage缓存大小
        with self._photoimage_cache_lock:
            photoimage_cache_size = len(self._photoimage_cache)

        return {
            "memory_cache_size": memory_cache_size,
            "memory_cache_limit": self.MAX_MEMORY_CACHE,
            "photoimage_cache_size": photoimage_cache_size,
            "photoimage_cache_limit": self._photoimage_cache_max_size,
            "disk_cache_files": len(cache_files),
            "disk_cache_size_mb": round(disk_size_mb, 2),
            "memory_hits": self._cache_hits,
            "disk_hits": self._disk_hits,
            "npk_hits": self._npk_hits,
            "photoimage_hits": self._photoimage_hits,
        }

    def clear_memory_cache(self):
        """清理内存缓存（保留磁盘缓存）- 线程安全"""
        with self._memory_cache_lock:
            self.icon_cache.clear()
        with self._photoimage_cache_lock:
            self._photoimage_cache.clear()

    def clean_disk_cache(self, max_age_days: int = 30, keep_count: int = 1000):
        """清理过期磁盘缓存 - 线程安全

        Args:
            max_age_days: 删除超过此天数未访问的缓存
            keep_count: 至少保留的最新缓存数量
        """
        from time import time

        now = int(time())
        max_age_seconds = max_age_days * 24 * 3600

        # 在锁内复制元数据，避免遍历时被修改
        with self._cache_lock:
            meta_items = list(self._cache_meta.get("items", {}).items())

        # 获取所有缓存文件及其访问时间
        cache_files = []
        for cache_key, meta in meta_items:
            # 尝试找到对应的文件
            parts = cache_key.rsplit(":", 2)
            if len(parts) == 3:
                npk, img, frame = parts
                cache_path = self._get_cache_path(npk, img, int(frame))
                if cache_path.exists():
                    last_access = meta.get("last_access", 0)
                    cache_files.append((cache_path, last_access, cache_key))

        # 按访问时间排序
        cache_files.sort(key=lambda x: x[1], reverse=True)

        deleted = 0
        keys_to_remove = []
        for i, (cache_path, last_access, cache_key) in enumerate(cache_files):
            # 保留最新的N个，删除超时的
            if i >= keep_count and (now - last_access) > max_age_seconds:
                try:
                    cache_path.unlink()
                    deleted += 1
                    keys_to_remove.append(cache_key)
                except Exception:
                    pass

        # 批量删除元数据
        if keys_to_remove:
            with self._cache_lock:
                for key in keys_to_remove:
                    if key in self._cache_meta["items"]:
                        del self._cache_meta["items"][key]

        self._save_cache_meta()
        print(f"[Cache] 清理完成: 删除 {deleted} 个过期缓存文件")
        return deleted

    # ============ 索引帧（ImageLink）缓存 ============

    def _get_frame_cache_path(self) -> Path:
        """获取索引帧缓存文件路径"""
        return self.cache_dir / "frame_link_cache.json"

    def load_frame_cache(self) -> Dict:
        """加载索引帧缓存"""
        cache_path = self._get_frame_cache_path()
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARN] 加载索引帧缓存失败: {e}")
        return {}

    def save_frame_cache(self, cache: Dict):
        """保存索引帧缓存"""
        cache_path = self._get_frame_cache_path()
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] 保存索引帧缓存失败: {e}")

    def get_actual_frame(self, img_path: str, frame_idx: int, img_file=None) -> int:
        """获取实际帧号（解析ImageLink后的帧号）- 线程安全
        返回: 实际帧号（如果该帧是ImageLink指向其他帧，则返回目标帧号）
        """
        cache_key = f"{img_path}:{frame_idx}"

        # 1. 检查内存缓存（加锁读取）
        with self._frame_cache_lock:
            if cache_key in self._frame_link_cache:
                return self._frame_link_cache[cache_key]

        # 2. 从文件加载（如果内存缓存为空）- 只需加载一次
        if not self._frame_link_cache:
            file_cache = self.load_frame_cache()
            with self._frame_cache_lock:
                if not self._frame_link_cache:  # 双重检查
                    self._frame_link_cache.update(file_cache)
                    if cache_key in self._frame_link_cache:
                        return self._frame_link_cache[cache_key]

        # 3. 解析ImageLink
        actual_frame = self._resolve_frame_link(img_path, frame_idx, img_file)

        # 4. 缓存结果（加锁写入，延迟保存）
        with self._frame_cache_lock:
            self._frame_link_cache[cache_key] = actual_frame
            self._frame_cache_dirty = True

        return actual_frame

    def save_frame_cache_if_dirty(self):
        """如果有未保存的修改，保存索引帧缓存 - 批量保存优化"""
        with self._frame_cache_lock:
            if self._frame_cache_dirty and self._frame_link_cache:
                self._frame_cache_dirty = False
                cache_copy = copy.deepcopy(self._frame_link_cache)
            else:
                return

        # 在锁外保存
        self.save_frame_cache(cache_copy)

    def _resolve_frame_link(self, img_path: str, frame_idx: int, img_file=None) -> int:
        """解析ImageLink获取实际帧号"""
        try:
            if img_file is None:
                # 从索引获取img_file
                img_info = self.img_index.get(img_path)
                if not img_info or not img_info["loaded"]:
                    return frame_idx
                img_file = img_info["file"]

            if not img_file:
                return frame_idx

            img = img_file.to_img()
            if frame_idx >= len(img.images):
                return frame_idx

            sprite = img.images[frame_idx]

            # 检查是否是ImageLink（需要导入ImageLink类）
            from pydoftools.npk.img.image import ImageLink

            if isinstance(sprite, ImageLink):
                # ImageLink通常指向另一个帧
                target_idx = sprite.index
                # 递归解析（防止循环）
                visited = {frame_idx}
                depth = 0
                while isinstance(sprite, ImageLink) and depth < 10:
                    if target_idx in visited or target_idx >= len(img.images):
                        break
                    visited.add(target_idx)
                    sprite = img.images[target_idx]
                    if isinstance(sprite, ImageLink):
                        target_idx = sprite.index
                    depth += 1
                return target_idx

            return frame_idx

        except Exception as e:
            print(f"[WARN] 解析ImageLink失败 {img_path}:{frame_idx}: {e}")
            return frame_idx

    def save_standard_npks(self):
        """保存标准NPK列表到文件"""
        cache_path = self.cache_dir / "standard_npks.json"
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "npk_base_path": str(self.npk_base_path),
                        "npk_ext_path": str(self.npk_ext_path),
                        "standard_npks": sorted(list(self.standard_npks)),
                        "img_count": len(self.img_index),
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            print(f"[INFO] 标准NPK列表已保存: {cache_path}")
        except Exception as e:
            print(f"[WARN] 保存标准NPK列表失败: {e}")

    def load_standard_npks(self) -> bool:
        """从文件加载标准NPK列表
        返回: 是否成功加载且路径匹配
        """
        cache_path = self.cache_dir / "standard_npks.json"
        if not cache_path.exists():
            return False

        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 检查路径是否匹配
            cached_path = data.get("npk_base_path", "")
            cached_ext_path = data.get("npk_ext_path", "")
            if cached_path != str(self.npk_base_path):
                print(
                    f"[INFO] NPK路径变更，重新构建索引: {cached_path} -> {self.npk_base_path}"
                )
                return False

            # 恢复标准NPK列表
            self.standard_npks = set(data.get("standard_npks", []))
            print(f"[INFO] 已加载标准NPK列表: {len(self.standard_npks)} 个")

            # 重建IMG索引（标记标准/非标准）
            for img_name, info in list(self.img_index.items()):
                if info["npk"] in self.standard_npks:
                    info["is_standard"] = True
                else:
                    info["is_standard"] = False

            return True
        except Exception as e:
            print(f"[WARN] 加载标准NPK列表失败: {e}")
            return False

    def set_npk_path(self, base_path: str):
        """更新NPK基础路径 - 线程安全"""
        self.npk_base_path = Path(base_path)
        self.npk_ext_path = self.npk_base_path / "extension"
        with self._npk_load_lock:
            self.loaded_icon_npks.clear()
        with self._memory_cache_lock:
            self.icon_cache.clear()


# =============================================================================
# 动画加载器
# =============================================================================


class AnimationLoader:
    """动画文件加载器"""

    def __init__(
        self, animation_path: str = r"D:\DOF\output\Avatar\舞台\animation.txt"
    ):
        self.animation_path = Path(animation_path)
        self.animations: Dict[str, Dict[str, List[int]]] = {}
        self._load_animations()

    def _load_animations(self):
        """加载动画文件"""
        if not self.animation_path.exists():
            return

        try:
            with open(self.animation_path, "r", encoding="gbk") as f:
                content = f.read()

            current_job = None
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue

                if line.startswith("[") and line.endswith("]"):
                    current_job = line[1:-1]
                    self.animations[current_job] = {}
                elif "|" in line and current_job:
                    parts = line.split("|")
                    if len(parts) == 2:
                        action_name = parts[0].strip()
                        frames = [
                            int(f)
                            for f in parts[1].strip().split("-")
                            if f.isdigit() or (f.startswith("-") and f[1:].isdigit())
                        ]
                        if frames:
                            self.animations[current_job][action_name] = frames
        except Exception as e:
            print(f"Error loading animation file: {e}")

    def get_actions(self, job: str) -> List[str]:
        return list(self.animations.get(job, {}).keys())

    def get_frames(self, job: str, action: str) -> List[int]:
        return self.animations.get(job, {}).get(action, [])


# =============================================================================
# 主应用
# =============================================================================


class DressingRoomApp:
    """试衣间应用"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("试衣间 - Avatar Dressing Room (Optimized)")
        
        # 设置窗口大小并居中
        window_width = 1440
        window_height = 900
        self._center_window(self.root, window_width, window_height)
        
        self.root.resizable(True, True)

        # 先初始化缓存文件路径
        self.cache_file = Path(__file__).parent / "dressing_room_cache.json"

        # 初始化NPK路径（第一次启动时弹出选择对话框）
        self.npk_dir = self._init_npk_path()
        if not self.npk_dir:
            return  # 用户取消选择，程序将退出

        # 使用用户选择的NPK路径初始化各个loader
        self.loader = DressingRoomLoader(base_path=self.npk_dir)
        self.animation_loader = AnimationLoader()
        self.suit_loader = SuitLoader()  # 使用程序所在目录下的装扮配置
        self.icon_loader = IconLoader(npk_base_path=self.npk_dir)

        # 构建IMG索引（延迟到设置NPK路径后）
        self._img_index_built = False

        self.selected_parts: Dict[str, int] = {}
        self.missing_items: Dict[str, str] = {}
        self.current_part: Optional[str] = None

        self.items_per_page = 64  # 默认8x8布局
        self.current_page = 0
        self.total_pages = 0
        self.grid_layout_mode = "8x8"  # 布局模式: "8x8" 或 "4x4"
        self.filtered_options: List[Tuple] = []

        self.animation_running = False
        self.current_action = "idle"
        self.current_frame = 0
        self.current_animation_frames: List[int] = []
        self.animation_frame_index = 0
        self.show_icons = False
        self.show_missing_only = False  # 是否只显示缺失对应关系的项

        # f层（发光层）处理开关
        self.process_f_layers = True  # 默认启用f层去黑底+线性减淡处理

        # 预览背景类型: "black", "white", "gray", "checkerboard"
        self.preview_bg_type = "checkerboard"

        # g层（半透明阴影层）处理开关和不透明度调节
        self.process_g_layers = True  # 默认启用g层处理
        self.g_layer_opacity = 0  # g层不透明度调节 (-100~100, 0=原样, -100=完全透明)

        # h层（深层阴影层）处理开关和不透明度调节
        self.process_h_layers = True  # 默认启用h层处理
        self.h_layer_opacity = 0  # h层不透明度调节 (-100~100, 0=原样, -100=完全透明)

        # 强制显示隐藏部位开关
        self.force_show_hidden = False  # 默认不强制显示，被隐藏的部位正常隐藏

        # 统一缓存管理器（整合原来分散的6个缓存字典）
        self.cache = CacheManager()

        # 后台缓存控制
        self._caching_thread = None
        self._cache_stop_flag = False
        self._cache_progress_var = tk.StringVar(value="")
        self._preview_image_id = None  # Canvas图像对象ID，用于复用

        # 武器类型选择
        self.weapon_type_var = tk.StringVar(value="beamswd")  # 默认光剑
        self.weapon_type_frame = None  # 武器类型下拉框容器
        self.weapon_type_combo = None  # 武器类型下拉框

        # 初始化主题管理器（从缓存加载主题偏好）
        self.theme_manager = ThemeManager(self._load_theme_preference())

        self._create_ui()

    def _load_theme_preference(self) -> str:
        """加载主题偏好设置"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                    theme = cache.get("theme", "light")
                    if theme in ThemeManager.THEMES:
                        return theme
        except Exception as e:
            print(f"[WARN] 加载主题偏好失败: {e}")
        return "light"

    def _save_theme_preference(self, theme_name: str):
        """保存主题偏好设置"""
        try:
            cache = {}
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
            cache["theme"] = theme_name
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] 保存主题偏好失败: {e}")

    def switch_theme(self, theme_name: str):
        """切换主题"""
        if self.theme_manager.set_theme(theme_name):
            self._save_theme_preference(theme_name)
            messagebox.showinfo(
                "主题切换",
                f"主题已切换为: {self.theme_manager.get('name')}\n请重启程序以应用新主题。",
            )
        else:
            messagebox.showerror("错误", f"未知主题: {theme_name}")

    def _load_npk_cache(self) -> str:
        """加载NPK路径缓存，如果没有则返回空字符串"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    cache = json.load(f)
                    cached_path = cache.get("npk_dir", "")
                    if cached_path and Path(cached_path).exists():
                        return cached_path
        except Exception as e:
            print(f"加载缓存失败: {e}")
        return ""

    def _init_npk_path(self) -> str:
        """初始化NPK路径，第一次启动时弹出选择对话框"""
        npk_dir = self._load_npk_cache()
        if npk_dir:
            return npk_dir

        # 第一次启动，弹出选择对话框
        messagebox.showinfo(
            "首次启动",
            "欢迎使用试衣间！\n\n请选择NPK文件所在的目录（包含 .npk 文件的文件夹）。",
        )

        selected = filedialog.askdirectory(
            title="选择NPK目录",
            initialdir=str(Path.home()),
        )

        if selected:
            npk_path = Path(selected)
            # 检查目录中是否有NPK文件
            npk_files = list(npk_path.glob("*.npk")) + list(npk_path.glob("*.NPK"))
            if not npk_files:
                if not messagebox.askyesno(
                    "警告",
                    f"该目录中没有找到NPK文件。\n路径: {selected}\n\n是否仍要使用此目录？",
                ):
                    # 用户取消，退出程序
                    self.root.destroy()
                    return ""

            self._save_npk_cache(str(npk_path))
            return str(npk_path)
        else:
            # 用户取消了选择，退出程序
            messagebox.showerror("错误", "必须选择NPK目录才能使用程序")
            self.root.destroy()
            return ""

    def _save_npk_cache(self, npk_dir: str):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump({"npk_dir": npk_dir}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存缓存失败: {e}")

    def _center_window(self, window, width: int = None, height: int = None):
        """将窗口居中显示"""
        window.update_idletasks()
        
        # 获取窗口大小
        if width is None or height is None:
            width = window.winfo_width()
            height = window.winfo_height()
        else:
            window.geometry(f"{width}x{height}")
        
        # 获取屏幕尺寸
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        
        # 计算居中位置
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        # 确保窗口不会超出屏幕边界
        x = max(0, min(x, screen_width - width))
        y = max(0, min(y, screen_height - height))
        
        window.geometry(f"+{x}+{y}")

    def _create_ui(self):
        """创建界面"""
        tm = self.theme_manager

        # 配置ttk样式 - 确保所有ttk控件都使用主题颜色
        style = ttk.Style()
        style.configure(
            "Selected.TButton", background=tm.get("accent_primary"), foreground="white"
        )

        # 配置TFrame背景色
        style.configure("TFrame", background=tm.get("bg_primary"))
        style.configure("Toolbar.TFrame", background=tm.get("bg_primary"))

        # 配置TLabel背景色和前景色
        style.configure(
            "TLabel", background=tm.get("bg_primary"), foreground=tm.get("fg_primary")
        )

        # 配置TButton样式
        style.configure(
            "TButton", background=tm.get("button_bg"), foreground=tm.get("button_fg")
        )
        style.map(
            "TButton",
            background=[
                ("active", tm.get("button_active_bg")),
                ("pressed", tm.get("accent_primary")),
            ],
            foreground=[("active", tm.get("button_active_fg")), ("pressed", "white")],
        )

        # 配置TEntry样式
        style.configure(
            "TEntry", fieldbackground=tm.get("entry_bg"), foreground=tm.get("entry_fg")
        )

        # 配置TLabelFrame样式
        style.configure(
            "TLabelFrame",
            background=tm.get("bg_primary"),
            foreground=tm.get("fg_primary"),
        )
        style.configure(
            "TLabelFrame.Label",
            background=tm.get("bg_primary"),
            foreground=tm.get("fg_primary"),
        )

        # 配置TCombobox样式
        style.configure(
            "TCombobox",
            fieldbackground=tm.get("entry_bg"),
            foreground=tm.get("entry_fg"),
        )
        style.map("TCombobox", fieldbackground=[("readonly", tm.get("entry_bg"))])

        # 配置TNotebook样式
        style.configure("TNotebook", background=tm.get("bg_primary"))
        style.configure(
            "TNotebook.Tab",
            background=tm.get("bg_tertiary"),
            foreground=tm.get("fg_primary"),
        )
        style.map(
            "TNotebook.Tab",
            background=[
                ("selected", tm.get("tab_selected_bg")),
                ("active", tm.get("tab_active_bg")),
            ],
            foreground=[
                ("selected", tm.get("tab_selected_fg")),
                ("active", tm.get("tab_active_fg")),
            ],
        )

        # 配置Treeview（列表框）样式
        style.configure(
            "Treeview", background=tm.get("listbox_bg"), foreground=tm.get("listbox_fg")
        )
        style.configure(
            "Treeview.Heading",
            background=tm.get("bg_tertiary"),
            foreground=tm.get("fg_primary"),
        )

        # 配置Scrollbar样式
        style.configure(
            "TScrollbar",
            background=tm.get("bg_tertiary"),
            troughcolor=tm.get("bg_primary"),
        )

        # 配置TCheckbutton样式
        style.configure(
            "TCheckbutton",
            background=tm.get("bg_primary"),
            foreground=tm.get("fg_primary"),
        )

        # 配置TRadiobutton样式
        style.configure(
            "TRadiobutton",
            background=tm.get("bg_primary"),
            foreground=tm.get("fg_primary"),
        )

        # 设置根窗口背景
        self.root.configure(bg=tm.get("bg_primary"))

        self.main_frame = tk.Frame(self.root, bg=tm.get("bg_primary"), padx=5, pady=5)
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=0)
        self.main_frame.columnconfigure(1, weight=1)
        self.main_frame.rowconfigure(1, weight=1)

        self._create_toolbar()
        self._create_left_panel()
        self._create_right_panel()
        self._create_bottom_panel()

        # 如果有缓存的NPK路径，延迟构建IMG索引
        self.root.after(500, self._init_img_index)

    def _init_img_index(self):
        """初始化IMG索引（延迟执行）"""
        npk_dir = self.npk_dir_var.get()

        # 检查目录是否有效
        if not npk_dir:
            self.status_label.config(text="提示: 请选择NPK目录")
            return

        npk_path = Path(npk_dir)
        if not npk_path.exists():
            self.status_label.config(text="提示: NPK目录不存在，请重新选择")
            return

        # 检查目录中是否有NPK文件
        npk_files = list(npk_path.glob("*.NPK")) + list(npk_path.glob("*.npk"))
        if not npk_files:
            self.status_label.config(text="提示: 目录中没有NPK文件，请重新选择")
            return

        if self._img_index_built:
            return

        print(f"[DEBUG] 初始化IMG索引: {npk_dir}")
        self.status_label.config(text="正在构建IMG索引...")
        self.root.update()

        try:
            self.icon_loader.set_npk_path(npk_dir)
            self.icon_loader.build_img_index()
            self._img_index_built = True
            self.status_label.config(
                text=f"IMG索引构建完成: {len(self.icon_loader.img_index)} 个IMG"
            )
            print(f"[INFO] IMG索引构建完成: {len(self.icon_loader.img_index)} 个IMG")
        except Exception as e:
            print(f"[ERROR] IMG索引构建失败: {e}")
            self.status_label.config(text=f"IMG索引构建失败: {e}")

    def _create_toolbar(self):
        """顶部工具栏"""
        tm = self.theme_manager
        toolbar = tk.Frame(self.main_frame, bg=tm.get("bg_primary"), padx=5, pady=5)
        toolbar.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))

        tk.Label(
            toolbar,
            text="试衣间",
            font=("Microsoft YaHei", 12, "bold"),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=(0, 20))

        # 保留job_var用于状态存储
        self.job_var = tk.StringVar()
        # 创建中文名到英文代码的反向查找字典
        if not hasattr(self, "job_name_to_key"):
            self.job_name_to_key = {v["name"]: k for k, v in JOB_CONFIG.items()}

        tk.Label(
            toolbar, text="NPK目录:", bg=tm.get("bg_primary"), fg=tm.get("fg_primary")
        ).pack(side=tk.LEFT, padx=(20, 0))
        self.npk_dir_var = tk.StringVar(value=self.npk_dir)
        self.npk_dir_entry = tk.Entry(
            toolbar,
            textvariable=self.npk_dir_var,
            width=30,
            state="readonly",
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        )
        self.npk_dir_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(
            toolbar,
            text="浏览...",
            command=self._select_npk_dir,
            width=6,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT)
        tk.Button(
            toolbar,
            text="检查缺失",
            command=self._check_missing_npk,
            width=8,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=(5, 0))

        # 主题切换菜单
        self.theme_btn = tk.Menubutton(
            toolbar,
            text="主题",
            relief=tk.RAISED,
            bg=tm.get("accent_primary"),
            fg="white",
            font=("Arial", 9),
            width=8,
        )
        self.theme_btn.pack(side=tk.LEFT, padx=(10, 0))

        theme_menu = tk.Menu(self.theme_btn, tearoff=0)
        for theme_key, theme_name in ThemeManager().get_theme_names():
            theme_menu.add_command(
                label=theme_name, command=lambda t=theme_key: self.switch_theme(t)
            )
        self.theme_btn.config(menu=theme_menu)

        self.status_label = tk.Label(
            toolbar, text="", bg=tm.get("bg_primary"), fg=tm.get("label_info")
        )
        self.status_label.pack(side=tk.LEFT, padx=(20, 0))

    def _create_left_panel(self):
        """左侧：职业选择 + 部位选择 + 装扮列表 + 预览图"""
        tm = self.theme_manager
        self.left_frame = tk.Frame(self.main_frame, bg=tm.get("bg_primary"))
        self.left_frame.grid(
            row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5)
        )
        self.left_frame.columnconfigure(0, weight=1)
        self.left_frame.rowconfigure(1, weight=1)

        # 职业和部位选择（合并到同一行）
        parts_frame = tk.LabelFrame(
            self.left_frame,
            text="职业/部位",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            padx=5,
            pady=5,
        )
        parts_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        # 按钮布局：两行，每行6个
        # 第一行：职业、随机、帽子、头发、脸部、胸部
        # 第二行：上衣、腰带、裤子、鞋子、皮肤、武器

        # 职业选择按钮
        self.job_select_btn = tk.Button(
            parts_frame,
            text="职业",
            width=6,
            bg=tm.get("accent_primary"),
            fg="white",
            command=self._show_job_select_dialog,
        )
        self.job_select_btn.grid(row=0, column=0, padx=2, pady=2)

        # 随机按钮
        random_btn = tk.Button(
            parts_frame,
            text="随机",
            width=6,
            bg=tm.get("accent_danger"),
            fg="white",
            command=self._randomize_outfit,
        )
        random_btn.grid(row=0, column=1, padx=2, pady=2)

        # 部位选择按钮
        self.part_buttons: Dict[str, tk.Button] = {}
        parts_row1 = ["cap", "hair", "face", "neck"]  # 第0行：第2-5列
        parts_row2 = [
            "coat",
            "belt",
            "pants",
            "shoes",
            "skin",
            "weapon",
        ]  # 第1行：第0-5列

        # 第一行部位（4个：帽子、头发、脸部、胸部）
        for i, part in enumerate(parts_row1):
            btn = tk.Button(
                parts_frame,
                text=PART_NAMES.get(part, part),
                width=6,
                bg=tm.get("button_bg"),
                fg=tm.get("button_fg"),
                command=lambda p=part: self._on_part_select(p),
            )
            btn.grid(row=0, column=i + 2, padx=2, pady=2)
            self.part_buttons[part] = btn

        # 第二行部位（6个：上衣、腰带、裤子、鞋子、皮肤、武器）
        for i, part in enumerate(parts_row2):
            btn = tk.Button(
                parts_frame,
                text=PART_NAMES.get(part, part),
                width=6,
                bg=tm.get("button_bg"),
                fg=tm.get("button_fg"),
                command=lambda p=part: self._on_part_select(p),
            )
            btn.grid(row=1, column=i, padx=2, pady=2)
            self.part_buttons[part] = btn

        # 武器类型下拉框（仅在选择武器部位时显示）
        self.weapon_type_frame = tk.Frame(parts_frame, bg=tm.get("bg_primary"))
        # 默认隐藏，放在第2行

        weapon_type_label = tk.Label(
            self.weapon_type_frame,
            text="武器类型:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        weapon_type_label.pack(side=tk.LEFT, padx=(0, 5))

        self.weapon_type_combo = ttk.Combobox(
            self.weapon_type_frame,
            textvariable=self.weapon_type_var,
            state="readonly",
            width=12,
        )
        self.weapon_type_combo.pack(side=tk.LEFT)
        self.weapon_type_combo.bind("<<ComboboxSelected>>", self._on_weapon_type_change)

        # 装扮列表 - 下拉式
        list_frame = tk.LabelFrame(
            self.left_frame,
            text="装扮列表",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            padx=5,
            pady=5,
        )
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        self.items_var = tk.StringVar()
        self.items_combo = ttk.Combobox(
            list_frame,
            textvariable=self.items_var,
            state="readonly",
            width=28,
            height=15,
        )
        self.items_combo.pack(fill=tk.X, expand=True)
        self.items_combo.bind("<<ComboboxSelected>>", self._on_items_combo_select)

        # 保存装扮索引映射：combo显示文本 -> 原始索引
        self.items_index_map: List[int] = []

        # 当前选择信息
        info_frame = tk.LabelFrame(
            self.left_frame,
            text="当前选择",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            padx=5,
            pady=5,
        )
        info_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        self.selection_icons: Dict[str, tk.Canvas] = {}
        self.selection_icon_images: Dict[str, Optional[ImageTk.PhotoImage]] = {}
        self.selection_labels: Dict[str, tk.Label] = {}

        for i, part in enumerate(PARTS):
            # 每个部位一行，左图标右文字
            row_frame = tk.Frame(info_frame, bg=tm.get("bg_primary"))
            row_frame.grid(row=i, column=0, sticky=tk.W, pady=1)

            # 图标显示区域 (32x32)
            icon_canvas = tk.Canvas(
                row_frame,
                width=32,
                height=32,
                bg=tm.get("grid_bg"),
                highlightthickness=1,
                highlightbackground=tm.get("border"),
            )
            icon_canvas.pack(side=tk.LEFT, padx=(0, 5))
            self.selection_icons[part] = icon_canvas
            self.selection_icon_images[part] = None

            # 文字标签
            label = tk.Label(
                row_frame,
                text=f"{PART_NAMES.get(part, part)}: 未选择",
                bg=tm.get("bg_primary"),
                fg=tm.get("fg_secondary"),
                anchor=tk.W,
            )
            label.pack(side=tk.LEFT)
            self.selection_labels[part] = label

        # 预览图
        preview_frame = tk.LabelFrame(
            self.left_frame,
            text="预览",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            padx=5,
            pady=5,
        )
        preview_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        self.preview_canvas = tk.Canvas(
            preview_frame, bg=tm.get("grid_bg"), width=200, height=200
        )
        self.preview_canvas.pack()

    def _create_right_panel(self):
        """右侧：装扮网格 + 套装选择区"""
        tm = self.theme_manager
        self.right_frame = tk.Frame(
            self.main_frame, bg=tm.get("bg_primary"), padx=5, pady=5
        )
        self.right_frame.grid(row=1, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.right_frame.columnconfigure(0, weight=0)
        self.right_frame.columnconfigure(1, weight=1)
        self.right_frame.rowconfigure(0, weight=1)

        # ========== 创建标签页控件 ==========
        self.icon_notebook = ttk.Notebook(self.right_frame)
        self.icon_notebook.grid(row=0, column=0, sticky=(tk.N, tk.S), padx=(0, 5))

        # ----- 标准图标标签页 -----
        self.standard_frame = tk.Frame(
            self.icon_notebook, bg=tm.get("bg_primary"), padx=5, pady=5
        )
        self.icon_notebook.add(self.standard_frame, text="标准图标")
        self.standard_frame.config(width=660, height=680)
        self.standard_frame.columnconfigure(0, weight=1)
        self.standard_frame.rowconfigure(1, weight=1)

        # 标准图标顶部控制栏
        std_top_control = tk.Frame(self.standard_frame, bg=tm.get("bg_primary"))
        std_top_control.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        tk.Label(
            std_top_control,
            text="筛选:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT)
        self.filter_var = tk.StringVar()
        tk.Entry(
            std_top_control,
            textvariable=self.filter_var,
            width=20,
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            std_top_control,
            text="应用",
            command=self._apply_filter,
            width=6,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT)
        tk.Button(
            std_top_control,
            text="清空",
            command=self._clear_filter,
            width=6,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=5)

        self.display_mode_var = tk.StringVar(value="3d")
        self.mode_btn = tk.Button(
            std_top_control,
            text="模式: 3D",
            command=self._toggle_display_mode,
            width=10,
            bg=tm.get("accent_primary"),
            fg="white",
        )
        self.mode_btn.pack(side=tk.RIGHT, padx=5)

        # 缺失筛选按钮
        self.missing_filter_btn = tk.Button(
            std_top_control,
            text="显示: 全部",
            command=self._toggle_missing_filter,
            width=12,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        )
        self.missing_filter_btn.pack(side=tk.RIGHT, padx=5)

        # 布局切换按钮
        self.layout_btn = tk.Button(
            std_top_control,
            text="布局: 8x8",
            command=self._toggle_layout_mode,
            width=10,
            bg=tm.get("bg_tertiary"),
            fg=tm.get("fg_primary"),
        )
        self.layout_btn.pack(side=tk.RIGHT, padx=5)

        # 标准图标画布
        self.items_canvas = tk.Canvas(
            self.standard_frame, bg=tm.get("grid_bg"), width=640, height=530
        )
        self.items_canvas.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 绑定画布点击事件（只绑定一次，通过tags识别点击项）
        self.items_canvas.bind("<Button-1>", self._on_canvas_click)
        self.items_canvas.bind("<Button-3>", self._on_canvas_right_click)

        # 标准图标分页控制
        std_page_frame = tk.Frame(self.standard_frame, bg=tm.get("bg_primary"))
        std_page_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

        tk.Button(
            std_page_frame,
            text="◀",
            command=self._prev_page,
            width=3,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT)
        self.page_var = tk.StringVar(value="1 / 1")
        tk.Label(
            std_page_frame,
            textvariable=self.page_var,
            width=10,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(
            std_page_frame,
            text="▶",
            command=self._next_page,
            width=3,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT)

        tk.Label(
            std_page_frame,
            text="跳转:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=(20, 5))
        self.page_entry = tk.Entry(
            std_page_frame,
            width=5,
            justify=tk.CENTER,
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        )
        self.page_entry.pack(side=tk.LEFT)
        self.page_entry.insert(0, "1")
        self.page_entry.bind("<Return>", self._goto_page)
        self.goto_btn = tk.Button(
            std_page_frame,
            text="Go",
            command=self._goto_page,
            width=4,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        )
        self.goto_btn.pack(side=tk.LEFT, padx=5)

        # 跳转到当前选中的时装
        tk.Button(
            std_page_frame,
            text="跳转到当前",
            command=self._jump_to_current,
            width=10,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.RIGHT, padx=5)

        # ----- 自定义图标标签页 -----
        self.custom_frame = tk.Frame(
            self.icon_notebook, bg=tm.get("bg_primary"), padx=5, pady=5
        )
        self.icon_notebook.add(self.custom_frame, text="自定义图标")
        self.custom_frame.config(width=660, height=680)
        self.custom_frame.columnconfigure(0, weight=1)
        self.custom_frame.rowconfigure(1, weight=1)  # 第1行是图标显示区域

        # 顶部控制栏：搜索 + 下拉选择
        custom_control_frame = tk.Frame(self.custom_frame, bg=tm.get("bg_primary"))
        custom_control_frame.grid(
            row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5)
        )

        tk.Label(
            custom_control_frame,
            text="搜索IMG:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT)
        self.custom_img_filter_var = tk.StringVar()
        self.custom_img_filter_entry = tk.Entry(
            custom_control_frame,
            textvariable=self.custom_img_filter_var,
            width=20,
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        )
        self.custom_img_filter_entry.pack(side=tk.LEFT, padx=5)
        self.custom_img_filter_entry.bind("<KeyRelease>", self._on_custom_img_filter)

        tk.Label(
            custom_control_frame,
            text="选择IMG:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=(15, 5))
        self.custom_img_combo = ttk.Combobox(
            custom_control_frame, width=40, state="readonly"
        )
        self.custom_img_combo.pack(side=tk.LEFT, padx=5)
        self.custom_img_combo.bind("<<ComboboxSelected>>", self._on_custom_img_selected)

        tk.Button(
            custom_control_frame,
            text="刷新",
            command=self._refresh_custom_img_list,
            width=6,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=5)

        # 自定义图标使用滚动区域
        self.custom_canvas = tk.Canvas(
            self.custom_frame, bg=tm.get("bg_canvas_custom"), width=640, height=560
        )
        self.custom_canvas.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        custom_scrollbar = ttk.Scrollbar(
            self.custom_frame, orient=tk.VERTICAL, command=self.custom_canvas.yview
        )
        custom_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        self.custom_canvas.configure(yscrollcommand=custom_scrollbar.set)

        # 自定义图标内容容器
        self.custom_content_frame = tk.Frame(
            self.custom_canvas, bg=tm.get("bg_canvas_custom")
        )
        self.custom_canvas.create_window(
            (0, 0), window=self.custom_content_frame, anchor=tk.NW
        )
        self.custom_content_frame.bind("<Configure>", self._on_custom_frame_configure)

        # 存储当前自定义图标数据
        self._current_custom_imgs = []  # 所有可用的IMG路径
        self._selected_custom_img = None  # 当前选中的IMG

        # ----- 动画编辑标签页 -----
        self.animation_frame = tk.Frame(
            self.icon_notebook, bg=tm.get("bg_primary"), padx=5, pady=5
        )
        self.icon_notebook.add(self.animation_frame, text="动画")
        self.animation_frame.config(width=660, height=680)
        self.animation_frame.columnconfigure(0, weight=1)
        self.animation_frame.rowconfigure(2, weight=1)  # 预览区域可扩展
        
        # 动画编辑 - 名称输入
        anim_name_frame = tk.Frame(self.animation_frame, bg=tm.get("bg_primary"))
        anim_name_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        tk.Label(
            anim_name_frame,
            text="动画名称:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            width=10,
        ).pack(side=tk.LEFT)
        self.anim_name_var = tk.StringVar(value="自定义动画")
        tk.Entry(
            anim_name_frame,
            textvariable=self.anim_name_var,
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
            width=25,
        ).pack(side=tk.LEFT, padx=5)
        
        # 动画编辑 - 帧序列输入
        anim_frames_frame = tk.Frame(self.animation_frame, bg=tm.get("bg_primary"))
        anim_frames_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        tk.Label(
            anim_frames_frame,
            text="帧序列:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            width=10,
        ).pack(side=tk.LEFT)
        self.anim_frames_var = tk.StringVar(value="0-10")
        tk.Entry(
            anim_frames_frame,
            textvariable=self.anim_frames_var,
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
            width=30,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            anim_frames_frame,
            text="加载当前",
            command=self._load_current_animation,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
            width=10,
        ).pack(side=tk.LEFT, padx=5)
        
        # 动画编辑 - 预览区域
        anim_preview_frame = tk.LabelFrame(
            self.animation_frame,
            text="动画预览",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        anim_preview_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        anim_preview_frame.columnconfigure(0, weight=1)
        
        # 预览画布
        self.anim_canvas_size = 350
        self.anim_preview_canvas = tk.Canvas(
            anim_preview_frame,
            bg=tm.get("grid_bg"),
            width=self.anim_canvas_size,
            height=self.anim_canvas_size,
        )
        self.anim_preview_canvas.pack(pady=5)
        
        # 动画控制区域
        anim_control_frame = tk.Frame(anim_preview_frame, bg=tm.get("bg_primary"))
        anim_control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 速度控制
        tk.Label(
            anim_control_frame,
            text="速度:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT)
        self.anim_speed_var = tk.DoubleVar(value=1.0)
        tk.Scale(
            anim_control_frame,
            from_=0.1,
            to=3.0,
            resolution=0.1,
            orient=tk.HORIZONTAL,
            variable=self.anim_speed_var,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            highlightthickness=0,
            length=120,
        ).pack(side=tk.LEFT, padx=5)
        
        # 状态标签
        self.anim_status_var = tk.StringVar(value="点击播放开始预览")
        tk.Label(
            anim_preview_frame,
            textvariable=self.anim_status_var,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_secondary"),
        ).pack(pady=2)
        
        # 播放控制按钮
        anim_btn_frame = tk.Frame(anim_preview_frame, bg=tm.get("bg_primary"))
        anim_btn_frame.pack(pady=5)
        
        self.anim_play_btn = tk.Button(
            anim_btn_frame,
            text="▶ 播放",
            command=self._toggle_animation_preview,
            bg=tm.get("accent_primary"),
            fg="white",
            width=10,
        )
        self.anim_play_btn.pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            anim_btn_frame,
            text="⏹ 停止",
            command=self._stop_animation_preview,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
            width=10,
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            anim_btn_frame,
            text="⏮ 上一帧",
            command=self._prev_animation_frame,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
            width=10,
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            anim_btn_frame,
            text="下一帧 ⏭",
            command=self._next_animation_frame,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
            width=10,
        ).pack(side=tk.LEFT, padx=5)
        
        # 保存按钮
        anim_save_frame = tk.Frame(self.animation_frame, bg=tm.get("bg_primary"))
        anim_save_frame.grid(row=3, column=0, pady=10)
        
        tk.Button(
            anim_save_frame,
            text="保存动画",
            command=self._save_custom_animation,
            bg="#28a745",
            fg="white",
            width=15,
        ).pack()
        
        # 动画播放状态
        self.anim_preview_state = {
            'is_playing': False,
            'current_idx': 0,
            'after_id': None,
            'frames': [],
        }

        # 标签页切换事件
        self.icon_notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # ========== 套装选择区（保持不变）==========

        # 套装选择区
        self.extra_frame = tk.LabelFrame(
            self.right_frame,
            text="套装选择",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            padx=5,
            pady=5,
        )
        self.extra_frame.grid(
            row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0)
        )
        self.extra_frame.columnconfigure(0, weight=1)
        self.extra_frame.rowconfigure(1, weight=1)

        suit_filter_frame = tk.Frame(self.extra_frame, bg=tm.get("bg_primary"))
        suit_filter_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        tk.Label(
            suit_filter_frame,
            text="筛选:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT)
        self.suit_filter_var = tk.StringVar()
        tk.Entry(
            suit_filter_frame,
            textvariable=self.suit_filter_var,
            width=15,
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            suit_filter_frame,
            text="应用",
            command=self._apply_suit_filter,
            width=5,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT)
        tk.Button(
            suit_filter_frame,
            text="去重",
            command=self._deduplicate_suits,
            width=5,
            bg=tm.get("accent_warning"),
            fg="white",
        ).pack(side=tk.LEFT, padx=(5, 0))

        suit_list_frame = tk.Frame(self.extra_frame, bg=tm.get("bg_primary"))
        suit_list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        suit_list_frame.columnconfigure(0, weight=1)
        suit_list_frame.rowconfigure(0, weight=1)

        self.suit_listbox = tk.Listbox(
            suit_list_frame,
            selectmode=tk.SINGLE,
            width=25,
            bg=tm.get("listbox_bg"),
            fg=tm.get("listbox_fg"),
            selectbackground=tm.get("listbox_select_bg"),
            selectforeground=tm.get("listbox_select_fg"),
        )
        self.suit_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        suit_scrollbar = ttk.Scrollbar(
            suit_list_frame, orient=tk.VERTICAL, command=self.suit_listbox.yview
        )
        suit_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.suit_listbox.configure(yscrollcommand=suit_scrollbar.set)
        self.suit_listbox.bind("<<ListboxSelect>>", self._on_suit_select)
        self.suit_listbox.bind("<Button-3>", self._on_suit_right_click)

        tk.Button(
            self.extra_frame,
            text="应用整套装扮",
            command=self._apply_suit,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

        # 使用 deque 限制大小，防止内存泄漏
        self.item_images: deque = deque(maxlen=100)

    def _create_bottom_panel(self):
        """底部：帧控制"""
        tm = self.theme_manager
        bottom_frame = tk.Frame(
            self.main_frame, bg=tm.get("bg_primary"), padx=5, pady=5
        )
        bottom_frame.grid(
            row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 0)
        )

        # 生成套装按钮（最左侧）
        self.create_suit_btn = tk.Button(
            bottom_frame,
            text="➕ 生成套装",
            command=self._on_create_suit,
            bg=tm.get("accent_primary"),
            fg="white",
            font=("Arial", 9, "bold"),
            width=12,
        )
        self.create_suit_btn.pack(side=tk.LEFT, padx=(0, 15))

        tk.Button(
            bottom_frame,
            text="◀",
            width=3,
            command=self._prev_frame,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT)
        self.frame_var = tk.StringVar(value="0")
        self.frame_entry = tk.Entry(
            bottom_frame,
            textvariable=self.frame_var,
            width=5,
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
            justify=tk.CENTER,
        )
        self.frame_entry.pack(side=tk.LEFT, padx=5)
        self.frame_entry.bind("<Return>", self._on_frame_entry)
        tk.Button(
            bottom_frame,
            text="▶",
            width=3,
            command=self._next_frame,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT)

        tk.Label(
            bottom_frame,
            text="  动作:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=(15, 0))
        self.action_var = tk.StringVar(value="待机动画")
        self.action_combo = ttk.Combobox(
            bottom_frame,
            textvariable=self.action_var,
            values=[],
            width=15,
            state="readonly",
        )
        self.action_combo.pack(side=tk.LEFT, padx=5)
        self.action_combo.bind("<<ComboboxSelected>>", self._on_action_change)

        # 编辑动画按钮 - 切换到动画标签页
        tk.Button(
            bottom_frame,
            text="编辑动画",
            command=lambda: self.icon_notebook.select(2),  # 切换到动画标签页
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=5)

        self.play_all_frames = tk.BooleanVar(value=False)
        tk.Checkbutton(
            bottom_frame,
            text="全帧",
            variable=self.play_all_frames,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            selectcolor=tm.get("entry_bg"),
        ).pack(side=tk.LEFT, padx=(15, 0))

        self.play_btn = tk.Button(
            bottom_frame,
            text="▶ 播放",
            command=self._toggle_animation,
            width=10,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        )
        self.play_btn.pack(side=tk.LEFT, padx=(15, 0))

        # f层处理开关
        self.f_layer_var = tk.BooleanVar(value=self.process_f_layers)
        self.f_layer_check = tk.Checkbutton(
            bottom_frame,
            text="f层处理",
            variable=self.f_layer_var,
            command=self._toggle_f_layer_processing,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            selectcolor=tm.get("entry_bg"),
        )
        self.f_layer_check.pack(side=tk.LEFT, padx=(15, 0))

        # g层（半透明阴影层）处理开关和不透明度滑块
        g_frame = tk.Frame(bottom_frame, bg=tm.get("bg_primary"))
        g_frame.pack(side=tk.LEFT, padx=(15, 0))

        self.g_layer_var = tk.BooleanVar(value=self.process_g_layers)
        self.g_layer_check = tk.Checkbutton(
            g_frame,
            text="g层",
            variable=self.g_layer_var,
            command=self._toggle_g_layer_processing,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            selectcolor=tm.get("entry_bg"),
        )
        self.g_layer_check.pack(side=tk.LEFT)

        self.g_layer_opacity_var = tk.IntVar(value=self.g_layer_opacity)
        self.g_layer_scale = tk.Scale(
            g_frame,
            from_=-100,
            to=100,
            resolution=5,
            orient=tk.HORIZONTAL,
            variable=self.g_layer_opacity_var,
            command=self._on_g_layer_opacity_changed,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            highlightthickness=0,
            length=100,
            showvalue=0,
        )
        self.g_layer_scale.pack(side=tk.LEFT, padx=(5, 0))

        self.g_layer_label = tk.Label(
            g_frame,
            text=f"{self.g_layer_opacity:+d}%",  # 显示带符号的百分比，如 "+0%" 或 "-50%"
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            font=("Arial", 8),
            width=5,
        )
        self.g_layer_label.pack(side=tk.LEFT)

        # h层（深层阴影层）处理开关和不透明度滑块
        h_frame = tk.Frame(bottom_frame, bg=tm.get("bg_primary"))
        h_frame.pack(side=tk.LEFT, padx=(10, 0))

        self.h_layer_var = tk.BooleanVar(value=self.process_h_layers)
        self.h_layer_check = tk.Checkbutton(
            h_frame,
            text="h层",
            variable=self.h_layer_var,
            command=self._toggle_h_layer_processing,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            selectcolor=tm.get("entry_bg"),
        )
        self.h_layer_check.pack(side=tk.LEFT)

        self.h_layer_opacity_var = tk.IntVar(value=self.h_layer_opacity)
        self.h_layer_scale = tk.Scale(
            h_frame,
            from_=-100,
            to=100,
            resolution=5,
            orient=tk.HORIZONTAL,
            variable=self.h_layer_opacity_var,
            command=self._on_h_layer_opacity_changed,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            highlightthickness=0,
            length=100,
            showvalue=0,
        )
        self.h_layer_scale.pack(side=tk.LEFT, padx=(5, 0))

        self.h_layer_label = tk.Label(
            h_frame,
            text=f"{self.h_layer_opacity:+d}%",  # 显示带符号的百分比，如 "+0%" 或 "-50%"
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            font=("Arial", 8),
            width=5,
        )
        self.h_layer_label.pack(side=tk.LEFT)

        # 预览背景切换按钮
        bg_frame = tk.Frame(bottom_frame, bg=tm.get("bg_primary"))
        bg_frame.pack(side=tk.LEFT, padx=(15, 0))

        tk.Label(
            bg_frame,
            text="背景:",
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            font=("Arial", 9),
        ).pack(side=tk.LEFT)

        self.bg_var = tk.StringVar(value=self.preview_bg_type)
        bg_options = [
            ("灰", "gray"),
            ("黑", "black"),
            ("白", "white"),
            ("透明", "checkerboard"),
        ]
        for text, value in bg_options:
            tk.Radiobutton(
                bg_frame,
                text=text,
                variable=self.bg_var,
                value=value,
                command=self._on_preview_bg_changed,
                bg=tm.get("bg_primary"),
                fg=tm.get("fg_primary"),
                selectcolor=tm.get("entry_bg"),
                font=("Arial", 8),
            ).pack(side=tk.LEFT, padx=(2, 0))

        # 强制显示隐藏部位开关
        self.force_show_var = tk.BooleanVar(value=self.force_show_hidden)
        self.force_show_check = tk.Checkbutton(
            bottom_frame,
            text="强制显示隐藏",
            variable=self.force_show_var,
            command=self._toggle_force_show_hidden,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
            selectcolor=tm.get("entry_bg"),
        )
        self.force_show_check.pack(side=tk.LEFT, padx=(10, 0))

    def _select_npk_dir(self):
        """选择NPK目录"""
        current_dir = self.npk_dir_var.get()
        if not Path(current_dir).exists():
            current_dir = r"NPK"

        selected = filedialog.askdirectory(
            title="选择NPK目录",
            initialdir=current_dir if Path(current_dir).exists() else ".",
        )
        if selected:
            npk_path = Path(selected)
            if not npk_path.exists():
                messagebox.showerror("错误", "选择的目录不存在")
                return

            if not list(npk_path.glob("*.npk")):
                if not messagebox.askyesno(
                    "警告",
                    f"该目录中没有找到NPK文件。\n路径: {selected}\n\n是否仍要使用此目录？",
                ):
                    return

            self.npk_dir_var.set(str(npk_path))
            self._save_npk_cache(str(npk_path))
            self.loader.base_path = npk_path
            self.icon_loader.set_npk_path(str(npk_path))

            # 检查是否需要重新构建索引（目录变更）
            current_indexed_dir = getattr(self, "_indexed_npk_dir", None)
            dir_changed = current_indexed_dir != str(npk_path)

            print(
                f"[DEBUG] 检查IMG索引状态: _img_index_built={self._img_index_built}, dir_changed={dir_changed}"
            )
            if not self._img_index_built or dir_changed:
                if dir_changed:
                    print(f"[DEBUG] NPK目录变更: {current_indexed_dir} -> {npk_path}")
                    self._img_index_built = False  # 重置状态

                self.status_label.config(text="正在构建IMG索引...")
                self.root.update()
                print("[DEBUG] 开始构建IMG索引...")
                try:
                    self.icon_loader.build_img_index()
                    self._img_index_built = True
                    self._indexed_npk_dir = str(npk_path)  # 记录已索引的目录
                    print(
                        f"[INFO] IMG索引构建完成: {len(self.icon_loader.img_index)} 个IMG"
                    )
                    self.status_label.config(
                        text=f"IMG索引构建完成: {len(self.icon_loader.img_index)} 个IMG"
                    )
                except Exception as e:
                    print(f"[ERROR] IMG索引构建失败: {e}")
                    self.status_label.config(text=f"IMG索引构建失败")
                    messagebox.showerror("错误", f"构建IMG索引失败:\n{e}")
            else:
                print("[DEBUG] IMG索引已构建且目录未变更，跳过")

            if self.loader.current_job:
                self._load_job()
            self.status_label.config(text=f"NPK目录已更新: {npk_path}")

    def _check_missing_npk(self):
        """检查所有职业缺失的文件（装备NPK、图标NPK、装扮表）"""
        npk_dir = Path(self.npk_dir_var.get())
        if not npk_dir.exists():
            messagebox.showerror("错误", "NPK目录不存在")
            return

        result_window = tk.Toplevel(self.root)
        result_window.title("文件检查结果")
        result_window.transient(self.root)
        
        # 设置大小并居中
        self._center_window(result_window, 700, 600)

        tm = self.theme_manager
        result_window.configure(bg=tm.get("bg_primary"))

        text_frame = tk.Frame(result_window, bg=tm.get("bg_primary"), padx=10, pady=10)
        text_frame.pack(fill=tk.BOTH, expand=True)

        text_widget = tk.Text(
            text_frame,
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        )
        scrollbar = tk.Scrollbar(
            text_frame,
            orient=tk.VERTICAL,
            command=text_widget.yview,
            bg=tm.get("bg_tertiary"),
        )
        text_widget.configure(yscrollcommand=scrollbar.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 配置标签样式
        text_widget.tag_configure("header", font=("Microsoft YaHei", 11, "bold"))
        text_widget.tag_configure(
            "category",
            font=("Microsoft YaHei", 10, "bold"),
            foreground=tm.get("label_info"),
        )
        text_widget.tag_configure("missing", foreground=tm.get("label_error"))
        text_widget.tag_configure("ok", foreground=tm.get("label_success"))
        text_widget.tag_configure("summary", font=("Microsoft YaHei", 10, "bold"))
        text_widget.tag_configure("warning", foreground=tm.get("label_warning"))

        total_missing_equipment = 0
        total_missing_icon = 0
        # 注：不再检查txt装扮表文件，只使用JSON格式

        for job_key, config in JOB_CONFIG.items():
            job_name = config["name"]
            folder = config["folder"]

            text_widget.insert(tk.END, f"\n【{job_name} ({job_key})】\n", "header")

            # 1. 检查装备NPK文件
            text_widget.insert(tk.END, "  [装备NPK文件]\n", "category")
            missing_equipment_parts = []
            for part in PARTS:
                if "_at" in folder:
                    npk_name = f"sprite_character_{folder.replace('_at', '')}_atequipment_avatar_{part}.npk"
                else:
                    npk_name = f"sprite_character_{folder}_equipment_avatar_{part}.npk"

                if not (npk_dir / npk_name).exists():
                    missing_equipment_parts.append((part, npk_name))

            if missing_equipment_parts:
                text_widget.insert(
                    tk.END, f"    缺失 {len(missing_equipment_parts)} 个:\n", "missing"
                )
                for part, npk_name in missing_equipment_parts:
                    text_widget.insert(tk.END, f"      - {part}: {npk_name}\n")
                total_missing_equipment += len(missing_equipment_parts)
            else:
                text_widget.insert(tk.END, "    ✓ 齐全\n", "ok")

            # 2. 检查图标NPK文件
            text_widget.insert(tk.END, "  [图标NPK文件]\n", "category")
            icon_npk_name = self.suit_loader.get_icon_npk_name(job_key)
            if icon_npk_name:
                icon_npk_path = npk_dir / f"{icon_npk_name}.NPK"
                if not icon_npk_path.exists():
                    text_widget.insert(
                        tk.END, f"    缺失: {icon_npk_name}.NPK\n", "missing"
                    )
                    total_missing_icon += 1
                else:
                    text_widget.insert(tk.END, f"    ✓ {icon_npk_name}.NPK\n", "ok")
            else:
                text_widget.insert(tk.END, "    未配置图标NPK映射\n", "warning")

        # 汇总
        text_widget.insert(tk.END, f"\n{'='*60}\n", "summary")
        text_widget.insert(tk.END, "【检查结果汇总】\n", "summary")

        total_missing = total_missing_equipment + total_missing_icon

        if total_missing > 0:
            text_widget.insert(tk.END, f"总计缺失: {total_missing} 个文件\n", "summary")
            text_widget.insert(tk.END, f"  - 装备NPK: {total_missing_equipment} 个\n")
            text_widget.insert(tk.END, f"  - 图标NPK: {total_missing_icon} 个\n")
        else:
            text_widget.insert(tk.END, "✓ 所有文件齐全！\n", "ok")

        text_widget.configure(state=tk.DISABLED)
        tk.Button(
            result_window,
            text="关闭",
            command=result_window.destroy,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(pady=10)

    def _show_job_select_dialog(self):
        """显示职业选择对话框"""
        tm = self.theme_manager

        dialog = tk.Toplevel(self.root)
        dialog.title("选择职业")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=tm.get("bg_primary"))
        
        # 设置大小并居中
        self._center_window(dialog, 400, 350)
        dialog.resizable(False, False)

        # 标题
        tk.Label(
            dialog,
            text="选择职业",
            font=("Microsoft YaHei", 12, "bold"),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(pady=10)

        # 职业网格容器
        grid_frame = tk.Frame(dialog, bg=tm.get("bg_primary"), padx=10, pady=5)
        grid_frame.pack(fill=tk.BOTH, expand=True)

        # 创建职业按钮网格 (4列)
        jobs = list(JOB_CONFIG.items())  # [(key, config), ...]
        cols = 4

        for idx, (job_key, job_config) in enumerate(jobs):
            row = idx // cols
            col = idx % cols

            job_name = job_config["name"]
            job_code = job_config["code"]

            # 创建职业按钮（后续可以改为图标）
            btn = tk.Button(
                grid_frame,
                text=f"{job_name}\n({job_code.upper()})",
                width=10,
                height=3,
                bg=tm.get("button_bg"),
                fg=tm.get("button_fg"),
                command=lambda j=job_name, d=dialog: self._on_job_select_from_dialog(
                    j, d
                ),
            )
            btn.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

        # 关闭按钮
        tk.Button(
            dialog,
            text="关闭",
            width=10,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
            command=dialog.destroy,
        ).pack(pady=10)

        # 居中显示
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

    def _on_job_select_from_dialog(self, job_name: str, dialog: tk.Toplevel):
        """从对话框选择职业"""
        self.job_var.set(job_name)
        dialog.destroy()
        self._load_job()

    def _load_job(self):
        """加载职业"""
        job_str = self.job_var.get()
        if not job_str:
            messagebox.showwarning("提示", "请先选择职业")
            return

        npk_dir = self.npk_dir_var.get()
        if not npk_dir or not Path(npk_dir).exists():
            messagebox.showerror("错误", "NPK目录无效")
            return

        self.loader.base_path = Path(npk_dir)
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""
        job_name = JOB_CONFIG.get(job_key, {}).get("name", job_key)

        self.status_label.config(text=f"正在加载: {job_name}...")
        self.root.update()

        # 使用当前武器类型加载职业
        weapon_type = self.weapon_type_var.get()
        if self.loader.load_job(job_key):
            self.selected_parts.clear()
            self.missing_items.clear()
            self.current_page = 0
            self.filter_var.set("")

            # 清除缓存（职业切换，装备数据改变）
            self.cache.f_layer.clear()
            self.cache.g_layer.clear()
            self.cache.h_layer.clear()
            self.cache.frame.clear()
            self.cache.photo.clear()
            self._preview_image_id = None
            self.cache.thumbnail.clear()  # 清除缩略图缓存
            self.cache.thumbnail_photo.clear()  # 清除PhotoImage缓存
            self.cache.icon_status.clear()  # 清除图标状态缓存

            # 管理NPK资源：释放非标准NPK，加载当前职业标准NPK
            self._manage_npk_resources(job_key)

            loaded_parts = len(self.loader.part_options)
            total_options = sum(len(opts) for opts in self.loader.part_options.values())
            self.status_label.config(
                text=f"已加载: {job_name} | {loaded_parts}个部位 | 共{total_options}个装扮"
            )

            for part in PARTS:
                if part in self.loader.part_options and self.loader.part_options[part]:
                    self.selected_parts[part] = 0

            actions = self.animation_loader.get_actions(job_name)
            if actions:
                self.action_combo["values"] = actions
                self.action_var.set(actions[0])
                self.current_animation_frames = self.animation_loader.get_frames(
                    job_name, actions[0]
                )
            else:
                self.action_combo["values"] = ["待机动画", "行走", "跑步"]
                self.action_var.set("待机动画")
                self.current_animation_frames = list(range(161))

            self.suit_loader.load_suits_for_job(job_key)
            self._load_suit_list()

            self.animation_frame_index = 0
            self.current_frame = (
                self.current_animation_frames[0] if self.current_animation_frames else 0
            )
            self.frame_var.set(str(self.current_frame))

            start_part = (
                "coat"
                if "coat" in self.loader.part_options
                else ("skin" if "skin" in self.loader.part_options else None)
            )
            if start_part:
                self._on_part_select(start_part)

            self._update_selection_display()
            self._update_preview()

            # 重置武器类型为新职业的默认第一个类型
            self._reset_weapon_type_for_job(job_key)

            # 后台预加载图标缓存
            self._preload_icons_async(job_key)
        else:
            messagebox.showerror("错误", "加载失败")

    def _manage_npk_resources(self, job_key: str):
        """管理NPK资源：释放非标准NPK，加载当前职业标准NPK"""
        # 获取当前职业的标准NPK名称
        standard_npk = self.suit_loader.get_icon_npk_name(job_key)
        if not standard_npk:
            return

        # 释放已加载的非标准NPK（不在标准NPK列表中的）
        npks_to_unload = []
        for npk_name in list(self.icon_loader.loaded_icon_npks.keys()):
            if (
                npk_name != standard_npk
                and npk_name not in self.icon_loader.standard_npks
            ):
                npks_to_unload.append(npk_name)

        for npk_name in npks_to_unload:
            self.icon_loader.unload_npk(npk_name)
            print(f"[NPK] 释放资源: {npk_name}")

        # 加载当前职业的标准NPK
        if standard_npk not in self.icon_loader.loaded_icon_npks:
            self.icon_loader.load_icon_npk(standard_npk)
            print(f"[NPK] 加载标准NPK: {standard_npk}")

    def _preload_icons_async(self, job_key: str):
        """后台异步预加载图标缓存"""
        import threading

        def preload():
            try:
                npk_name = self.suit_loader.get_icon_npk_name(job_key)
                if not npk_name:
                    return

                # 确保NPK已加载
                if not self.icon_loader.load_icon_npk(npk_name):
                    return

                npk = self.icon_loader.loaded_icon_npks.get(npk_name)
                if not npk:
                    return

                total_cached = 0
                total_frames_all = 0

                for part in PARTS:
                    img_name = self.suit_loader.get_icon_img_name(job_key, part)
                    if not img_name:
                        continue

                    img_file = next((f for f in npk.files if img_name in f.name), None)
                    if not img_file:
                        continue

                    total_frames = len(img_file.to_img().images)
                    total_frames_all += total_frames

                    # 预加载所有帧到缓存
                    for frame_idx in range(total_frames):
                        cache_path = self.icon_loader._get_cache_path(
                            npk_name, img_name, frame_idx
                        )
                        if not cache_path.exists():
                            icon = self.icon_loader.get_icon(
                                npk_name, img_name, frame_idx, (56, 56)
                            )
                            if icon:
                                total_cached += 1

                if total_cached > 0:
                    print(
                        f"[Preload] 新增缓存 {total_cached} 个图标，总计 {total_frames_all} 个"
                    )
                    # 更新状态栏显示缓存信息
                    self.root.after(
                        0,
                        lambda: self.status_label.config(
                            text=f"{self.status_label.cget('text')} | 图标缓存完成"
                        ),
                    )

            except Exception as e:
                print(f"[Preload] Error: {e}")

        thread = threading.Thread(target=preload, daemon=True)
        thread.start()

    def _preload_thumbnails_async(self, job_key: str, part: str, page: int = 0):
        """后台异步预加载3D缩略图缓存 - 优化版：并行加载

        Args:
            job_key: 职业key
            part: 部位
            page: 要预加载的页码，默认0（第一页）
        """
        import threading

        def preload():
            try:
                options = self.loader.part_options.get(part, [])
                if not options:
                    return

                # 计算当前页的范围
                start_idx = page * self.items_per_page
                end_idx = min(start_idx + self.items_per_page, len(options))

                # 根据布局模式确定缩略图大小
                if self.grid_layout_mode == "8x8":
                    thumb_size = (56, 56)
                else:
                    thumb_size = (112, 112)

                # 收集需要加载的索引
                # 缓存键包含job_key和武器类型，避免不同职业/武器类型的缓存冲突
                weapon_type = self.weapon_type_var.get() if part == "weapon" else ""
                indices_to_load = []
                for idx in range(start_idx, end_idx):
                    cache_key = (job_key, part, idx, thumb_size, weapon_type)
                    if cache_key not in self.cache.thumbnail:
                        indices_to_load.append(idx)

                if not indices_to_load:
                    return

                # 并行生成缩略图
                def generate_single(idx: int) -> Tuple[int, Optional[Image.Image]]:
                    """生成单个缩略图"""
                    try:
                        thumb = self.loader.generate_thumbnail(
                            part, idx, size=thumb_size, job_key=job_key
                        )
                        return (idx, thumb)
                    except Exception:
                        return (idx, None)

                cached_count = 0
                max_workers = min(
                    4, len(indices_to_load)
                )  # 预加载用较少线程避免资源竞争

                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_idx = {
                        executor.submit(generate_single, idx): idx
                        for idx in indices_to_load
                    }

                    for future in as_completed(future_to_idx):
                        idx, thumb = future.result()
                        if thumb:
                            cache_key = (job_key, part, idx, thumb_size, weapon_type)
                            # 线程安全地存入缓存
                            if (
                                len(self.cache.thumbnail)
                                >= self.cache.thumbnail.max_size
                            ):
                                keys_to_remove = list(self.cache.thumbnail.keys())[
                                    : self.cache.thumbnail.max_size // 10
                                ]
                                for key in keys_to_remove:
                                    self.cache.thumbnail.pop(key, None)
                            self.cache.thumbnail[cache_key] = thumb
                            cached_count += 1

                if cached_count > 0:
                    print(
                        f"[Preload] 预加载 {part} 第{page+1}页缩略图: {cached_count} 个"
                    )

            except Exception as e:
                print(f"[Preload] 缩略图预加载错误: {e}")

        thread = threading.Thread(target=preload, daemon=True)
        thread.start()

    def _on_part_select(self, part: str):
        """选择部位"""
        self.current_part = part
        self.current_page = 0
        self.filter_var.set("")
        self.custom_img_filter_var.set("")  # 清空自定义图标搜索

        # 根据当前标签页加载内容
        current_tab = self.icon_notebook.index("current")
        if current_tab == 0:  # 标准图标页
            self._load_items_grid(part)
        elif current_tab == 1:  # 自定义图标页
            self._refresh_custom_img_list()  # 刷新IMG下拉列表
        elif current_tab == 2:  # 动画页
            self._load_current_animation()  # 刷新动画

        tm = self.theme_manager
        for p, btn in self.part_buttons.items():
            if hasattr(btn, "config"):
                btn.config(
                    bg=tm.get("accent_primary") if p == part else tm.get("button_bg"),
                    fg="white" if p == part else tm.get("button_fg"),
                )

        # 处理武器类型下拉框的显示/隐藏
        if part == "weapon":
            self._update_weapon_type_combo()
            self.weapon_type_frame.grid(
                row=2, column=0, columnspan=6, pady=(5, 0), sticky=tk.W
            )
            # 确保武器数据已加载（切换职业后可能需要重新加载）
            self._reload_weapon_npk()

        self._load_items_list(part)
        self._load_items_grid(part)

    def _load_items_list(self, part: str):
        """加载装扮到下拉列表"""
        job_str = self.job_var.get()
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""

        options = self.loader.part_options.get(part, [])
        display_items = []
        self.items_index_map = []

        for i, opt in enumerate(options):
            display_code = opt[0]
            name = self.suit_loader.get_item_name(job_key, part, display_code)
            display_text = (
                f"[{i}] {display_code} - {name}" if name else f"[{i}] {display_code}"
            )
            display_items.append(display_text)
            self.items_index_map.append(i)

        self.items_combo["values"] = display_items

        if part in self.selected_parts:
            idx = self.selected_parts[part]
            if idx < len(display_items):
                self.items_combo.current(idx)

    def _update_weapon_type_combo(self):
        """更新武器类型下拉框内容"""
        job_str = self.job_var.get()
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""

        # 获取当前职业的武器类型映射
        weapon_types = WEAPON_TYPES.get(job_key, {})
        if not weapon_types:
            # 默认使用鬼剑士的武器类型
            weapon_types = WEAPON_TYPES.get("swordman_male", {})

        # 构建下拉框选项列表 (显示名称, 实际值)
        combo_values = []
        type_keys = list(weapon_types.keys())
        for type_key in type_keys:
            type_name = weapon_types[type_key]
            combo_values.append(f"{type_name} ({type_key})")

        self.weapon_type_combo["values"] = combo_values

        # 设置当前选中项 - 使用索引避免影响绑定的变量
        current_type = self.weapon_type_var.get()
        if current_type in weapon_types:
            # 通过索引设置选中项，而不是使用 set() 方法
            index = type_keys.index(current_type)
            self.weapon_type_combo.current(index)
        elif combo_values:
            # 默认选中第一个
            first_type = type_keys[0]
            self.weapon_type_var.set(first_type)
            self.weapon_type_combo.current(0)

    def _reset_weapon_type_for_job(self, job_key: str):
        """切换职业后重置武器类型为新职业的默认类型"""
        # 获取新职业的武器类型
        weapon_types = WEAPON_TYPES.get(job_key, {})
        if not weapon_types:
            weapon_types = WEAPON_TYPES.get("swordman_male", {})

        if weapon_types:
            # 重置为第一个武器类型
            first_type = list(weapon_types.keys())[0]
            self.weapon_type_var.set(first_type)

            # 更新下拉框显示
            self._update_weapon_type_combo()
            print(f"[Weapon] 职业切换: {job_key}，重置武器类型为: {first_type}")
            # 重新加载武器NPK
            self._reload_weapon_npk()

            print(f"[Weapon] 职业切换后重置武器类型: {first_type}")

    def _on_weapon_type_change(self, event=None):
        """武器类型切换事件"""
        selected = self.weapon_type_combo.get()
        if not selected:
            return

        # 从显示文本中提取实际的武器类型key (格式: "名称 (key)")
        match = re.search(r"\((\w+)\)$", selected)
        if match:
            new_type = match.group(1)
            if new_type != self.weapon_type_var.get():
                self.weapon_type_var.set(new_type)
                # 重新加载武器NPK
                self._reload_weapon_npk()

    def _reload_weapon_npk(self):
        """重新加载武器NPK"""
        job_str = self.job_var.get()
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""
        if not job_key:
            return

        weapon_type = self.weapon_type_var.get()
        npk_path = self.loader.base_path / self.loader.get_npk_filename(
            job_key, "weapon", weapon_type
        )

        if npk_path.exists():
            try:
                with open(npk_path, "rb") as f:
                    npk = NPK.open(f)
                    npk.load_all()
                    self.loader.loaded_npks["weapon"] = npk
                    self.loader._process_part_options()
                    print(f"[Weapon] 已加载武器类型: {weapon_type} ({npk_path.name})")

                    # 清除武器相关的选中状态和缓存
                    if "weapon" in self.selected_parts:
                        del self.selected_parts["weapon"]
                    self._clear_weapon_cache()

                    # 刷新武器列表（无论当前是否选中武器部位）
                    self._load_items_list("weapon")
                    self._load_items_grid("weapon")

                    # 更新选择显示和预览
                    self._update_selection_display()
                    self._update_preview()
            except Exception as e:
                print(f"[Error] 加载武器NPK失败: {e}")
        else:
            print(f"[Warn] 武器NPK文件不存在: {npk_path}")

    def _clear_weapon_cache(self):
        """清除武器相关的缓存"""
        # 清除帧缓存中的武器图层
        keys_to_remove = []
        for key in self.cache.frame.keys():
            if isinstance(key, tuple) and len(key) >= 2:
                # 假设缓存键格式包含部位信息
                if "weapon" in str(key):
                    keys_to_remove.append(key)
        for key in keys_to_remove:
            del self.cache.frame[key]

        # 清除缩略图缓存中的武器项
        # 缓存键格式: (job_key, part, idx, thumb_size, weapon_type)
        thumb_keys = [
            k for k in self.cache.thumbnail.keys() if len(k) >= 2 and k[1] == "weapon"
        ]
        for key in thumb_keys:
            del self.cache.thumbnail[key]

        # 清除PhotoImage缓存
        photo_keys = [
            k
            for k in self.cache.thumbnail_photo.keys()
            if len(k) >= 2 and k[1] == "weapon"
        ]
        for key in photo_keys:
            del self.cache.thumbnail_photo[key]

        # 清除图标状态缓存
        status_keys = [
            k for k in self.cache.icon_status.keys() if len(k) >= 2 and k[1] == "weapon"
        ]
        for key in status_keys:
            del self.cache.icon_status[key]

        print(f"[Weapon] 已清除武器缓存")

    def _on_items_combo_select(self, event=None):
        """下拉列表选择事件"""
        if not self.current_part:
            return
        combo_idx = self.items_combo.current()
        if combo_idx >= 0 and combo_idx < len(self.items_index_map):
            original_idx = self.items_index_map[combo_idx]
            self._on_item_select(original_idx)

    def _load_items_grid(self, part: str):
        """加载8x8装扮网格"""
        tm = self.theme_manager
        self.items_canvas.delete("all")
        self.item_images.clear()

        job_str = self.job_var.get()
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""

        # 根据布局模式计算尺寸
        padding = 8
        if self.grid_layout_mode == "8x8":
            items_per_row = 8
            item_size = 72  # 8x8 布局，较小尺寸
        else:
            items_per_row = 4
            item_size = 144  # 4x4 布局，较大尺寸 (约 2x)

        page_items = []

        if self.show_icons:
            # 优化：先获取帧映射信息，再按需加载当前页图标
            frame_mapping = self._get_icon_frame_mapping(job_key, part)
            total_frames = frame_mapping["total_frames"]
            frame_to_code = frame_mapping["frame_to_code"]

            # 构建帧索引列表
            all_frame_indices = list(range(total_frames))

            # 应用缺失筛选：只保留没有对应时装的帧
            if self.show_missing_only:
                all_frame_indices = [
                    idx for idx in all_frame_indices if idx not in frame_to_code
                ]

            total_filtered = len(all_frame_indices)
            self.total_pages = max(
                1, (total_filtered + self.items_per_page - 1) // self.items_per_page
            )
            self.current_page = min(self.current_page, self.total_pages - 1)
            self.page_var.set(f"{self.current_page + 1} / {self.total_pages}")

            # 只加载当前页需要的帧
            start_idx = self.current_page * self.items_per_page
            end_idx = min(start_idx + self.items_per_page, total_filtered)
            page_frame_indices = all_frame_indices[start_idx:end_idx]

            # 批量加载当前页图标
            page_items = self._load_icon_items_by_frames(
                job_key, part, page_frame_indices, frame_to_code
            )
        else:
            options = self.loader.part_options.get(part, [])
            filter_text = self.filter_var.get().lower()

            filtered = [
                (idx, opt)
                for idx, opt in enumerate(options)
                if not filter_text or filter_text in opt[0].lower()
            ]

            # 应用缺失筛选：只保留没有对应图标的时装
            if self.show_missing_only:
                filtered = [
                    (idx, opt)
                    for idx, opt in filtered
                    if self._check_has_icon(job_key, part, opt[0]) != "yes"
                ]

            self.filtered_options = filtered

            total_filtered = len(filtered)
            self.total_pages = max(
                1, (total_filtered + self.items_per_page - 1) // self.items_per_page
            )
            self.current_page = min(self.current_page, self.total_pages - 1)
            self.page_var.set(f"{self.current_page + 1} / {self.total_pages}")

            start_idx = self.current_page * self.items_per_page
            end_idx = min(start_idx + self.items_per_page, total_filtered)

            # 根据布局模式调整缩略图大小
            if self.grid_layout_mode == "8x8":
                thumb_size = (56, 56)
            else:
                thumb_size = (112, 112)  # 4x4 布局，缩略图更大

            # 获取武器类型（如果是武器部位）用于缓存键
            weapon_type = self.weapon_type_var.get() if part == "weapon" else ""

            for filtered_idx in range(start_idx, end_idx):
                original_idx, option = filtered[filtered_idx]
                display_code = option[0]

                # ========== 优化: 使用缩略图缓存 ==========
                # 缓存键包含job_key和武器类型，避免不同职业/武器类型的缓存冲突
                cache_key = (job_key, part, original_idx, thumb_size, weapon_type)

                # L1: 检查PhotoImage缓存（最快）
                photo = self.cache.thumbnail_photo.get(cache_key)
                if photo is None:
                    # L2: 检查PIL缩略图缓存
                    thumb = self.cache.thumbnail.get(cache_key)
                    if thumb is None:
                        # L3: 生成缩略图（传入job_key以使用职业特定帧号）
                        thumb = self.loader.generate_thumbnail(
                            part, original_idx, size=thumb_size, job_key=job_key
                        )
                        if thumb is None:
                            thumb = Image.new("RGBA", thumb_size, (200, 200, 200, 128))

                        # 存入PIL缓存
                        if len(self.cache.thumbnail) >= self.cache.thumbnail.max_size:
                            keys_to_remove = list(self.cache.thumbnail.keys())[
                                : self.cache.thumbnail.max_size // 10
                            ]
                            for key in keys_to_remove:
                                del self.cache.thumbnail[key]

                        self.cache.thumbnail[cache_key] = thumb

                    # 转换为PhotoImage并缓存
                    photo = ImageTk.PhotoImage(thumb)
                    if (
                        len(self.cache.thumbnail_photo)
                        >= self.cache.thumbnail_photo.max_size
                    ):
                        keys_to_remove = list(self.cache.thumbnail_photo.keys())[
                            : self.cache.thumbnail_photo.max_size // 10
                        ]
                        for key in keys_to_remove:
                            del self.cache.thumbnail_photo[key]
                    self.cache.thumbnail_photo[cache_key] = photo

                icon_status = self._check_has_icon(job_key, part, display_code)
                border_color = (
                    "#999999"
                    if icon_status == "yes"
                    else ("#ffcc00" if icon_status == "no_frame" else "#cc0000")
                )
                page_items.append(
                    (
                        original_idx,
                        display_code,
                        photo,  # 直接返回PhotoImage
                        True,
                        border_color,
                        None,
                        filtered_idx,
                    )
                )

        # 缓存主题颜色值，避免重复字典查找
        grid_bg = tm.get("grid_bg")
        accent_primary = tm.get("accent_primary")
        border_highlight = tm.get("border_highlight")
        label_error = tm.get("label_error")
        fg_primary = tm.get("fg_primary")
        item_code_normal = tm.get("item_code_normal")

        for i, item_data in enumerate(page_items):
            index, display_text, photo, has_equip, border_color, frame_idx = item_data[
                :6
            ]
            filtered_idx = item_data[6] if len(item_data) > 6 else i

            row, col = i // items_per_row, i % items_per_row
            x, y = padding + col * (item_size + padding), padding + row * (
                item_size + padding
            )

            # photo 现在已经是 PhotoImage（从缓存直接获取）
            self.item_images.append(photo)

            is_selected = self.selected_parts.get(part) == index

            if is_selected:
                # 选中状态：先绘制外层边框（显示缺失状态），再绘制内层蓝色背景
                self.items_canvas.create_rectangle(
                    x,
                    y,
                    x + item_size,
                    y + item_size,
                    fill=grid_bg,
                    outline=border_color if has_equip else label_error,
                    width=3,
                )
                # 内缩4像素绘制蓝色选中背景
                inner_pad = 4
                self.items_canvas.create_rectangle(
                    x + inner_pad,
                    y + inner_pad,
                    x + item_size - inner_pad,
                    y + item_size - inner_pad,
                    fill=accent_primary,
                    outline=border_highlight,
                    width=2,
                )
            else:
                # 未选中状态：正常绘制
                self.items_canvas.create_rectangle(
                    x,
                    y,
                    x + item_size,
                    y + item_size,
                    fill=grid_bg,
                    outline=border_color if has_equip else label_error,
                    width=2,
                )

            # 图标
            self.items_canvas.create_image(
                x + item_size // 2, y + item_size // 2 - 5, image=photo
            )

            # 帧索引文字（仅icon模式）
            if self.show_icons and frame_idx is not None:
                self.items_canvas.create_text(
                    x + 12,
                    y + 10,
                    text=str(frame_idx),
                    fill='#ffffff',
                    font=("Arial", 9, "bold"),
                    anchor="center",
                )

            # 时装代码
            self.items_canvas.create_text(
                x + item_size // 2,
                y + item_size - 8,
                text=display_text,
                fill=item_code_normal,
                font=("Arial", 12, "bold"),
            )

            # 点击区域（最上层）- 使用tags识别点击项，不需要逐个绑定事件
            self.items_canvas.create_rectangle(
                x,
                y,
                x + item_size,
                y + item_size,
                fill="",
                outline="",
                tags=f"item_{index}",
            )

        # 更新页码输入框的值
        self.page_entry.delete(0, tk.END)
        self.page_entry.insert(0, str(self.current_page + 1))

    def _on_canvas_click(self, event):
        """画布点击事件处理 - 通过tags识别点击项"""
        items = self.items_canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for item in reversed(items):
            tags = self.items_canvas.gettags(item)
            for tag in tags:
                if tag.startswith("item_"):
                    try:
                        idx = int(tag.split("_")[1])
                        self._on_item_select(idx)
                    except (ValueError, IndexError):
                        pass
                    return

    def _on_canvas_right_click(self, event):
        """画布右键点击事件处理"""
        items = self.items_canvas.find_overlapping(event.x, event.y, event.x, event.y)
        for item in reversed(items):
            tags = self.items_canvas.gettags(item)
            for tag in tags:
                if tag.startswith("item_"):
                    try:
                        idx = int(tag.split("_")[1])
                        self._on_item_right_click(event, idx)
                    except (ValueError, IndexError):
                        pass
                    return

    def _on_item_select(self, index: int):
        """选择装扮"""
        if not self.current_part:
            return

        # 图标模式下，负数 index 表示无映射图标，不应该被选中
        if self.show_icons and index < 0:
            return

        self.selected_parts[self.current_part] = index
        self.missing_items.pop(self.current_part, None)

        # 清除缓存（装备改变，需要重新处理）
        self.cache.f_layer.clear()
        self.cache.g_layer.clear()
        self.cache.h_layer.clear()
        self.cache.frame.clear()
        self.cache.photo.clear()
        self._preview_image_id = None
        self._cache_stop_flag = True  # 停止之前的缓存线程

        # 同步下拉列表选择
        if 0 <= index < len(self.items_index_map):
            combo_idx = self.items_index_map.index(index) if index in self.items_index_map else -1
            if combo_idx >= 0:
                self.items_combo.current(combo_idx)

        self._load_items_grid(self.current_part)
        # 清除缓存（装备改变，需要重新处理）
        self.cache.f_layer.clear()
        self.cache.g_layer.clear()
        self.cache.h_layer.clear()
        self._clear_render_cache()
        self._cache_stop_flag = True  # 停止之前的缓存线程

        self._update_selection_display()
        self._update_preview()

        # 后台预缓存所有帧
        self._pre_cache_all_frames()

    def _get_icon_count(self, job_key: str, part: str) -> int:
        """获取指定部位的标准图标数量（仅标准NPK图标）"""
        try:
            npk_name = self.suit_loader.get_icon_npk_name(job_key)
            img_name = self.suit_loader.get_icon_img_name(job_key, part)

            if not npk_name or not img_name:
                return 0

            if not self.icon_loader.load_icon_npk(npk_name):
                return 0

            npk = self.icon_loader.loaded_icon_npks.get(npk_name)
            if not npk:
                return 0

            for file in npk.files:
                if img_name in file.name:
                    return len(file.to_img().images)
            return 0
        except Exception as e:
            print(f"Error getting icon count: {e}")
            return 0

    def _check_has_icon(self, job_key: str, part: str, display_code: str) -> str:
        """检查指定时装是否有对应的图标 - 带缓存优化
        返回: "yes" - 有图标, "no_frame" - 有IMG但帧超出范围, "no_index" - 无图标
        """
        # 检查缓存
        cache_key = (job_key, part, display_code)
        if cache_key in self.cache.icon_status:
            return self.cache.icon_status[cache_key]

        result = "no_index"
        try:
            # 检查来源类型
            source_type, frame_idx = self.suit_loader.get_icon_source(
                job_key, part, display_code
            )

            if source_type == "none" or frame_idx is None or frame_idx == -1:
                result = "no_index"
            elif source_type == "custom":
                # 自定义图标 - 通过IMG路径检查
                custom = self.suit_loader.get_custom_icon(job_key, part, display_code)
                if not custom:
                    result = "no_index"
                else:
                    img_path = custom.get("img")
                    frame_idx = custom.get("frame", 0)
                    if not img_path:
                        result = "no_index"
                    elif not self.icon_loader._index_built:
                        result = "no_index"
                    else:
                        img_info = self.icon_loader.get_img_info(img_path)
                        if not img_info:
                            result = "no_index"
                        else:
                            npk_name = img_info["npk"]
                            if not img_info["loaded"]:
                                if not self.icon_loader.load_icon_npk(npk_name):
                                    result = "no_index"
                                else:
                                    img_file = self.icon_loader.img_index[img_path].get(
                                        "file"
                                    )
                                    if not img_file:
                                        result = "no_index"
                                    else:
                                        img = img_file.to_img()
                                        result = (
                                            "yes"
                                            if frame_idx < len(img.images)
                                            else "no_frame"
                                        )
                            else:
                                img_file = self.icon_loader.img_index[img_path].get(
                                    "file"
                                )
                                if not img_file:
                                    result = "no_index"
                                else:
                                    img = img_file.to_img()
                                    result = (
                                        "yes"
                                        if frame_idx < len(img.images)
                                        else "no_frame"
                                    )
            else:
                # 标准图标 - 原有逻辑
                npk_name = self.suit_loader.get_icon_npk_name(job_key)
                img_name = self.suit_loader.get_icon_img_name(job_key, part)
                if not npk_name or not img_name:
                    result = "no_index"
                elif not self.icon_loader.load_icon_npk(npk_name):
                    result = "no_index"
                else:
                    npk = self.icon_loader.loaded_icon_npks.get(npk_name)
                    if not npk:
                        result = "no_index"
                    else:
                        found = False
                        for file in npk.files:
                            if img_name in file.name:
                                img = file.to_img()
                                result = (
                                    "yes" if frame_idx < len(img.images) else "no_frame"
                                )
                                found = True
                                break
                        if not found:
                            result = "no_index"

            # 存入缓存
            if len(self.cache.icon_status) >= self.cache.icon_status.max_size:
                keys_to_remove = list(self.cache.icon_status.keys())[
                    : self.cache.icon_status.max_size // 10
                ]
                for key in keys_to_remove:
                    del self.cache.icon_status[key]
            self.cache.icon_status[cache_key] = result

        except Exception as e:
            print(f"Error checking icon: {e}")
            result = "no_index"

        return result

    def _load_icon_items(
        self, job_key: str, part: str, start_idx: int, end_idx: int
    ) -> List[Tuple]:
        """加载标准图标模式的网格项（仅加载标准NPK图标，自定义图标在单独标签页）"""
        page_items = []

        try:
            npk_name = self.suit_loader.get_icon_npk_name(job_key)
            img_name = self.suit_loader.get_icon_img_name(job_key, part)

            if not npk_name or not img_name:
                return page_items

            if not self.icon_loader.load_icon_npk(npk_name):
                return page_items

            npk = self.icon_loader.loaded_icon_npks.get(npk_name)
            if not npk:
                return page_items

            img_file = next((f for f in npk.files if img_name in f.name), None)
            if not img_file:
                return page_items

            total_frames = len(img_file.to_img().images)

            # 建立帧索引到时装code的反向映射
            options = self.loader.part_options.get(part, [])
            frame_to_code = {}
            for original_idx, option in enumerate(options):
                display_code = option[0]
                frame_idx = self.suit_loader.get_icon_frame(job_key, part, display_code)
                if frame_idx is not None and frame_idx < total_frames:
                    frame_to_code[frame_idx] = (display_code, original_idx)

            # 加载标准图标
            for frame_idx in range(start_idx, min(end_idx, total_frames)):
                icon_img = self.icon_loader.get_icon(
                    npk_name, img_name, frame_idx, (56, 56)
                )
                if icon_img is None:
                    icon_img = Image.new("RGBA", (56, 56), (200, 200, 200, 128))

                if frame_idx in frame_to_code:
                    display_code, original_idx = frame_to_code[frame_idx]
                    # 使用 original_idx 作为 index，frame_idx 存储在最后一个元素用于选中判断
                    page_items.append(
                        (
                            original_idx,
                            display_code,
                            icon_img,
                            True,
                            "#999999",
                            frame_idx,
                        )
                    )
                else:
                    # 无映射的图标使用负数 index（-frame_idx-1）避免与有映射的冲突
                    # 这样 original_idx >= 0，无映射的 < 0，不会相互影响
                    page_items.append(
                        (-frame_idx - 1, "", icon_img, False, "#999999", frame_idx)
                    )

        except Exception as e:
            print(f"Error loading icon items: {e}")
            import traceback

            traceback.print_exc()

        return page_items

    def _get_icon_frame_mapping(self, job_key: str, part: str) -> Dict:
        """获取图标帧映射信息（快速，不加载图片）

        Returns:
            {
                'total_frames': 总帧数,
                'frame_to_code': {frame_idx: (display_code, original_idx)}
            }
        """
        result = {"total_frames": 0, "frame_to_code": {}}

        try:
            npk_name = self.suit_loader.get_icon_npk_name(job_key)
            img_name = self.suit_loader.get_icon_img_name(job_key, part)

            if not npk_name or not img_name:
                return result

            if not self.icon_loader.load_icon_npk(npk_name):
                return result

            npk = self.icon_loader.loaded_icon_npks.get(npk_name)
            if not npk:
                return result

            img_file = next((f for f in npk.files if img_name in f.name), None)
            if not img_file:
                return result

            total_frames = len(img_file.to_img().images)

            # 建立帧索引到时装code的反向映射
            options = self.loader.part_options.get(part, [])
            frame_to_code = {}
            for original_idx, option in enumerate(options):
                display_code = option[0]
                frame_idx = self.suit_loader.get_icon_frame(job_key, part, display_code)
                if frame_idx is not None and frame_idx < total_frames:
                    frame_to_code[frame_idx] = (display_code, original_idx)

            result["total_frames"] = total_frames
            result["frame_to_code"] = frame_to_code

        except Exception as e:
            print(f"[WARN] 获取帧映射失败: {e}")

        return result

    def _load_icon_items_by_frames(
        self, job_key: str, part: str, frame_indices: List[int], frame_to_code: Dict
    ) -> List[Tuple]:
        """根据帧索引列表加载图标（仅加载指定帧）- 优化版：并行加载PIL Image，主线程转PhotoImage

        Args:
            frame_indices: 需要加载的帧索引列表
            frame_to_code: 帧到时装code的映射

        Returns:
            图标项列表 (返回PhotoImage直接可用)
        """
        page_items = []

        # 如果没有帧需要加载，直接返回空列表
        if not frame_indices:
            return page_items

        try:
            npk_name = self.suit_loader.get_icon_npk_name(job_key)
            img_name = self.suit_loader.get_icon_img_name(job_key, part)

            if not npk_name or not img_name:
                return page_items

            # 根据布局模式调整图标大小
            if self.grid_layout_mode == "8x8":
                icon_size = (56, 56)
            else:
                icon_size = (112, 112)  # 4x4 布局，图标更大

            # 并行加载 PIL Image（I/O密集型，可在线程中执行）
            def load_pil_image(
                frame_idx: int,
            ) -> Tuple[int, Optional[Image.Image], bool, str]:
                """在线程中加载 PIL Image，返回 (frame_idx, pil_img, has_equip, display_code)"""
                pil_img = self.icon_loader.get_icon(
                    npk_name, img_name, frame_idx, icon_size
                )

                if frame_idx in frame_to_code:
                    display_code, _ = frame_to_code[frame_idx]
                    return (frame_idx, pil_img, True, display_code)
                else:
                    return (frame_idx, pil_img, False, "")

            # 使用线程池并行加载 PIL Image
            max_workers = min(8, len(frame_indices))
            pil_results = {}

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_frame = {
                    executor.submit(load_pil_image, idx): idx for idx in frame_indices
                }
                for future in as_completed(future_to_frame):
                    frame_idx = future_to_frame[future]
                    try:
                        result = future.result()
                        pil_results[frame_idx] = result
                    except Exception as e:
                        print(f"[WARN] 加载图标帧 {frame_idx} 失败: {e}")
                        pil_results[frame_idx] = (frame_idx, None, False, "")

            # 在主线程中将 PIL Image 转换为 PhotoImage（Tkinter 线程安全要求）
            results = {}
            for frame_idx in frame_indices:
                if frame_idx in pil_results:
                    _, pil_img, has_equip, display_code = pil_results[frame_idx]

                    if pil_img is not None:
                        photo = ImageTk.PhotoImage(pil_img)
                    else:
                        placeholder = Image.new("RGBA", icon_size, (200, 200, 200, 128))
                        photo = ImageTk.PhotoImage(placeholder)

                    results[frame_idx] = (frame_idx, photo, has_equip, display_code)

            # 按原始顺序组装结果
            for frame_idx in frame_indices:
                if frame_idx in results:
                    _, photo, has_equip, display_code = results[frame_idx]
                    if has_equip and frame_idx in frame_to_code:
                        _, original_idx = frame_to_code[frame_idx]
                        page_items.append(
                            (
                                original_idx,
                                display_code,
                                photo,
                                True,
                                "#999999",
                                frame_idx,
                            )
                        )
                    else:
                        page_items.append(
                            (-frame_idx - 1, "", photo, False, "#999999", frame_idx)
                        )

        except Exception as e:
            print(f"[ERROR] 加载图标失败: {e}")
            import traceback

            traceback.print_exc()

        return page_items

    def _on_tab_changed(self, event=None):
        """标签页切换事件"""
        current_tab = self.icon_notebook.index("current")
        if current_tab == 0:  # 标准图标
            if self.current_part:
                self.show_icons = True
                self._load_items_grid(self.current_part)
        elif current_tab == 1:  # 自定义图标
            if self.current_part:
                # 切换到自定义图标时，必须切换到图标模式
                if not self.show_icons:  # 当前是3D模式
                    self._switch_to_icon_mode()
                self._refresh_custom_img_list()  # 刷新IMG列表
        elif current_tab == 2:  # 动画编辑
            # 切换到动画标签页时，加载当前动画
            self._load_current_animation()

    def _switch_to_icon_mode(self):
        """切换到图标模式"""
        tm = self.theme_manager
        self.display_mode_var.set("icon")
        self.show_icons = True
        self.mode_btn.config(text="模式: 图标", bg=tm.get("accent_secondary"))
        # 如果有选中的时装，跳转到对应图标页
        part = self.current_part
        if part:
            selected_idx = self.selected_parts.get(part)
            if selected_idx is not None:
                target_page = self._get_icon_page_for_equip(part, selected_idx)
                if target_page is not None:
                    self.current_page = target_page

    def _refresh_custom_img_list(self):
        tm = self.theme_manager
        """刷新自定义IMG列表 - 显示所有非标准NPK的IMG"""
        # 从IMG索引中获取所有非标准的IMG
        if not self.icon_loader._index_built:
            print("[DEBUG] IMG索引未构建")
            self.custom_img_combo["values"] = []
            return

        # 收集所有非标准IMG路径
        img_paths = []
        for img_path, info in self.icon_loader.img_index.items():
            if not info.get("is_standard", True):  # 非标准格式
                img_paths.append(img_path)

        print(f"[DEBUG] 非标准IMG总数: {len(img_paths)}")

        self._current_custom_imgs = sorted(img_paths)
        self._update_custom_img_combo()

        # 如果有IMG，默认选择第一个
        if self._current_custom_imgs:
            self.custom_img_combo.current(0)
            self._on_custom_img_selected()
        else:
            # 清空显示
            for widget in self.custom_content_frame.winfo_children():
                widget.destroy()
            tk.Label(
                self.custom_content_frame,
                text="没有找到非标准图标IMG",
                font=("Microsoft YaHei", 12),
                fg=tm.get("fg_tertiary"),
                bg=tm.get("bg_canvas_custom"),
            ).pack(pady=50)

    def _update_custom_img_combo(self):
        """根据过滤条件更新下拉列表"""
        filter_text = self.custom_img_filter_var.get().lower()

        if filter_text:
            filtered = [
                img for img in self._current_custom_imgs if filter_text in img.lower()
            ]
        else:
            filtered = self._current_custom_imgs

        self.custom_img_combo["values"] = filtered

        # 如果当前选中的不在过滤结果中，清空选择
        current = self.custom_img_combo.get()
        if current and current not in filtered:
            self.custom_img_combo.set("")

    def _on_custom_img_filter(self, event=None):
        """自定义IMG过滤输入事件"""
        self._update_custom_img_combo()

    def _on_custom_img_selected(self, event=None):
        """下拉列表选择IMG事件"""
        selected = self.custom_img_combo.get()
        if not selected:
            return

        self._selected_custom_img = selected
        self._load_custom_img_display(selected)

    def _load_custom_img_display(self, img_path: str):
        """加载并显示指定IMG的所有图标"""
        tm = self.theme_manager
        job_str = self.job_var.get()
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""
        part = self.current_part

        # 清空内容
        for widget in self.custom_content_frame.winfo_children():
            widget.destroy()
        self.custom_item_images = []

        # 获取该IMG在当前部位的映射（如果有的话）
        frame_to_code = {}
        if job_key and part:
            custom_icons = self.suit_loader.custom_icons.get(job_key, {}).get(part, {})
            for code, config in custom_icons.items():
                if config.get("img") == img_path:
                    frame_to_code[config.get("frame", 0)] = code

        # 显示IMG路径标题
        header_frame = tk.Frame(
            self.custom_content_frame, bg=tm.get("bg_canvas_custom")
        )
        header_frame.pack(fill=tk.X, pady=(0, 10))

        # 截断过长的路径
        display_path = img_path if len(img_path) < 60 else "..." + img_path[-57:]
        tk.Label(
            header_frame,
            text=f"IMG: {display_path}",
            font=("Microsoft YaHei", 9),
            fg=tm.get("label_info"),
            bg=tm.get("bg_canvas_custom"),
        ).pack(side=tk.LEFT)

        # 显示映射信息
        if frame_to_code:
            tk.Label(
                header_frame,
                text=f"已映射: {len(frame_to_code)}个",
                font=("Microsoft YaHei", 9),
                fg=tm.get("accent_success"),
                bg=tm.get("bg_canvas_custom"),
            ).pack(side=tk.RIGHT)
        else:
            tk.Label(
                header_frame,
                text="未映射",
                font=("Microsoft YaHei", 9),
                fg=tm.get("fg_tertiary"),
                bg=tm.get("bg_canvas_custom"),
            ).pack(side=tk.RIGHT)

        # 获取IMG信息
        if not self.icon_loader._index_built:
            tk.Label(
                self.custom_content_frame,
                text="IMG索引未构建",
                fg=tm.get("label_error"),
                bg=tm.get("bg_canvas_custom"),
            ).pack()
            return

        img_info = self.icon_loader.get_img_info(img_path)
        if not img_info:
            tk.Label(
                self.custom_content_frame,
                text=f"IMG未找到: {img_path}",
                fg=tm.get("label_error"),
                bg=tm.get("bg_canvas_custom"),
            ).pack()
            return

        # 动态加载NPK
        npk_name = img_info["npk"]
        if not img_info["loaded"]:
            if not self.icon_loader.load_icon_npk(npk_name):
                tk.Label(
                    self.custom_content_frame,
                    text=f"加载NPK失败: {npk_name}",
                    fg=tm.get("label_error"),
                    bg=tm.get("bg_canvas_custom"),
                ).pack()
                return

        # 获取总帧数
        img_file = self.icon_loader.img_index[img_path].get("file")
        if not img_file:
            tk.Label(
                self.custom_content_frame,
                text="IMG文件对象为空",
                fg=tm.get("label_error"),
                bg=tm.get("bg_canvas_custom"),
            ).pack()
            return

        try:
            img = img_file.to_img()
            total_frames = len(img.images)
        except Exception as e:
            tk.Label(
                self.custom_content_frame,
                text=f"读取IMG失败: {e}",
                fg=tm.get("label_error"),
                bg=tm.get("bg_canvas_custom"),
            ).pack()
            return

        # 创建图标网格
        icons_frame = tk.Frame(self.custom_content_frame, bg=tm.get("bg_canvas_custom"))
        icons_frame.pack(fill=tk.X)

        item_size, padding, items_per_row = 72, 8, 8

        for frame_idx in range(total_frames):
            row = frame_idx // items_per_row
            col = frame_idx % items_per_row

            # 创建图标容器
            icon_container = tk.Frame(
                icons_frame,
                width=item_size,
                height=item_size,
                bg=tm.get("bg_secondary"),
            )
            icon_container.grid(row=row, column=col, padx=padding, pady=padding)
            icon_container.grid_propagate(False)

            # 加载图标
            icon_img = self.icon_loader.get_icon_by_img_path(
                img_path, frame_idx, (56, 56)
            )
            if icon_img is None:
                icon_img = Image.new("RGBA", (56, 56), (200, 200, 200, 128))

            photo = ImageTk.PhotoImage(icon_img)
            self.custom_item_images.append(photo)

            # 检查是否有映射
            has_mapping = frame_idx in frame_to_code
            border_color = (
                tm.get("accent_success") if has_mapping else tm.get("border_secondary")
            )
            bg_color = tm.get("bg_tertiary") if has_mapping else tm.get("bg_secondary")

            # 创建画布显示图标
            canvas = tk.Canvas(
                icon_container,
                width=item_size,
                height=item_size,
                bg=bg_color,
                highlightbackground=border_color,
                highlightthickness=2,
            )
            canvas.pack()
            canvas.create_image(item_size // 2, item_size // 2, image=photo)

            # 帧号（左下角）
            canvas.create_text(
                10,
                item_size - 8,
                text=str(frame_idx),
                fill=tm.get("fg_primary"),
                font=("Arial", 10, "bold"),
                anchor=tk.W,
            )

            # 如果有映射，显示代码（左上角）
            if has_mapping:
                code = frame_to_code[frame_idx]
                canvas.create_text(
                    10,
                    12,
                    text=f"[{code}]",
                    fill="#00aa00",
                    font=("Arial", 9, "bold"),
                    anchor=tk.W,
                )

        # 更新滚动区域
        self.custom_content_frame.update_idletasks()
        self.custom_canvas.configure(scrollregion=self.custom_canvas.bbox("all"))

    def _on_custom_frame_configure(self, event=None):
        """自定义图标容器大小变化时更新滚动区域"""
        self.custom_canvas.configure(scrollregion=self.custom_canvas.bbox("all"))

    def _load_custom_icons(self, part: str):
        """加载自定义图标（按IMG分组显示）"""
        # 清空内容
        for widget in self.custom_content_frame.winfo_children():
            widget.destroy()
        self.custom_item_images = []

        job_str = self.job_var.get()
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""

        if not job_key:
            return

        # 获取自定义图标配置
        custom_icons = self.suit_loader.custom_icons.get(job_key, {}).get(part, {})
        if not custom_icons:
            tk.Label(
                self.custom_content_frame,
                text="该部位没有自定义图标",
                font=("Microsoft YaHei", 12),
                fg=tm.get("fg_tertiary"),
                bg=tm.get("bg_canvas_custom"),
            ).pack(pady=50)
            return

        # 按IMG路径分组
        img_groups = {}  # {img_path: [{code, frame}, ...]}
        for code, config in custom_icons.items():
            img_path = config.get("img")
            frame = config.get("frame", 0)
            if img_path:
                if img_path not in img_groups:
                    img_groups[img_path] = []
                img_groups[img_path].append({"code": code, "frame": frame})

        # 加载并显示每个IMG组
        for img_path, mappings in img_groups.items():
            self._load_custom_img_group(img_path, mappings, job_key, part)

        # 更新滚动区域
        self.custom_content_frame.update_idletasks()
        self.custom_canvas.configure(scrollregion=self.custom_canvas.bbox("all"))

    def _toggle_display_mode(self):
        """切换显示模式 - 优化版：预加载目标模式缓存"""
        part = self.current_part
        selected_idx = self.selected_parts.get(part) if part else None
        job_str = self.job_var.get()
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""

        if self.display_mode_var.get() == "3d":
            # 3D -> 图标
            # 先显示占位符，后台预加载图标
            self.items_canvas.delete("all")
            tm = self.theme_manager
            self.items_canvas.create_text(
                self.items_canvas.winfo_width() // 2,
                self.items_canvas.winfo_height() // 2,
                text="正在加载图标...",
                fill=tm.get("fg_secondary"),
                font=("Microsoft YaHei", 14),
            )
            self.root.update_idletasks()

            # 切换到图标模式
            self._switch_to_icon_mode()
            if part:
                self._load_items_grid(part)

        else:
            # 图标 -> 3D
            # 如果在自定义图标或动画标签，先切换回标准图标标签
            current_tab = self.icon_notebook.index("current")
            if current_tab in (1, 2):  # 自定义图标或动画标签
                self.icon_notebook.select(0)  # 切换回标准图标标签

            # 先显示占位符
            self.items_canvas.delete("all")
            tm = self.theme_manager
            self.items_canvas.create_text(
                self.items_canvas.winfo_width() // 2,
                self.items_canvas.winfo_height() // 2,
                text="正在加载3D预览...",
                fill=tm.get("fg_secondary"),
                font=("Microsoft YaHei", 14),
            )
            self.root.update_idletasks()

            # 切换到3D模式
            self.display_mode_var.set("3d")
            self.show_icons = False
            self.mode_btn.config(
                text="模式: 3D", bg=self.theme_manager.get("accent_primary")
            )
            if part and selected_idx is not None:
                target_page = self._get_equip_page_for_icon(part, selected_idx)
                if target_page is not None:
                    self.current_page = target_page
            if part:
                self._load_items_grid(part)
                # 后台预加载相邻页的缩略图
                self._preload_thumbnails_async(job_key, part, self.current_page)
                if self.current_page > 0:
                    self._preload_thumbnails_async(job_key, part, self.current_page - 1)
                self._preload_thumbnails_async(job_key, part, self.current_page + 1)

    def _toggle_missing_filter(self):
        """切换缺失筛选模式"""
        tm = self.theme_manager
        self.show_missing_only = not self.show_missing_only

        if self.show_missing_only:
            self.missing_filter_btn.config(
                text="显示: 缺失", bg=tm.get("accent_warning"), fg="white"
            )
        else:
            self.missing_filter_btn.config(
                text="显示: 全部", bg=tm.get("button_bg"), fg=tm.get("button_fg")
            )

        self.current_page = 0
        if self.current_part:
            self._load_items_grid(self.current_part)

    def _toggle_layout_mode(self):
        """切换布局模式 (8x8 <-> 4x4)"""
        tm = self.theme_manager
        if self.grid_layout_mode == "8x8":
            self.grid_layout_mode = "4x4"
            self.items_per_page = 16
            self.layout_btn.config(
                text="布局: 4x4", bg=tm.get("accent_primary"), fg="white"
            )
        else:
            self.grid_layout_mode = "8x8"
            self.items_per_page = 64
            self.layout_btn.config(
                text="布局: 8x8", bg=tm.get("bg_tertiary"), fg=tm.get("button_fg")
            )

        self.current_page = 0
        if self.current_part:
            self._load_items_grid(self.current_part)

    def _get_icon_page_for_equip(self, part: str, equip_idx: int) -> Optional[int]:
        """获取指定时装在图标模式下的页面编号"""
        try:
            job_key = (
                self.job_name_to_key.get(self.job_var.get(), self.job_var.get())
                if self.job_var.get()
                else ""
            )
            options = self.loader.part_options.get(part, [])
            if equip_idx >= len(options):
                return None

            display_code = options[equip_idx][0]
            frame_idx = self.suit_loader.get_icon_frame(job_key, part, display_code)
            if frame_idx is None:
                return None
            return frame_idx // self.items_per_page
        except Exception as e:
            print(f"Error calculating icon page: {e}")
            return None

    def _get_equip_page_for_icon(self, part: str, icon_frame_idx: int) -> Optional[int]:
        """获取指定图标帧对应的时装在3D模式下的页面编号"""
        try:
            job_key = (
                self.job_name_to_key.get(self.job_var.get(), self.job_var.get())
                if self.job_var.get()
                else ""
            )
            options = self.loader.part_options.get(part, [])

            for idx, option in enumerate(options):
                display_code = option[0]
                frame_idx = self.suit_loader.get_icon_frame(job_key, part, display_code)
                if frame_idx == icon_frame_idx:
                    filter_text = self.filter_var.get().lower()
                    if filter_text:
                        filtered_indices = [
                            i
                            for i, opt in enumerate(options)
                            if filter_text in opt[0].lower()
                        ]
                        if idx in filtered_indices:
                            return filtered_indices.index(idx) // self.items_per_page
                        return None
                    return idx // self.items_per_page
            return None
        except Exception as e:
            print(f"Error calculating equip page: {e}")
            return None

    def _apply_filter(self):
        self.current_page = 0
        if self.current_part:
            self._load_items_grid(self.current_part)

    def _clear_filter(self):
        self.filter_var.set("")
        self.current_page = 0
        if self.current_part:
            self._load_items_grid(self.current_part)

    def _next_page(self):
        """下一页（支持循环翻页）- 优化版：预加载下一页"""
        if self.total_pages <= 1:
            return
        self.current_page = (self.current_page + 1) % self.total_pages
        if self.current_part:
            self._load_items_grid(self.current_part)
            # 预加载下一页
            if not self.show_icons:  # 3D模式预加载缩略图
                job_str = self.job_var.get()
                job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""
                next_page = (self.current_page + 1) % self.total_pages
                self._preload_thumbnails_async(job_key, self.current_part, next_page)

    def _prev_page(self):
        """上一页（支持循环翻页）- 优化版：预加载上一页"""
        if self.total_pages <= 1:
            return
        self.current_page = (self.current_page - 1) % self.total_pages
        if self.current_part:
            self._load_items_grid(self.current_part)
            # 预加载上一页
            if not self.show_icons:  # 3D模式预加载缩略图
                job_str = self.job_var.get()
                job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""
                prev_page = (self.current_page - 1) % self.total_pages
                self._preload_thumbnails_async(job_key, self.current_part, prev_page)

    def _goto_page(self, event=None):
        """跳转到指定页"""
        if not self.current_part or self.total_pages <= 0:
            return

        try:
            # 从输入框读取页码
            page_str = self.page_entry.get().strip()
            if not page_str:
                return

            page = int(page_str)

            # 页码范围检查（支持1-based输入）
            if page < 1:
                page = 1
            elif page > self.total_pages:
                page = self.total_pages

            # 转换为0-based索引
            self.current_page = page - 1
            self._load_items_grid(self.current_part)

        except ValueError:
            # 输入不是有效数字，恢复显示当前页
            self.page_var.set(f"{self.current_page + 1} / {self.total_pages}")
            self.page_entry.delete(0, tk.END)
            self.page_entry.insert(0, str(self.current_page + 1))

    def _jump_to_current(self):
        """跳转到当前选中的时装所在页"""
        if not self.current_part:
            return

        part = self.current_part
        selected_idx = self.selected_parts.get(part)

        if selected_idx is None:
            return

        try:
            if self.show_icons:
                # 图标模式：跳转到包含当前时装图标的页
                target_page = self._get_icon_page_for_equip(part, selected_idx)
                if target_page is not None:
                    self.current_page = target_page
                    self._load_items_grid(part)
            else:
                # 3D模式：计算当前时装在过滤后列表中的页码
                filter_text = self.filter_var.get().lower()
                options = self.loader.part_options.get(part, [])

                if filter_text:
                    # 计算过滤后的索引位置
                    filtered_indices = [
                        i for i, opt in enumerate(options)
                        if filter_text in opt[0].lower()
                    ]
                    if selected_idx in filtered_indices:
                        position = filtered_indices.index(selected_idx)
                        self.current_page = position // self.items_per_page
                else:
                    # 无过滤，直接使用原始索引
                    self.current_page = selected_idx // self.items_per_page

                self._load_items_grid(part)

        except Exception as e:
            print(f"Error jumping to current: {e}")

    def _update_selection_icon(self, part: str, job_key: str, display_code: str):
        """更新单个部位的选择图标"""
        canvas = self.selection_icons.get(part)
        if not canvas:
            return

        # 清除旧图片
        canvas.delete("icon")
        self.selection_icon_images[part] = None

        if not job_key or not display_code:
            return

        try:
            # 获取图标配置
            item_config = self.suit_loader.get_item_config(job_key, part, display_code)
            if not item_config:
                return

            icon_type = item_config.get("icon_type")
            frame = item_config.get("frame")

            # 检查是否有效图标
            if icon_type is None or frame is None or frame == -1:
                return

            pil_img = None

            # 根据图标类型加载
            if icon_type == "standard":
                npk_name = self.suit_loader.get_icon_npk_name(job_key)
                img_name = self.suit_loader.get_icon_img_name(job_key, part)
                if npk_name and img_name:
                    pil_img = self.icon_loader.get_icon(
                        npk_name, img_name, frame, size=(32, 32)
                    )
            elif icon_type == "custom":
                # 自定义图标从配置中获取img路径
                custom_config = self.suit_loader.get_custom_icon(job_key, part, display_code)
                if custom_config:
                    img_path = custom_config.get("img")
                    custom_frame = custom_config.get("frame", 0)
                    if img_path:
                        pil_img = self.icon_loader.get_icon_by_img_path(
                            img_path, custom_frame, size=(32, 32)
                        )

            # 显示图标
            if pil_img:
                photo = ImageTk.PhotoImage(pil_img)
                self.selection_icon_images[part] = photo
                canvas.create_image(
                    16, 16, image=photo, tags="icon", anchor=tk.CENTER
                )
        except Exception as e:
            print(f"Error updating selection icon for {part}: {e}")

    def _clear_selection_icon(self, part: str):
        """清除单个部位的选择图标"""
        canvas = self.selection_icons.get(part)
        if canvas:
            canvas.delete("icon")
        self.selection_icon_images[part] = None

    def _update_selection_display(self):
        """更新左侧当前选择显示 - 不同状态使用不同颜色便于区分"""
        job_str = self.job_var.get()
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""

        # 颜色定义
        COLOR_NORMAL = "#84929e"  # 蓝色：正常状态
        COLOR_HIDDEN = "#ff6600"  # 橙色：被隐藏状态（醒目）
        COLOR_MISSING = "#cc0000"  # 红色：时装缺失（错误）
        COLOR_EMPTY = "#999999"  # 灰色：无时装（空闲）
        COLOR_NO_ICON = "#cc9900"  # 橙色：无图标（有配置但无图标映射）

        for part in PARTS:
            label = self.selection_labels.get(part)
            if not label:
                continue

            if part in self.missing_items:
                # 状态：时装缺失（错误状态）
                missing_code = self.missing_items[part]
                label.config(
                    text=f"{PART_NAMES.get(part, part)}: {missing_code} [时装缺失]",
                    foreground=COLOR_MISSING,
                )
                self._clear_selection_icon(part)
            elif part in self.selected_parts and self.loader.part_options.get(part):
                option_idx = self.selected_parts[part]
                options = self.loader.part_options[part]
                if option_idx < len(options):
                    display_code = options[option_idx][0]
                    item_name = self.suit_loader.get_item_name(
                        job_key, part, display_code
                    )
                    layer_count, layer_names = self.loader.get_sprite_layer_info(
                        part, option_idx
                    )

                    base_text = f"{PART_NAMES.get(part, part)}: {display_code}"
                    if item_name:
                        base_text += f" {item_name}"
                    if layer_count > 1:
                        # 简化图层名显示，去掉 part 前缀（如 weapon_b -> b）
                        simplified_names = []
                        for ln in layer_names:
                            if ln.startswith(f"{part}_"):
                                simplified_names.append(
                                    ln[len(part) + 1 :]
                                )  # 去掉 "{part}_"
                            else:
                                simplified_names.append(ln)
                        base_text += f" [{','.join(simplified_names)}]"

                    # 检查是否被隐藏
                    hidden_sources = self._get_hidden_parts_with_sources()
                    if part in hidden_sources:
                        # 状态：被隐藏（特殊状态，使用醒目颜色）
                        source_parts = hidden_sources[part]
                        source_names = [CN_PART_NAMES.get(p, p) for p in source_parts]
                        source_text = ",".join(source_names)
                        label.config(
                            text=base_text + f" [已隐藏:{source_text}]",
                            foreground=COLOR_HIDDEN,
                        )
                        # 被隐藏仍然显示图标
                        self._update_selection_icon(part, job_key, display_code)
                    else:
                        # 检查是否有图标
                        item_config = self.suit_loader.get_item_config(
                            job_key, part, display_code
                        )
                        has_icon = False
                        if item_config:
                            icon_type = item_config.get("icon_type")
                            frame = item_config.get("frame")
                            has_icon = (
                                icon_type is not None
                                and frame is not None
                                and frame != -1
                            )

                        if item_config and not has_icon:
                            # 状态：有配置但无图标
                            label.config(
                                text=base_text + " [无图标]",
                                foreground=COLOR_NO_ICON,
                            )
                        else:
                            # 状态：正常
                            label.config(text=base_text, foreground=COLOR_NORMAL)

                        # 更新图标显示
                        self._update_selection_icon(part, job_key, display_code)
                else:
                    # 状态：无装备（索引越界）
                    label.config(
                        text=f"{PART_NAMES.get(part, part)}: -1", foreground=COLOR_EMPTY
                    )
                    self._clear_selection_icon(part)
            else:
                # 状态：无装备（未选择）
                label.config(
                    text=f"{PART_NAMES.get(part, part)}: -1", foreground=COLOR_EMPTY
                )
                self._clear_selection_icon(part)

    def _update_preview(self):
        """更新预览 - 优先使用预缓存的帧和PhotoImage"""
        if not self.selected_parts:
            return

        # 优先检查PhotoImage缓存（最快路径 - 直接显示）
        # 注意：缓存的图像不包含背景，需要重新添加
        if self.current_frame in self.cache.photo:
            # 从缓存获取PIL图像并添加背景
            cached_img = self.cache.frame.get(self.current_frame)
            if cached_img is not None:
                result_img = self._draw_preview_background(cached_img.copy())
                photo = ImageTk.PhotoImage(result_img)
                if self._preview_image_id:
                    self.preview_canvas.itemconfig(self._preview_image_id, image=photo)
                else:
                    self.preview_canvas.delete("all")
                    self._preview_image_id = self.preview_canvas.create_image(
                        0, 0, anchor=tk.NW, image=photo
                    )
                self.current_preview = photo
                return

        # 检查是否有预缓存的PIL帧（需要转换为PhotoImage并添加背景）
        if self.current_frame in self.cache.frame:
            result_img = self.cache.frame[self.current_frame].copy()
            result_img = self._draw_preview_background(result_img)

            # 转换为PhotoImage
            photo = ImageTk.PhotoImage(result_img)

            # 管理PhotoImage缓存大小
            if len(self.cache.photo) >= self.cache.photo.max_size:
                keys_to_remove = list(self.cache.photo.keys())[
                    : self.cache.photo.max_size // 10
                ]
                for key in keys_to_remove:
                    del self.cache.photo[key]

            self.cache.photo[self.current_frame] = photo

            if self._preview_image_id:
                self.preview_canvas.itemconfig(self._preview_image_id, image=photo)
            else:
                self.preview_canvas.delete("all")
                self._preview_image_id = self.preview_canvas.create_image(
                    0, 0, anchor=tk.NW, image=photo
                )
            self.current_preview = photo
            return

        # 没有缓存，实时生成（较慢）
        # print(f"[Perf] 缓存未命中，实时生成帧{self.current_frame}...")
        self._generate_frame_realtime()
        # print(f"[Perf] 实时生成完成，帧{self.current_frame}: {(time.time()-start_time)*1000:.2f}ms")

    def _get_hidden_parts(self) -> set:
        """获取当前需要隐藏的部位集合

        Returns:
            需要隐藏的部位名称集合
        """
        sources = self._get_hidden_parts_with_sources()
        return set(sources.keys())

    def _get_hidden_parts_with_sources(self) -> Dict[str, List[str]]:
        """获取当前需要隐藏的部位及其来源

        Returns:
            {被隐藏部位: [来源部位列表]}
            例如: {'cap': ['skin'], 'coat': ['skin', 'belt']}
        """
        # 如果开启强制显示，返回空字典
        if self.force_show_hidden:
            return {}

        hidden_sources: Dict[str, List[str]] = {}
        job_str = self.job_var.get()
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""

        if not job_key:
            return hidden_sources

        for source_part, option_idx in self.selected_parts.items():
            # 获取时装代码
            options = self.loader.part_options.get(source_part, [])
            if option_idx < len(options):
                code = options[option_idx][0]  # display_code
                # 从SuitLoader获取完整配置
                item_config = self.suit_loader.get_item_config(
                    job_key, source_part, code
                )
                if item_config:
                    # 安全获取hide_parts
                    hide_parts = item_config.get("hide_parts") or []
                    if isinstance(hide_parts, list):
                        for hidden_part in hide_parts:
                            if hidden_part not in hidden_sources:
                                hidden_sources[hidden_part] = []
                            hidden_sources[hidden_part].append(source_part)

        return hidden_sources

    def _generate_frame_realtime(self):
        """实时生成当前帧（用于静态预览或无缓存时）- 支持隐藏部位"""
        CANVAS_WIDTH, CANVAS_HEIGHT, SCALE = 200, 200, 1
        CENTER_X, CENTER_Y = 100, 100

        frame_canvas = Image.new("RGBA", (500, 500), (0, 0, 0, 0))

        # 获取需要隐藏的部位
        hidden_parts = self._get_hidden_parts()

        # 收集所有需要绘制的图层
        render_items = []
        for part, option_idx in self.selected_parts.items():
            # 跳过被隐藏的部位
            if part in hidden_parts:
                continue

            layer_count, layer_names = self.loader.get_sprite_layer_info(
                part, option_idx
            )
            for layer in layer_names:
                priority = LAYER_DICT.get(
                    f"{part}_{layer}", 0 if part == "skin" else 3000
                )
                render_items.append((part, option_idx, layer, priority))

        render_items.sort(key=lambda x: x[3])

        # 图层处理调试计数
        f_layer_count = 0
        f_layer_processed = 0
        g_layer_count = 0
        g_layer_processed = 0
        h_layer_count = 0
        h_layer_processed = 0

        # 调试：输出所有图层名
        # if render_items:
        #     layer_names = [layer for _, _, layer, _ in render_items]
        #     print(f"[Debug] Render layers: {layer_names}")

        for part, option_idx, layer, _ in render_items:
            layer_img = self.loader.get_layer_sprite(
                part, option_idx, layer, self.current_frame
            )
            if layer_img:
                # 检查是否为f层并处理
                if self.process_f_layers and is_f_layer(layer):
                    f_layer_count += 1
                    # 使用缓存键
                    cache_key = (part, option_idx, layer, self.current_frame)

                    # 检查f层缓存
                    if cache_key in self.cache.f_layer:
                        processed_img = self.cache.f_layer[cache_key]
                        frame_canvas.paste(processed_img, (0, 0), processed_img)
                    else:
                        # 缓存未命中，进行f层处理（单独去黑底）
                        processed = apply_f_layer_process(layer_img, black_threshold=50)

                        # 存入f层缓存
                        if len(self.cache.f_layer) >= self.cache.f_layer.max_size:
                            keys_to_remove = list(self.cache.f_layer.keys())[
                                : self.cache.f_layer.max_size // 10
                            ]
                            for key in keys_to_remove:
                                del self.cache.f_layer[key]

                        self.cache.f_layer[cache_key] = processed
                        frame_canvas.paste(processed, (0, 0), processed)
                    f_layer_processed += 1
                elif self.process_g_layers and is_g_layer(layer):
                    g_layer_count += 1
                    # g层: 半透明混合（类似f层处理方式）
                    cache_key = (part, option_idx, layer, self.current_frame)

                    if cache_key in self.cache.g_layer:
                        processed_img = self.cache.g_layer[cache_key]
                        frame_canvas.paste(processed_img, (0, 0), processed_img)
                    else:
                        # 裁剪base区域进行不透明度混合
                        crop_box = (0, 0, layer_img.width, layer_img.height)
                        base_region = frame_canvas.crop(crop_box)
                        blended = blend_layer_with_opacity(
                            base_region, layer_img, opacity_pct=self.g_layer_opacity
                        )

                        # 存入g层缓存
                        if len(self.cache.g_layer) >= self.cache.g_layer.max_size:
                            keys_to_remove = list(self.cache.g_layer.keys())[
                                : self.cache.g_layer.max_size // 10
                            ]
                            for key in keys_to_remove:
                                del self.cache.g_layer[key]

                        self.cache.g_layer[cache_key] = blended
                        frame_canvas.paste(blended, (0, 0), blended)
                    g_layer_processed += 1
                elif self.process_h_layers and is_h_layer(layer):
                    h_layer_count += 1
                    # h层: 半透明混合（类似f层处理方式）
                    cache_key = (part, option_idx, layer, self.current_frame)

                    if cache_key in self.cache.h_layer:
                        processed_img = self.cache.h_layer[cache_key]
                        frame_canvas.paste(processed_img, (0, 0), processed_img)
                    else:
                        # 裁剪base区域进行不透明度混合
                        crop_box = (0, 0, layer_img.width, layer_img.height)
                        base_region = frame_canvas.crop(crop_box)
                        blended = blend_layer_with_opacity(
                            base_region, layer_img, opacity_pct=self.h_layer_opacity
                        )

                        # 存入h层缓存
                        if len(self.cache.h_layer) >= self.cache.h_layer.max_size:
                            keys_to_remove = list(self.cache.h_layer.keys())[
                                : self.cache.h_layer.max_size // 10
                            ]
                            for key in keys_to_remove:
                                del self.cache.h_layer[key]

                        self.cache.h_layer[cache_key] = blended
                        frame_canvas.paste(blended, (0, 0), blended)
                    h_layer_processed += 1
                else:
                    # 普通层: 直接粘贴
                    frame_canvas.paste(layer_img, (0, 0), layer_img)

        bbox = frame_canvas.getbbox()
        if bbox:
            cropped = frame_canvas.crop(bbox)
            new_width, new_height = int(cropped.width * SCALE), int(
                cropped.height * SCALE
            )
            if new_width > 0 and new_height > 0:
                preview_img = cropped.resize(
                    (new_width, new_height), Image.Resampling.NEAREST
                )
                result_img = Image.new(
                    "RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0)
                )
                result_img.paste(
                    preview_img,
                    (CENTER_X - new_width // 2, CENTER_Y - new_height // 2),
                    preview_img,
                )
            else:
                result_img = Image.new(
                    "RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0)
                )
        else:
            result_img = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))

        # 输出图层处理调试信息
        # if f_layer_count > 0 or g_layer_count > 0 or h_layer_count > 0:
        #     debug_msg = f"[Layer] Frame {self.current_frame}:"
        #     if f_layer_count > 0:
        #         debug_msg += f" F={f_layer_count}/{f_layer_processed}"
        #     if g_layer_count > 0:
        #         debug_msg += f" G={g_layer_count}/{g_layer_processed}({self.g_layer_opacity:+d}%)"
        #     if h_layer_count > 0:
        #         debug_msg += f" H={h_layer_count}/{h_layer_processed}({self.h_layer_opacity:+d}%)"
        #     print(debug_msg)

        # 绘制预览背景
        result_img = self._draw_preview_background(result_img)

        self.current_preview = ImageTk.PhotoImage(result_img)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, anchor=tk.NW, image=self.current_preview)

    def _generate_frame(self, frame_idx: int, render_items: list) -> Image.Image:
        """生成单帧图像（用于预缓存）- 带f层缓存优化"""
        CANVAS_WIDTH, CANVAS_HEIGHT, SCALE = 200, 200, 1
        CENTER_X, CENTER_Y = 100, 100

        frame_canvas = Image.new("RGBA", (500, 500), (0, 0, 0, 0))

        for part, option_idx, layer, _ in render_items:
            layer_img = self.loader.get_layer_sprite(part, option_idx, layer, frame_idx)
            if layer_img:
                if self.process_f_layers and is_f_layer(layer):
                    # f层处理（使用缓存）
                    cache_key = (part, option_idx, layer, frame_idx)

                    if cache_key in self.cache.f_layer:
                        processed_img = self.cache.f_layer[cache_key]
                        frame_canvas.paste(processed_img, (0, 0), processed_img)
                    else:
                        # f层处理：单独去黑底
                        processed = apply_f_layer_process(layer_img, black_threshold=50)

                        # 存入f层缓存
                        if len(self.cache.f_layer) >= self.cache.f_layer.max_size:
                            keys_to_remove = list(self.cache.f_layer.keys())[
                                : self.cache.f_layer.max_size // 10
                            ]
                            for key in keys_to_remove:
                                del self.cache.f_layer[key]

                        self.cache.f_layer[cache_key] = processed
                        frame_canvas.paste(processed, (0, 0), processed)
                elif self.process_g_layers and is_g_layer(layer):
                    # g层处理（使用缓存）
                    cache_key = (part, option_idx, layer, frame_idx)

                    if cache_key in self.cache.g_layer:
                        processed_img = self.cache.g_layer[cache_key]
                        frame_canvas.paste(processed_img, (0, 0), processed_img)
                    else:
                        # 裁剪base区域进行不透明度混合
                        crop_box = (0, 0, layer_img.width, layer_img.height)
                        base_region = frame_canvas.crop(crop_box)
                        blended = blend_layer_with_opacity(
                            base_region, layer_img, opacity_pct=self.g_layer_opacity
                        )

                        # 存入g层缓存
                        if len(self.cache.g_layer) >= self.cache.g_layer.max_size:
                            keys_to_remove = list(self.cache.g_layer.keys())[
                                : self.cache.g_layer.max_size // 10
                            ]
                            for key in keys_to_remove:
                                del self.cache.g_layer[key]

                        self.cache.g_layer[cache_key] = blended
                        frame_canvas.paste(blended, (0, 0), blended)
                elif self.process_h_layers and is_h_layer(layer):
                    # h层处理（使用缓存）
                    cache_key = (part, option_idx, layer, frame_idx)

                    if cache_key in self.cache.h_layer:
                        processed_img = self.cache.h_layer[cache_key]
                        frame_canvas.paste(processed_img, (0, 0), processed_img)
                    else:
                        # 裁剪base区域进行不透明度混合
                        crop_box = (0, 0, layer_img.width, layer_img.height)
                        base_region = frame_canvas.crop(crop_box)
                        blended = blend_layer_with_opacity(
                            base_region, layer_img, opacity_pct=self.h_layer_opacity
                        )

                        # 存入h层缓存
                        if len(self.cache.h_layer) >= self.cache.h_layer.max_size:
                            keys_to_remove = list(
                                self.cache.h_layer.keys()[
                                    : self.cache.h_layer.max_size // 10
                                ]
                            )
                            for key in keys_to_remove:
                                del self.cache.h_layer[key]

                        self.cache.h_layer[cache_key] = blended
                        frame_canvas.paste(blended, (0, 0), blended)
                else:
                    frame_canvas.paste(layer_img, (0, 0), layer_img)

        # 裁剪和调整大小
        bbox = frame_canvas.getbbox()
        if bbox:
            cropped = frame_canvas.crop(bbox)
            new_width, new_height = int(cropped.width * SCALE), int(
                cropped.height * SCALE
            )
            if new_width > 0 and new_height > 0:
                preview_img = cropped.resize(
                    (new_width, new_height), Image.Resampling.NEAREST
                )
                result_img = Image.new(
                    "RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0)
                )
                result_img.paste(
                    preview_img,
                    (CENTER_X - new_width // 2, CENTER_Y - new_height // 2),
                    preview_img,
                )
                # 绘制预览背景
                result_img = self._draw_preview_background(result_img)
                return result_img

        # 绘制预览背景（即使是空图像也绘制背景）
        result_img = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        result_img = self._draw_preview_background(result_img)
        return result_img

    def _pre_cache_all_frames(self):
        """后台预缓存所有帧（限制最大帧数以保证响应速度）"""
        import threading

        # 设置停止标志，终止之前的缓存线程
        self._cache_stop_flag = True

        # 等待之前的线程结束
        if self._caching_thread and self._caching_thread.is_alive():
            self._caching_thread.join(timeout=0.5)

        # 重置停止标志
        self._cache_stop_flag = False

        def cache_worker():
            if not self.selected_parts or not self.current_animation_frames:
                return

            # 获取渲染项列表（与_update_preview一致）- 支持隐藏部位
            hidden_parts = self._get_hidden_parts()
            render_items = []
            for part, option_idx in self.selected_parts.items():
                # 跳过被隐藏的部位
                if part in hidden_parts:
                    continue
                layer_count, layer_names = self.loader.get_sprite_layer_info(
                    part, option_idx
                )
                for layer in layer_names:
                    priority = LAYER_DICT.get(
                        f"{part}_{layer}", 0 if part == "skin" else 3000
                    )
                    render_items.append((part, option_idx, layer, priority))
            render_items.sort(key=lambda x: x[3])

            # 限制预缓存帧数（优先缓存前面的帧）
            frames_to_cache = self.current_animation_frames[
                : AppConfig.UI.MAX_PRECACHE_FRAMES
            ]
            total_frames = len(frames_to_cache)
            cached_count = 0

            for i, frame_idx in enumerate(frames_to_cache):
                # 检查停止标志
                if self._cache_stop_flag:
                    return

                # 跳过已缓存的帧
                if frame_idx in self.cache.frame:
                    continue

                # 如果缓存已满，清理旧的
                if len(self.cache.frame) >= self.cache.frame.max_size:
                    # 保留最近的50%，清理最早的50%
                    all_keys = list(self.cache.frame.keys())
                    keys_to_remove = all_keys[: len(all_keys) // 2]
                    for key in keys_to_remove:
                        del self.cache.frame[key]

                # 生成并缓存帧
                try:
                    frame_img = self._generate_frame(frame_idx, render_items)
                    self.cache.frame[frame_idx] = frame_img
                    cached_count += 1
                except Exception as e:
                    print(f"缓存帧 {frame_idx} 失败: {e}")
                    continue

                # 每5帧更新一次进度
                if i % 5 == 0:
                    progress = (i + 1) / total_frames * 100
                    # 使用after确保在主线程更新UI
                    try:
                        self.after(
                            0,
                            lambda p=progress: self._cache_progress_var.set(
                                f"缓存... {p:.0f}%"
                            ),
                        )
                    except:
                        pass

            # 更新最终状态
            try:
                self.after(
                    0,
                    lambda: self._cache_progress_var.set(
                        f"已缓存 {len(self.cache.frame)} 帧"
                    ),
                )
            except:
                pass

        # 启动后台线程
        self._caching_thread = threading.Thread(target=cache_worker, daemon=True)
        self._caching_thread.start()

    def _on_action_change(self, event=None):
        action_str = self.action_var.get()
        if not action_str:
            return

        self.current_action = action_str
        
        # 优先检查自定义动画
        if hasattr(self, 'custom_animations') and action_str in self.custom_animations:
            self.current_animation_frames = self.custom_animations[action_str]
        elif job_str := self.job_var.get():
            job_name = job_str
            frames = self.animation_loader.get_frames(job_name, self.current_action)
            self.current_animation_frames = frames if frames else list(range(161))
        else:
            self.current_animation_frames = list(range(161))

        self.animation_frame_index = 0
        self.current_frame = (
            self.current_animation_frames[0] if self.current_animation_frames else 0
        )
        self.frame_var.set(str(self.current_frame))

        # 清除帧缓存（动作改变，帧列表改变）
        self.cache.frame.clear()
        self.cache.f_layer.clear()
        self.cache.g_layer.clear()
        self.cache.h_layer.clear()
        self.cache.photo.clear()
        self._preview_image_id = None
        self._cache_stop_flag = True  # 停止之前的缓存线程

        self._update_preview()

        # 后台预缓存所有帧
        self._pre_cache_all_frames()

    def _get_max_frame(self) -> int:
        """获取当前角色默认皮肤(code 0)的IMG最大帧数"""
        return self.loader.max_frame

    # ==================== 动画标签页方法 ====================
    
    def _parse_anim_frames(self):
        """解析动画帧序列字符串 - 保持输入顺序，允许重复"""
        try:
            frames_str = self.anim_frames_var.get().strip()
            if not frames_str:
                return []
            
            frames = []
            parts = frames_str.split(",")
            max_frame = self._get_max_frame()
            
            for part in parts:
                part = part.strip()
                if "-" in part:
                    # 范围格式，展开为连续帧
                    start, end = part.split("-")
                    start, end = int(start), int(end)
                    # 验证范围并在有效范围内添加
                    for f in range(start, end + 1):
                        if 0 <= f <= max_frame:
                            frames.append(f)
                else:
                    # 单个数字
                    f = int(part)
                    if 0 <= f <= max_frame:
                        frames.append(f)
            
            return frames
        except Exception as e:
            self.anim_status_var.set(f"解析错误: {e}")
            return []
    
    def _load_current_animation(self):
        """加载当前动画到动画标签页"""
        # 设置动画名称
        self.anim_name_var.set(self.action_var.get())
        
        # 设置帧序列
        if self.current_animation_frames:
            frames_str = ",".join(self._frames_to_ranges(self.current_animation_frames))
            self.anim_frames_var.set(frames_str)
        else:
            self.anim_frames_var.set("0-10")
        
        # 停止之前的播放
        self._stop_animation_preview()
        
        # 渲染第一帧
        frames = self._parse_anim_frames()
        if frames:
            self.anim_preview_state['frames'] = frames
            self.anim_preview_state['current_idx'] = 0
            self._render_anim_preview_frame(0)
            self.anim_status_var.set(f"共 {len(frames)} 帧，点击播放开始")
    
    def _render_anim_preview_frame(self, idx):
        """渲染指定帧到动画预览画布"""
        frames = self.anim_preview_state['frames']
        if not frames or idx >= len(frames):
            idx = 0
        
        frame_num = frames[idx]
        self.anim_status_var.set(f"帧: {idx + 1} / {len(frames)} (IMG帧: {frame_num})")
        
        # 生成预览图
        preview_img = self._generate_preview_for_frame(frame_num, 1.2)
        if preview_img:
            img_width = preview_img.width()
            img_height = preview_img.height()
            x = (self.anim_canvas_size - img_width) // 2
            y = (self.anim_canvas_size - img_height) // 2
            self.anim_preview_canvas.delete("all")
            self.anim_preview_canvas.create_image(x, y, anchor=tk.NW, image=preview_img)
            self.anim_preview_canvas.image = preview_img
        
        self.anim_preview_state['current_idx'] = idx
    
    def _play_animation_loop(self):
        """动画播放循环"""
        if not self.anim_preview_state['is_playing']:
            return
        
        self._render_anim_preview_frame(self.anim_preview_state['current_idx'])
        self.anim_preview_state['current_idx'] = (self.anim_preview_state['current_idx'] + 1) % len(self.anim_preview_state['frames'])
        
        base_delay = 100
        delay = int(base_delay / self.anim_speed_var.get())
        self.anim_preview_state['after_id'] = self.root.after(delay, self._play_animation_loop)
    
    def _toggle_animation_preview(self):
        """播放/暂停动画预览"""
        frames = self._parse_anim_frames()
        if not frames:
            self.anim_status_var.set("无效的帧序列")
            return
        
        # 如果帧序列改变，重置
        if frames != self.anim_preview_state['frames']:
            self.anim_preview_state['frames'] = frames
            self.anim_preview_state['current_idx'] = 0
            if self.anim_preview_state['after_id']:
                self.root.after_cancel(self.anim_preview_state['after_id'])
        
        if self.anim_preview_state['is_playing']:
            # 暂停
            self.anim_preview_state['is_playing'] = False
            self.anim_play_btn.config(text="▶ 播放")
            if self.anim_preview_state['after_id']:
                self.root.after_cancel(self.anim_preview_state['after_id'])
        else:
            # 播放
            self.anim_preview_state['is_playing'] = True
            self.anim_play_btn.config(text="⏸ 暂停")
            self._play_animation_loop()
    
    def _stop_animation_preview(self):
        """停止动画预览"""
        self.anim_preview_state['is_playing'] = False
        self.anim_play_btn.config(text="▶ 播放")
        if self.anim_preview_state['after_id']:
            self.root.after_cancel(self.anim_preview_state['after_id'])
            self.anim_preview_state['after_id'] = None
        self.anim_preview_state['current_idx'] = 0
        if self.anim_preview_state['frames']:
            self._render_anim_preview_frame(0)
    
    def _prev_animation_frame(self):
        """上一帧"""
        if not self.anim_preview_state['frames']:
            return
        new_idx = max(0, self.anim_preview_state['current_idx'] - 1)
        self._render_anim_preview_frame(new_idx)
    
    def _next_animation_frame(self):
        """下一帧"""
        if not self.anim_preview_state['frames']:
            return
        new_idx = (self.anim_preview_state['current_idx'] + 1) % len(self.anim_preview_state['frames'])
        self._render_anim_preview_frame(new_idx)
    
    def _save_custom_animation(self):
        """保存自定义动画"""
        frames = self._parse_anim_frames()
        if not frames:
            self.anim_status_var.set("无效的帧序列")
            return
        
        name = self.anim_name_var.get().strip()
        if not name:
            self.anim_status_var.set("请输入动画名称")
            return
        
        # 保存到自定义动画
        if not hasattr(self, 'custom_animations'):
            self.custom_animations = {}
        
        self.custom_animations[name] = frames
        
        # 更新动作下拉框
        current_values = list(self.action_combo["values"])
        if name not in current_values:
            current_values.append(name)
            self.action_combo["values"] = current_values
        
        # 切换到新动画
        self.action_var.set(name)
        self.current_animation_frames = frames
        self.animation_frame_index = 0
        self.current_frame = frames[0]
        self.frame_var.set(str(self.current_frame))
        
        self.anim_status_var.set(f"已保存: {name} ({len(frames)} 帧)")

    def _generate_preview_for_frame(self, frame_num: int, zoom: float = 1.0):
        """生成指定帧的预览图 - 使用与主预览相同的逻辑渲染所有选中部位
        
        Args:
            frame_num: 帧号
            zoom: 缩放比例
            
        Returns:
            PhotoImage 或 None
        """
        try:
            from PIL import ImageTk
            
            # 创建画布（使用与实时生成相同的尺寸）
            frame_canvas = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
            
            # 获取需要隐藏的部位
            hidden_parts = self._get_hidden_parts()
            
            # 收集所有需要绘制的图层
            render_items = []
            for part, option_idx in self.selected_parts.items():
                # 跳过被隐藏的部位
                if part in hidden_parts:
                    continue
                
                layer_count, layer_names = self.loader.get_sprite_layer_info(
                    part, option_idx
                )
                for layer in layer_names:
                    priority = LAYER_DICT.get(
                        f"{part}_{layer}", 0 if part == "skin" else 3000
                    )
                    render_items.append((part, option_idx, layer, priority))
            
            # 按优先级排序
            render_items.sort(key=lambda x: x[3])
            
            # 渲染所有图层
            for part, option_idx, layer, _ in render_items:
                layer_img = self.loader.get_layer_sprite(
                    part, option_idx, layer, frame_num
                )
                if layer_img:
                    # 处理f-layer（发光层）
                    if self.process_f_layers and is_f_layer(layer):
                        processed = apply_f_layer_process(layer_img, black_threshold=50)
                        frame_canvas.paste(processed, (0, 0), processed)
                    # 处理g-layer（半透明层）
                    elif self.process_g_layers and is_g_layer(layer):
                        crop_box = (0, 0, layer_img.width, layer_img.height)
                        base_region = frame_canvas.crop(crop_box)
                        blended = blend_layer_with_opacity(
                            base_region, layer_img, opacity_pct=self.g_layer_opacity
                        )
                        frame_canvas.paste(blended, (0, 0), blended)
                    else:
                        frame_canvas.paste(layer_img, (0, 0), layer_img)
            
            # 裁剪有效区域（先裁剪动画内容）
            bbox = frame_canvas.getbbox()
            if bbox:
                frame_canvas = frame_canvas.crop(bbox)
            
            # 应用缩放
            if zoom != 1.0:
                new_size = (int(frame_canvas.width * zoom), int(frame_canvas.height * zoom))
                frame_canvas = frame_canvas.resize(new_size, Image.Resampling.LANCZOS)
            
            # 创建最终预览画布（固定大小，背景覆盖整个画布）
            preview_size = self.anim_canvas_size  # 350x350
            final_canvas = Image.new("RGBA", (preview_size, preview_size), (0, 0, 0, 0))
            
            # 应用背景到整个预览画布
            final_canvas = self._draw_preview_background(final_canvas)
            
            # 将动画内容居中粘贴到预览画布上
            if frame_canvas.width > 0 and frame_canvas.height > 0:
                paste_x = (preview_size - frame_canvas.width) // 2
                paste_y = (preview_size - frame_canvas.height) // 2
                final_canvas.paste(frame_canvas, (paste_x, paste_y), frame_canvas)
            
            return ImageTk.PhotoImage(final_canvas)
        except Exception as e:
            print(f"[Preview] 生成预览失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _frames_to_ranges(self, frames):
        """将帧列表转换为范围字符串"""
        if not frames:
            return []
        
        ranges = []
        start = frames[0]
        end = frames[0]
        
        for frame in frames[1:]:
            if frame == end + 1:
                end = frame
            else:
                if start == end:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{end}")
                start = end = frame
        
        # 添加最后一个范围
        if start == end:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{end}")
        
        return ranges

    def _prev_frame(self):
        """切换到上一帧（自由模式，不受动画序列限制）"""
        # 自由切换：当前帧 - 1，最小为 0
        self.current_frame = max(-1, self.current_frame - 1)
        if self.current_frame == -1:
            self.current_frame = self._get_max_frame()
        self.frame_var.set(str(self.current_frame))
        self._update_preview()

    def _next_frame(self):
        """切换到下一帧（自由模式，最大为默认皮肤IMG帧数）"""
        max_frame = self._get_max_frame()
        self.current_frame = min(max_frame + 1, self.current_frame + 1)
        if self.current_frame == max_frame + 1:
            self.current_frame = 0
        self.frame_var.set(str(self.current_frame))
        self._update_preview()

    def _toggle_animation(self):
        if self.animation_running:
            self._stop_animation()
        else:
            self._start_animation()

    def _on_frame_entry(self, event=None):
        """处理帧号输入框回车事件"""
        try:
            frame = int(self.frame_var.get())
            # 限制在 0-默认皮肤最大帧数 范围内
            max_frame = self._get_max_frame()
            frame = max(0, min(max_frame, frame))
            self.current_frame = frame
            self.frame_var.set(str(frame))
            self._update_preview()
        except ValueError:
            # 输入无效，恢复当前帧
            self.frame_var.set(str(self.current_frame))

    def _start_animation(self):
        self.animation_running = True
        self.play_btn.config(text="⏸ 停止")
        self._animate_frame()

    def _stop_animation(self):
        self.animation_running = False
        self.play_btn.config(text="▶ 播放")
        if hasattr(self, "after_id") and self.after_id:
            self.root.after_cancel(self.after_id)

    def _animate_frame(self):
        """动画帧循环 - 优化版本"""
        if not self.animation_running:
            return

        # 计算下一帧
        if self.play_all_frames.get():
            self.current_frame = (self.current_frame + 1) % 161
        elif self.current_animation_frames:
            self.animation_frame_index = (self.animation_frame_index + 1) % len(
                self.current_animation_frames
            )
            self.current_frame = self.current_animation_frames[
                self.animation_frame_index
            ]
        else:
            self.current_frame = (self.current_frame + 1) % 161

        # 更新帧号显示（但不触发trace）
        self.frame_var.set(str(self.current_frame))

        # 更新预览（优先使用缓存）
        self._update_preview()

        # 计算下一帧的间隔（根据是否全帧模式调整）
        # 全帧模式：50ms (20fps) | 动作模式：66ms (15fps)
        interval = 50 if self.play_all_frames.get() else 66
        self.after_id = self.root.after(interval, self._animate_frame)

    def _randomize_outfit(self):
        """随机选择一套时装"""
        if not self.loader.part_options:
            messagebox.showwarning("提示", "请先载入职业")
            return

        self.missing_items.clear()

        # 清除缓存（时装改变，需要重新处理）
        self.cache.f_layer.clear()
        self.cache.g_layer.clear()
        self.cache.h_layer.clear()
        self._clear_render_cache()
        self._cache_stop_flag = True  # 停止之前的缓存线程

        for part in PARTS:
            if part in self.loader.part_options and self.loader.part_options[part]:
                options = self.loader.part_options[part]
                if options:
                    self.selected_parts[part] = random.randint(0, len(options) - 1)

        self._update_selection_display()
        self._update_preview()

        # 后台预缓存所有帧
        self._pre_cache_all_frames()

        if self.current_part:
            self._load_items_grid(self.current_part)

        self.status_label.config(text="已随机选择一套时装")

    def _load_suit_list(self, keep_selection: bool = False, select_suit_name: str = None):
        """加载套装列表，按部位 code 排序（coat、pants优先）
        
        Args:
            keep_selection: 是否保持当前选择位置，默认为False（刷新时重置）
            select_suit_name: 指定要选中的套装名称（优先级高于 keep_selection）
        """
        # 保存当前选择的套装名称（如果需要保持选择）
        selected_suit_name = select_suit_name
        if keep_selection and not select_suit_name:
            selection = self.suit_listbox.curselection()
            if selection and hasattr(self, "_filtered_suits") and selection[0] < len(self._filtered_suits):
                selected_suit_name = self._filtered_suits[selection[0]]["name"]

        self.suit_listbox.delete(0, tk.END)

        job_str = self.job_var.get()
        if not job_str:
            self._filtered_suits = []
            return

        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""
        suits = self.suit_loader.get_suits(job_key)

        # 按部位 code 排序
        # 优先级：coat > pants > 其他部位按 PARTS 顺序
        def get_sort_key(suit):
            items = suit.get("items", {})
            
            def get_code(part):
                code = items.get(part, "")
                try:
                    return int(code) if code else -1
                except (ValueError, TypeError):
                    return code if code else ""
            
            # 优先排序 coat 和 pants
            key_parts = [get_code("coat"), get_code("pants")]
            
            # 然后按 PARTS 顺序添加其他部位
            for part in PARTS:
                if part not in ("coat", "pants"):
                    key_parts.append(get_code(part))
            
            return tuple(key_parts)

        # 排序套装列表
        sorted_suits = sorted(suits, key=get_sort_key)

        # 保存筛选后的套装列表，供其他方法使用
        filter_text = self.suit_filter_var.get().lower()
        self._filtered_suits = [
            s for s in sorted_suits if not filter_text or filter_text in s["name"].lower()
        ]

        # 填充列表框
        new_selection_index = -1
        for i, suit in enumerate(self._filtered_suits):
            self.suit_listbox.insert(tk.END, suit["name"])
            # 如果需要选中特定套装，查找其位置
            if selected_suit_name and suit["name"] == selected_suit_name:
                new_selection_index = i

        # 恢复选择位置
        if new_selection_index >= 0:
            self.suit_listbox.selection_set(new_selection_index)
            self.suit_listbox.see(new_selection_index)

    def _apply_suit_filter(self):
        self._load_suit_list()

    def _deduplicate_suits(self):
        """套装去重：显示所有套装的勾选列表，重复套装默认勾选，按部位 code 排序（coat、pants优先）"""
        job_str = self.job_var.get()
        if not job_str:
            messagebox.showwarning("提示", "请先选择一个职业")
            return

        job_key = self.job_name_to_key.get(job_str, job_str)
        suits = self.suit_loader.get_suits(job_key)

        if not suits:
            messagebox.showinfo("去重", "当前没有套装")
            return

        # 按部位 code 排序（coat、pants优先）
        def get_sort_key(suit):
            items = suit.get("items", {})
            
            def get_code(part):
                code = items.get(part, "")
                try:
                    return int(code) if code else -1
                except (ValueError, TypeError):
                    return code if code else ""
            
            # 优先排序 coat 和 pants
            key_parts = [get_code("coat"), get_code("pants")]
            
            # 然后按 PARTS 顺序添加其他部位
            for part in PARTS:
                if part not in ("coat", "pants"):
                    key_parts.append(get_code(part))
            
            return tuple(key_parts)

        sorted_suits = sorted(suits, key=get_sort_key)

        # 分析重复（在排序后的列表上）
        seen = {}  # {特征键: 第一套的名称}
        duplicate_names = set()  # 重复套装的名称集合

        for suit in sorted_suits:
            items = suit.get("items", {})
            # 构建特征键：排除 skin 和 weapon
            key_parts = []
            for part in ["cap", "hair", "face", "neck", "coat", "pants", "belt", "shoes"]:
                key_parts.append(items.get(part, ""))
            key = tuple(key_parts)

            if key in seen:
                duplicate_names.add(suit["name"])
            else:
                seen[key] = suit["name"]

        # 显示勾选对话框
        self._show_dedup_dialog(job_key, sorted_suits, duplicate_names)

    def _show_dedup_dialog(self, job_key: str, suits: list, duplicate_names: set):
        """显示去重勾选对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("套装去重")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 设置大小并居中
        self._center_window(dialog, 500, 600)

        tm = self.theme_manager
        dialog.configure(bg=tm.get("bg_primary"))

        # 标题
        tk.Label(
            dialog,
            text="套装去重",
            font=("Arial", 14, "bold"),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(pady=10)

        # 统计信息
        info_text = f"共 {len(suits)} 套套装，检测到 {len(duplicate_names)} 套重复（已默认勾选）"
        tk.Label(
            dialog,
            text=info_text,
            font=("Arial", 9),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_secondary"),
        ).pack(pady=(0, 5))

        # 按钮区域
        btn_frame = tk.Frame(dialog, bg=tm.get("bg_primary"))
        btn_frame.pack(fill=tk.X, padx=20, pady=5)

        # 勾选框列表区域
        list_frame = tk.Frame(dialog, bg=tm.get("bg_secondary"), bd=1, relief=tk.SUNKEN)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        # Canvas + Scrollbar 实现滚动
        canvas = tk.Canvas(list_frame, bg=tm.get("bg_secondary"), highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=tm.get("bg_secondary"))

        scrollable_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor=tk.NW, width=440)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # 存储复选框变量
        check_vars = {}  # {套装名: IntVar}

        # 添加表头
        header_frame = tk.Frame(scrollable_frame, bg=tm.get("bg_tertiary"))
        header_frame.pack(fill=tk.X, pady=(0, 2))
        tk.Label(
            header_frame,
            text="删除",
            font=("Arial", 9, "bold"),
            width=6,
            bg=tm.get("bg_tertiary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=5)
        tk.Label(
            header_frame,
            text="套装名称",
            font=("Arial", 9, "bold"),
            bg=tm.get("bg_tertiary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=5)

        # 添加复选框
        for suit in suits:
            suit_name = suit["name"]
            var = tk.IntVar(value=1 if suit_name in duplicate_names else 0)
            check_vars[suit_name] = var

            row_frame = tk.Frame(scrollable_frame, bg=tm.get("bg_secondary"))
            row_frame.pack(fill=tk.X, pady=1)

            # 如果是重复项，高亮显示
            if suit_name in duplicate_names:
                row_frame.configure(bg=tm.get("accent_warning"))

            cb = tk.Checkbutton(
                row_frame,
                variable=var,
                bg=row_frame.cget("bg"),
                activebackground=row_frame.cget("bg"),
            )
            cb.pack(side=tk.LEFT, padx=5)

            # 显示套装名称（如果是重复项，标记出来）
            display_name = f"{suit_name} [重复]" if suit_name in duplicate_names else suit_name
            label_color = tm.get("accent_danger") if suit_name in duplicate_names else tm.get("fg_primary")
            tk.Label(
                row_frame,
                text=display_name,
                font=("Arial", 9),
                bg=row_frame.cget("bg"),
                fg=label_color,
                anchor=tk.W,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 快捷操作按钮
        def select_all():
            for var in check_vars.values():
                var.set(1)

        def deselect_all():
            for var in check_vars.values():
                var.set(0)

        def select_duplicates():
            for name, var in check_vars.items():
                var.set(1 if name in duplicate_names else 0)

        def invert_selection():
            for var in check_vars.values():
                var.set(0 if var.get() else 1)

        tk.Button(
            btn_frame,
            text="全选",
            command=select_all,
            width=8,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            btn_frame,
            text="全不选",
            command=deselect_all,
            width=8,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            btn_frame,
            text="仅选重复",
            command=select_duplicates,
            width=8,
            bg=tm.get("accent_warning"),
            fg="white",
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            btn_frame,
            text="反选",
            command=invert_selection,
            width=8,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=2)

        # 底部按钮区域
        bottom_frame = tk.Frame(dialog, bg=tm.get("bg_primary"))
        bottom_frame.pack(fill=tk.X, padx=20, pady=15)

        def on_confirm():
            # 收集选中的套装
            selected = [name for name, var in check_vars.items() if var.get() == 1]
            
            if not selected:
                messagebox.showinfo("提示", "没有选择任何套装", parent=dialog)
                return

            # 二次确认
            msg = f"确定要删除选中的 {len(selected)} 套套装吗？\n\n"
            msg += "\n".join([f"• {name}" for name in selected[:15]])
            if len(selected) > 15:
                msg += f"\n... 等共 {len(selected)} 套"

            if messagebox.askyesno("确认删除", msg, icon="warning", parent=dialog):
                deleted_count = 0
                for suit_name in selected:
                    if self.suit_loader.delete_suit(job_key, suit_name):
                        deleted_count += 1

                dialog.destroy()
                self._load_suit_list()
                messagebox.showinfo("完成", f"已删除 {deleted_count} 套套装")
                self.status_label.config(text=f"已删除 {deleted_count} 套套装")

        tk.Button(
            bottom_frame,
            text="取消",
            command=dialog.destroy,
            width=12,
            bg=tm.get("bg_tertiary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=10)
        tk.Button(
            bottom_frame,
            text="确认删除",
            command=on_confirm,
            width=12,
            bg=tm.get("accent_danger"),
            fg="white",
            font=("Arial", 9, "bold"),
        ).pack(side=tk.LEFT, padx=10)

    def _on_create_suit(self):
        """生成套装按钮点击事件"""
        job_str = self.job_var.get()
        if not job_str:
            messagebox.showwarning("提示", "请先选择一个职业")
            return

        job_key = self.job_name_to_key.get(job_str, job_str)

        # 收集当前已选择的部位（只保存已选择的，跳过未选择的/即-1）
        # 注意：套装不包含武器
        suit_items = {}
        for part in PARTS:
            if part == "weapon":
                continue
            if part in self.selected_parts:
                option_idx = self.selected_parts[part]
                options = self.loader.part_options.get(part, [])
                if option_idx < len(options):
                    code = options[option_idx][0]
                    suit_items[part] = code

        # 检查是否有选择任何部位
        if not suit_items:
            messagebox.showwarning("提示", "当前没有选择任何时装，请至少选择一个部位")
            return

        # 显示生成套装对话框
        self._show_create_suit_dialog(job_key, suit_items)

    def _show_create_suit_dialog(self, job_key: str, suit_items: Dict[str, str]):
        """显示生成套装对话框"""
        # 创建对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("生成自定义套装")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 设置大小并居中
        self._center_window(dialog, 400, 500)

        tm = self.theme_manager

        # 设置对话框背景色
        dialog.configure(bg=tm.get("bg_primary"))

        # 标题
        tk.Label(
            dialog,
            text="生成自定义套装",
            font=("Arial", 14, "bold"),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(pady=10)

        # 套装名称输入
        name_frame = tk.Frame(dialog, padx=20, pady=10, bg=tm.get("bg_primary"))
        name_frame.pack(fill=tk.X)
        tk.Label(
            name_frame,
            text="套装名称:",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT)
        name_var = tk.StringVar()
        name_entry = tk.Entry(
            name_frame,
            textvariable=name_var,
            width=30,
            font=("Arial", 10),
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        )
        name_entry.pack(side=tk.LEFT, padx=5)
        name_entry.focus()

        # 当前选择显示
        select_frame = tk.LabelFrame(
            dialog,
            text="当前选择",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=5,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        select_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 创建滚动区域显示选择
        canvas = tk.Canvas(select_frame, height=250, bg=tm.get("bg_secondary"))
        scrollbar = tk.Scrollbar(select_frame, orient=tk.VERTICAL, command=canvas.yview)
        content_frame = tk.Frame(canvas, bg=tm.get("bg_secondary"))

        content_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=content_frame, anchor=tk.NW, width=340)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 显示已选择的部位（只显示已选择的，不显示未选择的）
        configured_count = 0
        for part in PARTS:
            if part in suit_items:
                code = suit_items[part]
                configured_count += 1
                name = (
                    self.suit_loader.get_item_name(job_key, part, code) or f"时装{code}"
                )
                text = f"{CN_PART_NAMES.get(part, part)}: {code} {name}"
                tk.Label(
                    content_frame,
                    text=text,
                    font=("Arial", 9),
                    fg=tm.get("label_info"),
                    bg=tm.get("bg_secondary"),
                ).pack(anchor=tk.W, pady=1)

        # 统计信息
        tk.Label(
            dialog,
            text=f"共 {configured_count} 个部位",
            font=("Arial", 9),
            fg=tm.get("fg_secondary"),
            bg=tm.get("bg_primary"),
        ).pack(pady=5)

        # 按钮区域
        btn_frame = tk.Frame(dialog, pady=20, bg=tm.get("bg_primary"))
        btn_frame.pack()

        def on_confirm():
            suit_name = name_var.get().strip()
            if not suit_name:
                messagebox.showwarning("提示", "请输入套装名称", parent=dialog)
                return

            # 检查是否已存在同名套装
            existing_suits = self.suit_loader.get_suits(job_key)
            existing_suit = None
            for s in existing_suits:
                if s.get("name") == suit_name:
                    existing_suit = s
                    break

            if existing_suit:
                # 询问是否覆盖
                result = messagebox.askyesno(
                    "套装已存在",
                    f"套装【{suit_name}】已存在，是否覆盖？\n\n覆盖将替换该套装的所有部位配置。",
                    icon="warning",
                    parent=dialog,
                )
                if not result:
                    return

            # 保存套装
            success = self._save_custom_suit(job_key, suit_name, suit_items)
            if success:
                dialog.destroy()
                messagebox.showinfo("成功", f"套装【{suit_name}】已保存")
                # 刷新套装列表并选中新保存的套装
                self._load_suit_list(select_suit_name=suit_name)
            else:
                messagebox.showerror("错误", "保存套装失败")

        tk.Button(
            btn_frame,
            text="取消",
            command=dialog.destroy,
            width=10,
            bg=tm.get("bg_tertiary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=10)

        tk.Button(
            btn_frame,
            text="确认生成",
            command=on_confirm,
            width=12,
            bg=tm.get("accent_primary"),
            fg="white",
            font=("Arial", 10, "bold"),
        ).pack(side=tk.LEFT, padx=10)

    def _save_custom_suit(
        self, job_key: str, suit_name: str, suit_items: Dict[str, str]
    ) -> bool:
        """保存自定义套装到配置"""
        try:
            config = self.suit_loader._load_or_convert_config(job_key)
            if not config:
                return False

            # 确保suits存在
            if "suits" not in config:
                config["suits"] = []

            # 查找或创建套装
            suit = None
            for s in config["suits"]:
                if s.get("name") == suit_name:
                    suit = s
                    break

            if suit:
                # 更新现有套装
                suit["items"] = suit_items.copy()
            else:
                # 创建新套装
                suit = {"name": suit_name, "items": suit_items.copy()}
                config["suits"].append(suit)

            # 保存配置
            if self.suit_loader._save_config(job_key, config):
                # 更新内存中的套装列表
                self.suit_loader.suits[job_key] = config["suits"]
                return True
            return False

        except Exception as e:
            print(f"[ERROR] 保存套装失败: {e}")
            return False

    def _apply_suit(self):
        """应用选中的套装"""
        selection = self.suit_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个套装")
            return

        job_str = self.job_var.get()
        if not job_str:
            return

        # 使用缓存的筛选后套装列表，确保与显示一致
        if not hasattr(self, "_filtered_suits") or not self._filtered_suits:
            return

        if selection[0] >= len(self._filtered_suits):
            return

        suit = self._filtered_suits[selection[0]]

        # 先清除缓存（必须在修改 selected_parts 之前）
        self.cache.f_layer.clear()
        self.cache.g_layer.clear()
        self.cache.h_layer.clear()
        self._clear_render_cache()
        self._cache_stop_flag = True

        self.missing_items.clear()

        applied_parts = []
        for part in PARTS:
            # 套装不包含武器，跳过武器部位，保留当前武器选择
            if part == "weapon":
                continue

            if part in suit["items"]:
                code = suit["items"][part]
                found = False
                if part in self.loader.part_options:
                    for idx, opt in enumerate(self.loader.part_options[part]):
                        if opt[0] == code:
                            self.selected_parts[part] = idx
                            applied_parts.append(part)
                            found = True
                            break
                if not found:
                    self.selected_parts.pop(part, None)
                    self.missing_items[part] = code
            else:
                self.selected_parts.pop(part, None)

        self._update_selection_display()
        self._update_preview()

        # 后台预缓存所有帧
        self._pre_cache_all_frames()

        if self.current_part:
            self._load_items_grid(self.current_part)

        self.status_label.config(text=f"已应用套装: {suit['name']}")

    def _on_suit_select(self, event=None):
        """左键选择套装 - 自动应用"""
        selection = self.suit_listbox.curselection()
        if not selection:
            return

        # 延迟执行，避免快速切换时的闪烁
        self.root.after(50, self._apply_suit)

    def _on_suit_right_click(self, event):
        """右键点击套装 - 弹出操作菜单"""
        # 获取点击位置的索引
        index = self.suit_listbox.nearest(event.y)
        if index < 0 or index >= self.suit_listbox.size():
            return

        # 选中该项
        self.suit_listbox.selection_clear(0, tk.END)
        self.suit_listbox.selection_set(index)
        self.suit_listbox.see(index)

        # 使用缓存的筛选后列表获取套装名称，确保一致性
        if not hasattr(self, "_filtered_suits") or index >= len(self._filtered_suits):
            return

        suit_name = self._filtered_suits[index]["name"]
        if not suit_name:
            return

        # 创建右键菜单
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="✏️ 修改套装名", command=lambda: self._rename_suit(suit_name))
        menu.add_separator()
        menu.add_command(label="🗑️ 删除套装", command=lambda: self._delete_suit(suit_name))
        
        # 显示菜单
        menu.post(event.x_root, event.y_root)

    def _rename_suit(self, old_name: str):
        """修改套装名称"""
        job_str = self.job_var.get()
        if not job_str:
            return
        
        job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""
        
        # 弹出输入对话框
        dialog = tk.Toplevel(self.root)
        dialog.title("修改套装名")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 设置大小并居中
        self._center_window(dialog, 350, 150)
        dialog.resizable(False, False)
        
        tm = self.theme_manager
        dialog.configure(bg=tm.get("bg_primary"))
        
        # 提示信息
        tk.Label(
            dialog,
            text=f"原名称: {old_name}",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_secondary"),
        ).pack(pady=(15, 5))
        
        # 新名称输入框
        name_var = tk.StringVar(value=old_name)
        entry = tk.Entry(
            dialog,
            textvariable=name_var,
            width=30,
            font=("Arial", 11),
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        )
        entry.pack(pady=5)
        entry.select_range(0, tk.END)
        entry.focus()
        
        def do_rename():
            new_name = name_var.get().strip()
            if not new_name:
                messagebox.showwarning("提示", "套装名称不能为空", parent=dialog)
                return
            
            if new_name == old_name:
                dialog.destroy()
                return
            
            # 检查新名称是否已存在
            existing_suits = self.suit_loader.get_suits(job_key)
            for s in existing_suits:
                if s.get("name") == new_name:
                    messagebox.showerror(
                        "错误",
                        f"套装【{new_name}】已存在，请使用其他名称。",
                        parent=dialog
                    )
                    return
            
            # 执行重命名
            if self.suit_loader.rename_suit(job_key, old_name, new_name):
                dialog.destroy()
                # 刷新列表并选中重命名后的套装
                self._load_suit_list(select_suit_name=new_name)
                self.status_label.config(text=f"已重命名套装: {old_name} → {new_name}")
            else:
                messagebox.showerror("错误", "重命名失败，请检查配置文件。", parent=dialog)
        
        # 按钮区域
        btn_frame = tk.Frame(dialog, bg=tm.get("bg_primary"))
        btn_frame.pack(pady=15)
        
        tk.Button(
            btn_frame,
            text="取消",
            command=dialog.destroy,
            width=10,
            bg=tm.get("bg_tertiary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            btn_frame,
            text="确认",
            command=do_rename,
            width=10,
            bg=tm.get("accent_primary"),
            fg="white",
        ).pack(side=tk.LEFT, padx=5)
        
        # 绑定回车键
        entry.bind("<Return>", lambda e: do_rename())

    def _delete_suit(self, suit_name: str):
        """删除套装"""
        if messagebox.askyesno(
            "确认删除",
            f"确定要删除套装【{suit_name}】吗？\n\n此操作不可恢复。",
            icon="warning",
        ):
            job_str = self.job_var.get()
            if not job_str:
                return

            job_key = self.job_name_to_key.get(job_str, job_str) if job_str else ""

            if self.suit_loader.delete_suit(job_key, suit_name):
                # 删除成功，刷新列表
                self._load_suit_list()
                self.status_label.config(text=f"已删除套装: {suit_name}")
            else:
                messagebox.showerror("错误", f"删除套装【{suit_name}】失败")

    def _clear_render_cache(self):
        """清除渲染相关缓存（隐藏关系或装备改变时调用）"""
        self.cache.frame.clear()
        self.cache.photo.clear()
        self._preview_image_id = None

    def _clear_thumbnail_cache_for_item(self, job_key: str, part: str, equip_code: str):
        """清除特定时装的缩略图缓存"""
        try:
            # 查找该时装对应的选项索引
            if part in self.loader.part_options:
                for idx, opt in enumerate(self.loader.part_options[part]):
                    if opt[0] == equip_code:
                        # 清除缩略图缓存
                        cache_key = (job_key, part, idx)
                        if cache_key in self.cache.thumbnail.keys():
                            del self.cache.thumbnail[cache_key]
                        if cache_key in self.cache.thumbnail_photo.keys():
                            del self.cache.thumbnail_photo[cache_key]
                        break
            
            # 清除图标状态缓存（使用与 _check_has_icon 相同的键格式）
            icon_cache_key = (job_key, part, equip_code)
            if icon_cache_key in self.cache.icon_status.keys():
                del self.cache.icon_status[icon_cache_key]
                print(f"[DEBUG] 清除图标状态缓存: {icon_cache_key}")
        except Exception as e:
            print(f"[WARN] 清除缓存失败: {e}")

    def _toggle_force_show_hidden(self):
        """切换强制显示隐藏部位开关"""
        self.force_show_hidden = self.force_show_var.get()

        # 清除缓存（因为渲染内容改变了）
        self._clear_render_cache()

        # 更新预览
        self._update_preview()
        status = "开启" if self.force_show_hidden else "关闭"
        self.status_label.config(text=f"强制显示隐藏部位已{status}")

        # 重新预缓存所有帧
        if self.current_animation_frames:
            self._pre_cache_all_frames()

    def _toggle_f_layer_processing(self):
        """切换f层处理开关"""
        # 清除缓存（因为处理方式改变了）
        self.cache.f_layer.clear()
        self.cache.g_layer.clear()
        self.cache.h_layer.clear()
        self.cache.frame.clear()
        self.cache.photo.clear()
        self._preview_image_id = None

        self.process_f_layers = self.f_layer_var.get()
        # 更新预览以显示效果对比
        self._update_preview()
        status = "开启" if self.process_f_layers else "关闭"
        self.status_label.config(text=f"f层处理已{status}")

        # 重新预缓存所有帧
        if self.process_f_layers:
            self._pre_cache_all_frames()

    def _toggle_g_layer_processing(self):
        """切换g层处理开关"""
        # 清除缓存（因为处理方式改变了）
        self.cache.g_layer.clear()
        self.cache.frame.clear()
        self.cache.photo.clear()
        self._preview_image_id = None

        self.process_g_layers = self.g_layer_var.get()
        # 更新预览以显示效果对比
        self._update_preview()
        status = "开启" if self.process_g_layers else "关闭"
        self.status_label.config(text=f"g层处理已{status} ({self.g_layer_opacity:+d}%)")

        # 重新预缓存所有帧
        if self.process_g_layers:
            self._pre_cache_all_frames()

    def _on_g_layer_opacity_changed(self, value):
        """g层不透明度滑块值改变（-100~100%）"""
        opacity = int(float(value))  # -100 ~ 100

        if opacity == self.g_layer_opacity:
            return

        self.g_layer_opacity = opacity
        self.g_layer_label.config(text=f"{opacity:+d}%")  # 显示带符号的百分比

        # 清除g层缓存
        self.cache.g_layer.clear()
        self.cache.frame.clear()
        self.cache.photo.clear()
        self._preview_image_id = None

        # 更新预览
        self._update_preview()
        self.status_label.config(text=f"g层不透明度: {opacity:+d}%")

    def _toggle_h_layer_processing(self):
        """切换h层处理开关"""
        # 清除缓存（因为处理方式改变了）
        self.cache.h_layer.clear()
        self.cache.frame.clear()
        self.cache.photo.clear()
        self._preview_image_id = None

        self.process_h_layers = self.h_layer_var.get()
        # 更新预览以显示效果对比
        self._update_preview()
        status = "开启" if self.process_h_layers else "关闭"
        self.status_label.config(text=f"h层处理已{status} ({self.h_layer_opacity:+d}%)")

        # 重新预缓存所有帧
        if self.process_h_layers:
            self._pre_cache_all_frames()

    def _on_h_layer_opacity_changed(self, value):
        """h层不透明度滑块值改变（-100~100%）"""
        opacity = int(float(value))  # -100 ~ 100

        if opacity == self.h_layer_opacity:
            return

        self.h_layer_opacity = opacity
        self.h_layer_label.config(text=f"{opacity:+d}%")  # 显示带符号的百分比

        # 清除h层缓存
        self.cache.h_layer.clear()
        self.cache.frame.clear()
        self.cache.photo.clear()
        self._preview_image_id = None

        # 更新预览
        self._update_preview()
        self.status_label.config(text=f"h层不透明度: {opacity:+d}%")

    def _on_preview_bg_changed(self):
        """预览背景切换"""
        self.preview_bg_type = self.bg_var.get()

        # 清除缓存（背景改变需要重新渲染）
        self.cache.frame.clear()
        self.cache.photo.clear()
        self._preview_image_id = None

        # 更新预览
        self._update_preview()

        bg_names = {
            "black": "黑色",
            "white": "白色",
            "gray": "灰色",
            "checkerboard": "透明格子",
        }
        self.status_label.config(
            text=f"预览背景: {bg_names.get(self.preview_bg_type, self.preview_bg_type)}"
        )

    def _draw_preview_background(self, canvas: Image.Image) -> Image.Image:
        """绘制预览背景

        Args:
            canvas: 目标画布（RGBA模式）

        Returns:
            绘制了背景的画布
        """
        width, height = canvas.size

        if self.preview_bg_type == "black":
            # 黑色背景
            bg = Image.new("RGBA", (width, height), (0, 0, 0, 255))
            canvas = Image.alpha_composite(bg, canvas)
        elif self.preview_bg_type == "white":
            # 白色背景
            bg = Image.new("RGBA", (width, height), (255, 255, 255, 255))
            canvas = Image.alpha_composite(bg, canvas)
        elif self.preview_bg_type == "gray":
            # 灰色背景（使用主题色）
            gray_color = 64  # 深灰色，与 tk grid_bg 一致
            bg = Image.new(
                "RGBA", (width, height), (gray_color, gray_color, gray_color, 255)
            )
            canvas = Image.alpha_composite(bg, canvas)
        elif self.preview_bg_type == "checkerboard":
            # 黑白透明格子背景
            checker_size = 20
            bg = Image.new("RGBA", (width, height), (255, 255, 255, 255))
            draw = ImageDraw.Draw(bg)

            for y in range(0, height, checker_size):
                for x in range(0, width, checker_size):
                    # 计算格子颜色
                    if ((x // checker_size) + (y // checker_size)) % 2 == 0:
                        color = (200, 200, 200, 255)  # 浅灰
                    else:
                        color = (255, 255, 255, 255)  # 白色
                    draw.rectangle(
                        [x, y, x + checker_size, y + checker_size], fill=color
                    )

            canvas = Image.alpha_composite(bg, canvas)

        return canvas

    def _on_item_right_click(self, event, item_index: int):
        """右键点击时装项 - 仅在3D模式下可用"""
        # 图标模式下禁用右键菜单
        if self.show_icons:
            return

        part = self.current_part
        if not part:
            return

        options = self.loader.part_options.get(part, [])
        filter_text = self.filter_var.get().lower()

        filtered = [
            (idx, opt)
            for idx, opt in enumerate(options)
            if not filter_text or filter_text in opt[0].lower()
        ]

        if item_index >= len(filtered):
            return

        original_idx, option = filtered[item_index]
        equip_code = option[0]

        job_key = (
            self.job_name_to_key.get(self.job_var.get(), self.job_var.get())
            if self.job_var.get()
            else ""
        )

        dialog = AssignIconDialog(
            self.root, self, job_key, part, equip_code, original_idx
        )
        self.root.wait_window(dialog.dialog)

        if dialog.result:
            # 重新加载套装数据
            self.suit_loader.load_suits_for_job(job_key)
            # 清除相关缓存，确保显示最新数据
            self._clear_thumbnail_cache_for_item(job_key, part, equip_code)
            # 刷新时装列表显示
            self._load_items_grid(part)
            # 刷新装扮下拉列表（如果时装名称有变更）
            self._load_items_list(part)
            # 刷新套装列表（保持当前选择位置）
            self._load_suit_list(keep_selection=True)
            # 状态提示
            self.status_label.config(text=f"已更新时装信息: {part} {equip_code}")


# =============================================================================
# 分配图标对话框
# =============================================================================


class AssignIconDialog:
    """分配图标对话框 - 支持标准图标和自定义NPK图标"""

    def __init__(
        self, parent, app, job_key: str, part: str, equip_code: str, equip_index: int
    ):
        self.app = app
        self.job_key = job_key
        self.part = part
        self.equip_code = equip_code
        self.equip_index = equip_index
        self.result = False

        # 标准图标选择状态
        self.selected_frame = None
        # 自定义图标选择状态
        self.selected_custom_img = None
        self.selected_custom_frame = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(f"分配图标 - {CN_PART_NAMES.get(part, part)} {equip_code}")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # 设置大小并居中（通过 app 调用主窗口的居中方法）
        self.app._center_window(self.dialog, 700, 800)
        self.dialog.minsize(700, 800)

        self._create_ui()

    def _create_ui(self):
        tm = self.app.theme_manager

        # 设置对话框背景色
        self.dialog.configure(bg=tm.get("bg_primary"))

        # 信息区域
        info_frame = tk.Frame(self.dialog, padx=10, pady=10, bg=tm.get("bg_primary"))
        info_frame.pack(fill=tk.X)

        tk.Label(
            info_frame,
            text=f"部位: {CN_PART_NAMES.get(self.part, self.part)}",
            font=("Arial", 10, "bold"),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(anchor=tk.W)
        tk.Label(
            info_frame,
            text=f"时装代码: {self.equip_code}",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(anchor=tk.W)

        # 名称输入
        name_frame = tk.Frame(self.dialog, padx=10, pady=5, bg=tm.get("bg_primary"))
        name_frame.pack(fill=tk.X)
        tk.Label(
            name_frame,
            text="时装名称:",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT)
        self.name_entry = tk.Entry(
            name_frame,
            width=40,
            font=("Arial", 10),
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        )
        self.name_entry.pack(side=tk.LEFT, padx=5)

        existing_name = self.app.suit_loader.get_item_name(
            self.job_key, self.part, self.equip_code
        )
        if existing_name:
            self.name_entry.insert(0, existing_name)

        # 创建水平容器，将预览和隐藏部位并排显示
        top_frame = tk.Frame(self.dialog, bg=tm.get("bg_primary"))
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        # 左侧：当前时装预览区域
        self._create_preview_frame(top_frame)

        # 右侧：隐藏部位选择区域
        self._create_hide_parts_frame(top_frame)

        # 标签页
        self.notebook = ttk.Notebook(self.dialog)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 配置Notebook标签样式（使其更明显）
        style = ttk.Style()
        style.configure("TNotebook.Tab", font=("Arial", 10, "bold"), padding=[15, 5])
        style.map(
            "TNotebook.Tab",
            background=[
                ("selected", tm.get("tab_selected_bg")),
                ("active", tm.get("tab_active_bg")),
            ],
            foreground=[
                ("selected", tm.get("tab_selected_fg")),
                ("active", tm.get("tab_active_fg")),
            ],
        )

        # 标准图标标签页
        self.standard_frame = tk.Frame(self.notebook, bg=tm.get("bg_primary"))
        self.notebook.add(self.standard_frame, text="标准图标")
        self._create_standard_tab()

        # 自定义图标标签页
        self.custom_frame = tk.Frame(self.notebook, bg=tm.get("bg_primary"))
        self.notebook.add(self.custom_frame, text="自定义NPK图标")
        self._create_custom_tab()

        # 套装信息标签页
        self.suit_frame = tk.Frame(self.notebook, bg=tm.get("bg_primary"))
        self.notebook.add(self.suit_frame, text="套装信息")
        self._create_suit_tab()

        # 检查当前是否有自定义图标，如果有则切换到自定义标签页
        existing_custom = self.app.suit_loader.get_custom_icon(
            self.job_key, self.part, self.equip_code
        )
        if existing_custom:
            self.notebook.select(self.custom_frame)
            self.selected_custom_img = existing_custom.get("img")
            self.selected_custom_frame = existing_custom.get("frame")

        # 按钮区域
        self._create_button_frame()

    def _create_hide_parts_frame(self, parent=None):
        """创建隐藏部位选择区域"""
        tm = self.app.theme_manager
        if parent is None:
            parent = self.dialog
        hide_frame = tk.LabelFrame(
            parent,
            text="隐藏其他部位",
            font=("Arial", 9),
            padx=8,
            pady=5,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        hide_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # 获取现有配置
        item_config = self.app.suit_loader.get_item_config(
            self.job_key, self.part, self.equip_code
        )
        existing_hide_parts = item_config.get("hide_parts", []) if item_config else []

        # 创建复选框变量字典
        self.hide_parts_vars = {}

        # 添加全选/取消全选按钮
        select_all_frame = tk.Frame(hide_frame, bg=tm.get("bg_primary"))
        select_all_frame.pack(fill=tk.X, pady=(0, 5))

        def toggle_all_hide_parts():
            """切换所有隐藏部位的勾选状态"""
            # 获取当前所有复选框的状态
            all_checked = all(var.get() for var in self.hide_parts_vars.values())
            # 如果全部已勾选，则取消全选；否则全选
            new_state = not all_checked
            for var in self.hide_parts_vars.values():
                var.set(new_state)

        tk.Button(
            select_all_frame,
            text="☑ 全选/取消",
            command=toggle_all_hide_parts,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
            font=("Arial", 8),
            width=10,
        ).pack(side=tk.LEFT, padx=5)

        # 每行显示4个复选框
        row_frame = None
        display_count = 0
        for part in PARTS:
            # 跳过当前部位（不能隐藏自己）
            if part == self.part:
                continue

            if display_count % 4 == 0:
                row_frame = tk.Frame(hide_frame, bg=tm.get("bg_primary"))
                row_frame.pack(fill=tk.X, pady=2)

            var = tk.BooleanVar(value=part in existing_hide_parts)
            self.hide_parts_vars[part] = var

            cb = ttk.Checkbutton(
                row_frame, text=CN_PART_NAMES.get(part, part), variable=var
            )
            cb.pack(side=tk.LEFT, padx=10)
            display_count += 1

    def _create_preview_frame(self, parent=None):
        """创建当前时装预览区域（图标+3D预览）"""
        tm = self.app.theme_manager
        if parent is None:
            parent = self.dialog
        preview_frame = tk.LabelFrame(
            parent,
            text="当前时装预览",
            font=("Arial", 9, "bold"),
            padx=8,
            pady=5,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # 左侧：图标
        icon_container = tk.Frame(preview_frame, bg=tm.get("bg_primary"))
        icon_container.pack(side=tk.LEFT, padx=10)

        tk.Label(
            icon_container,
            text="图标:",
            font=("Arial", 9),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack()
        self.preview_icon_label = tk.Label(icon_container, bg=tm.get("bg_primary"))
        self.preview_icon_label.pack()

        # 右侧：3D预览
        thumb_container = tk.Frame(preview_frame, bg=tm.get("bg_primary"))
        thumb_container.pack(side=tk.LEFT, padx=10)

        tk.Label(
            thumb_container,
            text="预览:",
            font=("Arial", 9),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack()
        self.preview_thumb_label = tk.Label(thumb_container, bg=tm.get("bg_primary"))
        self.preview_thumb_label.pack()

        # 加载预览
        self._load_current_previews()

    def _load_current_previews(self):
        """加载当前时装的图标和预览图"""
        tm = self.app.theme_manager
        try:
            # 加载图标
            icon_img = self._get_equip_icon(self.equip_code)
            if icon_img:
                photo = ImageTk.PhotoImage(icon_img)
                self.preview_icon_label.config(image=photo)
                self.preview_icon_label.image = photo  # 保持引用
            else:
                self.preview_icon_label.config(text="无图标", fg=tm.get("fg_tertiary"))

            # 加载3D预览图
            thumb_img = self._get_equip_thumbnail(self.equip_code)
            if thumb_img:
                photo = ImageTk.PhotoImage(thumb_img)
                self.preview_thumb_label.config(image=photo)
                self.preview_thumb_label.image = photo  # 保持引用
            else:
                self.preview_thumb_label.config(text="无预览", fg=tm.get("fg_tertiary"))
        except Exception as e:
            print(f"[WARN] 加载预览失败: {e}")

    def _get_equip_icon(self, code: str) -> Optional[Image.Image]:
        """获取指定时装的图标"""
        try:
            # 检查是否有自定义图标
            custom = self.app.suit_loader.get_custom_icon(self.job_key, self.part, code)
            if custom:
                img_path = custom.get("img")
                frame = custom.get("frame", 0)
                if img_path:
                    icon = self.app.icon_loader.get_icon_by_img_path(
                        img_path, frame, (56, 56)
                    )
                    if icon:
                        return icon

            # 使用标准图标
            frame = self.app.suit_loader.get_icon_frame(self.job_key, self.part, code)
            if frame is not None:
                npk_name = self.app.suit_loader.get_icon_npk_name(self.job_key)
                img_name = self.app.suit_loader.get_icon_img_name(
                    self.job_key, self.part
                )
                if npk_name and img_name:
                    return self.app.icon_loader.get_icon(
                        npk_name, img_name, frame, (56, 56)
                    )

            return None
        except Exception as e:
            return None

    def _get_equip_thumbnail(self, code: str) -> Optional[Image.Image]:
        """获取指定时装的3D预览图"""
        try:
            # 查找时装的索引
            options = self.app.loader.part_options.get(self.part, [])
            for idx, opt in enumerate(options):
                if opt[0] == code:
                    thumb = self.app.loader.generate_thumbnail(
                        self.part, idx, (80, 80), job_key=self.job_key
                    )
                    return thumb
            return None
        except Exception as e:
            return None

    def _create_button_frame(self):
        """创建按钮区域"""
        tm = self.app.theme_manager
        btn_frame = tk.Frame(self.dialog, padx=10, pady=10, bg=tm.get("bg_primary"))
        btn_frame.pack(fill=tk.X)

        # 删除按钮（左对齐）
        tk.Button(
            btn_frame,
            text="删除记录",
            command=self._on_delete,
            bg=tm.get("accent_danger"),
            fg="white",
            font=("Arial", 10),
            width=10,
        ).pack(side=tk.LEFT, padx=5)

        # 删除图标按钮（左对齐，橙色警告色）
        tk.Button(
            btn_frame,
            text="删除图标",
            command=self._on_delete_icon,
            bg=tm.get("accent_warning"),
            fg="white",
            font=("Arial", 10),
            width=10,
        ).pack(side=tk.LEFT, padx=5)

        # 确认和取消按钮（右对齐）
        tk.Button(
            btn_frame,
            text="确认",
            command=self._on_confirm,
            bg=tm.get("accent_primary"),
            fg="white",
            font=("Arial", 10, "bold"),
            width=10,
        ).pack(side=tk.RIGHT, padx=5)
        tk.Button(
            btn_frame,
            text="取消",
            command=self._on_cancel,
            bg=tm.get("bg_tertiary"),
            fg=tm.get("fg_primary"),
            font=("Arial", 10),
            width=10,
        ).pack(side=tk.RIGHT, padx=5)

    def _on_delete_icon(self):
        """删除当前时装的图标（保留名称和隐藏部位）"""
        # 获取当前配置
        item_config = self.app.suit_loader.get_item_config(
            self.job_key, self.part, self.equip_code
        )

        # 检查是否有图标
        has_icon = False
        if item_config:
            icon_type = item_config.get("icon_type")
            frame = item_config.get("frame")
            has_icon = icon_type is not None and frame is not None and frame != -1

        if not has_icon:
            messagebox.showinfo("提示", "该时装当前没有图标配置", parent=self.dialog)
            return

        # 确认删除
        result = messagebox.askyesno(
            "确认删除图标",
            f"确定要删除【{CN_PART_NAMES.get(self.part, self.part)} {self.equip_code}】的图标吗？\n\n"
            f"删除后将：\n"
            f"• 清除图标映射\n"
            f"• 保留时装名称和隐藏部位设置\n"
            f"• 图标将显示为缺失状态",
            icon="warning",
            parent=self.dialog,
        )

        if not result:
            return

        # 执行删除图标操作
        name = (
            item_config.get("name", f"时装{self.equip_code}")
            if item_config
            else f"时装{self.equip_code}"
        )
        hide_parts = item_config.get("hide_parts") or [] if item_config else []

        # 使用 save_item_without_icon 保存（无图标状态）
        if self.app.suit_loader.save_item_without_icon(
            self.job_key, self.part, self.equip_code, name, hide_parts
        ):
            self.result = True
            messagebox.showinfo(
                "成功", "图标已删除，时装名称和隐藏部位设置已保留", parent=self.dialog
            )
            self.dialog.destroy()
        else:
            messagebox.showerror("错误", "删除图标失败", parent=self.dialog)

    # ==================== 标准图标标签页 ====================
    def _create_standard_tab(self):
        tm = self.app.theme_manager
        icon_frame = tk.LabelFrame(
            self.standard_frame,
            text="选择图标（未使用的图标帧）",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        icon_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        page_control = tk.Frame(icon_frame, bg=tm.get("bg_primary"))
        page_control.pack(fill=tk.X, pady=5)

        self.icon_page_var = tk.StringVar(value="1 / 1")
        tk.Label(
            page_control,
            textvariable=self.icon_page_var,
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            page_control,
            text="上一页",
            command=self._prev_icon_page,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            page_control,
            text="下一页",
            command=self._next_icon_page,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=5)

        self.selected_frame_var = tk.StringVar(value="未选择图标")
        tk.Label(
            page_control,
            textvariable=self.selected_frame_var,
            font=("Arial", 10, "bold"),
            fg=tm.get("label_info"),
            bg=tm.get("bg_primary"),
        ).pack(side=tk.LEFT, padx=5)

        self.icon_canvas_frame = tk.Frame(
            icon_frame, height=320, bg=tm.get("bg_primary")
        )
        self.icon_canvas_frame.pack(fill=tk.BOTH, expand=True)
        self.icon_canvas_frame.pack_propagate(False)

        self.icon_canvas = tk.Canvas(
            self.icon_canvas_frame,
            width=640,
            height=300,
            bg=tm.get("bg_canvas_custom"),
            highlightthickness=1,
            highlightbackground=tm.get("border_primary"),
        )
        self.icon_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        icon_scrollbar = tk.Scrollbar(
            self.icon_canvas_frame, orient=tk.VERTICAL, command=self.icon_canvas.yview
        )
        icon_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.icon_canvas.config(yscrollcommand=icon_scrollbar.set)

        self.icon_images = []
        self._load_unused_icons()

        # 检查当前时装是否已有图标配置，如果有则设置selected_frame
        self._load_existing_icon_selection()

    def _load_existing_icon_selection(self):
        """加载当前时装已有的图标选择"""
        # 获取当前时装的图标配置
        item_config = self.app.suit_loader.get_item_config(
            self.job_key, self.part, self.equip_code
        )

        if item_config:
            icon_type = item_config.get("icon_type")
            frame = item_config.get("frame")

            # 只有当有icon_type且frame有效时才设置
            if icon_type == "standard" and frame is not None and frame >= 0:
                self.selected_frame = frame
                self.selected_frame_var.set(f"已选择图标帧: {frame}")
            elif icon_type is None or frame is None or frame == -1:
                # 无图标
                self.selected_frame = None
                self.selected_frame_var.set("未选择图标（无图标）")
        else:
            # 无配置
            self.selected_frame = None
            self.selected_frame_var.set("未选择图标")

    def _load_unused_icons(self):
        self.unused_frames = []
        self.icon_page = 0
        self.icons_per_page = 40

        total_icons = self.app._get_icon_count(self.job_key, self.part)
        if total_icons == 0:
            return

        used_frames = set()
        options = self.app.loader.part_options.get(self.part, [])
        for opt in options:
            # 只检查标准图标的使用情况
            frame = (
                self.app.suit_loader.icon_frames.get(self.job_key, {})
                .get(self.part, {})
                .get(opt[0])
            )
            if frame is not None:
                used_frames.add(frame)

        self.unused_frames = [i for i in range(total_icons) if i not in used_frames]
        self._update_icon_grid()

    def _update_icon_grid(self):
        tm = self.app.theme_manager
        self.icon_canvas.delete("all")
        self.icon_images.clear()

        if not self.unused_frames:
            self.icon_canvas.create_text(
                320,
                160,
                text="没有未使用的图标帧",
                font=("Arial", 14),
                fill=tm.get("fg_tertiary"),
            )
            self.icon_page_var.set("0 / 0")
            return

        total_pages = (
            len(self.unused_frames) + self.icons_per_page - 1
        ) // self.icons_per_page
        self.icon_page = min(self.icon_page, total_pages - 1)
        self.icon_page_var.set(f"{self.icon_page + 1} / {total_pages}")

        start_idx = self.icon_page * self.icons_per_page
        end_idx = min(start_idx + self.icons_per_page, len(self.unused_frames))
        page_frames = self.unused_frames[start_idx:end_idx]

        npk_name = self.app.suit_loader.get_icon_npk_name(self.job_key)
        img_name = self.app.suit_loader.get_icon_img_name(self.job_key, self.part)

        item_size, padding, items_per_row = 56, 8, 10

        for i, frame_idx in enumerate(page_frames):
            row, col = i // items_per_row, i % items_per_row
            x, y = padding + col * (item_size + padding), padding + row * (
                item_size + padding + 20
            )

            icon_img = self.app.icon_loader.get_icon(
                npk_name, img_name, frame_idx, (48, 48)
            )
            if icon_img is None:
                icon_img = Image.new("RGBA", (48, 48), (200, 200, 200, 128))

            photo = ImageTk.PhotoImage(icon_img)
            self.icon_images.append(photo)

            is_selected = self.selected_frame == frame_idx
            border_color = (
                tm.get("border_highlight") if is_selected else tm.get("border_primary")
            )
            bg_color = tm.get("bg_tertiary") if is_selected else tm.get("bg_secondary")

            self.icon_canvas.create_rectangle(
                x,
                y,
                x + item_size,
                y + item_size,
                fill=bg_color,
                outline=border_color,
                width=2,
            )
            self.icon_canvas.create_image(
                x + item_size // 2, y + item_size // 2 - 1, image=photo
            )
            self.icon_canvas.create_text(
                x + item_size // 2,
                y + item_size,
                text=str(frame_idx),
                font=("Arial", 10, "bold"),
                fill=tm.get("fg_primary"),
            )

            self.icon_canvas.create_rectangle(
                x,
                y,
                x + item_size,
                y + item_size,
                fill="",
                outline="",
                tags=f"icon_{frame_idx}",
            )
            self.icon_canvas.tag_bind(
                f"icon_{frame_idx}",
                "<Button-1>",
                lambda e, f=frame_idx: self._on_icon_select(f),
            )

        total_rows = (len(page_frames) + items_per_row - 1) // items_per_row
        self.icon_canvas.config(
            scrollregion=(0, 0, 640, max(320, total_rows * (item_size + padding + 20)))
        )

    def _on_icon_select(self, frame_idx: int):
        self.selected_frame = frame_idx
        self.selected_frame_var.set(f"已选择图标帧: {frame_idx}")
        # 清除自定义图标选择
        self.selected_custom_img = None
        self.selected_custom_frame = None
        self._update_icon_grid()

    def _prev_icon_page(self):
        if self.icon_page > 0:
            self.icon_page -= 1
            self._update_icon_grid()

    def _next_icon_page(self):
        total_pages = (
            len(self.unused_frames) + self.icons_per_page - 1
        ) // self.icons_per_page
        if self.icon_page < total_pages - 1:
            self.icon_page += 1
            self._update_icon_grid()

    # ==================== 自定义图标标签页 ====================
    def _create_custom_tab(self):
        tm = self.app.theme_manager
        # IMG路径选择和搜索
        img_frame = tk.Frame(
            self.custom_frame, padx=10, pady=10, bg=tm.get("bg_primary")
        )
        img_frame.pack(fill=tk.X)

        tk.Label(
            img_frame,
            text="IMG路径:",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT)

        # 搜索框
        self.custom_img_filter_var = tk.StringVar()
        self.custom_img_filter_var.trace_add("write", self._on_custom_img_filter)
        tk.Entry(
            img_frame,
            textvariable=self.custom_img_filter_var,
            width=20,
            font=("Arial", 9),
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        ).pack(side=tk.LEFT, padx=5)

        self.img_combo = ttk.Combobox(img_frame, width=45, font=("Arial", 9))
        self.img_combo.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.img_combo.bind("<<ComboboxSelected>>", self._on_img_selected)

        tk.Button(
            img_frame,
            text="刷新",
            command=self._refresh_img_list,
            font=("Arial", 9),
            width=8,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=5)

        # 帧信息显示
        self.frame_info_var = tk.StringVar(value="请选择IMG路径")
        tk.Label(
            self.custom_frame,
            textvariable=self.frame_info_var,
            font=("Arial", 9),
            fg=tm.get("fg_secondary"),
            padx=10,
        ).pack(anchor=tk.W)

        # 图标显示区域
        icon_frame = tk.LabelFrame(
            self.custom_frame,
            text="选择图标帧",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        icon_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 分页控制
        page_control = tk.Frame(icon_frame, bg=tm.get("bg_primary"))
        page_control.pack(fill=tk.X, pady=5)

        self.custom_page_var = tk.StringVar(value="1 / 1")
        tk.Label(
            page_control,
            textvariable=self.custom_page_var,
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            page_control,
            text="上一页",
            command=self._prev_custom_page,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            page_control,
            text="下一页",
            command=self._next_custom_page,
            bg=tm.get("button_bg"),
            fg=tm.get("button_fg"),
        ).pack(side=tk.LEFT, padx=5)

        self.selected_custom_var = tk.StringVar(value="未选择图标")
        tk.Label(
            page_control,
            textvariable=self.selected_custom_var,
            font=("Arial", 10, "bold"),
            fg=tm.get("accent_success"),
            bg=tm.get("bg_primary"),
        ).pack(side=tk.LEFT, padx=20)

        # 使用滚动区域替代Canvas - 与主界面保持一致
        self.custom_canvas_frame = tk.Frame(icon_frame, bg=tm.get("bg_canvas_custom"))
        self.custom_canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.custom_icon_images = []
        self.custom_frames = []
        self.custom_page = 0
        self.custom_icons_per_page = 40
        self._all_custom_imgs = []  # 存储所有IMG路径

        # 加载IMG列表
        self._refresh_img_list()

    def _refresh_img_list(self):
        """刷新IMG路径列表"""
        # 获取所有非标准IMG路径
        img_paths = []
        for img_path, info in self.app.icon_loader.img_index.items():
            if not info.get("is_standard", True):
                img_paths.append(img_path)

        self._all_custom_imgs = sorted(img_paths)
        self._update_custom_img_combo()

        # 如果有已选择的自定义图标，选中它
        if (
            self.selected_custom_img
            and self.selected_custom_img in self._all_custom_imgs
        ):
            self.img_combo.set(self.selected_custom_img)
            self._load_custom_frames()

    def _update_custom_img_combo(self):
        """根据过滤条件更新下拉列表"""
        filter_text = self.custom_img_filter_var.get().lower()

        if filter_text:
            filtered = [
                img for img in self._all_custom_imgs if filter_text in img.lower()
            ]
        else:
            filtered = self._all_custom_imgs

        self.img_combo["values"] = filtered

        # 如果当前选中的不在过滤结果中，清空选择
        current = self.img_combo.get()
        if current and current not in filtered:
            self.img_combo.set("")

    def _on_custom_img_filter(self, *args):
        """自定义IMG过滤输入事件"""
        self._update_custom_img_combo()

    def _on_img_selected(self, event=None):
        """当选择IMG路径时"""
        img_path = self.img_combo.get()
        if img_path:
            self.selected_custom_img = img_path
            self._load_custom_frames()

    def _load_custom_frames(self):
        """加载选定IMG的所有帧 - 使用icon_loader的缓存机制"""
        self.custom_frames = []
        self.custom_page = 0

        img_path = self.selected_custom_img
        if not img_path:
            self.frame_info_var.set("请选择IMG路径")
            self._clear_custom_grid()
            return

        # 获取IMG信息
        img_info = self.app.icon_loader.get_img_info(img_path)
        if not img_info:
            self.frame_info_var.set(f"IMG未找到: {img_path}")
            self._clear_custom_grid()
            return

        # 动态加载NPK（如果未加载）
        npk_name = img_info["npk"]
        if not img_info["loaded"]:
            if not self.app.icon_loader.load_icon_npk(npk_name):
                self.frame_info_var.set(f"加载NPK失败: {npk_name}")
                self._clear_custom_grid()
                return

        # 获取IMG文件对象
        img_file = self.app.icon_loader.img_index[img_path].get("file")
        if not img_file:
            self.frame_info_var.set("IMG文件对象为空")
            self._clear_custom_grid()
            return

        # 获取总帧数
        try:
            img = img_file.to_img()
            total_frames = len(img.images)
            self.custom_frames = list(range(total_frames))
            self.frame_info_var.set(
                f"IMG: {img_path} | 总帧数: {total_frames} | NPK: {npk_name}"
            )
        except Exception as e:
            self.frame_info_var.set(f"读取IMG失败: {e}")
            self._clear_custom_grid()
            return

        self._update_custom_grid()

    def _clear_custom_grid(self):
        """清空图标网格"""
        for widget in self.custom_canvas_frame.winfo_children():
            widget.destroy()
        self.custom_icon_images.clear()

    def _update_custom_grid(self):
        """更新自定义图标网格 - 使用与主界面相同的方式"""
        tm = self.app.theme_manager
        # 清空现有内容
        self._clear_custom_grid()

        if not self.custom_frames:
            tk.Label(
                self.custom_canvas_frame,
                text="请选择IMG路径",
                font=("Microsoft YaHei", 12),
                fg=tm.get("fg_tertiary"),
                bg=tm.get("bg_canvas_custom"),
            ).pack(pady=50)
            self.custom_page_var.set("0 / 0")
            return

        total_pages = (
            len(self.custom_frames) + self.custom_icons_per_page - 1
        ) // self.custom_icons_per_page
        self.custom_page = min(self.custom_page, total_pages - 1)
        self.custom_page_var.set(f"{self.custom_page + 1} / {total_pages}")

        start_idx = self.custom_page * self.custom_icons_per_page
        end_idx = min(start_idx + self.custom_icons_per_page, len(self.custom_frames))
        page_frames = self.custom_frames[start_idx:end_idx]

        img_path = self.selected_custom_img
        item_size, padding, items_per_row = 72, 8, 8

        for i, frame_idx in enumerate(page_frames):
            row = i // items_per_row
            col = i % items_per_row

            # 创建图标容器
            icon_container = tk.Frame(
                self.custom_canvas_frame,
                width=item_size,
                height=item_size,
                bg=tm.get("bg_canvas_custom"),
            )
            icon_container.grid(row=row, column=col, padx=padding, pady=padding)
            icon_container.grid_propagate(False)

            # 加载图标
            icon_img = self.app.icon_loader.get_icon_by_img_path(
                img_path, frame_idx, (56, 56)
            )
            if icon_img is None:
                icon_img = Image.new("RGBA", (56, 56), (200, 200, 200, 128))

            photo = ImageTk.PhotoImage(icon_img)
            self.custom_icon_images.append(photo)

            is_selected = self.selected_custom_frame == frame_idx
            border_color = (
                tm.get("accent_success") if is_selected else tm.get("border_secondary")
            )
            bg_color = tm.get("bg_tertiary") if is_selected else tm.get("bg_secondary")

            # 创建画布显示图标
            canvas = tk.Canvas(
                icon_container,
                width=item_size,
                height=item_size,
                bg=bg_color,
                highlightbackground=border_color,
                highlightthickness=2,
            )
            canvas.pack()
            canvas.create_image(item_size // 2, item_size // 2, image=photo)

            # 帧号（左下角）
            canvas.create_text(
                10,
                item_size - 8,
                text=str(frame_idx),
                fill=tm.get("fg_primary"),
                font=("Arial", 10, "bold"),
                anchor=tk.W,
            )

            # 点击事件
            canvas.bind(
                "<Button-1>", lambda e, f=frame_idx: self._on_custom_icon_select(f)
            )

    def _on_custom_icon_select(self, frame_idx: int):
        """选择自定义图标帧"""
        self.selected_custom_frame = frame_idx
        self.selected_custom_var.set(f"已选择帧: {frame_idx}")
        # 清除标准图标选择
        self.selected_frame = None
        self._update_custom_grid()

    def _prev_custom_page(self):
        if self.custom_page > 0:
            self.custom_page -= 1
            self._update_custom_grid()

    def _next_custom_page(self):
        total_pages = (
            len(self.custom_frames) + self.custom_icons_per_page - 1
        ) // self.custom_icons_per_page
        if self.custom_page < total_pages - 1:
            self.custom_page += 1
            self._update_custom_grid()

    # ==================== 套装信息标签页 ====================
    def _create_suit_tab(self):
        """创建套装信息标签页"""
        tm = self.app.theme_manager
        # 当前所属套装显示区域
        current_frame = tk.LabelFrame(
            self.suit_frame,
            text="当前所属套装",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        current_frame.pack(fill=tk.X, padx=10, pady=10)

        self.current_suits_text = tk.Text(
            current_frame,
            height=4,
            wrap=tk.WORD,
            font=("Arial", 10),
            state=tk.DISABLED,
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        )
        self.current_suits_text.pack(fill=tk.BOTH, expand=True)
        self._update_current_suits_display()

        # 套装选择区域
        select_frame = tk.LabelFrame(
            self.suit_frame,
            text="添加/更换套装",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        select_frame.pack(fill=tk.X, padx=10, pady=10)

        # 搜索框
        search_frame = tk.Frame(select_frame, bg=tm.get("bg_primary"))
        search_frame.pack(fill=tk.X, pady=5)

        tk.Label(
            search_frame,
            text="搜索:",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=5)
        self.suit_search_var = tk.StringVar()
        self.suit_search_var.trace("w", lambda *args: self._filter_suit_list())
        tk.Entry(
            search_frame,
            textvariable=self.suit_search_var,
            font=("Arial", 10),
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 套装列表
        list_frame = tk.Frame(select_frame, bg=tm.get("bg_primary"))
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # 滚动条
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.suit_listbox = tk.Listbox(
            list_frame,
            height=8,
            font=("Arial", 10),
            yscrollcommand=scrollbar.set,
            bg=tm.get("listbox_bg"),
            fg=tm.get("listbox_fg"),
            selectbackground=tm.get("listbox_select_bg"),
            selectforeground=tm.get("listbox_select_fg"),
        )
        self.suit_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.suit_listbox.yview)

        # 加载套装列表
        self._load_suit_list_to_dialog()

        # 手动输入套装名
        input_frame = tk.Frame(select_frame, bg=tm.get("bg_primary"))
        input_frame.pack(fill=tk.X, pady=5)

        tk.Label(
            input_frame,
            text="或输入新套装名:",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(side=tk.LEFT, padx=5)
        self.new_suit_name_var = tk.StringVar()
        tk.Entry(
            input_frame,
            textvariable=self.new_suit_name_var,
            font=("Arial", 10),
            bg=tm.get("entry_bg"),
            fg=tm.get("entry_fg"),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 保存按钮
        tk.Button(
            select_frame,
            text="添加到套装",
            command=self._on_add_to_suit,
            bg=tm.get("accent_primary"),
            fg="white",
            font=("Arial", 10, "bold"),
        ).pack(pady=10)

    def _update_current_suits_display(self):
        """更新当前所属套装显示"""
        suits = self.app.suit_loader.get_suits_for_item(
            self.job_key, self.part, self.equip_code
        )

        self.current_suits_text.config(state=tk.NORMAL)
        self.current_suits_text.delete(1.0, tk.END)

        if suits:
            for suit in suits:
                suit_name = suit.get("name", "未命名")
                # 统计套装中已配置的部位数量（新格式：只保存已配置的部位）
                items = suit.get("items", {})
                configured = len(items)
                total = len(self.app.suit_loader.PART_ORDER)
                self.current_suits_text.insert(
                    tk.END, f"• {suit_name} ({configured}/{total} 部位)\n"
                )
        else:
            self.current_suits_text.insert(tk.END, "该时装暂未加入任何套装")

        self.current_suits_text.config(state=tk.DISABLED)

    def _load_suit_list_to_dialog(self):
        """加载套装列表到对话框，按部位 code 排序（coat、pants优先）"""
        suits = self.app.suit_loader.get_suits(self.job_key)
        
        # 按部位 code 排序（coat、pants优先）
        def get_sort_key(suit):
            items = suit.get("items", {})
            
            def get_code(part):
                code = items.get(part, "")
                try:
                    return int(code) if code else -1
                except (ValueError, TypeError):
                    return code if code else ""
            
            # 优先排序 coat 和 pants
            key_parts = [get_code("coat"), get_code("pants")]
            
            # 然后按 PARTS 顺序添加其他部位
            for part in PARTS:
                if part not in ("coat", "pants"):
                    key_parts.append(get_code(part))
            
            return tuple(key_parts)
        
        sorted_suits = sorted(suits, key=get_sort_key)
        self.all_suits = [s.get("name", "未命名") for s in sorted_suits]
        self._filter_suit_list()

    def _filter_suit_list(self):
        """根据搜索条件过滤套装列表"""
        filter_text = self.suit_search_var.get().lower()
        self.suit_listbox.delete(0, tk.END)

        for suit_name in self.all_suits:
            if not filter_text or filter_text in suit_name.lower():
                self.suit_listbox.insert(tk.END, suit_name)

    def _on_add_to_suit(self):
        """添加到套装按钮点击事件"""
        # 获取选中的套装或输入的新套装名
        selection = self.suit_listbox.curselection()
        new_name = self.new_suit_name_var.get().strip()

        if new_name:
            suit_name = new_name
        elif selection:
            suit_name = self.suit_listbox.get(selection[0])
        else:
            messagebox.showwarning(
                "提示", "请选择一个套装或输入新套装名", parent=self.dialog
            )
            return

        # 检查是否已在这个套装中
        existing_suits = self.app.suit_loader.get_suits_for_item(
            self.job_key, self.part, self.equip_code
        )
        for suit in existing_suits:
            if suit.get("name") == suit_name:
                messagebox.showinfo(
                    "提示", f"该时装已在套装【{suit_name}】中", parent=self.dialog
                )
                return

        # 检查是否有冲突（该套装此部位已有其他时装）
        suits = self.app.suit_loader.get_suits(self.job_key)
        target_suit = None
        for s in suits:
            if s.get("name") == suit_name:
                target_suit = s
                break

        if target_suit:
            existing_code = target_suit.get("items", {}).get(self.part)
            if existing_code and existing_code != self.equip_code:
                # 有冲突，显示对比对话框
                if not self._show_suit_conflict_dialog(suit_name, existing_code):
                    return  # 用户取消

        # 添加到套装
        success, replaced = self.app.suit_loader.add_or_update_suit(
            self.job_key, suit_name, self.part, self.equip_code
        )

        if success:
            self._update_current_suits_display()
            self._load_suit_list_to_dialog()  # 刷新列表（新套装会出现在列表中）
            self.new_suit_name_var.set("")  # 清空输入框
            if replaced:
                messagebox.showinfo(
                    "成功",
                    f"已添加到套装【{suit_name}】\n替换了原有时装: {replaced['name']}",
                    parent=self.dialog,
                )
            else:
                messagebox.showinfo(
                    "成功", f"已添加到套装【{suit_name}】", parent=self.dialog
                )
        else:
            messagebox.showerror("错误", "添加失败", parent=self.dialog)

    def _show_suit_conflict_dialog(self, suit_name: str, existing_code: str) -> bool:
        """显示套装冲突对比对话框

        Returns:
            True - 用户确认替换，False - 用户取消
        """
        tm = self.app.theme_manager

        # 获取当前时装信息
        current_name = self.name_entry.get().strip() or f"时装{self.equip_code}"

        # 获取已存在时装信息
        existing_name = (
            self.app.suit_loader.get_item_name(self.job_key, self.part, existing_code)
            or f"时装{existing_code}"
        )

        # 创建对话框
        dialog = tk.Toplevel(self.dialog)
        dialog.title(f"套装冲突 - {suit_name}")
        dialog.transient(self.dialog)
        dialog.grab_set()
        dialog.configure(bg=tm.get("bg_primary"))
        
        # 设置大小并居中
        self.app._center_window(dialog, 600, 400)

        # 提示信息
        tk.Label(
            dialog,
            text=f"套装【{suit_name}】的【{CN_PART_NAMES.get(self.part, self.part)}】部位已有时装",
            font=("Arial", 11, "bold"),
            fg=tm.get("label_error"),
            bg=tm.get("bg_primary"),
        ).pack(pady=10)

        # 对比区域
        compare_frame = tk.Frame(dialog, bg=tm.get("bg_primary"))
        compare_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        # 左侧：当前时装
        left_frame = tk.LabelFrame(
            compare_frame,
            text="当前时装（待添加）",
            font=("Arial", 10, "bold"),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        tk.Label(
            left_frame,
            text=f"代码: {self.equip_code}",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(pady=5)
        tk.Label(
            left_frame,
            text=f"名称: {current_name}",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(pady=5)

        # 当前时装图标和预览
        left_preview_frame = tk.Frame(left_frame, bg=tm.get("bg_primary"))
        left_preview_frame.pack(pady=5)

        left_icon_frame = tk.Frame(left_preview_frame, bg=tm.get("bg_primary"))
        left_icon_frame.pack(side=tk.LEFT, padx=5)
        tk.Label(
            left_icon_frame,
            text="图标:",
            font=("Arial", 9),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack()
        self._show_equip_icon_in_dialog(left_icon_frame, self.equip_code)

        left_thumb_frame = tk.Frame(left_preview_frame, bg=tm.get("bg_primary"))
        left_thumb_frame.pack(side=tk.LEFT, padx=5)
        tk.Label(
            left_thumb_frame,
            text="预览:",
            font=("Arial", 9),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack()
        self._show_equip_thumbnail_in_dialog(left_thumb_frame, self.equip_code)

        # 右侧：已存在时装
        right_frame = tk.LabelFrame(
            compare_frame,
            text="套装内已有（将被替换）",
            font=("Arial", 10, "bold"),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        )
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        tk.Label(
            right_frame,
            text=f"代码: {existing_code}",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(pady=5)
        tk.Label(
            right_frame,
            text=f"名称: {existing_name}",
            font=("Arial", 10),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack(pady=5)

        # 已存在时装图标和预览
        right_preview_frame = tk.Frame(right_frame, bg=tm.get("bg_primary"))
        right_preview_frame.pack(pady=5)

        right_icon_frame = tk.Frame(right_preview_frame, bg=tm.get("bg_primary"))
        right_icon_frame.pack(side=tk.LEFT, padx=5)
        tk.Label(
            right_icon_frame,
            text="图标:",
            font=("Arial", 9),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack()
        self._show_equip_icon_in_dialog(right_icon_frame, existing_code)

        right_thumb_frame = tk.Frame(right_preview_frame, bg=tm.get("bg_primary"))
        right_thumb_frame.pack(side=tk.LEFT, padx=5)
        tk.Label(
            right_thumb_frame,
            text="预览:",
            font=("Arial", 9),
            bg=tm.get("bg_primary"),
            fg=tm.get("fg_primary"),
        ).pack()
        self._show_equip_thumbnail_in_dialog(right_thumb_frame, existing_code)

        # 按钮区域
        btn_frame = tk.Frame(dialog, bg=tm.get("bg_primary"))
        btn_frame.pack(fill=tk.X, pady=20, padx=20)

        result = [False]  # 使用列表存储结果

        def on_confirm():
            result[0] = True
            dialog.destroy()

        def on_cancel():
            result[0] = False
            dialog.destroy()

        tk.Button(
            btn_frame,
            text="替换",
            command=on_confirm,
            bg=tm.get("accent_danger"),
            fg="white",
            font=("Arial", 10, "bold"),
            width=12,
        ).pack(side=tk.RIGHT, padx=10)

        tk.Button(
            btn_frame,
            text="取消",
            command=on_cancel,
            bg=tm.get("bg_tertiary"),
            fg=tm.get("fg_primary"),
            font=("Arial", 10),
            width=12,
        ).pack(side=tk.RIGHT, padx=10)

        self.dialog.wait_window(dialog)
        return result[0]

    def _show_equip_icon_in_dialog(self, parent: tk.Widget, code: str):
        """在对话框中显示时装图标预览"""
        tm = self.app.theme_manager
        try:
            # 获取图标帧
            frame = self.app.suit_loader.get_icon_frame(self.job_key, self.part, code)
            if frame is None:
                tk.Label(
                    parent,
                    text="无图标",
                    font=("Arial", 9),
                    fg=tm.get("fg_tertiary"),
                    bg=tm.get("bg_primary"),
                ).pack(pady=10)
                return

            # 获取图标NPK信息
            npk_name = self.app.suit_loader.get_icon_npk_name(self.job_key)
            img_name = self.app.suit_loader.get_icon_img_name(self.job_key, self.part)

            if not npk_name or not img_name:
                tk.Label(
                    parent,
                    text="无图标",
                    font=("Arial", 9),
                    fg=tm.get("fg_tertiary"),
                    bg=tm.get("bg_primary"),
                ).pack(pady=10)
                return

            # 加载图标
            icon_img = self.app.icon_loader.get_icon(
                npk_name, img_name, frame, (56, 56)
            )
            if icon_img:
                photo = ImageTk.PhotoImage(icon_img)
                label = tk.Label(parent, image=photo, bg=tm.get("bg_primary"))
                label.image = photo  # 保持引用
                label.pack(pady=10)
            else:
                tk.Label(
                    parent,
                    text="无图标",
                    font=("Arial", 9),
                    fg=tm.get("fg_tertiary"),
                    bg=tm.get("bg_primary"),
                ).pack(pady=10)
        except Exception as e:
            tk.Label(
                parent,
                text="加载失败",
                font=("Arial", 9),
                fg=tm.get("fg_tertiary"),
                bg=tm.get("bg_primary"),
            ).pack(pady=10)

    def _show_equip_thumbnail_in_dialog(self, parent: tk.Widget, code: str):
        """在对话框中显示时装3D预览图"""
        tm = self.app.theme_manager
        try:
            # 查找时装的索引
            options = self.app.loader.part_options.get(self.part, [])
            idx = None
            for i, opt in enumerate(options):
                if opt[0] == code:
                    idx = i
                    break

            if idx is None:
                tk.Label(
                    parent,
                    text="无预览",
                    font=("Arial", 9),
                    fg=tm.get("fg_tertiary"),
                    bg=tm.get("bg_primary"),
                ).pack(pady=10)
                return

            # 生成缩略图（使用职业特定帧号）
            thumb = self.app.loader.generate_thumbnail(
                self.part, idx, (80, 80), job_key=self.job_key
            )
            if thumb:
                photo = ImageTk.PhotoImage(thumb)
                label = tk.Label(parent, image=photo, bg=tm.get("bg_primary"))
                label.image = photo  # 保持引用
                label.pack(pady=10)
            else:
                tk.Label(
                    parent,
                    text="无预览",
                    font=("Arial", 9),
                    fg=tm.get("fg_tertiary"),
                    bg=tm.get("bg_primary"),
                ).pack(pady=10)
        except Exception as e:
            tk.Label(parent, text="加载失败", font=("Arial", 9), fg="#999999").pack(
                pady=10
            )

    # ==================== 确认和取消 ====================
    def _on_confirm(self):
        name = self.name_entry.get().strip()

        # 收集隐藏部位选择
        hide_parts = [part for part, var in self.hide_parts_vars.items() if var.get()]

        # 确定当前选中的标签页
        current_tab = self.notebook.index(self.notebook.select())

        if current_tab == 0:  # 标准图标标签页

            if not name:
                name = "未知装扮"

            # 删除可能存在的自定义图标配置
            self.app.suit_loader.remove_custom_icon(
                self.job_key, self.part, self.equip_code
            )

            if self.selected_frame is None or self.selected_frame < 0:
                # ===== 无图标：保存时装信息但不保存图标 =====
                if self.app.suit_loader.save_item_without_icon(
                    self.job_key, self.part, self.equip_code, name, hide_parts
                ):
                    self.result = True
                    self.dialog.destroy()
                else:
                    messagebox.showerror("错误", "保存配置失败", parent=self.dialog)
            else:
                # ===== 有图标：正常保存 =====
                cn_part = CN_PART_NAMES.get(self.part, self.part)
                icon_marker = f"{cn_part}{self.selected_frame}"

                if self.app.suit_loader.add_or_update_item(
                    self.job_key,
                    self.part,
                    self.equip_code,
                    icon_marker,
                    name,
                    hide_parts,
                ):
                    self.result = True
                    self.dialog.destroy()
                else:
                    messagebox.showerror("错误", "更新配置失败", parent=self.dialog)

        else:  # 自定义图标标签页
            if self.selected_custom_img is None or self.selected_custom_frame is None:
                messagebox.showwarning(
                    "提示", "请选择IMG路径和图标帧", parent=self.dialog
                )
                return

            if not name:
                name = "未知装扮"

            # 保存自定义图标配置
            self.app.suit_loader.add_custom_icon(
                self.job_key,
                self.part,
                self.equip_code,
                self.selected_custom_img,
                self.selected_custom_frame,
            )

            # 如果装扮表中有记录，更新名称和隐藏部位（但不修改图标标记）
            existing_name = self.app.suit_loader.get_item_name(
                self.job_key, self.part, self.equip_code
            )
            if existing_name is not None:
                # 获取现有的图标标记
                frame = self.app.suit_loader.get_icon_frame(
                    self.job_key, self.part, self.equip_code
                )
                if frame is not None:
                    cn_part = CN_PART_NAMES.get(self.part, self.part)
                    icon_marker = f"{cn_part}{frame}"
                    self.app.suit_loader.add_or_update_item(
                        self.job_key,
                        self.part,
                        self.equip_code,
                        icon_marker,
                        name,
                        hide_parts,
                    )
            else:
                # 仅更新隐藏部位
                self.app.suit_loader.update_item_hide_parts(
                    self.job_key, self.part, self.equip_code, hide_parts
                )

            self.result = True
            self.dialog.destroy()

    def _on_delete(self):
        """删除记录"""
        # 删除装扮表记录
        deleted_avatar = self.app.suit_loader.delete_item(
            self.job_key, self.part, self.equip_code
        )
        # 删除自定义图标配置
        deleted_custom = self.app.suit_loader.remove_custom_icon(
            self.job_key, self.part, self.equip_code
        )

        if deleted_avatar or deleted_custom:
            self.result = True
            messagebox.showinfo("提示", "记录已删除", parent=self.dialog)
            self.dialog.destroy()
        else:
            messagebox.showinfo("提示", "该时装无记录可删除", parent=self.dialog)

    def _on_cancel(self):
        self.dialog.destroy()


def main():
    root = tk.Tk()
    app = DressingRoomApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
