import re
import os
import json
from pprint import pprint
from pydoftools.npk import NPK
from pydoftools.npk.img.version import IMGv6


# 核心拆分函数
def split_mixed_string(s):
    match = re.match(r'^([a-zA-Z]+)(\d+)(.+)$', s)
    return match.groups() if match else (None, None, None)


# 初始化字典 & 指定路径
avatar_dict = {}
npk_folder = "npk_files"
output_json_path = "avatar_data.json"  # 输出的JSON文件路径

# 遍历NPK文件
if not os.path.exists(npk_folder):
    print(f"错误：文件夹 {npk_folder} 不存在！")
else:
    for file_name in os.listdir(npk_folder):
        if not file_name.lower().endswith(".npk"):
            continue

        npk_path = os.path.join(npk_folder, file_name)
        print(f"解析中: {npk_path}")

        try:
            with open(npk_path, "rb") as f:
                npk = NPK.open(f)
                npk.load_all()

                for nf in npk.files:
                    # 清理文件名 & 过滤无效文件
                    name = nf.name.split('/')[-1].replace('.img', '')
                    if 'mask' in name or '_' not in name:
                        continue

                    # 拆分信息
                    job, info = name.split('_', 1)
                    part, code, layer = split_mixed_string(info)
                    if not all([part, code, layer]):
                        continue

                    # 处理编号/索引
                    number = code[:-2] if len(code) >= 2 else code
                    index = code[-2:] if len(code) >= 2 else ''

                    # 初始化字典层级
                    avatar_dict.setdefault(job, {}).setdefault(part, {}).setdefault(number, {
                        'layer': set(), 'indexes': set(), 'count': 0
                    })
                    ad = avatar_dict[job][part][number]
                    ad['layer'].add(layer)
                    if index: ad['indexes'].add(index)

                    # 统计count
                    try:
                        img = nf.to_img()
                        ad['count'] = len(img.color_boards) if isinstance(img, IMGv6) else len(ad['indexes'])
                    except Exception as img_e:
                        print(f"  解析图片 {name} 出错: {str(img_e)[:30]}")
                        ad['count'] = len(ad['indexes'])

        except Exception as e:
            print(f"解析失败 {file_name}: {str(e)[:50]}")

    # 格式化最终数据
    for job, parts in avatar_dict.items():
        for part, nums in parts.items():
            avatar_dict[job][part] = sorted(
                [[int(num) if num.isdigit() else num, nums[num]['count'], sorted(nums[num]['layer'])]
                 for num in nums],
                key=lambda x: x[0] if isinstance(x[0], int) else 0
            )

# ========== 核心新增：将数据写入JSON文件 ==========
try:
    # indent=4 让JSON文件格式化显示，ensure_ascii=False支持中文（如有）
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(avatar_dict, f, indent=4, ensure_ascii=False)
    print(f"\n数据已成功写入 {output_json_path}")
except Exception as e:
    print(f"\n写入JSON文件失败: {str(e)}")

# 控制台打印预览
# pprint(avatar_dict)