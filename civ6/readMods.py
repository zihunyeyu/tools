import json
import xml.etree.ElementTree as ET

def read_mod():
    mods = []
    with open("test.ini", 'r', encoding='utf-8') as file:
        mod = {}
        for line in file.readlines():
            line = line.replace('\n', '')
            if line != '==============================================':
                key, value = line.split('@')
                mod[key]=  value
            else:
                mods.append(mod)
                mod = {}
    dependency = '<Dependency type="{type}" title="{title}" id="{_id}" />'

    mod_strings = {}
    for mod in mods:
        if mod['Official'] == 'false':
            _type = 'Mod'
            mod_string = dependency.format(type=_type, title=mod['Name'], _id=mod['Id'])
            mod_strings[mod['Id']] = mod_string
    for mod_string in mod_strings.values():
        print(mod_string)

def read_civ6proj():
    tree = ET.parse('ThreeKingdomHeroPack.civ6proj')
    root = tree.getroot()
    for child in root:
        print('Tag:', child.tag)
        print('Text:', child.text)
        print('Attributes:', child.attrib)

if __name__ == '__main__':
    read_mod()
    # read_civ6proj()