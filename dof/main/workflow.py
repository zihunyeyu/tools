"""
Avatar Workflow - Avatar 完整工作流

实现从 NPK 解析到 Equ 文件生成的完整流程：
1. 解析 NPK 文件提取 Avatar 数据
2. 解析 PVF 获取 Avatar 标签数据
3. 生成缺少的 Equ 文件

Usage:
    from main.workflow import AvatarWorkflow, run_full_workflow
    
    # 方式1: 使用工作流类
    workflow = AvatarWorkflow()
    workflow.run_npk_extraction()
    workflow.run_pvf_extraction()
    workflow.run_equ_generation()
    
    # 方式2: 使用便捷函数
    run_full_workflow()
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

from config import (
    NPK_COMPILE_DIR,
    AVATAR_DATA_JSON,
    EQUIPMENT_TAGS_TSV,
    EQUIPMENT_LST,
    SHOP_ETC,
    PVF_API_HOST,
    PVF_API_PORT,
    EQU_GENERATION_CONFIG,
)

# 导入核心模块
from modules.avatar_extractor import AvatarExtractor
from modules.avatar_table_loader import AvatarTableLoader
from modules.pvf_api_client import PvfUtilityApi
from modules.equ_template_cache import EquTemplateCache

# 导入主程序逻辑
sys.path.insert(0, str(Path(__file__).parent))
from avatar_data_extractor_npk import AvatarDataExtractor
from avatar_data_extractor_pvf import extract_avatar_data
from equipment_code_generator import EquipmentCodeGenerator

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/workflow.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class WorkflowResult:
    """工作流执行结果"""
    success: bool = False
    stage: str = ""
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    
    def __bool__(self):
        return self.success


class AvatarWorkflow:
    """
    Avatar 完整工作流管理器
    
    管理从 NPK 解析到 Equ 生成的完整流程。
    """
    
    def __init__(
        self,
        npk_dir: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        use_pvf_api: bool = True
    ):
        """
        初始化工作流
        
        Args:
            npk_dir: NPK 文件目录，默认使用 config.NPK_COMPILE_DIR
            output_dir: 输出目录，默认使用项目 output/
            use_pvf_api: 是否使用 PVF API
        """
        self.npk_dir = npk_dir or NPK_COMPILE_DIR
        self.output_dir = output_dir or Path(__file__).parent.parent / "output"
        self.use_pvf_api = use_pvf_api
        
        # 初始化组件
        self.npk_extractor: Optional[AvatarDataExtractor] = None
        self.pvf_extractor: Optional[AvatarExtractor] = None
        self.equ_generator: Optional[EquipmentCodeGenerator] = None
        self.pvf_api: Optional[PvfUtilityApi] = None
        
        # 确保日志目录存在
        (Path(__file__).parent.parent / "logs").mkdir(exist_ok=True)
        
        logger.info(f"工作流初始化完成: npk_dir={self.npk_dir}")
    
    def _init_pvf_api(self) -> bool:
        """初始化 PVF API 客户端"""
        if not self.use_pvf_api:
            return False
        
        try:
            self.pvf_api = PvfUtilityApi(
                host=PVF_API_HOST,
                port=PVF_API_PORT
            )
            # 测试连接
            version = self.pvf_api.get_version()
            logger.info(f"PVF API 连接成功: {version}")
            return True
        except Exception as e:
            logger.warning(f"PVF API 连接失败: {e}")
            self.pvf_api = None
            return False
    
    def run_npk_extraction(
        self,
        output_json: Optional[Path] = None
    ) -> WorkflowResult:
        """
        阶段1: 从 NPK 提取 Avatar 数据
        
        Args:
            output_json: 输出 JSON 文件路径
            
        Returns:
            WorkflowResult
        """
        stage = "NPK提取"
        logger.info(f"[{stage}] 开始执行...")
        
        try:
            output_json = output_json or AVATAR_DATA_JSON
            
            # 创建提取器
            self.npk_extractor = AvatarDataExtractor(self.npk_dir)
            
            # 执行提取
            output_path = self.npk_extractor.save_to_json(output_json)
            
            # 获取统计
            stats = {
                'processed_files': self.npk_extractor._processed_files,
                'error_files': self.npk_extractor._error_files,
                'output_path': str(output_path)
            }
            
            logger.info(f"[{stage}] 完成: 处理 {stats['processed_files']} 个文件")
            
            return WorkflowResult(
                success=True,
                stage=stage,
                message=f"NPK提取成功: {output_path}",
                data=stats
            )
            
        except Exception as e:
            logger.error(f"[{stage}] 失败: {e}", exc_info=True)
            return WorkflowResult(
                success=False,
                stage=stage,
                message=f"NPK提取失败: {e}"
            )
    
    def run_pvf_extraction(
        self,
        output_tsv: Optional[Path] = None
    ) -> WorkflowResult:
        """
        阶段2: 从 PVF 提取 Avatar 标签数据
        
        Args:
            output_tsv: 输出 TSV 文件路径
            
        Returns:
            WorkflowResult
        """
        stage = "PVF提取"
        logger.info(f"[{stage}] 开始执行...")
        
        try:
            output_tsv = output_tsv or EQUIPMENT_TAGS_TSV
            
            # 使用 avatar_data_extractor_pvf 的函数
            success = extract_avatar_data(output_tsv)
            
            if success:
                logger.info(f"[{stage}] 完成: 输出到 {output_tsv}")
                return WorkflowResult(
                    success=True,
                    stage=stage,
                    message=f"PVF提取成功: {output_tsv}",
                    data={'output_path': str(output_tsv)}
                )
            else:
                raise RuntimeError("PVF提取返回失败")
                
        except Exception as e:
            logger.error(f"[{stage}] 失败: {e}", exc_info=True)
            return WorkflowResult(
                success=False,
                stage=stage,
                message=f"PVF提取失败: {e}"
            )
    
    def run_equ_generation(
        self,
        avatar_json: Optional[Path] = None,
        output_lst: Optional[Path] = None
    ) -> WorkflowResult:
        """
        阶段3: 生成 Equ 文件
        
        Args:
            avatar_json: Avatar 数据 JSON 文件路径
            output_lst: 输出的 equ.lst 文件路径
            
        Returns:
            WorkflowResult
        """
        stage = "Equ生成"
        logger.info(f"[{stage}] 开始执行...")
        
        try:
            avatar_json = avatar_json or AVATAR_DATA_JSON
            output_lst = output_lst or EQUIPMENT_LST
            
            # 检查输入文件
            if not avatar_json.exists():
                raise FileNotFoundError(f"Avatar数据文件不存在: {avatar_json}")
            
            # 初始化 PVF API（如果需要）
            if self.use_pvf_api and not self.pvf_api:
                self._init_pvf_api()
            
            # 创建生成器
            self.equ_generator = EquipmentCodeGenerator()
            
            # 生成 equ 文件（使用 config 中的配置）
            result = self.equ_generator.generate(
                json_path=avatar_json,
                output_path=output_lst,
                write_equ_to_local=EQU_GENERATION_CONFIG.get("write_equ_to_local", True),
                import_to_pvf=EQU_GENERATION_CONFIG.get("import_to_pvf", False)
            )
            
            stats = {
                'total': result.get('total', 0),
                'success': result.get('success', 0),
                'failed': result.get('failed', 0),
                'lst_path': str(output_lst)
            }
            
            logger.info(f"[{stage}] 完成: 总计 {stats['total']}, 成功 {stats['success']}")
            
            return WorkflowResult(
                success=True,
                stage=stage,
                message=f"Equ生成成功: {stats['success']}/{stats['total']}",
                data=stats
            )
            
        except Exception as e:
            logger.error(f"[{stage}] 失败: {e}", exc_info=True)
            return WorkflowResult(
                success=False,
                stage=stage,
                message=f"Equ生成失败: {e}"
            )
    
    def run_full_workflow(
        self,
        skip_npk: bool = False,
        skip_pvf: bool = False,
        skip_equ: bool = False
    ) -> Dict[str, WorkflowResult]:
        """
        执行完整工作流
        
        Args:
            skip_npk: 跳过 NPK 提取
            skip_pvf: 跳过 PVF 提取
            skip_equ: 跳过 Equ 生成
            
        Returns:
            各阶段结果字典
        """
        results = {}
        
        logger.info("="*60)
        logger.info("开始执行完整 Avatar 工作流")
        logger.info("="*60)
        
        # 阶段1: NPK提取
        if not skip_npk:
            results['npk'] = self.run_npk_extraction()
            if not results['npk']:
                logger.error("NPK提取失败，终止工作流")
                return results
        else:
            logger.info("跳过 NPK 提取阶段")
            results['npk'] = WorkflowResult(success=True, stage="NPK提取", message="已跳过")
        
        # 阶段2: PVF提取
        if not skip_pvf:
            results['pvf'] = self.run_pvf_extraction()
            if not results['pvf']:
                logger.error("PVF提取失败，终止工作流")
                return results
        else:
            logger.info("跳过 PVF 提取阶段")
            results['pvf'] = WorkflowResult(success=True, stage="PVF提取", message="已跳过")
        
        # 阶段3: Equ生成
        if not skip_equ:
            results['equ'] = self.run_equ_generation()
            if not results['equ']:
                logger.error("Equ生成失败，但工作流继续")
        else:
            logger.info("跳过 Equ 生成阶段")
            results['equ'] = WorkflowResult(success=True, stage="Equ生成", message="已跳过")
        
        # 汇总
        logger.info("="*60)
        logger.info("工作流执行完成")
        for stage, result in results.items():
            status = "✓" if result.success else "✗"
            logger.info(f"  [{status}] {result.stage}: {result.message}")
        logger.info("="*60)
        
        return results


def run_full_workflow(
    npk_dir: Optional[Path] = None,
    skip_npk: bool = False,
    skip_pvf: bool = False,
    skip_equ: bool = False
) -> Dict[str, WorkflowResult]:
    """
    便捷的完整工作流执行函数
    
    Args:
        npk_dir: NPK 文件目录
        skip_npk: 跳过 NPK 提取
        skip_pvf: 跳过 PVF 提取
        skip_equ: 跳过 Equ 生成
        
    Returns:
        各阶段结果字典
        
    Example:
        >>> from main.workflow import run_full_workflow
        >>> results = run_full_workflow()
        >>> if results['equ'].success:
        ...     print("Equ生成成功！")
    """
    workflow = AvatarWorkflow(npk_dir=npk_dir)
    return workflow.run_full_workflow(
        skip_npk=skip_npk,
        skip_pvf=skip_pvf,
        skip_equ=skip_equ
    )


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Avatar 完整工作流 - NPK提取 -> PVF提取 -> Equ生成',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 执行完整工作流
  python -m main.workflow
  
  # 跳过 NPK 提取（使用现有 JSON）
  python -m main.workflow --skip-npk
  
  # 跳过 PVF 提取
  python -m main.workflow --skip-pvf
  
  # 只生成 Equ 文件
  python -m main.workflow --skip-npk --skip-pvf
  
  # 指定 NPK 目录
  python -m main.workflow --npk-dir "D:\\DOF\\AVATAR\\NPK"
        """
    )
    
    parser.add_argument(
        '--npk-dir',
        type=str,
        default=None,
        help='NPK 文件目录'
    )
    
    parser.add_argument(
        '--skip-npk',
        action='store_true',
        help='跳过 NPK 提取阶段'
    )
    
    parser.add_argument(
        '--skip-pvf',
        action='store_true',
        help='跳过 PVF 提取阶段'
    )
    
    parser.add_argument(
        '--skip-equ',
        action='store_true',
        help='跳过 Equ 生成阶段'
    )
    
    args = parser.parse_args()
    
    npk_dir = Path(args.npk_dir) if args.npk_dir else None
    
    # 执行工作流
    results = run_full_workflow(
        npk_dir=npk_dir,
        skip_npk=args.skip_npk,
        skip_pvf=args.skip_pvf,
        skip_equ=args.skip_equ
    )
    
    # 检查最终结果
    all_success = all(r.success for r in results.values())
    
    if all_success:
        print("\n✓ 工作流执行成功！")
        return 0
    else:
        print("\n✗ 工作流执行失败")
        for stage, result in results.items():
            if not result.success:
                print(f"  - {stage}: {result.message}")
        return 1


if __name__ == "__main__":
    exit(main())
