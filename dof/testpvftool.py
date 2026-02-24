import requests
import json
import re
import time
import logging
from typing import List, Dict, Optional, Any, Tuple
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("pvf_parser.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class PvfEquipmentParser:
    def __init__(self, host: str = "localhost", port: int = None):
        self.host = host
        self.port = port
        self.base_url = f"http://{self.host}:{self.port}/Api/PvfUtiltiy" if self.port else f"http://{self.host}/Api/PvfUtiltiy"
        self.timeout = 60
        self.batch_size = 15
        self.max_retries = 2
        self.max_workers = 3

        self.session_pool = [self._create_session() for _ in range(self.max_workers)]
        self.file_content_cache = {}
        self.code_path_mapping: Dict[str, str] = {}
        self.path_code_mapping: Dict[str, str] = {}

        self.equip_type_pattern = re.compile(r'\[equipment type\]\s*\n\s*`?([^`\t\r\n]+)`?\s*(\d+)?',
                                             re.IGNORECASE | re.MULTILINE)
        self.variation_pattern = re.compile(r'\[variation\]\s*\n\s*([^\r\n]+)', re.IGNORECASE | re.MULTILINE)

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(total=self.max_retries, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504],
                               allowed_methods=["GET", "POST"])
        session.mount("http://", HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20))
        session.headers.update({"Connection": "keep-alive"})
        return session

    def _get_session(self) -> requests.Session:
        session = self.session_pool.pop(0)
        self.session_pool.append(session)
        return session

    def _safe_request(self, method: str, endpoint: str, params: dict = None, data: Any = None) -> Optional[Dict]:
        url = f"{self.base_url}{endpoint}"
        session = self._get_session()

        for retry in range(self.max_retries):
            try:
                if method.upper() == "GET":
                    resp = session.get(url, params=params, timeout=self.timeout)
                elif method.upper() == "POST":
                    resp = session.post(url, params=params, data=json.dumps(data, ensure_ascii=False),
                                        headers={"Content-Type": "application/json"}, timeout=self.timeout)
                else:
                    logger.error(f"不支持的请求方法: {method}")
                    return None

                resp.raise_for_status()
                if not resp.content:
                    time.sleep(0.5)
                    continue

                result = resp.json()
                if result.get("IsError", True):
                    logger.error(f"接口错误: {result.get('Msg')}")
                    return None
                return result

            except Exception as e:
                if retry < self.max_retries - 1:
                    time.sleep(0.5)
                    continue
                logger.error(f"请求失败: {str(e)}")
                return None
        return None

    def parse_equipment_lst(self, lst_file_path: str = "equipment/equipment.lst") -> bool:
        logger.info(f"解析equipment.lst: {lst_file_path}")
        result = self._safe_request("POST", "/GetFileContents",
                                    data={"FileList": [lst_file_path], "UseCompatibleDecompiler": False,
                                          "EncodingType": "UTF8"})

        if not result or not result["Data"].get("FileContentData", {}).get(lst_file_path):
            logger.error("获取lst文件失败或内容为空")
            return False

        raw_lines = result["Data"]["FileContentData"][lst_file_path].split('\r\n')
        logger.info(f"lst总行数: {len(raw_lines)}")

        valid_count = 0
        for line_num, line in enumerate(raw_lines, 1):
            clean_line = line.strip()
            if not clean_line:
                continue

            parts = clean_line.split('\t')
            if len(parts) < 2:
                logger.warning(f"第{line_num}行格式错误: [{clean_line}]")
                continue

            equ_code = parts[0].strip()
            equ_path = 'equipment/' + parts[1].strip().replace('`', '')

            if not equ_code.isdigit() or not equ_path.endswith(
                    ".equ") or 'avatar' not in equ_path or '/aura/' in equ_path:
                continue

            self.code_path_mapping[equ_code] = equ_path
            self.path_code_mapping[equ_path] = equ_code
            valid_count += 1

        logger.info(f"解析完成：有效记录{valid_count}条")
        return valid_count > 0

    def extract_equipment_tags(self, file_content: str) -> Dict[str, str]:
        equip_type = self.equip_type_pattern.search(file_content).group(1).strip() if self.equip_type_pattern.search(
            file_content) else ""
        variation = self.variation_pattern.search(file_content).group(1).strip() if self.variation_pattern.search(
            file_content) else ""
        lines = file_content.split('\r\n')
        index = 0
        for line in lines:
            if line == '[variation]':
                variation = '_'.join(lines[index+1].strip().split('\t'))
                break
            index += 1


        # with open('test.txt', 'a+', encoding='utf-8') as f:
        #     f.write(f'{variation}, {variation.split('\t')}, =====\n')

        equip_type = equip_type.replace('[', '').replace(' avatar]', '')
        return {"equipment_type": equip_type, "variation": variation}

    def _process_single_batch(self, batch_files: List[str], batch_idx: int) -> Tuple[int, Dict[str, Dict[str, str]]]:
        batch_result = {}
        batch_success = 0

        for file_path in [f for f in batch_files if f in self.file_content_cache]:
            batch_result[file_path] = self.extract_equipment_tags(self.file_content_cache[file_path])
            batch_success += 1

        cache_miss_files = [f for f in batch_files if f not in self.file_content_cache]
        if cache_miss_files:
            file_contents = self._safe_request("POST", "/GetFileContents",
                                               data={"FileList": cache_miss_files, "UseCompatibleDecompiler": False,
                                                     "EncodingType": "UTF8"})
            if file_contents and "Data" in file_contents and "FileContentData" in file_contents["Data"]:
                self.file_content_cache.update(file_contents["Data"]["FileContentData"])
                for file_path in cache_miss_files:
                    if file_path in self.file_content_cache:
                        batch_result[file_path] = self.extract_equipment_tags(self.file_content_cache[file_path])
                        batch_success += 1
                    else:
                        batch_result[file_path] = {"equipment_type": "", "variation": ""}
            else:
                for file_path in cache_miss_files:
                    batch_result[file_path] = {"equipment_type": "", "variation": ""}

        # logger.info(f"批次 {batch_idx} 完成：成功 {batch_success}/{len(batch_files)}")
        return batch_idx, batch_result

    def batch_parse_equ_files(self) -> Dict[str, Dict[str, str]]:
        if not self.code_path_mapping:
            logger.error("无有效映射关系")
            return {}

        equ_file_paths = list(self.code_path_mapping.values())
        total_files = len(equ_file_paths)
        total_batches = (total_files + self.batch_size - 1) // self.batch_size
        # logger.info(f"批量解析{total_files}个.equ文件（{total_batches}批次）")

        batches = [(equ_file_paths[i:i + self.batch_size], i // self.batch_size + 1) for i in
                   range(0, total_files, self.batch_size)]
        all_results = {}
        processed_batches = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_batch = {executor.submit(self._process_single_batch, bf, bi): (bf, bi) for bf, bi in batches}
            batch_results = {}

            for future in as_completed(future_to_batch):
                batch_idx, batch_result = future.result()
                batch_results[batch_idx] = batch_result
                processed_batches += 1

                if processed_batches % 10 == 0 or processed_batches == total_batches:
                    logger.info(
                        f"进度：{processed_batches}/{total_batches} 批次 ({(processed_batches / total_batches) * 100:.1f}%)")

        for batch_idx in sorted(batch_results.keys()):
            all_results.update(batch_results[batch_idx])

        # logger.info(f"批量解析完成：成功{len(all_results)}个文件")
        return all_results

    def output_complete_tsv(self, equ_parse_results: Dict[str, Dict[str, str]],
                            output_file: str = "complete_equipment_tags.tsv"):
        # logger.info(f"生成TSV文件: {output_file}")
        output_lines = ["文件代码\t文件路径\tequipment type\tvariation\n"]

        for code in sorted(self.code_path_mapping.keys()):
            path = self.code_path_mapping[code]
            tags = equ_parse_results.get(path, {"equipment_type": "", "variation": ""})
            career = path.split('/')[2] if len(path.split('/')) >= 3 else path
            output_lines.append(f"{code}\t{career}\t{tags['equipment_type']}\t{tags['variation']}\n")

        with open(output_file, 'w', encoding='utf-8') as f:
            f.writelines(output_lines)

        logger.info("输出预览（前10行）：")
        for line in output_lines[:10]:
            print(line.strip())
        logger.info(f"TSV保存完成：{len(output_lines) - 1}条有效记录")

    def run_complete_parse(self):
        try:
            if not self.parse_equipment_lst():
                logger.error("解析lst失败，终止")
                return

            equ_results = self.batch_parse_equ_files()
            self.output_complete_tsv(equ_results)
            logger.info("解析流程执行完毕")

        except Exception as e:
            logger.error(f"流程异常：{str(e)}", exc_info=True)


if __name__ == "__main__":
    parser = PvfEquipmentParser(host="localhost", port=27000)
    parser.run_complete_parse()