"""
Equipment Code Generator - 装备编码生成器（适配新配置格式）

从 avatar_config.json 生成装备编码清单 (.lst 文件) 和 equ 文件。

新配置格式：
{
  "swordman_male": {
    "items": {
      "cap": {
        "10203": {
          "name": "白色末日使者肩饰",
          "frame": 328,
          "layers": ["c", "x"],
          "hide_parts": []
        }
      }
    }
  }
}

编码解析：
- "10203" -> variation_code=102, suffix=3
- "0" -> variation_code=0, suffix=0
- "1001" -> variation_code=10, suffix=1
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
    JOB_MAP, PART_CODE_MAP, LAYER_DICT,
    EQU_PATH_TEMPLATE, EQUIPMENT_LST, SHOP_ETC,
    PVF_API_HOST, PVF_API_PORT, BASE_DIR,
    EQU_GENERATION_CONFIG
)
from modules.equ_template_cache import EquTemplateCache, init_template_cache

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 职业键映射：新格式完整名 -> 原格式缩写
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


def parse_full_code(full_code_str: str) -> Tuple[int, int]:
    """
    解析完整编码为 variation_code 和 suffix
    
    Args:
        full_code_str: 完整编码字符串，如 "10203", "0", "1001"
    
    Returns:
        (variation_code, suffix)
        
    解析规则：
    - "10203" -> variation=102, suffix=3
    - "0" -> variation=0, suffix=0
    - "1001" -> variation=10, suffix=1
    - "4000" -> variation=40, suffix=0
    
    规则：后两位是 suffix，前面是 variation
          如果只有1位，variation=该数字, suffix=0
    """
    # 去除前导零，但保留至少一位
    full_code_str = full_code_str.lstrip('0')
    if not full_code_str:
        full_code_str = '0'
    
    if len(full_code_str) == 1:
        # 只有1位：variation=该数字, suffix=0
        return int(full_code_str), 0
    else:
        # 2位及以上：后两位是 suffix，前面是 variation
        suffix = int(full_code_str[-2:])
        variation = int(full_code_str[:-2]) if len(full_code_str) > 2 else 0
        return variation, suffix


class EquFileGenerator:
    """Equ 文件生成器"""
    
    PART_EQU_TYPE_MAP = {
        'coat': '[coat avatar]',
        'pants': '[pants avatar]',
        'belt': '[waist avatar]',
        'neck': '[breast avatar]',
        'shoes': '[shoes avatar]',
        'cap': '[hat avatar]',
        'hair': '[hair avatar]',
        'face': '[face avatar]',
        'skin': '[skin avatar]',
    }
    
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
    
    JOB_ICON_MAP_DETAILED = {
        'sm': ('swordman', 'sm'),
        'ft': ('fighter', 'ft'),
        'fm': ('atfighter', 'fm'),
        'gn': ('gunner', 'gn'),
        'gg': ('atgunner', 'gg'),
        'mg': ('mage', 'mg'),
        'mm': ('atmage', 'mm'),
        'pr': ('priest', 'pr'),
        'th': ('thief', 'tf'),
    }
    
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
    
    # 隐藏部位映射：部位 -> equ 装备类型
    HIDE_PART_MAP = {
        'cap': '[hat avatar]',
        'hair': '[hair avatar]',
        'face': '[face avatar]',
        'neck': '[breast avatar]',
        'coat': '[coat avatar]',
        'pants': '[pants avatar]',
        'belt': '[waist avatar]',
        'shoes': '[shoes avatar]',
        'skin': '[skin avatar]',
    }
    
    def __init__(self, pvf_api: Optional[PvfUtilityApi] = None, use_cache: bool = True):
        self._pvf_api = pvf_api
        self._templates: Dict[str, str] = {}
        self._layer_dict = LAYER_DICT
        self._template_cache: Optional[EquTemplateCache] = None
        
        if use_cache:
            try:
                self._template_cache = init_template_cache()
                logger.info("EquFileGenerator: 已启用模板缓存")
            except Exception as e:
                logger.warning(f"EquFileGenerator: 初始化模板缓存失败: {e}")
    
    def _get_template_key(self, job_name: str, part_name: str) -> str:
        return f"{job_name}_{part_name}"
    
    def _fetch_template_from_pvf(self, job_name: str, part_name: str) -> Optional[str]:
        if self._pvf_api is None:
            return None
        
        try:
            job_code, job_path, _ = JOB_MAP[job_name]
            search_path = f"equipment/character/{job_path}avatar/{part_name}"
            
            lst_info = self._pvf_api.get_lst_file_info('equipment/equipment.lst')
            
            for code_str, info in lst_info.items():
                if not isinstance(info, dict):
                    continue
                full_path = info.get('FullPath', '')
                if search_path in full_path and full_path.endswith('.equ'):
                    try:
                        content = self._pvf_api.get_file_content(full_path)
                        return content
                    except Exception:
                        continue
            
            return None
        except Exception as e:
            logger.warning(f"从PVF获取模板失败: {e}")
            return None
    
    def _build_template(self, job_name: str, part_name: str) -> str:
        equ_type = self.PART_EQU_TYPE_MAP.get(part_name, '[coat avatar]')
        usable_jobs = self.JOB_USABLE_MAP.get(job_name, [f'[{job_name}]'])
        anim_job = self.JOB_ANIMATION_MAP.get(job_name, f'[{job_name}]')
        lay_file = self.PART_LAY_MAP.get(job_name, f'equipment/character/{job_name}.lay')
        
        usable_jobs_str = '\n'.join([f'\t`{j}`' for j in usable_jobs])
        icon_path = self._get_icon_path(job_name, part_name)
        
        # 使用 % 占位符避免 f-string 和 {{}} 冲突
        template = """#PVF_File

