# DOF Equipment Generator - 装备生成器

基于 PVF Utility Web API 的 DNF 装备生成工具。

## 项目结构

```
dof/
├── config.py                       # 配置文件（路径、映射关系）
├── equipment_code_generator.py     # 主程序 - 装备编码和 equ 文件生成
├── avatar_table_loader.py          # 装扮表加载器 - 读取装扮表获取 name 和 icon
├── equ_template_cache.py           # Equ 模板缓存管理器
├── pvf_api_client.py               # PVF API 客户端
├── tsv_validator.py                # TSV 验证器
├── equipment_tag_parser.py         # 装备标签解析器
├── avatar_data_extractor.py        # Avatar 数据提取器
├── npk_compiler.py                 # NPK 编译器
├── npk_deduplicator.py             # NPK 去重器
│
├── model/                          # 数据模型
│   └── equ_models.py               # 装备代码映射和中文映射
│
├── data/                           # 数据目录
│   └── equ_templates_cache.json    # 缓存的 equ 模板
│
├── generated_equ/                  # 生成的 equ 文件输出目录
│   └── equipment/                  # equ 文件按职业/部位组织
│
└── [output files]                  # 输出文件
    ├── equ.lst                     # 装备编码清单
    └── shop.etc                    # 商店配置
```

## 核心模块说明

### 1. equipment_code_generator.py
主程序，负责：
- 从 avatar_data.json 读取数据
- 生成装备编码（equ_code）
- 生成 equ 文件内容（使用装扮表 name 和 icon）
- 写入 equ.lst 和 shop.etc
- 上传 equ 文件到 PVF

**使用方式：**
```bash
# 默认：直接上传到 PVF
python equipment_code_generator.py

# 保存到本地并上传
python equipment_code_generator.py --local

# 只保存到本地
python equipment_code_generator.py --local --no-upload
```

### 2. avatar_table_loader.py
装扮表加载器，负责：
- 从装扮表文件（如 `鬼剑士(男)装扮表.txt`）读取数据
- 构建索引支持按 (job, part, code) 查询
- 获取装备名称和图标索引

### 3. equ_template_cache.py
Equ 模板缓存管理器，负责：
- 从 PVF 获取指定代码的 equ 文件作为模板
- 缓存模板到本地 JSON 文件避免重复读取
- 提供模板查询接口

### 4. pvf_api_client.py
PVF API 客户端，封装 PVF Utility Web API：
- 文件内容获取
- 文件批量导入
- LST 文件信息查询
- 装备代码查找

### 5. config.py
项目配置文件，包含：
- 路径配置
- 职业映射（JOB_MAP）
- 部位映射（PART_CODE_MAP）
- PVF API 配置

## 数据流

```
avatar_data.json
       ↓
EquipmentCodeGenerator.process_avatar_data()
       ↓
┌─────────────────────────────────────┐
│  1. 生成装备编码 (equ_code)          │
│  2. 查询装扮表获取 name/icon_index   │
│  3. 获取 equ 模板                    │
│  4. 生成 equ 文件内容                │
└─────────────────────────────────────┘
       ↓
    输出文件
├─ equ.lst      (装备编码清单)
├─ shop.etc     (商店配置)
└─ [上传到 PVF] (equipment/character/...)
```

## 装备编码规则

### 编码格式
```
60{job_code}5{part_code}{sequence:04d}

示例：
- sm(1) + hair(6) → 601560001
- fm(3) + coat(0) → 603500001
```

### Icon 路径规则
```
item/avatar/{job_path}/{job_prefix}_{part_icon}.img

示例：
- sm + hair → item/avatar/swordman/sm_ahair.img
- fm + coat → item/avatar/atfighter/fm_acoat.img
- gg + belt → item/avatar/atgunner/gg_abelt.img
```

## 关键映射

### 职业映射
| 代码 | 职业 | 路径 | 文件名前缀 |
|------|------|------|-----------|
| sm | 鬼剑士 | swordman | sm |
| ft | 格斗家(女) | fighter | ft |
| fm | 格斗家(男) | atfighter | fm |
| gn | 神枪手(男) | gunner | gn |
| gg | 神枪手(女) | atgunner | gg |
| mg | 魔法师(女) | mage | mg |
| mm | 魔法师(男) | atmage | mm |
| pr | 圣职者 | priest | pr |
| th | 暗夜使者 | thief | tf |

### 部位图标映射
| 部位 | 图标文件名 |
|------|------------|
| coat | acoat |
| pants | apants |
| belt | abelt |
| neck | aneck |
| shoes | ashoes |
| cap | acap |
| hair | ahair |
| face | aface |
| skin | abody |

## 配置说明

### config.py 关键配置

```python
# 输出路径
EQUIPMENT_LST = BASE_DIR / "equ.lst"      # 装备编码清单
SHOP_ETC = BASE_DIR / "shop.etc"          # 商店配置

# PVF API 配置
PVF_API_HOST = "localhost"
PVF_API_PORT = 27000

# 装备路径模板
EQU_PATH_TEMPLATE = "`equipment/character/{job}avatar/{part}/{code}.equ`"
```

## 依赖

- Python 3.8+
- requests
- PVF Utility (运行中的 Web API 服务)

## 前置条件

1. 安装 Python 依赖：
```bash
pip install -r requirements.txt
```

2. 启动 PVF Utility 并打开 PVF 文件

3. 确保装扮表文件存在于：`E:	oolslackcat.6.12iles	ablees	able	able.bin`

## 输出文件格式

### equ.lst
```
60150001	`equipment/character/swordmanavatar/hair/60150001.equ`
60150002	`equipment/character/swordmanavatar/hair/60150002.equ`
```

### shop.etc
```
133012	60150001	3	0	0	-1	-1	60150001	4	0	0	-1
133012	60150002	3	0	0	-1	-1	60150002	4	0	0	-1
```

## 注意事项

1. **PVF 必须已加载**：运行前确保 pvfUtility 已打开 PVF 文件
2. **装扮表文件**：需要正确配置装扮表文件路径
3. **代码冲突**：会自动跳过已存在的装备代码
4. **上传路径**：equ 文件上传到 `equipment/character/{job}avatar/{part}/`
