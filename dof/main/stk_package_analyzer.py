"""
STK Package Analyzer - STK礼包分析器（精简版）

从PVF中读取stackable/stackable.lst，解析stk文件中的[package data]，
只保留时装类型（[equipment type]包含"avatar"）的equ，
输出stk名称和对应的equ代码、名称。

输出格式：
{
  "packages": [
    {
      "stk_name": "春节礼包",
      "items": [
        {"equ_code": "600105001", "equ_name": "白色末日使者肩饰"}
      ]
    }
  ]
}
"""

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.pvf_api_client import PvfUtilityApi
from modules.equ_parser import EquParser
from config import PVF_API_HOST, PVF_API_PORT

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PackageItem:
    """礼包中的单个装备项"""
    equ_code: str
    equ_name: str


@dataclass
class StkPackage:
    """STK礼包信息（精简）"""
    stk_name: str
    items: List[PackageItem] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "stk_name": self.stk_name,
            "items": [
                {"equ_code": item.equ_code, "equ_name": item.equ_name}
                for item in self.items
            ]
        }


class StkParser:
    """STK文件解析器"""
    
    @staticmethod
    def parse_name(content: str) -> str:
        """解析[name]标签内容"""
        match = re.search(r'\[name\]\s*\r?\n\s*`([^`]*)`', content)
        if match:
            return match.group(1).strip()
        return ""
    
    @staticmethod
    def parse_package_data(content: str) -> List[str]:
        """
        解析[package data]标签中的equ代码列表
        
        Returns:
            equ_code列表（去重，只保留代码，不解析数量）
        """
        pattern = r'\[package data\]\s*\r?\n(.*?)\r?\n\s*\[/package data\]'
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            return []
        
        codes = []
        data_section = match.group(1)
        
        for line in data_section.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            
            parts = line.split('\t')
            if parts and parts[0].strip():
                code = parts[0].strip()
                if code not in codes:  # 去重
                    codes.append(code)
        
        return codes


