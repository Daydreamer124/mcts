import json
import os
import argparse
import sys
import re
from typing import Dict, Any, Optional
import openai
import requests

def get_python_to_vegalite_prompt(python_code: str) -> str:
    """生成用于将Python可视化代码转换为Vega-Lite的提示"""
    
    # 使用以/storyteller开头的路径
    dataset_path = "/storyteller/dataset/shopping.csv"

    prompt = f"""
你是一个专精数据可视化的AI助手，擅长将Python可视化代码转换为Vega-Lite规范。

请分析以下Python可视化代码，并将其直接转换为等效的Vega-Lite JSON配置。
请仔细分析代码的数据处理、图表类型、映射、坐标轴、标题等设置，确保Vega-Lite配置能够完整再现Python代码的可视化效果。

【格式要求】请严格遵循标准JSON格式：
- 所有字符串必须使用双引号，不能使用单引号： "text" 而非 'text'
- 数组或对象的最后一个元素后不能有逗号
- 布尔值使用 true/false 而非 True/False
- 确保所有括号、大括号正确配对并完整闭合

【数据引用处理】
- 请使用 "data": {{"url": "{dataset_path}"}} 来引用数据
- 也可以使用 "data": {{"values": [...] }} 来提供内联数据，当Python代码中明确创建了静态数据时
- 不要创建假数据或示例数据点
- 确保保留Python代码中的所有数据处理操作(如分组、聚合、筛选等)，将它们转换为Vega-Lite的适当编码方式

【关于可视化特性】
- 确保正确转换图表类型，例如bar、line、point、area、boxplot、arc(饼图)等

【转换步骤】
1. 识别代码使用的可视化库（matplotlib、seaborn、altair、plotly等）
2. 确定图表类型（柱状图、折线图、散点图、饼图、箱线图等）
3. 分析数据处理逻辑（例如分组、聚合、筛选等）
4. 提取关键配置：
   - 保留字段名称、轴标签、图例设置等
   - 保留所有聚合操作（如mean、count等）
   - 保留编码通道映射（颜色、大小、形状等）
5. 创建完整的Vega-Lite JSON规范

【重要：编码处理语法指南】
在Vega-Lite中，数据转换和聚合主要在encoding对象内部处理：

1. 【分箱操作】应该放在encoding里的字段定义中：
```
"encoding": {{
  "x": {{
    "field": "IMDB Rating",
    "bin": true,
    "type": "ordinal"
  }},
  "y": {{
    "aggregate": "count"
  }}
}}
```

2. 【聚合操作】也应该放在encoding里对应的编码通道中：
```
"encoding": {{
  "y": {{
    "field": "value",
    "aggregate": "mean"
  }}
}}
```

3. 【分组和染色】使用color或column等通道：
```
"encoding": {{
  "x": {{"field": "category"}},
  "y": {{"field": "value"}},
  "color": {{"field": "group"}}
}}
```

4. 【偏移和分面】使用xOffset或yOffset：
```
"encoding": {{
  "x": {{"field": "category"}},
  "y": {{"field": "value"}},
  "xOffset": {{"field": "group"}}
}}
```

请严格按以下模板格式返回Vega-Lite配置。确保JSON格式完全有效，不要添加任何额外说明，只返回JSON对象：

{{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "title": "图表标题",
  "description": "图表描述",
  "data": {{"url": "{dataset_path}"}},
  "mark": "图表类型", 
  "encoding": {{
    // 编码映射，包含数据转换操作
  }}
}}

Python可视化代码:
```
{python_code}
```

最终只返回一个有效的JSON对象，不要使用Markdown格式，不要添加任何解释文本。
"""
    return prompt

