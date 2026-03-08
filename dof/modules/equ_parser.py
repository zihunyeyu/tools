"""
Equ File Parser - Equ 文件解析器

支持解析所有类型的 PVF equ 装备文件：
- avatar: 时装/装扮
- weapon: 武器
- armor/common: 防具
- accessory: 饰品
- creature: 宠物装备
- 其他特殊装备
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any, Union


@dataclass
class IconInfo:
    """图标信息"""
    path: str = ""
    index: int = 0


@dataclass
class VariationInfo:
    """变体信息"""
    code: int = 0
    index: int = 0


@dataclass
class LayerVariation:
    """图层变体信息"""
    layer_index: int = 0
    layer_name: str = ""
    ani_script: str = ""  # 关联的动画脚本


@dataclass
class AnimationJob:
    """动画职业配置（完整）"""
    job: str = ""
    variation: VariationInfo = field(default_factory=VariationInfo)
    layer_variations: List[LayerVariation] = field(default_factory=list)


@dataclass
class EquData:
    """
    Equ 文件数据结构 - 支持所有装备类型
    
    通用字段 + 各类型特有字段
    """
    # ========== 基础信息 ==========
    name: str = ""
    name2: str = ""
    flavor_text: str = ""  # 描述文本
    grade: int = 0
    rarity: int = 0  # 稀有度
    
    # ========== 限制条件 ==========
    usable_jobs: List[str] = field(default_factory=list)
    minimum_level: int = 0
    
    # ========== 交易/绑定 ==========
    attach_type: str = ""  # [trade], [free], [sealing], etc.
    
    # ========== 图标 ==========
    icon: IconInfo = field(default_factory=IconInfo)
    field_image: str = ""  # 地面图像
    icon_mark: str = ""  # 图标标记
    
    # ========== 装备类型 ==========
    equipment_type: str = ""  # coat, pants, weapon, creature, etc.
    equipment_subtype: int = 0
    sub_type: str = ""  # 子类型
    
    # ========== 经济属性 ==========
    price: int = 0
    repair_price: int = 0
    value: int = 0
    
    # ========== 属性加成 ==========
    # 攻击
    physical_attack: int = 0
    magical_attack: int = 0
    attack_speed: int = 0
    cast_speed: int = 0
    separate_attack: int = 0  # 独立攻击
    
    # 防御
    physical_defense: int = 0
    magical_defense: int = 0
    
    # 其他属性
    hp_max: int = 0
    mp_max: int = 0
    mp_max_rate: int = 0  # MP MAX rate
    strength: int = 0
    intelligence: int = 0
    vitality: int = 0
    spirit: int = 0
    
    # 抗性
    all_elemental_resistance: int = 0
    
    # ========== 时装特有 ==========
    enable_dye: bool = False
    dye_type: int = 0
    part_set_index: int = 0
    avatar_type_select: List[List[str]] = field(default_factory=list)
    avatar_select_ability: List[List[str]] = field(default_factory=list)
    
    # ========== 动画/变体 ==========
    animation_jobs: List[AnimationJob] = field(default_factory=list)
    
    # ========== 物理属性 ==========
    move_wav: str = ""  # 移动音效
    weight: int = 0
    durability: int = 0
    cool_time: int = 0  # 冷却时间
    
    # ========== 武器特有 ==========
    equipment_physical_attack: str = ""  # 可能有两段值
    equipment_magical_attack: str = ""  # 可能有两段值
    
    # ========== 宠物装备特有 ==========
    creature_species: str = ""  # 宠物种类
    output_index: int = 0  # 输出索引
    set_item_master: str = ""  # 套装主件
    
    # ========== 其他标记 ==========
    possible_kiri_protect: bool = False
    creation_rate: int = 0  # 制作成功率
    
    # ========== 原始数据 ==========
    raw_sections: Dict[str, List[str]] = field(default_factory=dict)
    equ_type: str = ""  # avatar, weapon, armor, accessory, creature, other


class EquParser:
    """
    Equ 文件解析器 - 支持所有装备类型
    """
    
    @classmethod
    def parse(cls, content: str) -> EquData:
        """解析 equ 文件内容"""
        data = EquData()
        sections = cls._split_sections(content)
        data.raw_sections = sections
        
        # 解析所有 sections
        for section_name, lines in sections.items():
            cls._parse_section(data, section_name, lines)
        
        # 检测装备类型
        data.equ_type = cls._detect_equ_type(data)
        
        return data
    
    @staticmethod
    def _split_sections(content: str) -> Dict[str, List[str]]:
        """将内容分割为 sections"""
        sections: Dict[str, List[str]] = {}
        lines = content.split('\r\n')
        current_section = None
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            # section 开始
            if stripped.startswith('[') and not stripped.startswith('[/') and ']' in stripped:
                current_section = stripped[1:].split(']')[0]
                if current_section not in sections:
                    sections[current_section] = []
            # section 结束
            elif stripped.startswith('[/') and ']' in stripped:
                current_section = None
            # 数据行
            elif current_section is not None:
                sections[current_section].append(stripped)
        
        return sections
    
    @classmethod
    def _parse_section(cls, data: EquData, name: str, lines: List[str]):
        """根据 section 名称解析数据"""
        if not lines:
            return
        
        first_line = lines[0]
        
        # 基础信息
        if name == 'name':
            data.name = first_line.strip('`')
        elif name == 'name2':
            data.name2 = first_line.strip('`')
        elif name == 'flavor text':
            data.flavor_text = first_line.strip('`')
        elif name == 'grade':
            data.grade = cls._parse_int(first_line)
        elif name == 'rarity':
            data.rarity = cls._parse_int(first_line)
        
        # 限制条件
        elif name == 'usable job':
            data.usable_jobs = [line.strip('`') for line in lines]
        elif name == 'minimum level':
            data.minimum_level = cls._parse_int(first_line)
        
        # 交易
        elif name == 'attach type':
            data.attach_type = first_line.strip('`')
        
        # 图标
        elif name == 'icon':
            parts = first_line.split('\t')
            if len(parts) >= 2:
                data.icon.path = parts[0].strip('`')
                data.icon.index = cls._parse_int(parts[1])
            elif len(parts) == 1:
                data.icon.path = parts[0].strip('`')
        elif name == 'field image':
            data.field_image = first_line.strip('`')
        elif name == 'icon mark':
            data.icon_mark = first_line.strip('`')
        
        # 装备类型
        elif name == 'equipment type':
            parts = first_line.split('\t')
            data.equipment_type = parts[0].strip('`').strip('[]').replace(' avatar', '')
            if len(parts) >= 2:
                data.equipment_subtype = cls._parse_int(parts[1])
        elif name == 'sub type':
            data.sub_type = first_line.strip('`')
        
        # 经济
        elif name == 'price':
            data.price = cls._parse_int(first_line)
        elif name == 'repair price':
            data.repair_price = cls._parse_int(first_line)
        elif name == 'value':
            data.value = cls._parse_int(first_line)
        
        # 攻击属性
        elif name == 'physical attack':
            data.physical_attack = cls._parse_int(first_line)
        elif name == 'magical attack':
            data.magical_attack = cls._parse_int(first_line)
        elif name == 'attack speed':
            data.attack_speed = cls._parse_int(first_line)
        elif name == 'cast speed':
            data.cast_speed = cls._parse_int(first_line)
        elif name == 'separate attack':
            data.separate_attack = cls._parse_int(first_line)
        elif name == 'equipment physical attack':
            data.equipment_physical_attack = first_line
        elif name == 'equipment magical attack':
            data.equipment_magical_attack = first_line
        
        # 防御属性
        elif name == 'physical defense':
            data.physical_defense = cls._parse_int(first_line)
        elif name == 'magical defense':
            data.magical_defense = cls._parse_int(first_line)
        elif name == 'equipment physical defense':
            parts = first_line.split('\t')
            data.physical_defense = cls._parse_int(parts[0]) if parts else 0
        elif name == 'equipment magical defense':
            parts = first_line.split('\t')
            data.magical_defense = cls._parse_int(parts[0]) if parts else 0
        
        # 其他属性
        elif name == 'HP MAX':
            data.hp_max = cls._parse_int(first_line)
        elif name == 'MP MAX':
            data.mp_max = cls._parse_int(first_line)
        elif name == 'MP MAX rate':
            data.mp_max_rate = cls._parse_int(first_line)
        elif name == 'strength':
            data.strength = cls._parse_int(first_line)
        elif name == 'intelligence':
            data.intelligence = cls._parse_int(first_line)
        elif name == 'vitality':
            data.vitality = cls._parse_int(first_line)
        elif name == 'spirit':
            data.spirit = cls._parse_int(first_line)
        elif name == 'all elemental resistance':
            data.all_elemental_resistance = cls._parse_int(first_line)
        
        # 时装特有
        elif name == 'enable dye':
            parts = first_line.split('\t')
            if len(parts) >= 2:
                data.enable_dye = parts[0] == '1'
                data.dye_type = cls._parse_int(parts[1])
        elif name == 'part set index':
            data.part_set_index = cls._parse_int(first_line)
        elif name == 'avatar type select':
            data.avatar_type_select = [line.split('\t') for line in lines]
        elif name == 'avatar select ability':
            data.avatar_select_ability = [line.split('\t') for line in lines]
        
        # 动画/变体 - 需要整体处理
        elif name == 'animation job':
            # 标记需要后续处理
            pass
        
        # 物理属性
        elif name == 'move wav':
            data.move_wav = first_line.strip('`')
        elif name == 'weight':
            data.weight = cls._parse_int(first_line)
        elif name == 'durability':
            data.durability = cls._parse_int(first_line)
        elif name == 'cool time':
            data.cool_time = cls._parse_int(first_line)
        
        # 宠物特有
        elif name == 'creature species':
            data.creature_species = first_line.strip('`')
        elif name == 'output index':
            data.output_index = cls._parse_int(first_line)
        elif name == 'set item master':
            data.set_item_master = first_line.strip('`')
        
        # 其他
        elif name == 'possible kiri protect':
            data.possible_kiri_protect = True
        elif name == 'creation rate':
            data.creation_rate = cls._parse_int(first_line)
    
    @classmethod
    def _parse_animation_jobs(cls, data: EquData, sections: Dict[str, List[str]]):
        """解析动画职业配置"""
        # 收集有序的 section
        items = []
        for name, lines in sections.items():
            for line in lines:
                items.append((name, line))
        
        jobs = []
        current_job = None
        current_variation = VariationInfo()
        current_layers = []
        
        i = 0
        while i < len(items):
            section_name, line = items[i]
            
            if section_name == 'animation job':
                # 保存上一个
                if current_job:
                    jobs.append(AnimationJob(
                        job=current_job,
                        variation=current_variation,
                        layer_variations=current_layers
                    ))
                current_job = line.strip('`')
                current_variation = VariationInfo()
                current_layers = []
                
            elif section_name == 'variation':
                parts = line.split('\t')
                if len(parts) >= 1:
                    current_variation.code = cls._parse_int(parts[0])
                if len(parts) >= 2:
                    current_variation.index = cls._parse_int(parts[1])
                    
            elif section_name == 'layer variation':
                # 可能跨多行
                layer_idx = 0
                layer_name = ""
                
                # 当前行是 layer_index
                try:
                    layer_idx = int(line)
                    # 下一行是 layer_name
                    if i + 1 < len(items) and items[i + 1][0] == 'layer variation':
                        layer_name = items[i + 1][1].strip('`')
                        i += 1
                except ValueError:
                    layer_name = line.strip('`')
                
                # 查找对应的 ani script
                ani_script = ""
                if i + 1 < len(items) and items[i + 1][0] == 'equipment ani script':
                    ani_script = items[i + 1][1].strip('`')
                
                current_layers.append(LayerVariation(
                    layer_index=layer_idx,
                    layer_name=layer_name,
                    ani_script=ani_script
                ))
            
            i += 1
        
        # 最后一个
        if current_job:
            jobs.append(AnimationJob(
                job=current_job,
                variation=current_variation,
                layer_variations=current_layers
            ))
        
        data.animation_jobs = jobs
    
    @classmethod
    def parse_full(cls, content: str) -> EquData:
        """完整解析，包括动画职业"""
        data = cls.parse(content)
        sections = cls._split_sections(content)
        cls._parse_animation_jobs(data, sections)
        return data
    
    @staticmethod
    def _detect_equ_type(data: EquData) -> str:
        """检测装备类型"""
        eq_type = data.equipment_type.lower()
        
        if eq_type in ['coat', 'pants', 'belt', 'shoes', 'cap', 'hair', 'face', 'neck', 'skin']:
            if data.avatar_type_select:
                return 'avatar'
            else:
                return 'armor'
        elif 'weapon' in eq_type or eq_type in ['knuckle', 'sword', 'gun', 'rod', 'axe', 'spear']:
            return 'weapon'
        elif eq_type in ['ring', 'necklace', 'wrist', 'support', 'amulet', 'magic stone', 'earring']:
            return 'accessory'
        elif eq_type == 'creature':
            return 'creature'
        else:
            return 'other'
    
    @staticmethod
    def _parse_int(value: str) -> int:
        """安全解析整数"""
        try:
            return int(value.strip())
        except (ValueError, AttributeError):
            return 0


# ===== 便捷函数 =====

def parse_equ(content: str) -> EquData:
    """解析 equ 内容（基础）"""
    return EquParser.parse(content)


def parse_equ_full(content: str) -> EquData:
    """完整解析 equ 内容"""
    return EquParser.parse_full(content)


if __name__ == "__main__":
    # 测试
    from pvf_api_client import PvfUtilityApi
    from config import PVF_API_HOST, PVF_API_PORT
    
    api = PvfUtilityApi(PVF_API_HOST, PVF_API_PORT)
    
    # 测试不同类型的装备
    test_files = [
        ("avatar", "equipment/character/mage/avatar/coat/106500440.equ"),
        ("weapon", "equipment/character/fighter/weapon/knuckle/glove_default.equ"),
        ("common", "equipment/character/common/jacket/cloth/vest_owool.equ"),
        ("creature", "equipment/creature/faras.equ"),
    ]
    
    for eq_type, path in test_files:
        print(f"\n{'='*60}")
        print(f"测试: {eq_type} - {path}")
        print('='*60)
        
        try:
            content = api.get_file_content(path)
            data = EquParser.parse_full(content)
            
            print(f"名称: {data.name}")
            print(f"装备类型: {data.equipment_type}")
            print(f"检测类型: {data.equ_type}")
            print(f"图标: {data.icon.path}")
            print(f"可用职业: {data.usable_jobs}")
            print(f"动画职业: {[j.job for j in data.animation_jobs]}")
            
        except Exception as e:
            print(f"失败: {e}")
