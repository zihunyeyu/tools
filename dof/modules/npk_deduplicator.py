"""
NPK Deduplicator - NPK 去重工具

批量去除 NPK 文件内部的重复 IMG。
"""

import hashlib
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Union
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pydoftools.npk import NPK
from config import NPK_OUTPUT_DIR

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class DeduplicationStats:
    """去重统计信息"""
    original_count: int = 0
    unique_count: int = 0
    duplicate_count: int = 0
    
    @property
    def deduplication_rate(self) -> float:
        """计算去重率"""
        if self.original_count == 0:
            return 0.0
        return (self.duplicate_count / self.original_count) * 100


class NpkDeduplicator:
    """NPK 去重器"""
    
    def __init__(
        self,
        deduplicate_by: str = "name",
        keep_first: bool = False
    ):
        """
        初始化去重器
        
        Args:
            deduplicate_by: 去重维度，"name" 按 IMG 名称，"md5" 按内容 MD5
            keep_first: True 保留第一个出现的 IMG，False 保留最后一个
        """
        if deduplicate_by not in ("name", "md5"):
            raise ValueError("deduplicate_by 必须是 'name' 或 'md5'")
        
        self.deduplicate_by = deduplicate_by
        self.keep_first = keep_first
    
    @staticmethod
    def get_img_md5(img_file) -> str:
        """
        获取 IMG 文件内容的 MD5 值
        
        Args:
            img_file: IMG 文件对象
            
        Returns:
            MD5 字符串，失败则返回文件名
        """
        try:
            # 优先使用 data 属性
            if hasattr(img_file, "data") and img_file.data:
                return hashlib.md5(img_file.data).hexdigest()
            
            # 兜底：使用文件名
            return img_file.name
        except Exception as e:
            logger.warning(f"获取 IMG MD5 失败 ({img_file.name}): {e}")
            return img_file.name
    
    def _get_img_key(self, img) -> str:
        """获取用于去重的 key"""
        if self.deduplicate_by == "md5":
            return self.get_img_md5(img)
        return img.name
    
    def process_single_npk(
        self,
        npk_file: Union[str, Path],
        output_path: Union[str, Path]
    ) -> DeduplicationStats:
        """
        处理单个 NPK 文件
        
        Args:
            npk_file: 原始 NPK 文件路径
            output_path: 去重后 NPK 保存路径
            
        Returns:
            统计信息
        """
        stats = DeduplicationStats()
        npk_file = Path(npk_file)
        output_path = Path(output_path)
        
        try:
            # 读取原始 NPK
            with open(npk_file, "rb") as f:
                npk = NPK.open(f)
                npk.load_all()
                stats.original_count = len(npk.files)
            
            if stats.original_count == 0:
                logger.info(f"{npk_file.name}: 无 IMG 文件，直接复制")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(npk_file, "rb") as src, open(output_path, "wb") as dst:
                    dst.write(src.read())
                return stats
            
            # 去重处理
            unique_imgs: Dict[str, object] = {}
            for img in npk.files:
                img_key = self._get_img_key(img)
                
                if self.keep_first:
                    if img_key not in unique_imgs:
                        unique_imgs[img_key] = img
                    else:
                        stats.duplicate_count += 1
                else:
                    if img_key in unique_imgs:
                        stats.duplicate_count += 1
                    unique_imgs[img_key] = img  # 覆盖，保留最后一个
            
            # 更新并保存
            stats.unique_count = len(unique_imgs)
            npk.files.clear()
            npk.files.extend(list(unique_imgs.values()))
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as out_f:
                npk.save(out_f, group_by_md5=True)
            
            logger.info(
                f"✓ {npk_file.name}: "
                f"原始 {stats.original_count} 个, "
                f"去重后 {stats.unique_count} 个, "
                f"移除 {stats.duplicate_count} 个 "
                f"({stats.deduplication_rate:.1f}%)"
            )
            
        except Exception as e:
            logger.error(f"✗ 处理失败 {npk_file.name}: {e}")
        
        return stats
    
    @staticmethod
    def natural_sort_key(s: str) -> list:
        """
        自然排序辅助函数
        
        处理文件名中的数字，如：avatar1.npk < avatar2.npk < avatar10.npk
        """
        return [
            int(text) if text.isdigit() else text.lower() 
            for text in re.split(r'(\d+)', s)
        ]
    
    def process_batch(
        self,
        input_dir: Union[str, Path],
        output_dir: Union[str, Path],
        sort_by_name: bool = True,
        ignore_case_sort: bool = True,
        exclude_suffixes: Optional[List[str]] = None
    ) -> Dict[str, any]:
        """
        批量处理 NPK 文件
        
        Args:
            input_dir: 原始 NPK 文件夹
            output_dir: 去重后输出文件夹
            sort_by_name: 是否按文件名排序
            ignore_case_sort: 排序时是否忽略大小写
            exclude_suffixes: 排除的文件后缀列表
            
        Returns:
            统计信息字典
        """
        input_dir = Path(input_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 标准化排除后缀
        exclude_suffixes = exclude_suffixes or []
        exclude_suffixes = {
            s.lower() if s.startswith('.') else f'.{s.lower()}'
            for s in exclude_suffixes
        }
        
        # 检查输入目录
        if not input_dir.is_dir():
            raise FileNotFoundError(f"输入目录不存在: {input_dir}")
        
        # 获取所有 NPK 文件
        npk_files = [
            f for f in input_dir.iterdir()
            if f.is_file() 
            and f.suffix.lower() == ".npk"
            and f.suffix.lower() not in exclude_suffixes
        ]
        
        if not npk_files:
            logger.warning(f"在 {input_dir} 中未找到 NPK 文件")
            return {"processed": 0, "stats": DeduplicationStats()}
        
        # 排序
        if sort_by_name:
            if ignore_case_sort:
                npk_files.sort(key=lambda x: x.name.lower())
            else:
                npk_files.sort(key=lambda x: self.natural_sort_key(x.name))
        
        logger.info(f"找到 {len(npk_files)} 个 NPK 文件，开始去重...")
        
        # 批量处理
        total_stats = DeduplicationStats()
        processed = 0
        
        for idx, npk_file in enumerate(npk_files, 1):
            output_path = output_dir / npk_file.name
            stats = self.process_single_npk(npk_file, output_path)
            
            total_stats.original_count += stats.original_count
            total_stats.unique_count += stats.unique_count
            total_stats.duplicate_count += stats.duplicate_count
            processed += 1
            
            if idx % 10 == 0 or idx == len(npk_files):
                logger.info(f"进度: {idx}/{len(npk_files)} ({idx/len(npk_files)*100:.1f}%)")
        
        result = {
            "processed": processed,
            "stats": total_stats,
            "deduplication_rate": total_stats.deduplication_rate
        }
        
        logger.info(
            f"\n批量去重完成:\n"
            f"  处理文件: {result['processed']} 个\n"
            f"  原始 IMG: {total_stats.original_count} 个\n"
            f"  保留 IMG: {total_stats.unique_count} 个\n"
            f"  去重数量: {total_stats.duplicate_count} 个\n"
            f"  去重率: {total_stats.deduplication_rate:.2f}%"
        )
        
        return result


def main():
    """主入口"""
    from config import NPK_CONFIG
    
    deduplicator = NpkDeduplicator(
        deduplicate_by=NPK_CONFIG["deduplicate_by"],
        keep_first=NPK_CONFIG["keep_first"]
    )
    
    try:
        # 配置路径（可以根据需要修改）
        input_dir = Path(r"D:\DOF\70S2A1客户端\ImagePacks2")
        output_dir = Path(r"D:\DOF\70S2A1客户端\ImagePacks2\output")
        
        result = deduplicator.process_batch(
            input_dir=input_dir,
            output_dir=output_dir,
            sort_by_name=NPK_CONFIG["sort_npk_by_name"],
            ignore_case_sort=NPK_CONFIG["ignore_case_sort"],
            exclude_suffixes=NPK_CONFIG["exclude_suffixes"]
        )
        
        print(f"\n输出目录: {output_dir}")
        
    except Exception as e:
        logger.error(f"去重失败: {e}")
        raise


if __name__ == "__main__":
    main()
