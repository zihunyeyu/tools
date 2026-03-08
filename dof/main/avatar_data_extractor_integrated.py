"""
Avatar Data Extractor (Integrated) - 整合版 Avatar 数据提取器

从 NPK 游戏资源包中提取 avatar 数据，结合 avatar_config.json 的套装信息和现有配置，
生成新格式的整合配置文件。

优先级：
1. name: avatar_config.json 中已存在则优先使用，否则推导（套装）或省略
2. hide_parts: avatar_config.json 中已存在则优先使用，否则默认为 []
3. layers: 从 NPK 提取

输出格式：
{
  "swordman_male": {
    "metadata": { "version": "2.0", "format": "integrated" },
    "suits": [...],
    "items": {
      "cap": {
        "4000": { "name": "原始名称", "layers": ["b"], "hide_parts": [] },
        "4001": { "name": "推导名称", "layers": ["b"], "hide_parts": [] }
      }
    }
  }
}
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set, Tuple, Optional, Any, List

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from pydoftools.npk import NPK
from config import JOB_ABBREVIATIONS, PARTS, NPK_COMPILE_DIR


# 职业键映射：完整名 -> 缩写
JOB_KEY_MAP_REVERSE = {
    'swordman_male': 'sm',
    'fighter_female': 'ft',
    'fighter_male': 'fm',
    'gunner_male': 'gn',
    'gunner_female': 'gg',
    'mage_female': 'mg',
    'mage_male': 'mm',
    'priest_male': 'pr',
    'thief_female': 'th',
}

# 部位中文名映射
PART_NAMES_CN = {
    'cap': '头饰', 'hair': '发型', 'face': '面部',
    'neck': '胸部', 'coat': '上衣', 'pants': '下装',
    'belt': '腰带', 'shoes': '鞋子', 'skin': '皮肤'
}


class MixedStringParser:
    """混合字符串解析器"""

    PATTERN = re.compile(r"^([a-zA-Z]+)(\d+)(.+)$")
    BODY_PATTERN = re.compile(r"^(body)(\d+)$")

    @classmethod
    def parse(cls, s: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """拆分混合字符串为 (字母部分, 数字部分, 剩余部分)"""
        match = cls.BODY_PATTERN.match(s)
        if match:
            _, code = match.groups()
            return "skin", code, ""

        match = cls.PATTERN.match(s)
        if match:
            return match.groups()

        return None, None, None


class IntegratedAvatarDataExtractor:
    """整合版 Avatar 数据提取器"""

    def __init__(self, npk_folder: Path, config_path: Path):
        """
        初始化提取器

        Args:
            npk_folder: NPK 文件所在目录
            config_path: avatar_config.json 路径
        """
        self.npk_folder = Path(npk_folder)
        self.config_path = Path(config_path)
        
        # 加载现有配置（包含 items 中的 name 和 hide_parts）
        self.avatar_config = self._load_config()
        
        # NPK 提取数据存储
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

    def _load_config(self) -> Dict:
        """加载 avatar_config.json"""
        if not self.config_path.exists():
            print(f"[WARN] 配置文件不存在: {self.config_path}")
            return {}
        
        try:
            with open(self.config_path, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] 加载配置文件失败: {e}")
            return {}

    def _process_npk_file(self, npk_path: Path) -> None:
        """处理单个 NPK 文件"""
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
        """处理单个 IMG 文件"""
        name = nf.name.split("/")[-1].replace(".img", "")
        if "mask" in name or "_" not in name:
            return

        parts = name.split("_", 1)
        if len(parts) < 2:
            return

        job, info = parts
        if job not in JOB_ABBREVIATIONS:
            return

        part, code, layer = MixedStringParser.parse(info)

        if part not in PARTS or not part or not code:
            return
        if part != "skin" and not layer:
            return

        if layer:
            self._all_layers.add(layer)

        number = code[:-2] if len(code) >= 2 else code
        index = int(code[-2:]) if len(code) >= 2 else 0

        ad = self._avatar_dict[job][part][number]
        if layer:
            ad["layer"].add(layer)

        if index not in ad["indexes"]:
            ad["indexes"].append(index)

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

    def _derive_name(self, suit_name: str, part: str) -> str:
        """
        推导单件名称
        
        格式: 套装名-部位名
        例如: "08国庆-[款式1]-头饰"
        """
        part_cn = PART_NAMES_CN.get(part, part)
        return f"{suit_name}-{part_cn}"

    def _find_suit_name(self, job_config: Dict, part: str, avatar_code: int) -> Optional[str]:
        """
        查找变体属于哪个套装
        """
        suits = job_config.get('suits', [])
        
        for suit in suits:
            suit_code_str = suit['items'].get(part)
            if suit_code_str:
                try:
                    suit_code = int(suit_code_str)
                    suit_avatar_code = suit_code // 100
                    
                    if avatar_code == suit_avatar_code:
                        return suit['name']
                except ValueError:
                    continue
        
        return None

    def _get_existing_item(self, job_key: str, part: str, full_code: str) -> Optional[Dict]:
        """
        获取 avatar_config.json 中已存在的 item 配置
        
        Returns:
            包含 name, hide_parts 等的字典，或 None
        """
        job_config = self.avatar_config.get(job_key, {})
        items = job_config.get('items', {})
        part_items = items.get(part, {})
        
        # 尝试直接获取（完整编码作为键）
        if full_code in part_items:
            item = part_items[full_code]
            if isinstance(item, dict):
                return item
        
        return None

    def _format_items(self, job_abbr: str, job_config: Dict, job_key: str) -> Dict[str, Dict[str, Any]]:
        """
        格式化 items 部分
        
        完全展开所有 suffix，优先使用 avatar_config.json 中的 name 和 hide_parts
        """
        items: Dict[str, Dict[str, Any]] = defaultdict(dict)
        npk_data = self._avatar_dict.get(job_abbr, {})
        
        # 获取已存在的 items（用于继承）
        existing_items = job_config.get('items', {})
        
        for part, nums in npk_data.items():
            part_existing = existing_items.get(part, {})
            
            for avatar_code_str, data in nums.items():
                try:
                    avatar_code = int(avatar_code_str)
                except ValueError:
                    continue
                
                # 从 NPK 获取 layers
                layers = sorted(data["layer"]) if data["layer"] else []
                count = len(data["indexes"]) if data["indexes"] else 1
                
                # 展开所有 suffix
                for suffix in range(count):
                    full_code = int(f"{avatar_code}{suffix:02d}")
                    full_code_str = str(full_code)
                    
                    # 构建基础 item
                    item = {}
                    
                    # 添加 layers（从 NPK）
                    item["layers"] = layers
                    
                    # 获取已存在的配置（优先）
                    existing = part_existing.get(full_code_str)
                    if existing and isinstance(existing, dict):
                        # 优先使用现有的字段
                        if "name" in existing:
                            item["name"] = existing["name"]
                        if "frame" in existing:
                            item["frame"] = existing["frame"]
                        if "icon_type" in existing:
                            item["icon_type"] = existing["icon_type"]
                        if "hide_parts" in existing:
                            item["hide_parts"] = existing["hide_parts"]
                        else:
                            item["hide_parts"] = []
                    else:
                        # 没有现有配置，设置默认 hide_parts
                        item["hide_parts"] = []
                    
                    # 如果没有 name，检查是否属于套装并推导
                    if "name" not in item:
                        suit_name = self._find_suit_name(job_config, part, avatar_code)
                        if suit_name:
                            item["name"] = self._derive_name(suit_name, part)
                    
                    items[part][full_code_str] = item
        
        return dict(items)

    def _format_output(self) -> Dict[str, Any]:
        """格式化输出为整合格式"""
        result = {}
        
        for job_key, job_config in self.avatar_config.items():
            job_abbr = JOB_KEY_MAP_REVERSE.get(job_key)
            if not job_abbr:
                print(f"[WARN] 未知职业键: {job_key}")
                continue
            
            # 获取原始 metadata
            original_metadata = job_config.get('metadata', {})
            
            result[job_key] = {
                "metadata": {
                    **original_metadata,
                    "version": "2.0",
                    "format": "integrated",
                    "generated_by": "avatar_data_extractor_integrated.py"
                },
                "suits": job_config.get('suits', []),
                "items": self._format_items(job_abbr, job_config, job_key)
            }
        
        return result

    def extract(self) -> Dict[str, Any]:
        """执行提取流程"""
        if not self.npk_folder.exists():
            raise FileNotFoundError(f"文件夹不存在: {self.npk_folder}")
        
        if not self.avatar_config:
            raise ValueError("avatar_config.json 未加载或为空")

        # 遍历 NPK 文件
        npk_files = list(self.npk_folder.glob("*.npk"))
        if not npk_files:
            print(f"[WARN] 未找到 NPK 文件: {self.npk_folder}")
            return {}

        print(f"[INFO] 开始处理 {len(npk_files)} 个 NPK 文件...")
        
        for npk_path in npk_files:
            self._process_npk_file(npk_path)

        print(f"[INFO] 处理完成: {self._processed_files} 成功, {self._error_files} 失败")
        
        # 格式化数据
        result = self._format_output()
        
        return result

    def save_to_json(self, output_path: Optional[Path] = None, indent: int = 2) -> Path:
        """
        提取并保存到 JSON 文件
        """
        data = self.extract()
        
        if output_path is None:
            output_path = Path(__file__).parent.parent / "output" / "avatar_config_integrated.json"
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)

        print(f"[INFO] 成功！输出文件: {output_path}")
        
        # 打印统计
        self._print_stats(data)
        
        return output_path

    def _print_stats(self, data: Dict):
        """打印统计信息"""
        total_jobs = len(data)
        total_suits = sum(len(job.get('suits', [])) for job in data.values())
        total_items = sum(
            sum(len(part_items) for part_items in job.get('items', {}).values())
            for job in data.values()
        )
        items_with_name = sum(
            sum(
                1 for part_items in job.get('items', {}).values()
                for item in part_items.values() if 'name' in item
            )
            for job in data.values()
        )
        items_with_hide_parts = sum(
            sum(
                1 for part_items in job.get('items', {}).values()
                for item in part_items.values() if 'hide_parts' in item
            )
            for job in data.values()
        )
        
        print(f"\n[统计]")
        print(f"  职业数: {total_jobs}")
        print(f"  套装数: {total_suits}")
        print(f"  总单件数: {total_items}")
        print(f"  有名称的单件: {items_with_name} ({items_with_name/total_items*100:.1f}%)")
        print(f"  有 hide_parts 的单件: {items_with_hide_parts} ({items_with_hide_parts/total_items*100:.1f}%)")


def main():
    """主入口"""
    npk_folder = Path(r'D:\DOF\NPK')
    config_path = Path(__file__).parent.parent / "avatar_config.json"
    output_path = Path(__file__).parent.parent / "output" / "avatar_config_integrated.json"
    
    extractor = IntegratedAvatarDataExtractor(npk_folder, config_path)
    
    try:
        extractor.save_to_json(output_path)
        return 0
    except Exception as e:
        print(f"[ERROR] 提取失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
