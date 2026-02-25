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

# 职业文件名映射（用于查找装扮表）
JOB_TO_FILENAME = {
    'sm': '鬼剑士(男)',
    'ft': '格斗家(女)',
    'fm': '格斗家(男)',
    'gn': '神枪手(男)',
    'gg': '神枪手(女)',
    'mg': '魔法师(女)',
    'mm': '魔法师(男)',
    'pr': '圣职者(男)',
    'th': '暗夜使者',
}

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
            raise FileNotFoundError(f"TSV 文件不存在: {self.tsv_path}")
        
        try:
            with open(self.tsv_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    path = row.get('文件路径', '').strip()
                    equip_type = row.get('equipment type', '').strip()
                    variation = row.get('variation', '').strip()  # 格式: "36_0", "37_1" 等
                    code = row.get('文件代码', '').strip()
                    
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
            pvf_api: PVF API 客户端，用于读取stackable.lst
        """
        self.base_path = Path(avatar_table_base_path)
        self._suit_data: Dict[str, List[SuitInfo]] = {}  # job -> list of SuitInfo
        
        # 初始化 TSV 查找器
        if tsv_path is None:
            tsv_path = Path(__file__).parent / "output" / "complete_equipment_tags.tsv"
        self._tsv_finder = TsvCodeFinder(tsv_path)
        
        # 初始化 STK 代码管理器
        self._stk_manager = StkCodeManager(pvf_api)
        
        # 存储生成的stk文件信息 (stk_code, stk_path)
        self._generated_stk_files: List[Tuple[int, str]] = []
    
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
        
        Args:
            job: 职业代码
            
        Returns:
            加载成功返回 True
        """
        filename = f"{JOB_TO_FILENAME.get(job, job)}装扮表.txt"
        file_path = self.base_path / filename
        
        if not file_path.exists():
            logger.error(f"装扮表文件不存在: {file_path}")
            return False
        
        try:
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                lines = f.readlines()
            
            suits = []
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
                            suits.append(suit_info)
            
            self._suit_data[job] = suits
            logger.info(f"加载 {job} 职业套装数据: {len(suits)} 套")
            return True
            
        except Exception as e:
            logger.error(f"加载 {job} 职业套装数据失败: {e}")
            return False
    
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
                    logger.warning(f"TSV 中找不到: {job}/{part}/{suit_code}")
            
            if not package_lines:
                logger.error(f"套装 {suit_info.name} 没有找到任何可用的 equ_code")
                return False, None
            
            if missing_parts:
                logger.warning(f"套装 {suit_info.name} 缺少以下部位: {', '.join(missing_parts)}")
            
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
            
            # 记录生成的文件信息（相对路径）
            relative_path = f"{output_path}/{stk_code}.stk"
            self._generated_stk_files.append((stk_code, relative_path))
            
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
                for stk_code, stk_path in self._generated_stk_files:
                    lst_log =f"{stk_code}\t`{stk_path.replace('output\\', '')}`\n".replace('\\', '/')
                    f.write(lst_log)
            
            logger.info(f"stk.lst 已写入: {output_path} ({len(self._generated_stk_files)} 条记录)")
            return True
            
        except Exception as e:
            logger.error(f"写入stk.lst失败: {e}")
            return False
    
    def get_generated_files(self) -> List[Tuple[int, str]]:
        """获取生成的stk文件列表"""
        return self._generated_stk_files.copy()


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='礼包文件生成器 - 根据装扮表中的套装数据从TSV查找equ_code并生成 .stk 礼包文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 默认：生成所有职业的所有套装礼包
  python gift_package_generator.py

  # 生成所有职业包含"春节"的套装礼包
  python gift_package_generator.py -f "春节"

  # 列出鬼剑士的所有套装
  python gift_package_generator.py -j sm -l

  # 生成特定套装的礼包（从TSV查找equ_code）
  python gift_package_generator.py -j sm -s "09年春节套"

  # 生成单个职业所有包含"春节"的套装礼包
  python gift_package_generator.py -j sm -f "春节"

  # 指定TSV文件路径和输出目录
  python gift_package_generator.py -f "春节" --tsv "path/to/tags.tsv" -o "output/gifts"

匹配逻辑:
  装扮表code（如3600）转换为variation格式：
  - avatar_code = 3600 // 100 = 36
  - suffix = 3600 % 100 = 0
  - variation = "36_0"

STK代码:
  从PVF的stackable/stackable.lst读取最大stk_code，加1000作为起始
  生成的stk文件以stk_code命名，保存在 output/cash/additional/{job}/ 目录下
        """
    )
    
    parser.add_argument('-j', '--job',
                        choices=list(JOB_TO_TSV_PATH.keys()),
                        help='职业代码（不指定则处理所有职业）')
    
    parser.add_argument('-b', '--base-path',
                        default=r'E:\DOF\Tools\blackcat.6.12\output\Avatar',
                        help='装扮表文件基础路径（默认: %(default)s）')
    
    parser.add_argument('--tsv',
                        default=str(Path(__file__).parent / "output" / "complete_equipment_tags.tsv"),
                        help='TSV文件路径（默认: %(default)s）')
    
    parser.add_argument('-o', '--output',
                        default='generated_gifts',
                        help='输出目录（默认: %(default)s）')
    
    parser.add_argument('--stk-lst',
                        default='output/stk.lst',
                        help='stk.lst输出路径（默认: %(default)s）')
    
    parser.add_argument('-l', '--list', action='store_true',
                        help='列出该职业的所有套装')
    
    parser.add_argument('-s', '--suit',
                        help='指定套装名称，生成单个礼包')
    
    parser.add_argument('-f', '--filter',
                        help='过滤套装名称（支持部分匹配）')
    
    parser.add_argument('--all', action='store_true',
                        help='生成该职业的所有套装礼包')
    
    parser.add_argument('--name',
                        help='自定义礼包名称（仅与 -s 配合使用）')
    
    parser.add_argument('--icon-path',
                        help='自定义图标路径')
    
    parser.add_argument('--icon-index', type=int, default=745,
                        help='图标索引（默认: %(default)s）')
    
    parser.add_argument('--no-pvf', action='store_true',
                        help='不从PVF读取stackable.lst（使用默认起始code=1000）')
    
    args = parser.parse_args()
    
    # 如果没有指定职业，默认处理所有职业
    if args.job is None and not (args.list or args.suit):
        # 导入批量生成函数
        from model.equ_models import job_chinese
        
        # 创建PVF API客户端
        pvf_api = None
        if not args.no_pvf:
            try:
                from pvf_api_client import PvfUtilityApi
                from config import PVF_API_HOST, PVF_API_PORT
                pvf_api = PvfUtilityApi(host=PVF_API_HOST, port=PVF_API_PORT)
                logger.info("PVF API 客户端初始化成功")
            except Exception as e:
                logger.warning(f"PVF API 客户端初始化失败: {e}，使用默认起始code")
        
        # 创建生成器
        generator = GiftPackageGenerator(args.base_path, args.tsv, pvf_api)
        
        jobs = list(job_chinese.keys())
        print("=" * 70)
        if args.filter:
            print(f"批量生成所有职业包含 '{args.filter}' 的套装礼包")
        else:
            print(f"批量生成所有职业的所有套装礼包")
        print(f"职业列表: {', '.join(jobs)}")
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
        print("批量生成完成")
        print("=" * 70)
        print(f"总职业数: {len(jobs)}")
        print(f"总套装数: {total_count}")
        print(f"成功生成: {total_success}")
        
        # 写入stk.lst
        if generator.get_generated_files():
            generator.write_stk_lst(args.stk_lst)
        
        return
    
    # 需要指定职业的操作
    if args.job is None:
        parser.error("请指定职业代码 -j，或不指定职业直接生成所有职业的礼包")
        return
    
    # 创建PVF API客户端（如果可用）
    pvf_api = None
    if not args.no_pvf:
        try:
            from pvf_api_client import PvfUtilityApi
            from config import PVF_API_HOST, PVF_API_PORT
            pvf_api = PvfUtilityApi(host=PVF_API_HOST, port=PVF_API_PORT)
            logger.info("PVF API 客户端初始化成功")
        except Exception as e:
            logger.warning(f"PVF API 客户端初始化失败: {e}，使用默认起始code")
    
    # 创建生成器
    generator = GiftPackageGenerator(args.base_path, args.tsv, pvf_api)
    
    # 列出套装
    if args.list:
        print("=" * 70)
        print(f"{JOB_TO_FILENAME.get(args.job, args.job)} 套装列表")
        print("=" * 70)
        
        suits = generator.list_suits(args.job)
        for i, suit in enumerate(suits, 1):
            parts_str = ', '.join(suit.parts.keys())
            print(f"{i}. {suit.name} [{len(suit.parts)}件: {parts_str}]")
        
        print(f"\n共 {len(suits)} 套")
        return
    
    # 生成单个礼包
    if args.suit:
        suit_info = generator.get_suit_info(args.job, args.suit)
        if not suit_info:
            logger.error(f"找不到套装: {args.suit}")
            print(f"\n可用套装（使用 -l 查看完整列表）:")
            suits = generator.list_suits(args.job)
            for s in suits[:10]:
                print(f"  - {s.name}")
            return
        
        success, stk_code = generator.generate_gift_stk(
            job=args.job,
            suit_info=suit_info,
            output_path=args.output,
            gift_name=args.name,
            icon_path=args.icon_path,
            icon_index=args.icon_index
        )
        
        if success:
            print(f"\n✓ 礼包生成成功: {args.output}/{stk_code}.stk")
            # 写入stk.lst
            generator.write_stk_lst(args.stk_lst)
        else:
            print(f"\n✗ 礼包生成失败")
        return
    
    # 批量生成单个职业的礼包
    if args.all or args.filter:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print("=" * 70)
        if args.filter:
            print(f"生成包含 '{args.filter}' 的套装礼包")
        else:
            print(f"生成所有套装礼包")
        print("=" * 70)
        
        results = generator.generate_all_suits(
            job=args.job,
            output_dir=output_dir,
            suit_filter=args.filter
        )
        
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)
        
        print(f"\n生成完成: 成功 {success_count}/{total_count}")
        print(f"输出目录: {output_dir}")
        
        # 写入stk.lst
        if generator.get_generated_files():
            generator.write_stk_lst(args.stk_lst)
        
        return
    
    # 如果没有指定操作，显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
