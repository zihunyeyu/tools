import json
import os.path
from pprint import pprint
from typing import Union

from Toolkits.tool_funcs import convert_obj_zhHans
from Toolkits.web_funcs import get_json


class DataManager:

    base_urls = {
        'en': r'https://arkhamdb.com',
        'zh': r'https://zh.arkhamdb.com',
    }

    apis = {
        'card': r'/api/public/card/{card_id}',
        'cards': r'/api/public/cards/?encounter=1',
        'packs': r'/api/public/packs',
    }

    def __init__(self, language='zh'):

        # print('Initializing...')

        self.language = language
        self.__init_data()

    def __init_data(self):
        self.cards_data = {}
        if os.path.exists(f'./data/{self.language}_cards.json'):
            with open(f'./data/{self.language}_cards.json', 'r', encoding='utf-8') as f:
                cards_data = json.load(f)
        else:
            card_url = self.base_urls[self.language] + self.apis['cards']
            cards_data = get_json(card_url)
        for card in cards_data:
            self.cards_data[card['code']] = card

        if os.path.exists(f'./data/{self.language}_packs.json'):
            with open(f'./data/{self.language}_packs.json', 'r', encoding='utf-8') as f:
                self.packs_data = json.load(f)
        else:
            pack_url = self.base_urls[self.language]+self.apis['packs']
            self.packs_data = get_json(pack_url)

        with open(f'./data/{self.language}_packs.json', 'w', encoding='utf-8') as f:
            json.dump(convert_obj_zhHans(self.packs_data), f, ensure_ascii=False, indent=4)
        with open(f'./data/{self.language}_cards.json', 'w', encoding='utf-8') as f:
            json.dump(convert_obj_zhHans(cards_data), f, ensure_ascii=False, indent=4)

    def get_card(self, card_id):
        if card_id in self.cards_data:
            return self.cards_data[card_id]
        else:
            card_url = self.base_urls[self.language]+self.apis['card'].format(card_id=card_id)
            return get_json(card_url)

    def get_cards(self):
        return self.cards_data

    def get_packs(self):
        return self.packs_data

    def get_packs_by_cycle(self, cycle_position: int):
        cycle_pack = []
        for pack in self.packs_data:
            if pack['cycle_position'] == cycle_position:
                cycle_pack.append(pack['id'])
        return cycle_pack

    def get_pack_by_name(self, name: str):
        for pack in self.packs_data:
            if pack['name'] == name:
                return pack
        return None

    def get_pack_by_id(self, pack_id: int):
        for pack in self.packs_data:
            if pack['id'] == pack_id:
                return pack
        return None


class Pack:
    def __init__(self, param: Union[str, int], data: DataManager):

        self.dataManager = data

        if isinstance(param, str):
            self.name = param
            self._init_by_name()
        elif isinstance(param, int):
            self.id = param
            self._init_by_id()
        else:
            raise TypeError

        self.name = None
        self.id = None
        self.code = None
        self.total = None
        self.url = None
        self.cycle_position = None
        self.mainPack = self

        self._init_pack()
        self._get_main_pack()

    def _init_by_name(self):
        self.pack = self.dataManager.get_pack_by_name(self.name)

    def _init_by_id(self):
        self.pack = self.dataManager.get_pack_by_id(self.id)

    def _get_main_pack(self):
        if self.cycle_position:
            packs = self.dataManager.get_packs_by_cycle(self.cycle_position)
            if len(packs) >= 1:
                self.mainPack = packs[0]

    def _init_pack(self):
        pack = self.pack
        if pack:
            self.name = pack['name']
            self.id = pack['id']
            self.code = pack['code']
            self.total = pack['total']
            self.url = pack['url']
            self.cycle_position = pack['cycle_position']

    def __str__(self):
        return f'{self.cycle_position-1}循环《{Pack(self.mainPack, self.dataManager).name}》：《{self.name}》'

if __name__ == '__main__':
    manager = DataManager()
    # for pack in manager.get_packs():
    #     print(Pack(pack['id'], manager))
    # pack = Pack(9, manager)