[name]
\t`%(name)s`

[name2]
\t``

[enable dye]
\t1\t0

[grade]
\t2

[part set index]
\t2

[usable job]
%(usable_jobs)s
[/usable job]

[attach type]
\t`[trade]`

[minimum level]
\t1

[icon]
\t`%(icon_path)s`\t%(icon_index)s

[equipment type]
\t`%(equ_type)s`\t0

[avatar type select]
\t7\t0\t0\t600\t0
\t30\t0\t0\t1200\t0
\t0\t0\t0\t2400\t0
\t0\t0\t0\t2600\t2
\t`[C socket]`\t`[C socket]`
[/avatar type select]

[avatar select ability]
\t`[SKILL_LEVEL]`\t`%(anim_job)s`\t1\t1
[/avatar select ability]

[animation job]
\t`%(anim_job_full)s`

%(hide_equipment)s

%(hide_layer)s

[variation]
\t%(variation_code)s\t%(suffix)s

%(layer_variations)s

[move wav]
\t`CLOTH_TOUCH`
"""
        # 存储模板和参数，稍后填充
        self._template_params = {
            'usable_jobs': usable_jobs_str,
            'icon_path': icon_path,
            'equ_type': equ_type,
            'anim_job': anim_job.strip("[]"),
            'anim_job_full': anim_job,
        }
        return template
    
    def _get_icon_path(self, job_name: str, part_name: str) -> str:
        base_path = self.JOB_ICON_MAP.get(job_name, f'item/avatar/{job_name}')
        icon_file = self.PART_ICON_FILE_MAP.get(part_name, 'acoat')
        
        job_prefix_map = {
            'sm': 'sm', 'ft': 'ft', 'fm': 'ft',
            'gn': 'gn', 'gg': 'gn', 'mg': 'mg',
            'mm': 'mg', 'pr': 'pr', 'th': 'tf'
        }
        job_prefix = job_prefix_map.get(job_name, job_name)
        
        return f"{base_path}/{job_prefix}_{icon_file}.img"
    
    def _replace_name_tag(self, content: str, name: str) -> str:
        pattern = r'(\[name\]\s*\n\s*`)([^`]+)(`)'
        return re.sub(pattern, rf'\g<1>{name}\g<3>', content, count=1)
    
    def _replace_or_add_flavor_text_tag(self, content: str, flavor_text: str) -> str:
        if not flavor_text:
            pattern = r'\n?\[flavor text\]\s*\r?\n\s*`[^`]*`\s*\r?\n'
            return re.sub(pattern, '\n', content, count=1)
        
        flavor_section = f"\n[flavor text]\n\t`{flavor_text}`\n"
        
        if '[flavor text]' in content:
            pattern = r'(\[flavor text\]\s*\r?\n\s*`)([^`]*)(`)'
            return re.sub(pattern, rf'\g<1>{flavor_text}\g<3>', content, count=1)
        else:
            pattern = r'(\[name\]\s*\r?\n\s*`[^`]*`\s*\r?\n)'
            return re.sub(pattern, rf'\g<1>{flavor_section}', content, count=1)
    
    def _replace_icon_tag(self, content: str, icon_path: str, icon_index: int) -> str:
        """替换 [icon] 标签内容"""
        pattern = r'(\[icon\]\s*\r?\n\s*`)([^`]+)(`\s+)(\d+)'
        
        def replace_icon(match):
            prefix = match.group(1)
            middle = match.group(3)
            return f'{prefix}{icon_path}{middle}{icon_index}'
        
        return re.sub(pattern, replace_icon, content, count=1)
    
    def _get_layer_index(self, part_name: str, layer: str) -> int:
        key = f"{part_name}_{layer}"
        return self._layer_dict.get(key, 1000)
    
    def _generate_icon_path(self, job_name: str, part_name: str) -> str:
        job_path, job_prefix = self.JOB_ICON_MAP_DETAILED.get(job_name, (job_name, job_name))
        part_icon = self.PART_ICON_ABBREV.get(part_name, f'a{part_name}')
        return f"item/avatar/{job_path}/{job_prefix}_{part_icon}.img"
    
    def _build_layer_variations(self, job_name: str, part_name: str, layers: List[str]) -> str:
        lay_path = self.PART_LAY_MAP.get(job_name, f'equipment/character/{job_name}.lay')
        
        variations = []
        for layer in layers:
            order = self._get_layer_index(part_name, layer)
            variations.append(f"[layer variation]\n\t{order}\n\t`{part_name}_{layer}`")
            variations.append(f"[equipment ani script]\n\t`{lay_path}`")
        
        return '\n\n'.join(variations)
    
    def _build_hide_equipment(self, hide_parts: List[str]) -> str:
        """
        构建 [hide equipment] 字段
        
        Args:
            hide_parts: 隐藏部位列表，如 ["cap", "hair"]
        
        Returns:
            格式化后的字符串，如果没有则返回空字符串
        """
        if not hide_parts:
            return ""
        
        lines = ["[hide equipment]"]
        
        for part in hide_parts:
            equ_type = self.HIDE_PART_MAP.get(part)
            if equ_type:
                lines.append(f"\t`{equ_type}`")
        
        lines.append("[/hide equipment]")
        
        return "\n".join(lines)
    
    def _get_hide_layer_indices(self, hide_parts: List[str]) -> List[int]:
        """
        根据隐藏部位获取所有相关的 layer index
        
        Args:
            hide_parts: 隐藏部位列表
        
        Returns:
            layer index 列表，按降序排列
        """
        indices = set()
        
        for part in hide_parts:
            # 在 LAYER_DICT 中查找该部位的所有 layer
            for key, value in self._layer_dict.items():
                if key.startswith(f"{part}_"):
                    indices.add(value)
        
        # 转换为列表并按降序排列
        return sorted(list(indices), reverse=True)
    
    def _build_hide_layer(self, hide_parts: List[str]) -> str:
        """
        构建 [hide layer] 字段
        
        Args:
            hide_parts: 隐藏部位列表
        
        Returns:
            格式化后的字符串，如果没有则返回空字符串
        """
        if not hide_parts:
            return ""
        
        indices = self._get_hide_layer_indices(hide_parts)
        if not indices:
            return ""
        
        # 格式: [hide layer]\n\tindex1\tindex2\t...\n[/hide layer]
        indices_str = "\t".join(str(idx) for idx in indices)
        return f"[hide layer]\n\t{indices_str}\n[/hide layer]"
    
    def get_template(self, job_name: str, part_name: str) -> str:
        key = self._get_template_key(job_name, part_name)
        
        if key not in self._templates:
            template = None
            
            if self._template_cache:
                cache_template = self._template_cache.get_template(job_name, part_name)
                if cache_template:
                    template = cache_template.content
            
            if template is None and self._pvf_api:
                template = self._fetch_template_from_pvf(job_name, part_name)
            
            if template is None:
                template = self._build_template(job_name, part_name)
            
            self._templates[key] = template
        
        return self._templates[key]
    
    def generate_equ_content(
        self,
        job_name: str,
        part_name: str,
        variation_code: int,
        suffix: int,
        item_config: Dict
    ) -> str:
        """
        生成 equ 文件内容（新格式）
        
        Args:
            job_name: 职业名称（缩写如 sm）
            part_name: 部位名称
            variation_code: 变体代码（如 102）
            suffix: 后缀（如 3）
            item_config: 包含 name, frame, layers, hide_parts 的字典
        """
        template = self.get_template(job_name, part_name)
        
        # 获取配置
        layers = item_config.get('layers', [])
        if not layers:
            layers = ['a']  # 默认图层
        
        name = item_config.get('name', f'{job_name}_{part_name}_{variation_code}{suffix:02d}')
        frame = item_config.get('frame', 0)  # 图标索引
        hide_parts = item_config.get('hide_parts', [])  # 隐藏部位
        
        # 生成图层变体
        layer_variations = self._build_layer_variations(job_name, part_name, layers)
        
        # 生成隐藏部位字段
        hide_equipment = self._build_hide_equipment(hide_parts)
        hide_layer = self._build_hide_layer(hide_parts)
        
        # 生成 icon 路径
        icon_path = self._generate_icon_path(job_name, part_name)
        
        # 获取模板参数
        params = getattr(self, '_template_params', {})
        
        # 填充模板
        content = template % {
            **params,
            'name': name,
            'icon_index': frame,
            'variation_code': variation_code,
            'suffix': suffix,
            'layer_variations': layer_variations,
            'hide_equipment': hide_equipment,
            'hide_layer': hide_layer,
        }
        
        # 如果模板来自PVF，替换[variation]行
        if '{{variation_code}}' not in template:
            content = re.sub(
                r'(\[variation\]\s*\n\s*)\d+(\s+)\d+',
                rf'\g<1>{variation_code}\g<2>{suffix}',
                content
            )
            
            # 替换 layer variations（简化处理）
            anim_job_pattern = r'(\[animation job\]\s*\r?\n\s*`\[([^\]]+)\]`\s*\r?\n+\s*\[variation\]\s*\r?\n\s*\d+\s+\d+)\s*\r?\n+((?:\s*\[layer variation\]\s*\r?\n[^\[]*\[equipment ani script\][^\[]*)+)(?=\s*\[animation job\]|\s*\[move wav\])'
            
            def replace_layers(match):
                prefix = match.group(1)
                anim_job_name = match.group(2)
                
                if 'demonic' in anim_job_name.lower():
                    lay_file = 'equipment/character/dsswordman.lay'
                elif 'at fighter' in anim_job_name.lower():
                    lay_file = 'equipment/character/atfighter.lay'
                elif 'at gunner' in anim_job_name.lower():
                    lay_file = 'equipment/character/atgunner.lay'
                elif 'at mage' in anim_job_name.lower() or 'creator' in anim_job_name.lower():
                    lay_file = 'equipment/character/atmage.lay'
                else:
                    job_lower = anim_job_name.lower().replace(' ', '')
                    lay_file = f'equipment/character/{job_lower}.lay'
                
                new_layers = self._build_layer_variations(job_name, part_name, layers)
                new_layers = new_layers.replace(
                    self.PART_LAY_MAP.get(job_name, f'equipment/character/{job_name}.lay'),
                    lay_file
                )
                return prefix + '\n\n' + new_layers + '\n'
            
            content = re.sub(anim_job_pattern, replace_layers, content, flags=re.DOTALL)
        
        return content


class EquipmentCodeGenerator:
    """装备编码生成器"""
    
    DEFAULT_EXISTING_LST_PATH = "equipment/equipment.lst"
    
    def __init__(
        self,
        validator: Optional[EquipmentTagValidator] = None,
        start_code: int = 133011,
        pvf_api: Optional[PvfUtilityApi] = None,
        existing_lst_path: Optional[str] = None,
        equ_output_dir: Optional[Path] = None,
        generate_equ_files: bool = True,
        max_equ_per_job_part: Optional[int] = None
    ):
        self.validator = validator or EquipmentTagValidator()
        self.start_code = start_code
        self._equ_codes: Dict[str, str] = {}
        self._equ_contents: Dict[str, str] = {}
        self._error_count = 0
        
        self._existing_codes: Set[str] = set()
        self._pvf_api = pvf_api
        self._existing_lst_path = existing_lst_path or self.DEFAULT_EXISTING_LST_PATH
        self._code_counters: Dict[str, int] = {}
        
        self._generate_equ_files = generate_equ_files
        self._equ_output_dir = equ_output_dir or BASE_DIR / "output/generated_equ"
        self._equ_generator: Optional[EquFileGenerator] = None
        self._max_equ_per_job_part = max_equ_per_job_part
        
        if self._generate_equ_files:
            self._equ_generator = EquFileGenerator(pvf_api=self._pvf_api)
        
        self._load_existing_codes()
        self._init_code_counters()
    
    @staticmethod
    def format_equ_code(base_code: int, suffix: int) -> str:
        return f"{base_code:06d}{suffix}"
    
    def _get_base_code(self, job_name: str, part_name: str) -> int:
        job_code = JOB_MAP[job_name][0]
        part_code = PART_CODE_MAP[part_name][0]
        return int(f"60{job_code}5{part_code}0000")
    
    def _init_code_counters(self) -> None:
        max_codes: Dict[str, int] = {}
        
        for code_str in self._existing_codes:
            if len(code_str) >= 9 and code_str.startswith('60'):
                try:
                    job_code = int(code_str[2])
                    part_code = int(code_str[4])
                    
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
        
        for job_name in JOB_MAP:
            for part_name in PART_CODE_MAP:
                counter_key = f"{job_name}_{part_name}"
                base_code = self._get_base_code(job_name, part_name)
                
                if counter_key in max_codes:
                    self._code_counters[counter_key] = max_codes[counter_key] + 1
                else:
                    self._code_counters[counter_key] = base_code
    
    def _get_next_available_code(self, job_name: str, part_name: str) -> str:
        counter_key = f"{job_name}_{part_name}"
        max_attempts = 1000
        
        for _ in range(max_attempts):
            current_code = self._code_counters[counter_key]
            full_code = str(current_code)
            
            if full_code not in self._existing_codes and full_code not in self._equ_codes:
                self._code_counters[counter_key] = current_code + 1
                return full_code
            
            self._code_counters[counter_key] = current_code + 1
        
        raise RuntimeError(f"无法找到可用代码，已尝试 {max_attempts} 次")
    
    def _load_existing_codes(self) -> None:
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
    
    def _check_tsv_exists(self, job_name: str, part_name: str, variation_code: int, suffix: int) -> bool:
        equ_job = JOB_MAP[job_name][2]
        equ_part = PART_CODE_MAP[part_name][1]
        variation = f"{variation_code}\t{suffix}"
        
        return self.validator.verify((equ_job, equ_part, variation))
    
    def _generate_entry(
        self,
        job_name: str,
        part_name: str,
        variation_code: int,
        suffix: int,
        item_config: Dict
    ) -> Optional[Tuple[str, str, Optional[str]]]:
        """
        生成单条装备记录
        
        Args:
            job_name: 职业缩写（如 sm）
            part_name: 部位名称
            variation_code: 变体代码
            suffix: 后缀
            item_config: 包含 name, frame, layers 等
        """
        # 检查 TSV
        if self._check_tsv_exists(job_name, part_name, variation_code, suffix):
            logger.debug(f"TSV 中已存在，跳过: {job_name}/{part_name}/{variation_code}/{suffix}")
            return None
        
        # 获取装备代码
        equ_code = self._get_next_available_code(job_name, part_name)
        
        # 生成路径
        job_code, job_path, _ = JOB_MAP[job_name]
        equ_path = EQU_PATH_TEMPLATE.format(
            job=job_path,
            part=part_name,
            code=equ_code
        )
        
        # 生成 equ 文件内容
        equ_content = None
        if self._generate_equ_files and self._equ_generator:
            try:
                equ_content = self._equ_generator.generate_equ_content(
                    job_name, part_name, variation_code, suffix, item_config
                )
            except Exception as e:
                logger.warning(f"生成 equ 内容失败: {e}")
        
        return equ_code, equ_path, equ_content
    
    def process_avatar_data(self, data: Dict) -> Dict[str, str]:
        """
        处理 avatar 数据生成装备编码（新格式）
        
        Args:
            data: avatar_config.json 解析后的字典
        """
        self._equ_codes.clear()
        self._equ_contents.clear()
        self._error_count = 0
        
        job_part_counts: Dict[str, int] = {}
        
        logger.info(f"开始生成装备编码，已有装备代码数: {len(self._existing_codes)}")
        
        # 遍历新格式数据
        for job_key, job_data in data.items():
            # 转换职业键：swordman_male -> sm
            job_name = JOB_KEY_MAP_REVERSE.get(job_key)
            if not job_name:
                logger.warning(f"未知职业键 {job_key}，跳过")
                continue
            
            if job_name not in JOB_MAP:
                logger.warning(f"职业 {job_name} 不在 JOB_MAP 中，跳过")
                continue
            
            items = job_data.get('items', {})
            
            for part_name, part_items in items.items():
                # 处理 body -> skin 映射
                if part_name == 'body':
                    part_name = 'skin'
                
                if part_name not in PART_CODE_MAP:
                    logger.debug(f"部位 {part_name} 不在 PART_CODE_MAP 中，跳过")
                    continue
                
                counter_key = f"{job_name}_{part_name}"
                
                # 检查限制
                if self._max_equ_per_job_part is not None:
                    current_count = job_part_counts.get(counter_key, 0)
                    if current_count >= self._max_equ_per_job_part:
                        logger.debug(f"{counter_key} 已达到限制，跳过")
                        continue
                
                # 遍历每个单件
                for full_code_str, item_config in part_items.items():
                    # 检查限制
                    if self._max_equ_per_job_part is not None:
                        current_count = job_part_counts.get(counter_key, 0)
                        if current_count >= self._max_equ_per_job_part:
                            logger.info(f"{counter_key} 已达到限制，停止生成")
                            break
                    
                    # 解析编码
                    try:
                        variation_code, suffix = parse_full_code(full_code_str)
                    except ValueError as e:
                        logger.warning(f"解析编码失败 {full_code_str}: {e}")
                        self._error_count += 1
                        continue
                    
                    # 生成条目
                    entry = self._generate_entry(
                        job_name, part_name, variation_code, suffix, item_config
                    )
                    
                    if entry:
                        equ_code, equ_path, equ_content = entry
                        self._equ_codes[equ_code] = equ_path.replace('/body', '/skin')
                        if equ_content:
                            self._equ_contents[equ_code] = equ_content
                        
                        # 增加计数
                        if self._max_equ_per_job_part is not None:
                            job_part_counts[counter_key] = job_part_counts.get(counter_key, 0) + 1
        
        return self._equ_codes
    
    def write_lst_file(self, output_path: Path) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        sorted_items = sorted(self._equ_codes.items(), key=lambda x: x[0])
        
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            for code, path in sorted_items:
                f.write(f"{code}\t{path.replace('equipment/', '')}\n")
        
        logger.info(f"已写入 {len(sorted_items)} 条记录到 {output_path}")
    
    def generate(
        self,
        json_path: Path,
        output_path: Path,
        write_equ_to_local: bool = None,
        import_to_pvf: bool = None
    ) -> Dict[str, any]:
        """
        主生成流程（新格式）
        
        Args:
            json_path: 输入 JSON 文件路径（avatar_config.json）
            output_path: 输出 lst 文件路径
        """
        if write_equ_to_local is None:
            write_equ_to_local = EQU_GENERATION_CONFIG.get("write_equ_to_local", False)
        if import_to_pvf is None:
            import_to_pvf = EQU_GENERATION_CONFIG.get("import_to_pvf", True)
        
        json_path = Path(json_path)
        
        # 读取 JSON
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
        
        # 处理数据
        self.process_avatar_data(data)
        
        # 写入 lst 文件
        self.write_lst_file(output_path)
        
        # 统计
        stats = {
            "total_codes": len(self._equ_codes),
            "error_count": self._error_count,
            "output_file": str(output_path),
            "existing_codes": len(self._existing_codes),
        }
        
        logger.info(f"生成完成！新装备编码数: {stats['total_codes']}, 错误数: {stats['error_count']}")
        
        return stats


def main():
    """主入口"""
    import argparse
    
    default_write_local = EQU_GENERATION_CONFIG.get("write_equ_to_local", False)
    
    parser = argparse.ArgumentParser(description='装备编码生成器（新格式）')
    parser.add_argument('--config', type=Path, default=Path('avatar_config.json'),
                        help='输入配置文件路径')
    parser.add_argument('--output', type=Path, default=Path('output/equ.lst'),
                        help='输出 lst 文件路径')
    
    args = parser.parse_args()
    
    generator = EquipmentCodeGenerator()
    
    try:
        stats = generator.generate(
            json_path=args.config,
            output_path=args.output,
            write_equ_to_local=True
        )
        
        print(f"\n生成统计:")
        print(f"  - 新装备编码数: {stats['total_codes']}")
        print(f"  - 错误数: {stats['error_count']}")
        print(f"  - 输出文件: {stats['output_file']}")
        
    except Exception as e:
        logger.error(f"生成失败: {e}")
        raise


if __name__ == "__main__":
    main()
