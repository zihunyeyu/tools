
import xml.etree.ElementTree as ET

# 示例XML字符串
xml_string = '''
<Row>
    <ModifierId>MOD_BONUS_VS_WOUNDED_UNITS_ZHANGFEI</ModifierId>
    <Name>Amount</Name>
    <Value>15</Value>
</Row>
'''

# 解析XML字符串
root = ET.fromstring(xml_string)

# 将子元素转换为属性
dict_ = {}
for child in root:
    dict_[child.tag] = child.text


root.clear()
# 删除所有子元素

for key, value in dict_.items():
    root.set(key, value)


# 将修改后的XML转换为字符串
modified_xml = ET.tostring(root, encoding='utf-8').decode('utf-8')

print(modified_xml)