class StkPackageAnalyzer:
    """STK礼包分析器（精简版）"""
    
    STACKABLE_LST_PATH = "stackable/stackable.lst"
    EQUIPMENT_LST_PATH = "equipment/equipment.lst"
    
    def __init__(self, pvf_api: PvfUtilityApi):
        self._pvf_api = pvf_api
        self._stk_parser = StkParser()
        self._equ_parser = EquParser()
        
        self._stackable_lst: Dict[str, str] = {}
        self._equipment_lst: Dict[str, str] = {}
        self._equ_name_cache: Dict[str, Optional[str]] = {}
    
    def load_stackable_lst(self) -> None:
        """从PVF加载stackable.lst"""
        logger.info(f"正在加载 {self.STACKABLE_LST_PATH}...")
        
        lst_info = self._pvf_api.get_lst_file_info(self.STACKABLE_LST_PATH)
        for code_str, info in lst_info.items():
            if isinstance(info, dict) and 'FullPath' in info:
                self._stackable_lst[code_str] = info['FullPath']
            elif isinstance(info, str):
                self._stackable_lst[code_str] = info
        
        logger.info(f"已加载 {len(self._stackable_lst)} 条stk记录")
    
    def load_equipment_lst(self) -> None:
        """从PVF加载equipment.lst"""
        logger.info(f"正在加载 {self.EQUIPMENT_LST_PATH}...")
        
        lst_info = self._pvf_api.get_lst_file_info(self.EQUIPMENT_LST_PATH)
        for code_str, info in lst_info.items():
            if isinstance(info, dict) and 'FullPath' in info:
                self._equipment_lst[code_str] = info['FullPath']
            elif isinstance(info, str):
                self._equipment_lst[code_str] = info
        
        logger.info(f"已加载 {len(self._equipment_lst)} 条equ记录")
    
    def is_avatar_equipment(self, equ_code: str) -> Tuple[bool, Optional[str]]:
        """
        检测是否为时装并返回名称
        
        Returns:
            (是否时装, equ_name) - 不是时装返回(False, None)
        """
        # 检查缓存
        if equ_code in self._equ_name_cache:
            name = self._equ_name_cache[equ_code]
            return name is not None, name
        
        # 检查是否在equipment.lst中
        equ_path = self._equipment_lst.get(equ_code)
        if not equ_path:
            self._equ_name_cache[equ_code] = None
            return False, None
        
        try:
            content = self._pvf_api.get_file_content(equ_path)
        except Exception:
            self._equ_name_cache[equ_code] = None
            return False, None
        
        # 检查是否为avatar类型
        if "[avatar" not in content.lower():
            self._equ_name_cache[equ_code] = None
            return False, None
        
        # 解析名称
        equ_data = self._equ_parser.parse(content)
        name = equ_data.name if equ_data.name else None
        
        self._equ_name_cache[equ_code] = name
        return name is not None, name
    
    def analyze_stk(self, stk_code: str) -> Optional[StkPackage]:
        """
        分析单个stk礼包
        
        Returns:
            StkPackage对象，如果没有avatar时装返回None
        """
        stk_path = self._stackable_lst.get(stk_code)
        if not stk_path:
            return None
        
        try:
            content = self._pvf_api.get_file_content(stk_path)
        except Exception:
            return None
        
        stk_name = self._stk_parser.parse_name(content)
        if not stk_name:
            stk_name = f"礼包_{stk_code}"
        
        equ_codes = self._stk_parser.parse_package_data(content)
        if not equ_codes:
            return None
        
        # 筛选avatar时装
        items = []
        for equ_code in equ_codes:
            is_avatar, equ_name = self.is_avatar_equipment(equ_code)
            if is_avatar and equ_name:
                items.append(PackageItem(equ_code=equ_code, equ_name=equ_name))
        
        if not items:
            return None
        
        return StkPackage(stk_name=stk_name, items=items)
    
    def analyze_all(self, progress_interval: int = 100) -> List[StkPackage]:
        """分析所有stk礼包"""
        results = []
        total = len(self._stackable_lst)
        
        logger.info(f"开始分析 {total} 个stk礼包...")
        
        for idx, stk_code in enumerate(sorted(self._stackable_lst.keys(), key=int), 1):
            try:
                pkg = self.analyze_stk(stk_code)
                if pkg:
                    results.append(pkg)
                
                if idx % progress_interval == 0:
                    logger.info(f"进度: {idx}/{total} ({idx/total*100:.1f}%), 找到有效礼包: {len(results)}")
                    
            except Exception as e:
                logger.debug(f"分析stk {stk_code} 时出错: {e}")
        
        logger.info(f"分析完成！共找到 {len(results)} 个包含时装的礼包")
        return results
    
    def export_json(self, results: List[StkPackage], output_path: Path) -> bool:
        """导出结果为JSON"""
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "packages": [pkg.to_dict() for pkg in results]
            }
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"JSON已导出: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"导出JSON失败: {e}")
            return False


def main():
    """主程序入口"""
    # ==================== 配置区域 ====================
    PVF_API_HOST = "localhost"
    PVF_API_PORT = 27000
    OUTPUT_PATH = Path(__file__).parent.parent / "output" / "stk_packages.json"
    PROGRESS_INTERVAL = 100
    # ==================================================
    
    logger.info("STK Package Analyzer - 开始运行")
    
    try:
        pvf_api = PvfUtilityApi(host=PVF_API_HOST, port=PVF_API_PORT)
        version = pvf_api.get_version()
        logger.info(f"PVF API连接成功，版本: {version}")
        
        analyzer = StkPackageAnalyzer(pvf_api)
        analyzer.load_stackable_lst()
        analyzer.load_equipment_lst()
        
        results = analyzer.analyze_all(progress_interval=PROGRESS_INTERVAL)
        
        if results:
            analyzer.export_json(results, OUTPUT_PATH)
        else:
            logger.warning("没有解析到任何包含时装的礼包")
        
        logger.info("处理完成！")
        
    except Exception as e:
        logger.error(f"程序运行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
