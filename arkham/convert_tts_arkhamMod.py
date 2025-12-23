import json
from concurrent.futures import ThreadPoolExecutor

from Toolkits.tool_funcs import convert_obj_zhHans
from arkham.DataManager import DataManager

replace_text = '\"FrontName\": \"{f_name}\",\n  \"BackName\": \"{b_name}\",\n  \"id\"'

num_threads = 500000

card_zh_datas = {}
card_en_datas = {}
card_urls = []
error_cards = {}


def get_card_data(c_id):
    data_manager = DataManager()

    card_data = data_manager.get_card(c_id)
    if card_data:
        card_data = convert_obj_zhHans(card_data)
        card_zh_datas[c_id] = card_data
    else:
        card_data = data_manager.get_card(c_id)
        if card_data:
            card_en_datas[c_id] = card_data


def get_note_json(note: str):
    formatted_note = note.replace(' ', '').replace('\n', '')
    try:
        return json.loads(formatted_note)
    except:
        return {}


def card_node_process(node):
    if isinstance(node, dict):
        if 'Nickname' in node and 'GMNotes' in node:
            note_json = get_note_json(node['GMNotes'])
            gm_note = node['GMNotes']
            if 'id' in note_json:
                card_id = note_json['id']
                if card_id not in card_zh_datas and card_id not in card_en_datas:
                    error_cards[card_id] = node['Nickname']
                else:
                    card_data = card_zh_datas[card_id]
                    if 'xp' in card_data and card_data['xp'] > 0:
                        card_data['name'] = r'{a}({b})'.format(a=card_data['name'], b=card_data['xp'])
                    if 'back_name' in card_data and card_data['back_name'] is not None:
                        node['GMNotes'] = gm_note.replace('\"id\"', replace_text.format(f_name=card_data['name'],
                                                                                        b_name=card_data['back_name']))
                        node['Nickname'] = card_data['back_name']
                    else:
                        node['Nickname'] = card_data['name']

        for value in node.values():
            card_node_process(value)

    elif isinstance(node, list):
        for child in node:
            card_node_process(child)


def save_card_datas():
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        future_to_url = {executor.submit(get_card_data, c_id): c_id for c_id in error_cards}
        for future in future_to_url:
            _ = future_to_url[future]


if __name__ == '__main__':

    with open('./data/base.json', 'r', encoding='utf-8') as f:
        base_json = json.load(f)

    with open('./data/zh_cards.json', 'r', encoding='utf-8') as f:
        cards_json = json.load(f)
    for card in cards_json:
        card_zh_datas[card['code']] = card

    card_node_process(base_json)
    with open('./data/Arkham.SCE.v4.4.1.json', 'w', encoding='UTF-8') as f:
        json.dump(base_json, f, indent=4, ensure_ascii=False)
