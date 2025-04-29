#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import json
import base64
import requests
import time
import re
from pathlib import Path

# API配置 - 使用配置文件中的值
API_KEY = "7ca9f48d315049bbad0b355afcd5f3a147a8395e46f249e3b7890ffa9ca5122c"
BASE_URL = "https://gpt-api.hkust-gz.edu.cn/v1"
MODEL = "gpt-4-turbo"

# 评估维度提示
EVALUATION_PROMPT = """
请对数据可视化报告进行评估,从以下四个维度进行打分(1-10分)并提供详细理由:

1. 数据表达的准确性与完整性 (Representation) - 40%
- 图表类型适合性：所选图表类型是否适合表达该类数据及其关系？
- 比例尺准确性：轴、面积等视觉元素是否如实反映数据大小关系？
- 数据完整性：关键数据点是否完整呈现，没有明显遗漏？
- 数据上下文完备性：是否提供必要的标题、坐标轴、图例等信息？

2. 信息传递的有效性与清晰度 (Presentation) - 30%
- 核心信息突显：关键信息是否通过视觉元素突出？
- 认知友好：信息密度是否适中，标注是否清晰？
- 内容衔接：可视化与文本是否形成连贯叙事？

3. 设计的美学质量与专业性 (Aesthetics) - 20%
- 整体视觉和谐：配色是否协调，布局是否平衡？
- 细节精致：间距、对齐等细节是否专业？
- 简约克制：是否避免了多余装饰？

4. 叙事结构完整性 (Narrative) - 10%
- 是否包含摘要、正文、结论等完整结构？
- 各部分是否逻辑连贯？
- 内容是否紧扣用户查询？

请基于以上标准进行评分,输出格式为JSON:
{
    "representation": {"score": x, "rationale": "..."},
    "presentation": {"score": x, "rationale": "..."},
    "aesthetics": {"score": x, "rationale": "..."},
    "narrative": {"score": x, "rationale": "..."}
}
"""