def call_openai(prompt: str, **kwargs) -> str:
    """调用OpenAI API或兼容的API端点
    
    支持以下调用方法:
    1. 原生OpenAI API
    2. 兼容OpenAI API的自定义端点
    3. 通过requests直接调用API（适用于某些特殊场景）
    """
    try:
        print(f"🔄 API调用参数: model={kwargs.get('model', 'gpt-4-turbo')}, base_url={kwargs.get('base_url', '默认OpenAI')}")
        
        # 检查是否有指定的API端点
        base_url = kwargs.get('base_url')
        api_key = kwargs.get('api_key', os.environ.get("OPENAI_API_KEY", ""))
        model = kwargs.get('model', 'gpt-4-turbo')
        
        # 直接使用requests调用API（当提供了特定格式的base_url时）
        if base_url and (base_url.endswith('/chat/completions') or 'hkust-gz' in base_url):
            try:
                print(f"🔄 使用直接请求方式调用API: {base_url}")
                headers = {
                    "Content-Type": "application/json"
                }
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                
                data = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You are a data visualization expert."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": kwargs.get("temperature", 0.0),
                    "max_tokens": kwargs.get("max_tokens", 4096)
                }
                
                response = requests.post(
                    base_url,
                    headers=headers,
                    json=data
                )
                
                response_json = response.json()
                if response.status_code == 200 and 'choices' in response_json and response_json['choices']:
                    return response_json['choices'][0]['message']['content']
                else:
                    print(f"❌ API返回错误: {response.status_code} - {response_json}")
                    return ""
            except Exception as e:
                print(f"❌ 使用直接请求方式调用API失败: {str(e)}")
                print("⚠️ 尝试回退到OpenAI客户端方式")
        
        # 使用OpenAI客户端SDK调用API
        # 创建客户端参数
        client_kwargs = {}
        if api_key:
            client_kwargs["api_key"] = api_key
        
        # 仅当base_url不是完整的chat/completions端点时才设置
        if base_url and not base_url.endswith('/chat/completions'):
            client_kwargs["base_url"] = base_url
        
        # 创建客户端
        client = openai.OpenAI(**client_kwargs)
        
        # 生成回答
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a data visualization expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=kwargs.get("temperature", 0.0),
            max_tokens=kwargs.get("max_tokens", 4096)
        )
        
        # 返回回答
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ 调用所有API方式都失败: {str(e)}")
        import traceback
        traceback.print_exc()
        



