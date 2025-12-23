import json
from pprint import pprint

from arkham.DataManager import DataManager
from arkham.convert_tts_arkhamMod import get_note_json
from arkham.main import data_manager

with open(f'./data/zh_cards.json', 'r', encoding='utf-8') as f:
    zh_cards = json.load(f)

# def card_node_process(node):
#     if isinstance(node, dict):
#         if "GMNotes" in node and "CustomDeck" in node:
#             if node["Name"] == "Card" or node["Name"] == "CardCustom":
#                 note_json = get_note_json(node["GMNotes"])
#                 if "id" in note_json and "alternate_ids" in note_json:
#                     card_id = note_json["id"]
#                     print(card_id, )
#                     for alter_card_id in note_json["alternate_ids"]:
#                         if card_id in zh_cards and alter_card_id in zh_cards:
#                             zh_cards[alter_card_id]["alternate_id"] = card_id
#
#         for value in node.values():
#             card_node_process(value)
#     elif isinstance(node, list):
#         for child in node:
#             card_node_process(child)



def main():
    # with open('./data/base.json', 'r', encoding='utf-8') as f:
    #     base_json = json.load(f)
    # card_node_process(base_json)
    #
    # with open(f'./data/zh_cards.json', 'w', encoding='utf-8') as f:
    #     json.dump(zh_cards, f, ensure_ascii=False, indent=4)

    data_manager = DataManager()

if __name__ == "__main__":
    main()