"""
NPK Viewer Launcher - NPK 浏览器启动脚本

使用方法:
    python run_npk_viewer.py
    python run_npk_viewer.py <npk文件路径>

快捷方式:
    可以将 .npk 文件拖放到此脚本上打开
"""

import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from npk_viewer import main

if __name__ == "__main__":
    main()
