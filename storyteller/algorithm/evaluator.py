import json
import re
import requests
import traceback
import io
import base64
import time
from storyteller.llm_call.openai_llm import call_openai
from storyteller.llm_call.prompt_factory import get_prompt
from typing import Dict, Any

# API配置
# 学校API配置
SCHOOL_API_CONFIG = {
    "API_KEY": "7ca9f48d315049bbad0b355afcd5f3a147a8395e46f249e3b7890ffa9ca5122c",
    "BASE_URL": "https://gpt-api.hkust-gz.edu.cn/v1",
    "MODEL": "gpt-4-turbo",
    "AUTH_TYPE": "Bearer"  # 使用Bearer授权类型
}

# 其他服务商API配置（保留之前的配置）
OTHER_API_CONFIG = {
    "API_KEY": "sk-GNAtKRfZXeXBN2sqsuZhsuzYoQb1Sg6oKwdvcGY7HAINBrf6",  
    "BASE_URL": "https://api.chsdw.top/v1",
    "MODEL": "gpt-4o-2024-05-13",
    "AUTH_TYPE": "Bearer"  # 也使用Bearer授权类型
}

# 默认API配置（可以根据需要更改）
DEFAULT_API_CONFIG = SCHOOL_API_CONFIG

EVALUATION_DIMENSIONS = """
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

def compress_image(image_base64, max_size_mb=4.0, quality=85):
    """压缩base64编码的图像数据
    
    Args:
        image_base64: 图像的base64编码字符串
        max_size_mb: 最大图像大小（MB）
        quality: JPEG压缩质量
        
    Returns:
        压缩后的base64图像字符串
    """
    try:
        from PIL import Image
        
        # 将base64解码为二进制
        image_data = base64.b64decode(image_base64)
        image_size_mb = len(image_data) / (1024 * 1024)
        
        # 如果图像已经足够小，无需压缩
        if image_size_mb <= max_size_mb:
            print(f"图像大小已满足要求: {image_size_mb:.2f} MB")
            return image_base64
            
        print(f"原始图像大小: {image_size_mb:.2f} MB，开始压缩...")
        
        # 加载图像
        image_io = io.BytesIO(image_data)
        img = Image.open(image_io)
        
        # 保存原始尺寸
        original_width, original_height = img.size
        
        # 如果图像尺寸过大，先调整尺寸
        max_dimension = 1600  # 最大尺寸
        if max(img.size) > max_dimension:
            ratio = max_dimension / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
            print(f"调整图像尺寸: {original_width}x{original_height} -> {new_size[0]}x{new_size[1]}")
        
        # 转换为RGB模式（去除透明通道）
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else None)
            img = bg
            print(f"转换图像格式: {img.mode}")
        
        # 压缩图像
        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        compressed_size_mb = output.tell() / (1024 * 1024)
        print(f"压缩后图像大小: {compressed_size_mb:.2f} MB (质量: {quality})")
        
        # 如果还是太大，继续降低质量
        while compressed_size_mb > max_size_mb and quality > 40:
            quality -= 10
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=quality, optimize=True)
            compressed_size_mb = output.tell() / (1024 * 1024)
            print(f"进一步压缩图像: 质量={quality}, 大小={compressed_size_mb:.2f} MB")
        
        # 获取压缩后的base64
        output.seek(0)
        compressed_base64 = base64.b64encode(output.read()).decode('utf-8')
        print(f"图像压缩完成: {image_size_mb:.2f} MB -> {compressed_size_mb:.2f} MB")
        return compressed_base64
        
    except Exception as e:
        print(f"❌ 图像压缩失败: {str(e)}")
        return image_base64  # 返回原始图像

def call_vision_api_v2(prompt, image_base64, use_school_api=True, **kwargs):
    """使用视觉模型API调用
    
    Args:
        prompt: 文本提示
        image_base64: 图像的base64编码
        use_school_api: 是否使用学校API，默认为True
        **kwargs: 其他参数
        
    Returns:
        API响应内容或None（如果调用失败）
    """
    # 选择API配置
    api_config = SCHOOL_API_CONFIG if use_school_api else OTHER_API_CONFIG
    
    try:
        url = f"{api_config['BASE_URL']}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_config['API_KEY']}"
        }
        
        data = {
            "model": api_config['MODEL'],
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
            "max_tokens": kwargs.get("max_tokens", 3000),
            "temperature": kwargs.get("temperature", 0.5)
        }
        
        print(f"📡 发送请求到: {url}")
        print(f"🔄 使用API: {'学校API' if use_school_api else '其他服务商API'}")
        print(f"🔄 使用模型: {api_config['MODEL']}")
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

def evaluate_report(
    dataset_context: str, 
    query: str, 
    html_report: str, 
    report_image: str = None,
    use_school_api: bool = True,
    llm_kwargs: Dict[str, Any] = None
) -> float:
    """
    评估数据可视化报告质量
    
    参数:
        dataset_context: 数据集上下文
        query: 用户查询
        html_report: 报告HTML内容
        report_image: 报告截图的base64编码（可选）
        use_school_api: 是否使用学校API（默认为True）
        llm_kwargs: LLM调用参数
    
    返回:
        float: 加权评分 (0-10分)
    """
    # 初始化响应文本
    response_text = None
    
    # 调用API进行评估
    try:
        # 方法1: 使用视觉API
        if report_image:
            api_type = "学校API" if use_school_api else "其他服务商API"
            print(f"📊 使用{api_type}进行报告评估（带图像）...")
            
            # 压缩图像，减小请求大小
            compressed_image = compress_image(report_image)
            
            # 直接构建提示词，不使用模板系统
            prompt = f"""
{EVALUATION_DIMENSIONS}

