import glob
import os

from PIL import Image, ImageDraw
# from wand import image as dds_image
from pathlib import Path
import imageio.v2 as imageio

def read_dds_image(image_path):
    image_array = imageio.imread(image_path)
    image = Image.fromarray(image_array)
    return image



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
    Image_glob = os.path.join(dir_path, "*.png")
    Image_name_list = []

    Image_name_list.extend(glob.glob(Image_glob))
    _images = []
    for i in range(len(Image_name_list)):
        _image = apply_circle_mask(read_dds_image(dir_path+'{id}.png'.format(id=(i+1))))
        _images.append(_image)

    return _images

if __name__ == '__main__':
    # root = r'C:\Users\10704\PycharmProjects\PythonProject\civ6\save_images'  # 保存地址

    images = get_dir_images('./original_images/EX2/')
    # images.extend(get_dir_images('./original_images/EX2/'))
    concatenated_image_horizontal = Image.new("RGBA", (2200, 220*(len(images)//10+1)), (0,0,0,0))

    index = 0
    row_index = 0
    for image in images:
        if index%10 == 0:
            row_index += 1

        weight = (index%10)*220
        height = (row_index-1)*220

        concatenated_image_horizontal.paste(image, (weight, height))
        index += 1
    concatenated_image_horizontal.save('test.png')
