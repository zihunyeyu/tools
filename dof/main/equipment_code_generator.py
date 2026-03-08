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

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.tsv_validator import EquipmentTagValidator
from modules.pvf_api_client import PvfUtilityApi
from config import (
    AVATAR_TABLE_BASE_PATH, JOB_MAP, PART_CODE_MAP, LAYER_DICT,
    EQU_PATH_TEMPLATE, EQUIPMENT_LST, SHOP_ETC, AVATAR_DATA_JSON,
    PVF_API_HOST, PVF_API_PORT, BASE_DIR,
    EQU_GENERATION_CONFIG
)
from modules.equ_template_cache import EquTemplateCache, init_template_cache
from modules.avatar_table_loader import AvatarTableLoader, construct_code, generate_equ_name

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
        if not isinstance(data, (list, tuple)) or len(data) < 3:
            return None
        code, count, layers, lost = data
        if not isinstance(code, int) or not isinstance(count, int):
            return None
        return cls(code=code, count=count, layers=list(layers) if layers else [])


# 使用 config.LAYER_DICT


class EquFileGenerator:
    """
    Equ 文件生成器
    
    根据 avatar 数据生成对应的 equ 文件内容。
    
    支持两种模板获取方式（按优先级）：
    1. EquTemplateCache - 从 equ_models.py 指定的代码预加载的模板
    2. PVF 实时获取 - 从 PVF 中搜索现有 equ 文件作为模板
    3. 基础模板 - 使用内置的基础模板
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
        'body': '[skin avatar]',
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
        'neck': 'aneck',
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
    
    # Job 到 icon 路径和缩写的映射（用于重新生成 icon 路径）
    # 格式: job: (路径名, 文件名前缀)
    # 注意: 转职/特定性别职业有特殊的文件夹命名
    JOB_ICON_MAP_DETAILED = {
        'sm': ('swordman', 'sm'),
        'ft': ('fighter', 'ft'),      # 格斗家(女)
        'fm': ('atfighter', 'fm'),    # 格斗家(男) - 转职后路径
        'gn': ('gunner', 'gn'),       # 神枪手(男)
        'gg': ('atgunner', 'gg'),     # 神枪手(女) - 转职后路径
        'mg': ('mage', 'mg'),         # 魔法师(女)
        'mm': ('atmage', 'mm'),       # 魔法师(男) - 转职后路径
        'pr': ('priest', 'pr'),
        'th': ('thief', 'tf'),        # thief 的缩写是 tf
    }
    
    # 部位到 icon 文件缩写的映射
    PART_ICON_ABBREV = {
        'coat': 'acoat',
        'pants': 'apants',
        'belt': 'abelt',
        'neck': 'aneck',
        'shoes': 'ashoes',
        'cap': 'acap',
        'hair': 'ahair',
        'face': 'aface',
        'skin': 'abody',
    }
    
    def __init__(self, pvf_api: Optional[PvfUtilityApi] = None, use_cache: bool = True, avatar_table_loader: Optional[AvatarTableLoader] = None):
        """
        初始化 Equ 文件生成器
        
        Args:
            pvf_api: PVF API 客户端，用于获取模板
            use_cache: 是否使用 EquTemplateCache，默认为 True
            avatar_table_loader: 装扮表加载器，用于获取 name 和 icon_index
        """
        self._pvf_api = pvf_api
        self._templates: Dict[str, str] = {}
        self._layer_dict = LAYER_DICT
        self._template_cache: Optional[EquTemplateCache] = None
        self._avatar_loader: Optional[AvatarTableLoader] = avatar_table_loader
        
        # 初始化模板缓存
        if use_cache:
            try:
                self._template_cache = init_template_cache()
                logger.info("EquFileGenerator: 已启用模板缓存")
            except Exception as e:
                logger.warning(f"EquFileGenerator: 初始化模板缓存失败: {e}，将使用 PVF 实时获取")
        
        # 初始化装扮表加载器
        if self._avatar_loader is None:
            try:
                # 默认路径
                # avatar_base_path = r'D:\DOF\output\Avatar'
                self._avatar_loader = AvatarTableLoader(AVATAR_TABLE_BASE_PATH)
                logger.info("EquFileGenerator: 已初始化装扮表加载器")
            except Exception as e:
                logger.warning(f"EquFileGenerator: 初始化装扮表加载器失败: {e}")
    
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
    
    def _replace_name_tag(self, content: str, name: str) -> str:
        """
        替换 [name] 标签内容
        
        Args:
            content: 原始内容
            name: 新的 name 值
            
        Returns:
            替换后的内容
        """
        # 匹配 [name]\n\t`...`
        pattern = r'(\[name\]\s*\n\s*`)([^`]+)(`)'
        return re.sub(pattern, rf'\g<1>{name}\g<3>', content, count=1)
    
    def _replace_or_add_flavor_text_tag(self, content: str, flavor_text: str) -> str:
        """
        替换或添加 [flavor text] 标签内容
        
        如果 flavor_text 为空，则不添加该标签。
        如果内容中已存在 [flavor text] 标签，则替换其值。
        如果不存在，则在 [name] 标签后添加。
        
        Args:
            content: 原始内容
            flavor_text: flavor text 值
            
        Returns:
            替换后的内容
        """
        # 如果 flavor_text 为空，移除已有的 [flavor text] 标签（如果存在）
        if not flavor_text:
            # 匹配 [flavor text]\n\t`...`\n 或类似格式
            pattern = r'\n?\[flavor text\]\s*\r?\n\s*`[^`]*`\s*\r?\n'
            return re.sub(pattern, '\n', content, count=1)
        
        # 格式化 flavor_text 行
        flavor_section = f"\n[flavor text]\n\t`{flavor_text}`\n"
        
        # 检查是否已存在 [flavor text] 标签
        if '[flavor text]' in content:
            # 替换现有的 flavor text
            pattern = r'(\[flavor text\]\s*\r?\n\s*`)([^`]*)(`)'
            return re.sub(pattern, rf'\g<1>{flavor_text}\g<3>', content, count=1)
        else:
            # 在 [name] 标签后插入
            # 找到 [name] 标签的结束位置
            pattern = r'(\[name\]\s*\r?\n\s*`[^`]*`\s*\r?\n)'
            return re.sub(pattern, rf'\g<1>{flavor_section}', content, count=1)
    
    def _replace_icon_tag(self, content: str, icon_path: str, icon_index: int) -> str:
        """
        替换 [icon] 标签内容
        
        Args:
            content: 原始内容
            icon_path: 新的 icon 路径
            icon_index: 图标索引
            
        Returns:
            替换后的内容
        """
        # 匹配 [icon]\n\t`...`\t{index}
        # 需要处理不同的换行符格式
        pattern = r'(\[icon\]\s*\r?\n\s*`)([^`]+)(`\s+)(\d+)'
        
        def replace_icon(match):
            prefix = match.group(1)
            # 原路径不保留，使用新路径
            middle = match.group(3)
            return f'{prefix}{icon_path}{middle}{icon_index}'
        
        return re.sub(pattern, replace_icon, content, count=1)
    
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
    
    def _generate_icon_path(self, job_name: str, part_name: str) -> str:
        """
        生成 icon 路径
        
        格式: item/avatar/{job_path}/{job_prefix}_{part_icon}.img
        
        Args:
            job_name: 职业代码
            part_name: 部位代码
            
        Returns:
            icon 路径
        """
        job_path, job_prefix = self.JOB_ICON_MAP_DETAILED.get(job_name, (job_name, job_name))
        part_icon = self.PART_ICON_ABBREV.get(part_name, f'a{part_name}')
        return f"item/avatar/{job_path}/{job_prefix}_{part_icon}.img"
    
    def _get_equ_name_and_icon(self, job_name: str, part_name: str, avatar_code: int, suffix: int) -> Tuple[str, int]:
        """
        获取 equ 的 name 和 icon_index
        
        优先从装扮表查找，找不到使用默认格式
        
        Args:
            job_name: 职业代码
            part_name: 部位代码
            avatar_code: avatar 变体代码
            suffix: 后缀索引
            
        Returns:
            (name, icon_index)
        """
        if self._avatar_loader:
            name, icon_index, found = generate_equ_name(
                job_name, part_name, avatar_code, suffix, self._avatar_loader
            )
            return name, icon_index
        else:
            # 装扮表加载器不可用，使用默认格式
            code = construct_code(avatar_code, suffix)
            default_name = f"{job_name}_{part_name}_{code}"
            return default_name, 0
    
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
        获取模板，优先级：缓存 > PVF实时获取 > 基础模板
        
        Args:
            job_name: 职业名称
            part_name: 部位名称
            
        Returns:
            模板内容
        """
        key = self._get_template_key(job_name, part_name)
        
        if key not in self._templates:
            template = None
            
            # 1. 优先从缓存获取（基于 equ_models.py 的指定代码）
            if self._template_cache:
                cache_template = self._template_cache.get_template(job_name, part_name)
                if cache_template:
                    template = cache_template.content
                    logger.debug(f"从缓存获取模板: {key} (code: {cache_template.code})")
            
            # 2. 缓存未命中，尝试从PVF实时获取
            if template is None and self._pvf_api:
                template = self._fetch_template_from_pvf(job_name, part_name)
                if template:
                    logger.debug(f"从PVF获取模板: {key}")
            
            # 3. 使用基础模板
            if template is None:
                template = self._build_template(job_name, part_name)
                logger.debug(f"使用基础模板: {key}")
            
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
        
        # 获取 name 和 icon_index（从装扮表或默认格式）
        equ_name, icon_index = self._get_equ_name_and_icon(
            job_name, part_name, avatar_index.code, suffix
        )
        
        # 获取套装名（用于 flavor text）
        suit_name = None
        if self._avatar_loader:
            # 构造完整的 code（如 avatar_code=36, suffix=0 -> 3600）
            full_code = int(f"{avatar_index.code}{suffix:02d}")
            suit_name = self._avatar_loader.get_suit_name(job_name, part_name, full_code)
        
        # 生成 icon 路径
        icon_path = self._generate_icon_path(job_name, part_name)
        
        # 替换模板中的变量
        content = template
        
        # 替换 name 标签
        content = self._replace_name_tag(content, equ_name)
        
        # 替换或添加 flavor text 标签
        content = self._replace_or_add_flavor_text_tag(content, suit_name)
        
        # 替换 icon 标签
        content = self._replace_icon_tag(content, icon_path, icon_index)
        
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
        max_equ_per_job_part: Optional[int] = None  # 新增：限制每个职业部位生成的equ数量
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
        self._equ_output_dir = equ_output_dir or BASE_DIR / "output/generated_equ"
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
                            self._equ_codes[equ_code] = equ_path.replace('/body', '/skin')
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
                f.write(f"{code}\t{path.replace('equipment/', '')}\n")
        
        logger.info(f"已写入 {len(sorted_items)} 条记录到 {output_path}")
    
    def _get_last_avatar_index_from_pvf(self) -> int:
        """
        从 PVF 的 etc/newcashshop.etc 读取 [avatar] 标签最后一项的起始标签
        
        Returns:
            最后一项的起始标签，如果失败则返回默认值 133011
        """
        default_last_index = 133011  # 默认值，用于计算起始索引
        
        if self._pvf_api is None:
            logger.warning("PVF API 未初始化，使用默认起始标签")
            return default_last_index
        
        try:
            content = self._pvf_api.get_file_content('etc/newcashshop.etc')
            if not content:
                logger.warning("无法读取 newcashshop.etc，使用默认起始标签")
                return default_last_index
            
            # 解析 [avatar] 部分
            lines = content.split('\n')
            in_avatar_section = False
            last_start_index = 0
            
            for line in lines:
                stripped = line.strip()
                
                # 检测 [avatar] 标签开始
                if stripped == '[avatar]':
                    in_avatar_section = True
                    continue
                
                # 检测其他标签（离开 [avatar] 部分）
                if in_avatar_section and stripped.startswith('[') and stripped != '[avatar]':
                    break
                
                # 解析 [avatar] 中的条目（以制表符开头的行）
                if in_avatar_section and stripped and stripped[0].isdigit():
                    parts = stripped.split('\t')
                    if parts and parts[0].isdigit():
                        idx = int(parts[0])
                        if idx > last_start_index:
                            last_start_index = idx
            
            if last_start_index > 0:
                logger.info(f"从 PVF 读取到 [avatar] 最后一项起始标签: {last_start_index}")
                return last_start_index
            else:
                logger.warning("未在 [avatar] 中找到有效条目，使用默认起始标签")
                return default_last_index
                
        except Exception as e:
            logger.error(f"读取 PVF [avatar] 标签失败: {e}")
            return default_last_index
    
    def write_shop_etc(self, output_path: Path) -> Optional[List[str]]:
        """
        写入 shop.etc 文件
        
        格式: <start_index>\t{equ_code}\t3\t0\t0\t-1\t-1\t{equ_code}\t4\t0\t0\t-1
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            生成的 shop.etc 条目列表（用于更新 PVF），失败返回 None
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        sorted_codes = sorted(self._equ_codes.keys(), key=lambda x: int(x))
        
        # 动态获取起始标签：最后一项 + 1000
        last_index = self._get_last_avatar_index_from_pvf()
        start_index = last_index + 1000
        logger.info(f"shop.etc 起始标签: {start_index} (基于 PVF 最后一项 {last_index} + 1000)")
        
        shop_entries = []
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            for equ_code in sorted_codes:
                # 格式: <start_index>\t{equ_code}\t3\t0\t0\t-1\t-1\t{equ_code}\t4\t0\t0\t-1
                line = f"\t{start_index}\t{equ_code}\t3\t0\t0\t-1\t-1\t{equ_code}\t4\t0\t0\t-1\n"
                f.write(line)
                shop_entries.append(f"{start_index}\t{equ_code}\t3\t0\t0\t-1\t-1\t{equ_code}\t4\t0\t0\t-1")
                start_index += 1
        
        logger.info(f"已写入 {len(sorted_codes)} 条记录到 {output_path}")
        return shop_entries
    
    def _update_newcashshop_etc_in_pvf(self, shop_entries: List[str]) -> bool:
        """
        将新生成的 [avatar] 条目更新到 PVF 的 etc/newcashshop.etc
        
        Args:
            shop_entries: shop.etc 条目列表（每行一个，不含开头的制表符）
            
        Returns:
            成功返回 True
        """
        if self._pvf_api is None:
            logger.error("PVF API 未初始化，无法更新 newcashshop.etc")
            return False
        
        if not shop_entries:
            logger.info("没有 shop.etc 条目需要更新")
            return True
        
        try:
            # 读取当前 PVF 中的 newcashshop.etc
            current_content = self._pvf_api.get_file_content('etc/newcashshop.etc')
            if not current_content:
                logger.error("无法读取 PVF 中的 newcashshop.etc")
                return False
            
            # 构建新的 [avatar] 条目（带制表符前缀）
            new_avatar_lines = '\n'.join([f"\t{entry}" for entry in shop_entries])
            
            # 找到 [avatar] 标签的位置
            lines = current_content.split('\n')
            avatar_end_idx = -1
            in_avatar = False
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped == '[avatar]':
                    in_avatar = True
                    continue
                if in_avatar and stripped.startswith('['):
                    avatar_end_idx = i
                    break
            
            # 如果找不到结束位置，则在文件末尾添加
            if avatar_end_idx == -1:
                avatar_end_idx = len(lines)
            
            # 插入新条目到 [avatar] 部分末尾
            # 在 [avatar] 标签后找到最后一个条目行
            last_entry_idx = -1
            in_avatar = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped == '[avatar]':
                    in_avatar = True
                    continue
                if in_avatar and stripped.startswith('['):
                    break
                if in_avatar and stripped and stripped[0].isdigit():
                    last_entry_idx = i
            
            # 在最后一个条目后插入新条目
            if last_entry_idx >= 0:
                lines.insert(last_entry_idx + 1, new_avatar_lines)
            else:
                # 如果没找到条目，在 [avatar] 标签后添加
                for i, line in enumerate(lines):
                    if line.strip() == '[avatar]':
                        lines.insert(i + 1, new_avatar_lines)
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
                logger.warning(f"newcashshop.etc 更新失败: {failed}")
                return False
            else:
                logger.info(f"newcashshop.etc 更新成功，新增 {len(shop_entries)} 条 [avatar] 条目")
                return True
                
        except Exception as e:
            logger.error(f"更新 newcashshop.etc 失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
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
    
    def import_equ_files_to_pvf(self, update_lst: bool = True) -> Tuple[int, List[str]]:
        """
        将生成的 equ 文件导入到 PVF，并更新 equipment.lst
        
        Args:
            update_lst: 是否更新 PVF 的 equipment.lst
            
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
            # 步骤1: 上传 equ 文件
            failed = self._pvf_api.import_files(file_info_list)
            success_count = len(file_info_list) - len(failed)
            logger.info(f"上传 equ 文件完成: 成功 {success_count}, 失败 {len(failed)}")
            
            if failed:
                logger.warning(f"以下 equ 文件上传失败: {failed}")
            
            # 步骤2: 更新 PVF 的 equipment.lst
            if update_lst and success_count > 0:
                self._update_equipment_lst_in_pvf()
            
            return success_count, failed
        except Exception as e:
            logger.error(f"导入 PVF 失败: {e}")
            return 0, [f["FilePath"] for f in file_info_list]
    
    def _update_equipment_lst_in_pvf(self) -> bool:
        """
        更新 PVF 中的 equipment/equipment.lst，添加新生成的条目
        
        Returns:
            成功返回 True
        """
        if self._pvf_api is None:
            logger.error("PVF API 未初始化，无法更新 equipment.lst")
            return False
        
        try:
            # 读取当前 PVF 中的 equipment.lst
            current_lst = self._pvf_api.get_file_content('equipment/equipment.lst')
            
            # 构建新条目（equipment.lst 中的路径不带 equipment/ 前缀）
            new_entries_lines = []
            for equ_code, equ_path in sorted(self._equ_codes.items(), key=lambda x: x[0]):
                # 去掉 ` 字符和 equipment/ 前缀
                clean_path = equ_path.strip('`')
                if clean_path.startswith('equipment/'):
                    clean_path = clean_path[10:]  # 去掉 "equipment/"
                    
                new_entries_lines.append(f"{equ_code}\t`{clean_path}`")
            new_entries = '\r\n'.join(new_entries_lines) + '\n'
            
            # 合并：在现有内容后添加新条目
            if current_lst:
                merged_content = current_lst.rstrip() + '\r\n' + new_entries
            else:
                merged_content = new_entries
            
            # 上传合并后的 equipment.lst
            lst_file_info = [{
                "FilePath": "equipment/equipment.lst",
                "FileContent": merged_content
            }]
            
            failed = self._pvf_api.import_files(lst_file_info)
            
            if failed:
                logger.warning(f"equipment.lst 更新失败: {failed}")
                return False
            else:
                logger.info("equipment.lst 更新成功")
                return True
                
        except Exception as e:
            logger.error(f"更新 equipment.lst 失败: {e}")
            return False
    
    def generate(
        self,
        json_path: Path,
        output_path: Path,
        write_equ_to_local: bool = None,
        import_to_pvf: bool = None
    ) -> Dict[str, any]:
        """
        主生成流程
        
        Args:
            json_path: 输入 JSON 文件路径
            output_path: 输出 lst 文件路径
            write_equ_to_local: 是否将 equ 文件写入本地目录（默认从 config 读取）
            import_to_pvf: 是否将 equ 文件导入到 PVF（默认从 config 读取）
            
        Returns:
            统计信息字典
        """
        # 从 config 获取默认值
        if write_equ_to_local is None:
            write_equ_to_local = EQU_GENERATION_CONFIG.get("write_equ_to_local", False)
        if import_to_pvf is None:
            import_to_pvf = EQU_GENERATION_CONFIG.get("import_to_pvf", True)
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
        
        # 5. 写入 shop.etc（同时获取条目用于更新 PVF）
        shop_path = Path(output_path).parent / "shop.etc"
        shop_entries = self.write_shop_etc(shop_path)
        
        # 6. 导入到 PVF
        imported_count = 0
        shop_updated = False
        if import_to_pvf and self._generate_equ_files:
            imported_count, _ = self.import_equ_files_to_pvf()
            
            # 更新 newcashshop.etc 的 [avatar] 部分
            if shop_entries:
                shop_updated = self._update_newcashshop_etc_in_pvf(shop_entries)
        
        # 7. 返回统计
        stats = {
            "total_codes": len(self._equ_codes),
            "error_count": self._error_count,
            "output_file": str(output_path),
            "existing_codes": len(self._existing_codes),
            "equ_files_generated": len(self._equ_contents),
            "equ_files_written": equ_count,
            "equ_files_imported": imported_count,
            "shop_entries_count": len(shop_entries) if shop_entries else 0,
            "shop_updated_in_pvf": shop_updated,
            "max_per_job_part": self._max_equ_per_job_part,
        }
        
        logger.info(f"生成完成！新装备编码数: {stats['total_codes']}, PVF已有: {stats['existing_codes']}, 错误数: {stats['error_count']}")
        if self._generate_equ_files:
            logger.info(f"Equ文件: 生成 {stats['equ_files_generated']}, 本地写入 {stats['equ_files_written']}, PVF导入 {stats['equ_files_imported']}")
        if shop_entries:
            logger.info(f"Shop条目: 生成 {stats['shop_entries_count']}, PVF更新: {'成功' if shop_updated else '失败'}")
        
        return stats


