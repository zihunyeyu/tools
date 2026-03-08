"""
Extract NPK Entry - NPK 提取入口

调用 main.avatar_data_extractor_npk 提取 NPK Avatar 数据。

Usage:
    python extract_npk.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from main.avatar_data_extractor_npk import main

if __name__ == "__main__":
    exit(main())
