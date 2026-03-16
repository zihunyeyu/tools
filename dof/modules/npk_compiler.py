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
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
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
        exclude_suffixes: Optional[Set[str]] = None,
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
            s if s.startswith(".") else f".{s}" for s in exclude_suffixes
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
        output_dir: Path,
        compare_frames: bool = False,
    ):
        """
        初始化编译器

        Args:
            input_dirs: NPK 文件夹列表，按顺序依次合并
                       第一个文件夹为基础，后面的依次合并进去
            output_dir: 输出文件夹
            compare_frames: 是否比较帧数来解析冲突，默认为 False
                           为 True 时，同名 IMG 优先保留帧数多的版本
                           帧数相同时，再比较调色板数量
        """
        # 支持单个路径或路径列表
        if isinstance(input_dirs, (str, Path)):
            self.input_dirs = [Path(input_dirs)]
        else:
            self.input_dirs = [Path(d) for d in input_dirs]

        self.output_dir = Path(output_dir)
        self.compare_frames = compare_frames
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
        basename = filename.lower().split("/")[-1].split("\\")[-1]

        # 去掉 .img 后缀
        if basename.endswith(".img"):
            basename = basename[:-4]

        # 匹配模式: [前缀_][图层名][代码][后缀][数字]
        # 例如: sm_coat0000a, fm_claw7800a1, coat0000b
        # 图层名是最后的字母部分在数字之前

        # 从后往前找：最后的数字后面的字母是图层后缀，再往前是代码，再往前是图层名
        # coat0000a → coat + 0000 + a
        # claw7800a1 → claw + 7800 + a + 1 (最后的数字是调色板索引，忽略)

        # 找到最后一个数字序列和其后的字母
        match = re.search(r"([a-z]+)(\d+)([a-z])", basename)
        if match:
            layer_name = match.group(1)  # coat, claw 等
            code = int(match.group(2))  # 0000, 7800 等
            layer_suffix = match.group(3)  # a, b, c...
            return (layer_name, code, layer_suffix)

        # 尝试只匹配数字（无后缀，默认a层）
        match = re.search(r"([a-z]+)(\d+)$", basename)
        if match:
            layer_name = match.group(1)
            code = int(match.group(2))
            return (layer_name, code, "a")

        return None

    def _get_img_info(self, file) -> Tuple[int, int]:
        """
        获取 IMG 文件的调色板数量和帧数

        Args:
            file: NPK 文件对象

        Returns:
            (调色板数量, 帧数)
        """
        palette_count = 0
        frame_count = 0

        try:
            img = file.to_img()
            version = img.version

            # 获取调色板数量
            if version == 6 and hasattr(img, "color_boards") and img.color_boards:
                palette_count = len(img.color_boards)
            elif version == 4:
                palette_count = 1

            # 获取帧数 - 尝试多种可能的属性名
            if hasattr(img, "frames"):
                try:
                    frames = img.frames
                    if frames is not None:
                        if isinstance(frames, (list, tuple)):
                            frame_count = len(frames)
                        elif hasattr(frames, "__len__"):
                            frame_count = len(frames)
                        else:
                            # 可能是生成器或迭代器，尝试转换
                            frame_count = len(list(frames))
                except Exception:
                    pass

            # 尝试从 images 属性获取帧数（某些版本的 IMG）
            if frame_count == 0 and hasattr(img, "images"):
                try:
                    images = img.images
                    if images is not None:
                        if isinstance(images, (list, tuple)):
                            frame_count = len(images)
                        elif hasattr(images, "__len__"):
                            frame_count = len(images)
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"获取 IMG 信息失败: {e}")

        return palette_count, frame_count

    def _resolve_code_conflicts(self, files: list) -> Tuple[list, Set[str], dict]:
        """
        解决同名 IMG 文件的冲突

        策略：
        1. 只处理同名文件（完全相同的文件名）
        2. 对于同名的 IMG 文件：
           - 默认：保留调色板数量更多的版本
           - compare_frames=True 时：优先保留帧数多的版本，帧数相同时比较调色板
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
            "frame_upgrades": 0,  # 帧数升级次数
            "total_removed": 0,
        }

        for file_name, file_list in files_by_name.items():
            if len(file_list) == 1:
                # 没有同名文件，直接保留
                files_to_keep.append(file_list[0])
                continue

            # 有同名文件，需要比较
            stats["duplicates"] += len(file_list) - 1

            # 收集所有文件的信息用于调试
            file_infos = []
            for i, file in enumerate(file_list):
                palette_count, frame_count = self._get_img_info(file)
                file_infos.append((file, palette_count, frame_count))
                logger.debug(
                    f"    候选 {i+1}: {file.name} - {frame_count}帧, {palette_count}调色板"
                )

            # 找出最优版本
            best_file = None
            best_palette_count = -1
            best_frame_count = -1

            for file, palette_count, frame_count in file_infos:
                is_better = False

                if self.compare_frames:
                    # 优先比较帧数
                    if frame_count > best_frame_count:
                        is_better = True
                    elif frame_count == best_frame_count:
                        # 帧数相同，比较调色板
                        if palette_count > best_palette_count:
                            is_better = True
                else:
                    # 只比较调色板
                    if palette_count > best_palette_count:
                        is_better = True

                if is_better:
                    best_file = file
                    best_palette_count = palette_count
                    best_frame_count = frame_count

            # 保留最优版本，记录删除其他同名文件
            if best_file:
                files_to_keep.append(best_file)
                # 始终记录选择信息（用于调试）
                logger.info(
                    f"  [选择] {file_name}: 保留 {best_frame_count}帧/{best_palette_count}调色板版本"
                )

                for file, palette_count, frame_count in file_infos:
                    if file is not best_file:
                        files_to_remove.add(file.name)
                        # 记录升级类型
                        if self.compare_frames:
                            if best_frame_count > frame_count:
                                stats["frame_upgrades"] += 1
                                logger.info(
                                    f"    -> 帧数升级: {frame_count}帧 -> {best_frame_count}帧"
                                )
                            elif best_palette_count > palette_count:
                                stats["palette_upgrades"] += 1
                                logger.info(
                                    f"    -> 调色板升级: {palette_count}p -> {best_palette_count}p"
                                )
                        elif best_palette_count > palette_count:
                            stats["palette_upgrades"] += 1
                            logger.info(
                                f"    -> 调色板升级: {palette_count}p -> {best_palette_count}p"
                            )

        stats["total_removed"] = len(files_to_remove)
        return files_to_keep, files_to_remove, stats

    def _merge_additional_npks(
        self, npk: NPK, file_name: str, input_dirs: List[Path]
    ) -> tuple:
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
                f
                for f in input_dir.glob("*.npk")
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
                            logger.debug(
                                f"    从 {file_path} 合并 {len(additional_npk.files)} 个文件"
                            )

                except Exception as e:
                    logger.warning(f"    合并失败 {file_path}: {e}")

        return npk, merged_count

    def _deduplicate_npk(self, npk: NPK) -> tuple:
        """
        去除 NPK 中的重复文件，按文件名排序。
        根据配置优先保留帧数多或调色板数量多的版本。

        Args:
            npk: NPK 对象

        Returns:
            (去重并排序后的 NPK 对象, 被覆盖信息列表)
        """
        unique_dict: dict = {}
        overwritten = []

        for file in npk.files:
            if file.name not in unique_dict:
                unique_dict[file.name] = file
            else:
                # 存在同名文件，进行比较
                existing = unique_dict[file.name]

                existing_palette, existing_frames = self._get_img_info(existing)
                new_palette, new_frames = self._get_img_info(file)

                should_replace = False

                if self.compare_frames:
                    # 优先比较帧数
                    if new_frames > existing_frames:
                        should_replace = True
                        reason = f"{new_frames}f > {existing_frames}f"
                    elif new_frames == existing_frames and new_palette > existing_palette:
                        should_replace = True
                        reason = f"{new_palette}p > {existing_palette}p"
                else:
                    # 只比较调色板
                    if new_palette > existing_palette:
                        should_replace = True
                        reason = f"{new_palette}p > {existing_palette}p"

                if should_replace:
                    unique_dict[file.name] = file
                    overwritten.append((file.name, reason))

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
            resolved_files, internal_removed, internal_stats = (
                self._resolve_code_conflicts(npk.files)
            )
            if internal_stats["total_removed"] > 0:
                total_conflicts += internal_stats["total_removed"]
                log_msg = (
                    f"  基础去重: 移除 {internal_stats['total_removed']} 个重复 "
                    f"(同名冲突:{internal_stats.get('duplicates', 0)}"
                )
                if internal_stats.get("frame_upgrades", 0) > 0:
                    log_msg += f", 帧数升级:{internal_stats['frame_upgrades']}"
                if internal_stats.get("palette_upgrades", 0) > 0:
                    log_msg += f", 调色板升级:{internal_stats['palette_upgrades']}"
                log_msg += ")"
                logger.info(log_msg)
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
            resolved_files, merge_removed, merge_stats = self._resolve_code_conflicts(
                npk.files
            )
            if merge_stats["total_removed"] > 0:
                total_conflicts += merge_stats["total_removed"]
                log_msg = (
                    f"  合并去重: 移除 {merge_stats['total_removed']} 个重复 "
                    f"(同名冲突:{merge_stats.get('duplicates', 0)}"
                )
                if merge_stats.get("frame_upgrades", 0) > 0:
                    log_msg += f", 帧数升级:{merge_stats['frame_upgrades']}"
                if merge_stats.get("palette_upgrades", 0) > 0:
                    log_msg += f", 调色板升级:{merge_stats['palette_upgrades']}"
                log_msg += ")"
                logger.info(log_msg)
            npk.files.clear()
            npk.files.extend(resolved_files)

            # 第4步：去重同名文件（最终保底）
            npk, overwritten = self._deduplicate_npk(npk)
            final_count = len(npk.files)

            # 保存
            output_path = self.output_dir / file_name
            with open(output_path, "wb") as out_io:
                npk.save(out_io, True)

            # 只有在有变化时才输出日志
            has_change = (
                (final_count != original_count)
                or bool(overwritten)
                or (total_conflicts > 0)
            )
            if has_change:
                for name, reason in overwritten:
                    logger.info(f"  覆盖 {name}: {reason}")
                logger.info(
                    f"✓ {file_name}: {original_count} -> {final_count} 个文件 (解决 {total_conflicts} 个冲突)"
                )

            return True

        except Exception as e:
            logger.error(f"✗ 处理失败 {file_name}: {e}")
            import traceback

            logger.debug(traceback.format_exc())
            return False

    def _collect_npk_names(self, keyword: Optional[str] = None) -> Set[str]:
        """
        收集第一个输入文件夹中的 NPK 文件名

        Args:
            keyword: 如果指定，只收集文件名包含该关键词的 NPK 文件

        Returns:
            NPK 文件名集合
        """
        base_dir = self.input_dirs[0]
        if not base_dir.exists():
            logger.error(f"基础输入目录不存在: {base_dir}")
            return set()

        npk_names = set()
        for npk_file in base_dir.glob("*.npk"):
            if keyword is None or keyword.lower() in npk_file.name.lower():
                npk_names.add(npk_file.name)

        return npk_names

    def compile(self, keyword: Optional[str] = None) -> dict:
        """
        执行编译流程

        从第一个文件夹获取基础 NPK，依次合并其他文件夹中的同名 NPK

        Args:
            keyword: 如果指定，只处理文件名包含该关键词的 NPK 文件

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

        # 显示比较策略
        if self.compare_frames:
            logger.info("冲突解决策略: 优先保留帧数多的版本（帧数相同时比较调色板）")
        else:
            logger.info("冲突解决策略: 优先保留调色板多的版本")

        # 收集基础文件夹中的 NPK 文件名
        npk_names = self._collect_npk_names(keyword)
        if not npk_names:
            if keyword:
                logger.error(f"在 {self.input_dirs[0]} 中未找到包含 '{keyword}' 的 NPK 文件")
            else:
                logger.error(f"在 {self.input_dirs[0]} 中未找到 NPK 文件")
            return {"processed": 0, "failed": 0, "total": 0}

        if keyword:
            logger.info(f"找到 {len(npk_names)} 个包含 '{keyword}' 的 NPK 文件，开始处理...")
        else:
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
            "total": len(npk_names),
        }

        logger.info(
            f"处理完成: 成功 {stats['processed']} 个, " f"失败 {stats['failed']} 个"
        )

        return stats

    def compile_with_filter(self, keyword: str) -> dict:
        """
        执行编译流程，只处理文件名包含指定关键词的 NPK 文件

        Args:
            keyword: 要匹配的关键词（不区分大小写）

        Returns:
            统计信息字典
        """
        return self.compile(keyword=keyword)


