#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import base64
import argparse
from PIL import Image
import io
import json
import re
import time
from datetime import datetime

# 导入evaluator模块
from storyteller.algorithm.evaluator import evaluate_report, compress_image

def read_image_as_base64(image_path, compress=True, max_size_mb=4.0):
    """读取图像文件并转换为base64编码"""
    if not os.path.exists(image_path):
        print(f"❌ 图像文件不存在: {image_path}")
        return None
        
    try:
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
            image_size_mb = len(image_data) / (1024 * 1024)
            print(f"✅ 图像加载成功: {image_size_mb:.2f} MB")
            
            # 转换为base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # 压缩图像（如果需要且大小超过限制）
            if compress and image_size_mb > max_size_mb:
                print(f"图像大小超过 {max_size_mb}MB，正在压缩...")
                compressed_base64 = compress_image(image_base64, max_size_mb)
                return compressed_base64
            else:
                return image_base64
    except Exception as e:
        print(f"❌ 读取图像文件出错: {str(e)}")
        return None

def read_html_file(html_path):
    """读取HTML文件内容"""
    if not os.path.exists(html_path):
        print(f"❌ HTML文件不存在: {html_path}")
        return ""
        
    try:
        with open(html_path, "r", encoding="utf-8") as html_file:
            html_content = html_file.read()
            print(f"✅ 读取HTML文件: {html_path} ({len(html_content)} 字符)")
            return html_content
    except Exception as e:
        print(f"❌ 读取HTML文件出错: {str(e)}")
        return ""

def extract_dataset_info(html_content):
    """从HTML内容中提取数据集上下文和查询"""
    # 提取数据集名称
    dataset_match = re.search(r'数据集[\s\S]*?包含([\s\S]*?)的数据', html_content)
    dataset_name = dataset_match.group(1).strip() if dataset_match else "销售数据"
    
    # 提取查询内容，通常在标题后的摘要或第一段
    query_match = re.search(r'<h1>.*?</h1>.*?<p>(.*?)</p>', html_content, re.DOTALL)
    if query_match:
        query = query_match.group(1).strip()
    else:
        # 尝试从标题中提取
        title_match = re.search(r'<h1>(.*?)</h1>', html_content)
        query = title_match.group(1).strip() if title_match else "分析销售数据"
    
    # 构建数据集上下文
    dataset_context = f"这是一个关于{dataset_name}的数据集，包含各种相关指标和统计数据。"
    
    return dataset_context, query

def test_report_evaluation(html_path, image_path, use_school_api=True, compress=True):
    """评估报告质量"""
    print("\n" + "="*60)
    print(f"📊 开始评估报告")
    print("="*60)
    print(f"HTML文件: {html_path}")
    print(f"图像文件: {image_path}")
    print(f"使用API: {'学校API' if use_school_api else '其他服务商API'}")
    print(f"压缩图像: {'是' if compress else '否'}")
    
    # 记录开始时间
    start_time = datetime.now()
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 读取文件
    html_content = read_html_file(html_path)
    image_base64 = read_image_as_base64(image_path, compress=compress)
    
    if not html_content or not image_base64:
        print("❌ 文件读取失败，无法继续评估")
        return
    
    # 提取数据集信息和查询
    dataset_context, query = extract_dataset_info(html_content)
    print(f"\n数据集上下文: {dataset_context}")
    print(f"查询: {query}\n")
    
    # 调用评估函数
    print("🔄 调用评估函数...")
    try:
        score = evaluate_report(
            dataset_context=dataset_context,
            query=query,
            html_report=html_content,
            report_image=image_base64,
            use_school_api=use_school_api
        )
        
        # 记录结束时间
        end_time = datetime.now()
        duration = end_time - start_time
        
        print("\n" + "="*60)
        print(f"✅ 评估完成！")
        print(f"最终评分: {score}/10")
        print(f"评估耗时: {duration}")
        print("="*60)
        
        # 保存评估结果
        result_dir = os.path.dirname(image_path)
        result_path = os.path.join(result_dir, f"evaluation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({
                "score": score,
                "dataset_context": dataset_context,
                "query": query,
                "html_path": html_path,
                "image_path": image_path,
                "api_type": "school" if use_school_api else "other",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration_seconds": duration.total_seconds()
            }, f, indent=2, ensure_ascii=False)
        
        print(f"评估结果已保存至: {result_path}")
        
        return score
    
    except Exception as e:
        print(f"❌ 评估过程中出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def main():
    parser = argparse.ArgumentParser(description="测试报告评估功能")
    parser.add_argument("--html", type=str, default="/Users/zhangzhiyang/mcts/storyteller/output/iterations/iteration_1/report_orange.html", 
                        help="HTML报告文件路径")
    parser.add_argument("--image", type=str, default="/Users/zhangzhiyang/mcts/storyteller/output/iterations/iteration_1/report_orange.png", 
                        help="报告截图文件路径")
    parser.add_argument("--api", type=str, choices=["school", "other"], default="school", 
                        help="使用哪种API: school=学校API, other=其他服务商API")
    parser.add_argument("--no-compress", action="store_true",
                        help="不压缩图像（默认会压缩图像以减小请求大小）")
    
    args = parser.parse_args()
    
    # 执行评估
    test_report_evaluation(
        html_path=args.html,
        image_path=args.image,
        use_school_api=(args.api == "school"),
        compress=not args.no_compress
    )

if __name__ == "__main__":
    main() 