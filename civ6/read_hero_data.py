import pandas as pd
from fontTools.ttLib.tables.G__l_o_c import Gloc_header
from pypinyin import lazy_pinyin



promotion_text = r'''<Replace Tag="LOC_PROMOTION_TK_{hero}_{x}_{y}_NAME" Language="zh_Hans_CN">
			<Text>
				{p_name}
			</Text>
		</Replace>
		<Replace Tag="LOC_PROMOTION_TK_{hero}_{x}_{y}_DESCRIPTION" Language="zh_Hans_CN">
			<Text>
				{p_des}
			</Text>
		</Replace>'''

promotion_modifier = "('PROMOTION_TK_{hero}_{x}_{y}', 'MODIFIER_PROMOTION_TK_{hero}_{x}_{y}'),"

# peomoted_modifier_text = "('PROMOTION_TK_{hero}_{x}_{y}',	'Preview',	'+{1_Amount} {LOC_PROMOTION_AMBUSH_NAME} {LOC_PROMOTION_DESCRIPTOR_PREVIEW_TEXT}'),"

text_database_header = r'''
INSERT OR REPLACE INTO LocalizedText(Language, Tag, Text)
VALUES
'''

# aoe_ability_modifier = r'''('MODIFIER_PROMOTION_TK_{hero}_{x}_{y}',      'MODIFIER_ALL_UNITS_GRANT_ABILITY',                     'AOE5_REQUIREMENTS'),'''
# aoe_ability_argument = r'''('MODIFIER_PROMOTION_TK_{hero}_{x}_{y}',      'AbilityType',  'ABILITY_MODIFIER_PROMOTION_TK_{hero}_{x}_{y}'),'''
# aoe_ability_type = r'''('ABILITY_MODIFIER_PROMOTION_TK_{hero}_{x}_{y}',	'KIND_ABILITY'),'''
# aoe_ability_typeTag = r'''('ABILITY_MODIFIER_PROMOTION_TK_{hero}_{x}_{y}',	'CLASS_UNIT_HERO_TKH_{hero}'),'''
# aoe_ability = r'''('ABILITY_MODIFIER_PROMOTION_TK_{hero}_{x}_{y}',	null,	'LOC_PROMOTION_TK_{hero}_{x}_{y}_DESCRIPTION',	1,	0),'''
# ability_modifier = r'''('ABILITY_MODIFIER_PROMOTION_TK_{hero}_{x}_{y}',	'MOD_ABILITY_MODIFIER_PROMOTION_TK_{hero}_{x}_{y}'),'''



ability_modifier = r'''('ABILITY_TK_S_HERO_SKILL_{hero}_{skill_index}',	'MOD_ABILITY_TK_S_HERO_SKILL_{hero}_{skill_index}'),'''
aoe_ability_modifier = r'''('MOD_ABILITY_TK_S_HERO_SKILL_{hero}_{skill_index}',      'MODIFIER_ALL_UNITS_GRANT_ABILITY',                     'AOE5_REQUIREMENTS'),'''
aoe_ability_argument = r'''('MOD_ABILITY_TK_S_HERO_SKILL_{hero}_{skill_index}',      'AbilityType',  'ABILITY_MOD_ABILITY_TK_S_HERO_SKILL_{hero}_{skill_index}'),'''

s_hero_skill_ability = r'''('ABILITY_MOD_ABILITY_TK_S_HERO_SKILL_{hero}_{skill_index}',	'KIND_ABILITY'),'''
s_hero_skill_tag = r'''('ABILITY_MOD_ABILITY_TK_S_HERO_SKILL_{hero}_{skill_index}',	'CLASS_UNIT_HERO_TKH_{hero}'),'''
s_hero_skill_text = r'''('ABILITY_MOD_ABILITY_TK_S_HERO_SKILL_{hero}_{skill_index}',	null,	'LOC_ABILITY_TK_S_HERO_SKILL_{hero}_{skill_index}_DESCRIPTION',	0,	0),'''
s_hero_skill_modifier = r'''('ABILITY_MOD_ABILITY_TK_S_HERO_SKILL_{hero}_{skill_index}',	'{modifier}'),'''