def call_vision_api(prompt, image_base64):
    """使用配置的API调用视觉模型"""
    try:
        url = f"{BASE_URL}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }
        
        data = {
            "model": MODEL,
            "messages": [
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 3000,
            "temperature": 0.5
        }
        
        print(f"📡 发送请求到: {url}")
        print(f"🔄 使用模型: {MODEL}")
        print(f"📊 请求大小: {len(json.dumps(data))/1024/1024:.2f} MB")
        
        response = requests.post(url, headers=headers, json=data, timeout=60)
        
        if response.status_code == 200:
            response_json = response.json()
            
            if 'choices' in response_json and response_json['choices']:
                content = response_json['choices'][0]['message']['content'].strip()
                print(f"✅ API调用成功，返回 {len(content)} 字符")
                return content
            else:
                print(f"❌ API返回异常格式: {response_json}")
        else:
            print(f"❌ API调用失败，状态码 {response.status_code}: {response.text}")
        
    except Exception as e:
        print(f"❌ API调用出错: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return None

def extract_json_from_text(text):
    """从文本中提取JSON对象"""
    try:
        # 首先尝试直接将整个文本解析为JSON
        return json.loads(text)
    except json.JSONDecodeError:
        # 如果失败，尝试查找JSON块
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                json_str = json_match.group(1).strip()
                return json.loads(json_str)
            except:
                pass
                
        # 尝试查找括号包围的JSON对象
        json_match = re.search(r'(\{[\s\S]*\})', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass
                
        print(f"❌ 无法从文本中提取JSON: {text[:100]}...")
        return None

def evaluate_report(image_path, html_path=None, max_retries=3):
    """使用新API评估报告质量"""
    # 确保图片路径存在
    if not os.path.exists(image_path):
        print(f"❌ 图片文件不存在: {image_path}")
        return
    
    # 如果提供了HTML路径，读取内容
    html_content = ""
    if html_path and os.path.exists(html_path):
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
                print(f"✅ 读取HTML文件: {html_path} ({len(html_content)} 字符)")
        except Exception as e:
            print(f"❌ 读取HTML文件失败: {str(e)}")
    
    # 读取图片并转换为base64
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
            image_base64 = base64.b64encode(image_data).decode()
            image_size = len(image_data) / 1024 / 1024  # MB
            print(f"✅ 图片加载成功: {image_size:.2f} MB")
    except Exception as e:
        print(f"❌ 图片读取失败: {str(e)}")
        return
    
    # 构建评估提示词
    prompt = f"""
{EVALUATION_PROMPT}

请评估以下数据可视化报告：

用户查询: "分析各种客户类型的差异"

查看图片中的可视化报告，并提供评分和详细理由。
"""
    
    # 使用重试机制调用API
    response_text = None
    for attempt in range(max_retries):
        try:
            print(f"\n🔄 第{attempt+1}次尝试评估报告...")
            response_text = call_vision_api(prompt, image_base64)
            if response_text:
                break
            else:
                print(f"⚠️ 第{attempt+1}次尝试未返回有效响应")
        except Exception as e:
            print(f"⚠️ 第{attempt+1}次尝试出错: {str(e)}")
        
        if attempt < max_retries - 1:
            wait_time = 2 * (attempt + 1)  # 指数退避
            print(f"🔄 等待{wait_time}秒后重试...")
            time.sleep(wait_time)
    
    if not response_text:
        print("❌ 所有尝试均失败，无法评估报告")
        return
    
    # 输出原始响应（仅截取部分）
    print(f"\n📝 API响应(截取前200字符):\n{response_text[:200]}...")
    
    # 处理可能的markdown格式
    if response_text.startswith("```json"):
        response_text = response_text.replace("```json", "").replace("```", "")
    elif response_text.startswith("```"):
        response_text = response_text.replace("```", "")
    response_text = response_text.strip()
    
    # 解析JSON
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        import re
        print("⚠️ 直接JSON解析失败，尝试提取JSON...")
        # 尝试找到JSON对象
        match = re.search(r'(\{[\s\S]*\})', response_text)
        if match:
            try:
                result = json.loads(match.group(1))
            except:
                print("❌ 无法提取有效JSON")
                return
        else:
            print("❌ 无法提取有效JSON")
            return
    
    # 验证所有必要的键是否存在
    required_keys = ["representation", "presentation", "aesthetics", "narrative"]
    for key in required_keys:
        if key not in result:
            print(f"❌ 缺少必要的评估维度: {key}")
            return
    
    # 确保评分是数值类型
    try:
        for key in required_keys:
            if not isinstance(result[key]["score"], (int, float)):
                result[key]["score"] = float(result[key]["score"])
    except (ValueError, TypeError) as e:
        print(f"❌ 评分转换为数值时出错: {str(e)}")
        return
    
    # 计算加权分数
    weighted_score = (
        0.4 * result["representation"]["score"] +
        0.3 * result["presentation"]["score"] +
        0.2 * result["aesthetics"]["score"] +
        0.1 * result["narrative"]["score"]
    )
    
    # 打印详细评分和理由
    print("\n📊 报告评估结果:")
    print(f"- 数据表达 (40%): {result['representation']['score']}/10")
    print(f"  理由: {result['representation']['rationale'][:200]}...")
    
    print(f"\n- 信息传递 (30%): {result['presentation']['score']}/10")
    print(f"  理由: {result['presentation']['rationale'][:200]}...")
    
    print(f"\n- 设计美学 (20%): {result['aesthetics']['score']}/10")
    print(f"  理由: {result['aesthetics']['rationale'][:200]}...")
    
    print(f"\n- 叙事结构 (10%): {result['narrative']['score']}/10")
    print(f"  理由: {result['narrative']['rationale'][:200]}...")
    
    print(f"\n✨ 加权总分: {weighted_score:.2f}/10")
    
    # 保存评估结果
    try:
        result_path = f"{os.path.splitext(image_path)[0]}_evaluation.json"
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump({
                "scores": result,
                "weighted_score": weighted_score,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }, f, indent=2, ensure_ascii=False)
        print(f"✅ 评估结果已保存至: {result_path}")
    except Exception as e:
        print(f"❌ 保存评估结果失败: {str(e)}")


if __name__ == "__main__":
    # 处理命令行参数
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        html_path = sys.argv[2] if len(sys.argv) > 2 else None
    else:
        # 默认图片路径
        image_path = "/Users/zhangzhiyang/mcts/storyteller/output/iterations/iteration_1/report_orange.png"
        html_path = "/Users/zhangzhiyang/mcts/storyteller/output/iterations/iteration_1/report_orange.html"
    
    print(f"🔍 开始评估报告: {image_path}")
    evaluate_report(image_path, html_path) 