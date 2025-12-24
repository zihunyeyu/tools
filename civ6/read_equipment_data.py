import pandas as pd
import numpy as np
from pypinyin import pinyin, lazy_pinyin, Style

# -- ('EQUIPMENT_FangTianHuaJi', 'EQUIPMENT_WEAPON', 'LV_BU', 0, 20, NULL, NULL, 1, 9000, 0, 0, 0),
e = "('{e_name}', '{e_type}', '{e_hero}', 0, 20, NULL, NULL, 1, 9000, 0, 0, 0),"
icon = '<Row Name="ICON_{e_name}" Atlas="ATLAS_ICON_EQUIPMENTS" Index="{index}" />'

df = pd.read_excel("equipmentData2.xlsx")

# df.index.values，获取行索引向量，返回类型为ndarray（一维）；
# df.columns.values

# print(len(df.values))
# print(df.values[0])
index = 0
for i in df.values:
    E_NAME = 'EQUIPMENT_' + ''.join([p.capitalize() for p in lazy_pinyin(i[1])])
    print(e.format(e_name=E_NAME, e_type=i[3], e_hero=i[4]))
    # print(icon.format(e_name=E_NAME, index=index))
    # index += 1