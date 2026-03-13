"""
Avatar Extractor - Avatar 数据提取器

从 PVF 中提取 avatar（时装）装备数据，支持解析 equipment.lst 和 .equ 文件。
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    PVF_API_HOST, PVF_API_PORT, PVF_API_TIMEOUT,
    BATCH_SIZE, MAX_WORKERS, MAX_RETRIES,
    EQUIP_TYPE_PATTERN, VARIATION_PATTERN
)

logger = logging.getLogger(__name__)


@dataclass
class AvatarData:
    """Avatar 数据类"""
    code: str
    path: str
    career: str
    equipment_type: str
    variation: str
    
    def to_dict(self) -> Dict[str, str]:
        """转换为字典"""
        return {
            'code': self.code,
            'path': self.path,
            'career': self.career,
            'equipment_type': self.equipment_type,
            'variation': self.variation
        }


@dataclass
class AvatarExtractStats:
    """Avatar 提取统计信息"""
    total_files: int = 0
    parsed_files: int = 0
    failed_files: int = 0
    start_time: float = field(default_factory=time.time)
    
    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time
    
    @property
    def success_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.parsed_files / self.total_files) * 100


class AvatarExtractor:
    """
    Avatar 数据提取器
    
    负责从 PVF 中提取 avatar（时装）装备数据：
    1. 解析 equipment.lst 获取 avatar 装备列表
    2. 批量获取 .equ 文件内容
    3. 提取 equipment_type 和 variation 标签
    4. 输出标准化的 avatar 数据
    """
    
    # Avatar 路径过滤关键字
    AVATAR_KEYWORDS = ['/avatar/', '/at_avatar/', ]  # 包含 avatar 但不包含 aura 的路径
    EXCLUDE_KEYWORDS = ['/aura/', '/weapon/']
    
    def __init__(
        self,
        host: str = PVF_API_HOST,
        port: int = PVF_API_PORT,
        timeout: int = PVF_API_TIMEOUT,
        batch_size: int = BATCH_SIZE,
        max_workers: int = MAX_WORKERS,
        max_retries: int = MAX_RETRIES
    ):
        """
        初始化提取器
        
        Args:
            host: API 主机地址
            port: API 端口
            timeout: 请求超时时间
            batch_size: 批处理大小
            max_workers: 最大线程数
            max_retries: 最大重试次数
        """
        self.base_url = f"http://{host}:{port}/Api/PvfUtiltiy" if port else f"http://{host}/Api/PvfUtiltiy"
        self.timeout = timeout
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.max_retries = max_retries
        
        # 预编译正则表达式
        self.equip_type_pattern = re.compile(EQUIP_TYPE_PATTERN, re.IGNORECASE | re.MULTILINE)
        self.variation_pattern = re.compile(VARIATION_PATTERN, re.IGNORECASE | re.MULTILINE)
        
        # 初始化 Session 池
        self.session_pool: List[requests.Session] = [
            self._create_session() for _ in range(max_workers)
        ]
        
        # 缓存和映射
        self.file_content_cache: Dict[str, str] = {}
        self.code_path_mapping: Dict[str, str] = {}
        self.path_code_mapping: Dict[str, str] = {}
        
        # 提取结果
        self.avatar_data: Dict[str, AvatarData] = {}
        
        # 统计
        self.stats = AvatarExtractStats()
    
    def _create_session(self) -> requests.Session:
        """创建配置好的 Session"""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=20
        )
        session.mount("http://", adapter)
        session.headers.update({"Connection": "keep-alive"})
        return session
    
    def _get_session(self) -> requests.Session:
        """轮询获取 Session"""
        session = self.session_pool.pop(0)
        self.session_pool.append(session)
        return session
    
    def _api_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Any = None
    ) -> Optional[Dict]:
        """
        发送 API 请求（带重试）
        
        Args:
            method: 请求方法
            endpoint: 端点
            params: URL 参数
            data: POST 数据
            
        Returns:
            响应数据或 None
        """
        url = f"{self.base_url}{endpoint}"
        session = self._get_session()
        
        for retry in range(self.max_retries):
            try:
                if method.upper() == "GET":
                    resp = session.get(url, params=params, timeout=self.timeout)
                elif method.upper() == "POST":
                    resp = session.post(
                        url, params=params,
                        data=json.dumps(data, ensure_ascii=False),
                        headers={"Content-Type": "application/json"},
                        timeout=self.timeout
                    )
                else:
                    logger.error(f"不支持的请求方法: {method}")
                    return None
                
                resp.raise_for_status()
                if not resp.content:
                    time.sleep(0.5)
                    continue
                
                result = resp.json()
                if result.get("IsError", True):
                    logger.error(f"API 错误: {result.get('Msg')}")
                    return None
                
                return result
                
            except Exception as e:
                if retry < self.max_retries - 1:
                    time.sleep(0.5)
                    continue
                logger.error(f"请求失败: {e}")
                return None
        
        return None
    
    def _is_avatar_path(self, path: str) -> bool:
        """
        检查路径是否为 avatar 装备
        
        Args:
            path: 装备路径
            
        Returns:
            True 如果是 avatar 装备
        """
        if not path.endswith('.equ'):
            return False
        
        # 必须包含 avatar 关键字
        if not any(kw in path for kw in self.AVATAR_KEYWORDS):
            return False
        
        # 排除 aura 光环
        if any(ex in path for ex in self.EXCLUDE_KEYWORDS):
            return False
        
        return True
    
    def _extract_career(self, path: str) -> str:
        """
        从路径中提取职业名称
        
        Args:
            path: 装备路径
            
        Returns:
            职业名称
        """
        path_parts = path.split('/')
        if len(path_parts) < 3:
            return 'unknown'
        
        career = path_parts[2]
        
        # 处理不同性别职业
        if 'at_avatar' in path or '/at_' in path:
            career = 'at ' + career
        return career
    
    def _normalize_equipment_type(self, equipment_type: str) -> str:
        """
        标准化 equipment_type 字符串
        
        Args:
            equipment_type: 原始 equipment_type
            
        Returns:
            标准化后的字符串
        """
        return equipment_type.replace('[', '').replace(' avatar]', '').strip()
    
    def _normalize_variation(self, variation: str) -> str:
        """
        标准化 variation 字符串
        
        Args:
            variation: 原始 variation
            
        Returns:
            标准化后的字符串
        """
        # 制表符统一替换为下划线
        if '\t' in variation:
            variation = '_'.join(variation.strip().split('\t'))
        return variation.strip()
    
    def _extract_tags_from_content(self, content: str) -> Tuple[str, str]:
        """
        从文件内容中提取 equipment_type 和 variation
        
        Args:
            content: 文件内容
            
        Returns:
            (equipment_type, variation) 元组
        """
        equipment_type = ""
        variation = ""
        
        # 使用正则提取
        equip_match = self.equip_type_pattern.search(content)
        if equip_match:
            equipment_type = equip_match.group(1).strip()
        
        var_match = self.variation_pattern.search(content)
        if var_match:
            variation = var_match.group(1).strip()
        
        # 备用：逐行解析 variation
        if not variation:
            lines = content.split('\r\n')
            for i, line in enumerate(lines):
                if line.strip().lower() == '[variation]':
                    if i + 1 < len(lines):
                        variation = lines[i + 1].strip()
                    break
        
        return self._normalize_equipment_type(equipment_type), self._normalize_variation(variation)
    
    def parse_equipment_lst(self, lst_file_path: str = "equipment/equipment.lst") -> bool:
        """
        解析 equipment.lst 文件，提取 avatar 装备列表
        
        Args:
            lst_file_path: lst 文件路径
            
        Returns:
            True 如果成功解析到有效记录
        """
        logger.info(f"解析 equipment.lst: {lst_file_path}")
        
        result = self._api_request(
            "POST", "/GetFileContents",
            data={
                "FileList": [lst_file_path],
                "UseCompatibleDecompiler": False,
                "EncodingType": "UTF8"
            }
        )
        
        if not result:
            logger.error("获取 lst 文件失败")
            return False
        
        content = result["Data"].get("FileContentData", {}).get(lst_file_path)
        if not content:
            logger.error("lst 文件内容为空")
            return False
        
        lines = content.split('\r\n')
        logger.info(f"lst 总行数: {len(lines)}")
        
        valid_count = 0
        for line_num, line in enumerate(lines, 1):
            clean_line = line.strip()
            if not clean_line:
                continue
            
            parts = clean_line.split('\t')
            if len(parts) < 2:
                logger.debug(f"第 {line_num} 行格式错误: [{clean_line}]")
                continue
            
            equ_code = parts[0].strip()
            equ_path = 'equipment/' + parts[1].strip().replace('`', '')
            
            # 过滤非数字 code
            if not equ_code.isdigit():
                continue
            
            # 过滤非 avatar 装备
            if not self._is_avatar_path(equ_path):
                continue
            
            self.code_path_mapping[equ_code] = equ_path
            self.path_code_mapping[equ_path] = equ_code
            valid_count += 1
        
        logger.info(f"解析完成: 有效 avatar 记录 {valid_count} 条")
        self.stats.total_files = valid_count
        return valid_count > 0
    
    def _process_batch(
        self,
        batch_items: List[Tuple[str, str]],
        batch_idx: int
    ) -> Tuple[int, Dict[str, AvatarData]]:
        """
        处理单个批次
        
        Args:
            batch_items: 批次中的 (code, path) 列表
            batch_idx: 批次索引
            
        Returns:
            (批次索引, 结果字典)
        """
        paths = [p for _, p in batch_items]
        batch_result: Dict[str, AvatarData] = {}
        
        # 处理缓存命中
        cache_hits = [(code, path) for code, path in batch_items if path in self.file_content_cache]
        for code, path in cache_hits:
            equipment_type, variation = self._extract_tags_from_content(self.file_content_cache[path])
            career = self._extract_career(path)
            batch_result[path] = AvatarData(
                code=code,
                path=path,
                career=career,
                equipment_type=equipment_type,
                variation=variation
            )
        
        # 处理缓存未命中
        cache_miss_paths = [p for _, p in batch_items if p not in self.file_content_cache]
        if cache_miss_paths:
            response = self._api_request(
                "POST", "/GetFileContents",
                data={
                    "FileList": cache_miss_paths,
                    "UseCompatibleDecompiler": False,
                    "EncodingType": "UTF8"
                }
            )
            
            if response and "Data" in response:
                contents = response["Data"].get("FileContentData", {})
                self.file_content_cache.update(contents)
                
                for code, path in batch_items:
                    if path not in [p for _, p in cache_hits]:
                        if path in contents:
                            equipment_type, variation = self._extract_tags_from_content(contents[path])
                            career = self._extract_career(path)
                            batch_result[path] = AvatarData(
                                code=code,
                                path=path,
                                career=career,
                                equipment_type=equipment_type,
                                variation=variation
                            )
                            self.stats.parsed_files += 1
                        else:
                            # API 未返回内容，创建空数据
                            career = self._extract_career(path)
                            batch_result[path] = AvatarData(
                                code=code,
                                path=path,
                                career=career,
                                equipment_type="",
                                variation=""
                            )
                            self.stats.failed_files += 1
            else:
                # API 失败，创建空数据
                for code, path in batch_items:
                    if path not in [p for _, p in cache_hits]:
                        career = self._extract_career(path)
                        batch_result[path] = AvatarData(
                            code=code,
                            path=path,
                            career=career,
                            equipment_type="",
                            variation=""
                        )
                        self.stats.failed_files += 1
        
        return batch_idx, batch_result
    
    def extract_all(self) -> Dict[str, AvatarData]:
        """
        批量提取所有 avatar 数据
        
        Returns:
            路径到 AvatarData 的映射字典
        """
        if not self.code_path_mapping:
            logger.error("无有效映射关系，请先调用 parse_equipment_lst()")
            return {}
        
        items = list(self.code_path_mapping.items())
        total_files = len(items)
        total_batches = (total_files + self.batch_size - 1) // self.batch_size
        
        logger.info(f"开始批量提取 {total_files} 个 avatar 文件（{total_batches} 批次）")
        
        # 创建批次
        batches = [
            (items[i:i + self.batch_size], i // self.batch_size)
            for i in range(0, total_files, self.batch_size)
        ]
        
        all_results: Dict[str, AvatarData] = {}
        processed_batches = 0
        
        # 多线程处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_batch = {
                executor.submit(self._process_batch, batch_items, batch_idx): (batch_items, batch_idx)
                for batch_items, batch_idx in batches
            }
            batch_results: Dict[int, Dict[str, AvatarData]] = {}
            
            for future in as_completed(future_to_batch):
                batch_idx, batch_result = future.result()
                batch_results[batch_idx] = batch_result
                processed_batches += 1
                
                if processed_batches % 10 == 0 or processed_batches == total_batches:
                    progress = (processed_batches / total_batches) * 100
                    # logger.info(f"进度: {processed_batches}/{total_batches} 批次 ({progress:.1f}%)")
        
        # 按顺序合并结果
        for batch_idx in sorted(batch_results.keys()):
            all_results.update(batch_results[batch_idx])
        
        self.avatar_data = all_results
        logger.info(f"批量提取完成: 成功 {len(all_results)} 个文件")
        return all_results
    
    def get_avatar_data(self, code: str) -> Optional[AvatarData]:
        """
        获取单个 avatar 数据
        
        Args:
            code: 装备代码
            
        Returns:
            AvatarData 对象，找不到返回 None
        """
        path = self.code_path_mapping.get(code)
        if not path:
            return None
        return self.avatar_data.get(path)
    
    def get_by_career(self, career: str) -> List[AvatarData]:
        """
        按职业获取 avatar 数据
        
        Args:
            career: 职业名称
            
        Returns:
            AvatarData 列表
        """
        return [data for data in self.avatar_data.values() if data.career == career]
    
    def get_by_equipment_type(self, equipment_type: str) -> List[AvatarData]:
        """
        按装备类型获取 avatar 数据
        
        Args:
            equipment_type: 装备类型（如 coat, pants 等）
            
        Returns:
            AvatarData 列表
        """
        return [data for data in self.avatar_data.values() if data.equipment_type == equipment_type]
    
    def save_to_tsv(self, output_file: Path) -> Path:
        """
        保存结果到 TSV 文件
        
        Args:
            output_file: 输出文件路径
            
        Returns:
            输出文件路径
        """
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        lines = ["code\tjob\tequipment type\tvariation\n"]
        
        for code in sorted(self.code_path_mapping.keys()):
            path = self.code_path_mapping[code]
            data = self.avatar_data.get(path)
            
            if data:
                lines.append(f"{code}\t{data.career}\t{data.equipment_type}\t{data.variation}\n")
            else:
                lines.append(f"{code}\t\t\t\n")
        
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            f.writelines(lines)
        
        logger.info(f"TSV 文件已保存: {output_file} ({len(lines) - 1} 条记录)")
        return output_file
    
    def save_to_json(self, output_file: Path) -> Path:
        """
        保存结果到 JSON 文件
        
        Args:
            output_file: 输出文件路径
            
        Returns:
            输出文件路径
        """
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        data_list = [data.to_dict() for data in self.avatar_data.values()]
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)
        
        logger.info(f"JSON 文件已保存: {output_file} ({len(data_list)} 条记录)")
        return output_file
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'total_files': self.stats.total_files,
            'parsed_files': self.stats.parsed_files,
            'failed_files': self.stats.failed_files,
            'success_rate': f"{self.stats.success_rate:.2f}%",
            'elapsed_time': f"{self.stats.elapsed_time:.2f}s"
        }
    
    def run(self, output_file: Optional[Path] = None) -> bool:
        """
        执行完整提取流程
        
        Args:
            output_file: 输出文件路径（可选）
            
        Returns:
            True 如果成功
        """
        try:
            # 1. 解析 lst
            if not self.parse_equipment_lst():
                logger.error("解析 lst 失败，终止")
                return False
            
            # 2. 批量提取 avatar 数据
            self.extract_all()
            
            # 3. 输出到 TSV（如果指定了输出路径）
            if output_file:
                self.save_to_tsv(output_file)
            
            # 4. 输出统计
            stats = self.get_stats()
            logger.info(
                f"\n提取流程完成:\n"
                f"  总文件数: {stats['total_files']}\n"
                f"  成功解析: {stats['parsed_files']}\n"
                f"  失败: {stats['failed_files']}\n"
                f"  成功率: {stats['success_rate']}\n"
                f"  耗时: {stats['elapsed_time']}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"流程异常: {e}", exc_info=True)
            return False


def extract_avatar_data(
    output_file: Optional[Path] = None,
    host: str = PVF_API_HOST,
    port: int = PVF_API_PORT
) -> Tuple[bool, Dict[str, AvatarData]]:
    """
    便捷的 avatar 数据提取函数
    
    Args:
        output_file: 输出文件路径（可选）
        host: API 主机地址
        port: API 端口
        
    Returns:
        (是否成功, avatar_data 字典)
    """
    extractor = AvatarExtractor(host=host, port=port)
    success = extractor.run(output_file=output_file)
    return success, extractor.avatar_data
