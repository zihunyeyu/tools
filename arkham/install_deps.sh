#!/bin/bash
# 安装卡牌文本替换工具的依赖

echo "=================================="
echo "安装卡牌文本替换工具依赖"
echo "=================================="

# 检测操作系统
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "检测到 Linux 系统"
    
    # 检测发行版
    if command -v apt-get &> /dev/null; then
        echo "使用 apt 安装系统依赖..."
        sudo apt-get update
        sudo apt-get install -y libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev
        
        # 安装中文字体
        echo "安装中文字体..."
        sudo apt-get install -y fonts-wqy-zenhei fonts-wqy-microhei fonts-noto-cjk
        
    elif command -v yum &> /dev/null; then
        echo "使用 yum 安装系统依赖..."
        sudo yum install -y mesa-libGL glib2
        
        # 安装中文字体
        echo "安装中文字体..."
        sudo yum install -y wqy-zenhei-fonts wqy-microhei-fonts
    fi
    
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "检测到 macOS 系统"
    
    if command -v brew &> /dev/null; then
        echo "使用 Homebrew 安装依赖..."
        brew install libomp
    else
        echo "警告: 未检测到 Homebrew，某些功能可能受限"
    fi
    
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    echo "检测到 Windows 系统"
    echo "Windows 用户通常不需要额外安装系统依赖"
fi

# 安装 Python 依赖
echo ""
echo "安装 Python 依赖..."
pip install paddlepaddle -i https://pypi.tuna.tsinghua.edu.cn/simple || pip install paddlepaddle
pip install paddleocr opencv-python numpy pillow -i https://pypi.tuna.tsinghua.edu.cn/simple

echo ""
echo "=================================="
echo "安装完成！"
echo "=================================="
echo ""
echo "测试命令:"
echo "  python smart_card_replacer.py --help"
