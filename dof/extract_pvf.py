"""
Extract PVF Entry - PVF 提取入口

调用 main.avatar_data_extractor_pvf 提取 PVF Avatar 数据。

Usage:
    python extract_pvf.py
    python extract_pvf.py -o output/avatar_data.tsv
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from main.avatar_data_extractor_pvf import main

if __name__ == "__main__":
    exit(main())
