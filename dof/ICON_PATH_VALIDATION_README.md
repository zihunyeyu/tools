# Icon 路径验证功能说明 (v2)

## 问题背景

从 PVF equ 文件中读取的 `[icon]` 路径可能与当前部位不匹配，例如：

```ini
[icon]
	`item/new_equipment/01_weapon/swordman/sswd/sswd.img`	141
```

这是武器图标路径，但当前部位是 `cap`（头饰），两者不匹配。

## 解决方案

脚本 v2 版本添加了 icon 路径验证功能：

1. **提取**：从 equ 文件读取 `[icon]` 标签的路径和 frame
2. **验证**：检查路径是否是有效的时装路径
3. **替换**：如果无效，使用标准生成的时装路径
4. **保留**：始终保留 frame（图标索引）

## 验证规则

### 无效路径特征
- 包含 `weapon` 关键字
- 包含武器类型（`sswd`, `swd`, `katana`, `club` 等）
- 不在 `item/avatar/` 目录下

### 有效路径特征
- 包含 `item/avatar/`
- 路径中包含部位标识（`cap`, `coat`, `hair` 等）

## 路径映射

### 职业映射
| equ career | job_name | icon 路径示例 |
|-----------|----------|--------------|
| swordman | sm | item/avatar/swordman/sm_***.img |
| fighter | ft | item/avatar/fighter/ft_***.img |
| at fighter | fm | item/avatar/atfighter/fm_***.img |
| gunner | gn | item/avatar/gunner/gn_***.img |
| at gunner | gg | item/avatar/atgunner/gg_***.img |
| mage | mg | item/avatar/mage/mg_***.img |
| at mage | mm | item/avatar/atmage/mm_***.img |
| priest | pr | item/avatar/priest/pr_***.img |
| thief | th | item/avatar/thief/tf_***.img |

### 部位映射
| part | icon 文件名 |
|------|------------|
| cap | acap |
| hair | ahair |
| face | aface |
| neck | aneck |
| coat | acoat |
| pants | apants |
| belt | abelt |
| shoes | ashoes |
| skin | abody |

### 标准路径格式
```
item/avatar/{职业路径}/{职业前缀}_{部位图标}.img

例如：
- item/avatar/swordman/sm_acap.img
- item/avatar/fighter/ft_ahair.img
- item/avatar/atfighter/fm_acoat.img
```

## 使用示例

### 输入 equ 文件

```ini
[name]
	`白色末日使者肩饰`

[icon]
	`item/new_equipment/01_weapon/swordman/sswd/sswd.img`	328

[equipment type]
	`[hat avatar]`
```

### 处理结果

```
处理: equipment/character/swordmanavatar/cap/60150001.equ
  职业: swordman -> swordman_male
  部位: hat -> cap
  Name: 白色末日使者肩饰
  Frame: 328
  Icon 路径: item/new_equipment/01_weapon/swordman/sswd/sswd.img
  Icon 有效: ✗ (将使用: item/avatar/swordman/sm_acap.img)
  ...
  找到匹配: swordman_male/cap/10203
    更新: frame: 0 -> 328
    更新: icon_path: '' -> 'item/avatar/swordman/sm_acap.img'
```

### 输出配置

```json
{
  "swordman_male": {
    "items": {
      "cap": {
        "10203": {
          "name": "白色末日使者肩饰",
          "frame": 328,
          "icon_path": "item/avatar/swordman/sm_acap.img",
          "hide_parts": []
        }
      }
    }
  }
}
```

## 执行命令

```bash
# 使用 v2 版本（带 icon 路径验证）
python sync_equ_to_config_v2.py

# 试运行
python sync_equ_to_config_v2.py --dry-run

# 不创建备份
python sync_equ_to_config_v2.py --no-backup
```

## 输出统计

脚本执行完成后会显示：

```
完成:
  处理文件: 1250
  更新 items: 45

共有 23 个文件的 icon 路径无效，已使用标准路径代替
```

## 与 v1 版本的区别

| 功能 | v1 | v2 |
|------|----|----|
| 提取 name | ✓ | ✓ |
| 提取 frame | ✓ | ✓ |
| 提取 hide_parts | ✓ | ✓ |
| 提取 icon 路径 | ✗ | ✓ |
| 验证 icon 路径 | ✗ | ✓ |
| 替换无效路径 | ✗ | ✓ |
| 保存 icon_path | ✗ | ✓（可选） |

## 注意事项

1. **icon_path 字段**：v2 版本会在配置中添加 `icon_path` 字段用于调试，可以手动删除
2. **frame 始终保留**：无论 icon 路径是否有效，frame（图标索引）都会保留
3. **自动生成路径**：如果原路径无效，会使用脚本生成的标准路径
4. **统计报告**：脚本会报告有多少个文件的 icon 路径无效

## 故障排除

### 大量 icon 路径无效

如果报告显示大量 icon 路径无效，可能原因：
- PVF 中的时装数据确实使用了非标准路径
- 提取的文件不是时装文件（而是武器或其他装备）
- 正则表达式匹配规则需要调整

### 生成的路径不正确

检查 `JOB_ICON_MAP` 和 `PART_ICON_MAP` 是否包含所有职业和部位。
