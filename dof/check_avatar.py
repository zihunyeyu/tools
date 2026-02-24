import csv
from typing import List, Dict, Tuple

tsv_data = {}

with open("complete_equipment_tags.tsv", 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter='\t')
    # 表头：文件代码	文件路径	equipment type	variation
    for row in reader:
        # 构建唯一标识：(文件路径, equipment_type, variation)
        key = (
            row['文件路径'].strip(),
            row['equipment type'].strip(),
            row['variation'].strip(),
        )

        tsv_data[key] = True  # 标记为存在


def verify_tsv_records(
        item: Tuple[str, str, str],
) -> bool:
    path = item[0].strip()
    equip_type = item[1].strip()
    variation = '_'.join(item[2].strip().split('\t'))
    check_key = (path, equip_type, variation)

    result = check_key in tsv_data
    return result


# ==================== 使用示例 ====================
if __name__ == "__main__":
    check_records = [
        ("swordman", "hat", "0	0"),  # 示例1：存在的记录
        ("thief", "hair", "3	5"),  # 示例2：存在的记录
        ("swordman", "head", "10	20"),  # 示例3：不存在的记录
        ("mage", "foot", ""),  # 示例4：变体为空的记录
    ]

    # 3. 执行验证
    print(verify_tsv_records(
        item=check_records[1],
    ))
