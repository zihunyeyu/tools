"""
NPK Extractor Base - NPK提取器基类

提供从NPK文件提取avatar数据的通用功能
"""

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from pydoftools.npk import NPK


class MixedStringParser:
    """混合字符串解析器 - 解析文件名如 coat1230d"""
    
    PATTERN = re.compile(r"^([a-zA-Z]+)(\d+)(.+)$")
    BODY_PATTERN = re.compile(r"^(body)(\d+)$")
    
    @classmethod
    def parse(cls, s: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        拆分混合字符串为 (字母部分, 数字部分, 剩余部分)
        
        Args:
            s: 文件名，如 "coat1230d" 或 "body0"
            
        Returns:
            (part, code, layer) 元组
            例如: ("coat", "1230", "d") 或 ("skin", "0", "")
        """
        # 特殊处理 body -> skin
        match = cls.BODY_PATTERN.match(s)
        if match:
            _, code = match.groups()
            return "skin", code, ""
        
        # 常规解析
        match = cls.PATTERN.match(s)
        if match:
            return match.groups()
        
        return None, None, None


class NPKAvatarExtractorBase(ABC):
    """NPK Avatar 提取器基类"""
    
    def __init__(self, npk_folder: Path):
        """
        初始化提取器
        
        Args:
            npk_folder: NPK 文件所在目录
        """
        self.npk_folder = Path(npk_folder)
        self.data: Dict[str, Any] = {}
    
    def extract_all(self) -> Dict[str, Any]:
        """
        提取所有 NPK 文件
        
        Returns:
            提取的数据字典，格式由子类决定
        """
        for npk_file in self.npk_folder.glob("*.npk"):
            self._process_npk_file(npk_file)
        
        return self.data
    
    def _process_npk_file(self, npk_path: Path):
        """处理单个 NPK 文件"""
        try:
            with NPK.open(npk_path) as npk:
                for img_name, nf in npk.items():
                    self._process_img_file(nf, img_name, npk_path.name)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"处理NPK失败 {npk_path}: {e}")
    
    def _process_img_file(self, nf, img_name: str, npk_name: str):
        """
        处理单个 IMG 文件
        
        Args:
            nf: NPK File对象
            img_name: IMG名称
            npk_name: 所属的NPK文件名
        """
        # 解析文件名
        part, code, layer = MixedStringParser.parse(img_name)
        if not part or not code:
            return
        
        # 提取图层信息
        layers = self._extract_layers(nf)
        
        # 调用子类处理
        self._handle_avatar_item(part, code, layer, layers, img_name, npk_name)
    
    def _extract_layers(self, nf) -> List[str]:
        """
        提取图层列表
        
        Args:
            nf: NPK File对象
            
        Returns:
            图层字母列表（去重，排序）
        """
        layer_set = set()
        
        try:
            for img in nf.images:
                # 从 frame 名称提取图层
                for frame in img.frames:
                    if hasattr(frame, 'name'):
                        # 提取最后一个字符作为图层
                        if frame.name:
                            layer = frame.name[-1:].lower()
                            if layer.isalpha():
                                layer_set.add(layer)
        except Exception:
            pass
        
        return sorted(list(layer_set))
    
    @abstractmethod
    def _handle_avatar_item(
        self,
        part: str,
        code: str,
        layer: str,
        layers: List[str],
        img_name: str,
        npk_name: str
    ):
        """
        处理单个avatar项 - 子类必须实现
        
        Args:
            part: 部位名
            code: 代码
            layer: 当前图层
            layers: 所有图层列表
            img_name: 原始IMG名称
            npk_name: 所属的NPK文件名
        """
        pass


class RawNPKExtractor(NPKAvatarExtractorBase):
    """原始格式NPK提取器 - 返回简单列表格式"""
    
    def __init__(self, npk_folder: Path):
        super().__init__(npk_folder)
        self.data: Dict[str, Dict[str, List]] = {}  # job -> part -> items
    
    def _handle_avatar_item(
        self,
        part: str,
        code: str,
        layer: str,
        layers: List[str],
        img_name: str,
        npk_name: str
    ):
        """处理为原始格式"""
        # 从NPK文件名推断职业
        job = self._infer_job_from_npk(npk_name)
        if not job:
            return
        
        if job not in self.data:
            self.data[job] = {}
        
        if part not in self.data[job]:
            self.data[job][part] = []
        
        # 添加到列表
        self.data[job][part].append({
            'code': code,
            'layers': layers,
            'source': img_name
        })
    
    def _infer_job_from_npk(self, npk_name: str) -> Optional[str]:
        """从NPK文件名推断职业"""
        npk_lower = npk_name.lower()
        
        job_mapping = {
            'swordman': 'swordman',
            'atfighter': 'fighter_male',
            'fighter': 'fighter_female',
            'atgunner': 'gunner_female',
            'gunner': 'gunner_male',
            'atmage': 'mage_male',
            'mage': 'mage_female',
            'priest': 'priest',
            'thief': 'thief',
        }
        
        for key, job in job_mapping.items():
            if key in npk_lower:
                return job
        
        return None


class ConfigurableNPKExtractor(NPKAvatarExtractorBase):
    """可配置NPK提取器 - 支持传入配置进行数据合并"""
    
    def __init__(self, npk_folder: Path, config: Optional[Dict] = None):
        """
        初始化
        
        Args:
            npk_folder: NPK文件目录
            config: 可选的现有配置，用于合并数据
        """
        super().__init__(npk_folder)
        self.config = config or {}
        self.data: Dict[str, Any] = {}
    
    def _handle_avatar_item(
        self,
        part: str,
        code: str,
        layer: str,
        layers: List[str],
        img_name: str,
        npk_name: str
    ):
        """处理并合并到配置"""
        # 子类可实现具体的合并逻辑
        pass
