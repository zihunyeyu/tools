"""
通用工具模块
提供文件读写、日志记录等通用功能
"""

from pathlib import Path
from typing import List, Tuple, Optional


def log_error(msg: str, e: Exception = None):
    """简化的错误日志输出"""
    if e:
        print(f"[ERROR] {msg}: {e}")
    else:
        print(f"[ERROR] {msg}")


def read_text_file(
    file_path: Path, encodings: Tuple[str, ...] = ("utf-8", "gbk", "gb18030")
) -> List[str]:
    """读取文本文件，自动尝试多种编码"""
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"Cannot decode file: {file_path}")


def write_text_file(
    file_path: Path, lines: List[str], encodings: Tuple[str, ...] = ("utf-8", "gbk")
) -> bool:
    """写入文本文件，失败时尝试备用编码"""
    for encoding in encodings:
        try:
            with open(file_path, "w", encoding=encoding) as f:
                f.writelines(lines)
            return True
        except Exception as e:
            print(f"Error writing with {encoding}: {e}")
            continue
    return False


class LRUCache:
    """简单的 LRU 缓存实现"""
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = {}
        self.order = []
    
    def get(self, key):
        if key not in self.cache:
            return None
        # 移动到最新
        self.order.remove(key)
        self.order.append(key)
        return self.cache[key]
    
    def put(self, key, value):
        if key in self.cache:
            self.order.remove(key)
        elif len(self.cache) >= self.capacity:
            # 淘汰最旧的
            oldest = self.order.pop(0)
            del self.cache[oldest]
        self.cache[key] = value
        self.order.append(key)
    
    def clear(self):
        self.cache.clear()
        self.order.clear()
    
    def __len__(self):
        return len(self.cache)
