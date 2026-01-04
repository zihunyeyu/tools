import pandas as pd
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


df = pd.read_excel("hero_promotion_data.xlsx", keep_default_na=False)



index = 0
for i in df.values:
    _i = index - (index // 10)*10 + 1

    print(
        promotion_text.format(
            hero=i[0],
            x=1 if _i <= 5 else 3,
            y=_i if _i <= 5 else _i - 5,
            p_name=i[1],
            p_des=i[2]
        )
    )

    index += 1
