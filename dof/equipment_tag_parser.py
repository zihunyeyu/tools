"""
Equipment Tag Parser - 装备标签解析器

批量解析 PVF 中的装备文件并提取标签信息。
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

from config import (
    PVF_API_HOST, PVF_API_PORT, PVF_API_TIMEOUT,
    BATCH_SIZE, MAX_WORKERS, MAX_RETRIES,
    EQUIP_TYPE_PATTERN, VARIATION_PATTERN,
    EQUIPMENT_TAGS_TSV
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("pvf_parser.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class EquipmentTags:
    """装备标签数据类"""
    equipment_type: str = ""
    variation: str = ""
    
    def normalize(self) -> None:
        """标准化数据"""
        self.equipment_type = self.equipment_type.replace('[', '').replace(' avatar]', '').strip()
        # variation 中的制表符统一替换为下划线
        if '\t' in self.variation:
            self.variation = '_'.join(self.variation.strip().split('\t'))


@dataclass 
class ParseStats:
    """解析统计信息"""
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


class PvfEquipmentParser:
    """PVF 装备标签解析器"""
    
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
        初始化解析器
        
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
        
        # 缓存
        self.file_content_cache: Dict[str, str] = {}
        self.code_path_mapping: Dict[str, str] = {}
        self.path_code_mapping: Dict[str, str] = {}
        
        # 统计
        self.stats = ParseStats()
    
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
    
    def parse_equipment_lst(self, lst_file_path: str = "equipment/equipment.lst") -> bool:
        """
        解析 equipment.lst 文件
        
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
            
            # 过滤非 avatar 或 aura 装备
            if (not equ_code.isdigit() 
                or not equ_path.endswith(".equ")
                or 'avatar' not in equ_path 
                or '/aura/' in equ_path):
                continue
            
            self.code_path_mapping[equ_code] = equ_path
            self.path_code_mapping[equ_path] = equ_code
            valid_count += 1
        
        logger.info(f"解析完成: 有效记录 {valid_count} 条")
        self.stats.total_files = valid_count
        return valid_count > 0
    
    def extract_equipment_tags(self, file_content: str) -> EquipmentTags:
        """
        从文件内容中提取装备标签
        
        Args:
            file_content: 文件内容
            
        Returns:
            装备标签对象
        """
        tags = EquipmentTags()
        
        # 使用正则提取
        equip_match = self.equip_type_pattern.search(file_content)
        if equip_match:
            tags.equipment_type = equip_match.group(1).strip()
        
        var_match = self.variation_pattern.search(file_content)
        if var_match:
            tags.variation = var_match.group(1).strip()
        
        # 备用：逐行解析 variation
        if not tags.variation:
            lines = file_content.split('\r\n')
            for i, line in enumerate(lines):
                if line.strip().lower() == '[variation]':
                    if i + 1 < len(lines):
                        tags.variation = lines[i + 1].strip()
                    break
        
        tags.normalize()
        return tags
    
    def _process_batch(
        self,
        batch_files: List[str],
        batch_idx: int
    ) -> Tuple[int, Dict[str, EquipmentTags]]:
        """
        处理单个批次
        
        Args:
            batch_files: 批次中的文件列表
            batch_idx: 批次索引
            
        Returns:
            (批次索引, 结果字典)
        """
        batch_result: Dict[str, EquipmentTags] = {}
        
        # 处理缓存命中
        cache_hits = [f for f in batch_files if f in self.file_content_cache]
        for file_path in cache_hits:
            batch_result[file_path] = self.extract_equipment_tags(
                self.file_content_cache[file_path]
            )
        
        # 处理缓存未命中
        cache_miss = [f for f in batch_files if f not in self.file_content_cache]
        if cache_miss:
            response = self._api_request(
                "POST", "/GetFileContents",
                data={
                    "FileList": cache_miss,
                    "UseCompatibleDecompiler": False,
                    "EncodingType": "UTF8"
                }
            )
            
            if response and "Data" in response:
                contents = response["Data"].get("FileContentData", {})
                self.file_content_cache.update(contents)
                
                for file_path in cache_miss:
                    if file_path in contents:
                        batch_result[file_path] = self.extract_equipment_tags(
                            contents[file_path]
                        )
                    else:
                        batch_result[file_path] = EquipmentTags()
                        self.stats.failed_files += 1
            else:
                # API 失败，返回空标签
                for file_path in cache_miss:
                    batch_result[file_path] = EquipmentTags()
                    self.stats.failed_files += 1
        
        self.stats.parsed_files += len(batch_result)
        return batch_idx, batch_result
    
    def batch_parse_equ_files(self) -> Dict[str, EquipmentTags]:
        """
        批量解析所有 .equ 文件
        
        Returns:
            文件路径到标签的映射
        """
        if not self.code_path_mapping:
            logger.error("无有效映射关系")
            return {}
        
        equ_file_paths = list(self.code_path_mapping.values())
        total_files = len(equ_file_paths)
        total_batches = (total_files + self.batch_size - 1) // self.batch_size
        
        logger.info(f"开始批量解析 {total_files} 个 .equ 文件（{total_batches} 批次）")
        
        # 创建批次
        batches = [
            (equ_file_paths[i:i + self.batch_size], i // self.batch_size + 1)
            for i in range(0, total_files, self.batch_size)
        ]
        
        all_results: Dict[str, EquipmentTags] = {}
        processed_batches = 0
        
        # 多线程处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_batch = {
                executor.submit(self._process_batch, bf, bi): (bf, bi)
                for bf, bi in batches
            }
            batch_results: Dict[int, Dict[str, EquipmentTags]] = {}
            
            for future in as_completed(future_to_batch):
                batch_idx, batch_result = future.result()
                batch_results[batch_idx] = batch_result
                processed_batches += 1
                
                if processed_batches % 10 == 0 or processed_batches == total_batches:
                    progress = (processed_batches / total_batches) * 100
                    logger.info(f"进度: {processed_batches}/{total_batches} 批次 ({progress:.1f}%)")
        
        # 按顺序合并结果
        for batch_idx in sorted(batch_results.keys()):
            all_results.update(batch_results[batch_idx])
        
        logger.info(f"批量解析完成: 成功 {len(all_results)} 个文件")
        return all_results
    
    def output_to_tsv(
        self,
        equ_parse_results: Dict[str, EquipmentTags],
        output_file: Path = EQUIPMENT_TAGS_TSV
    ) -> Path:
        """
        输出到 TSV 文件
        
        Args:
            equ_parse_results: 解析结果
            output_file: 输出文件路径
            
        Returns:
            输出文件路径
        """
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        lines = ["文件代码\t文件路径\tequipment type\tvariation\n"]
        
        for code in sorted(self.code_path_mapping.keys()):
            path = self.code_path_mapping[code]
            tags = equ_parse_results.get(path, EquipmentTags())
            
            # 提取职业名称
            path_parts = path.split('/')
            career = path_parts[2] if len(path_parts) >= 3 else path
            
            lines.append(f"{code}\t{career}\t{tags.equipment_type}\t{tags.variation}\n")
        
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            f.writelines(lines)
        
        logger.info(f"TSV 文件已保存: {output_file} ({len(lines) - 1} 条记录)")
        
        # 显示前 10 行预览
        logger.info("输出预览（前 10 行）:")
        for line in lines[:min(10, len(lines))]:
            print(f"  {line.strip()}")
        
        return output_file
    
    def run(self, output_file: Path = EQUIPMENT_TAGS_TSV) -> bool:
        """
        执行完整解析流程
        
        Args:
            output_file: 输出文件路径
            
        Returns:
            True 如果成功
        """
        try:
            # 1. 解析 lst
            if not self.parse_equipment_lst():
                logger.error("解析 lst 失败，终止")
                return False
            
            # 2. 批量解析装备文件
            equ_results = self.batch_parse_equ_files()
            
            # 3. 输出到 TSV
            self.output_to_tsv(equ_results, output_file)
            
            # 4. 输出统计
            logger.info(
                f"\n解析流程完成:\n"
                f"  总文件数: {self.stats.total_files}\n"
                f"  成功解析: {self.stats.parsed_files}\n"
                f"  失败: {self.stats.failed_files}\n"
                f"  成功率: {self.stats.success_rate:.2f}%\n"
                f"  耗时: {self.stats.elapsed_time:.2f} 秒"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"流程异常: {e}", exc_info=True)
            return False


def main():
    """主入口"""
    parser = PvfEquipmentParser()
    success = parser.run()
    
    if success:
        print("\n✓ 解析完成")
    else:
        print("\n✗ 解析失败")
        exit(1)


if __name__ == "__main__":
    main()
