"""
Equ Template Cache Manager - Equ 模板缓存管理器

从 equ_models.py 中定义的指定装备代码获取 equ 文件模板，
并将这些模板序列化保存为本地资源，避免每次重新从 PVF 读取。
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, asdict

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from model.equ_models import equ_model
from modules.pvf_api_client import PvfUtilityApi, PvfApiError
from config import PVF_API_HOST, PVF_API_PORT, BASE_DIR

logger = logging.getLogger(__name__)

# 默认缓存文件路径
DEFAULT_CACHE_PATH = BASE_DIR / "data" / "equ_templates_cache.json"


@dataclass
class EquTemplate:
    """Equ 模板数据结构"""
    job: str                    # 职业代码 (sm, ft, etc.)
    part: str                   # 部位名称 (coat, pants, etc.)
    code: str                   # 装备代码
    file_path: str              # PVF 中的文件路径
    content: str                # 文件内容
    version: int = 1            # 缓存版本号，用于兼容性控制


class EquTemplateCache:
    """
    Equ 模板缓存管理器
    
    功能：
    1. 从 PVF 获取 equ_models.py 中定义的指定代码对应的 equ 文件
    2. 将模板序列化保存到本地 JSON 文件
    3. 提供模板查询和获取接口
    4. 支持缓存刷新和版本控制
    """
    
    CACHE_VERSION = 1  # 缓存版本号
    
    def __init__(
        self,
        cache_path: Optional[Path] = None,
        pvf_api: Optional[PvfUtilityApi] = None
    ):
        """
        初始化缓存管理器
        
        Args:
            cache_path: 缓存文件路径，None 则使用默认路径
            pvf_api: PVF API 客户端，None 则自动创建
        """
        self._cache_path = Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._pvf_api = pvf_api
        self._templates: Dict[str, EquTemplate] = {}  # key: "job_part"
        self._loaded = False
        
        # 尝试加载缓存
        self._load_cache()
    
    def _get_template_key(self, job: str, part: str) -> str:
        """获取模板键"""
        return f"{job}_{part}"
    
    def _load_cache(self) -> bool:
        """
        从本地文件加载缓存
        
        Returns:
            True 如果成功加载有效缓存
        """
        if not self._cache_path.exists():
            logger.info(f"缓存文件不存在: {self._cache_path}")
            return False
        
        try:
            with open(self._cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查缓存版本
            cache_version = data.get('version', 0)
            if cache_version != self.CACHE_VERSION:
                logger.warning(f"缓存版本不匹配: {cache_version} != {self.CACHE_VERSION}，需要刷新")
                return False
            
            # 加载模板数据
            templates_data = data.get('templates', {})
            for key, template_dict in templates_data.items():
                self._templates[key] = EquTemplate(**template_dict)
            
            self._loaded = True
            logger.info(f"成功从缓存加载 {len(self._templates)} 个模板")
            return True
            
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(f"加载缓存失败: {e}，将重新生成")
            self._templates.clear()
            return False
    
    def _save_cache(self) -> bool:
        """
        保存缓存到本地文件
        
        Returns:
            True 如果保存成功
        """
        try:
            data = {
                'version': self.CACHE_VERSION,
                'templates': {
                    key: asdict(template) 
                    for key, template in self._templates.items()
                }
            }
            
            with open(self._cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"成功保存 {len(self._templates)} 个模板到缓存: {self._cache_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存缓存失败: {e}")
            return False
    
    def _ensure_pvf_api(self) -> bool:
        """
        确保 PVF API 客户端可用
        
        Returns:
            True 如果 API 可用
        """
        if self._pvf_api is None:
            try:
                self._pvf_api = PvfUtilityApi(host=PVF_API_HOST, port=PVF_API_PORT)
            except Exception as e:
                logger.error(f"无法创建 PVF API 客户端: {e}")
                return False
        return True
    
    def _get_equ_file_path(self, code: str) -> Optional[str]:
        """
        从 equipment.lst 获取指定代码的文件路径
        
        Args:
            code: 装备代码
            
        Returns:
            文件路径，如果找不到则返回 None
        """
        if not self._ensure_pvf_api():
            return None
        
        try:
            lst_info = self._pvf_api.get_lst_file_info('equipment/equipment.lst')
            
            for code_str, info in lst_info.items():
                if code_str == code and isinstance(info, dict):
                    full_path = info.get('FullPath', '')
                    if full_path:
                        logger.debug(f"找到代码 {code} 的路径: {full_path}")
                        return full_path
            
            logger.warning(f"在 equipment.lst 中找不到代码: {code}")
            return None
            
        except Exception as e:
            logger.error(f"获取文件路径失败 {code}: {e}")
            return None
    
    def _fetch_template_from_pvf(
        self, 
        job: str, 
        part: str, 
        code: str
    ) -> Optional[EquTemplate]:
        """
        从 PVF 获取单个模板
        
        Args:
            job: 职业代码
            part: 部位名称
            code: 装备代码
            
        Returns:
            EquTemplate 对象，如果获取失败则返回 None
        """
        if not self._ensure_pvf_api():
            return None
        
        # 获取文件路径
        file_path = self._get_equ_file_path(code)
        if not file_path:
            return None
        
        # 获取文件内容
        try:
            content = self._pvf_api.get_file_content(file_path)
            logger.debug(f"成功获取模板: {job}/{part} ({code})")
            
            return EquTemplate(
                job=job,
                part=part,
                code=code,
                file_path=file_path,
                content=content
            )
            
        except Exception as e:
            logger.error(f"获取文件内容失败 {file_path}: {e}")
            return None
    
    def refresh_cache(self, force: bool = False) -> Tuple[int, int]:
        """
        刷新缓存，从 PVF 获取所有模板
        
        Args:
            force: 是否强制刷新（即使缓存已存在）
            
        Returns:
            (成功数量, 失败数量)
        """
        if self._loaded and not force and self._templates:
            logger.info("缓存已存在，使用已有缓存（如需刷新请设置 force=True）")
            return len(self._templates), 0
        
        if not self._ensure_pvf_api():
            logger.error("PVF API 不可用，无法刷新缓存")
            return 0, len(equ_model) * 9  # 9 个部位
        
        success_count = 0
        fail_count = 0
        
        # 清空现有缓存
        self._templates.clear()
        
        # 遍历 equ_model 中定义的所有职业和部位
        for job, parts in equ_model.items():
            for part, code in parts.items():
                template = self._fetch_template_from_pvf(job, part, code)
                if template:
                    key = self._get_template_key(job, part)
                    self._templates[key] = template
                    success_count += 1
                else:
                    logger.warning(f"获取模板失败: {job}/{part} ({code})")
                    fail_count += 1
        
        # 保存到文件
        if success_count > 0:
            self._save_cache()
            self._loaded = True
        
        logger.info(f"缓存刷新完成: 成功 {success_count}, 失败 {fail_count}")
        return success_count, fail_count
    
    def get_template(self, job: str, part: str) -> Optional[EquTemplate]:
        """
        获取指定职业和部位的模板
        
        Args:
            job: 职业代码 (sm, ft, etc.)
            part: 部位名称 (coat, pants, etc.)
            
        Returns:
            EquTemplate 对象，如果不存在则返回 None
        """
        key = self._get_template_key(job, part)
        
        # 如果缓存未加载，尝试加载
        if not self._loaded:
            self._load_cache()
        
        # 如果仍然没有，尝试从 PVF 获取
        if key not in self._templates:
            logger.info(f"缓存中不存在 {key}，尝试从 PVF 获取")
            if job in equ_model and part in equ_model[job]:
                code = equ_model[job][part]
                template = self._fetch_template_from_pvf(job, part, code)
                if template:
                    self._templates[key] = template
                    self._save_cache()
        
        return self._templates.get(key)
    
    def get_template_content(self, job: str, part: str) -> Optional[str]:
        """
        获取指定职业和部位的模板内容
        
        Args:
            job: 职业代码
            part: 部位名称
            
        Returns:
            模板内容字符串，如果不存在则返回 None
        """
        template = self.get_template(job, part)
        return template.content if template else None
    
    def get_all_templates(self) -> Dict[str, EquTemplate]:
        """
        获取所有模板
        
        Returns:
            模板字典，key 为 "job_part"
        """
        if not self._loaded:
            self._load_cache()
        return self._templates.copy()
    
    def is_cached(self, job: str, part: str) -> bool:
        """
        检查指定模板是否已缓存
        
        Args:
            job: 职业代码
            part: 部位名称
            
        Returns:
            True 如果已缓存
        """
        key = self._get_template_key(job, part)
        if not self._loaded:
            self._load_cache()
        return key in self._templates
    
    def clear_cache(self) -> bool:
        """
        清除缓存
        
        Returns:
            True 如果清除成功
        """
        self._templates.clear()
        self._loaded = False
        
        try:
            if self._cache_path.exists():
                self._cache_path.unlink()
                logger.info(f"已删除缓存文件: {self._cache_path}")
            return True
        except Exception as e:
            logger.error(f"删除缓存文件失败: {e}")
            return False
    
    def get_cache_info(self) -> Dict:
        """
        获取缓存信息
        
        Returns:
            包含缓存统计信息的字典
        """
        if not self._loaded:
            self._load_cache()
        
        # 统计各职业的模板数量
        job_counts = {}
        for key, template in self._templates.items():
            job = template.job
            job_counts[job] = job_counts.get(job, 0) + 1
        
        return {
            'cache_version': self.CACHE_VERSION,
            'cache_path': str(self._cache_path),
            'loaded': self._loaded,
            'total_templates': len(self._templates),
            'job_counts': job_counts,
            'expected_total': sum(len(parts) for parts in equ_model.values()),
        }


def init_template_cache(force_refresh: bool = False) -> EquTemplateCache:
    """
    初始化模板缓存（便捷函数）
    
    Args:
        force_refresh: 是否强制刷新缓存
        
    Returns:
        EquTemplateCache 实例
    """
    cache = EquTemplateCache()
    
    if force_refresh or not cache._loaded:
        success, fail = cache.refresh_cache(force=force_refresh)
        if fail > 0:
            logger.warning(f"部分模板获取失败: {fail} 个")
    
    return cache


def main():
    """主入口：用于手动刷新缓存"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Equ 模板缓存管理工具')
    parser.add_argument('--refresh', '-r', action='store_true', help='强制刷新缓存')
    parser.add_argument('--clear', '-c', action='store_true', help='清除缓存')
    parser.add_argument('--info', '-i', action='store_true', help='显示缓存信息')
    parser.add_argument('--list', '-l', action='store_true', help='列出所有模板')
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    cache = EquTemplateCache()
    
    if args.clear:
        cache.clear_cache()
        print("缓存已清除")
        return
    
    if args.refresh:
        success, fail = cache.refresh_cache(force=True)
        print(f"\n缓存刷新完成: 成功 {success}, 失败 {fail}")
        return
    
    if args.info or args.list or (not args.clear and not args.refresh):
        info = cache.get_cache_info()
        print("\n缓存信息:")
        print(f"  缓存版本: {info['cache_version']}")
        print(f"  缓存路径: {info['cache_path']}")
        print(f"  已加载: {info['loaded']}")
        print(f"  模板数量: {info['total_templates']} / {info['expected_total']}")
        
        if info['job_counts']:
            print("\n各职业模板数量:")
            for job, count in sorted(info['job_counts'].items()):
                job_name = {
                    'sm': '鬼剑士', 'ft': '格斗家(男)', 'fm': '格斗家(女)',
                    'gn': '神枪手(男)', 'gg': '神枪手(女)', 'mg': '魔法师(男)',
                    'mm': '魔法师(女)', 'pr': '圣职者', 'th': '盗贼'
                }.get(job, job)
                print(f"    {job} ({job_name}): {count}")
        
        if args.list and cache._templates:
            print("\n模板列表:")
            for key, template in sorted(cache._templates.items()):
                print(f"  {key}: code={template.code}, path={template.file_path}")


if __name__ == "__main__":
    main()
