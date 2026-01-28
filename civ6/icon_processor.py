import glob
import os
import cv2

# from wand import image as dds_image
import imageio.v2 as imageio
from PIL import Image, ImageDraw
from pypinyin import lazy_pinyin


def read_dds_image(image_path):
    image_array = imageio.imread(image_path)
    resize_image = cv2.resize(image_array, (300, 300))
    img = Image.fromarray(resize_image)
    return img

def create_circle_mask(image_size):
    mask = Image.new('L', image_size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, image_size[0], image_size[1]), fill=255)
    return mask

def apply_circle_mask(original_image):
    original_image = original_image.convert('RGBA')
    mask = create_circle_mask(original_image.size)
    background = Image.new('RGBA', original_image.size, (0,0,0,255))
    original_image = Image.alpha_composite(background, original_image)
    result = Image.new('RGBA', original_image.size)
    result.paste(original_image, (0, 0), mask)
    return result

def get_dir_images(dir_path):
    img_glob = os.path.join(dir_path, "*.png")
    img_paths = []

    img_paths.extend(glob.glob(img_glob))
    _images = []
    index = 0
    for i in img_paths:
        icon = r'''<Replace Name="{file_name}" Atlas="ATLAS_ICON_TKH_UNIT" Index="{index}" />'''

        # hero_class_str = r'''<Row Name="ATLAS_ICON_{hero_class}" IconSize="105" IconsPerRow="1" IconsPerColumn="1" Filename="{hero_class}-105" />'''
        # icon_hero_class_str = r'''<Replace Name="ICON_{hero_class}_PORTRAIT" Atlas="ATLAS_TKH_GUARD_PORTRAIT" Index="0" />'''
        file_name = i.split("\\")[-1].split(".")[0]
        # hero_name = f'{file_name.replace('-105', '')}_PORTRAIT'
        print(icon.format(file_name=file_name, index=index) )
        # _image = apply_circle_mask(read_dds_image(read_dds_image(i)))
        _image = read_dds_image(i)
        _images.append(_image)
        index += 1
    return _images

if __name__ == '__main__':
    # fileList = os.listdir('./icon_unit_portrait/')
    # for file in fileList:
    #     file_name = file.split(".")[0].replace('ICON_UNIT_TKH_', '').replace('UNIT_HERO_TKH_', '').replace('_PORTRAIT', '')
    #     file_name = '_'.join([p.capitalize() for p in lazy_pinyin(file_name)]).upper()
    #     old_path =  './icon_unit_portrait/' + os.sep + file
    #     new_path = './icon_unit_portrait/' + os.sep + 'ICON_UNIT_HERO_TKH_' + file_name + '_PORTRAIT'
    #     os.rename(old_path,new_path + '.png')

    # root = r'C:\Users\10704\PycharmProjects\PythonProject\civ6\save_images'  # 保存地址


    images = get_dir_images('./icon_unit_portrait/')
    concatenated_image_horizontal = Image.new("RGBA", (3000, 300*(len(images)//10+1)), (0,0,0,0))

    index = 0
    row_index = 0
    for image in images:
        if index%10 == 0:
            row_index += 1

        weight = (index%10)*300
        height = (row_index-1)*300

        concatenated_image_horizontal.paste(image, (weight, height))
        index += 1
    concatenated_image_horizontal.save('ICON_TKH_UNIT.png')
