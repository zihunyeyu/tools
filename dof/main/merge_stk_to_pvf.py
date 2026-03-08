"""
将生成的 stk.lst 和 stk 文件合并到 PVF 的 stackable/stackable.lst 中

用法:
    python merge_stk_to_pvf.py --dry-run              # 预览合并效果
    python merge_stk_to_pvf.py --pvf-path "D:/PVF"    # 执行实际合并
    python merge_stk_to_pvf.py --check-only           # 仅检查代码冲突
"""

import argparse
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Set, Tuple

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.pvf_api_client import PvfUtilityApi
from config import PVF_API_HOST, PVF_API_PORT, BASE_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StkLstMerger:
    """stk.lst 合并工具"""
    
    DEFAULT_STACKABLE_LST_PATH = "stackable/stackable.lst"
    DEFAULT_TARGET_SUBDIR = "stackable/avatar_gifts"
    
    def __init__(self, pvf_api: PvfUtilityApi = None, pvf_base_path: str = None):
        """
        初始化合并工具
        
        Args:
            pvf_api: PVF API 客户端
            pvf_base_path: PVF 基础路径（用于本地文件操作）
        """
        self._pvf_api = pvf_api
        self._pvf_base_path = Path(pvf_base_path) if pvf_base_path else None
        self._existing_codes: Set[str] = set()
        
    def load_pvf_stackable_lst(self) -> Dict[str, str]:
        """
        从 PVF 加载 stackable.lst
        
        Returns:
            {code: path} 字典
        """
        if self._pvf_api is None:
            logger.warning("PVF API 未初始化，无法加载 stackable.lst")
            return {}
        
        try:
            lst_info = self._pvf_api.get_lst_file_info(self.DEFAULT_STACKABLE_LST_PATH)
            # lst_info 格式: {code: {'FullPath': path, ...}, ...}
            result = {}
            for code, info in lst_info.items():
                if isinstance(info, dict) and 'FullPath' in info:
                    result[code] = info['FullPath']
                    self._existing_codes.add(code)
            logger.info(f"从 PVF 加载了 {len(result)} 条 stackable.lst 记录")
            return result
        except Exception as e:
            logger.error(f"加载 PVF stackable.lst 失败: {e}")
            return {}
    
    def parse_generated_stk_lst(self, stk_lst_path: Path) -> List[Tuple[str, str]]:
        """
        解析生成的 stk.lst 文件
        
        Args:
            stk_lst_path: stk.lst 文件路径
            
        Returns:
            [(code, path), ...] 列表
        """
        entries = []
        if not stk_lst_path.exists():
            logger.error(f"stk.lst 文件不存在: {stk_lst_path}")
            return entries
        
        with open(stk_lst_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t')
                if len(parts) >= 2:
                    code = parts[0]
                    path = parts[1].strip('`')
                    entries.append((code, path))
        
        logger.info(f"从 stk.lst 解析了 {len(entries)} 条记录")
        return entries
    
    def check_conflicts(self, entries: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """
        检查代码冲突
        
        Args:
            entries: [(code, path), ...] 列表
            
        Returns:
            冲突的条目列表
        """
        conflicts = []
        for code, path in entries:
            if code in self._existing_codes:
                conflicts.append((code, path))
        
        if conflicts:
            logger.warning(f"发现 {len(conflicts)} 个代码冲突:")
            for code, path in conflicts[:10]:
                logger.warning(f"  冲突: {code} -> {path}")
            if len(conflicts) > 10:
                logger.warning(f"  ... 还有 {len(conflicts) - 10} 个")
        else:
            logger.info("未发现代码冲突")
        
        return conflicts
    
    def keep_original_path(self, original_path: str) -> str:
        """
        保持原始路径格式（不进行转换）
        
        Args:
            original_path: 原始路径 (generated_gifts/sm/xxx.stk)
            
        Returns:
            原路径不变
        """
        return original_path
    
    def merge_to_pvf_api(self, entries: List[Tuple[str, str]], dry_run: bool = False) -> Tuple[int, int]:
        """
        使用 PVF API 合并到 PVF
        
        Args:
            entries: [(code, path), ...] 列表
            dry_run: 是否为预览模式
            
        Returns:
            (成功数, 失败数)
        """
        if self._pvf_api is None:
            logger.error("PVF API 未初始化")
            return 0, len(entries)
        
        success = 0
        failed = 0
        
        file_info_list = []
        
        for code, original_path in entries:
            # 转换路径
            target_path = self.convert_path(original_path)
            full_target_path = f"{self.DEFAULT_TARGET_SUBDIR}/{original_path.replace('generated_gifts/', '')}"
            
            # 读取 stk 文件内容
            stk_file_path = BASE_DIR / original_path
            if not stk_file_path.exists():
                logger.warning(f"stk 文件不存在: {stk_file_path}")
                failed += 1
                continue
            
            with open(stk_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if dry_run:
                logger.info(f"[预览] 将导入: {code} -> {full_target_path}")
                success += 1
            else:
                file_info_list.append({
                    "FilePath": full_target_path,
                    "FileContent": content
                })
        
        if not dry_run and file_info_list:
            try:
                failed_files = self._pvf_api.import_files(file_info_list)
                success = len(file_info_list) - len(failed_files)
                failed = len(failed_files)
                logger.info(f"导入完成: 成功 {success}, 失败 {failed}")
            except Exception as e:
                logger.error(f"导入失败: {e}")
                failed = len(file_info_list)
        
        return success, failed
    
    def generate_merged_stackable_lst(
        self, 
        entries: List[Tuple[str, str]], 
        output_path: Path,
        dry_run: bool = False
    ) -> bool:
        """
        生成合并后的 stackable.lst 文件
        
        将 PVF 原有的 stackable.lst 与生成的 stk.lst 合并，
        保持原始路径格式（generated_gifts/...）
        
        Args:
            entries: [(code, path), ...] 列表（新生成的条目）
            output_path: 输出文件路径
            dry_run: 是否为预览模式
            
        Returns:
            成功返回 True
        """
        try:
            # 获取 PVF 原有的 stackable.lst 内容
            existing_lines = []
            if self._pvf_api:
                try:
                    lst_info = self._pvf_api.get_lst_file_info(self.DEFAULT_STACKABLE_LST_PATH)
                    for code in sorted(lst_info.keys(), key=lambda x: int(x) if x.isdigit() else x):
                        info = lst_info[code]
                        if isinstance(info, dict) and 'FullPath' in info:
                            line = f"{code}\t`{info['FullPath']}`"
                            existing_lines.append(line)
                    logger.info(f"从 PVF 加载了 {len(existing_lines)} 条现有记录")
                except Exception as e:
                    logger.warning(f"从 PVF 加载 stackable.lst 失败: {e}")
            
            # 准备新条目（保持原路径格式）
            new_lines = []
            for code, original_path in entries:
                # 路径保持原样，不进行转换
                lst_line = f"{code}\t`{original_path}`"
                new_lines.append(lst_line)
            
            if dry_run:
                logger.info(f"[预览] 将生成合并后的 stackable.lst:")
                logger.info(f"[预览]   - 原有记录: {len(existing_lines)} 条")
                logger.info(f"[预览]   - 新增记录: {len(new_lines)} 条")
                logger.info(f"[预览]   - 总计: {len(existing_lines) + len(new_lines)} 条")
                logger.info(f"[预览]   - 输出路径: {output_path}")
                # 显示前5条示例
                logger.info(f"[预览]   - 示例条目:")
                for line in new_lines[:5]:
                    logger.info(f"[预览]     {line}")
                if len(new_lines) > 5:
                    logger.info(f"[预览]     ... 还有 {len(new_lines) - 5} 条")
                return True
            
            # 写入合并后的文件
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                # 写入原有记录
                for line in existing_lines:
                    f.write(line + '\n')
                # 写入新记录
                for line in new_lines:
                    f.write(line + '\n')
            
            logger.info(f"已生成合并后的 stackable.lst: {output_path}")
            logger.info(f"  - 原有记录: {len(existing_lines)} 条")
            logger.info(f"  - 新增记录: {len(new_lines)} 条")
            logger.info(f"  - 总计: {len(existing_lines) + len(new_lines)} 条")
            
            return True
            
        except Exception as e:
            logger.error(f"生成合并后的 stackable.lst 失败: {e}")
            return False
    
    def upload_merged_lst_to_pvf(self, merged_lst_path: Path) -> bool:
        """
        将合并后的 stackable.lst 上传到 PVF 替换原文件
        
        Args:
            merged_lst_path: 合并后的 lst 文件路径
            
        Returns:
            成功返回 True
        """
        if self._pvf_api is None:
            logger.error("PVF API 未初始化")
            return False
        
        try:
            with open(merged_lst_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 使用 import_files 导入合并后的 lst 文件
            file_info = [{
                "FilePath": self.DEFAULT_STACKABLE_LST_PATH,
                "FileContent": content
            }]
            
            failed = self._pvf_api.import_files(file_info)
            
            if failed:
                logger.error(f"上传 stackable.lst 失败: {failed}")
                return False
            else:
                logger.info(f"成功上传合并后的 stackable.lst 到 PVF")
                return True
                
        except Exception as e:
            logger.error(f"上传 stackable.lst 失败: {e}")
            return False
    
    def upload_stk_files_to_pvf(self, entries: List[Tuple[str, str]], 
                                 dry_run: bool = False) -> Tuple[int, int]:
        """
        上传 stk 文件到 PVF
        
        Args:
            entries: [(code, path), ...] 列表
            dry_run: 是否为预览模式
            
        Returns:
            (成功数, 失败数)
        """
        if self._pvf_api is None:
            logger.error("PVF API 未初始化")
            return 0, len(entries)
        
        success = 0
        failed = 0
        
        file_info_list = []
        
        for code, original_path in entries:
            # 路径保持原样
            full_target_path = original_path
            
            # 读取 stk 文件内容
            stk_file_path = BASE_DIR / original_path
            if not stk_file_path.exists():
                logger.warning(f"stk 文件不存在: {stk_file_path}")
                failed += 1
                continue
            
            with open(stk_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if dry_run:
                logger.info(f"[预览] 将导入 stk 文件: {code} -> {full_target_path}")
                success += 1
            else:
                file_info_list.append({
                    "FilePath": full_target_path,
                    "FileContent": content
                })
        
        if not dry_run and file_info_list:
            try:
                failed_files = self._pvf_api.import_files(file_info_list)
                success = len(file_info_list) - len(failed_files)
                failed = len(failed_files)
                logger.info(f"导入 stk 文件完成: 成功 {success}, 失败 {failed}")
            except Exception as e:
                logger.error(f"导入 stk 文件失败: {e}")
                failed = len(file_info_list)
        
        return success, failed


def main():
    parser = argparse.ArgumentParser(
        description='将生成的 stk.lst 合并到 PVF stackable.lst',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 预览合并效果（不实际修改）
  python merge_stk_to_pvf.py --dry-run

  # 仅检查代码冲突
  python merge_stk_to_pvf.py --check-only

  # 生成合并后的 stackable.lst 文件（默认操作）
  python merge_stk_to_pvf.py

  # 生成并上传到 PVF（替换原文件）
  python merge_stk_to_pvf.py --upload

  # 只上传 stk 文件，不替换 lst
  python merge_stk_to_pvf.py --upload-stk-only
        """
    )
    
    parser.add_argument('--stk-lst', 
                        default=str(BASE_DIR / 'output' / 'stk.lst'),
                        help='生成的 stk.lst 文件路径')
    
    parser.add_argument('--output',
                        default=str(BASE_DIR / 'output' / 'stackable.lst'),
                        help='合并后的 stackable.lst 输出路径')
    
    parser.add_argument('--upload', action='store_true',
                        help='上传到 PVF 替换原 stackable.lst（默认操作）')
    
    parser.add_argument('--upload-stk-only', action='store_true',
                        help='只上传 stk 文件，不替换 stackable.lst')
    
    parser.add_argument('--dry-run', action='store_true',
                        help='预览模式，不实际修改文件')
    
    parser.add_argument('--check-only', action='store_true',
                        help='仅检查代码冲突')
    
    parser.add_argument('--no-upload', action='store_true',
                        help='不上传到 PVF，只生成本地文件')
    
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='显示详细日志')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 创建合并工具（默认使用 PVF API）
    pvf_api = None
    if not args.no_upload or args.upload or args.upload_stk_only:
        try:
            pvf_api = PvfUtilityApi(host=PVF_API_HOST, port=PVF_API_PORT)
            logger.info("PVF API 连接成功")
        except Exception as e:
            logger.error(f"PVF API 连接失败: {e}")
            if not args.no_upload:
                logger.error("使用 --no-upload 参数可以只生成本地文件")
                return 1
    
    merger = StkLstMerger(pvf_api=pvf_api)
    
    # 解析生成的 stk.lst
    stk_lst_path = Path(args.stk_lst)
    entries = merger.parse_generated_stk_lst(stk_lst_path)
    
    if not entries:
        logger.error("没有条目需要合并")
        return 1
    
    print()
    print("=" * 70)
    print("合并信息")
    print("=" * 70)
    print(f"源文件: {stk_lst_path}")
    print(f"条目数: {len(entries)}")
    print(f"代码范围: {entries[0][0]} ~ {entries[-1][0]}")
    
    # 加载 PVF 现有代码检查冲突
    print()
    print("=" * 70)
    print("冲突检查")
    print("=" * 70)
    
    if pvf_api:
        merger.load_pvf_stackable_lst()
    
    conflicts = merger.check_conflicts(entries)
    
    if args.check_only:
        return 0 if not conflicts else 1
    
    if conflicts and not args.dry_run:
        print()
        response = input(f"发现 {len(conflicts)} 个冲突，是否继续? [y/N]: ")
        if response.lower() != 'y':
            logger.info("用户取消操作")
            return 0
    
    # 执行合并
    print()
    print("=" * 70)
    print("合并操作")
    print("=" * 70)
    
    # 1. 生成合并后的 stackable.lst 文件
    output_path = Path(args.output)
    success = merger.generate_merged_stackable_lst(
        entries, output_path, dry_run=args.dry_run
    )
    
    if not success:
        logger.error("生成合并后的 stackable.lst 失败")
        return 1
    
    # 2. 上传 stk 文件到 PVF
    stk_success, stk_failed = 0, 0
    if not args.no_upload:
        stk_success, stk_failed = merger.upload_stk_files_to_pvf(
            entries, dry_run=args.dry_run
        )
    
    # 3. 上传合并后的 stackable.lst 到 PVF（替换原文件）
    lst_uploaded = False
    if not args.no_upload and args.upload and not args.upload_stk_only:
        if not args.dry_run:
            lst_uploaded = merger.upload_merged_lst_to_pvf(output_path)
    
    print()
    print("=" * 70)
    print("合并结果")
    print("=" * 70)
    print(f"生成的文件: {output_path}")
    if not args.no_upload:
        print(f"STK 文件上传: 成功 {stk_success}, 失败 {stk_failed}")
        if args.upload and not args.upload_stk_only:
            if args.dry_run:
                print(f"Stackable.lst: [预览] 将上传到 PVF")
            elif lst_uploaded:
                print(f"Stackable.lst: ✓ 已上传到 PVF")
            else:
                print(f"Stackable.lst: ✗ 上传失败")
    
    if args.dry_run:
        print("\n[这是预览模式，没有实际修改文件]")
    else:
        print("\n✓ 合并完成!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