def write_aoe_ability_modifier(df, p=4):
    with open('TKH_PROMOTED_MODIFIER_AOE_ABILITY.sql', 'w', encoding='UTF-8') as file:
        # for _str in [aoe_ability_modifier, aoe_ability_argument, aoe_ability_type, aoe_ability_typeTag, aoe_ability,
        #              ability_modifier]:
        # for _str in [s_hero_skill_ability, s_hero_skill_tag, s_hero_skill_text, s_hero_skill_modifier]:
        index = 0
        for i in df.values:
            hero = '_'.join([p.capitalize() for p in lazy_pinyin(i[1])]).upper()
            # if i[2] != '':
            file.write(f"('zh_Hans_CN', 'LOC_ABILITY_TK_S_HERO_SKILL_{hero}_{index - (index // 8)*8 + 1}_NAME', '{i[2]}'),\n")
            file.write(f"('zh_Hans_CN', 'LOC_ABILITY_TK_S_HERO_SKILL_{hero}_{index - (index // 8) * 8 + 1}_DESCRIPTION', '{i[4]}'),\n")
            # if i[2] == 'AOE':

                # modifiers = i[2].split(',')
                # for i_ in range(len(modifiers)):
                #     file.write(_str.format(hero=hero, modifier=modifiers[i_],skill_index=index - (index // 8)*8 + 1))
                #     file.write('\n')
            index += 1
        file.write('\n\n\n')

def write_promoted_text(df):
    with open('TKH_HeroText.sql', 'w', encoding='UTF-8') as file:
        file.write(text_database_header)
        index = 0
        for i in df.values:
            _i = index - (index // 10) * 10 + 1
            hero = i[0]
            x = 1 if _i <= 5 else 3
            y = _i if _i <= 5 else _i - 5
            p_name = i[1]
            p_des = i[3]
            promotion_name_tag = f"LOC_PROMOTION_TK_{hero}_{x}_{y}_NAME"
            promotion_des_tag = f"LOC_PROMOTION_TK_{hero}_{x}_{y}_DESCRIPTION"
            file.write(f"('zh_Hans_CN', '{promotion_name_tag}', '{p_name}'),\n")
            file.write(f"('zh_Hans_CN', '{promotion_des_tag}', '{p_des}'),\n")
            index += 1

# with open('TKH_HeroText.sql', 'w', encoding='UTF-8') as file:
#     index = 0
#     for i in df.values:
#         _i = index - (index // 10)*10 + 1
#         hero = i[0]
#         x = 1 if _i <= 5 else 3
#         y = _i if _i <= 5 else _i - 5
#         p_name = i[1]
#         p_des=i[3]
#         if i[2] not in ['', 'CUSTOM', 'ARMOR']:
#             modifiers = i[2].split(',')
#             for modifier in modifiers:
#                 file.write(f"('PROMOTION_TK_{hero}_{x}_{y}', '{modifier}'),\n")
#
#
#         index += 1

if __name__ == '__main__':
    df = pd.read_excel("hero_promotion_data.xlsx", keep_default_na=False)
    # write_aoe_ability_modifier(df)

    combat_types = {'ATTACK_': '攻击{target}单位',
                    'DEFEND_': '防御{target}单位攻击',
                    'COMBAT_': '与{target}单位战斗'}
    combat_targets = ['CLASS_ANTI_CAVALRY', 'CLASS_RANGED',
                      'CLASS_MELEE', 'CLASS_TKH_CAVALRY',
                      'CLASS_TKH_HERO', 'CLASS_SIEGE',
                      'CLASS_WARRIOR_MONK', 'CLASS_RECON']

    combat_targets_ZH = ['抗骑兵', '远程', '近战', '骑兵', '英雄', '攻城', '武僧', '侦察']

    modifier_string = r'''INSERT OR REPLACE INTO ModifierStrings(ModifierId,	Context,	Text)
SELECT mod.ModifierId, 'Preview', '{loc}'
FROM Modifiers mod JOIN ModifierArguments arg
ON mod.ModifierId = arg.ModifierId
AND mod.ModifierType = 'MODIFIER_UNIT_ADJUST_COMBAT_STRENGTH' 
AND mod.SubjectRequirementSetId = '{req}'
AND mod.OwnerRequirementSetId IS NULL
AND arg.Name = 'Amount'
AND mod.ModifierId NOT IN (SELECT ModifierId FROM ModifierStrings);


'''

    for combat_type, loc_header in combat_types.items():
        # print(combat_type, loc_header)
        for i in range(len(combat_targets)):
            # print(combat_targets[i], combat_targets_ZH[i])
            req = f'REQS_TKH_{combat_type if combat_type != 'COMBAT_' else ''}TAG_IS_{combat_targets[i]}'

            loc_zh = loc_header.format(target=combat_targets_ZH[i]) + '时+uuu [ICON_Strength] 战斗力'
            # print(req, loc)
            loc = f"('zh_Hans_CN', '{f'LOC_TKH_MOD_STRING_{combat_type}MINUS_{combat_targets[i]}'}', '{loc_zh}'),"
            print(loc)


    # write_promoted_text(df)
    # with open('TKH_HeroText.sql', 'w', encoding='UTF-8') as file:
    #     index = 0
    #     s_heroes = []
    #     for i in df.values:
    #         _i = index - (index // 8)*8 + 1
    #         hero_name = '_'.join([p.capitalize() for p in lazy_pinyin(i[0])]).upper()
