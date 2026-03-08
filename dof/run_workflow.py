"""
Avatar Workflow Entry - Avatar 工作流入口

简化入口，直接调用 main.workflow 的完整工作流。

Usage:
    python run_workflow.py
    python run_workflow.py --skip-npk
    python run_workflow.py --skip-pvf
    python run_workflow.py --skip-equ
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from main.workflow import main

if __name__ == "__main__":
    exit(main())