def convert_python_to_vegalite(python_code: str, llm_kwargs: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
    """
    使用LLM将Python可视化代码转换为Vega-Lite配置
    
    参数:
        python_code: Python可视化代码
        llm_kwargs: LLM调用参数
        
    返回:
        Vega-Lite配置对象或None（如果转换失败）
    """
    try:
        # 准备提示
        prompt = get_python_to_vegalite_prompt(python_code)
        
        # 处理llm_kwargs
        if llm_kwargs is None:
            llm_kwargs = {}
        
        # 确保必要的参数存在
        if not llm_kwargs.get("model"):
            llm_kwargs["model"] = "gpt-4-turbo"
        
        # 设置低温度以获得更确定的结果
        llm_kwargs["temperature"] = 0.0
        llm_kwargs["max_tokens"] = llm_kwargs.get("max_tokens", 4096)
        
        print(f"🔍 调用LLM ({llm_kwargs.get('model')})将Python代码转换为Vega-Lite配置...")
        print(f"   使用base_url: {llm_kwargs.get('base_url', '默认')}")
        
        # 调用LLM
        response = call_openai(prompt, **llm_kwargs)
        
        # 提取JSON内容
        json_content = extract_json_from_response(response)
        if json_content:
            return json_content
            
        
    except Exception as e:
        print(f"❌ 转换代码时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def extract_json_from_response(response: str) -> Optional[Dict[str, Any]]:
    """从LLM响应中提取JSON内容"""
    if not response:
        print("❌ LLM返回了空响应")
        return None
    
    # 记录原始响应便于调试
    print("📝 LLM原始响应:")
    print(response)
    
    # 尝试多种方式提取和解析JSON
    try:
        # 首先尝试使用更安全的json解析方式
        try:
            # 使用eval方式解析，这对于包含$schema的JSON更友好
            # 先检查响应是否是一个完整的JSON对象
            if response.strip().startswith('{') and response.strip().endswith('}'):
                # 用更灵活的方式解析
                import ast
                # 将$schema中的$替换为临时标记，以避免Python解析问题
                temp_response = response.replace('$schema', '__DOLLAR_SCHEMA__')
                # 替换JSON布尔值为Python格式
                temp_response = re.sub(r'\btrue\b', 'True', temp_response)
                temp_response = re.sub(r'\bfalse\b', 'False', temp_response)
                # 使用ast.literal_eval解析（更安全的eval）
                parsed_dict = ast.literal_eval(temp_response)
                # 恢复$schema
                if '__DOLLAR_SCHEMA__' in parsed_dict:
                    parsed_dict['$schema'] = parsed_dict.pop('__DOLLAR_SCHEMA__')
                return parsed_dict
        except (SyntaxError, ValueError) as e:
            print(f"⚠️ 安全解析方式失败: {str(e)}")
            
        # 1. 检查是否存在markdown代码块，优先提取
        if "```" in response:
            markdown_pattern = r'```(?:json)?(.*?)```'
            matches = re.findall(markdown_pattern, response, re.DOTALL)
            if matches:
                for match in matches:
                    json_content = match.strip()
                    try:
                        # 使用自定义的安全解析方法
                        return safe_parse_json(json_content)
                    except Exception as e:
                        print(f"⚠️ Markdown代码块解析失败: {str(e)}")
        
        # 2. 尝试直接将整个响应作为JSON解析
        try:
            return safe_parse_json(response.strip())
        except Exception as e:
            print(f"⚠️ 直接解析响应失败: {str(e)}")
            
        # 3. 尝试清理后解析
        clean_json = clean_json_content(response)
        try:
            return safe_parse_json(clean_json)
        except Exception as e:
            print(f"⚠️ 清理后解析失败: {str(e)}")
            
        # 4. 尝试提取大括号内的内容
        json_match = re.search(r'(\{.*\})', response, re.DOTALL)
        if json_match:
            extracted_json = json_match.group(0)
            try:
                return safe_parse_json(extracted_json)
            except Exception as e:
                print(f"⚠️ 提取大括号内容解析失败: {str(e)}")
                
        print("❌ 所有JSON解析尝试都失败了")
        return None
        
    except Exception as e:
        print(f"❌ 提取JSON时出错: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def safe_parse_json(json_str: str) -> Dict[str, Any]:
    """安全解析JSON，处理包含$符号的情况和true/false布尔值"""
    
    # 先判断是否包含$schema
    has_dollar_schema = '"$schema"' in json_str
    
    if has_dollar_schema:
        # 替换$schema为一个安全的临时标记
        json_str = json_str.replace('"$schema"', '"__DOLLAR_SCHEMA__"')
    
    # 尝试解析修改后的JSON
    try:
        import json
        parsed = json.loads(json_str)
        
        # 恢复$schema键
        if has_dollar_schema and '__DOLLAR_SCHEMA__' in parsed:
            parsed['$schema'] = parsed.pop('__DOLLAR_SCHEMA__')
        
        return parsed
    except Exception as e:
        # 如果直接解析失败，尝试更多的替换
        try:
            # 使用正则表达式找出所有可能带$的键
            dollar_keys = re.findall(r'"(\$[^"]+)"', json_str)
            
            temp_json = json_str
            replacements = {}
            
            # 替换所有带$的键
            for key in dollar_keys:
                temp_key = f"__DOLLAR_{key[1:]}"
                replacements[temp_key] = key
                temp_json = temp_json.replace(f'"{key}"', f'"{temp_key}"')
            
            # 解析替换后的JSON
            import json
            parsed = json.loads(temp_json)
            
            # 恢复所有原始键
            for temp_key, original_key in replacements.items():
                if temp_key in parsed:
                    parsed[original_key] = parsed.pop(temp_key)
            
            return parsed
        except Exception as e:
            # 最后的备用方法：使用ast
            try:
                # 使用ast.literal_eval，但先处理true/false
                import ast
                
                # 替换JSON布尔值为Python格式
                temp_str = re.sub(r'\btrue\b', 'True', json_str)
                temp_str = re.sub(r'\bfalse\b', 'False', temp_str)
                
                # 替换所有带$的部分以避免eval问题
                temp_str = re.sub(r'"(\$[^"]+)"', r'"__DOLLAR_\1"', temp_str)
                temp_str = temp_str.replace('$', '__DOLLAR__')
                
                # 解析
                parsed_dict = ast.literal_eval(temp_str)
                
                # 恢复所有$相关的键
                for key in list(parsed_dict.keys()):
                    if key.startswith('__DOLLAR_'):
                        original_key = '$' + key[9:]  # 移除 '__DOLLAR_'
                        parsed_dict[original_key] = parsed_dict.pop(key)
                
                return parsed_dict
            except Exception as final_e:
                print(f"❌ JSON解析最终失败: {str(final_e)}")
                raise  # 如果所有方法都失败，抛出异常

def clean_json_content(json_str: str) -> str:
    """清理JSON内容，移除注释和其他非JSON元素"""
    # 移除单行注释 (// ...)
    json_str = re.sub(r'//.*?($|\n)', '', json_str)
    
    # 移除多行注释 (/* ... */)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    
    # 移除尾部逗号
    json_str = re.sub(r',(\s*[\]}])', r'\1', json_str)
    
    # 移除可能的markdown标记
    json_str = re.sub(r'^```json|```$', '', json_str, flags=re.MULTILINE).strip()
    
    return json_str

def save_vegalite_config(config: Dict[str, Any], output_path: str) -> None:
    """保存Vega-Lite配置到文件"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✅ Vega-Lite配置已保存到: {output_path}")
    except Exception as e:
        print(f"❌ 保存配置时出错: {str(e)}")

def create_html_viewer(config: Dict[str, Any], output_path: str) -> None:
    """创建一个包含Vega-Lite可视化的HTML文件
    
    使用配置中指定的数据集URL，不再内联数据
    """
    if not config:
        print("❌ 无法创建HTML查看器：配置为空")
        return
    
    # 确保配置中包含正确的数据引用
    if "data" not in config or "url" not in config["data"]:
        config["data"] = {"url": "/storyteller/dataset/shopping.csv"}
    else:
        # 如果已有url，确保使用正确的格式
        current_url = config["data"]["url"]
        if not current_url.startswith("/storyteller/"):
            config["data"]["url"] = "/storyteller/dataset/shopping.csv"

    # 获取图表类型，处理mark是字典或字符串的情况
    chart_type = config.get("mark", "未知图表类型")
    if isinstance(chart_type, dict):
        chart_type = chart_type.get("type", "未知图表类型")
    
    # 美化的HTML模板，使用现代CSS样式
    html_template = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <title>Vega-Lite 数据可视化</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
        <script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
        <script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
        <style>
            :root {
                --primary-color: #4285f4;
                --secondary-color: #34a853;
                --background-color: #f8f9fa;
                --text-color: #202124;
                --card-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            }
            
            body {
                margin: 0;
                padding: 0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                background-color: var(--background-color);
                color: var(--text-color);
            }
            
            .container {
                max-width: 1000px;
                margin: 0 auto;
                padding: 20px;
            }
            
            header {
                text-align: center;
                padding: 20px 0;
                margin-bottom: 30px;
                border-bottom: 1px solid #e0e0e0;
            }
            
            h1 {
                color: var(--primary-color);
                margin: 0;
                font-weight: 500;
            }
            
            .subtitle {
                color: #5f6368;
                margin-top: 10px;
            }
            
            .visualization-card {
                background-color: white;
                border-radius: 8px;
                box-shadow: var(--card-shadow);
                overflow: hidden;
                margin-bottom: 30px;
            }
            
            .card-header {
                padding: 15px 20px;
                border-bottom: 1px solid #e0e0e0;
            }
            
            .card-title {
                margin: 0;
                color: var(--text-color);
                font-size: 1.2rem;
                font-weight: 500;
            }
            
            .card-body {
                padding: 20px;
                min-height: 400px;
            }
            
            #vis {
                width: 100%;
                height: 100%;
            }
            
            footer {
                text-align: center;
                padding: 20px 0;
                font-size: 0.9rem;
                color: #5f6368;
                border-top: 1px solid #e0e0e0;
                margin-top: 30px;
            }
            
            .badge {
                display: inline-block;
                padding: 3px 8px;
                border-radius: 12px;
                background-color: var(--secondary-color);
                color: white;
                font-size: 0.8rem;
                margin-left: 10px;
            }
            
            @media (max-width: 768px) {
                .container {
                    padding: 10px;
                }
                
                .card-body {
                    min-height: 300px;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>Python代码转换的Vega-Lite可视化</h1>
                <p class="subtitle">通过chart2vega工具自动转换</p>
            </header>
            
            <div class="visualization-card">
                <div class="card-header">
                    <h2 class="card-title">{chart_title} <span class="badge">{chart_type}</span></h2>
                </div>
                <div class="card-body">
                    <div id="vis"></div>
                </div>
            </div>
            
            <footer>
                <p>由LIDA框架自动生成 | 使用Vega-Lite渲染</p>
            </footer>
        </div>
        
        <script type="text/javascript">
            const spec = {config_json};
            
            vegaEmbed('#vis', spec, {
                renderer: 'canvas',
                actions: true,
                theme: 'light'
            }).then(result => console.log('可视化加载成功')).catch(error => console.error('可视化加载失败:', error));
        </script>
    </body>
    </html>
    """
    
    try:
        # 准备模板变量
        chart_title = config.get("title", "数据可视化")
        
        # 转换为JSON字符串
        config_json = json.dumps(config, ensure_ascii=False)
        
        # 替换模板变量
        html_content = html_template.replace('{config_json}', config_json)
        html_content = html_content.replace('{chart_title}', chart_title)
        html_content = html_content.replace('{chart_type}', str(chart_type))
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"✅ HTML查看器已保存到: {output_path}")
    except Exception as e:
        print(f"❌ 创建HTML查看器时出错: {str(e)}")
        import traceback
        traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description='将Python可视化代码转换为Vega-Lite配置')
    parser.add_argument('input_file', help='包含Python可视化代码的输入文件路径')
    parser.add_argument('--output', '-o', help='Vega-Lite配置输出文件路径', default='vegalite_output.json')
    parser.add_argument('--html', help='HTML查看器输出文件路径', default='vegalite_viewer.html')
    parser.add_argument('--model', '-m', help='使用的LLM模型（默认为gpt-4-turbo）', default='gpt-4-turbo')
    parser.add_argument('--base-url', '-b', help='API基础URL', default=None)
    parser.add_argument('--api-key', '-k', help='API密钥', default=None)
    parser.add_argument('--no-html', action='store_true', help='不生成HTML查看器')
    
    args = parser.parse_args()
    
    # 读取Python代码
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            python_code = f.read()
    except Exception as e:
        print(f"❌ 读取Python代码文件时出错: {str(e)}")
        return
    
    # 转换为Vega-Lite
    llm_kwargs = {
        "model": args.model
    }
    if args.base_url:
        llm_kwargs["base_url"] = args.base_url
    if args.api_key:
        llm_kwargs["api_key"] = args.api_key
        
    vegalite_config = convert_python_to_vegalite(python_code, llm_kwargs=llm_kwargs)
    if vegalite_config:
        # 保存配置
        save_vegalite_config(vegalite_config, args.output)
        
        # 生成HTML查看器
        if not args.no_html:
            create_html_viewer(vegalite_config, args.html)
    else:
        print("❌ 转换失败")

if __name__ == "__main__":
    main() 