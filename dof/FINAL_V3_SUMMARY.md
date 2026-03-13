# 最终版 v3 - 跳过包含 weapon 的 equ 文件

## 核心功能

**只跳过 icon 路径包含 "weapon" 关键字的 equ 文件**

```python
def contains_weapon_keyword(icon_path: str) -> bool:
    return 'weapon' in icon_path.lower()

# 使用时
if contains_weapon_keyword(icon_path):
    logger.warning(f"跳过包含 weapon 的 equ: {path}")
    continue  # 跳过
```

## 处理逻辑

```
读取 equ 文件
    │
    ├─ 提取 [name]
    │   └─ 是英文+数字？→ 跳过
    │
    ├─ 提取 [icon] 路径
    │   └─ 包含 "weapon"？→ 跳过
    │
    └─ 提取 [hide equipment]
        │
        ▼
    更新 avatar_config.json
```

## 跳过示例

```
跳过包含 weapon 的 equ: equipment/character/swordmanavatar/cap/xxxx.equ
  Icon 路径: item/new_equipment/01_weapon/swordman/sswd.img

跳过包含 weapon 的 equ: equipment/character/fighteravatar/coat/yyyy.equ
  Icon 路径: item/equipment/weapon/fighter/knuckle.img
```

## 处理示例

```
处理: equipment/character/swordmanavatar/cap/zzzz.equ
  职业: swordman -> swordman_male
  部位: hat -> cap
  Name: 白色末日使者肩饰
  Frame: 328
  Icon 路径: item/avatar/swordman/sm_acap.img
  找到匹配: swordman_male/cap/10203
    更新: name: '' -> '白色末日使者肩饰'
    更新: frame: 0 -> 328
```

## 使用

```bash
python sync_equ_to_config_v3.py
```

## 文件列表

- `sync_equ_to_config_v3.py` - 主脚本（最终版）
- `test_weapon_skip.py` - 单元测试
- `FINAL_V3_SUMMARY.md` - 本文档