def main():
    """主入口"""
    import argparse
    
    # 从 config 获取默认配置
    default_write_local = EQU_GENERATION_CONFIG.get("write_equ_to_local", False)
    default_upload_pvf = EQU_GENERATION_CONFIG.get("import_to_pvf", True)
    
    parser = argparse.ArgumentParser(
        description='装备编码生成器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
当前配置 (config.py):
  - 写入本地: {default_write_local}
  - 上传到 PVF: {default_upload_pvf}

使用说明:
  --local     强制保存 equ 文件到本地
  --no-local  不保存到本地
  --upload    上传到 PVF
  --no-upload 不上传到 PVF

示例:
  python generate_equ.py                    # 使用 config 配置
  python generate_equ.py --local            # 强制保存到本地
  python generate_equ.py --upload           # 强制上传到 PVF
  python generate_equ.py --local --upload   # 同时保存本地和上传
        """
    )
    parser.add_argument('--local', action='store_true', 
                        help='强制保存 equ 文件到本地')
    parser.add_argument('--no-local', action='store_true',
                        help='不保存到本地')
    parser.add_argument('--upload', action='store_true',
                        help='上传到 PVF')
    parser.add_argument('--no-upload', action='store_true',
                        help='不上传到 PVF')
    
    args = parser.parse_args()
    
    generator = EquipmentCodeGenerator()
    
    # 根据命令行参数覆盖 config 配置
    write_local = default_write_local
    if args.local:
        write_local = True
    elif args.no_local:
        write_local = False
    
    upload_pvf = default_upload_pvf
    if args.upload:
        upload_pvf = True
    elif args.no_upload:
        upload_pvf = False
    
    try:
        print("=" * 70)
        print("装备编码生成器")
        print("=" * 70)
        print(f"\n当前配置:")
        print(f"  - 写入本地: {write_local} (config默认: {default_write_local})")
        print(f"  - 上传到 PVF: {upload_pvf} (config默认: {default_upload_pvf})")
        print(f"\n提示: 修改 config.py 中的 EQU_GENERATION_CONFIG 可更改默认行为")
        
        stats = generator.generate(
            json_path=AVATAR_DATA_JSON,
            output_path=EQUIPMENT_LST,
            write_equ_to_local=write_local,
            import_to_pvf=upload_pvf
        )
        
        print(f"\n" + "=" * 70)
        print("生成统计:")
        print("=" * 70)
        print(f"  - 新装备编码数: {stats['total_codes']}")
        print(f"  - PVF已有装备数: {stats['existing_codes']}")
        print(f"  - 错误数: {stats['error_count']}")
        print(f"  - 输出文件: {stats['output_file']}")
        if 'equ_files_generated' in stats:
            print(f"  - Equ文件生成数: {stats['equ_files_generated']}")
            print(f"  - Equ文件本地写入数: {stats['equ_files_written']}")
            print(f"  - Equ文件PVF导入数: {stats['equ_files_imported']}")
        if 'shop_entries_count' in stats:
            print(f"  - Shop条目生成数: {stats['shop_entries_count']}")
        
        if upload_pvf:
            print(f"\n✓ 文件已成功上传到 PVF:")
            print(f"  - equipment/character/{{job}}avatar/{{part}}/ 目录")
            if stats.get('shop_updated_in_pvf'):
                print(f"  - etc/newcashshop.etc [avatar] 标签已更新")
        
    except Exception as e:
        logger.error(f"生成失败: {e}")
        raise

if __name__ == "__main__":
    main()
