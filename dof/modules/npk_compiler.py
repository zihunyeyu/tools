"""
NPK Compiler - NPK 文件合并器

合并基础 NPK 和其他区服的 NPK 文件。
"""

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import List, Optional, Set, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pydoftools.npk import NPK
from config import NPK_INPUT_DIR, NPK_BASE_DIR, NPK_COMPILE_DIR

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NpkFileFinder:
    """NPK 文件查找器"""
    
    @staticmethod
    def find_files_containing_name(
        target_dir: Path,
        keyword: str,
        recursive: bool = True,
        ignore_case: bool = True,
        exclude_suffixes: Optional[Set[str]] = None
    ) -> List[Path]:
        """
        查找文件名包含关键词的文件
        
        Args:
            target_dir: 要查找的文件夹路径
            keyword: 要匹配的文件名关键词
            recursive: 是否递归查找子文件夹
            ignore_case: 是否忽略大小写
            exclude_suffixes: 要排除的文件后缀集合
            
        Returns:
            匹配的文件路径列表
        """
        target_dir = Path(target_dir)
        if not target_dir.is_dir():
            logger.warning(f"目录不存在或不是文件夹: {target_dir}")
            return []
        
        exclude_suffixes = exclude_suffixes or set()
        exclude_suffixes = {
            s if s.startswith('.') else f'.{s}' 
            for s in exclude_suffixes
        }
        
        keyword_compare = keyword.lower() if ignore_case else keyword
        matched_files: List[Path] = []
        
        # 选择遍历方式
        glob_pattern = "**/*" if recursive else "*"
        
        for item in target_dir.glob(glob_pattern):
            if not item.is_file():
                continue
            
            # 排除指定后缀
            if item.suffix in exclude_suffixes:
                continue
            
            # 文件名匹配
            file_name = item.name.lower() if ignore_case else item.name
            if keyword_compare in file_name:
                matched_files.append(item)
        
        return matched_files


