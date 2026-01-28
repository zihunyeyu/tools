import pandas as pd
from pypinyin import lazy_pinyin

# -- ('EQUIPMENT_FangTianHuaJi', 'EQUIPMENT_WEAPON', 'LV_BU', 0, 20, NULL, NULL, 1, 9000, 0, 0, 0),
equipment_sql = "('{e_name}', '{e_type}', '{e_hero}', 0, 20, NULL, NULL, 1, 9000, {e_armor}, 0, 0),"
equipment_ab_modifier = "('ABILITY_TKH_{e_name}',\t\t\t\t'MODIFIER_{e_name}'),"
ab_modifier = "('MODIFIER_{e_name}',\t\t\t'{m_type}',\t\t\t{req}),"
ab_modifier_arguments = "('MODIFIER_{e_name}',        	'Amount',   {arg}),"

icon = '<Row Name="ICON_{e_name}" Atlas="ATLAS_ICON_EQUIPMENTS_EX2" Index="{index}" />'


df_equ = pd.read_excel("TKH_DATA.xlsx", keep_default_na=False, sheet_name='equ')
df_equ_sql = pd.read_excel("TKH_DATA.xlsx", keep_default_na=False, sheet_name='equ_sql')
df_suit = pd.read_excel("TKH_DATA.xlsx", keep_default_na=False, sheet_name='suit')


# for i in df.values:
#     Equipment = 'EQUIPMENT_' + ''.join([p.capitalize() for p in lazy_pinyin(i[1])])

aoe_ability_modifier = r'''('MODIFIER_ALL_UNITS_GRANT_ABILITY',                     'MODIFIER_ABILITY_TKH_{suit}{suit_num}',      'AOE5_REQUIREMENTS'),'''
aoe_ability_argument = r'''('AbilityType', 'MODIFIER_ABILITY_TKH_{suit}{suit_num}',  'ABILITY_MODIFIER_ABILITY_TKH_{suit}{suit_num}'),'''
aoe_ability_type = r'''('ABILITY_MODIFIER_ABILITY_TKH_{suit}{suit_num}',	'KIND_ABILITY'),'''
aoe_ability_typeTag = r'''('ABILITY_MODIFIER_ABILITY_TKH_{suit}{suit_num}',	'CLASS_UNIT_HERO_TKH_'),'''
aoe_ability = r'''('ABILITY_MODIFIER_ABILITY_TKH_{suit}{suit_num}',	null,	'LOC_ABILITY_MODIFIER_ABILITY_TKH_{suit}{suit_num}_DESCRIPTION',	1,	0),'''
# ability_modifier = r'''('ABILITY_MODIFIER_PROMOTION_TK_{hero}_{x}_{y}',	'MOD_ABILITY_MODIFIER_PROMOTION_TK_{hero}_{x}_{y}'),'''

aoe = r'''('ABILITY_TKH_{suit}{suit_num}',	'MODIFIER_ABILITY_TKH_{suit}{suit_num}'),'''


for i in df_suit.values:
    suit_3 = f"LOC_{i[0]}_DESCRIPTION3"
    suit_4 = f"LOC_{i[0]}_DESCRIPTION4"

    print(f"('zh_Hans_CN',	'{suit_3}',	'{i[2]}'),")
    print(f"('zh_Hans_CN',	'{suit_4}',	'{i[4]}'),")



    

# for equ in df_equ.values:
#     Equipment = 'EQUIPMENT_' + ''.join([p.capitalize() for p in lazy_pinyin(equ[1])])
#     index = 0
#     for equ_sql in df_equ_sql.values:
#
#         if Equipment  == equ_sql[0] and equ[7] != '':
#             # equ_sql[-2] = equ[7]
#             df_equ_sql.loc[index, 16] = equ[7]
#         index += 1
#
# df_equ_sql.to_excel("text.xlsx", sheet_name='equ_sql')