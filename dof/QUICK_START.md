# 快速开始

## 1. 环境准备

```bash
# 安装依赖
pip install -r requirements.txt
```

## 2. 启动 PVF Utility

1. 打开 pvfUtility
2. 点击"打开PVF"选择你的 .npk 文件
3. 确保 PVF 已成功加载

## 3. 运行生成器

### 默认模式（直接上传到 PVF）
```bash
python equipment_code_generator.py
```

### 保存到本地并上传
```bash
python equipment_code_generator.py --local
```

### 只保存到本地
```bash
python equipment_code_generator.py --local --no-upload
```

## 4. 查看输出

运行后会生成：
- `equ.lst` - 装备编码清单
- `shop.etc` - 商店配置
- `generated_equ/` - equ 文件目录（如果使用了 --local）

## 5. 配置说明

如需修改配置，编辑 `config.py`：

```python
# PVF API 地址
PVF_API_HOST = "localhost"
PVF_API_PORT = 27000

# 装扮表路径
# 在 avatar_table_loader.py 中修改 JOB_TO_FILENAME

# 输出路径
EQUIPMENT_LST = BASE_DIR / "equ.lst"
SHOP_ETC = BASE_DIR / "shop.etc"
```

## 常见问题

**Q: 提示"请先载入PVF封包"**
A: 需要在 pvfUtility 中先打开 PVF 文件

**Q: 如何只生成特定职业？**
A: 修改 `avatar_data.json`，只保留需要的职业数据

**Q: 装扮表文件在哪里？**
A: 默认路径在 `E:\DOF\Tools\blackcat.6.12\output\Avatar\`，可在 `avatar_table_loader.py` 中修改
