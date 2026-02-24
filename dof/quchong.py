import os
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Union, Optional
from pydoftools.npk import NPK

# 核心配置（按需调整）
CONFIG = {
    "input_npk_dir": r"E:\DOF\Clients\DNF1031客户端\ImagePacks2",  # 原始NPK文件夹
    "output_npk_dir": r"E:\DOF\Tools\blackcat.6.12\deduplicated_npk",  # 去重后NPK输出目录
    "deduplicate_by": "name",  # 去重维度：name（按IMG名称）/md5（按IMG内容）
    "sort_npk_by_name": True,  # 是否按NPK文件名排序处理
    "ignore_case_sort": True,  # 排序时是否忽略大小写
    "keep_first": False,  # 去重时保留第一个出现的IMG（False则保留最后一个）
    "exclude_suffixes": [".log", ".tmp", ".txt"],  # 排除非NPK文件
}


def get_img_md5(img_file) -> str:
    """
    获取IMG文件内容的MD5值（用于精准去重）
    需根据你的File/IMG类实际接口调整！
    """
    try:
        # 场景1：IMG有data属性存储二进制内容（推荐）
        if hasattr(img_file, "data") and img_file.data:
            return hashlib.md5(img_file.data).hexdigest()

        # 场景2：IMG需通过save方法写入IO获取内容（备用）
        # from io import BytesIO
        # with BytesIO() as f:
        #     img_file.save(f)
        #     f.seek(0)
        #     return hashlib.md5(f.read()).hexdigest()

        # 兜底：MD5获取失败则用名称作为key
        return img_file.name
    except Exception as e:
        print(f"⚠️  警告：获取IMG MD5失败 → {img_file.name} | 错误：{str(e)}")
        return img_file.name


def deduplicate_single_npk(
        npk_file: Path,
        output_path: Path,
        deduplicate_by: str = "name",
        keep_first: bool = False
) -> Dict[str, int]:
    """
    处理单个NPK文件：去除内部重复的IMG，保留原文件名

    Args:
        npk_file: 原始NPK文件路径
        output_path: 去重后NPK保存路径
        deduplicate_by: 去重维度（name/md5）
        keep_first: 保留第一个出现的IMG（False保留最后一个）

    Returns:
        统计信息字典（原数量/去重后数量/重复数量）
    """
    stats = {
        "original_count": 0,
        "unique_count": 0,
        "duplicate_count": 0
    }

    try:
        # 1. 读取原始NPK文件
        with open(npk_file, "rb") as f:
            npk = NPK.open(f)
            npk.load_all()  # 加载所有IMG的完整数据
            stats["original_count"] = len(npk.files)

            if stats["original_count"] == 0:
                print(f"📄 {npk_file.name}：无IMG文件，直接复制")
                # 无内容则直接复制原文件
                with open(output_path, "wb") as out_f:
                    out_f.write(f.read())
                return stats

        # 2. 单文件内去重（核心逻辑）
        unique_imgs: Dict[str, object] = {}
        for img in npk.files:
            # 确定去重key
            if deduplicate_by == "md5":
                img_key = get_img_md5(img)
            else:
                img_key = img.name

            # 去重规则：保留第一个/最后一个
            if keep_first:
                if img_key not in unique_imgs:
                    unique_imgs[img_key] = img
                else:
                    stats["duplicate_count"] += 1
            else:
                if img_key in unique_imgs:
                    stats["duplicate_count"] += 1
                unique_imgs[img_key] = img  # 覆盖，保留最后一个

        # 3. 更新NPK并保存
        stats["unique_count"] = len(unique_imgs)
        npk.files.clear()
        npk.files.extend(list(unique_imgs.values()))

        with open(output_path, "wb") as out_f:
            npk.save(out_f, group_by_md5=True)  # 开启MD5分组进一步优化

        return stats

    except Exception as e:
        print(f"❌ 错误：处理 {npk_file.name} 失败 → {str(e)}")
        return stats


