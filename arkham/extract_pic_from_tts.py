import json
import os.path
import re
import time

from PIL import Image

from Toolkits.tool_funcs import split_image
from arkham.convert_tts_arkhamMod import get_note_json

image_path = r"E:\steam\steamapps\common\Tabletop Simulator\Tabletop Simulator_Data\Mods\Images\{image_name}.jpg"

save_path = r"D:\ArkhamHorrorCardImagesTemp"
saved_image_dir = r"C:\Users\10704\ArkhamHorrorCardGame\asset\images\cards"
saved_dir = r"D:\temp"
saved_images = {}

card_images = {}
card_images_index = {}

error_cards = []

def get_deck_image(custom_deck: dict):
    image_file_name = None
    if custom_deck.keys().__sizeof__() > 0:
        deck_id, deck_dict = list(custom_deck.items())[0]
        # print(deck_id, deck_dict)
        image_file_name =  ''.join(re.findall("[a-zA-Z0-9]", deck_dict["FaceURL"]))

        if image_file_name in card_images:
            return image_file_name

        card_image_path = image_path.format(image_name=image_file_name)
        if os.path.exists(card_image_path):
            card_images[image_file_name] = {
                "ext": ".jpg",
                "rows": deck_dict["NumWidth"],
                "cols": deck_dict["NumHeight"],
                # "deck_id": deck_id,
            }
        elif os.path.exists(card_image_path.replace(".jpg", ".png")):
            card_images[image_file_name] = {
                "ext": ".png",
                "rows": deck_dict["NumWidth"],
                "cols": deck_dict["NumHeight"],
                # "deck_id": deck_id,
            }
        else:
            return None

    return image_file_name

def save_images(image_file_name, deck_info):
    images = split_image(deck_info["path"], deck_info["width"], deck_info["height"])
    for index, card_id in deck_info["cards"].items():
        if index < len(images):
            images[index].save(save_path.format(card_id=card_id), quality=95)

def image_process():
    files = [os.path.join(saved_image_dir, file) for file in os.listdir(saved_image_dir)]
    for file in files:
        image = Image.open(file)
        if image.size != (739, 1049):
            image.close()
            os.remove(file)

def save_tile(tile, path):
    tile.save(path)
    pass

def get_texture_offset():
    start_time = time.time()
    t_list = []
    for image_file_name, deck_info in card_images.items():
        image_file = image_path.replace("{image_name}.jpg", "") + image_file_name + deck_info["ext"]
        if os.path.exists(image_file):
            rows = deck_info['rows']
            cols = deck_info['cols']
            tiles = split_image(image_file, rows, cols)
            index = 0
            for tile in tiles:
                if index in deck_info["cardIndexes"]:
                    save_tile(tile, '\\'.join([saved_image_dir, '%s.png' % deck_info["cardIndexes"][index]]))

                #     t = threading.Thread(target=save_tile, args=(tile, '\\'.join([saved_image_dir, '%s.png' % deck_info["cardIndexes"][index]]),))
                #     t_list.append(t)
                #     t.start()
                index += 1
    # for t in t_list:
    #     t.join()
    # end_time = time.time()
    # print(f"多线程处理图片总耗时：{end_time - start_time} 秒")

def card_node_process(node):
    if isinstance(node, dict):
        if "GMNotes" in node and "CustomDeck" in node:
            if node["Name"] == "Card" or node["Name"] == "CardCustom":
                note_json = get_note_json(node["GMNotes"])
                if "id" in note_json and note_json["id"] not in saved_images:
                    card_id = note_json["id"]
                    image_file_name = get_deck_image(node["CustomDeck"])
                    if image_file_name:
                        card_image_index = int(str(node["CardID"])[-2:])
                        if not "cardIndexes" in card_images[image_file_name]:
                            card_images[image_file_name]["cardIndexes"] = {}
                        card_images[image_file_name]["cardIndexes"][card_image_index] = card_id

        for value in node.values():
            card_node_process(value)
    elif isinstance(node, list):
        for child in node:
            card_node_process(child)

def main():
    for file in os.listdir(saved_dir):
        saved_images[file.replace(".png", "")] = True

    with open('./data/base.json', 'r', encoding='utf-8') as f:
        base_json = json.load(f)

    # card_node_process(base_json)
    # pprint(card_images)
    # get_texture_offset()

    # with open('./data/zh_cards.json', 'r', encoding='utf-8') as f:
    #     zh_cards = json.load(f)
    #
    # for card in zh_cards:
    #     card_id = card["code"]
    #     if card_id in card_deck_index:
    #         card["card_image"] = card_deck_index[card_id]

    # with open('./data/zh_cards.json', 'w', encoding='UTF-8') as f:
    #     json.dump(zh_cards, f, indent=4, ensure_ascii=False)

    ## copy all files
    # for file in os.listdir(saved_dir):
    #     copyfile(saved_dir+"\\"+file, (saved_image_dir+"\\"+file))

if __name__ == "__main__":
    main()
