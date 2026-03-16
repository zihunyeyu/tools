"""
Common Utilities - 通用工具函数

集中管理日志配置、PVF API初始化、文件备份等通用功能
"""

import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import PVF_API_HOST, PVF_API_PORT
from modules.pvf_api_client import PvfUtilityApi


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    设置统一日志配置
    
    Args:
        level: 日志级别，默认 INFO
        
    Returns:
        配置好的logger实例
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def init_pvf_api(
    host: str = PVF_API_HOST,
    port: int = PVF_API_PORT,
    test_connection: bool = True
) -> PvfUtilityApi:
    """
    初始化PVF API客户端
    
    Args:
        host: API主机地址
        port: API端口
        test_connection: 是否测试连接
        
    Returns:
        初始化好的PvfUtilityApi实例
        
    Raises:
        ConnectionError: 如果测试连接失败
    """
    logger = logging.getLogger(__name__)
    
    logger.info(f"连接PVF API: {host}:{port}")
    api = PvfUtilityApi(host=host, port=port)
    
    if test_connection:
        version = api.get_version()
        logger.info(f"PVF API连接成功，版本: {version}")
    
    return api


def backup_file(
    source_path: Path,
    backup_dir: Optional[Path] = None,
    suffix: str = "bak"
) -> Path:
    """
    创建文件备份
    
    Args:
        source_path: 源文件路径
        backup_dir: 备份目录，默认为源文件所在目录
        suffix: 备份文件后缀
        
    Returns:
        备份文件路径
    """
    source_path = Path(source_path)
    
    if backup_dir is None:
        backup_dir = source_path.parent
    else:
        backup_dir = Path(backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"{source_path.stem}.{suffix}.{timestamp}{source_path.suffix}"
    backup_path = backup_dir / backup_name
    
    shutil.copy2(source_path, backup_path)
    
    logger = logging.getLogger(__name__)
    logger.info(f"已备份: {backup_path}")
    
    return backup_path


def load_json(path: Path) -> dict:
    """加载JSON文件"""
    import json
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(path: Path, data: dict, indent: int = 2):
    """保存JSON文件"""
    import json
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    
    logger = logging.getLogger(__name__)
    logger.info(f"已保存: {path}")


class ProgressTracker:
    """进度跟踪器"""
    
    def __init__(self, total: int, interval: int = 100):
        """
        初始化进度跟踪器
        
        Args:
            total: 总任务数
            interval: 报告间隔
        """
        self.total = total
        self.interval = interval
        self.current = 0
        self.logger = logging.getLogger(__name__)
    
    def update(self, increment: int = 1):
        """更新进度"""
        self.current += increment
        
        if self.current % self.interval == 0:
            self._report()
    
    def _report(self):
        """报告进度"""
        percent = self.current / self.total * 100
        self.logger.info(f"进度: {self.current}/{self.total} ({percent:.1f}%)")
    
    def finish(self):
        """完成报告"""
        self.logger.info(f"完成: {self.current}/{self.total}")


class StatsCollector:
    """统计收集器"""
    
    def __init__(self):
        self.stats = {}
    
    def increment(self, key: str, value: int = 1):
        """增加统计值"""
        self.stats[key] = self.stats.get(key, 0) + value
    
    def set(self, key: str, value):
        """设置统计值"""
        self.stats[key] = value
    
    def get(self, key: str, default=0):
        """获取统计值"""
        return self.stats.get(key, default)
    
    def print_summary(self, title: str = "统计"):
        """打印统计摘要"""
        logger = logging.getLogger(__name__)
        logger.info("=" * 50)
        logger.info(f"{title}:")
        for key, value in sorted(self.stats.items()):
            logger.info(f"  {key}: {value}")
        logger.info("=" * 50)
