"""
Generate Equ Entry - Equ 生成入口

调用 main.equipment_code_generator 生成 Equ 文件。

Usage:
    python generate_equ.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from main.equipment_code_generator import main

if __name__ == "__main__":
    exit(main())