def main():
    """主入口"""
    # 示例1：单个输入文件夹（无合并）
    # compiler = NpkCompiler(
    #     input_dirs=Path(r'D:\DOF\NPK'),
    #     output_dir=Path(r'D:\DOF\output\com')
    # )

    # 示例2：多个输入文件夹（依次合并，比较调色板）
    # 第一个文件夹为基础，后面的依次合并进去
    compiler = NpkCompiler(
        input_dirs=[
            Path(r"E:\DOF\NPK"),  # [基础] 基础文件
            Path(r"E:\DOF\Tools\blackcat.6.12\output\Download\北美地区-正式服"),  # [合并] 合并到国服
            Path(r"E:\DOF\Tools\blackcat.6.12\output\Download\日本-正式服"),  # [合并] 再合并
        ],
        output_dir=Path(r"E:\DOF\NPK"),
        compare_frames=True,  # False = 比较调色板，True = 比较帧数
    )

    try:
        # 处理所有 NPK 文件
        # stats = compiler.compile()

        # 只处理文件名包含 "swordman" 的 NPK 文件
        stats = compiler.compile_with_filter("sprite_item_avatar_")

        print(f"\n编译统计:")
        print(f"  - 成功: {stats['processed']}")
        print(f"  - 失败: {stats['failed']}")
        print(f"  - 总计: {stats['total']}")
    except Exception as e:
        logger.error(f"编译失败: {e}")
        raise


if __name__ == "__main__":
    main()
