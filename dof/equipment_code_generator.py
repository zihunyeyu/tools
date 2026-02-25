"""
Equipment Code Generator - 装备编码生成器

从 avatar_data.json 生成装备编码清单 (.lst 文件) 和 equ 文件。
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, List, Set
from dataclasses import dataclass

from tsv_validator import EquipmentTagValidator
from pvf_api_client import PvfUtilityApi
from config import (
    JOB_MAP, PART_CODE_MAP,
    EQU_PATH_TEMPLATE, EQUIPMENT_LST, AVATAR_DATA_JSON,
    PVF_API_HOST, PVF_API_PORT, BASE_DIR
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class AvatarIndex:
    """Avatar 索引数据结构"""
    code: int
    count: int
    layers: List[str]
    
    @classmethod
    def from_tuple(cls, data: Tuple) -> Optional['AvatarIndex']:
        """从元组创建对象"""
        if not isinstance(data, (list, tuple)) or len(data) != 3:
            return None
        code, count, layers = data
        if not isinstance(code, int) or not isinstance(count, int):
            return None
        return cls(code=code, count=count, layers=list(layers) if layers else [])


# 导入 layer_dict (从 model/avatars.py)
layer_dict = {
    'coat_f': 2850,
    'neck_f': 2840,
    'face_f': 2830,
    'cap_f': 2810,
    'belt_e': 2800,
    'neck_e': 2780,
    'neck_ef': 2751,
    'face_g': 2750,
    'face_a': 2700,
    'cap_c': 2500,
    'hair_c': 2400,
    'coat_c': 2300,
    'neck_g': 2251,
    'neck_cf': 2201,
    'neck_c': 2200,
    'cap_g': 2125,
    'cap_a': 2100,
    'hair_a': 2000,
    'neck_xf': 1980,
    'neck_x': 1975,
    'neck_z': 1963,
    'coat_x': 1960,
    'belt_f': 1952,
    'belt_g': 1951,
    'belt_c': 1950,
    'belt_c1': 1949,
    'face_c': 1925,
    'neck_a': 1900,
    'coat_g': 1850,
    'coat_a': 1800,
    'belt_a': 1700,
    'pants_f': 1651,
    'pants_c': 1650,
    'shoes_f': 1601,
    'shoes_c': 1600,
    'pants_g': 1501,
    'pants_a': 1500,
    'shoes_g': 1450,
    'shoes_a': 1400,
    'pants_b': 1300,
    'shoes_h': 1201,
    'shoes_b': 1200,
    'shoes_d': 1190,
    'pants_h': 1151,
    'pants_d': 1150,
    'belt_b': 1100,
    'neck_bf': 1050,
    'neck_b': 1000,
    'coat_h': 925,
    'coat_b': 900,
    'belt_h': 851,
    'belt_d': 850,
    'belt_d1': 849,
    'hair_b': 800,
    'cap_h': 750,
    'cap_b': 700,
    'neck_df': 650,
    'neck_d': 600,
    'neck_h': 550,
    'coat_d': 500,
    'hair_d': 400,
    'cap_d': 300,
    'neck_kf': 291,
    'neck_k': 290,
    'face_h': 270,
    'face_b': 100,
    'hair_f1': 20
}


class EquFileGenerator:
    """
    Equ 文件生成器
    
    根据 avatar 数据生成对应的 equ 文件内容。
    """
    
    # 部位到装备类型的映射
    PART_EQU_TYPE_MAP = {
        'coat': '[coat avatar]',
        'pants': '[pants avatar]',
        'belt': '[waist avatar]',
        'neck': '[breast avatar]',
        'shoes': '[shoes avatar]',
        'cap': '[hat avatar]',
        'hair': '[hair avatar]',
        'face': '[face avatar]',
        'skin': '[body avatar]',
    }
    
    # 职业到可用职业的映射（用于[usable job]字段）
    JOB_USABLE_MAP = {
        'sm': ['[swordman]', '[demonic swordman]'],
        'ft': ['[fighter]'],
        'fm': ['[fighter]'],
        'gn': ['[gunner]'],
        'gg': ['[gunner]'],
        'mg': ['[mage]', '[creator mage]'],
        'mm': ['[mage]', '[creator mage]'],
        'pr': ['[priest]'],
        'th': ['[thief]'],
    }
    
    # 职业到动画职业的映射（用于[animation job]字段）
    JOB_ANIMATION_MAP = {
        'sm': '[swordman]',
        'ft': '[fighter]',
        'fm': '[fighter]',
        'gn': '[gunner]',
        'gg': '[gunner]',
        'mg': '[mage]',
        'mm': '[mage]',
        'pr': '[priest]',
        'th': '[thief]',
    }
    
    # 职业到图标路径的映射
    JOB_ICON_MAP = {
        'sm': 'item/avatar/swordman',
        'ft': 'item/avatar/fighter',
        'fm': 'item/avatar/fighter',
        'gn': 'item/avatar/gunner',
        'gg': 'item/avatar/gunner',
        'mg': 'item/avatar/mage',
        'mm': 'item/avatar/mage',
        'pr': 'item/avatar/priest',
        'th': 'item/avatar/thief',
    }
    
    # 部位到图标文件名的映射
    PART_ICON_FILE_MAP = {
        'coat': 'acoat',
        'pants': 'apants',
        'belt': 'awaist',
        'neck': 'abreast',
        'shoes': 'ashoes',
        'cap': 'acap',
        'hair': 'ahair',
        'face': 'aface',
        'skin': 'abody',
    }
    
    # 部位到动画脚本 lay 文件的映射
    PART_LAY_MAP = {
        'sm': 'equipment/character/swordman.lay',
        'ft': 'equipment/character/fighter.lay',
        'fm': 'equipment/character/fighter.lay',
        'gn': 'equipment/character/gunner.lay',
        'gg': 'equipment/character/gunner.lay',
        'mg': 'equipment/character/mage.lay',
        'mm': 'equipment/character/mage.lay',
        'pr': 'equipment/character/priest.lay',
        'th': 'equipment/character/thief.lay',
    }
    
    def __init__(self, pvf_api: Optional[PvfUtilityApi] = None):
        """
        初始化 Equ 文件生成器
        
        Args:
            pvf_api: PVF API 客户端，用于获取模板
        """
        self._pvf_api = pvf_api
        self._templates: Dict[str, str] = {}
        self._layer_dict = layer_dict
    
    def _get_template_key(self, job_name: str, part_name: str) -> str:
        """获取模板键"""
        return f"{job_name}_{part_name}"
    
    def _fetch_template_from_pvf(self, job_name: str, part_name: str) -> Optional[str]:
        """
        从 PVF 获取模板 equ 文件
        
        Args:
            job_name: 职业名称
            part_name: 部位名称
            
        Returns:
            模板文件内容，如果获取失败则返回 None
        """
        if self._pvf_api is None:
            return None
        
        try:
            # 构建路径前缀
            job_code, job_path, _ = JOB_MAP[job_name]
            
            # 尝试从PVF中获取一个现有的equ文件作为模板
            # 路径格式: equipment/character/{job_path}avatar/{part}/{code}.equ
            search_path = f"equipment/character/{job_path}avatar/{part_name}"
            
            # 从 equipment.lst 中查找匹配的条目
            lst_info = self._pvf_api.get_lst_file_info('equipment/equipment.lst')
            
            for code_str, info in lst_info.items():
                if not isinstance(info, dict):
                    continue
                full_path = info.get('FullPath', '')
                if search_path in full_path and full_path.endswith('.equ'):
                    try:
                        content = self._pvf_api.get_file_content(full_path)
                        logger.debug(f"从PVF获取模板: {full_path}")
                        return content
                    except Exception as e:
                        logger.debug(f"获取文件内容失败 {full_path}: {e}")
                        continue
            
            return None
        except Exception as e:
            logger.warning(f"从PVF获取模板失败: {e}")
            return None
    
    def _build_template(self, job_name: str, part_name: str) -> str:
        """
        构建基础模板（当无法从PVF获取时使用）
        
        Args:
            job_name: 职业名称
            part_name: 部位名称
            
        Returns:
            基础模板内容
        """
        equ_type = self.PART_EQU_TYPE_MAP.get(part_name, '[coat avatar]')
        usable_jobs = self.JOB_USABLE_MAP.get(job_name, [f'[{job_name}]'])
        anim_job = self.JOB_ANIMATION_MAP.get(job_name, f'[{job_name}]')
        lay_file = self.PART_LAY_MAP.get(job_name, f'equipment/character/{job_name}.lay')
        
        # 构建usable job部分
        usable_jobs_str = '\n'.join([f'\t`{j}`' for j in usable_jobs])
        
        template = f"""#PVF_File

