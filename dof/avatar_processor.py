import json
import os
from pathlib import Path

from dof.check_avatar import verify_tsv_records
from dof.model.avatars import *

# 职业映射：缩写 -> (编码, 路径前缀)
JOB_MAP = {
    'sm': (1, 'swordman/', 'swordman'),
    'gg': (2, 'gunner/at_', 'at gunner'),
    'gn': (3, 'gunner/', 'gunner'),
    'ft': (4, 'fighter/', 'fighter'),
    'fm': (5, 'fighter/at_', 'at fighter'),
    'mg': (6, 'mage/', 'mage'),
    'mm': (7, 'mage/at_', 'at mage'),
    'pr': (8, 'priest/', 'priest'),
    'th': (9, 'thief/', 'thief')
}

# 部位映射：名称 -> 编码
PART_MAP = {
    'belt': 1,
    'cap': 2,
    'coat': 3,
    'face': 4,
    'hair': 5,
    'neck': 6,
    'pants': 7,
    'shoes': 8
}

EQU_PART_MAP = {
    'belt': 'waist',
    'cap': 'hat',
    'coat': 'coat',
    'face': 'face',
    'hair': 'hair',
    'neck': 'breast',
    'pants': 'pants',
    'shoes': 'shoes'
}

# 装备路径模板（改用Path处理跨平台路径）
EQU_PATH = "`character/{job}avatar/{part}/{code}.equ`"


def fix_equ(equ_code, job, part, layers):
    pass


def fix_equ_code(base_code: int, suffix: int) -> str:
    """生成标准化的7位编码（6位基础+1位后缀）"""
    base_str = str(base_code).zfill(6)
    return f"{base_str}{suffix}"


def generate_equ_list(json_path: str, output_path: str):
    """从JSON生成装备编码清单和空.equ文件"""
    # 1. 读取JSON数据（增强异常处理）
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            datas = json.load(f)
        if not isinstance(datas, dict):
            print("错误：JSON文件根节点必须是字典")
            return
        print(f"成功读取JSON数据，包含 {len(datas)} 个职业")
    except FileNotFoundError:
        print(f"错误：JSON文件 {json_path} 不存在")
        return
    except json.JSONDecodeError as e:
        print(f"错误：JSON格式无效 - {e}")
        return
    except Exception as e:
        print(f"读取JSON异常 - {e}")
        return

    # 2. 遍历数据生成装备编码
    equ_codes = {}
    error_count = 0

    for job, auras in datas.items():
        if job not in JOB_MAP:
            print(f"警告：未知职业 {job}，跳过")
            continue
        job_code, job_path, equ_job = JOB_MAP[job]

        if not isinstance(auras, dict):
            error_count += 1
            continue

        for part, indexes in auras.items():
            if part not in PART_MAP:
                continue
            part_code = PART_MAP[part]

            if not isinstance(indexes, list):
                error_count += 1
                continue

            for idx, index in enumerate(indexes):
                # 校验三元组格式
                if not isinstance(index, (list, tuple)) or len(index) != 3:
                    error_count += 1
                    continue

                code, count, layers = index
                # 校验数字类型
                if not isinstance(code, int) or not isinstance(count, int):
                    error_count += 1
                    continue

                # 遍历count生成编码
                for i in range(count):
                    base_7code = fix_equ_code(code, i)
                    e_code = f"{job_code}{part_code}{base_7code}"
                    check = (equ_job, EQU_PART_MAP[part], f"{code}	{i}")
                    if verify_tsv_records(check):
                        # print(check)
                        continue
                    # 去重：已处理过的编码跳过
                    if e_code in equ_codes:
                        continue

                    # 生成跨平台路径
                    e_path = EQU_PATH.format(job=job_path, part=part, code=e_code)
                    equ_codes[e_code] = e_path

                    # try:
                    #     file_path = Path(e_path.replace('/', os.sep).replace('`', ''))  # 自动适配系统分隔符
                    #
                    #     # 创建目录（不存在则创建）
                    #     file_path.parent.mkdir(parents=True, exist_ok=True)
                    #     # 创建空.equ文件（仅当文件不存在时创建）
                    #     if not file_path.exists():
                    #         try:
                    #             file_path.touch()  # 更安全的创建空文件方式
                    #         except Exception as e:
                    #             print(f"警告：创建文件 {file_path} 失败 - {e}")
                    #             error_count += 1
                    #             continue
                    #     # 填写equ文件
                    #     equ_animation = EQU_ANIMATION_STRING.format(job=equ_job, code=code, index=i)
                    #     layer_string = ''
                    #     for layer in layers:
                    #         layer_ = f'{part}_{layer}'
                    #         if layer_ in layer_dict.keys():
                    #             layer_string += LAYER_STRING.format(layer_index=layer_dict[layer_], layer=layer_,
                    #                                                 job=equ_job.replace(' ', ''))
                    #             layer_string += '\n\n'
                    #
                    #     equ_text = EQU_TEMP.format(equ_code=e_code, job=equ_job, equ_part=EQU_PART_MAP[part],
                    #                                animation_job=equ_animation, layer_variation=layer_string)
                    #     with open(file_path, 'w', encoding='utf-8') as e_f:
                    #         e_f.write(equ_text)
                    #
                    #     # 存储编码和路径
                    # except:
                    #     pass

    # 3. 写入lst文件
    try:
        with open(output_path, 'w', encoding='utf-8') as lst:
            sorted_items = sorted(equ_codes.items(), key=lambda x: x[0])

            start_code = 133011

            for code, path in sorted_items:
                start_code += 1

                lst.write(f"{code}\t{path}\n")
                # lst.write(f'	{start_code}	{code}	3	0	0	-1	-1	{code}	4	0	0	-1\n')
    except Exception as e:
        print(f"写入lst文件失败 - {e}")
        return

    # 4. 输出统计
    print(f"\n生成完成！")
    print(f"输出文件：{output_path}")
    print(f"总装备编码数：{len(equ_codes)}")
    print(f"处理过程中错误数：{error_count}")


if __name__ == "__main__":
    JSON_FILE = "avatar_data.json"
    LST_FILE = "equ.lst"

    # 示例JSON格式（你可以根据实际情况调整）
    # avatar_data.json 内容示例：
    # {
    #   "sm": {
    #     "coat": [(2850, 2, 1), (2840, 1, 1)],
    #     "cap": [(2810, 1, 1)]
    #   },
    #   "gg": {
    #     "neck": [(2780, 1, 1)]
    #   }
    # }

    generate_equ_list(JSON_FILE, LST_FILE)

    # 可选：验证输出
    # if os.path.exists(LST_FILE):
    #     with open(LST_FILE, 'r', encoding='utf-8') as f:
    #         print("\n前10条结果：")
    #         for i, line in enumerate(f):
    #             if i >= 10:
    #                 break
    #             print(line.strip())
