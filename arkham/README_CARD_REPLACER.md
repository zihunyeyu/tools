# 卡牌文本替换工具

将中文卡图（拍照/扫描）的文本识别并替换到清晰的英文卡图上，保持卡图清晰度的同时使用中文字幕。

## 功能特点

- **精确文本定位**: 基于 PaddleOCR 的高精度文字检测
- **智能区域匹配**: 基于卡牌固定布局的智能匹配算法
- **图像修复**: 使用 OpenCV Inpainting 技术清除原文本，无缝替换
- **样式保持**: 自动检测文本颜色和字体大小，保持原卡图风格
- **批量处理**: 支持批量处理多张卡牌

## 安装依赖

```bash
# 安装 Python 依赖
pip install paddleocr opencv-python numpy pillow

# Linux 用户可能需要安装系统依赖
sudo apt-get install libgl1-mesa-glx libglib2.0-0

# macOS 用户可能需要
brew install libomp
```

## 快速开始

### 单张处理

```bash
# 基础版本
python card_text_replacer.py \
    --cn ./chinese_card.jpg \
    --en ./english_card.png \
    --output ./result.png

# 智能版本（推荐）
python smart_card_replacer.py \
    --cn ./chinese_card.jpg \
    --en ./english_card.png \
    --output ./result.png \
    --debug
```

### 批量处理

假设你有以下目录结构：
```
./chinese_cards/     # 中文卡图（拍照/扫描）
    ├── 01001.jpg
    ├── 01002.jpg
    └── ...

./english_cards/     # 英文卡图（清晰的）
    ├── 01001.png
    ├── 01002.png
    └── ...
```

运行批量处理：

```bash
python smart_card_replacer.py \
    --batch \
    --cn-dir ./chinese_cards/ \
    --en-dir ./english_cards/ \
    --output-dir ./output/
```

## 工具对比

| 特性 | card_text_replacer.py | smart_card_replacer.py |
|------|----------------------|------------------------|
| 文本检测 | 基础 OCR | 高级 OCR + 布局分析 |
| 区域匹配 | 基于距离 | 基于类型 + 位置 |
| 字体处理 | 统一处理 | 按区域类型差异化 |
| 图像修复 | 基础 Inpaint | 高级 Inpaint |
| 适合场景 | 简单卡图 | 复杂布局卡图 |

**建议**: 对于 Arkham Horror LCG 等复杂卡牌，使用 `smart_card_replacer.py`

## 参数说明

### 通用参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--cn` | 中文卡图路径 | `--cn ./ch.jpg` |
| `--en` | 英文卡图路径 | `--en ./en.png` |
| `--output` | 输出路径 | `--output ./out.png` |
| `--debug` | 输出调试信息 | `--debug` |

### 批量处理参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--batch` | 启用批量模式 | `--batch` |
| `--cn-dir` | 中文卡图目录 | `--cn-dir ./cn/` |
| `--en-dir` | 英文卡图目录 | `--en-dir ./en/` |
| `--output-dir` | 输出目录 | `--output-dir ./out/` |

## 工作原理

1. **OCR 检测**: 使用 PaddleOCR 分别检测中英文卡图中的所有文本区域
2. **区域匹配**: 基于相对位置和卡牌布局，匹配对应的文本区域
3. **图像修复**: 使用 Inpainting 算法清除英文卡图上的原文本
4. **文本绘制**: 将识别到的中文文本绘制到清理后的区域

## 注意事项

### 中文卡图要求
- 尽量清晰，文字可辨认
- 避免过度倾斜或反光
- 完整的卡牌图片

### 英文卡图要求
- 高清晰度，用于作为底板
- 与中文卡图内容对应
- 建议尺寸一致

### 常见问题

**Q: OCR 识别中文不准确？**
A: 确保中文卡图清晰，可以尝试：
- 提高照片分辨率
- 改善拍摄光线
- 使用 PaddleOCR 的更高精度模型

**Q: 文本替换位置偏移？**
A: 确保中英文卡图尺寸比例一致，或者让智能版本自动调整

**Q: 字体显示异常？**
A: 需要安装中文字体：
```bash
# Ubuntu/Debian
sudo apt-get install fonts-wqy-zenhei fonts-wqy-microhei

# CentOS/RHEL
sudo yum install wqy-zenhei-fonts
```

## 文件对应规则

批量处理时，工具按以下顺序查找对应的英文卡图：

1. 同名同后缀: `01001.jpg` → `01001.jpg`
2. 同名 PNG: `01001.jpg` → `01001.png`
3. 去掉 `_cn` 后缀: `01001_cn.jpg` → `01001.png`

## 自定义配置

可以编辑 `smart_card_replacer.py` 中的 `CardLayoutAnalyzer.LAYOUT_ZONES` 来调整不同区域的定位参数：

```python
LAYOUT_ZONES = {
    'title': {'y_range': (0.02, 0.12), 'x_range': (0.15, 0.85)},
    'cost': {'y_range': (0.02, 0.12), 'x_range': (0.02, 0.15)},
    'text': {'y_range': (0.65, 0.90), 'x_range': (0.08, 0.92)},
    # ... 更多区域
}
```

## 示例输出

```
处理: 01001.jpg
  中文: ./chinese_cards/01001.jpg
  英文: ./english_cards/01001.png
  调整尺寸: (1200, 1800) -> (1500, 2250)
  检测中文文本...
  检测英文文本...
  发现: 8 个中文区域, 8 个英文区域
  匹配文本区域...
  成功匹配: 8 对
  输出: ./output/01001_replaced.png
```
