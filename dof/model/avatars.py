# 时装层级



layer_dict = {
    'coat_f': 2850,
    'neck_f': 2840,
    'face_f': 2830,
    'cap_f': 2810,
    'belt_e': 2800,  # 注意：原文本中是blet_e，可能是belt_e的笔误
    'neck_e': 2780,
    'neck_ef': 2751,
    'face_g': 2750,
    'face_a': 2700,
    'cap_c': 2500,
    'hair_c': 2400,
    'coat_c': 2300,
    'neck_g': 2251,
    'neck_cf': 2201,
    'neck_c': 2200,
    'cap_g': 2125,
    'cap_a': 2100,
    'hair_a': 2000,
    'neck_xf': 1980,
    'neck_x': 1975,
    'neck_z': 1963,
    'coat_x': 1960,
    'belt_f': 1952,
    'belt_g': 1951,
    'belt_c': 1950,
    'belt_c1': 1949,
    'face_c': 1925,
    'neck_a': 1900,
    'coat_g': 1850,
    'coat_a': 1800,
    'belt_a': 1700,
    'pants_f': 1651,
    'pants_c': 1650,
    'shoes_f': 1601,
    'shoes_c': 1600,
    'pants_g': 1501,
    'pants_a': 1500,
    'shoes_g': 1450,
    'shoes_a': 1400,
    'pants_b': 1300,
    'shoes_h': 1201,
    'shoes_b': 1200,
    'shoes_d': 1190,
    'pants_h': 1151,
    'pants_d': 1150,
    'belt_b': 1100,
    'neck_bf': 1050,
    'neck_b': 1000,
    'coat_h': 925,
    'coat_b': 900,
    'belt_h': 851,
    'belt_d': 850,
    'belt_d1': 849,
    'hair_b': 800,
    'cap_h': 750,
    'cap_b': 700,
    'neck_df': 650,
    'neck_d': 600,
    'neck_h': 550,
    'coat_d': 500,
    'hair_d': 400,
    'cap_d': 300,
    'neck_kf': 291,
    'neck_k': 290,
    'face_h': 270,
    'face_b': 100,
    'hair_f1': 20
}

LAYER_STRING = r'''[layer variation]
	{layer_index}
	`{layer}`

[equipment ani script]
	`equipment/character/{job}.lay`'''

EQU_ANIMATION_STRING = r'''[animation job]
	`[{job}]`

[variation]
	{code}	{index}'''

EQU_TEMP = r'''#PVF_File

[name]
	`{equ_code}`

[enable dye]
	1	0

[grade]
	2

[part set index]
	2

[usable job]
	`[{job}]`
[/usable job]

[attach type]
	`[trade]`

[minimum level]
	1

[icon]
	`item/avatar/fighter/ft_abelt.img`	227

[equipment type]
	`[{equ_part} avatar]`	0

[avatar type select]
	7	0	0	400	0
	30	0	0	800	0
	0	0	0	1600	0
	0	0	0	1800	2
	`[D socket]`	`[D socket]`
[/avatar type select]

[avatar select ability]
	`[ELEMENT_TOLERANCE_FIRE]`	`+`	25
	`[ELEMENT_TOLERANCE_WATER]`	`+`	25
	`[ELEMENT_TOLERANCE_DARK]`	`+`	25
	`[ELEMENT_TOLERANCE_LIGHT]`	`+`	25
	`[ACTIVESTATUS_TOLERANCE_STUCK]`	`+`	40
	`[INVENTORY_MAX_WEIGHT]`	`+`	9000
[/avatar select ability]

{animation_job}

{layer_variation}



[move wav]
	`CLOTH_TOUCH`
'''
