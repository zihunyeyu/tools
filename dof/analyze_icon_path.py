"""
分析 icon 路径匹配问题

问题：从 equ 文件读取的 icon 路径可能与当前部位不匹配
例如：
- 部位是 cap（头饰）
- 但 icon 路径是武器路径：item/new_equipment/01_weapon/swordman/sswd/sswd.img
"""

import re
from pathlib import Path


# 标准时装 icon 路径模式
AVATAR_ICON_PATTERNS = {
    'cap': r'item/avatar/[^/]+/.*cap.*\.img',
    'hair': r'item/avatar/[^/]+/.*hair.*\.img',
    'face': r'item/avatar/[^/]+/.*face.*\.img',
    'neck': r'item/avatar/[^/]+/.*neck.*\.img|item/avatar/[^/]+/.*breast.*\.img',
    'coat': r'item/avatar/[^/]+/.*coat.*\.img',
    'pants': r'item/avatar/[^/]+/.*pants.*\.img',
    'belt': r'item/avatar/[^/]+/.*belt.*\.img|item/avatar/[^/]+/.*waist.*\.img',
    'shoes': r'item/avatar/[^/]+/.*shoes.*\.img',
    'skin': r'item/avatar/[^/]+/.*body.*\.img|item/avatar/[^/]+/.*skin.*\.img',
}

# 武器 icon 路径特征（不匹配时装）
WEAPON_ICON_PATTERNS = [
    r'item/new_equipment/\d+_weapon/',
    r'item/equipment/weapon/',
    r'/wp/',
    r'/sswd/',  # swordman sword
    r'/swd/',
    r'/katana/',
    r'/club/',
    r'/lswd/',  # large sword
    r'/bld/',   # blade
    r'/axe/',
    r'/knuckle/',
]


def is_avatar_icon_path(icon_path: str, part: str) -> bool:
    """
    检查 icon 路径是否与部位匹配
    
    Args:
        icon_path: icon 路径，如 "item/avatar/swordman/sm_acap.img"
        part: 部位，如 "cap"
    
    Returns:
        True 如果是有效的时装 icon 路径
    """
    icon_path = icon_path.lower()
    
    # 检查是否是武器路径
    for pattern in WEAPON_ICON_PATTERNS:
        if re.search(pattern, icon_path):
            return False
    
    # 检查是否在 item/avatar/ 目录下
    if 'item/avatar/' not in icon_path:
        return False
    
    # 检查是否与部位匹配
    part_pattern = AVATAR_ICON_PATTERNS.get(part, '')
    if part_pattern and re.search(part_pattern, icon_path):
        return True
    
    # 如果不匹配具体部位，只要在 item/avatar/ 下就算有效
    return 'item/avatar/' in icon_path


def generate_correct_icon_path(job_name: str, part: str) -> str:
    """
    生成正确的时装 icon 路径
    
    Args:
        job_name: 职业缩写，如 'sm', 'ft'
        part: 部位，如 'cap', 'coat'
    
    Returns:
        正确的 icon 路径
    """
    # 职业映射
    JOB_ICON_MAP = {
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
    
    # 部位文件名映射
    PART_ICON_MAP = {
        'cap': 'acap',
        'hair': 'ahair',
        'face': 'aface',
        'neck': 'aneck',
        'coat': 'acoat',
        'pants': 'apants',
        'belt': 'abelt',
        'shoes': 'ashoes',
        'skin': 'abody',
    }
    
    job_path, job_prefix = JOB_ICON_MAP.get(job_name, (job_name, job_name))
    part_icon = PART_ICON_MAP.get(part, f'a{part}')
    
    return f"item/avatar/{job_path}/{job_prefix}_{part_icon}.img"


def analyze_icon_path(icon_path: str, part: str, job_name: str) -> dict:
    """
    分析 icon 路径，返回检查结果和建议
    
    Returns:
        {
            'is_valid': bool,           # 是否有效
            'is_weapon': bool,          # 是否是武器路径
            'matches_part': bool,       # 是否与部位匹配
            'suggested_path': str,      # 建议的路径
            'issues': [str],            # 问题列表
        }
    """
    result = {
        'is_valid': False,
        'is_weapon': False,
        'matches_part': False,
        'suggested_path': '',
        'issues': [],
    }
    
    icon_path_lower = icon_path.lower()
    
    # 检查是否是武器路径
    for pattern in WEAPON_ICON_PATTERNS:
        if re.search(pattern, icon_path_lower):
            result['is_weapon'] = True
            result['issues'].append(f"路径包含武器特征: {pattern}")
            break
    
    # 检查是否在 avatar 目录
    if 'item/avatar/' not in icon_path_lower:
        result['issues'].append("路径不在 item/avatar/ 目录下")
    
    # 检查部位匹配
    part_pattern = AVATAR_ICON_PATTERNS.get(part, '')
    if part_pattern and re.search(part_pattern, icon_path_lower):
        result['matches_part'] = True
    else:
        result['issues'].append(f"路径不包含部位特征: {part}")
    
    # 总体有效性
    result['is_valid'] = (
        not result['is_weapon'] and 
        'item/avatar/' in icon_path_lower and 
        result['matches_part']
    )
    
    # 生成建议路径
    result['suggested_path'] = generate_correct_icon_path(job_name, part)
    
    return result


def main():
    print("=" * 70)
    print("Icon 路径匹配分析")
    print("=" * 70)
    
    # 测试用例
    test_cases = [
        # (icon_path, part, job_name, 描述)
        ("item/avatar/swordman/sm_acap.img", "cap", "sm", "标准时装路径"),
        ("item/new_equipment/01_weapon/swordman/sswd/sswd.img", "cap", "sm", "武器路径-不匹配"),
        ("item/equipment/weapon/swordman/swd_katana.img", "coat", "sm", "武器路径-不匹配"),
        ("item/avatar/swordman/sm_acoat.img", "coat", "sm", "标准外套路径"),
        ("item/avatar/fighter/ft_ahair.img", "hair", "ft", "标准发型路径"),
        ("item/new_equipment/02_armor/coat/coat.img", "coat", "sm", "护甲路径-可能不匹配"),
    ]
    
    print("\n测试用例分析:")
    print("-" * 70)
    
    for icon_path, part, job_name, desc in test_cases:
        result = analyze_icon_path(icon_path, part, job_name)
        
        print(f"\n描述: {desc}")
        print(f"路径: {icon_path}")
        print(f"部位: {part}, 职业: {job_name}")
        print(f"是否有效: {'✓' if result['is_valid'] else '✗'}")
        print(f"是否武器: {'是' if result['is_weapon'] else '否'}")
        print(f"部位匹配: {'✓' if result['matches_part'] else '✗'}")
        print(f"建议路径: {result['suggested_path']}")
        if result['issues']:
            print(f"问题: {', '.join(result['issues'])}")
    
    print("\n" + "=" * 70)
    print("解决方案建议")
    print("=" * 70)
    print("""
1. 检查 icon 路径是否有效：
   - 必须包含 "item/avatar/"
   - 不能包含武器路径特征（如 "weapon", "sswd", "swd" 等）
   - 路径中的部位标识应与当前部位匹配

2. 如果路径无效：
   - 使用生成的标准路径代替
   - 保留从 equ 文件读取的 frame（图标索引）

3. 修改同步脚本：
   - 在 extract_frame() 之后添加路径验证
   - 如果路径无效，使用 generate_correct_icon_path() 生成正确路径
   - 记录警告日志
""")


if __name__ == '__main__':
    main()
