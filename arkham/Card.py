from pprint import pprint

from Toolkits.tool_funcs import convert_obj_zhHans
from arkham.DataManager import DataManager

test_data = {
        "pack_code": "tmm",
        "pack_name": "The Miskatonic Museum",
        "type_code": "event",
        "type_name": "Event",
        "faction_code": "seeker",
        "faction_name": "Seeker",
        "position": 107,
        "exceptional": False,
        "myriad": False,
        "code": "02107",
        "name": "\"我有个计划！\"",
        "real_name": "\"I've got a plan!\"",
        "cost": 3,
        "text": "<b>攻击</b>。这次攻击使用[intellect]代替[combat]。你每持有1个线索，这次攻击造成+1伤害(最大+3伤害)。",
        "real_text": "<b>Fight</b>. This attack uses [intellect]. You deal +1 damage for this attack for each clue you have (max +3 damage).",
        "quantity": 2,
        "skill_intellect": 1,
        "skill_combat": 1,
        "xp": 0,
        "health_per_investigator": False,
        "deck_limit": 2,
        "real_slot": "",
        "traits": "洞察. 策略",
        "real_traits": "Insight. Tactic.",
        "flavor": "\"这应该是我听过最烂的计划了。好吧，那还磨蹭什么？快动手吧！\"",
        "illustrator": "Robert Laskey",
        "is_unique": False,
        "permanent": False,
        "double_sided": False,
        "octgn_id": "04f8c0c9-800a-4665-b39b-e1e206a390c6",
        "url": "https://zh.arkhamdb.com/card/02107",
        "imagesrc": "/bundles/cards/02107.png"
    }

data_manager = DataManager()

class Card:
        def __init__(self, card_id):
                self.id = card_id
                self.data = convert_obj_zhHans(data_manager.get_card(card_id))
                self._ana_data()
        def _ana_data(self):
                pprint(self.data)
                self.name = self.data["name"]
                self.faction = self.data["faction_code"]

                if 'alternated_by' in self.data:
                        self.alternated_cards = []
                        for _aCardCode in self.data["alternated_by"]:
                                self.alternated_cards.append(Card(_aCardCode))

        def __str__(self):
                return self.name

if __name__ == "__main__":
        card = Card('90030')



