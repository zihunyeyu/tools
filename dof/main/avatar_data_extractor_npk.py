"""
Avatar Data Extractor - NPK Avatar 数据提取器

从 NPK 游戏资源包中提取 avatar 数据并生成 JSON。
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set, Tuple, Optional, Any

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from pydoftools.npk import NPK
from pydoftools.npk.img.version import IMGv6
from config import JOB_ABBREVIATIONS, PARTS, AVATAR_DATA_JSON, NPK_COMPILE_DIR


class MixedStringParser:
    """混合字符串解析器"""

    # 标准格式：part + number + index + layer，如 "coat1230d"
    PATTERN = re.compile(r"^([a-zA-Z]+)(\d+)(.+)$")
    # Body 格式：body + number，如 "body0000"（无图层后缀）
    BODY_PATTERN = re.compile(r"^(body)(\d+)$")

    @classmethod
    def parse(cls, s: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        拆分混合字符串为 (字母部分, 数字部分, 剩余部分)

        Args:
            s: 输入字符串，如 "coat1230d" 或 "body0000"

        Returns:
            (part, code, layer) 三元组，解析失败返回 (None, None, None)
            对于 body 部位，返回 skin, code, ""
        """
        # 优先尝试 body 格式（无图层），避免被标准格式截断
        match = cls.BODY_PATTERN.match(s)
        if match:
            _, code = match.groups()
            return "skin", code, ""  # body 映射为 skin

        # 标准格式
        match = cls.PATTERN.match(s)
        if match:
            return match.groups()

        return None, None, None


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
            lambda: defaultdict(
                lambda: defaultdict(
                    lambda: {"layer": set(), "indexes": [], "count": 0}
                )
            )
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

        except Exception:
            self._error_files += 1

    def _process_img_file(self, nf) -> None:
        """
        处理单个 IMG 文件

        Args:
            nf: NPK 中的文件对象
        """
        # 清理文件名
        name = nf.name.split("/")[-1].replace(".img", "")
        # 过滤无效文件
        if "mask" in name or "_" not in name:
            return

        # 拆分职业和信息
        parts = name.split("_", 1)
        if len(parts) < 2:
            return

        job, info = parts
        if job not in JOB_ABBREVIATIONS:
            return

        # 解析部位、代码、图层
        part, code, layer = MixedStringParser.parse(info)

        # skin(body) 部位允许 layer 为空，其他部位需要 layer
        if part not in PARTS or not part or not code:
            return
        if part != "skin" and not layer:
            return

        # 记录图层（skin 部位无图层，跳过）
        if layer:
            self._all_layers.add(layer)

        # 提取编号和索引
        number = code[:-2] if len(code) >= 2 else code
        index = int(code[-2:] if len(code) >= 2 else "")

        # 更新数据
        ad = self._avatar_dict[job][part][number]
        if layer:
            ad["layer"].add(layer)
    
    
        if index not in ad["indexes"]:
            ad["indexes"].append(index)
        # 统计 count
        try:
            img = nf.to_img()

            indexes = (
                [i for i in range(len(img.color_boards))] if img.version == 6 else []
            )
            for idx in indexes:
                if idx not in ad["indexes"]:
                    ad["indexes"].append(idx)
        except Exception:
            pass



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
                    indexes = sorted(data["indexes"])
                    lost_indexes = []
                    if max(indexes) >= len(indexes):
                        lost_indexes = [i for i in range(max(indexes)) if i not in indexes]
                    entries.append([num_key, len(sorted(data["indexes"])), sorted(data["layer"]), lost_indexes])
    
                # 按编号排序
                result[job][part] = sorted(
                    entries, key=lambda x: x[0] if isinstance(x[0], int) else 0
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
            return {}

        for npk_path in npk_files:
            self._process_npk_file(npk_path)

        # 格式化数据
        result = self._format_output()

        return result

    def save_to_json(self, output_path: Optional[Path] = None, indent: int = 4) -> Path:
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

        # 确保目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)

        return output_path


def main():
    """主入口 - 从 NPK 提取 Avatar 数据"""
    extractor = AvatarDataExtractor(Path(r'D:\DOF\output\Download\中国大陆-魔界'))
    try:
        output_path = extractor.save_to_json()
        print(f"\n成功！输出文件: {output_path}")
        return 0
    except Exception as e:
        print(f"提取失败: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
