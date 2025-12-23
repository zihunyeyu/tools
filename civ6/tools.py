import xml.etree.ElementTree as ET

# tree = ET.parse('input.xml')
# root = tree.getroot()
#
# # 遍历所有<Row>节点
# for row in root.findall('.//Row'):
#     # 将子元素转换为属性
#     for child in row:
#         row.set(child.tag, child.text)
#     # 删除所有子元素
#     row.clear()
#
# # 保存修改后的XML文件
# tree.write('output.xml', encoding='utf-8', xml_declaration=True)


source_xml = 'Three_Kingdom_Heroes.xml'


source = ET.parse(source_xml)
source_root = source.getroot()

for child_s in source_root:
    print(child_s.tag, child_s.attrib)
    for child_row in child_s:
        dict_ = {}
        for child in child_row:
            dict_[child.tag] = child.text
        if dict_.keys().__len__() != 0:
            child_row.clear()
            for key, value in dict_.items():
                child_row.set(key, value)

source.write('output.xml', encoding='utf-8', xml_declaration=True)
