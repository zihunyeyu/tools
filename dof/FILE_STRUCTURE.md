# 项目文件结构

## 核心文件

| 文件 | 说明 | 大小 |
|------|------|------|
| `equipment_code_generator.py` | 主程序 - 装备编码生成器 | 47.5 KB |
| `avatar_table_loader.py` | 装扮表加载器 | 12.1 KB |
| `equ_template_cache.py` | Equ 模板缓存管理器 | 15.0 KB |
| `pvf_api_client.py` | PVF API 客户端 | 14.8 KB |
| `config.py` | 配置文件 | 3.7 KB |

## 辅助模块

| 文件 | 说明 |
|------|------|
| `tsv_validator.py` | TSV 验证器 |
| `equipment_tag_parser.py` | 装备标签解析器 |
| `avatar_data_extractor.py` | Avatar 数据提取器 |
| `npk_compiler.py` | NPK 编译器 |
| `npk_deduplicator.py` | NPK 去重器 |

## 数据模型

| 文件 | 说明 |
|------|------|
| `model/equ_models.py` | 装备代码映射和中文映射 |
| `model/avatars.py` | Avatar 模型（可选） |

## 配置文件

| 文件 | 说明 |
|------|------|
| `requirements.txt` | Python 依赖 |

## 文档

| 文件 | 说明 |
|------|------|
| `README.md` | 项目说明文档 |
| `QUICK_START.md` | 快速开始指南 |
| `IMPLEMENTATION_SPEC.md` | 实现规范（可选） |

## 输出文件（运行时生成）

| 文件 | 说明 |
|------|------|
| `equ.lst` | 装备编码清单 |
| `shop.etc` | 商店配置 |
| `data/equ_templates_cache.json` | 模板缓存 |
| `generated_equ/` | 生成的 equ 文件 |

## 输入文件

| 文件 | 说明 |
|------|------|
| `avatar_data.json` | Avatar 数据 |
| `complete_equipment_tags.tsv` | 装备标签数据 |

## 使用示例

```bash
# 直接上传到 PVF（默认）
python equipment_code_generator.py

# 保存到本地并上传
python equipment_code_generator.py --local

# 只保存到本地
python equipment_code_generator.py --local --no-upload
```
