import openpyxl
import pandas as pd

from Toolkits.tool_funcs import cal_len
from arkham.DataManager import DataManager

tags = {
    'permanent':'永久',
    'exceptional': '卓越',
    'myriad': '无数',
    'is_unique': '唯一',
}

need_tags = {
    'pack_code':'拓展代码',
    'pack_name': '拓展包名',
    'type_name': '类型',
    'faction_name': '职阶',
    'position': 'position',
    'code':'code',
    'name': '卡名',
    'text': '描述',
    'quantity': 'quantity',
    'traits': '特质',
    'slot': '槽位',
    'cost': '花费',
    'xp': '经验',
    'subtype_name': 'subtype_name',
    'customization_text':'customization_text',
}

faction_names = ['求生者', '潜修者', '守卫者', '流浪者', '探求者', '中立']

faction_colors = {
    'Sheet1':'000000',
    '求生者': 'f3d4d5',
    '潜修者': 'd5caeb',
    '守卫者': 'd3e4f9',
    '流浪者': '509f16',
    '探求者': 'fde7d7',
    '中立': '808080',
    '本表': 'ffffff'
}

data_manager = DataManager()

def data_process(cards):
    new_cards = {}
    packs = data_manager.get_packs()
    for i in range(len(cards)):
        card = cards[i]
        if card['pack_code'] == 'core':
            continue
        new_card = {}
        extra_tags = []
        factions = [card['faction_name']]
        for key in card:
            if key in tags and card[key]:
                extra_tags.append(tags[key])
                if key == 'exceptional' and 'xp' in card:
                    card['xp'] = card['xp'] * 2
            if key in need_tags:
                new_card[need_tags[key]] = card[key]
        if 'subname' in card:
            new_card['卡名'] = '：'.join([card['name'], card['subname']])
        if '经验' in new_card:
            new_card['卡名'] = '{}({})'.format(new_card['卡名'], new_card['经验'])
        if 'faction3_name' in card and card['faction3_name'] != '':
            factions.append(card['faction3_name'])
        if 'faction2_name' in card and card['faction2_name'] != '':
            factions.append(card['faction2_name'])

        new_card['职阶'] = '. '.join(factions)
        new_card['额外标签'] = '. '.join(extra_tags)
        # new_cards.append(new_card)
        new_card['pack_id'] = -1
        if packs:
            for pack in packs:
                if new_card['拓展代码'] == pack['code']:
                    new_card['pack_id'] = pack['id']
                    break

        new_cards[new_card['卡名']+new_card['职阶']] = new_card

    return new_cards.values()

def convert_data2excel(data):

    with pd.ExcelWriter('cardsData.xlsx') as writer:
        df = pd.DataFrame(data)
        df.sort_values(by=['pack_id', '职阶', '类型', '经验', '槽位', '花费', '特质'], ascending=[True, True, True, True, True, True, False],
                               inplace=True)
        df.to_excel(writer, sheet_name='本表', index=False, header=True)
        for faction in faction_names:
            faction_cards = []
            for card in data:
                if faction in card['职阶']:
                    if card['类型'] != '调查员':
                        faction_cards.append(card)
            df_faction = pd.DataFrame(faction_cards)
            df_faction.sort_values(by=['类型', '经验', '槽位', '花费', '特质'], ascending=[False, True, True, True, False], inplace=True)
            start_index = (faction_names.index(faction))*500+1
            df_faction['序号'] = range(start_index, len(df_faction) + start_index)
            df_faction.to_excel(writer, sheet_name=faction, index=False, header=True)

def excel_process(file_path):
    wb = openpyxl.load_workbook(file_path)
    sheets = wb.sheetnames
    for sheet_name in sheets:
        sheet = wb[sheet_name]
        sheet.sheet_properties.tabColor = faction_colors[sheet_name]
        for i, col in enumerate(sheet.columns):
            max_lent = 0
            for cell in col:  # 查找最长单元格
                lent = cal_len(str(cell.value))
                if lent > max_lent:
                    max_lent = lent
            width = max_lent + 2  # 增加2个字符宽度，显示不会太紧凑
            c = col[0].column_letter
            sheet.column_dimensions[c].width = width
        hide_col = ['拓展包名', '拓展代码', '描述', 'customization_text', '职阶', 'position', 'quantity', '额外标签', 'pack_id']
        if sheet_name != '本表':
            for col in sheet.columns:
                if col[0].value in hide_col:
                    column_index = col[0].column_letter
                    sheet.column_dimensions[column_index].hidden = True
    wb.save(file_path)


if __name__ == '__main__':


    # with open('cards_data.json', 'r', encoding='UTF-8') as f:
    #     cards_data = json.load(f)
    # convert_data2excel(data_process(cards_data))
    # excel_process('cardsData.xlsx')

    # get_json()


    pass
