import xml.etree.ElementTree as ET

tree = ET.parse('TKH_Text.xml')
root = tree.getroot()

with open('text.sql', 'w', encoding='utf-8') as f:
    for i in root:
            # print(i.tag, i.attrib)
            for j in i:
                f.write(f"('{j.attrib['Language']}', '{j.attrib['Tag']}', '{j.find('Text').text.strip()}')," + '\n')
