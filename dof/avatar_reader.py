import re
import os
import json
from pydoftools.npk import NPK
from pydoftools.npk.img.version import IMGv6

from arkham.extract_pic_from_tts import card_images

jobs = ['sm', 'gg', 'gn', 'ft', 'fm', 'mg', 'mm', 'pr', 'th']
jobs_full = ['swordman', 'gunner_at', 'gunner', 'fighter', 'fighter_at', 'mage', 'mage_at', 'priest', 'thief']
parts = ['belt', 'cap', 'coat', 'face', 'hair', 'neck', 'pants', 'shoes']

kr_dir = 'D:\\BaiduNetdiskDownload\\ImagePacks2\\'
jp_dir = 'E:\\DOF\\Tools\\blackcat.6.12\\output\\Download\\日本-正式服\\'
na_ir = 'E:\\DOF\\Tools\\blackcat.6.12\\output\\Download\\北美地区-正式服\\'
compile_dir = 'E:\\DOF\\Tools\\blackcat.6.12\\compiles\\'


layers = {}

# 核心拆分函数
def split_mixed_string(s):
    match = re.match(r'^([a-zA-Z]+)(\d+)(.+)$', s)
    return match.groups() if match else (None, None, None)


# 初始化字典 & 指定路径
avatar_dict = {}
npk_folder = "E:\\DOF\\Tools\\blackcat.6.12\\compiles"
output_json_path = "avatar_data.json"  # 输出的JSON文件路径

# 遍历NPK文件
if not os.path.exists(npk_folder):
    print(f"错误：文件夹 {npk_folder} 不存在！")
else:
    for file_name in os.listdir(npk_folder):

        if not file_name.lower().endswith(".npk"):
            continue
        npk_path = os.path.join(npk_folder, file_name)

        try:
            with open(npk_path, "rb") as f:
                npk = NPK.open(f)
                npk.load_all()
                # 合并其他区服NPK
                # for c_dir in [jp_dir, kr_dir, na_ir]:
                #     c_path = os.path.join(c_dir, file_name)
                #     try:
                #         with open(c_path, 'rb') as c_f:
                #             c_npk = NPK.open(c_f)
                #             c_npk.load_all()
                #             npk.files.extend(c_npk.files)
                #     except:
                #         pass
                #
                # unique_dict = {}
                # for file in npk.files:
                #     unique_dict[file.name] = file  # 覆盖重复值
                # unique_files = list(unique_dict.values())
                # npk.files.clear()
                # npk.files.extend(unique_files)
                # with open(os.path.join(compile_dir, file_name), 'wb') as out_io:
                #     npk.save(out_io, True)

                # 处理IMGs
                for nf in npk.files:
                    # 清理文件名 & 过滤无效文件
                    name = nf.name.split('/')[-1].replace('.img', '')
                    if 'mask' in name or '_' not in name:
                        continue

                    # 拆分信息
                    job, info = name.split('_', 1)
                    if job not in jobs:
                        continue

                    part, code, layer = split_mixed_string(info)

                    if layer not in layers.keys():
                        layers[layer] = True

                    if part not in parts or not all([part, code, layer]):
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


print(layers.keys())