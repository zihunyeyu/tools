import os.path
import re
from pprint import pprint
from PIL import Image, ImageChops

from zhconv import zhconv

import numpy as np
import cv2
import os
import matplotlib.pyplot as plt

from Toolkits.web_funcs import __get_json_test


def cal_len(text):
    pattern = re.compile(r'[\u4e00-\u9fa5]')
    cn_char = re.findall(pattern,text)       # 查找中文字符
    lent = len(cn_char) + len(text)
    return lent

def convert_obj_zhHans(_obj):
    if isinstance(_obj, dict):
        for key in _obj:
            _obj[key] = convert_obj_zhHans(_obj[key])
    elif isinstance(_obj, list):
        for i in range(len(_obj)):
            _obj[i] = convert_obj_zhHans(_obj[i])
    elif isinstance(_obj, str):
        _obj = zhconv.convert(_obj, 'zh-hans')
    return _obj

def split_image(image_path, rows, cols) -> list:
    images = []
    try:
        image = Image.open(image_path)
        width, height = image.size
        tile_width = width // rows
        tile_height = height // cols
        for row in range(cols):
            for col in range(rows):
                left = col * tile_width
                upper = row * tile_height
                right = left + tile_width
                lower = upper + tile_height
                tile = image.crop((left, upper, right, lower))

                # print(left, upper, right, lower)

                images.append(tile)
        return images

    except Exception as e:
        print(str(e))
        return images

def trim_white_border(image_source: str):
    image = cv2.imread(image_source)  # 读取图片
    img = cv2.medianBlur(image, 5)  # 中值滤波，去除黑色边际中可能含有的噪声干扰
    b = cv2.threshold(img, 3, 255, cv2.THRESH_BINARY)  # 调整裁剪效果
    binary_image = b[1]  # 二值图--具有三信道
    binary_image = cv2.cvtColor(binary_image, cv2.COLOR_BGR2GRAY)
    # print(binary_image.shape)     #改为单信道

    edges_y, edges_x = np.where(binary_image == 255)  ##h, w
    bottom = min(edges_y)
    top = max(edges_y)
    height = top - bottom

    left = min(edges_x)
    right = max(edges_x)
    height = top - bottom
    width = right - left

    res_image = image[bottom:bottom + height, left:left + width]

    plt.figure()
    plt.subplot(1, 2, 1)
    plt.imshow(image)
    plt.subplot(1, 2, 2)
    plt.imshow(res_image)
    # plt.savefig(os.path.join("res_combine.jpg"))
    # plt.show()
    file_name = image_source.split("\\")[-1]
    ext = file_name.split('.')[-1]
    name = file_name.replace("."+ext, '')

    print(file_name, name, ext)

    cv2.imwrite(os.path.join(image_source.replace(file_name, ""), name+'_process.'+ext), res_image)
    # return res_image

from PIL import Image
import os

def dds_to_png(dds_path, png_path):
    try:
        # 打开 DDS 文件
        img = Image.open(dds_path)
        # 保存为 PNG 格式
        img.save(png_path, 'png')
        print(f"成功转换: {dds_path} -> {png_path}")
    except Exception as e:
        print(f"转换失败: {dds_path}, 错误: {e}")

def convert_dds_to_png(input_folder, output_folder):
    # 示例: 转换单个文件
    # dds_file = 'your_image.dds'
    # png_file = 'your_image.png'
    # dds_to_png(dds_file, png_file)

    # 示例: 批量转换文件夹内的所有 DDS 文件
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for filename in os.listdir(input_folder):
        print(filename)
        if filename.lower().endswith('.dds'):
            dds_path = os.path.join(input_folder, filename)
            # 构建输出 PNG 文件名
            base_name = os.path.splitext(filename)[0]
            png_path = os.path.join(output_folder, f"{base_name}.png")
            dds_to_png(dds_path, png_path)


def find_max_between_two_nums(num_list, num1, num2):
    """
    在数字列表中查找指定两个数字之间（包含边界）的最大值

    参数:
        num_list (list): 待查找的数字列表
        num1 (int/float): 范围下限（或上限，函数会自动识别）
        num2 (int/float): 范围上限（或下限，函数会自动识别）

    返回:
        int/float: 范围内的最大值；若无符合条件的数，返回 None
    """
    # 先确定范围的上下限（避免用户输入的 num1 大于 num2）
    lower = min(num1, num2)
    upper = max(num1, num2)

    # 筛选出在 [lower, upper] 范围内的数字
    filtered_nums = [num for num in num_list if lower <= num <= upper]

    # 判断是否有符合条件的数字，有则返回最大值，无则返回 None
    if filtered_nums:
        return max(filtered_nums)
    else:
        return None


if __name__ == '__main__':
    convert_dds_to_png("./icon_unit_portrait/", './icon_unit_portrait/')
    pass