"""
示例：生成装备编码和对应的 equ 文件

此脚本演示如何使用 equipment_code_generator 生成装备编码（.lst 文件）
以及对应的 equ 文件。
"""
import argparse
from pathlib import Path
from equipment_code_generator import EquipmentCodeGenerator
from config import AVATAR_DATA_JSON, EQUIPMENT_LST, BASE_DIR


def main():
    parser = argparse.ArgumentParser(description='生成装备编码和 equ 文件')
    parser.add_argument(
        '--no-equ-files',
        action='store_true',
        help='不生成 equ 文件，只生成 lst 文件'
    )
    parser.add_argument(
        '--equ-output-dir',
        type=str,
        default=str(BASE_DIR / "generated_equ"),
        help='equ 文件输出目录（默认: ./generated_equ）'
    )
    parser.add_argument(
        '--import-to-pvf',
        action='store_true',
        help='将生成的 equ 文件导入到 PVF（需要 PVF API 可访问）'
    )
    parser.add_argument(
        '--json-path',
        type=str,
        default=str(AVATAR_DATA_JSON),
        help='avatar 数据 JSON 文件路径'
    )
    parser.add_argument(
        '--lst-output',
        type=str,
        default=str(EQUIPMENT_LST),
        help='lst 文件输出路径'
    )
    parser.add_argument(
        '--max-per-job-part',
        type=int,
        default=None,
        help='每个职业部位最多生成的 equ 数量（默认无限制，测试时建议设为10）'
    )
    
    args = parser.parse_args()
    
    # 创建生成器
    generator = EquipmentCodeGenerator(
        generate_equ_files=not args.no_equ_files,
        equ_output_dir=Path(args.equ_output_dir),
        max_equ_per_job_part=args.max_per_job_part
    )
    
    # 生成
    print(f"开始生成...")
    print(f"  JSON 输入: {args.json_path}")
    print(f"  LST 输出: {args.lst_output}")
    print(f"  生成 equ 文件: {not args.no_equ_files}")
    if not args.no_equ_files:
        print(f"  equ 输出目录: {args.equ_output_dir}")
        print(f"  每个职业部位限制: {args.max_per_job_part if args.max_per_job_part else '无限制'}")
    print(f"  导入到 PVF: {args.import_to_pvf}")
    print()
    
    try:
        stats = generator.generate(
            json_path=Path(args.json_path),
            output_path=Path(args.lst_output),
            write_equ_to_local=not args.no_equ_files,
            import_to_pvf=args.import_to_pvf
        )
        
        print("\n" + "="*50)
        print("生成完成！")
        print("="*50)
        print(f"新装备编码数: {stats['total_codes']}")
        print(f"PVF 已有装备数: {stats['existing_codes']}")
        print(f"错误数: {stats['error_count']}")
        print(f"LST 输出文件: {stats['output_file']}")
        
        if 'equ_files_generated' in stats:
            print(f"\nEqu 文件统计:")
            print(f"  生成数: {stats['equ_files_generated']}")
            print(f"  本地写入数: {stats['equ_files_written']}")
            if args.import_to_pvf:
                print(f"  PVF 导入数: {stats['equ_files_imported']}")
            if stats.get('max_per_job_part'):
                print(f"  每个职业部位限制: {stats['max_per_job_part']}")
        
    except Exception as e:
        print(f"\n错误: {e}")
        raise


if __name__ == "__main__":
    main()
