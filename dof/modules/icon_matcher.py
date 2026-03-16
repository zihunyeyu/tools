"""
Icon Matcher - ICON 图标对比匹配器

功能：
1. 构建标准 NPK 图标缓存（按职业+部位组织）
2. 构建 PVF NPK 映射表（img_path → npk_file）
3. 提取 sprite 并转换为 numpy 数组
4. 像素级对比匹配，找到相同图标的标准帧号

使用示例:
    matcher = IconMatcher(
        standard_npk_dir=r"E:\\DOF\\Tools\\blackcat.6.12\\output\\Download\\中国大陆-魔界",
        pvf_npk_dir=r"D:\\BaiduNetdiskDownload\\ImagePacks2"
    )
    matcher.build_standard_cache()
    matcher.build_pvf_npk_map()
    
    # 查找匹配
    result = matcher.find_matching_frame(
        job='atfighter',
        part='cap',
        pvf_img='item/avatar/custom_folder/fm_acap.img',
        pvf_frame=10
    )
    # 返回: 标准NPK中的帧号，或 None
"""

import json
import logging
import re
import pickle
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from PIL import Image
from dataclasses import dataclass, field

from pydoftools.npk import NPK

logger = logging.getLogger(__name__)


@dataclass
class SpriteData:
    """Sprite 数据类"""
    npk_file: str           # 所属 NPK 文件名
    img_path: str           # IMG 文件路径（NPK内部）
    frame: int              # 帧号
    width: int              # 宽度
    height: int             # 高度
    pixel_array: np.ndarray = field(repr=False)  # 像素矩阵 (H, W, 4) RGBA
    
    def get_key(self) -> str:
        """生成唯一键"""
        return f"{self.npk_file}#{self.img_path}#{self.frame}"