class NpkCompiler:
    """NPK 编译器（合并器）"""
    
    def __init__(
        self,
        input_dirs: List[Path],
        output_dir: Path
    ):
        """
        初始化编译器
        
        Args:
            input_dirs: NPK 文件夹列表，按顺序依次合并
                       第一个文件夹为基础，后面的依次合并进去
            output_dir: 输出文件夹
        """
        # 支持单个路径或路径列表
        if isinstance(input_dirs, (str, Path)):
            self.input_dirs = [Path(input_dirs)]
        else:
            self.input_dirs = [Path(d) for d in input_dirs]
        
        self.output_dir = Path(output_dir)
        self._processed = 0
        self._failed = 0
    
    @staticmethod
    def _extract_layer_and_code(filename: str) -> Optional[Tuple[str, int, str]]:
        """
        从文件名提取图层名、代码和图层后缀
        
        支持格式:
        - sm_coat0000a.img → ("coat", 0, "a")
        - fm_claw7800a1.img → ("claw", 7800, "a")
        - sprite/.../sm_coat0000b.img → ("coat", 0, "b")
        
        Args:
            filename: IMG文件名
            
        Returns:
            (layer_name, code, layer_suffix) 或 None
        """
        # 提取纯文件名（去掉路径）
        basename = filename.lower().split('/')[-1].split('\\')[-1]
        
        # 去掉 .img 后缀
        if basename.endswith('.img'):
            basename = basename[:-4]
        
        # 匹配模式: [前缀_][图层名][代码][后缀][数字]
        # 例如: sm_coat0000a, fm_claw7800a1, coat0000b
        # 图层名是最后的字母部分在数字之前
        
        # 从后往前找：最后的数字后面的字母是图层后缀，再往前是代码，再往前是图层名
        # coat0000a → coat + 0000 + a
        # claw7800a1 → claw + 7800 + a + 1 (最后的数字是调色板索引，忽略)
        
        # 找到最后一个数字序列和其后的字母
        match = re.search(r'([a-z]+)(\d+)([a-z])', basename)
        if match:
            layer_name = match.group(1)   # coat, claw 等
            code = int(match.group(2))    # 0000, 7800 等
            layer_suffix = match.group(3) # a, b, c...
            return (layer_name, code, layer_suffix)
        
        # 尝试只匹配数字（无后缀，默认a层）
        match = re.search(r'([a-z]+)(\d+)$', basename)
        if match:
            layer_name = match.group(1)
            code = int(match.group(2))
            return (layer_name, code, "a")
        
        return None
    
    def _resolve_code_conflicts(self, files: list) -> Tuple[list, Set[str], dict]:
        """
        解决同名 IMG 文件的冲突
        
        策略：
        1. 只处理同名文件（完全相同的文件名）
        2. 对于同名的 IMGv6 文件，保留调色板数量更多的版本
        3. 不处理代码冲突，不处理 IMGv6 展开范围
        4. 不同名的文件全部保留
        
        Args:
            files: NPK文件列表
            
        Returns:
            (保留的文件列表, 被移除的文件名集合, 统计信息字典)
        """
        # 按文件名分组
        files_by_name = defaultdict(list)  # {file_name: [file_obj, ...]}
        
        for file in files:
            files_by_name[file.name].append(file)
        
        files_to_keep = []
        files_to_remove = set()
        stats = {
            "duplicates": 0,  # 同名文件数量
            "palette_upgrades": 0,  # 调色板升级次数
            "total_removed": 0
        }
        
        for file_name, file_list in files_by_name.items():
            if len(file_list) == 1:
                # 没有同名文件，直接保留
                files_to_keep.append(file_list[0])
                continue
            
            # 有同名文件，需要比较调色板
            stats["duplicates"] += len(file_list) - 1
            
            # 找出调色板最多的版本（优先 IMGv6）
            best_file = file_list[0]
            best_palette_count = 0
            best_version = 0
            
            for file in file_list:
                try:
                    img = file.to_img()
                    palette_count = 0
                    version = img.version
                    
                    if version == 6 and hasattr(img, 'color_boards') and img.color_boards:
                        palette_count = len(img.color_boards)
                    elif version == 4 and hasattr(img, 'color_board') and img.color_board:
                        palette_count = 1
                    
                    # 选择调色板更多的，如果相同则选择版本更新的
                    if (palette_count > best_palette_count or 
                        (palette_count == best_palette_count and version > best_version)):
                        best_file = file
                        best_palette_count = palette_count
                        best_version = version
                        
                except Exception:
                    pass
            
            # 保留最优版本，删除其他同名文件
            files_to_keep.append(best_file)
            for file in file_list:
                if file is not best_file:
                    files_to_remove.add(file.name)
                    if best_palette_count > 0:
                        stats["palette_upgrades"] += 1
                        logger.info(
                            f"  [调色板升级] {file_name}: {best_file.name} ({best_palette_count}p)"
                        )
        
        stats["total_removed"] = len(files_to_remove)
        return files_to_keep, files_to_remove, stats
    
    def _merge_additional_npks(self, npk: NPK, file_name: str, input_dirs: List[Path]) -> tuple:
        """
        从额外的输入文件夹中合并同名 NPK 文件
        
        合并所有文件（包括同名的，后续通过 _resolve_code_conflicts 处理冲突）
        
        Args:
            npk: 当前 NPK 对象
            file_name: 文件名（不含扩展名）
            input_dirs: 要合并的输入文件夹列表（按顺序）
            
        Returns:
            (合并后的 NPK 对象, 合并的文件数量)
        """
        merged_count = 0
        
        for input_dir in input_dirs:
            if not input_dir.exists():
                continue
                
            # 查找该目录中的同名文件（精确匹配，忽略大小写）
            matching_files = [
                f for f in input_dir.glob("*.npk") 
                if f.stem.lower() == file_name.lower()
            ]
            
            for file_path in matching_files:
                try:
                    with open(file_path, "rb") as f:
                        additional_npk = NPK.open(f)
                        additional_npk.load_all()
                        
                        # 合并所有文件（包括同名的）
                        if additional_npk.files:
                            npk.files.extend(additional_npk.files)
                            merged_count += len(additional_npk.files)
                            logger.debug(f"    从 {file_path} 合并 {len(additional_npk.files)} 个文件")
                        
                except Exception as e:
                    logger.warning(f"    合并失败 {file_path}: {e}")
        
        return npk, merged_count
    
    def _deduplicate_npk(self, npk: NPK) -> tuple:
        """
        去除 NPK 中的重复文件，按文件名排序。
        对于 IMGv6 格式，调色板数量多的优先保留。
        
        Args:
            npk: NPK 对象
            
        Returns:
            (去重并排序后的 NPK 对象, 是否有 IMG 被覆盖)
        """
        unique_dict: dict = {}
        overwritten = []
        
        for file in npk.files:
            if file.name not in unique_dict:
                unique_dict[file.name] = file
            else:
                # 存在同名文件，比较调色板数量（仅针对 IMGv6）
                existing = unique_dict[file.name]
                try:
                    existing_img = existing.to_img()
                    new_img = file.to_img()
                    
                    # 只有都是 IMGv6 时才比较调色板
                    if (existing_img.version == 6 and new_img.version == 6):
                        existing_palettes = len(existing_img.color_boards)
                        new_palettes = len(new_img.color_boards)
                        
                        if new_palettes > existing_palettes:
                            unique_dict[file.name] = file
                            overwritten.append((file.name, new_palettes, existing_palettes))
                    else:
                        # 非 IMGv6 或版本不同，保留后出现的
                        unique_dict[file.name] = file
                except Exception:
                    # 转换失败，保留后出现的
                    unique_dict[file.name] = file
        
        # 按文件名排序
        sorted_files = sorted(unique_dict.values(), key=lambda f: f.name)
        
        npk.files.clear()
        npk.files.extend(sorted_files)
        
        return npk, overwritten
    
    def _process_single_file(self, file_name: str) -> bool:
        """
        处理单个 NPK 文件（从多个输入文件夹中合并）
        
        Args:
            file_name: NPK 文件名（如 "sprite_character_swordman.npk"）
            
        Returns:
            True 如果成功，False 如果失败
        """
        try:
            # 从第一个文件夹加载基础 NPK
            base_dir = self.input_dirs[0]
            base_path = base_dir / file_name
            
            if not base_path.exists():
                logger.warning(f"基础文件不存在: {base_path}")
                return False
            
            with open(base_path, "rb") as f:
                npk = NPK.open(f)
                npk.load_all()
            
            original_count = len(npk.files)
            total_conflicts = 0
            
            # 第1步：解决同名文件冲突（保留调色板更多的 IMGv6）
            resolved_files, internal_removed, internal_stats = self._resolve_code_conflicts(npk.files)
            if internal_stats["total_removed"] > 0:
                total_conflicts += internal_stats["total_removed"]
                logger.info(
                    f"  基础去重: 移除 {internal_stats['total_removed']} 个重复 "
                    f"(同名冲突:{internal_stats.get('duplicates', 0)}, "
                    f"调色板升级:{internal_stats.get('palette_upgrades', 0)})"
                )
            npk.files.clear()
            npk.files.extend(resolved_files)
            
            # 第2步：依次合并其他文件夹中的同名 NPK（合并所有文件）
            if len(self.input_dirs) > 1:
                additional_dirs = self.input_dirs[1:]
                npk, merged_img_count = self._merge_additional_npks(
                    npk, base_path.stem, additional_dirs
                )
                if merged_img_count > 0:
                    logger.info(f"  合并: 新增 {merged_img_count} 个文件")
            
            # 第3步：解决合并后的同名文件冲突
            resolved_files, merge_removed, merge_stats = self._resolve_code_conflicts(npk.files)
            if merge_stats["total_removed"] > 0:
                total_conflicts += merge_stats["total_removed"]
                logger.info(
                    f"  合并去重: 移除 {merge_stats['total_removed']} 个重复 "
                    f"(同名冲突:{merge_stats.get('duplicates', 0)}, "
                    f"调色板升级:{merge_stats.get('palette_upgrades', 0)})"
                )
            npk.files.clear()
            npk.files.extend(resolved_files)
            
            # 第4步：去重同名文件（最终保底）
            npk, overwritten = self._deduplicate_npk(npk)
            final_count = len(npk.files)
            
            # 保存
            output_path = self.output_dir / file_name
            with open(output_path, 'wb') as out_io:
                npk.save(out_io, True)
            
            # 只有在有变化时才输出日志
            has_change = (final_count != original_count) or bool(overwritten) or (total_conflicts > 0)
            if has_change:
                for name, new_p, old_p in overwritten:
                    logger.info(f"  覆盖 {name}: {new_p} > {old_p} 调色板")
                logger.info(f"✓ {file_name}: {original_count} -> {final_count} 个文件 (解决 {total_conflicts} 个冲突)")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ 处理失败 {file_name}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def _collect_npk_names(self) -> Set[str]:
        """
        收集第一个输入文件夹中的所有 NPK 文件名
        
        Returns:
            NPK 文件名集合
        """
        base_dir = self.input_dirs[0]
        if not base_dir.exists():
            logger.error(f"基础输入目录不存在: {base_dir}")
            return set()
        
        npk_names = set()
        for npk_file in base_dir.glob("*.npk"):
            npk_names.add(npk_file.name)
        
        return npk_names
    
    def compile(self) -> dict:
        """
        执行编译流程
        
        从第一个文件夹获取基础 NPK，依次合并其他文件夹中的同名 NPK
        
        Returns:
            统计信息字典
        """
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查输入目录
        if not self.input_dirs:
            logger.error("未指定输入目录")
            return {"processed": 0, "failed": 0, "total": 0}
        
        if not self.input_dirs[0].exists():
            logger.error(f"基础输入目录不存在: {self.input_dirs[0]}")
            return {"processed": 0, "failed": 0, "total": 0}
        
        # 显示配置
        logger.info(f"输入目录 ({len(self.input_dirs)} 个):")
        for i, input_dir in enumerate(self.input_dirs):
            marker = " [基础]" if i == 0 else " [合并]"
            exists = "✓" if input_dir.exists() else "✗"
            logger.info(f"  {exists} {input_dir}{marker}")
        
        # 收集基础文件夹中的所有 NPK 文件名
        npk_names = self._collect_npk_names()
        if not npk_names:
            logger.error(f"在 {self.input_dirs[0]} 中未找到 NPK 文件")
            return {"processed": 0, "failed": 0, "total": 0}
        
        logger.info(f"找到 {len(npk_names)} 个 NPK 文件，开始处理...")
        
        # 处理每个文件
        for file_name in sorted(npk_names):
            if self._process_single_file(file_name):
                self._processed += 1
            else:
                self._failed += 1
        
        stats = {
            "processed": self._processed,
            "failed": self._failed,
            "total": len(npk_names)
        }
        
        logger.info(
            f"处理完成: 成功 {stats['processed']} 个, "
            f"失败 {stats['failed']} 个"
        )
        
        return stats


def main():
    """主入口"""
    # 示例1：单个输入文件夹（无合并）
    # compiler = NpkCompiler(
    #     input_dirs=Path(r'D:\DOF\NPK'),
    #     output_dir=Path(r'D:\DOF\output\com')
    # )
    
    # 示例2：多个输入文件夹（依次合并）
    # 第一个文件夹为基础，后面的依次合并进去
    compiler = NpkCompiler(
        input_dirs=[
            Path(r'D:\DOF\NPK'),          # [基础] 基础文件
            Path(r'D:\DOF\output\Download\韩国-正式服'),          # [合并] 合并到国服
            Path(r'D:\DOF\output\Download\北美地区-正式服'),          # [合并] 再合并
        ],
        output_dir=Path(r'D:\DOF\output\Download\com')
    )

    try:
        stats = compiler.compile()
        print(f"\n编译统计:")
        print(f"  - 成功: {stats['processed']}")
        print(f"  - 失败: {stats['failed']}")
        print(f"  - 总计: {stats['total']}")
    except Exception as e:
        logger.error(f"编译失败: {e}")
        raise


if __name__ == "__main__":
    main()
