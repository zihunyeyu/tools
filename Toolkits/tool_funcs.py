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


if __name__ == '__main__':
    # card_en_datas = convert_obj_zhHans(card_en_datas)
    # print(convert_obj_zhHans('羅蘭·班克斯'))
    # pprint(convert_obj_zhHans(__get_json_test()))
    # test_image = Image.open("D:\\temp1\\test.jpg")
    trim_white_border("D:\\temp1\\test.jpg")
    # cv2.imwrite(os.path.join("D:\\temp1\\", "res_0923.jpg"), img)
    pass