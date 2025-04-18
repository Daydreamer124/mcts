import os
import subprocess
import glob
import argparse

def process_all_reports(template='orange', all_templates=False, specific_dir=None):
    # 如果指定了特定目录，只处理该目录
    if specific_dir:
        if os.path.exists(specific_dir) and os.path.isdir(specific_dir):
            iteration_dirs = [specific_dir]
        else:
            print(f"错误: 指定的目录 '{specific_dir}' 不存在或不是目录")
            return
    else:
        # 否则查找所有iteration目录
        base_dir = 'storyteller/output/iterations'
        iteration_dirs = glob.glob(f'{base_dir}/iteration_*')
    
    # 如果指定了生成所有模板，则使用所有可用模板
    templates_to_use = ['orange', 'blue', 'green', 'purple', 'sidebar', 'grid', 'dark', 'magazine', 'dashboard'] if all_templates else [template]
    
    for iteration_dir in sorted(iteration_dirs):
        # 检查是否存在report.md文件
        report_path = os.path.join(iteration_dir, 'report.md')
        if os.path.exists(report_path):
            print(f"Processing: {report_path}")
            
            # 对每个模板生成报告
            for template_style in templates_to_use:
                output_file = os.path.join(iteration_dir, f'report_{template_style}.html')
                print(f"  Generating {template_style} template...")
                
                # 调用报告生成脚本
                cmd = [
                    'python', 
                    'storyteller/algorithm/utils/generate_report_from_md.py', 
                    report_path, 
                    '--output', output_file,
                    '--template', template_style
                ]
                
                try:
                    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
                    print(f"    {result.stdout.strip()}")
                except subprocess.CalledProcessError as e:
                    print(f"    Error processing {report_path} with {template_style}: {e}")
                    print(f"    Error details: {e.stderr}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process all markdown reports and generate HTML files')
    parser.add_argument('--template', choices=['orange', 'blue', 'green', 'purple', 'sidebar', 'grid', 'dark', 'magazine', 'dashboard'], 
                        default='orange', help='Template style to use')
    parser.add_argument('--all', action='store_true', help='Generate reports with all available templates')
    parser.add_argument('--dir', type=str, help='Specific directory to process instead of all iteration directories')
    args = parser.parse_args()
    
    process_all_reports(args.template, args.all, args.dir)
    
    if args.all:
        print("All reports processed with all template styles!")
    else:
        print(f"All reports processed with {args.template} template!") 