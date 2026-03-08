"""
Gift Package Generator - 礼包文件生成器

根据装扮表中的 [suit] 套装代码，从 complete_equipment_tags.tsv 中查找对应的 equ_code，
生成包含多个 equ_code 的礼包 stk 文件。
"""

import argparse
import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AVATAR_TABLE_BASE_PATH, AVATAR_TABLE_FILES, BASE_DIR

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============ 职业和部位映射 ============

# 装扮表列索引映射（cap, hair, face, neck, coat, pants, belt, shoes, skin）
SUIT_COLUMN_INDEX = {
    'cap': 1,    # 第2列
    'hair': 2,   # 第3列
    'face': 3,   # 第4列
    'neck': 4,   # 第5列
    'coat': 5,   # 第6列
    'pants': 6,  # 第7列
    'belt': 7,   # 第8列
    'shoes': 8,  # 第9列
    'skin': 9,   # 第10列
}

# 部位映射：装扮表部位 -> TSV equipment type
PART_TO_EQUIP_TYPE = {
    'cap': 'hat',
    'hair': 'hair',
    'face': 'face',
    'neck': 'breast',
    'coat': 'coat',
    'pants': 'pants',
    'belt': 'waist',
    'shoes': 'shoes',
    'skin': 'skin',
}

# 职业映射：job code -> TSV 文件路径
JOB_TO_TSV_PATH = {
    'sm': 'swordman',
    'ft': 'fighter',
    'fm': 'at fighter',
    'gn': 'gunner',
    'gg': 'at gunner',
    'mg': 'mage',
    'mm': 'at mage',
    'pr': 'priest',
    'th': 'thief',
}

# 职业文件名映射（用于查找装扮表，从 config 导入）
JOB_TO_FILENAME = AVATAR_TABLE_FILES

# 礼包模板
GIFT_TEMPLATE = """#PVF_File

[name]
	`{name}`

[flavor text]
	`<{flavor_text}>`

[grade]
	1

[attach type]
	`[trade]`

[rarity]
	2

[usable job]
	`[all]`
[/usable job]

[minimum level]
	1

[icon]
	`{icon_path}`	{icon_index}

[stackable type]
	`[usable cera package]`	0

[move wav]
	`CLOTH_TOUCH`

[package data]
{package_data}
[/package data]

[suitable job]
	`[{job_code}]`
[/suitable job]

[impossible contents]
	`gift`
[/impossible contents]

[stack limit]
	1

[icon mark]
	`Item/IconMark.img`	64
"""


@dataclass
class SuitInfo:
    """套装信息"""
    name: str
    parts: Dict[str, int]  # part -> code (装扮表中的code)


