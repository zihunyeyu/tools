"""
Batch Gift Package Generator - 批量礼包文件生成器

根据 equ_models.py 中的 job_chinese 定义，为所有职业批量生成礼包文件。
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from main.gift_package_generator import GiftPackageGenerator, JOB_TO_TSV_PATH
from model.equ_models import job_chinese

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def generate_all_jobs(
    base_path: str = r'E:\DOF\Tools\blackcat.6.12\output\Avatar',
    tsv_path: str = None,
    output_base: str = 'output/cash/additional',
    stk_lst_path: str = 'output/stk.lst',
    suit_filter: str = None,
    use_pvf: bool = True
) -> dict:
    """
    为所有职业生成礼包文件
    
    Args:
        base_path: 装扮表文件基础路径
        tsv_path: TSV 文件路径
        output_base: 输出基础目录
        stk_lst_path: stk.lst 输出路径
        suit_filter: 套装名称过滤（可选）
        use_pvf: 是否从PVF读取stackable.lst
        
    Returns:
        {job: {suit_name: success}} 嵌套字典
    """
    if tsv_path is None:
        tsv_path = Path(__file__).parent / "output" / "complete_equipment_tags.tsv"
    
    # 创建PVF API客户端（如果可用且启用）
    pvf_api = None
    if use_pvf:
        try:
            from pvf_api_client import PvfUtilityApi
            from config import PVF_API_HOST, PVF_API_PORT
            pvf_api = PvfUtilityApi(host=PVF_API_HOST, port=PVF_API_PORT)
            logger.info("PVF API 客户端初始化成功")
        except Exception as e:
            logger.warning(f"PVF API 客户端初始化失败: {e}，使用默认起始code")
    
    # 创建生成器
    generator = GiftPackageGenerator(base_path, tsv_path, pvf_api)
    
    # 获取所有职业
    jobs = list(job_chinese.keys())
    logger.info(f"开始为 {len(jobs)} 个职业生成礼包文件")
    logger.info(f"职业列表: {', '.join(jobs)}")
    
    all_results = {}
    total_suits = 0
    success_suits = 0
    
    for job in jobs:
        print("=" * 70)
        print(f"处理职业: {job} ({job_chinese[job]})")
        print("=" * 70)
        
        # 检查该职业是否有装扮表
        suits = generator.list_suits(job)
        if not suits:
            logger.warning(f"职业 {job} 没有可用的套装数据，跳过")
            all_results[job] = {}
            continue
        
        # 创建输出目录 output/cash/additional/{job}/
        output_dir = Path(output_base) / job
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成该职业的所有套装礼包
        results = generator.generate_all_suits(
            job=job,
            output_dir=output_dir,
            suit_filter=suit_filter
        )
        
        all_results[job] = results
        job_success = sum(1 for v in results.values() if v)
        job_total = len(results)
        total_suits += job_total
        success_suits += job_success
        
        print(f"\n职业 {job} 完成: 成功 {job_success}/{job_total}")
        print(f"输出目录: {output_dir}")
    
    # 写入stk.lst
    if generator.get_generated_files():
        generator.write_stk_lst(stk_lst_path)
    
    print("\n" + "=" * 70)
    print("批量生成完成")
    print("=" * 70)
    print(f"总职业数: {len(jobs)}")
    print(f"总套装数: {total_suits}")
    print(f"成功生成: {success_suits}")
    print(f"基础输出目录: {output_base}")
    print(f"stk.lst 路径: {stk_lst_path}")
    
    return all_results


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='批量礼包文件生成器 - 为所有职业生成礼包文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 为所有职业生成所有套装礼包
  python batch_generate_gifts.py

  # 只生成包含"春节"的套装
  python batch_generate_gifts.py -f "春节"

  # 指定输出目录
  python batch_generate_gifts.py -o "my_output/gifts"

  # 指定装扮表路径和TSV路径
  python batch_generate_gifts.py -b "E:\\Avatar" --tsv "path/to/tags.tsv"

  # 不从PVF读取stackable.lst（使用默认起始code=1000）
  python batch_generate_gifts.py --no-pvf
        """
    )
    
    parser.add_argument('-b', '--base-path',
                        default=r'E:\DOF\Tools\blackcat.6.12\output\Avatar',
                        help='装扮表文件基础路径（默认: %(default)s）')
    
    parser.add_argument('--tsv',
                        default=str(Path(__file__).parent / "output" / "complete_equipment_tags.tsv"),
                        help='TSV文件路径（默认: %(default)s）')
    
    parser.add_argument('-o', '--output',
                        default='output/cash/additional',
                        help='输出基础目录（默认: %(default)s）')
    
    parser.add_argument('--stk-lst',
                        default='output/stk.lst',
                        help='stk.lst输出路径（默认: %(default)s）')
    
    parser.add_argument('-f', '--filter',
                        help='过滤套装名称（支持部分匹配，例如："春节"、"国庆套"等）')
    
    parser.add_argument('--no-pvf', action='store_true',
                        help='不从PVF读取stackable.lst（使用默认起始code=1000）')
    
    args = parser.parse_args()
    
    generate_all_jobs(
        base_path=args.base_path,
        tsv_path=args.tsv,
        output_base=args.output,
        stk_lst_path=args.stk_lst,
        suit_filter=args.filter,
        use_pvf=not args.no_pvf
    )


if __name__ == "__main__":
    main()
