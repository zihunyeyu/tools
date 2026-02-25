"""
NPK Compiler - NPK 文件合并器

合并基础 NPK 和其他区服的 NPK 文件。
"""

import logging
from pathlib import Path
from typing import List, Optional, Set

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
        input_dir: Path,
        base_dir: Path,
        output_dir: Path
    ):
        """
        初始化编译器
        
        Args:
            input_dir: 原始 NPK 文件夹
            base_dir: 基础 NPK 文件夹（用于合并）
            output_dir: 输出文件夹
        """
        self.input_dir = Path(input_dir)
        self.base_dir = Path(base_dir)
        self.output_dir = Path(output_dir)
        self._processed = 0
        self._failed = 0
    
    def _merge_npk_files(self, base_npk: NPK, file_name: str) -> NPK:
        """
        合并同名的基础 NPK 文件
        
        Args:
            base_npk: 基础 NPK 对象
            file_name: 文件名（不含扩展名）
            
        Returns:
            合并后的 NPK 对象
        """
        # 查找基础目录中的同名文件
        base_files = NpkFileFinder.find_files_containing_name(
            self.base_dir,
            file_name.lower()
        )
        
        for file_path in base_files:
            try:
                with open(file_path, "rb") as f:
                    additional_npk = NPK.open(f)
                    additional_npk.load_all()
                    base_npk.files.extend(additional_npk.files)
                    logger.debug(f"  合并: {file_path.name}")
            except Exception as e:
                logger.warning(f"  无法合并 {file_path}: {e}")
        
        return base_npk
    
    def _deduplicate_npk(self, npk: NPK) -> NPK:
        """
        去除 NPK 中的重复文件（保留最后一个）
        
        Args:
            npk: NPK 对象
            
        Returns:
            去重后的 NPK 对象
        """
        unique_dict: dict = {}
        for file in npk.files:
            unique_dict[file.name] = file  # 覆盖重复值，保留最后一个
        
        npk.files.clear()
        npk.files.extend(unique_dict.values())
        
        return npk
    
    def _process_single_file(self, npk_path: Path) -> bool:
        """
        处理单个 NPK 文件
        
        Args:
            npk_path: NPK 文件路径
            
        Returns:
            True 如果成功，False 如果失败
        """
        try:
            with open(npk_path, "rb") as f:
                npk = NPK.open(f)
                npk.load_all()
            
            # 合并其他区服文件
            file_stem = npk_path.stem
            npk = self._merge_npk_files(npk, file_stem)
            
            # 去重
            npk = self._deduplicate_npk(npk)
            
            # 保存
            output_path = self.output_dir / npk_path.name
            with open(output_path, 'wb') as out_io:
                npk.save(out_io, True)
            
            logger.info(f"✓ {npk_path.name} -> {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"✗ 处理失败 {npk_path.name}: {e}")
            return False
    
    def compile(self) -> dict:
        """
        执行编译流程
        
        Returns:
            统计信息字典
        """
        # 确保输出目录存在
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查输入目录
        if not self.input_dir.exists():
            raise FileNotFoundError(f"输入目录不存在: {self.input_dir}")
        
        if not self.base_dir.exists():
            logger.warning(f"基础目录不存在: {self.base_dir}")
        
        # 获取所有 NPK 文件
        npk_files = sorted(self.input_dir.glob("*.npk"))
        if not npk_files:
            logger.warning(f"在 {self.input_dir} 中未找到 NPK 文件")
            return {"processed": 0, "failed": 0, "total": 0}
        
        logger.info(f"找到 {len(npk_files)} 个 NPK 文件，开始处理...")
        
        # 处理每个文件
        for npk_path in npk_files:
            if self._process_single_file(npk_path):
                self._processed += 1
            else:
                self._failed += 1
        
        stats = {
            "processed": self._processed,
            "failed": self._failed,
            "total": len(npk_files)
        }
        
        logger.info(
            f"处理完成: 成功 {stats['processed']} 个, "
            f"失败 {stats['failed']} 个"
        )
        
        return stats


def main():
    """主入口"""
    compiler = NpkCompiler(
        input_dir=NPK_INPUT_DIR,
        base_dir=NPK_BASE_DIR,
        output_dir=NPK_COMPILE_DIR
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