class TsvCodeFinder:
    """
    TSV 文件代码查找器
    
    通过 (文件路径, equipment type, variation) 查找对应的 文件代码
    
    匹配逻辑：
    - 装扮表code（如3600）转换为variation格式：
      avatar_code = code // 100, suffix = code % 100
      例如：3600 -> avatar_code=36, suffix=0 -> variation="36_0"
    """
    
    def __init__(self, tsv_path: Path):
        """
        初始化查找器
        
        Args:
            tsv_path: TSV 文件路径
        """
        self.tsv_path = Path(tsv_path)
        self._index: Dict[Tuple[str, str, str], str] = {}  # (path, equip_type, variation) -> code
        self._loaded = False
    
    def load(self) -> None:
        """加载 TSV 文件并建立索引"""
        if self._loaded:
            return
        
        if not self.tsv_path.exists():
            # raise FileNotFoundError(f"TSV 文件不存在: {self.tsv_path}")
            pass
        
        try:
            with open(self.tsv_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    path = row.get('job', '').strip()
                    equip_type = row.get('equipment type', '').strip()
                    variation = row.get('variation', '').strip()  # 格式: "36_0", "37_1" 等
                    code = row.get('code', '').strip()
                    
                    if path and equip_type and variation and code:
                        key = (path, equip_type, variation)
                        self._index[key] = code
            
            self._loaded = True
            logger.info(f"TSV 索引加载完成: {len(self._index)} 条记录")
            
        except Exception as e:
            raise RuntimeError(f"加载 TSV 文件失败: {e}")
    
    def _convert_code_to_variation(self, code: int) -> Tuple[int, int]:
        """
        将装扮表code转换为variation的avatar_code和suffix
        
        规则：
        - avatar_code = code // 100
        - suffix = code % 100
        
        例如：3600 -> (36, 0) -> variation="36_0"
              4601 -> (46, 1) -> variation="46_1"
        
        Args:
            code: 装扮表code
            
        Returns:
            (avatar_code, suffix)
        """
        avatar_code = code // 100
        suffix = code % 100
        return avatar_code, suffix
    
    def find_code(self, path: str, equip_type: str, suit_code: int) -> Optional[str]:
        """
        查找文件代码
        
        Args:
            path: 文件路径（职业）
            equip_type: 装备类型
            suit_code: 装扮表code（如3600）
            
        Returns:
            文件代码，找不到返回 None
        """
        if not self._loaded:
            self.load()
        
        # 将装扮表code转换为variation格式
        avatar_code, suffix = self._convert_code_to_variation(suit_code)
        variation = f"{avatar_code}_{suffix}"
        
        key = (path, equip_type, variation)
        return self._index.get(key)
    
    def find_codes_for_suit(self, job: str, part: str, suit_code: int) -> List[str]:
        """
        查找套装某部位的equ代码
        
        一个装扮表code可能对应多个variation（不同的avatar_type_select），
        但通常只需要第一个。
        
        Args:
            job: 职业代码
            part: 部位代码
            suit_code: 装扮表code
            
        Returns:
            文件代码列表（通常只有一个）
        """
        path = JOB_TO_TSV_PATH.get(job)
        equip_type = PART_TO_EQUIP_TYPE.get(part)
        
        if not path or not equip_type:
            return []
        
        code = self.find_code(path, equip_type, suit_code)
        if code:
            return [code]
        
        # 如果找不到，记录调试信息
        avatar_code, suffix = self._convert_code_to_variation(suit_code)
        variation = f"{avatar_code}_{suffix}"
        logger.debug(f"TSV 中找不到: {job}/{part}/{suit_code} (variation={variation})")
        return []


class StkCodeManager:
    """
    STK 代码管理器
    
    从 PVF 的 stackable/stackable.lst 读取现有 stk 代码，
    生成新的 stk 代码（最大code + 1000起步）
    """
    
    STACKABLE_LST_PATH = "stackable/stackable.lst"
    CODE_INCREMENT = 1000
    
    def __init__(self, pvf_api=None):
        """
        初始化管理器
        
        Args:
            pvf_api: PVF API 客户端，None 则从本地文件读取
        """
        self._pvf_api = pvf_api
        self._max_code = 0
        self._next_code = self.CODE_INCREMENT  # 默认起始值
        self._loaded = False
    
    def load(self) -> None:
        """从PVF加载stackable.lst并解析最大stk_code"""
        if self._loaded:
            return
        
        lst_content = None
        
        # 1. 尝试从PVF API读取
        if self._pvf_api is not None:
            try:
                lst_info = self._pvf_api.get_lst_file_info(self.STACKABLE_LST_PATH)
                if lst_info:
                    # 找到最大的code
                    max_code = 0
                    for code_str in lst_info.keys():
                        try:
                            code = int(code_str)
                            if code > max_code:
                                max_code = code
                        except ValueError:
                            continue
                    self._max_code = max_code
                    self._next_code = max_code + self.CODE_INCREMENT
                    logger.info(f"从PVF加载stackable.lst: 最大stk_code={max_code}, 起始code={self._next_code}")
                    self._loaded = True
                    return
            except Exception as e:
                logger.warning(f"从PVF API读取stackable.lst失败: {e}")
        
        # 2. 使用默认值
        logger.info(f"使用默认起始stk_code: {self._next_code}")
        self._loaded = True
    
    def get_next_code(self) -> int:
        """
        获取下一个可用的stk_code
        
        Returns:
            新的stk_code
        """
        if not self._loaded:
            self.load()
        
        code = self._next_code
        self._next_code += 1
        return code
    
    def get_max_code(self) -> int:
        """获取当前最大stk_code"""
        if not self._loaded:
            self.load()
        return self._max_code


class GiftPackageGenerator:
    """
    礼包文件生成器
    """
    
    def __init__(self, avatar_table_base_path: str, tsv_path: Optional[str] = None, pvf_api=None):
        """
        初始化生成器
        
        Args:
            avatar_table_base_path: 装扮表文件基础路径
            tsv_path: TSV 文件路径，默认使用 output/complete_equipment_tags.tsv
            pvf_api: PVF API 客户端，用于读取stackable.lst和上传stk文件
        """
        self.base_path = Path(avatar_table_base_path)
        self._suit_data: Dict[str, List[SuitInfo]] = {}  # job -> list of SuitInfo
        self._pvf_api = pvf_api  # 保存PVF API客户端用于上传
        
        # 初始化 TSV 查找器
        if tsv_path is None:
            tsv_path = (Path(__file__).parent / "output" / "complete_equipment_tags.tsv")
        self._tsv_finder = TsvCodeFinder(tsv_path)
        
        # 初始化 STK 代码管理器
        self._stk_manager = StkCodeManager(pvf_api)
        
        # 存储生成的stk文件信息 (stk_code, stk_path, name)
        self._generated_stk_files: List[Tuple[int, str, str]] = []
    
    def _parse_suit_line(self, line: str) -> Optional[SuitInfo]:
        """
        解析 suit 数据行
        
        格式: 套装名称,cap,hair,face,neck,coat,pants,belt,shoes,skin
        
        Args:
            line: 数据行
            
        Returns:
            SuitInfo 对象，解析失败返回 None
        """
        parts = line.split(',')
        if len(parts) < 10:
            return None
        
        name = parts[0].strip()
        if not name or name == '默认套装':
            return None
        
        suit_parts = {}
        for part, index in SUIT_COLUMN_INDEX.items():
            try:
                code = int(parts[index])
                if code > 0:  # 只保留有效的 code
                    suit_parts[part] = code
            except (ValueError, IndexError):
                continue
        
        if not suit_parts:
            return None
        
        return SuitInfo(name=name, parts=suit_parts)
    
    def load_suit_data(self, job: str) -> bool:
        """
        加载指定职业的 suit 数据
        
        对于同一职业下重复的套装名称，会自动添加[款式X]后缀进行区分。
        例如：两套"08年国庆套"会被重命名为"08年国庆套[款式1]"和"08年国庆套[款式2]"。
        
        Args:
            job: 职业代码
            
        Returns:
            加载成功返回 True
        """
        filename = f"{JOB_TO_FILENAME.get(job, job)}.txt"
        file_path = self.base_path / filename
        
        if not file_path.exists():
            logger.error(f"装扮表文件不存在: {file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                lines = f.readlines()
            
            raw_suits = []
            in_suit_section = False
            
            for line in lines:
                line = line.strip()
                
                # 检测 section
                if line == '[suit]':
                    in_suit_section = True
                    continue
                
                if in_suit_section:
                    # 遇到下一个 section 结束
                    if line.startswith('[') and line != '[suit]':
                        break
                    
                    if line:
                        suit_info = self._parse_suit_line(line)
                        if suit_info:
                            raw_suits.append(suit_info)
            
            # 处理重复的套装名称，添加[款式X]后缀
            suits = self._deduplicate_suit_names(raw_suits)
            
            self._suit_data[job] = suits
            # logger.info(f"加载 {job} 职业套装数据: {len(suits)} 套")
            return True
            
        except Exception as e:
            logger.error(f"加载 {job} 职业套装数据失败: {e}")
            return False
    
    def _deduplicate_suit_names(self, suits: List[SuitInfo]) -> List[SuitInfo]:
        """
        为重复的套装名称添加[款式X]后缀进行区分
        
        Args:
            suits: 原始套装列表
            
        Returns:
            处理后的套装列表
        """
        from collections import Counter
        
        # 统计每个名称出现的次数
        name_counts = Counter(suit.name for suit in suits)
        
        # 记录每个名称的当前序号
        name_indices: Dict[str, int] = {}
        
        result = []
        for suit in suits:
            name = suit.name
            if name_counts[name] > 1:
                # 需要添加后缀
                if name not in name_indices:
                    name_indices[name] = 1
                else:
                    name_indices[name] += 1
                
                # 创建新的SuitInfo，使用带后缀的名称
                new_name = f"{name}[款式{name_indices[name]}]"
                new_suit = SuitInfo(name=new_name, parts=suit.parts.copy())
                result.append(new_suit)
            else:
                # 不重复，保持原样
                result.append(suit)
        
        return result
    
    def get_suit_info(self, job: str, suit_name: str) -> Optional[SuitInfo]:
        """
        获取指定套装信息
        
        Args:
            job: 职业代码
            suit_name: 套装名称
            
        Returns:
            SuitInfo 对象，找不到返回 None
        """
        if job not in self._suit_data:
            self.load_suit_data(job)
        
        for suit in self._suit_data.get(job, []):
            if suit.name == suit_name:
                return suit
        
        return None
    
    def list_suits(self, job: str) -> List[SuitInfo]:
        """
        列出指定职业的所有套装
        
        Args:
            job: 职业代码
            
        Returns:
            SuitInfo 列表
        """
        if job not in self._suit_data:
            self.load_suit_data(job)
        
        return self._suit_data.get(job, [])
    
    def generate_gift_stk(
        self,
        job: str,
        suit_info: SuitInfo,
        output_path: Path,
        gift_name: Optional[str] = None,
        flavor_text: Optional[str] = None,
        icon_path: Optional[str] = None,
        icon_index: int = 745
    ) -> Tuple[bool, Optional[int]]:
        """
        生成礼包 stk 文件
        
        从 TSV 中查找 equ_code，使用 stk_code 作为文件名
        
        Args:
            job: 职业代码
            suit_info: 套装信息
            output_path: 输出目录路径（stk文件会保存为 {stk_code}.stk）
            gift_name: 礼包名称，默认使用套装名称
            flavor_text: flavor 文本
            icon_path: 图标路径
            icon_index: 图标索引
            
        Returns:
            (成功标志, stk_code) 元组
        """
        try:
            # 从 TSV 查找每个部位的 equ_code
            package_lines = []
            found_parts = []
            missing_parts = []
            
            for part, suit_code in suit_info.parts.items():
                codes = self._tsv_finder.find_codes_for_suit(job, part, suit_code)
                
                if codes:
                    # 使用该部位找到的第一个 code
                    package_lines.append(f"\t{codes[0]}\t1")
                    found_parts.append(part)
                    logger.debug(f"找到 {job}/{part}/{suit_code} -> {codes[0]}")
                else:
                    missing_parts.append(f"{part}({suit_code})")
                    # logger.warning(f"TSV 中找不到: {job}/{part}/{suit_code}")
            
            if not package_lines:
                logger.error(f"职业 {job} 套装 {suit_info.name} 没有找到任何可用的 equ_code")
                return False, None
            
            if missing_parts:
                logger.warning(f"{job}  {suit_info.name} 缺: {', '.join(missing_parts)}")
            
            package_data = '\n'.join(package_lines)
            
            # 获取职业路径用于图标
            job_path_map = {
                'sm': 'swordman', 'ft': 'fighter', 'fm': 'atfighter',
                'gn': 'gunner', 'gg': 'atgunner', 'mg': 'mage',
                'mm': 'atmage', 'pr': 'priest', 'th': 'tf'
            }
            job_path = job_path_map.get(job, job)
            
            # suitable job 使用 TSV 文件路径映射（swordman, fighter等）
            suitable_job = JOB_TO_TSV_PATH.get(job, job)
            
            # 构建参数
            params = {
                'name': gift_name or f"{suit_info.name}礼包",
                'flavor_text': flavor_text or suit_info.name,
                'icon_path': icon_path or f'item/avatar/{job_path}/{job}_acap.img',
                'icon_index': icon_index,
                'package_data': package_data,
                'job_code': suitable_job,
            }
            
            # 生成内容
            content = GIFT_TEMPLATE.format(**params)
            
            # 获取stk_code并构建输出路径
            stk_code = self._stk_manager.get_next_code()
            output_dir = Path(output_path)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 使用stk_code作为文件名
            file_path = output_dir / f"{stk_code}.stk"
            
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                f.write(content)
            
            # 记录生成的文件信息（相对路径）和name
            relative_path = f"{output_path}/{stk_code}.stk"
            self._generated_stk_files.append((stk_code, relative_path, params['name']))
            
            # logger.info(f"礼包文件已生成: {file_path} (stk_code={stk_code})")
            # logger.info(f"  包含 {len(found_parts)} 个部位: {', '.join(found_parts)}")
            return True, stk_code
            
        except Exception as e:
            logger.error(f"生成礼包文件失败: {e}")
            return False, None
    
    def generate_all_suits(
        self,
        job: str,
        output_dir: Path,
        suit_filter: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        生成指定职业的所有套装礼包
        
        Args:
            job: 职业代码
            output_dir: 输出目录
            suit_filter: 套装名称过滤（可选，支持部分匹配）
            
        Returns:
            {suit_name: success} 字典
        """
        suits = self.list_suits(job)
        results = {}
        
        for suit in suits:
            # 如果有过滤条件，检查是否匹配
            if suit_filter and suit_filter.lower() not in suit.name.lower():
                continue
            
            success, _ = self.generate_gift_stk(
                job=job,
                suit_info=suit,
                output_path=output_dir
            )
            results[suit.name] = success
        
        return results
    
    def write_stk_lst(self, output_path: Path) -> bool:
        """
        将生成的stk文件信息写入stk.lst
        
        格式: {stk_code}\t{stk_path}
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            写入成功返回 True
        """
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                for stk_code, stk_path, name in self._generated_stk_files:
                    lst_log = f"{stk_code}\t`{stk_path.replace('\\', '/')}`\n"
                    f.write(lst_log)
            
            logger.info(f"stk.lst 已写入: {output_path} ({len(self._generated_stk_files)} 条记录)")
            return True
            
        except Exception as e:
            logger.error(f"写入stk.lst失败: {e}")
            return False
    
    def get_generated_files(self) -> List[Tuple[int, str, str]]:
        """获取生成的stk文件列表 (stk_code, stk_path, name)"""
        return self._generated_stk_files.copy()
    
    def _get_last_package_index_from_pvf(self) -> int:
        """
        从 PVF 的 etc/newcashshop.etc 读取 [package] 标签最后一项的起始索引
        
        Returns:
            最后一项的起始索引，如果失败则返回默认值 6941
        """
        default_last_index = 6941  # 默认值
        
        if self._pvf_api is None:
            logger.warning("PVF API 未初始化，使用默认起始标签 6941")
            return default_last_index
        
        try:
            content = self._pvf_api.get_file_content('etc/newcashshop.etc')
            if not content:
                logger.warning("无法读取 newcashshop.etc，使用默认起始标签 6941")
                return default_last_index
            
            # 解析 [package] 部分
            lines = content.split('\n')
            in_package_section = False
            last_start_index = 0
            
            for line in lines:
                stripped = line.strip()
                
                # 检测 [package] 标签开始
                if stripped == '[package]':
                    in_package_section = True
                    continue
                
                # 检测其他标签（离开 [package] 部分）
                if in_package_section and stripped.startswith('['):
                    break
                
                # 解析 [package] 中的条目（以数字开头的行）
                if in_package_section and stripped and stripped[0].isdigit():
                    parts = stripped.split('\t')
                    if parts and parts[0].isdigit():
                        idx = int(parts[0])
                        if idx > last_start_index:
                            last_start_index = idx
            
            if last_start_index > 0:
                logger.info(f"从 PVF 读取到 [package] 最后一项起始索引: {last_start_index}")
                return last_start_index
            else:
                logger.warning("未在 [package] 中找到有效条目，使用默认起始标签 6941")
                return default_last_index
                
        except Exception as e:
            logger.error(f"读取 PVF [package] 标签失败: {e}")
            return default_last_index
    
    def _update_newcashshop_etc_package(self) -> bool:
        """
        将生成的 stk 条目更新到 PVF 的 etc/newcashshop.etc 的 [package] 标签内
        
        格式: <start_index>\t<stk_code>\t0\t0\t0\t`name`\t0\t0\t-1\t-1
        价格固定为 0
        
        Returns:
            成功返回 True
        """
        if self._pvf_api is None:
            logger.error("PVF API 未初始化，无法更新 newcashshop.etc")
            return False
        
        if not self._generated_stk_files:
            logger.info("没有 stk 条目需要更新到 [package]")
            return True
        
        try:
            # 读取当前 PVF 中的 newcashshop.etc
            current_content = self._pvf_api.get_file_content('etc/newcashshop.etc')
            if not current_content:
                logger.error("无法读取 PVF 中的 newcashshop.etc")
                return False
            
            # 动态获取起始索引：最后一项 + 1000
            last_index = self._get_last_package_index_from_pvf()
            start_index = last_index + 1000
            logger.info(f"[package] 新条目起始索引: {start_index} (基于 PVF 最后一项 {last_index} + 1000)")
            
            # 构建新的 [package] 条目
            new_package_lines = []
            current_idx = start_index
            for stk_code, stk_path, name in self._generated_stk_files:
                # 格式: <start_index>\t<stk_code>\t0\t0\t0\t`name`\t0\t0\t-1\t-1
                line = f"{current_idx}\t{stk_code}\t0\t0\t0\t`{name}`\t0\t0\t-1\t-1"
                new_package_lines.append(line)
                current_idx += 1
            
            new_package_entries = '\n'.join(new_package_lines)
            
            # 解析文件内容，找到 [package] 部分的最后一个条目
            lines = current_content.split('\n')
            last_entry_idx = -1
            in_package = False
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped == '[package]':
                    in_package = True
                    continue
                if in_package and stripped.startswith('['):
                    break
                if in_package and stripped and stripped[0].isdigit():
                    last_entry_idx = i
            
            # 在最后一个条目后插入新条目
            if last_entry_idx >= 0:
                lines.insert(last_entry_idx + 1, new_package_entries)
            else:
                # 如果没找到条目，在 [package] 标签后添加
                for i, line in enumerate(lines):
                    if line.strip() == '[package]':
                        lines.insert(i + 1, new_package_entries)
                        break
            
            # 合并回完整内容
            merged_content = '\n'.join(lines)
            
            # 上传更新后的文件
            file_info = [{
                "FilePath": "etc/newcashshop.etc",
                "FileContent": merged_content
            }]
            
            failed = self._pvf_api.import_files(file_info)
            
            if failed:
                logger.warning(f"newcashshop.etc [package] 更新失败: {failed}")
                return False
            else:
                logger.info(f"newcashshop.etc [package] 更新成功，新增 {len(self._generated_stk_files)} 条条目")
                return True
                
        except Exception as e:
            logger.error(f"更新 newcashshop.etc [package] 失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def import_stk_files_to_pvf(self, stk_lst_path: Optional[Path] = None, update_package: bool = True) -> Tuple[int, int]:
        """
        将生成的stk文件导入到PVF，并更新stackable.lst和newcashshop.etc的[package]标签
        
        Args:
            stk_lst_path: stk.lst文件路径，用于更新PVF的stackable.lst
            update_package: 是否更新 newcashshop.etc 的 [package] 标签（默认True）
            
        Returns:
            (成功数量, 失败数量) 元组
        """
        if self._pvf_api is None:
            logger.error("PVF API 未初始化，无法导入stk文件")
            return 0, len(self._generated_stk_files)
        
        if not self._generated_stk_files:
            logger.info("没有stk文件需要导入")
            return 0, 0
        
        success_count = 0
        failed_count = 0
        
        try:
            from pathlib import Path
            
            # 步骤1: 上传所有stk文件内容
            file_info_list = []
            for stk_code, stk_path, name in self._generated_stk_files:
                # 构建完整文件路径
                full_path = Path(stk_path)
                if not full_path.is_absolute():
                    full_path = Path(BASE_DIR) / stk_path
                
                if not full_path.exists():
                    logger.warning(f"stk文件不存在: {full_path}")
                    failed_count += 1
                    continue
                
                # 读取文件内容
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # 路径前加上 'stackable/' 前缀
                upload_path = f"stackable/{stk_path.replace('\\', '/')}"
                file_info_list.append({
                    "FilePath": upload_path,
                    "FileContent": content
                })
            
            if not file_info_list:
                logger.error("没有有效的stk文件可以导入")
                return 0, failed_count
            
            # 批量导入stk文件
            failed_files = self._pvf_api.import_files(file_info_list)
            stk_success = len(file_info_list) - len(failed_files)
            failed_count += len(failed_files)
            
            logger.info(f"stk文件上传完成: 成功 {stk_success}, 失败 {failed_count}")
            
            if failed_files:
                logger.warning(f"以下stk文件上传失败: {failed_files}")
            
            # 步骤2: 更新PVF的stackable.lst（合并新条目）
            if stk_lst_path and stk_success > 0:
                try:
                    # 读取当前PVF中的stackable.lst
                    current_lst = self._pvf_api.get_file_content('stackable/stackable.lst')
                    
                    # 读取本地生成的stk.lst内容（路径不需要加 stackable/ 前缀）
                    with open(stk_lst_path, 'r', encoding='utf-8') as f:
                        new_entries = f.read()
                    
                    # 合并：在现有内容后添加新条目
                    if current_lst:
                        merged_content = current_lst.rstrip() + '\n' + new_entries
                    else:
                        merged_content = new_entries
                    
                    # 上传合并后的stackable.lst
                    lst_file_info = [{
                        "FilePath": "stackable/stackable.lst",
                        "FileContent": merged_content
                    }]
                    
                    lst_failed = self._pvf_api.import_files(lst_file_info)
                    
                    if lst_failed:
                        logger.warning(f"stackable.lst 更新失败: {lst_failed}")
                    else:
                        logger.info("stackable.lst 更新成功")
                        success_count = stk_success
                except Exception as e:
                    logger.error(f"更新 stackable.lst 失败: {e}")
                    # stk文件已上传成功，但lst更新失败
                    success_count = stk_success
            else:
                success_count = stk_success
            
            # 步骤3: 更新PVF的newcashshop.etc的[package]标签
            if update_package and stk_success > 0:
                self._update_newcashshop_etc_package()
            
        except Exception as e:
            logger.error(f"导入stk文件到PVF失败: {e}")
            return 0, len(self._generated_stk_files)
        
        return success_count, failed_count


def main():
    """命令行入口 - 简化版，默认生成所有职业的所有套装礼包并上传到PVF"""
    parser = argparse.ArgumentParser(
        description='礼包文件生成器 - 根据装扮表中的套装数据生成 .stk 礼包文件并上传到PVF',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 默认：生成所有职业的所有套装礼包并上传到PVF
  python gift_package_generator.py

  # 生成包含"春节"的套装礼包并上传到PVF
  python gift_package_generator.py -f "春节"

  # 生成但不上传到PVF
  python gift_package_generator.py --no-upload

  # 指定TSV文件路径和输出目录
  python gift_package_generator.py -f "春节" --tsv "path/to/tags.tsv" -o "output/gifts"
        """
    )
    
    parser.add_argument('-b', '--base-path',
                        default=AVATAR_TABLE_BASE_PATH,
                        help='装扮表文件基础路径（默认: %(default)s）')
    
    parser.add_argument('--tsv',
                        default=str(BASE_DIR / "output" / "complete_equipment_tags.tsv"),
                        help='TSV文件路径（默认: %(default)s）')
    
    parser.add_argument('-o', '--output',
                        default='generated_gifts',
                        help='输出目录（默认: %(default)s）')
    
    parser.add_argument('--stk-lst',
                        default='output/stk.lst',
                        help='stk.lst输出路径（默认: %(default)s）')
    
    parser.add_argument('-f', '--filter',
                        help='过滤套装名称（支持部分匹配）')
    
    parser.add_argument('--no-pvf', action='store_true',
                        help='不从PVF读取stackable.lst（使用默认起始code=1000）')
    
    parser.add_argument('--no-upload', action='store_true',
                        help='不上传stk文件到PVF（默认会自动上传）')
    
    args = parser.parse_args()
    
    # 导入职业列表
    from model.equ_models import job_chinese
    
    # 创建PVF API客户端（用于读取stackable.lst和上传stk文件）
    pvf_api = None
    if not args.no_pvf or not args.no_upload:
        try:
            from modules.pvf_api_client import PvfUtilityApi
            from config import PVF_API_HOST, PVF_API_PORT
            pvf_api = PvfUtilityApi(host=PVF_API_HOST, port=PVF_API_PORT)
            logger.info("PVF API 客户端初始化成功")
        except Exception as e:
            if not args.no_upload:
                logger.warning(f"PVF API 客户端初始化失败: {e}，stk文件将不会上传到PVF")
            else:
                logger.warning(f"PVF API 客户端初始化失败: {e}，使用默认起始code")
    
    # 创建生成器
    generator = GiftPackageGenerator(args.base_path, args.tsv, pvf_api)
    
    jobs = list(job_chinese.keys())
    print("=" * 70)
    if args.filter:
        print(f"生成所有职业包含 '{args.filter}' 的套装礼包")
    else:
        print(f"生成所有职业的所有套装礼包")
    print(f"职业列表: {', '.join(jobs)}")
    print(f"上传到PVF: {'否' if args.no_upload else '是'}")
    print("=" * 70)
    
    total_success = 0
    total_count = 0
    
    for job in jobs:
        print(f"\n处理职业: {job} ({job_chinese[job]})")
        
        # 检查该职业是否有装扮表
        suits = generator.list_suits(job)
        if not suits:
            logger.warning(f"职业 {job} 没有可用的套装数据，跳过")
            continue
        
        # 创建输出目录
        output_dir = Path(args.output) / job
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成该职业的套装
        results = generator.generate_all_suits(
            job=job,
            output_dir=output_dir,
            suit_filter=args.filter
        )
        
        job_success = sum(1 for v in results.values() if v)
        job_total = len(results)
        total_success += job_success
        total_count += job_total
        
        print(f"  完成: 成功 {job_success}/{job_total}")
    
    print("\n" + "=" * 70)
    print("生成完成")
    print("=" * 70)
    print(f"总职业数: {len(jobs)}")
    print(f"总套装数: {total_count}")
    print(f"成功生成: {total_success}")
    
    # 写入stk.lst
    if generator.get_generated_files():
        generator.write_stk_lst(args.stk_lst)
        print(f"stk.lst 已生成: {args.stk_lst}")
        
        # 上传到PVF（默认行为）
        if not args.no_upload:
            print("\n正在上传stk文件到PVF...")
            success, failed = generator.import_stk_files_to_pvf(args.stk_lst, update_package=True)
            print(f"上传完成: 成功 {success}, 失败 {failed}")
            print(f"✓ etc/newcashshop.etc [package] 标签已更新")
    
    return


if __name__ == "__main__":
    main()