[name]
\t``

[name2]
\t``

[enable dye]
\t1\t0

[grade]
\t2

[part set index]
\t2

[usable job]
{usable_jobs_str}
[/usable job]

[attach type]
\t`[trade]`

[minimum level]
\t1

[icon]
\t`{self._get_icon_path(job_name, part_name)}`\t1

[equipment type]
\t`{equ_type}`\t0

[avatar type select]
\t7\t0\t0\t600\t0
\t30\t0\t0\t1200\t0
\t0\t0\t0\t2400\t0
\t0\t0\t0\t2600\t2
\t`[C socket]`\t`[C socket]`
[/avatar type select]

[avatar select ability]
\t`[SKILL_LEVEL]`\t`{anim_job.strip("[]")}`\t1\t1
[/avatar select ability]

[animation job]
\t`{anim_job}`

[variation]
\t{{variation_code}}\t{{suffix}}

{{layer_variations}}

[move wav]
\t`CLOTH_TOUCH`
"""
        return template
    
    def _get_icon_path(self, job_name: str, part_name: str) -> str:
        """
        获取图标路径
        
        Args:
            job_name: 职业名称
            part_name: 部位名称
            
        Returns:
            图标路径
        """
        base_path = self.JOB_ICON_MAP.get(job_name, f'item/avatar/{job_name}')
        icon_file = self.PART_ICON_FILE_MAP.get(part_name, 'acoat')
        
        # 构建职业前缀
        job_prefix_map = {
            'sm': 'sm', 'ft': 'ft', 'fm': 'ft',
            'gn': 'gn', 'gg': 'gn', 'mg': 'mg',
            'mm': 'mg', 'pr': 'pr', 'th': 'tf'
        }
        job_prefix = job_prefix_map.get(job_name, job_name)
        
        return f"{base_path}/{job_prefix}_{icon_file}.img"
    
    def _get_layer_index(self, part_name: str, layer: str) -> int:
        """
        获取 layer 的索引值
        
        Args:
            part_name: 部位名称
            layer: layer 字母（如 a, b, c）
            
        Returns:
            layer 索引值，如果找不到则返回默认值
        """
        key = f"{part_name}_{layer}"
        return self._layer_dict.get(key, 1000)
    
    def _build_layer_variations(
        self,
        job_name: str,
        part_name: str,
        layers: List[str]
    ) -> str:
        """
        构建图层变体部分
        
        Args:
            job_name: 职业名称
            part_name: 部位名称
            layers: 图层列表（如 ['a', 'b', 'c']）
            
        Returns:
            layer variation 部分的字符串
        """
        lay_path = self.PART_LAY_MAP.get(job_name, f'equipment/character/{job_name}.lay')
        
        variations = []
        for layer in layers:
            order = self._get_layer_index(part_name, layer)
            variations.append(f"[layer variation]\n\t{order}\n\t`{part_name}_{layer}`")
            variations.append(f"[equipment ani script]\n\t`{lay_path}`")
        
        return '\n\n'.join(variations)
    
    def get_template(self, job_name: str, part_name: str) -> str:
        """
        获取模板，优先从PVF获取，否则使用基础模板
        
        Args:
            job_name: 职业名称
            part_name: 部位名称
            
        Returns:
            模板内容
        """
        key = self._get_template_key(job_name, part_name)
        
        if key not in self._templates:
            # 尝试从PVF获取
            template = self._fetch_template_from_pvf(job_name, part_name)
            if template is None:
                # 使用基础模板
                template = self._build_template(job_name, part_name)
                logger.debug(f"使用基础模板: {key}")
            else:
                logger.debug(f"从PVF获取模板: {key}")
            
            self._templates[key] = template
        
        return self._templates[key]
    
    def generate_equ_content(
        self,
        job_name: str,
        part_name: str,
        avatar_index: AvatarIndex,
        suffix: int
    ) -> str:
        """
        生成 equ 文件内容
        
        Args:
            job_name: 职业名称
            part_name: 部位名称
            avatar_index: Avatar索引数据
            suffix: 后缀索引（用于选择图层）
            
        Returns:
            equ 文件内容
        """
        # 获取模板
        template = self.get_template(job_name, part_name)
        
        # 为 avatar 的所有 layer 生成 layer variations
        # 注意：avatar_index.layers 包含所有可用的 layer 字母
        # 我们不为每个 suffix 选择不同的 layer，而是为所有 layer 生成字段
        layers_to_use = avatar_index.layers if avatar_index.layers else ['a']
        layer_variations = self._build_layer_variations(
            job_name, part_name, layers_to_use
        )
        
        # 替换模板中的变量
        content = template
        
        # 替换 variation_code 和 suffix
        content = content.replace('{{variation_code}}', str(avatar_index.code))
        content = content.replace('{{suffix}}', str(suffix))
        content = content.replace('{{layer_variations}}', layer_variations)
        
        # 如果模板来自PVF，需要替换[variation]和[layer variation]
        if '{{variation_code}}' not in template:
            # 替换[variation]行 - 同时替换avatar code和suffix
            content = re.sub(
                r'(\[variation\]\s*\n\s*)\d+(\s+)\d+',
                rf'\g<1>{avatar_index.code}\g<2>{suffix}',
                content
            )
            
            # 对于每个 [animation job] 段，替换其后面的 [layer variation] 部分
            # 找到所有 [animation job] ... [move wav] 或下一个 [animation job] 之间的内容
            # 使用更宽松的正则，支持 \r\n 和 \n 换行符
            anim_job_pattern = r'(\[animation job\]\s*\r?\n\s*`\[([^\]]+)\]`\s*\r?\n+\s*\[variation\]\s*\r?\n\s*\d+\s+\d+)\s*\r?\n+((?:\s*\[layer variation\]\s*\r?\n[^\[]*\[equipment ani script\][^\[]*)+)(?=\s*\[animation job\]|\s*\[move wav\])'
            
            def replace_layers_in_block(match):
                prefix = match.group(1)
                anim_job_name = match.group(2)
                # 根据 animation job 确定 lay 文件
                if 'demonic' in anim_job_name.lower():
                    lay_file = f'equipment/character/dsswordman.lay'
                elif 'at fighter' in anim_job_name.lower():
                    lay_file = f'equipment/character/atfighter.lay'
                elif 'at gunner' in anim_job_name.lower():
                    lay_file = f'equipment/character/atgunner.lay'
                elif 'at mage' in anim_job_name.lower() or 'creator' in anim_job_name.lower():
                    lay_file = f'equipment/character/atmage.lay'
                else:
                    # 基础职业
                    job_lower = anim_job_name.lower().replace(' ', '')
                    lay_file = f'equipment/character/{job_lower}.lay'
                
                # 生成新的 layer variations
                new_layers = self._build_layer_variations(job_name, part_name, layers_to_use)
                # 替换 lay 文件路径
                new_layers = new_layers.replace(
                    self.PART_LAY_MAP.get(job_name, f'equipment/character/{job_name}.lay'),
                    lay_file
                )
                return prefix + '\n\n' + new_layers + '\n'
            
            content = re.sub(anim_job_pattern, replace_layers_in_block, content, flags=re.DOTALL)
        
        return content


class EquipmentCodeGenerator:
    """装备编码生成器"""
    
    # 默认的 PVF 已有装备 lst 文件路径
    DEFAULT_EXISTING_LST_PATH = "equipment/equipment.lst"
    
    def __init__(
        self,
        validator: Optional[EquipmentTagValidator] = None,
        start_code: int = 133011,
        pvf_api: Optional[PvfUtilityApi] = None,
        existing_lst_path: Optional[str] = None,
        equ_output_dir: Optional[Path] = None,
        generate_equ_files: bool = True,
        max_equ_per_job_part: Optional[int] = 10  # 新增：限制每个职业部位生成的equ数量
    ):
        """
        初始化生成器
        
        Args:
            validator: 标签验证器，None 则创建新实例
            start_code: lst 文件起始编码（保留以向后兼容，但实际使用新的编码格式）
            pvf_api: PVF API 客户端，None 则自动创建
            existing_lst_path: 已有装备 lst 文件路径，None 则使用默认值
            equ_output_dir: equ 文件输出目录，None 则使用默认目录
            generate_equ_files: 是否生成 equ 文件，默认 True
            max_equ_per_job_part: 每个职业部位最多生成的 equ 数量，None 则无限制
        """
        self.validator = validator or EquipmentTagValidator()
        self.start_code = start_code
        self._equ_codes: Dict[str, str] = {}
        self._equ_contents: Dict[str, str] = {}  # 存储生成的equ内容
        self._error_count = 0
        
        # 存储 PVF 中已有的装备代码
        self._existing_codes: Set[str] = set()
        self._pvf_api = pvf_api
        self._existing_lst_path = existing_lst_path or self.DEFAULT_EXISTING_LST_PATH
        
        # 存储每个职业+部位组合的当前可用代码
        self._code_counters: Dict[str, int] = {}
        
        # equ文件生成相关
        self._generate_equ_files = generate_equ_files
        self._equ_output_dir = equ_output_dir or BASE_DIR / "generated_equ"
        self._equ_generator: Optional[EquFileGenerator] = None
        self._max_equ_per_job_part = max_equ_per_job_part  # 每个职业部位的最大equ数量
        
        # 如果提供了 PVF API 或配置了端口，则加载已有装备代码
        if self._pvf_api is None:
            try:
                self._pvf_api = PvfUtilityApi(host=PVF_API_HOST, port=PVF_API_PORT)
            except Exception as e:
                logger.warning(f"无法创建 PVF API 客户端: {e}")
        
        # 初始化equ文件生成器
        if self._generate_equ_files:
            self._equ_generator = EquFileGenerator(pvf_api=self._pvf_api)
        
        self._load_existing_codes()
        self._init_code_counters()
    
    @staticmethod
    def format_equ_code(base_code: int, suffix: int) -> str:
        """
        生成标准化的 7 位编码（6位基础+1位后缀）
        
        Args:
            base_code: 基础编码
            suffix: 后缀索引
            
        Returns:
            7 位编码字符串
        """
        return f"{base_code:06d}{suffix}"
    
    def _get_base_code(self, job_name: str, part_name: str) -> int:
        """
        获取指定职业+部位的基础代码（60{job_code}5{part_code}0000）
        
        格式：60 + job_code(1位) + 5 + part_code(1位) + 0000
        例如：sm(1) + coat(0) = 60150000
        
        Args:
            job_name: 职业名称
            part_name: 部位名称
            
        Returns:
            8位基础代码
        """
        job_code = JOB_MAP[job_name][0]
        part_code = PART_CODE_MAP[part_name][0]
        return int(f"60{job_code}5{part_code}0000")
    
    def _init_code_counters(self) -> None:
        """
        初始化各职业+部位的代码计数器
        
        从 PVF 的 equipment.lst 中找到每个职业+部位的最大代码值，
        然后在此基础上 +1 作为起始代码。
        
        代码格式：60{job_code}5{part_code}XXXX
        """
        # 按职业+部位分组，找到每组的最大代码
        max_codes: Dict[str, int] = {}
        
        for code_str in self._existing_codes:
            # 代码格式：60{job_code}5{part_code}XXXX
            if len(code_str) >= 9 and code_str.startswith('60'):
                try:
                    job_code = int(code_str[2])  # 第3位
                    part_code = int(code_str[4])  # 第5位
                    
                    # 找到对应的职业和部位名称
                    job_name = None
                    for j_name, (j_code, _, _) in JOB_MAP.items():
                        if j_code == job_code:
                            job_name = j_name
                            break
                    
                    part_name = None
                    for p_name, (p_code, _) in PART_CODE_MAP.items():
                        if p_code == part_code:
                            part_name = p_name
                            break
                    
                    if job_name and part_name:
                        counter_key = f"{job_name}_{part_name}"
                        code_int = int(code_str)
                        
                        if counter_key not in max_codes or code_int > max_codes[counter_key]:
                            max_codes[counter_key] = code_int
                
                except (ValueError, IndexError):
                    continue
        
        # 设置各职业+部位的起始代码
        for job_name in JOB_MAP:
            for part_name in PART_CODE_MAP:
                counter_key = f"{job_name}_{part_name}"
                base_code = self._get_base_code(job_name, part_name)
                
                if counter_key in max_codes:
                    # 从最大值 +1 开始
                    self._code_counters[counter_key] = max_codes[counter_key] + 1
                    logger.debug(f"{counter_key} 从 equipment.lst 最大值 {max_codes[counter_key]} 继续，起始代码 = {self._code_counters[counter_key]}")
                else:
                    # 该组合在 PVF 中没有代码，从基础代码开始
                    self._code_counters[counter_key] = base_code
                    logger.debug(f"{counter_key} 在 PVF 中无记录，从基础代码 {base_code} 开始")
    
    def _get_next_available_code(self, job_name: str, part_name: str) -> str:
        """
        获取下一个可用代码
        
        Args:
            job_name: 职业名称
            part_name: 部位名称
            
        Returns:
            可用的完整代码字符串
        """
        counter_key = f"{job_name}_{part_name}"
        max_attempts = 1000
        
        for _ in range(max_attempts):
            current_code = self._code_counters[counter_key]
            full_code = str(current_code)
            
            # 检查是否可用
            if full_code not in self._existing_codes and full_code not in self._equ_codes:
                # 增加计数器供下次使用
                self._code_counters[counter_key] = current_code + 1
                return full_code
            
            # 不可用则递增并重试
            self._code_counters[counter_key] = current_code + 1
        
        raise RuntimeError(f"无法找到可用代码，已尝试 {max_attempts} 次")
    
    def _load_existing_codes(self) -> None:
        """
        从 PVF 加载已有装备代码到 _existing_codes 集合中
        """
        if self._pvf_api is None:
            logger.warning("PVF API 客户端未初始化，无法加载已有装备代码")
            return
        
        try:
            lst_info = self._pvf_api.get_lst_file_info(self._existing_lst_path)
            
            for code_str, info in lst_info.items():
                if isinstance(info, dict) and 'FullPath' in info:
                    self._existing_codes.add(code_str)
            
            logger.info(f"已从 {self._existing_lst_path} 加载 {len(self._existing_codes)} 条已有装备代码")
        
        except Exception as e:
            logger.warning(f"加载已有装备代码失败: {e}")
    
    def reload_existing_codes(self, lst_path: Optional[str] = None) -> None:
        """
        重新加载已有装备代码
        
        Args:
            lst_path: 新的 lst 文件路径，None 则使用初始化时的路径
        """
        if lst_path:
            self._existing_lst_path = lst_path
        self._existing_codes.clear()
        self._load_existing_codes()
    
    def is_code_exists(self, code: str) -> bool:
        """
        检查装备代码是否已存在（在 PVF 中或已生成）
        
        Args:
            code: 装备代码
            
        Returns:
            True 如果代码已存在
        """
        return code in self._existing_codes or code in self._equ_codes
    
    def _check_tsv_exists(
        self,
        job_name: str,
        part_name: str,
        base_code: int,
        suffix: int
    ) -> bool:
        """
        检查 TSV 中是否已存在该装备
        
        Args:
            job_name: 职业名称
            part_name: 部位名称
            base_code: 基础编码（avatar_index.code）
            suffix: 后缀索引
            
        Returns:
            True 如果 TSV 中已存在
        """
        equ_job = JOB_MAP[job_name][2]
        equ_part = PART_CODE_MAP[part_name][1]
        variation = f"{base_code}\t{suffix}"
        
        return self.validator.verify((equ_job, equ_part, variation))
    
    def _generate_entry(
        self,
        job_name: str,
        part_name: str,
        avatar_index: AvatarIndex,
        suffix: int
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        """
        生成单条装备记录
        
        编码格式：60{job_code}5{part_code}0000，在此基础上递增
        
        Returns:
            (编码, 路径, equ内容) 元组，如果 TSV 中已存在则返回 None
        """
        # 1. 首先检查 TSV 中是否已存在
        if self._check_tsv_exists(job_name, part_name, avatar_index.code, suffix):
            logger.debug(f"TSV 中已存在，跳过: {job_name}/{part_name}/{avatar_index.code}/{suffix}")
            return None
        
        # 2. 获取下一个可用代码
        # 代码格式：60{job_code}5{part_code}0000 基础上递增
        equ_code = self._get_next_available_code(job_name, part_name)
        
        # 3. 生成路径
        job_code, job_path, _ = JOB_MAP[job_name]
        equ_path = EQU_PATH_TEMPLATE.format(
            job=job_path,
            part=part_name,
            code=equ_code
        )
        
        # 4. 生成 equ 文件内容
        equ_content = None
        if self._generate_equ_files and self._equ_generator:
            try:
                equ_content = self._equ_generator.generate_equ_content(
                    job_name, part_name, avatar_index, suffix
                )
            except Exception as e:
                logger.warning(f"生成 equ 内容失败 {job_name}/{part_name}/{avatar_index.code}/{suffix}: {e}")
        
        return equ_code, equ_path, equ_content
    
    def get_existing_codes_count(self) -> int:
        """获取已加载的 PVF 已有装备代码数量"""
        return len(self._existing_codes)
    
    def process_avatar_data(self, data: Dict) -> Dict[str, str]:
        """
        处理 avatar 数据生成装备编码
        
        Args:
            data: avatar_data.json 解析后的字典
            
        Returns:
            编码到路径的映射字典
        """
        self._equ_codes.clear()
        self._equ_contents.clear()
        self._error_count = 0
        
        # 记录每个职业+部位已生成的数量（用于限制）
        job_part_counts: Dict[str, int] = {}
        
        logger.info(f"开始生成装备编码，已有装备代码数: {len(self._existing_codes)}")
        
        for job_name, parts_data in data.items():
            if job_name not in JOB_MAP:
                logger.warning(f"未知职业 {job_name}，跳过")
                continue
            
            if not isinstance(parts_data, dict):
                self._error_count += 1
                continue
            
            for part_name, indexes in parts_data.items():
                if part_name not in PART_CODE_MAP:
                    continue
                
                if not isinstance(indexes, list):
                    self._error_count += 1
                    continue
                
                # 检查该职业+部位是否已达到限制
                counter_key = f"{job_name}_{part_name}"
                if self._max_equ_per_job_part is not None:
                    current_count = job_part_counts.get(counter_key, 0)
                    if current_count >= self._max_equ_per_job_part:
                        logger.debug(f"{counter_key} 已达到限制 {self._max_equ_per_job_part}，跳过")
                        continue
                
                for idx, index_data in enumerate(indexes):
                    avatar_index = AvatarIndex.from_tuple(index_data)
                    if avatar_index is None:
                        self._error_count += 1
                        continue
                    
                    # 为每个 count 生成编码
                    for suffix in range(avatar_index.count):
                        # 检查是否达到限制
                        if self._max_equ_per_job_part is not None:
                            current_count = job_part_counts.get(counter_key, 0)
                            if current_count >= self._max_equ_per_job_part:
                                logger.info(f"{counter_key} 已达到限制 {self._max_equ_per_job_part}，停止生成")
                                break
                        
                        entry = self._generate_entry(
                            job_name, part_name, avatar_index, suffix
                        )
                        if entry:
                            equ_code, equ_path, equ_content = entry
                            self._equ_codes[equ_code] = equ_path
                            if equ_content:
                                self._equ_contents[equ_code] = equ_content
                            
                            # 增加计数
                            if self._max_equ_per_job_part is not None:
                                job_part_counts[counter_key] = job_part_counts.get(counter_key, 0) + 1
                    
                    # 检查是否达到限制（跳出外层循环）
                    if self._max_equ_per_job_part is not None:
                        current_count = job_part_counts.get(counter_key, 0)
                        if current_count >= self._max_equ_per_job_part:
                            break
        
        return self._equ_codes
    
    def write_lst_file(self, output_path: Path) -> None:
        """
        写入 lst 文件
        
        Args:
            output_path: 输出文件路径
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        sorted_items = sorted(self._equ_codes.items(), key=lambda x: x[0])
        
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            for code, path in sorted_items:
                f.write(f"{code}\t{path}\n")
        
        logger.info(f"已写入 {len(sorted_items)} 条记录到 {output_path}")
    
    def write_equ_files(self, output_dir: Optional[Path] = None) -> int:
        """
        写入 equ 文件到本地目录
        
        Args:
            output_dir: 输出目录，None 则使用初始化时设置的目录
            
        Returns:
            写入的文件数量
        """
        if not self._equ_contents:
            logger.info("没有 equ 文件内容需要写入")
            return 0
        
        output_dir = Path(output_dir) if output_dir else self._equ_output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        count = 0
        for equ_code, equ_path in self._equ_codes.items():
            if equ_code not in self._equ_contents:
                continue
            
            # 构建文件路径（去掉路径中的`字符和equipment/前缀）
            clean_path = equ_path.strip('`')
            if clean_path.startswith('equipment/'):
                clean_path = clean_path[10:]  # 去掉 "equipment/"
            
            file_path = output_dir / clean_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 写入文件
            content = self._equ_contents[equ_code]
            try:
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    f.write(content)
                count += 1
            except Exception as e:
                logger.error(f"写入 equ 文件失败 {file_path}: {e}")
        
        logger.info(f"已写入 {count} 个 equ 文件到 {output_dir}")
        return count
    
    def import_equ_files_to_pvf(self) -> Tuple[int, List[str]]:
        """
        将生成的 equ 文件导入到 PVF
        
        Returns:
            (成功数量, 失败文件列表)
        """
        if not self._equ_contents:
            logger.info("没有 equ 文件需要导入")
            return 0, []
        
        if self._pvf_api is None:
            logger.error("PVF API 未初始化，无法导入文件")
            return 0, []
        
        file_info_list = []
        for equ_code, equ_path in self._equ_codes.items():
            if equ_code not in self._equ_contents:
                continue
            
            # equ_path 已经包含 `equipment/...` 格式，需要去掉 ` 字符
            clean_path = equ_path.strip('`')
            content = self._equ_contents[equ_code]
            
            file_info_list.append({
                "FilePath": clean_path,
                "FileContent": content
            })
        
        if not file_info_list:
            return 0, []
        
        try:
            failed = self._pvf_api.import_files(file_info_list)
            success_count = len(file_info_list) - len(failed)
            logger.info(f"导入 PVF 完成: 成功 {success_count}, 失败 {len(failed)}")
            return success_count, failed
        except Exception as e:
            logger.error(f"导入 PVF 失败: {e}")
            return 0, [f["FilePath"] for f in file_info_list]
    
    def generate(
        self,
        json_path: Path,
        output_path: Path,
        write_equ_to_local: bool = True,
        import_to_pvf: bool = False
    ) -> Dict[str, any]:
        """
        主生成流程
        
        Args:
            json_path: 输入 JSON 文件路径
            output_path: 输出 lst 文件路径
            write_equ_to_local: 是否将 equ 文件写入本地目录
            import_to_pvf: 是否将 equ 文件导入到 PVF
            
        Returns:
            统计信息字典
        """
        json_path = Path(json_path)
        
        # 1. 读取 JSON
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, dict):
                raise ValueError("JSON 根节点必须是字典")
            
            logger.info(f"成功读取 JSON 数据，包含 {len(data)} 个职业")
        
        except FileNotFoundError:
            logger.error(f"JSON 文件不存在: {json_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"JSON 格式无效: {e}")
            raise
        
        # 2. 处理数据
        self.process_avatar_data(data)
        
        # 3. 写入 lst 文件
        self.write_lst_file(output_path)
        
        # 4. 写入 equ 文件到本地
        equ_count = 0
        if write_equ_to_local and self._generate_equ_files:
            equ_count = self.write_equ_files()
        
        # 5. 导入到 PVF
        imported_count = 0
        if import_to_pvf and self._generate_equ_files:
            imported_count, _ = self.import_equ_files_to_pvf()
        
        # 6. 返回统计
        stats = {
            "total_codes": len(self._equ_codes),
            "error_count": self._error_count,
            "output_file": str(output_path),
            "existing_codes": len(self._existing_codes),
            "equ_files_generated": len(self._equ_contents),
            "equ_files_written": equ_count,
            "equ_files_imported": imported_count,
            "max_per_job_part": self._max_equ_per_job_part,
        }
        
        logger.info(f"生成完成！新装备编码数: {stats['total_codes']}, PVF已有: {stats['existing_codes']}, 错误数: {stats['error_count']}")
        if self._generate_equ_files:
            logger.info(f"Equ文件: 生成 {stats['equ_files_generated']}, 本地写入 {stats['equ_files_written']}, PVF导入 {stats['equ_files_imported']}")
        
        return stats


def main():
    """主入口"""
    generator = EquipmentCodeGenerator()
    try:
        stats = generator.generate(
            json_path=AVATAR_DATA_JSON,
            output_path=EQUIPMENT_LST,
            write_equ_to_local=True,
            import_to_pvf=False  # 默认不导入到PVF，避免意外修改
        )
        print(f"\n生成统计:")
        print(f"  - 新装备编码数: {stats['total_codes']}")
        print(f"  - PVF已有装备数: {stats['existing_codes']}")
        print(f"  - 错误数: {stats['error_count']}")
        print(f"  - 输出文件: {stats['output_file']}")
        if 'equ_files_generated' in stats:
            print(f"  - Equ文件生成数: {stats['equ_files_generated']}")
            print(f"  - Equ文件本地写入数: {stats['equ_files_written']}")
            print(f"  - Equ文件PVF导入数: {stats['equ_files_imported']}")
    except Exception as e:
        logger.error(f"生成失败: {e}")
        raise


def demo_load_existing_codes():
    """
    演示：从 PVF 加载已有装备代码并生成新装备代码
    """
    from pvf_api_client import PvfUtilityApi
    from config import PVF_API_HOST, PVF_API_PORT
    
    # 创建 PVF API 客户端
    api = PvfUtilityApi(host=PVF_API_HOST, port=PVF_API_PORT)
    
    # 创建生成器并传入 PVF API 客户端
    generator = EquipmentCodeGenerator(pvf_api=api)
    
    print(f"已加载 {generator.get_existing_codes_count()} 条已有装备代码")
    
    # 检查某个代码是否已存在
    test_code = "10018"
    if generator.is_code_exists(test_code):
        print(f"代码 {test_code} 已存在于 PVF 中")
    
    # 生成新装备代码时会自动跳过已存在的代码
    # ...


if __name__ == "__main__":
    main()
