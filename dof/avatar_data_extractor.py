"""
Avatar Data Extractor - NPK Avatar 数据提取器

从 NPK 游戏资源包中提取 avatar 数据并生成 JSON。
"""

import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set, Tuple, Optional, Any

from pydoftools.npk import NPK
from pydoftools.npk.img.version import IMGv6

from config import JOB_ABBREVIATIONS, PARTS, AVATAR_DATA_JSON, NPK_COMPILE_DIR

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MixedStringParser:
    """混合字符串解析器"""
    
    PATTERN = re.compile(r'^([a-zA-Z]+)(\d+)(.+)$')
    
    @classmethod
    def parse(cls, s: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        拆分混合字符串为 (字母部分, 数字部分, 剩余部分)
        
        Args:
            s: 输入字符串，如 "coat1230d"
            
        Returns:
            (part, code, layer) 三元组，解析失败返回 (None, None, None)
        """
        match = cls.PATTERN.match(s)
        return match.groups() if match else (None, None, None)


class AvatarDataExtractor:
    """Avatar 数据提取器"""
    
    def __init__(self, npk_folder: Path):
        """
        初始化提取器
        
        Args:
            npk_folder: NPK 文件所在目录
        """
        self.npk_folder = Path(npk_folder)
        self._avatar_dict: Dict[str, Any] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: {
                'layer': set(),
                'indexes': set(),
                'count': 0
            }))
        )
        self._all_layers: Set[str] = set()
        self._processed_files = 0
        self._error_files = 0
    
    def _process_npk_file(self, npk_path: Path) -> None:
        """
        处理单个 NPK 文件
        
        Args:
            npk_path: NPK 文件路径
        """
        try:
            with open(npk_path, "rb") as f:
                npk = NPK.open(f)
                npk.load_all()
                
                for nf in npk.files:
                    self._process_img_file(nf)
                
                self._processed_files += 1
                
        except Exception as e:
            self._error_files += 1
            logger.warning(f"解析失败 {npk_path.name}: {str(e)[:50]}")
    
    def _process_img_file(self, nf) -> None:
        """
        处理单个 IMG 文件
        
        Args:
            nf: NPK 中的文件对象
        """
        # 清理文件名
        name = nf.name.split('/')[-1].replace('.img', '')
        
        # 过滤无效文件
        if 'mask' in name or '_' not in name:
            return
        
        # 拆分职业和信息
        parts = name.split('_', 1)
        if len(parts) < 2:
            return
        
        job, info = parts
        if job not in JOB_ABBREVIATIONS:
            return
        
        # 解析部位、代码、图层
        part, code, layer = MixedStringParser.parse(info)
        
        if part not in PARTS or not all([part, code, layer]):
            return
        
        # 记录图层
        self._all_layers.add(layer)
        
        # 提取编号和索引
        number = code[:-2] if len(code) >= 2 else code
        index = code[-2:] if len(code) >= 2 else ''
        
        # 更新数据
        ad = self._avatar_dict[job][part][number]
        ad['layer'].add(layer)
        if index:
            ad['indexes'].add(index)
        
        # 统计 count
        try:
            img = nf.to_img()
            ad['count'] = len(img.color_boards) if isinstance(img, IMGv6) else len(ad['indexes'])
        except Exception as e:
            logger.debug(f"解析图片 {name} 出错: {str(e)[:30]}")
            ad['count'] = len(ad['indexes'])
    
    def _format_output(self) -> Dict[str, Any]:
        """
        格式化输出数据
        
        Returns:
            格式化后的字典
        """
        result = {}
        
        for job, parts_data in self._avatar_dict.items():
            result[job] = {}
            for part, nums in parts_data.items():
                # 转换为列表并排序
                entries = []
                for num, data in nums.items():
                    # 尝试将 num 转为整数以便排序
                    num_key = int(num) if num.isdigit() else num
                    entries.append([
                        num_key,
                        data['count'],
                        sorted(data['layer'])
                    ])
                
                # 按编号排序
                result[job][part] = sorted(
                    entries,
                    key=lambda x: x[0] if isinstance(x[0], int) else 0
                )
        
        return result
    
    def extract(self) -> Dict[str, Any]:
        """
        执行提取流程
        
        Returns:
            提取的 avatar 数据
        """
        if not self.npk_folder.exists():
            raise FileNotFoundError(f"文件夹不存在: {self.npk_folder}")
        
        # 遍历 NPK 文件
        npk_files = list(self.npk_folder.glob("*.npk"))
        if not npk_files:
            logger.warning(f"在 {self.npk_folder} 中未找到 NPK 文件")
            return {}
        
        logger.info(f"找到 {len(npk_files)} 个 NPK 文件，开始处理...")
        
        for npk_path in npk_files:
            self._process_npk_file(npk_path)
        
        # 格式化数据
        result = self._format_output()
        
        logger.info(
            f"处理完成: 成功 {self._processed_files} 个文件, "
            f"失败 {self._error_files} 个文件, "
            f"发现 {len(self._all_layers)} 种图层"
        )
        
        return result
    
    def save_to_json(
        self,
        output_path: Optional[Path] = None,
        indent: int = 4
    ) -> Path:
        """
        提取并保存到 JSON 文件
        
        Args:
            output_path: 输出路径，默认使用配置中的路径
            indent: JSON 缩进
            
        Returns:
            输出文件路径
        """
        data = self.extract()
        output_path = Path(output_path or AVATAR_DATA_JSON)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        
        logger.info(f"数据已保存到 {output_path}")
        return output_path


def main():
    """主入口"""
    extractor = AvatarDataExtractor(NPK_COMPILE_DIR)
    try:
        output_path = extractor.save_to_json()
        print(f"\n成功！输出文件: {output_path}")
    except Exception as e:
        logger.error(f"提取失败: {e}")
        raise


if __name__ == "__main__":
    main()