请评估以下数据可视化报告：

数据集上下文: {dataset_context}

用户查询: {query}

查看图片中的可视化报告，并提供评分和详细理由。
"""
            
            # 使用重试机制
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response_text = call_vision_api_v2(
                        prompt, 
                        compressed_image,
                        use_school_api=use_school_api,
                        **(llm_kwargs or {})
                    )
                    if response_text:
                        print(f"✅ 成功使用{api_type}获取响应")
                        break
                    else:
                        print(f"⚠️ 第{attempt+1}次尝试: {api_type}未返回有效响应")
                except Exception as e:
                    print(f"⚠️ 第{attempt+1}次尝试: {api_type}调用出错: {str(e)}")
                
                if attempt < max_retries - 1:
                    wait_time = 2 * (attempt + 1)
                    print(f"🔄 等待{wait_time}秒后重试...")
                    time.sleep(wait_time)
        
        # 方法2: 如果视觉API失败，尝试使用通用API（备选方式）
        if not response_text:
            try:
                print("📝 尝试使用通用API进行报告评估...")
                
                # 构建提示词
                prompt_args = {
                    "DATASET_CONTEXT": dataset_context,
                    "QUERY": query,
                    "REPORT": html_report,
                    "REPORT_IMAGE": ""  # 不包含图像
                }
                
                # 使用模板生成提示词
                prompt = get_prompt("report_evaluation", prompt_args)
                
                responses = call_openai(prompt, **(llm_kwargs or {}))
                if responses:
                    response_text = responses[0].strip()
                    print("✅ 成功使用通用API获取响应")
                else:
                    print("⚠️ 通用API未返回有效响应")
            except Exception as e:
                print(f"⚠️ 通用API调用出错: {str(e)}")
                  
        # 如果两种方法都失败，返回默认评分
        if not response_text:
            print("❌ 所有API调用方式均失败，返回默认评分")
            return 5.0
            
        # 输出原始响应，方便调试
        print(f"\n📝 评估响应(截取前200字符):\n{response_text[:200]}...")
        
        # 处理可能的markdown格式
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "")
        elif response_text.startswith("```"):
            response_text = response_text.replace("```", "")
        response_text = response_text.strip()
        
        # 尝试直接解析JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # 如果直接解析失败，使用增强的JSON提取方法
            print("⚠️ 直接JSON解析失败，尝试提取JSON...")
            result = extract_json_from_text(response_text)
            
            if not result:
                print("❌ 无法从响应中提取有效JSON")
                return 5.0  # 默认中等分数
        
        # 验证所有必要的键是否存在
        required_keys = ["representation", "presentation", "aesthetics", "narrative"]
        for key in required_keys:
            if key not in result:
                print(f"❌ 缺少必要的评估维度: {key}")
                return 5.0  # 默认中等分数
        
        # 确保评分是数值类型
        try:
            for key in required_keys:
                if not isinstance(result[key]["score"], (int, float)):
                    result[key]["score"] = float(result[key]["score"])
        except (ValueError, TypeError) as e:
            print(f"❌ 评分转换为数值时出错: {str(e)}")
            return 5.0
        
        # 计算加权分数
        weighted_score = (
            0.4 * result["representation"]["score"] +
            0.3 * result["presentation"]["score"] +
            0.2 * result["aesthetics"]["score"] +
            0.1 * result["narrative"]["score"]
        )
        
        # 打印评估结果
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
        
        return round(weighted_score, 2)
        
    except Exception as e:
        print(f"❌ 评估出错: {str(e)}")
        traceback.print_exc()  # 打印详细错误堆栈
        return 5.0 