class IconMatcher:
    """
    ICON 图标对比匹配器
    
    用于将 PVF equ 中的非标准 icon 路径匹配到标准 NPK 中的对应帧
    """
    
    # 标准职业目录列表（小写）
    VALID_JOBS = {'swordman', 'fighter', 'atfighter', 'gunner', 'atgunner', 
                  'mage', 'atmage', 'priest', 'thief'}
    
    # 部位列表
    VALID_PARTS = {'cap', 'hair', 'face', 'neck', 'coat', 'pants', 'belt', 'shoes', 'skin'}
    
    # 标准NPK文件名模式: sprite_item_avatar_{job}.NPK
    STANDARD_NPK_PATTERN = re.compile(r'sprite_item_avatar_(\w+)\.npk$', re.IGNORECASE)
    
    # 标准IMG路径模式: sprite/item/avatar/{job}/{prefix}_a{part}.img
    STANDARD_IMG_PATTERN = re.compile(
        r'sprite/item/avatar/(\w+)/\w+_a(cap|coat|hair|face|neck|pants|belt|shoes|skin|body)\.img$',
        re.IGNORECASE
    )
    
    def __init__(
        self,
        standard_npk_dir: str,
        pvf_npk_dir: str,
        cache_dir: Optional[str] = None,
        use_cache: bool = True
    ):
        """
        初始化匹配器
        
        Args:
            standard_npk_dir: 标准NPK目录路径（包含 sprite_item_avatar_xxx.NPK）
            pvf_npk_dir: PVF NPK目录路径（需要遍历生成映射）
            cache_dir: 缓存目录路径（用于缓存标准图标数据）
            use_cache: 是否使用缓存
        """
        self.standard_npk_dir = Path(standard_npk_dir)
        self.pvf_npk_dir = Path(r'E:\DOF\Clients\DNF\ImagePacks2')
        self.cache_dir = Path(cache_dir) if cache_dir else Path(__file__).parent.parent / 'icon_cache'
        self.use_cache = use_cache
        
        # 标准图标缓存: {(job, part, img_path): [SpriteData, ...]}
        self.standard_cache: Dict[Tuple[str, str, str], List[SpriteData]] = {}
        
        # 按像素hash索引的缓存: {pixel_hash: [(job, part, img_path, frame), ...]}
        self.pixel_index: Dict[str, List[Tuple[str, str, str, int]]] = {}
        
        # PVF NPK映射: {img_path -> npk_file_path}
        self.pvf_npk_map: Dict[str, Path] = {}
        
        # NPK文件句柄缓存（避免重复打开）
        self._npk_handles: Dict[Path, NPK] = {}
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_file(self, job: str) -> Path:
        """获取指定职业的缓存文件路径"""
        return self.cache_dir / f"standard_cache_{job}.pkl"
    
    def _compute_pixel_hash(self, pixel_array: np.ndarray) -> str:
        """
        计算像素数组的哈希值，用于快速索引
        
        Args:
            pixel_array: 像素数组 (H, W, C)
            
        Returns:
            哈希字符串
        """
        # 使用数组的tobytes和shape生成唯一标识
        return f"{pixel_array.shape}_{hash(pixel_array.tobytes()) & 0xFFFFFFFF:08x}"
    
    def _extract_sprite_to_numpy(
        self,
        npk_file: Path,
        img_path: str,
        frame: int,
        palette_index: int = 0
    ) -> Optional[np.ndarray]:
        """
        从 NPK 中提取指定 IMG 的指定帧，转换为 numpy 数组
        
        Args:
            npk_file: NPK 文件路径
            img_path: IMG 文件路径（NPK内部路径）
            frame: 帧号
            palette_index: 调色板索引（用于调色板模式）
            
        Returns:
            numpy 数组 (H, W, 4) RGBA，失败返回 None
        """
        try:
            # 获取或创建 NPK 句柄
            if npk_file not in self._npk_handles:
                with open(npk_file, 'rb') as f:
                    npk = NPK.open(f)
                    npk.load_all()
                    self._npk_handles[npk_file] = npk
            
            npk = self._npk_handles[npk_file]
            
            # 查找指定 IMG
            target_img_file = None
            for npk_file_obj in npk.files:
                if npk_file_obj.name.lower() == img_path.lower():
                    target_img_file = npk_file_obj
                    break
            
            if not target_img_file:
                logger.warning(f"IMG not found: {img_path} in {npk_file}")
                return None
            
            # 加载 IMG
            img = target_img_file.to_img()
            
            if not img.images or frame >= len(img.images):
                logger.warning(f"Invalid frame {frame} for {img_path}")
                return None
            
            # 提取 sprite
            sprite = img.image_by_index(frame)
            
            # 使用统一的转换方法（处理 ImageLink 等）
            return self._convert_sprite_to_numpy(sprite, img)
            
        except Exception as e:
            logger.error(f"Error extracting sprite from {npk_file}#{img_path}#{frame}: {e}")
            return None
    
    def _is_sprite_equal(self, arr1: np.ndarray, arr2: np.ndarray) -> bool:
        """
        比较两个 sprite 数组是否完全相同
        
        Args:
            arr1: 第一个数组 (H, W, 4)
            arr2: 第二个数组 (H, W, 4)
            
        Returns:
            是否完全相同
        """
        if arr1.shape != arr2.shape:
            return False
        return np.array_equal(arr1, arr2)
    
    def build_standard_cache(self, force_rebuild: bool = False) -> None:
        """
        构建标准图标缓存
        
        遍历标准NPK目录，提取所有职业的avatar图标并缓存
        
        Args:
            force_rebuild: 强制重新构建，忽略缓存文件
        """
        logger.info(f"Building standard icon cache from: {self.standard_npk_dir}")
        
        # 查找所有标准NPK文件
        npk_files = list(self.standard_npk_dir.glob("sprite_item_avatar_*.NPK"))
        logger.info(f"Found {len(npk_files)} standard NPK files")
        
        for npk_file in npk_files:
            match = self.STANDARD_NPK_PATTERN.match(npk_file.name)
            if not match:
                continue
            
            job = match.group(1).lower()
            if job not in self.VALID_JOBS:
                logger.warning(f"Unknown job in NPK filename: {job}")
                continue
            
            cache_file = self._get_cache_file(job)
            
            # 尝试加载缓存
            if not force_rebuild and self.use_cache and cache_file.exists():
                logger.info(f"Loading cache for {job}: {cache_file}")
                try:
                    with open(cache_file, 'rb') as f:
                        cached_data = pickle.load(f)
                        for key, sprite_list in cached_data.items():
                            self.standard_cache[key] = sprite_list
                            # 更新像素索引
                            for sprite in sprite_list:
                                pixel_hash = self._compute_pixel_hash(sprite.pixel_array)
                                if pixel_hash not in self.pixel_index:
                                    self.pixel_index[pixel_hash] = []
                                self.pixel_index[pixel_hash].append(
                                    (key[0], key[1], key[2], sprite.frame)
                                )
                    continue
                except Exception as e:
                    logger.warning(f"Failed to load cache for {job}: {e}")
            
            # 解析NPK文件
            logger.info(f"Processing {npk_file.name}...")
            self._process_standard_npk(npk_file, job)
            
            # 保存缓存
            if self.use_cache:
                self._save_job_cache(job)
        
        total_sprites = sum(len(v) for v in self.standard_cache.values())
        logger.info(f"Standard cache built: {len(self.standard_cache)} entries, {total_sprites} sprites")
    
    def _process_standard_npk(self, npk_file: Path, job: str) -> None:
        """
        处理单个标准NPK文件
        
        Args:
            npk_file: NPK文件路径
            job: 职业名称
        """
        try:
            with open(npk_file, 'rb') as f:
                npk = NPK.open(f)
                npk.load_all()
            
            for npk_file_obj in npk.files:
                img_path = npk_file_obj.name
                
                # 检查是否是标准IMG路径
                match = self.STANDARD_IMG_PATTERN.match(img_path)
                if not match:
                    continue
                
                extracted_job = match.group(1).lower()
                part = match.group(2).lower()
                
                # 验证职业匹配
                if extracted_job != job:
                    continue
                
                if part not in self.VALID_PARTS:
                    continue
                
                # 加载IMG并提取所有帧
                try:
                    img = npk_file_obj.to_img()
                    if not img.images:
                        continue
                    
                    cache_key = (job, part, img_path)
                    sprite_list: List[SpriteData] = []
                    
                    for frame_idx in range(len(img.images)):
                        try:
                            sprite = img.image_by_index(frame_idx)
                            
                            # 转换为numpy数组（会自动处理 ImageLink）
                            pixel_array = self._convert_sprite_to_numpy(sprite, img)
                            if pixel_array is None:
                                continue
                            
                            # 获取实际尺寸
                            h, w = pixel_array.shape[:2]
                            
                            sprite_data = SpriteData(
                                npk_file=npk_file.name,
                                img_path=img_path,
                                frame=frame_idx,
                                width=w,
                                height=h,
                                pixel_array=pixel_array
                            )
                            sprite_list.append(sprite_data)
                            
                            # 更新像素索引
                            pixel_hash = self._compute_pixel_hash(pixel_array)
                            if pixel_hash not in self.pixel_index:
                                self.pixel_index[pixel_hash] = []
                            self.pixel_index[pixel_hash].append((job, part, img_path, frame_idx))
                        
                        except Exception as e:
                            logger.debug(f"Error processing frame {frame_idx} in {img_path}: {e}")
                            continue
                    
                    if sprite_list:
                        self.standard_cache[cache_key] = sprite_list
                        logger.debug(f"Cached {len(sprite_list)} sprites for {job}/{part}/{img_path}")
                
                except Exception as e:
                    logger.warning(f"Error processing IMG {img_path}: {e}")
        
        except Exception as e:
            logger.error(f"Error processing NPK {npk_file}: {e}")
    
    def _convert_sprite_to_numpy(self, sprite, img) -> Optional[np.ndarray]:
        """
        将 sprite 转换为 numpy 数组 (RGBA)
        
        使用 img.build() 方法正确处理各种格式（包括 Zlib 压缩）
        
        Args:
            sprite: pydoftools sprite 对象
            img: pydoftools img 对象
            
        Returns:
            numpy 数组 (H, W, 4) RGBA
        """
        try:
            # 首先尝试使用 img.build() 方法（正确处理 Zlib 压缩和各种格式）
            try:
                pil_img = img.build(sprite)
                if pil_img is not None:
                    # 转换为 RGBA 模式
                    if pil_img.mode != 'RGBA':
                        pil_img = pil_img.convert('RGBA')
                    # 转换为 numpy 数组
                    return np.array(pil_img)
            except Exception as e:
                logger.debug(f"img.build() failed: {e}")
            
            # 回退：检查是否是 ImageLink
            if hasattr(sprite, 'link'):
                logger.debug(f"ImageLink detected: {sprite.link}")
                return self._resolve_image_link(img, sprite)
            
            # 检查是否有 w/h 属性
            if not hasattr(sprite, 'w') or not hasattr(sprite, 'h'):
                logger.debug(f"Sprite missing w/h attributes")
                return None
            
            w, h = sprite.w, sprite.h
            
            # 检查 data 是否存在
            if not hasattr(sprite, 'data') or sprite.data is None:
                logger.debug(f"Sprite has no data")
                return None
            
            data_len = len(sprite.data)
            expected_size_rgba = w * h * 4
            expected_size_rgb = w * h * 3
            expected_size_index = w * h
            
            if data_len == expected_size_rgba:
                # RGBA 格式
                return np.frombuffer(sprite.data, dtype=np.uint8).reshape((h, w, 4))
            
            elif data_len == expected_size_rgb:
                # RGB 格式，添加 Alpha 通道
                rgb = np.frombuffer(sprite.data, dtype=np.uint8).reshape((h, w, 3))
                return np.dstack([rgb, np.full((h, w), 255, dtype=np.uint8)])
            
            elif data_len == expected_size_index:
                # 调色板模式
                if hasattr(img, 'color_boards') and img.color_boards:
                    palette = img.color_boards[0]
                    indices = np.frombuffer(sprite.data, dtype=np.uint8).reshape((h, w))
                    colors = np.array(palette.colors, dtype=np.uint8)
                    return colors[indices]
            
            logger.debug(f"Unknown data format: {data_len} bytes for {w}x{h} image")
            return None
        
        except Exception as e:
            logger.debug(f"Error converting sprite to numpy: {e}")
            return None
    
    def _resolve_image_link(self, img, link_sprite) -> Optional[np.ndarray]:
        """
        解析 ImageLink 链接，获取实际的图像数据
        
        Args:
            img: pydoftools img 对象
            link_sprite: ImageLink 对象
            
        Returns:
            numpy 数组，失败返回 None
        """
        try:
            # ImageLink 通常有 target 或 link 属性指向目标帧
            # 尝试不同的属性名
            target_idx = None
            
            if hasattr(link_sprite, 'target'):
                target_idx = link_sprite.target
            elif hasattr(link_sprite, 'link'):
                target_idx = link_sprite.link
            elif hasattr(link_sprite, 'target_index'):
                target_idx = link_sprite.target_index
            
            if target_idx is None:
                return None
            
            # 确保目标索引有效
            if not img.images or target_idx < 0 or target_idx >= len(img.images):
                return None
            
            # 递归解析（防止循环链接）
            target_sprite = img.image_by_index(target_idx)
            if target_sprite is link_sprite:
                return None  # 避免循环
            
            return self._convert_sprite_to_numpy(target_sprite, img)
        
        except Exception as e:
            logger.debug(f"Error resolving image link: {e}")
            return None
    
    def _save_job_cache(self, job: str) -> None:
        """保存指定职业的缓存"""
        cache_file = self._get_cache_file(job)
        
        # 收集该职业的所有缓存
        job_cache = {}
        for key, sprite_list in self.standard_cache.items():
            if key[0] == job:
                job_cache[key] = sprite_list
        
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(job_cache, f)
            logger.info(f"Saved cache for {job}: {len(job_cache)} entries")
        except Exception as e:
            logger.error(f"Failed to save cache for {job}: {e}")
    
    def build_pvf_npk_map(self) -> None:
        """
        构建 PVF NPK 映射表
        
        遍历PVF NPK目录，建立 img_path → npk_file 映射
        """
        logger.info(f"Building PVF NPK map from: {self.pvf_npk_dir}")
        
        npk_files = list(self.pvf_npk_dir.glob("*.NPK"))
        logger.info(f"Found {len(npk_files)} PVF NPK files")
        
        total_imgs = 0
        for npk_file in npk_files:
            try:
                with open(npk_file, 'rb') as f:
                    npk = NPK.open(f)
                    npk.load_all()
                
                for npk_file_obj in npk.files:
                    img_path = npk_file_obj.name.lower()  # 使用小写以便匹配
                    if img_path not in self.pvf_npk_map:
                        self.pvf_npk_map[img_path] = npk_file
                        total_imgs += 1
            
            except Exception as e:
                logger.warning(f"Error reading {npk_file}: {e}")
        
        logger.info(f"PVF NPK map built: {len(self.pvf_npk_map)} unique IMG paths")
    
    def find_matching_frame(
        self,
        job: str,
        part: str,
        pvf_img: str,
        pvf_frame: int
    ) -> Optional[int]:
        """
        查找 PVF 图标在标准 NPK 中的匹配帧号
        
        Args:
            job: 职业（如 'atfighter'）
            part: 部位（如 'cap'）
            pvf_img: PVF中的IMG路径（如 'item/avatar/custom_folder/fm_acap.img'）
            pvf_frame: PVF中的帧号
            
        Returns:
            匹配的标准帧号，未找到返回 None
        """
        job = job.lower()
        part = part.lower()
        pvf_img_lower = pvf_img.lower()
        
        # 验证职业和部位
        if job not in self.VALID_JOBS:
            logger.warning(f"Invalid job: {job}")
            return None
        if part not in self.VALID_PARTS:
            logger.warning(f"Invalid part: {part}")
            return None
        
        # 1. 从PVF NPK中提取目标图标
        target_np_array = self._extract_from_pvf(pvf_img_lower, pvf_frame)
        if target_np_array is None:
            logger.warning(f"Failed to extract sprite from PVF: {pvf_img}#{pvf_frame}")
            return None
        
        # 2. 先在像素索引中快速查找
        pixel_hash = self._compute_pixel_hash(target_np_array)
        if pixel_hash in self.pixel_index:
            matches = self.pixel_index[pixel_hash]
            # 筛选同一职业和部位的匹配
            for m_job, m_part, m_img_path, m_frame in matches:
                if m_job == job and m_part == part:
                    # 验证数组确实相同
                    cache_key = (job, part, m_img_path)
                    if cache_key in self.standard_cache:
                        for sprite in self.standard_cache[cache_key]:
                            if sprite.frame == m_frame:
                                if self._is_sprite_equal(target_np_array, sprite.pixel_array):
                                    logger.debug(f"Fast match found: {m_img_path}#{m_frame}")
                                    return m_frame
        
        # 3. 在标准缓存中逐一遍历对比
        logger.debug(f"Falling back to full comparison for {job}/{part}")
        
        for cache_key, sprite_list in self.standard_cache.items():
            c_job, c_part, c_img_path = cache_key
            if c_job != job or c_part != part:
                continue
            
            for sprite in sprite_list:
                if self._is_sprite_equal(target_np_array, sprite.pixel_array):
                    logger.debug(f"Match found: {c_img_path}#{sprite.frame}")
                    return sprite.frame
        
        logger.debug(f"No match found for {pvf_img}#{pvf_frame}")
        return None
    
    def _extract_from_pvf(self, img_path: str, frame: int) -> Optional[np.ndarray]:
        """
        从PVF NPK中提取指定IMG的指定帧
        
        Args:
            img_path: IMG路径（小写）
            frame: 帧号
            
        Returns:
            numpy 数组，失败返回 None
        """
        # 转换路径格式: item/avatar/.../xxx.img -> sprite/item/avatar/.../xxx.img
        # 处理非标准路径，添加 sprite/ 前缀
        lookup_path = img_path
        if not img_path.startswith('sprite/'):
            lookup_path = f"sprite/{img_path}"
        
        # 查找NPK文件
        npk_file = self.pvf_npk_map.get(lookup_path)
        
        # 如果没找到，尝试搜索（有时候路径可能有大小写差异）
        if not npk_file:
            for path, file in self.pvf_npk_map.items():
                if path.lower() == lookup_path.lower():
                    npk_file = file
                    break
        
        # 如果还是没找到，尝试原始路径（有些可能本来就是标准路径）
        if not npk_file:
            npk_file = self.pvf_npk_map.get(img_path)
            if not npk_file:
                for path, file in self.pvf_npk_map.items():
                    if path.lower() == img_path.lower():
                        npk_file = file
                        break
        
        if not npk_file:
            logger.warning(f"IMG not found in PVF NPK map: {img_path} (tried: {lookup_path})")
            return None
        
        return self._extract_sprite_to_numpy(npk_file, lookup_path if lookup_path in self.pvf_npk_map else img_path, frame)
    
    def find_all_matching_frames(
        self,
        job: str,
        part: str,
        pvf_img: str,
        pvf_frame: int
    ) -> List[int]:
        """
        查找所有匹配的帧号（用于调试多对一情况）
        
        Args:
            job: 职业
            part: 部位
            pvf_img: PVF IMG路径
            pvf_frame: PVF帧号
            
        Returns:
            所有匹配的标准帧号列表
        """
        job = job.lower()
        part = part.lower()
        pvf_img_lower = pvf_img.lower()
        
        target_np_array = self._extract_from_pvf(pvf_img_lower, pvf_frame)
        if target_np_array is None:
            return []
        
        matches = []
        for cache_key, sprite_list in self.standard_cache.items():
            c_job, c_part, c_img_path = cache_key
            if c_job != job or c_part != part:
                continue
            
            for sprite in sprite_list:
                if self._is_sprite_equal(target_np_array, sprite.pixel_array):
                    matches.append(sprite.frame)
        
        return matches
    
    def close(self) -> None:
        """关闭所有NPK句柄，释放资源"""
        self._npk_handles.clear()
        logger.info("IconMatcher resources released")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
