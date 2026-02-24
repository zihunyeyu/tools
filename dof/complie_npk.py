import re
import os
from pathlib import Path
from typing import Optional, List
import json
from pydoftools.npk import NPK
from pydoftools.npk.img.version import IMGv6


# 核心拆分函数
def split_mixed_string(s):
    match = re.match(r'^([a-zA-Z]+)(\d+)(.+)$', s)
    return match.groups() if match else (None, None, None)


def find_files_containing_name_advanced(
        target_dir: str | Path,
        keyword: str,
        recursive: bool = True,
        ignore_case: bool = True,
        exclude_suffixes: Optional[List[str]] = None
) -> list[Path]:
    """
    高级版：查找文件名包含关键词的文件，支持递归、忽略大小写、排除后缀

    Args:
        target_dir: 要查找的文件夹路径
        keyword: 要匹配的文件名关键词
        recursive: 是否递归查找子文件夹（默认True）
        ignore_case: 是否忽略大小写（默认True）
        exclude_suffixes: 要排除的文件后缀列表（如 ['.log', '.tmp']）

    Returns:
        匹配的文件路径列表
    """
    target_dir = Path(target_dir)
    if not target_dir.is_dir():
        print(f"错误：文件夹 {target_dir} 不存在或不是目录")
        return []

    # 处理参数默认值
    exclude_suffixes = exclude_suffixes or []
    # 统一后缀格式（确保以.开头）
    exclude_suffixes = [s if s.startswith('.') else f'.{s}' for s in exclude_suffixes]

    # 处理关键词大小写
    keyword_compare = keyword.lower() if ignore_case else keyword

    matched_files = []

    # 遍历方式：递归/非递归
    glob_pattern = "**/*" if recursive else "*"
    for item in target_dir.glob(glob_pattern):
        # print(item)
        if item.is_file():
            # 1. 排除指定后缀的文件
            if item.suffix in exclude_suffixes:
                continue

            # 2. 处理文件名大小写
            file_name = item.name.lower() if ignore_case else item.name

            # 3. 匹配关键词
            if keyword_compare in file_name:
                matched_files.append(item)

    return matched_files


# 初始化字典 & 指定路径
avatar_dict = {}
npk_folder = "E:\\DOF\\Tools\\blackcat.6.12\\NPK"
base_folder = "E:\\DOF\\Tools\\blackcat.6.12\\base"
empty_folder = "E:\\DOF\\Tools\\blackcat.6.12\\compiles"

# 遍历NPK文件
for file_name in os.listdir(npk_folder):

    if not file_name.lower().endswith(".npk"):
        continue
    npk_path = os.path.join(npk_folder, file_name)

    with open(npk_path, "rb") as f:
        npk = NPK.open(f)
        npk.load_all()
        # 合并其他区服NPK
        for file_path in find_files_containing_name_advanced(base_folder, file_name.split('.')[0].lower()):
            with open(file_path, "rb") as c_f:
                c_npk = NPK.open(c_f)
                c_npk.load_all()
                npk.files.extend(c_npk.files)

        unique_dict = {}
        for file in npk.files:
            unique_dict[file.name] = file  # 覆盖重复值
        unique_files = list(unique_dict.values())
        npk.files.clear()
        npk.files.extend(unique_files)

        with open(os.path.join(empty_folder, file_name), 'wb') as out_io:
            npk.save(out_io, True)
