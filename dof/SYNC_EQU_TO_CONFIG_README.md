# 从 PVF equ 文件同步数据到 avatar_config.json

## 功能概述

这个脚本从 PVF 游戏数据中提取时装（avatar）的 equ 文件，筛选出 name 标签**不是**"英文+数字"组合的文件，然后将这些文件的名称、图标索引和隐藏部位信息更新到 `avatar_config.json` 中。

## 工作流程

```
PVF API
    │
    ├─ equipment.lst (装备列表)
    └─ *.equ 文件
           │
           ├─ [name] 标签 → 筛选（非英文+数字）
           ├─ [icon] 标签 → 提取 frame
           └─ [hide equipment] → 提取隐藏部位
                  │
                  ▼
         avatar_config.json
                  │
                  ├─ items.cap.10203.name
                  ├─ items.cap.10203.frame
                  └─ items.cap.10203.hide_parts
```

## 筛选规则

脚本会**跳过** name 符合以下模式的 equ 文件：
- ✅ `cap1230` - 跳过（纯英文+数字）
- ✅ `hat_456` - 跳过（纯英文+数字+下划线）
- ✅ `coat789` - 跳过（纯英文+数字）
- ❌ `白色末日使者肩饰` - **保留**（包含中文）
- ❌ `Red Dragon Coat` - **保留**（包含空格）
- ❌ `Super-Rare Hat` - **保留**（包含连字符）

## 提取字段

### 1. Name（名称）
从 `[name]` 标签提取：
```ini
[name]
	`白色末日使者肩饰`
```

### 2. Frame（图标索引）
从 `[icon]` 标签提取最后的数字：
```ini
[icon]
	`item/avatar/swordman/sm_acap.img`	328
```
提取结果：`frame: 328`

### 3. Hide Parts（隐藏部位）
从 `[hide equipment]` 标签提取并转换为部位代码：
```ini
[hide equipment]
	`[hat avatar]`
	`[hair avatar]`
	`[face avatar]`
[/hide equipment]
```
提取结果：`hide_parts: ["cap", "hair", "face"]`

## 使用方式

### 基本使用

```bash
python sync_equ_to_config.py
```

### 命令行参数

```bash
# 指定配置文件路径
python sync_equ_to_config.py --config path/to/avatar_config.json

# 指定备份目录
python sync_equ_to_config.py --backup-dir ./my_backups

# 指定 PVF API 地址
python sync_equ_to_config.py --host localhost --port 27000

# 试运行（不保存修改）
python sync_equ_to_config.py --dry-run

# 不创建备份
python sync_equ_to_config.py --no-backup
```

## 输出示例

```
2024-01-15 10:30:00,123 - INFO - 加载配置: avatar_config.json
2024-01-15 10:30:00,456 - INFO - 配置加载完成: 9 个职业
2024-01-15 10:30:00,789 - INFO - 已创建备份: backups\avatar_config_backup_20240115_103000.json
2024-01-15 10:30:01,000 - INFO - 连接 PVF API: localhost:27000
2024-01-15 10:30:02,000 - INFO - 解析 equipment.lst...
2024-01-15 10:30:05,000 - INFO - 提取 equ 文件...
2024-01-15 10:30:30,000 - INFO - 
处理 equ 文件...

2024-01-15 10:30:31,000 - INFO - 
处理: equipment/character/swordmanavatar/cap/60150001.equ
2024-01-15 10:30:31,001 - INFO -   职业: swordman -> swordman_male
2024-01-15 10:30:31,002 - INFO -   部位: hat -> cap
2024-01-15 10:30:31,003 - INFO -   Variation: 102_3 -> (102, 3)
2024-01-15 10:30:31,004 - INFO -   Name: 白色末日使者肩饰
2024-01-15 10:30:31,005 - INFO -   Frame: 328
2024-01-15 10:30:31,006 - INFO -   Hide parts: ['cap', 'hair']
2024-01-15 10:30:31,007 - INFO -   找到匹配: swordman_male/cap/10203
2024-01-15 10:30:31,008 - INFO -     更新: name: '旧名称' -> '白色末日使者肩饰'
2024-01-15 10:30:31,009 - INFO -     更新: frame: 0 -> 328
2024-01-15 10:30:31,010 - INFO -     更新: hide_parts: [] -> ['cap', 'hair']

...

2024-01-15 10:31:00,000 - INFO - 
完成:
2024-01-15 10:31:00,001 - INFO -   处理文件: 1250
2024-01-15 10:31:00,002 - INFO -   更新 items: 45
2024-01-15 10:31:00,003 - INFO - 配置已保存: avatar_config.json
```

## 字段映射

### 职业映射

| equ 文件中的 career | avatar_config.json 中的 job_key |
|-------------------|------------------------------|
| swordman | swordman_male |
| fighter | fighter_female |
| at fighter | fighter_male |
| gunner | gunner_male |
| at gunner | gunner_female |
| mage | mage_female |
| at mage | mage_male |
| priest | priest_male |
| thief | thief_female |

### 部位映射

| equ 中的 equipment_type | avatar_config.json 中的 part |
|-----------------------|---------------------------|
| hat | cap |
| hair | hair |
| face | face |
| breast | neck |
| coat | coat |
| pants | pants |
| waist | belt |
| shoes | shoes |
| skin | skin |

### Hide Equipment 映射

| equ 中的类型 | avatar_config.json 中的 part |
|------------|---------------------------|
| `[hat avatar]` | cap |
| `[hair avatar]` | hair |
| `[face avatar]` | face |
| `[breast avatar]` | neck |
| `[coat avatar]` | coat |
| `[pants avatar]` | pants |
| `[waist avatar]` | belt |
| `[shoes avatar]` | shoes |
| `[skin avatar]` | skin |

## 备份机制

脚本会自动创建备份，备份文件格式为：
```
backups/avatar_config_backup_YYYYMMDD_HHMMSS.json
```

可以使用 `--backup-dir` 指定备份目录，或使用 `--no-backup` 跳过备份。

## 完整操作流程

```bash
# 1. 确保 PVF API 服务正在运行
# 检查 localhost:27000 是否可访问

# 2. 试运行查看会更新哪些内容
python sync_equ_to_config.py --dry-run

# 3. 正式执行（会自动创建备份）
python sync_equ_to_config.py

# 4. 检查更新结果
# 查看日志输出，或对比备份文件
```

## 故障排除

### 找不到匹配项

如果显示"未找到匹配"，可能原因：
1. avatar_config.json 中不存在对应的 code
2. 职业或部位映射错误
3. variation code 解析错误

### API 连接失败

检查：
1. PVF API 服务是否正在运行
2. host 和 port 配置是否正确
3. 防火墙设置

### 更新后数据不正确

1. 检查备份文件，确认原始数据
2. 使用 `--dry-run` 查看详细日志
3. 检查 equ 文件中的原始数据

## 依赖要求

```bash
pip install requests urllib3
```

## 相关文件

- `sync_equ_to_config.py` - 主脚本
- `modules/avatar_extractor.py` - PVF 数据提取模块
- `avatar_config.json` - 目标配置文件
- `backups/` - 自动备份目录