def natural_sort_key(s: str) -> list:
    """自然排序辅助函数（处理文件名中的数字，如avatar1.npk < avatar10.npk < avatar2.npk）"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]


def batch_deduplicate_npk(
        input_dir: Union[str, Path],
        output_dir: Union[str, Path],
        deduplicate_by: str = "name",
        sort_npk_by_name: bool = True,
        ignore_case_sort: bool = True,
        keep_first: bool = False,
        exclude_suffixes: Optional[List[str]] = None
) -> None:
    """
    批量处理NPK文件：保留原文件结构，仅去除每个NPK内部的重复IMG

    Args:
        input_dir: 原始NPK文件夹
        output_dir: 去重后输出文件夹
        deduplicate_by: 去重维度（name/md5）
        sort_npk_by_name: 是否按NPK文件名排序处理
        ignore_case_sort: 排序时是否忽略大小写
        keep_first: 保留第一个出现的IMG
        exclude_suffixes: 排除的文件后缀
    """
    # 路径标准化
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)  # 自动创建输出目录
    exclude_suffixes = exclude_suffixes or []
    exclude_suffixes = [s.lower() if s.startswith('.') else f'.{s.lower()}' for s in exclude_suffixes]

    # 1. 校验输入目录
    if not input_dir.is_dir():
        print(f"❌ 错误：输入目录 {input_dir} 不存在！")
        return

    # 2. 获取所有NPK文件并排序
    npk_files: List[Path] = []
    for item in input_dir.iterdir():
        if item.is_file() and item.suffix.lower() == ".npk" and item.suffix.lower() not in exclude_suffixes:
            npk_files.append(item)

    # 按文件名排序
    if sort_npk_by_name:
        if ignore_case_sort:
            # 普通字母序（忽略大小写）
            npk_files.sort(key=lambda x: x.name.lower())
        else:
            # 自然排序（处理数字）
            npk_files.sort(key=lambda x: natural_sort_key(x.name))

    total_npk = len(npk_files)
    if total_npk == 0:
        print("📭 未找到任何NPK文件！")
        return

    print(f"🚀 开始处理：共找到 {total_npk} 个NPK文件")
    print(f"📌 去重规则：按{deduplicate_by}去重，{'保留第一个' if keep_first else '保留最后一个'}出现的IMG")
    print(f"📁 输出目录：{output_dir}\n")

    # 3. 批量处理每个NPK文件
    total_original = 0
    total_unique = 0
    total_duplicate = 0

    for idx, npk_file in enumerate(npk_files, 1):
        output_path = output_dir / npk_file.name  # 保留原文件名
        stats = deduplicate_single_npk(
            npk_file=npk_file,
            output_path=output_path,
            deduplicate_by=deduplicate_by,
            keep_first=keep_first
        )

        # 累计统计
        total_original += stats["original_count"]
        total_unique += stats["unique_count"]
        total_duplicate += stats["duplicate_count"]

        # 打印单文件结果
        print(
            f"[{idx}/{total_npk}] ✅ {npk_file.name} | 原IMG数：{stats['original_count']} | 去重后：{stats['unique_count']} | 重复：{stats['duplicate_count']}")

    # 4. 输出汇总统计
    print("\n📊 批量处理汇总")
    print("-" * 50)
    print(f"处理NPK文件总数：{total_npk}")
    print(f"原始IMG总数：{total_original}")
    print(f"去重后IMG总数：{total_unique}")
    print(f"去除重复IMG总数：{total_duplicate}")
    print(f"去重率：{total_duplicate / total_original * 100:.2f}%" if total_original > 0 else "0%")
    print(f"\n✅ 所有文件处理完成！输出目录：{output_dir}")


if __name__ == "__main__":
    # 执行批量去重
    batch_deduplicate_npk(
        input_dir=CONFIG["input_npk_dir"],
        output_dir=CONFIG["output_npk_dir"],
        deduplicate_by=CONFIG["deduplicate_by"],
        sort_npk_by_name=CONFIG["sort_npk_by_name"],
        ignore_case_sort=CONFIG["ignore_case_sort"],
        keep_first=CONFIG["keep_first"],
        exclude_suffixes=CONFIG["exclude_suffixes"]
    )