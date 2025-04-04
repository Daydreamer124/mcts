import os
import sys
import argparse
from storyteller.algorithm.utils.html2image import convert_html_file_to_image

def main():
    parser = argparse.ArgumentParser(description='将HTML报告转换为图片')
    parser.add_argument('html_file', help='HTML文件路径')
    parser.add_argument('--output', help='输出图片路径（默认为HTML文件同名的PNG文件）')
    args = parser.parse_args()
    
    html_file = args.html_file
    output_path = args.output
    
    if not os.path.exists(html_file):
        print(f"错误：HTML文件 '{html_file}' 不存在")
        sys.exit(1)
    
    # 如果未指定输出路径，使用HTML文件同名的PNG文件
    if not output_path:
        output_path = os.path.splitext(html_file)[0] + ".png"
    
    print(f"转换 {html_file} 为图片...")
    try:
        output_file = convert_html_file_to_image(html_file, output_path)
        print(f"成功！图片已保存至：{output_file}")
    except Exception as e:
        print(f"转换过程中出错：{e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 