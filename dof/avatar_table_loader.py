"""
Avatar Table Loader - 装扮表加载器

负责加载和查询装扮表文件，为 equ 生成提供 name 和 icon_index。
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from model.equ_models import job_chinese, part_chinese

logger = logging.getLogger(__name__)


# Job 代码到装扮表文件名的映射
JOB_TO_FILENAME = {
    'sm': '鬼剑士(男)装扮表.txt',
    'ft': '格斗家(女)装扮表.txt',
    'fm': '格斗家(男)装扮表.txt',
    'gn': '神枪手(男)装扮表.txt',
    'gg': '神枪手(女)装扮表.txt',
    'mg': '魔法师(女)装扮表.txt',
    'mm': '魔法师(男)装扮表.txt',
    'pr': '圣职者(男)装扮表.txt',
    'th': '暗夜使者装扮表.txt',
}

# 部位英文到中文的映射（用于匹配装扮表中的 part 字段）
# 扩展映射，包含装扮表中可能出现的多种中文表述
PART_TO_CHINESE = {
    'coat': '上衣',
    'pants': '下装',
    'belt': '腰带',
    'neck': '胸部',
    'shoes': '鞋子',
    'cap': '头饰',
    'hair': '发型',
    'face': '面部',
    'body': '皮肤',
}

# 反向映射：装扮表中的中文 -> 英文代码
# 处理多种可能的表述
CHINESE_TO_PART = {
    '上衣': 'coat',
    '下装': 'pants',
    '腰带': 'belt',
    '胸部': 'neck',
    '鞋子': 'shoes',
    '头饰': 'cap',
    '发型': 'hair',
    '面部': 'face', 
    '皮肤': 'body',
}


class AvatarInfo:
    """装扮信息数据类"""
    
    def __init__(self, code: int, part: str, icon_index: int, name: str):
        self.code = code
        self.part = part
        self.icon_index = icon_index
        self.name = name
    
    def __repr__(self):
        return f"AvatarInfo(code={self.code}, part='{self.part}', icon_index={self.icon_index}, name='{self.name}')"


class AvatarTableLoader:
    """
    装扮表加载器
    
    功能：
    1. 加载指定职业的装扮表文件
    2. 解析并构建查找索引
    3. 提供按 (job, part, code) 的查询接口
    """
    
    def __init__(self, base_path: str):
        """
        初始化加载器
        
        Args:
            base_path: 装扮表文件所在目录路径
        """
        self.base_path = Path(base_path)
        self._tables: Dict[str, Dict[Tuple[str, int], AvatarInfo]] = {}
        # _tables 结构: {job: {(part, code): AvatarInfo}}
    
    def _parse_line(self, line: str) -> Optional[AvatarInfo]:
        """
        解析装扮表中的一行数据
        
        格式: {code},{part}{icon_index},{name}
        示例: 100,发型1,运动型短卷发
        
        Args:
            line: 原始行数据
            
        Returns:
            AvatarInfo 对象，解析失败返回 None
        """
        line = line.strip()
        if not line or line.startswith('['):
            return None
        
        parts = line.split(',')
        if len(parts) < 3:
            return None
        
        try:
            # 解析 code
            code = int(parts[0])
            
            # 解析 part 和 icon_index
            # 格式如: "发型1", "上衣10"
            part_with_index = parts[1]
            part_cn = ""
            icon_index_str = ""
            
            # 分离中文部分和数字部分
            for i, char in enumerate(part_with_index):
                if char.isdigit():
                    part_cn = part_with_index[:i]
                    icon_index_str = part_with_index[i:]
                    break
            
            if not part_cn or not icon_index_str:
                return None
            
            icon_index = int(icon_index_str)
            
            # 解析 name
            name = parts[2]
            
            return AvatarInfo(code, part_cn, icon_index, name)
            
        except (ValueError, IndexError) as e:
            logger.debug(f"解析行失败: {line}, 错误: {e}")
            return None
    
    def _get_part_english(self, part_chinese: str) -> Optional[str]:
        """
        将部位中文名转为英文名
        
        Args:
            part_chinese: 部位中文名（如 "发型"、"上衣"、"面部"）
            
        Returns:
            部位英文名（如 "hair"、"coat"、"face"），找不到返回 None
        """
        return CHINESE_TO_PART.get(part_chinese)
    
    def load(self, job: str) -> bool:
        """
        加载指定职业的装扮表
        
        Args:
            job: 职业代码（如 'sm', 'ft'）
            
        Returns:
            加载成功返回 True
        """
        if job in self._tables:
            logger.debug(f"装扮表已加载: {job}")
            return True
        
        filename = JOB_TO_FILENAME.get(job)
        if not filename:
            logger.error(f"未知职业代码: {job}")
            return False
        
        file_path = self.base_path / filename
        if not file_path.exists():
            logger.error(f"装扮表文件不存在: {file_path}")
            return False
        
        try:
            # 读取文件
            with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                lines = f.readlines()
            
            # 解析数据
            table = {}
            current_part = None
            
            for line in lines:
                line = line.strip()
                
                # 检测 section 如 [avatar,hair]
                # section 名称是英文，如 hair, coat, pants 等
                if line.startswith('[avatar,') and line.endswith(']'):
                    part_section = line[8:-1]  # 提取 hair, coat 等
                    # part_section 已经是英文，检查是否有效
                    if part_section in PART_TO_CHINESE:
                        current_part = part_section
                        logger.debug(f"检测到部位 section: {part_section}")
                    else:
                        logger.debug(f"未知的 section: {part_section}")
                    continue
                
                # 解析数据行
                if current_part and line and not line.startswith('['):
                    info = self._parse_line(line)
                    if info:
                        # 验证 part 是否匹配（数据中的 part 是中文）
                        info_part_eng = self._get_part_english(info.part)
                        if info_part_eng == current_part:
                            key = (current_part, info.code)
                            table[key] = info
                        else:
                            logger.debug(f"Part 不匹配: {info.part}({info_part_eng}) != {current_part}")
            
            self._tables[job] = table
            logger.info(f"成功加载装扮表: {job}, 共 {len(table)} 条记录")
            return True
            
        except Exception as e:
            logger.error(f"加载装扮表失败 {job}: {e}")
            return False
    
    def load_all(self) -> int:
        """
        加载所有职业的装扮表
        
        Returns:
            成功加载的职业数量
        """
        count = 0
        for job in JOB_TO_FILENAME.keys():
            if self.load(job):
                count += 1
        return count
    
    def lookup(self, job: str, part: str, code: int) -> Optional[AvatarInfo]:
        """
        查找装扮信息
        
        Args:
            job: 职业代码（如 'sm'）
            part: 部位代码（如 'hair', 'coat'）
            code: 装扮代码（整数）
            
        Returns:
            AvatarInfo 对象，找不到返回 None
        """
        # 确保已加载
        if job not in self._tables:
            if not self.load(job):
                return None
        
        table = self._tables.get(job, {})
        key = (part, code)
        return table.get(key)
    
    def get_name(self, job: str, part: str, code: int) -> Optional[str]:
        """
        获取装扮名称
        
        Args:
            job: 职业代码
            part: 部位代码
            code: 装扮代码
            
        Returns:
            装扮名称，找不到返回 None
        """
        info = self.lookup(job, part, code)
        return info.name if info else None
    
    def get_icon_index(self, job: str, part: str, code: int) -> Optional[int]:
        """
        获取图标索引
        
        Args:
            job: 职业代码
            part: 部位代码
            code: 装扮代码
            
        Returns:
            图标索引，找不到返回 None
        """
        info = self.lookup(job, part, code)
        return info.icon_index if info else None
    
    def get_stats(self) -> Dict:
        """获取加载统计信息"""
        return {
            'loaded_jobs': list(self._tables.keys()),
            'total_records': sum(len(t) for t in self._tables.values()),
            'job_counts': {job: len(table) for job, table in self._tables.items()},
        }
    
    def clear(self):
        """清除所有加载的数据"""
        self._tables.clear()


def construct_code(avatar_code: int, suffix: int) -> int:
    """
    构造装扮代码
    
    格式: int(f"{avatar_code}{suffix:02d}")
    整数转换会自动去除前导零
    
    Args:
        avatar_code: avatar 变体代码
        suffix: 后缀索引
        
    Returns:
        整数 code
    """
    return int(f"{avatar_code}{suffix:02d}")


def generate_equ_name(
    job: str,
    part: str,
    avatar_code: int,
    suffix: int,
    loader: AvatarTableLoader
) -> Tuple[str, int, bool]:
    """
    生成 equ 的 name 标签内容
    
    Args:
        job: 职业代码
        part: 部位代码
        avatar_code: avatar 变体代码
        suffix: 后缀索引
        loader: AvatarTableLoader 实例
        
    Returns:
        (name, icon_index, found)
        - name: name 标签内容
        - icon_index: 图标索引
        - found: 是否在装扮表中找到
    """
    code = construct_code(avatar_code, suffix)
    
    # code=0 为特殊项
    if code == 0:
        default_name = f"{job}_{part}_{code}"
        return default_name, 0, False
    
    # 查询装扮表
    info = loader.lookup(job, part, code)
    
    if info:
        return info.name, info.icon_index, True
    else:
        default_name = f"{job}_{part}_{code}"
        return default_name, 0, False


def main():
    """测试入口"""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 测试加载器
    base_path = r'E:\DOF\Tools\blackcat.6.12\output\Avatar'
    loader = AvatarTableLoader(base_path)
    
    print("=" * 70)
    print("Avatar Table Loader 测试")
    print("=" * 70)
    
    # 加载鬼剑士装扮表
    if loader.load('sm'):
        print("\n✓ 成功加载鬼剑士装扮表")
        
        # 测试查询
        test_cases = [
            ('sm', 'hair', 100),   # 应找到
            ('sm', 'hair', 101),   # 应找到
            ('sm', 'hair', 99999), # 未找到
            ('sm', 'coat', 100),   # 应找到
        ]
        
        print("\n查询测试:")
        print("-" * 70)
        for job, part, code in test_cases:
            info = loader.lookup(job, part, code)
            if info:
                print(f"✓ {job}/{part}/{code}: {info.name} (icon={info.icon_index})")
            else:
                print(f"✗ {job}/{part}/{code}: 未找到")
        
        # 显示统计
        stats = loader.get_stats()
        print(f"\n统计: 已加载 {len(stats['loaded_jobs'])} 个职业, 共 {stats['total_records']} 条记录")
    else:
        print("\n✗ 加载失败")
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
