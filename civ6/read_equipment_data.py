import numpy
import pandas as pd
import numpy as np
from pypinyin import pinyin, lazy_pinyin, Style

# -- ('EQUIPMENT_FangTianHuaJi', 'EQUIPMENT_WEAPON', 'LV_BU', 0, 20, NULL, NULL, 1, 9000, 0, 0, 0),
equipment_sql = "('{e_name}', '{e_type}', '{e_hero}', 0, 20, NULL, NULL, 1, 9000, {e_armor}, 0, 0),"

icon = '<Row Name="ICON_{e_name}" Atlas="ATLAS_ICON_EQUIPMENTS_EX2" Index="{index}" />'

e_text = r'''<Replace Tag="LOC_{equipment}_NAME" Language="zh_Hans_CN">
			<Text>
				{e_name}
			</Text>
		</Replace>
		<Replace Tag="LOC_{equipment}_DESCRIPTION" Language="zh_Hans_CN">
			<Text>
				{e_name}：{e_des}
			</Text>
		</Replace>'''

df = pd.read_excel("equipmentData2.xlsx", keep_default_na=False)

# df.index.values，获取行索引向量，返回类型为ndarray（一维）；
# df.columns.values

# print(len(df.values))
# print(df.values[0])
index = 0
for i in df.values:
    Equipment = 'EQUIPMENT_' + ''.join([p.capitalize() for p in lazy_pinyin(i[1])])
    # print(i[3] == '')
    # print(equipment_sql.format(e_name=Equipment, e_type=i[4], e_hero=i[5], e_armor=0 if i[3] == '' else i[3]))

    # print(icon.format(e_name=Equipment, index=index))
    # index += 1

    print(e_text.format(
        equipment = Equipment,
        e_name = i[1],
        e_des = i[2]
    ))

