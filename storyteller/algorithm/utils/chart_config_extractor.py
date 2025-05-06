import json
import re
from typing import Dict, Any, List, Optional, Union, Tuple
import pandas as pd
import random
import os
import sys
import openai
from dotenv import load_dotenv
import numpy as np

# 加载环境变量
load_dotenv(override=True)

# 添加项目根目录到Python路径
# 获取当前文件的路径
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录（假设当前文件在storyteller/algorithm/utils/下）
project_root = os.path.abspath(os.path.join(current_dir, '../../..'))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入必要的函数
try:
    from storyteller.llm_call.openai_llm import call_openai
except ImportError:
    print("无法导入call_openai函数，将使用本地实现")
    # 提供一个简单的本地实现作为备份
    def call_openai(prompt, model="gpt-4o", **kwargs):
        """本地实现的OpenAI调用函数"""
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        
        if not api_key:
            raise ValueError("未找到OPENAI_API_KEY环境变量")
            
        client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url if base_url else "https://api.openai.com/v1"
        )
        
        try:
            # 打印调试信息
            #print(f"使用API密钥: {api_key[:5]}...{api_key[-5:]}")
            #print(f"使用基础URL: {base_url}")
            
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.0),
                max_tokens=kwargs.get("max_tokens", 4096),
                n=kwargs.get("n", 1),
                top_p=kwargs.get("top_p", 1.0),
                stop=kwargs.get("stop", None),
            )
            
            return [choice.message.content.strip() for choice in response.choices]
        except Exception as e:
            print(f"API调用失败: {str(e)}")
            if hasattr(e, 'response'):
                print(f"响应状态码: {e.response.status_code}")
                print(f"响应内容: {e.response.text}")
            return []

class ChartConfigExtractor:
    """
    使用LLM解析Python可视化代码，提取图表配置信息，
    以便转换为Chart.js或G2配置。
    """
    
    def __init__(self):
        """初始化提取器"""
        self.default_config = {
            "chart_type": "bar",
            "title": None,
            "x_field": None,
            "y_field": None,
            "data_columns": [],
            "hue_column": None,
            "is_stacked": False,
            "agg_method": None
        }

    def extract_from_code(self, code: str) -> Dict[str, Any]:
        """
        从代码中提取图表配置
        
        参数:
            code: 可视化代码字符串
            
        返回:
            包含图表配置的字典
        """
        try:
            # 自定义获取模板的方法，使用绝对路径
            def local_get_prompt(template_name, args):
                # 获取当前文件的目录
                current_dir = os.path.dirname(os.path.abspath(__file__))
                # 模板文件的完整路径
                template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))), 
                                            "storyteller", "templates", f"{template_name}.txt")
                
                print(f"尝试读取模板: {template_path}")
                
                if os.path.exists(template_path):
                    with open(template_path, "r", encoding="utf-8") as f:
                        template = f.read()
                    
                    # 替换模板中的参数
                    for key, value in args.items():
                        template = template.replace(f"{{{key}}}", str(value))
                    return template
                else:
                    print(f"警告: 模板文件不存在: {template_path}")
                    # 返回直接的提示词
                    return f"""
你是一位数据可视化专家，请分析下面的Python代码，提取用于生成图表的配置信息。
返回一个JSON对象，包含以下字段（如适用）：
- chart_type: 图表类型（bar, line, scatter, pie等）
- title: 图表标题
- x_field: x轴字段名
- y_field: y轴字段名（或要聚合的字段）
- agg_method: 聚合方法（如sum, mean, count等），如果代码中使用了value_counts()，则为"count"
- hue_column: 用于分组/颜色的字段名（如有）
- is_stacked: 是否为堆叠图
- data_columns: 代码中使用到的DataFrame列名列表

代码:
```python
{code}
```

注意：如果代码中使用了形如df.groupby('A')['B'].mean()的模式，则x_field应该是'A'，y_field应该是'B'，agg_method应该是'mean'。
如果使用了df['column'].value_counts()这样的代码，则x_field应该是'column'，agg_method应该是'count'。

请仅返回JSON格式的配置对象，不要有任何解释或其他文本。
"""
            
            # 准备参数
            prompt_args = {
                "CODE": code
            }
            
            # 获取模板（使用自定义方法）
            prompt = local_get_prompt("chart_config_analysis", prompt_args)
            
            # 直接使用环境变量中的API密钥和base_url（确保这里使用正确的环境变量名）
            api_key = os.environ.get("OPENAI_API_KEY")
            base_url = os.environ.get("OPENAI_BASE_URL")
            
            # 打印调试信息
            #if api_key:
            #    print(f"环境变量中的API密钥: {api_key[:5]}...{api_key[-5:]}")
            #if base_url:
            #    print(f"环境变量中的基础URL: {base_url}")
            
            # 调用LLM，显式传递API密钥和base_url
            responses = call_openai(prompt, api_key=api_key, base_url=base_url)
            
            if responses:
                response_text = responses[0].strip()
                print("✅ 成功获取LLM响应")
                
                # 解析JSON响应
                config = self._parse_json_response(response_text)
                
                # 如果获取到了配置
                if config:
                    # 填充默认值
                    return self._fill_config_defaults(config)
            
            # 如果没有获取到配置或解析失败
            print("⚠️ LLM调用未返回有效配置，返回默认配置")
            return self.default_config.copy()
        
        except Exception as e:
            print(f"提取图表配置时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            # 返回默认配置
            return self.default_config.copy()
    
    def _call_openai(self, prompt: str) -> Dict[str, Any]:
        """
        调用OpenAI API - 不再使用，保留为向后兼容
        改用统一的call_openai函数
        """
        try:
            # 使用项目的call_openai函数
            responses = call_openai(prompt)
            if responses:
                config_text = responses[0].strip()
                return self._parse_json_response(config_text)
            return None
        except Exception as e:
            print(f"调用OpenAI API时出错: {str(e)}")
            return None
    
    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """解析LLM返回的JSON响应"""
        try:
            # 直接尝试解析
            return json.loads(response_text)
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except:
                    print("无法解析提取的JSON部分")
            
            # 最后一次尝试：修复常见的JSON格式错误
            try:
                # 替换单引号为双引号
                fixed_text = response_text.replace("'", '"')
                # 确保属性名有双引号
                fixed_text = re.sub(r'(\w+):', r'"\1":', fixed_text)
                return json.loads(fixed_text)
            except:
                print("所有JSON解析尝试都失败了")
            
        return None
    
    def _fill_config_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """填充配置中缺失的默认值"""
        # 复制默认配置
        result = self.default_config.copy()
        
        # 确保不丢失派生列信息
        if "derived_columns" in config:
            result["derived_columns"] = config["derived_columns"]
        
        # 用提供的配置更新默认值
        result.update(config)
        
        # 确保图表类型有效
        if not result["chart_type"]:
            result["chart_type"] = "bar"
        
        # 智能构建标题（如果缺失）
        if not result["title"]:
            x_field = result.get("x_field", "")
            y_field = result.get("y_field", "")
            agg_method = result.get("agg_method", "")
            
            if agg_method and y_field:
                agg_display = {
                    "count": "Count of",
                    "sum": "Sum of",
                    "mean": "Average",
                    "min": "Minimum",
                    "max": "Maximum"
                }.get(agg_method, agg_method.capitalize())
                
                result["title"] = f"{agg_display} {y_field} by {x_field}"
            elif x_field and y_field:
                result["title"] = f"{y_field} by {x_field}"
        
        return result
    
    def extract_chart_data(self, df: pd.DataFrame, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        根据配置从DataFrame中提取图表数据
        
        参数:
            df: 原始DataFrame
            config: 图表配置字典，包含字段信息和聚合方法
            
        返回:
            Chart.js格式的图表数据
        """
        if df is None or df.empty:
            print("警告: 提供的DataFrame为空")
            return {
                "labels": [],
                "datasets": [{
                    "label": "空数据",
                    "data": [],
                }]
            }
            
        # 提取配置
        chart_type = config.get("chart_type", "bar")
        x_field = config.get("x_field")
        y_field = config.get("y_field")
        group_field = config.get("hue_column")
        
        # 修复: 安全处理agg_method，确保None值不会导致错误
        agg_method_raw = config.get("agg_method")
        if agg_method_raw is None:
            # 根据图表类型设置默认聚合方法
            if chart_type in ["boxplot", "violin", "histogram", "scatter"]:
                agg_method = "none"  # 这些类型不需要聚合
            else:
                agg_method = "sum"   # 默认使用sum作为聚合方法
        else:
            agg_method = str(agg_method_raw).lower()
            
        is_stacked = config.get("is_stacked", False)
        
        # 复制数据以避免修改原始数据
        df_copy = df.copy()
        
        # 处理派生列 - 如果配置中包含derived_columns
        if "derived_columns" in config and isinstance(config["derived_columns"], list):
            print("发现派生列定义，准备处理...")
            for derived_col in config["derived_columns"]:
                col_name = derived_col.get("name")
                source_col = derived_col.get("source_column")
                derivation_type = derived_col.get("derivation_type", "").lower()
                parameters = derived_col.get("parameters", {})
                
                if not col_name or not source_col:
                    print(f"警告: 派生列定义不完整，跳过: {derived_col}")
                    continue
                
                # 验证源列存在
                if source_col not in df_copy.columns:
                    print(f"警告: 源列 '{source_col}' 不存在，跳过派生列 '{col_name}'")
                    continue
                
                try:
                    # 根据不同的派生类型处理
                    if derivation_type == "bin":
                        # 处理分箱操作
                        bins = parameters.get("bins")
                        labels = parameters.get("labels")
                        right = parameters.get("right", True)
                        
                        if isinstance(bins, list) and isinstance(labels, list):
                            print(f"对列 '{source_col}' 进行分箱操作，创建派生列 '{col_name}'")
                            df_copy[col_name] = pd.cut(df_copy[source_col], 
                                                      bins=bins, 
                                                      labels=labels, 
                                                      right=right)
                            print(f"✅ 成功创建分箱列: {col_name}")
                        else:
                            print(f"警告: 分箱操作缺少必要参数，跳过")
                    
                    elif derivation_type == "transform":
                        # 处理变换操作
                        transform_type = parameters.get("type", "").lower()
                        
                        if transform_type == "log":
                            df_copy[col_name] = np.log(df_copy[source_col])
                            print(f"✅ 成功创建对数变换列: {col_name}")
                        elif transform_type == "sqrt":
                            df_copy[col_name] = np.sqrt(df_copy[source_col])
                            print(f"✅ 成功创建平方根变换列: {col_name}")
                        elif transform_type == "zscore":
                            df_copy[col_name] = (df_copy[source_col] - df_copy[source_col].mean()) / df_copy[source_col].std()
                            print(f"✅ 成功创建Z分数标准化列: {col_name}")
                        else:
                            print(f"警告: 不支持的变换类型: {transform_type}")
                    
                    elif derivation_type == "calculate":
                        # 处理计算派生列
                        expression = parameters.get("expression")
                        if expression:
                            # 安全地评估表达式 (仅支持简单的数学运算)
                            # 例如: "df['A'] * 2 + df['B']"
                            if "df[" in expression:
                                locals_dict = {"df": df_copy, "np": np}
                                df_copy[col_name] = eval(expression, {"__builtins__": {}}, locals_dict)
                                print(f"✅ 成功创建计算列: {col_name}")
                            else:
                                print(f"警告: 计算表达式格式无效: {expression}")
                        else:
                            print(f"警告: 计算派生列缺少表达式参数")
                    
                    else:
                        print(f"警告: 未知的派生类型: {derivation_type}")
                
                except Exception as e:
                    print(f"创建派生列 '{col_name}' 时出错: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            # 如果x_field是派生列名称，需要确保它已经被创建
            if x_field and x_field not in df_copy.columns:
                for derived_col in config["derived_columns"]:
                    if derived_col.get("name") == x_field:
                        print(f"注意: X轴字段 '{x_field}' 是派生列，已处理")
                        break
                else:
                    print(f"警告: X轴字段 '{x_field}' 不存在且未在派生列中定义")
        
        # 验证必要字段
        if not x_field or x_field not in df_copy.columns:
            print(f"警告: X轴字段 '{x_field}' 不存在，尝试选择合适的替代列")
            # 尝试选择替代的X轴字段
            for col in df_copy.columns:
                if pd.api.types.is_string_dtype(df_copy[col]) or pd.api.types.is_categorical_dtype(df_copy[col]):
                    x_field = col
                    print(f"使用 '{x_field}' 作为替代X轴字段")
                    break
            else:
                x_field = df_copy.columns[0]
                print(f"使用第一列 '{x_field}' 作为X轴字段")
        
        # 特殊处理聚合方法为count的情况
        if agg_method == "count":
            # 当聚合方法为count时，y_field可以不存在，将使用计数聚合
            # 但如果提供了y_field，我们会验证它
            if y_field and y_field not in df_copy.columns and y_field != "count":
                print(f"警告: 'count'聚合不需要特定Y轴字段，但若提供需存在")
                # 查找任意可用列作为辅助列以用于计数
                for col in df_copy.columns:
                    if col != x_field:
                        y_field = col
                        print(f"使用'{y_field}'仅用于计数")
                        break
                else:
                    y_field = None
                    print("对x轴字段值计数")
        elif y_field and y_field not in df_copy.columns:
            print(f"警告: Y轴字段 '{y_field}' 不存在，尝试选择合适的替代列")
            # 尝试选择替代的Y轴字段
            for col in df_copy.columns:
                if pd.api.types.is_numeric_dtype(df_copy[col]) and col != x_field:
                    y_field = col
                    print(f"使用 '{y_field}' 作为替代Y轴字段")
                    break
            else:
                # 如果找不到合适的数值列，计数就好
                print(f"未找到合适的数值列，将使用计数作为Y轴")
                agg_method = "count"
                y_field = None
                
        if group_field and group_field not in df_copy.columns:
            print(f"警告: 分组字段 '{group_field}' 不存在")
            group_field = None

        # 检查列的数据类型和处理复杂数据
        for col in [x_field, y_field, group_field]:
            if col and col in df_copy.columns:
                # 检查列是否包含列表/字典等复杂类型
                if df_copy[col].apply(lambda x: isinstance(x, (list, dict, tuple))).any():
                    print(f"警告: 列 '{col}' 包含复杂数据类型，尝试转换为字符串")
                    df_copy[col] = df_copy[col].astype(str)
                # 尝试将对象类型转换为字符串，以避免多维度问题
                elif df_copy[col].dtype == 'object':
                    df_copy[col] = df_copy[col].astype(str)
            
        # 特殊处理boxplot和类似的分布图表类型
        if chart_type in ["boxplot", "violin", "histogram", "scatter"]:
            try:
                # 这些图表类型通常不需要聚合，直接使用原始数据
                if x_field and y_field and y_field in df_copy.columns:
                    print(f"为{chart_type}类型准备数据，不使用聚合...")
                    
                    # 散点图特殊处理 - 直接返回原始数据点
                    if chart_type == "scatter":
                        # 确保x和y字段都是数值类型
                        for field, name in [(x_field, 'X轴'), (y_field, 'Y轴')]:
                            if not pd.api.types.is_numeric_dtype(df_copy[field]):
                                try:
                                    print(f"{name}字段不是数值类型，尝试转换...")
                                    df_copy[field] = pd.to_numeric(df_copy[field], errors='coerce')
                                except:
                                    print(f"无法将{name}字段转换为数值类型")
                        
                        # 去除缺失值
                        valid_data = df_copy.dropna(subset=[x_field, y_field])
                        if len(valid_data) < len(df_copy):
                            print(f"警告: 移除了{len(df_copy)-len(valid_data)}行含缺失值的数据")
                        
                        # 为散点图返回所有数据点
                        return {
                            "type": "scatter",
                            "datasets": [{
                                "label": y_field,
                                "data": [{"x": x, "y": y} for x, y in zip(valid_data[x_field].tolist(), valid_data[y_field].tolist())],
                                "backgroundColor": 'rgba(54, 162, 235, 0.7)',
                                "borderColor": 'rgba(54, 162, 235, 1.0)',
                                "borderWidth": 1,
                                "pointRadius": 4,
                                "pointHoverRadius": 6
                            }]
                        }
                    
                    # boxplot等其他分布图表处理
                    # 获取唯一的x值作为标签
                    unique_x = df_copy[x_field].unique()
                    labels = [str(x) for x in unique_x]
                    
                    # 为每个x值创建对应的y值数组
                    datasets = []
                    for x_val in unique_x:
                        y_values = df_copy[df_copy[x_field] == x_val][y_field].tolist()
                        datasets.append({
                            "label": str(x_val),
                            "data": y_values
                        })
                    
                    return {
                        "type": chart_type,  # 添加图表类型
                        "labels": labels,
                        "datasets": datasets
                    }
            except Exception as e:
                print(f"处理{chart_type}数据时出错: {str(e)}")
                import traceback
                traceback.print_exc()
                # 继续使用标准图表处理逻辑
        
        # 聚合函数映射
        agg_map = {
            "sum": "sum",
            "average": "mean",
            "mean": "mean",
            "count": "count",
            "max": "max",
            "min": "min",
            "median": "median",
            "none": None  # 不进行聚合
        }
        
        # 确定使用的聚合函数
        pandas_agg = agg_map.get(agg_method, "sum")
        
        # 处理不同图表类型
        if chart_type == "pie":
            # 饼图逻辑
            try:
                if y_field and y_field in df_copy.columns:
                    if pandas_agg == "count":
                        grouped = df_copy.groupby(x_field).size()
                    else:
                        grouped = df_copy.groupby(x_field)[y_field].agg(pandas_agg)
                else:
                    # 没有y值，使用计数
                    grouped = df_copy[x_field].value_counts()
                    
                # 准备饼图数据
                labels = grouped.index.astype(str).tolist()
                values = grouped.values.tolist()
                
                # 颜色配置
                colors = [
                    'rgba(255, 99, 132, 0.7)',
                    'rgba(54, 162, 235, 0.7)',
                    'rgba(255, 206, 86, 0.7)',
                    'rgba(75, 192, 192, 0.7)',
                    'rgba(153, 102, 255, 0.7)',
                    'rgba(255, 159, 64, 0.7)',
                    'rgba(199, 199, 199, 0.7)'
                ]
                
                # 构建Chart.js数据
                return {
                    "labels": labels,
                    "datasets": [{
                        "data": values,
                        "backgroundColor": colors[:len(labels)] if len(labels) <= len(colors) else colors * (len(labels) // len(colors) + 1)
                    }]
                }
            except Exception as e:
                print(f"处理饼图数据时出错: {str(e)}")
                import traceback
                traceback.print_exc()
                # 返回空数据
                return {
                    "labels": ["样本1", "样本2", "样本3"],
                    "datasets": [{
                        "data": [1, 1, 1],
                        "backgroundColor": ['rgba(255, 99, 132, 0.7)', 'rgba(54, 162, 235, 0.7)', 'rgba(255, 206, 86, 0.7)']
                    }]
                }
        elif group_field and group_field in df_copy.columns:
            # 多系列数据
            try:
                # 确保X轴和分组字段为一维（字符串或分类）
                if df_copy[x_field].dtype not in ['object', 'category', 'string']:
                    print(f"将X轴字段 '{x_field}' 转换为字符串类型")
                    df_copy[x_field] = df_copy[x_field].astype(str)
                    
                if df_copy[group_field].dtype not in ['object', 'category', 'string']:
                    print(f"将分组字段 '{group_field}' 转换为字符串类型")
                    df_copy[group_field] = df_copy[group_field].astype(str)
                
                if y_field and y_field in df_copy.columns:
                    if pandas_agg == "count":
                        # 使用crosstab进行计数
                        pivot_data = pd.crosstab(df_copy[x_field], df_copy[group_field])
                    elif pandas_agg is None:
                        # 不使用聚合，只是按组分组数据
                        print("不使用聚合，展示所有数据点")
                        # 这种情况需要特殊处理，返回每个组的所有原始数据点
                        groups = df_copy[group_field].unique()
                        labels = df_copy[x_field].unique().astype(str).tolist()
                        
                        datasets = []
                        colors = [
                            'rgba(255, 99, 132, 0.7)',
                            'rgba(54, 162, 235, 0.7)',
                            'rgba(255, 206, 86, 0.7)',
                            'rgba(75, 192, 192, 0.7)',
                            'rgba(153, 102, 255, 0.7)',
                            'rgba(255, 159, 64, 0.7)'
                        ]
                        
                        for i, group in enumerate(groups):
                            color = colors[i % len(colors)]
                            group_data = df_copy[df_copy[group_field] == group]
                            
                            datasets.append({
                                'label': str(group),
                                'data': group_data[y_field].tolist(),
                                'backgroundColor': color,
                                'borderColor': color.replace('0.7', '1.0'),
                                'borderWidth': 1
                            })
                        
                        return {
                            "labels": labels,
                            "datasets": datasets
                        }
                    else:
                        # 使用pivot_table进行其他聚合
                        pivot_data = pd.pivot_table(
                            df_copy, 
                            index=x_field, 
                            columns=group_field, 
                            values=y_field, 
                            aggfunc=pandas_agg
                        )
                else:
                    # 没有Y值，使用计数
                    pivot_data = pd.crosstab(df_copy[x_field], df_copy[group_field])
                
                # 准备标签和数据集
                labels = pivot_data.index.astype(str).tolist()
                
                # 颜色配置
                colors = [
                    'rgba(255, 99, 132, 0.7)',
                    'rgba(54, 162, 235, 0.7)',
                    'rgba(255, 206, 86, 0.7)',
                    'rgba(75, 192, 192, 0.7)',
                    'rgba(153, 102, 255, 0.7)',
                    'rgba(255, 159, 64, 0.7)',
                    'rgba(199, 199, 199, 0.7)'
                ]
                
                # 创建数据集
                datasets = []
                for i, category in enumerate(pivot_data.columns):
                    color = colors[i % len(colors)]
                    datasets.append({
                        'label': str(category),
                        'data': pivot_data[category].tolist(),
                        'backgroundColor': color,
                        'borderColor': color.replace('0.7', '1.0'),
                        'borderWidth': 1
                    })
                
                # Chart.js格式
                return {
                    "labels": labels,
                    "datasets": datasets
                }
            except Exception as e:
                print(f"处理分组数据时出错: {str(e)}")
                import traceback
                traceback.print_exc()
                # 回退到简单的单系列图
                group_field = None
                # 继续到单系列逻辑
        
        # 单系列数据
        try:
            if y_field and y_field in df_copy.columns:
                if pandas_agg == "count":
                    grouped = df_copy.groupby(x_field)[y_field].count()
                elif pandas_agg is None:
                    # 不需要聚合的情况，直接使用原始数据
                    print("单系列数据不使用聚合")
                    labels = df_copy[x_field].astype(str).unique().tolist()
                    values = df_copy[y_field].tolist()
                    
                    return {
                        "labels": labels,
                        "datasets": [{
                            "label": y_field,
                            "data": values,
                            "backgroundColor": 'rgba(54, 162, 235, 0.7)',
                            "borderColor": 'rgba(54, 162, 235, 1.0)',
                            "borderWidth": 1
                        }]
                    }
                else:
                    grouped = df_copy.groupby(x_field)[y_field].agg(pandas_agg)
            else:
                # 没有y值，使用计数
                grouped = df_copy[x_field].value_counts().sort_index()
            
            # 准备标签和数据
            labels = grouped.index.astype(str).tolist()
            values = grouped.values.tolist()
            
            # Chart.js格式
            return {
                "labels": labels,
                "datasets": [{
                    "label": y_field or f"{x_field} 计数",
                    "data": values,
                    "backgroundColor": 'rgba(54, 162, 235, 0.7)',
                    "borderColor": 'rgba(54, 162, 235, 1.0)',
                    "borderWidth": 1
                }]
            }
        except Exception as e:
            print(f"处理单系列数据时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            # 返回示例数据以避免完全失败
            return {
                "labels": ["类别A", "类别B", "类别C"],
                "datasets": [{
                    "label": "示例数据",
                    "data": [10, 20, 30],
                    "backgroundColor": 'rgba(54, 162, 235, 0.7)',
                    "borderColor": 'rgba(54, 162, 235, 1.0)',
                    "borderWidth": 1
                }]
            }
    
    def resolve_chart_data(self, df: pd.DataFrame, config: Dict[str, Any] = None):
        """
        根据配置从DataFrame中提取数据
        
        参数:
            df: DataFrame对象
            config: 图表配置
            
        返回:
            图表数据对象
        """
        if config is None:
            config = {}
            
        try:
            # 直接使用pandas处理数据
            print("使用pandas处理图表数据...")
            chart_data = self.extract_chart_data(df, config)
            if chart_data:
                print("✅ 使用pandas成功处理图表数据")
                return chart_data
        except Exception as e:
            print(f"使用pandas处理数据失败，将回退到基础处理: {str(e)}")
            import traceback
            traceback.print_exc()
        
        # 回退到基础的规则处理方式
        print("回退到基础规则处理...")
        chart_type = config.get("chart_type", "bar")
        x_field = config.get("x_field")
        y_field = config.get("y_field")
        hue_field = config.get("hue_column")
        agg_method = config.get("agg_method")
        
        # 修复：确保agg_method不为None时，设置一个默认值
        if agg_method is None:
            # 根据图表类型设置适当的默认值
            if chart_type in ["boxplot", "violin", "histogram", "scatter"]:
                # 这些类型不需要聚合方法
                agg_method = "none"
            else:
                # 默认聚合方法
                agg_method = "sum"
                
        is_stacked = config.get("is_stacked", False)
        
        # 如果x_field和y_field都是None，尝试使用默认值
        if x_field is None:
            # 尝试使用第一个字符串或分类列作为x轴
            for col in df.columns:
                if df[col].dtype == 'object' or pd.api.types.is_categorical_dtype(df[col]):
                    x_field = col
                    print(f"警告: 未指定X轴字段，自动使用 '{x_field}'")
                    break
        
            # 如果还是找不到，使用第一列
            if x_field is None and len(df.columns) > 0:
                x_field = df.columns[0]
                print(f"警告: 未指定X轴字段，自动使用第一列 '{x_field}'")
        
        if y_field is None:
            # 如果y_field是None，尝试使用第一个数值列作为y轴
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]) and col != x_field:
                    y_field = col
                    print(f"警告: 未指定Y轴字段，自动使用 '{y_field}'")
                    break
        
            # 如果还是找不到，使用第二列或最后一列
            if y_field is None:
                if len(df.columns) > 1:
                    y_field = df.columns[1] if df.columns[1] != x_field else df.columns[-1]
                elif len(df.columns) > 0 and df.columns[0] != x_field:
                    y_field = df.columns[0]
            else:
                # 实在没有合适的列，使用索引
                print(f"警告: 未找到合适的Y轴字段，将使用数据行索引")
                temp_df = df.copy()
                temp_df['row_index'] = range(len(df))
                df = temp_df
                y_field = 'row_index'
        
        # 验证字段存在
        try:
            self._validate_fields(df, config)
        except ValueError as e:
            print(f"警告: {str(e)}")
            # 在验证失败时不抛出异常，而是打印警告并继续
        
        # 根据图表类型处理数据
        if chart_type == "pie":
            return self._prepare_pie_data(df, x_field, y_field, agg_method)
        elif hue_field and hue_field in df.columns:
            return self._prepare_grouped_data(df, x_field, y_field, hue_field, agg_method, is_stacked)
        else:
            return self._prepare_single_series_data(df, x_field, y_field, agg_method)
    
    def _validate_fields(self, df: pd.DataFrame, config: Dict[str, Any]):
        """验证并修正字段名称，确保它们存在于DataFrame中"""
        # 简单验证
        x_field = config.get("x_field")
        if x_field and x_field not in df.columns:
            raise ValueError(f"X轴字段 '{x_field}' 在DataFrame中不存在")
        
        y_field = config.get("y_field")
        # 对于聚合操作，y可能不是直接的列名
        if y_field and y_field not in df.columns and y_field not in ["count", "mean", "sum", "median", "min", "max"]:
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            if numeric_cols:
                config["y_field"] = numeric_cols[0]
                print(f"警告: Y轴字段 '{y_field}' 不存在，使用 '{numeric_cols[0]}' 替代")
    
    def _prepare_pie_data(self, df: pd.DataFrame, x_field: str, y_field: str, agg_method: str):
        """准备饼图数据"""
        if not x_field or x_field not in df.columns:
            raise ValueError("饼图需要有效的类别字段")
        
        try:
            # 如果是聚合操作
            if y_field and y_field in df.columns:
                if agg_method == "count":
                    # 特别处理count聚合方法 - 计算每个x_field值的计数
                    data = df.groupby(x_field)[y_field].count()
                elif agg_method == "mean":
                    data = df.groupby(x_field)[y_field].mean()
                elif agg_method in [None, "none"]:
                    # 对于不需要聚合的情况，我们需要一个默认行为
                    print("饼图通常需要聚合，使用sum作为默认聚合方法")
                    data = df.groupby(x_field)[y_field].sum()
                else:  # 默认使用sum
                    data = df.groupby(x_field)[y_field].sum()
            else:
                # 如果只有x字段，使用计数
                data = df[x_field].value_counts()
            
            # 准备图表数据
            labels = data.index.tolist()
            values = data.values.tolist()
            
            # Chart.js格式
            return {
                "labels": labels,
                "datasets": [{
                    "data": values,
                    "backgroundColor": [
                        'rgba(255, 99, 132, 0.7)',
                        'rgba(54, 162, 235, 0.7)',
                        'rgba(255, 206, 86, 0.7)',
                        'rgba(75, 192, 192, 0.7)',
                        'rgba(153, 102, 255, 0.7)',
                        'rgba(255, 159, 64, 0.7)',
                        'rgba(199, 199, 199, 0.7)'
                    ]
                }]
            }
        except Exception as e:
            print(f"准备饼图数据时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 返回基本的错误数据结构
            return {
                "labels": ["错误", "请检查数据"],
                "datasets": [{
                    "label": "错误数据",
                    "data": [0, 0],
                    "backgroundColor": ['rgba(255, 99, 132, 0.7)', 'rgba(54, 162, 235, 0.7)'],
                    "borderColor": ['rgba(255, 99, 132, 1.0)', 'rgba(54, 162, 235, 1.0)'],
                    "borderWidth": 1
                }]
            }
    
    def _prepare_grouped_data(self, df: pd.DataFrame, x_field: str, y_field: str, hue_field: str, agg_method: str, is_stacked: bool):
        """准备分组数据（多系列）"""
        if not x_field or x_field not in df.columns:
            raise ValueError(f"X轴字段 '{x_field}' 不存在")
        if not hue_field or hue_field not in df.columns:
            raise ValueError(f"分组字段 '{hue_field}' 不存在")
        
        try:
            # 克隆数据，避免修改原数据
            df_copy = df.copy()
            
            # 确保数据类型正确，特别是处理一维性问题
            for col in [x_field, y_field, hue_field]:
                if col and col in df.columns:
                    # 检查列是否包含列表/字典等复杂类型
                    if df[col].apply(lambda x: isinstance(x, (list, dict, tuple))).any():
                        print(f"警告: 列 '{col}' 包含复杂数据类型，转换为字符串")
                        df_copy[col] = df_copy[col].astype(str)
                    # 将对象类型转为字符串，避免多维度问题
                    elif df[col].dtype == 'object' or not pd.api.types.is_categorical_dtype(df[col]):
                        # 确保是字符串类型以避免"not 1-dimensional"错误
                        df_copy[col] = df_copy[col].astype(str)
                        print(f"将列 '{col}' 转换为字符串类型以确保一维性")
            
            # 处理不同的聚合方法
            if y_field and y_field in df.columns:
                try:
                    if agg_method == "count":
                        # 使用crosstab进行计数
                        pivot_data = pd.crosstab(df_copy[x_field], df_copy[hue_field])
                    elif agg_method == "mean":
                        pivot_data = pd.pivot_table(df_copy, index=x_field, columns=hue_field, values=y_field, aggfunc='mean')
                    elif agg_method in ["sum", None]:
                        # 默认使用sum，如果agg_method为None也使用sum
                        agg_func = 'sum' if agg_method != None else None
                        pivot_data = pd.pivot_table(df_copy, index=x_field, columns=hue_field, values=y_field, aggfunc=agg_func)
                    else:
                        # 尝试使用其他聚合方法
                        pivot_data = pd.pivot_table(df_copy, index=x_field, columns=hue_field, values=y_field, aggfunc=agg_method)
                except Exception as e:
                    print(f"使用pivot_table聚合数据时出错: {str(e)}")
                    # 尝试一种更安全的方法
                    print("尝试使用替代方法处理数据...")
                    
                    # 使用groupby和unstack，这对某些数据结构更友好
                    if agg_method == "count":
                        grouped = df_copy.groupby([x_field, hue_field]).size()
                    else:
                        grouped = df_copy.groupby([x_field, hue_field])[y_field].agg(agg_method or 'sum')
                    
                    # 解构为二维表
                    try:
                        pivot_data = grouped.unstack(fill_value=0)
                    except Exception as inner_e:
                        print(f"unstack操作失败: {str(inner_e)}")
                        # 最后的尝试：使用crosstab
                        if y_field:
                            # 按x和hue进行交叉表统计
                            pivot_data = pd.crosstab(
                                df_copy[x_field], 
                                df_copy[hue_field],
                                values=df_copy[y_field],
                                aggfunc=agg_method or 'sum'
                            )
                        else:
                            # 如果没有y值，使用简单的计数
                            pivot_data = pd.crosstab(df_copy[x_field], df_copy[hue_field])
            else:
                # 如果没有y字段，使用计数
                try:
                    pivot_data = pd.crosstab(df_copy[x_field], df_copy[hue_field])
                except Exception as e:
                    print(f"使用crosstab计数时出错: {str(e)}")
                    # 尝试更安全的方法
                    grouped = df_copy.groupby([x_field, hue_field]).size()
                    pivot_data = grouped.unstack(fill_value=0)
            
            # 准备标签和数据集
            labels = pivot_data.index.astype(str).tolist()
            
            # 颜色配置
            colors = [
                'rgba(255, 99, 132, 0.7)',
                'rgba(54, 162, 235, 0.7)',
                'rgba(255, 206, 86, 0.7)',
                'rgba(75, 192, 192, 0.7)',
                'rgba(153, 102, 255, 0.7)',
                'rgba(255, 159, 64, 0.7)'
            ]
            
            # 创建数据集
            datasets = []
            for i, category in enumerate(pivot_data.columns):
                color = colors[i % len(colors)]
                datasets.append({
                    'label': str(category),
                    'data': pivot_data[category].tolist(),
                    'backgroundColor': color,
                    'borderColor': color.replace('0.7', '1.0'),
                    'borderWidth': 1
                })
            
            # Chart.js格式
            return {
                "labels": labels,
                "datasets": datasets
            }
        except Exception as e:
            print(f"准备分组数据时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 返回基本的错误数据结构
            return {
                "labels": ["错误", "请检查数据"],
                "datasets": [{
                    "label": "错误数据",
                    "data": [0, 0],
                    "backgroundColor": 'rgba(255, 99, 132, 0.7)',
                    "borderColor": 'rgba(255, 99, 132, 1.0)',
                    "borderWidth": 1
                }]
            }
    
    def _prepare_single_series_data(self, df: pd.DataFrame, x_field: str, y_field: str, agg_method: str):
        """准备单系列数据"""
        # 确保x_field存在于DataFrame中
        if x_field is None or x_field not in df.columns:
            print(f"警告: X轴字段 '{x_field}' 不存在或为None，使用索引作为X轴")
            # 创建一个临时DataFrame，使用索引作为X轴
            temp_df = df.copy()
            temp_df['index_as_x'] = range(len(df))
            df = temp_df
            x_field = 'index_as_x'
        
        try:    
            # 克隆数据，避免修改原数据
            df_copy = df.copy()
            
            # 确保数据类型正确
            for col in [x_field, y_field]:
                if col and col in df.columns:
                    # 将对象类型转为字符串，避免多维度问题
                    if df[col].dtype == 'object':
                        df_copy[col] = df_copy[col].astype(str)
            
            # 如果y是值字段并且存在
            if y_field and y_field in df.columns:
                if agg_method == "mean":
                    grouped = df_copy.groupby(x_field)[y_field].mean()
                elif agg_method == "count":
                    grouped = df_copy.groupby(x_field)[y_field].count()
                elif agg_method == "sum":
                    grouped = df_copy.groupby(x_field)[y_field].sum()
                elif agg_method in [None, "none"]:
                    # 对于不需要聚合的情况（如箱线图等）
                    print("不使用聚合方法，直接使用原始数据")
                    
                    # 为简单起见，我们返回每个x值的所有y值平均
                    # 这不是理想的箱线图数据格式，但可以作为后备选项
                    grouped = df_copy.groupby(x_field)[y_field].mean()
                    
                    # 备注：真正的箱线图数据应返回每个x的所有y值以计算分位数
                    # 但Chart.js标准格式不完全支持这种结构，所以这里简化处理
                else:  # 默认使用sum
                    grouped = df_copy.groupby(x_field)[y_field].sum()
            else:
                # 如果y_field不存在或为None，使用计数
                print(f"警告: Y轴字段 '{y_field}' 不存在或为None，使用计数作为Y轴")
                grouped = df_copy[x_field].value_counts().sort_index()
                    
            # 准备标签和数据
            labels = grouped.index.astype(str).tolist()
            values = grouped.values.tolist()
                
            # Chart.js格式
            return {
                "labels": labels,
                "datasets": [{
                    "label": y_field or "Count",
                    "data": values,
                    "backgroundColor": 'rgba(54, 162, 235, 0.7)',
                    "borderColor": 'rgba(54, 162, 235, 1.0)',
                    "borderWidth": 1
                }]
            }
        except Exception as e:
            print(f"准备单系列数据时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 返回基本的错误数据结构
            return {
                "labels": ["错误", "请检查数据"],
                "datasets": [{
                    "label": "错误数据",
                    "data": [0, 0],
                    "backgroundColor": 'rgba(54, 162, 235, 0.7)',
                    "borderColor": 'rgba(54, 162, 235, 1.0)',
                    "borderWidth": 1
                }]
            }
    
    def convert_to_chartjs_config(self, config: Dict[str, Any], chart_data=None) -> Dict[str, Any]:
        """
        将提取的配置转换为Chart.js配置
        
        参数:
            config: 提取的图表配置
            chart_data: 可选的预处理数据
            
        返回:
            Chart.js配置对象
        """
        chart_type = config.get("chart_type", "bar")
        title = config.get("title", "")
        x_field = config.get("x_field", "")
        y_field = config.get("y_field", "")
        is_stacked = config.get("is_stacked", False)
        
        # 映射图表类型到Chart.js类型
        chart_type_map = {
            "scatter": "scatter",
            "boxplot": "boxplot",
            "violin": "violin",
            "histogram": "bar",
            "bar": "bar",
            "line": "line",
            "pie": "pie",
            "doughnut": "doughnut"
        }
        chartjs_type = chart_type_map.get(chart_type, chart_type)
        
        # Chart.js配置
        chartjs_config = {
            "type": chartjs_type,
            "data": {"labels": [], "datasets": []},
            "options": {
                "responsive": True,
                "plugins": {
                    "title": {
                        "display": bool(title),
                        "text": title
                    },
                    "legend": {
                        "display": True
                    },
                    "tooltip": {
                        "mode": "index",
                        "intersect": False
                    }
                }
            }
        }
        
        # 如果有chart_data，替换数据部分
        if chart_data is not None:
            # 散点图特殊处理
            if chart_type == "scatter" and "type" in chart_data and chart_data["type"] == "scatter":
                # 散点图数据格式不同
                chartjs_config["data"] = {
                    "datasets": chart_data.get("datasets", [])
                }
            else:
                chartjs_config["data"] = chart_data
        
        # 配置各图表类型的特定选项
        if chart_type == "scatter":
            # 散点图特定配置
            chartjs_config["options"]["scales"] = {
                "x": {
                    "type": "linear",
                    "position": "bottom",
                    "title": {
                        "display": True,
                        "text": x_field
                    }
                },
                "y": {
                    "title": {
                        "display": True,
                        "text": y_field
                    }
                }
            }
        elif chart_type != "pie":
            # 其他非饼图的轴配置
            chartjs_config["options"]["scales"] = {
                "x": {
                    "title": {
                        "display": True,
                        "text": x_field
                    }
                },
                "y": {
                    "title": {
                        "display": True,
                        "text": y_field
                    }
                }
            }
        
        # 堆叠配置
        if is_stacked and chart_type == "bar":
            chartjs_config["options"]["scales"]["x"]["stacked"] = True
            chartjs_config["options"]["scales"]["y"]["stacked"] = True
        
        return chartjs_config
    
    def convert_to_antv_config(self, config: Dict[str, Any], chart_data=None) -> Dict[str, Any]:
        """
        将提取的配置转换为AntV G2配置
        
        参数:
            config: 提取的图表配置
            chart_data: 可选的预处理数据
            
        返回:
            AntV G2配置对象
        """
        chart_type = config.get("chart_type", "bar")
        title = config.get("title", "")
        x_field = config.get("x_field", "")
        y_field = config.get("y_field", "")
        hue_field = config.get("hue_column")
        is_stacked = config.get("is_stacked", False)
        
        # 颜色配置 - Chart.js风格的半透明颜色
        colors = [
            'rgba(255, 99, 132, 0.7)',   # 红色
            'rgba(54, 162, 235, 0.7)',   # 蓝色
            'rgba(255, 206, 86, 0.7)',   # 黄色
            'rgba(75, 192, 192, 0.7)',   # 绿色
            'rgba(153, 102, 255, 0.7)',  # 紫色
            'rgba(255, 159, 64, 0.7)',   # 橙色
            'rgba(199, 199, 199, 0.7)'   # 灰色
        ]
        
        # 映射Chart.js类型到G2类型
        type_map = {
            "bar": "interval",
            "line": "line",
            "scatter": "point",
            "pie": "pie",
            "boxplot": "box",
            "histogram": "histogram",
            "heatmap": "heatmap"
        }
        g2_type = type_map.get(chart_type, "interval")
        
        # 构建基础G2配置
        g2_config = {
            "type": g2_type,
            "data": [],
            "title": title,
            "autoFit": True,
            "animation": True
        }
        
        # 根据图表类型添加特定配置
        if chart_type == "pie":
            g2_config.update({
                "angleField": "value",
                "colorField": "category",
                "radius": 0.8,
                "label": {
                    "type": "outer",
                    "content": "{name}: {percentage}"
                },
                "color": colors  # 使用Chart.js风格颜色
            })
            
            # 提取饼图数据
            if chart_data is not None:
                pie_data = []
                for i, label in enumerate(chart_data["labels"]):
                    pie_data.append({
                        "category": label,
                        "value": chart_data["datasets"][0]["data"][i]
                    })
                g2_config["data"] = pie_data
        elif chart_type == "scatter":
            # 散点图特殊配置
            g2_config.update({
                "xField": "x",
                "yField": "y",
                "shape": "circle",
                "pointStyle": {
                    "fillOpacity": 0.7,
                    "stroke": "#ffffff",
                    "lineWidth": 0.5
                },
                "tooltip": {
                    "showMarkers": False
                },
                "state": {
                    "active": {
                        "style": {
                            "shadowBlur": 4,
                            "stroke": "#000",
                            "fill": "red"
                        }
                    }
                }
            })
            
            # 处理散点图数据
            if chart_data is not None and "datasets" in chart_data:
                # 散点图数据需要扁平化处理
                scatter_data = []
                dataset = chart_data["datasets"][0]
                
                if "data" in dataset and isinstance(dataset["data"], list):
                    # 数据可能是已经处理好的格式：[{x:..., y:...}, ...]
                    if isinstance(dataset["data"][0], dict) and "x" in dataset["data"][0] and "y" in dataset["data"][0]:
                        scatter_data = dataset["data"]
                    # 或者是原始的xy数组，需要转换
                    else:
                        for i, point in enumerate(dataset["data"]):
                            if isinstance(point, (list, tuple)) and len(point) >= 2:
                                scatter_data.append({"x": point[0], "y": point[1]})
                            elif isinstance(point, (int, float)):
                                # 假设是y值，x为索引
                                scatter_data.append({"x": i, "y": point})
                
                g2_config["data"] = scatter_data
        else:
            # 非饼图通用配置
            g2_config.update({
                "xField": x_field,
                "yField": y_field
            })
            
            # 添加分组字段
            if hue_field:
                g2_config["seriesField"] = hue_field
                # 使用Chart.js风格的颜色
                g2_config["color"] = colors
            else:
                # 单系列数据时使用单一颜色
                g2_config["color"] = colors[0]
            
            # 堆叠配置
            if is_stacked and chart_type == "bar":
                g2_config["isStack"] = True
            
            # 图表样式配置
            if chart_type == "bar" or chart_type == "column":
                # 为柱状图添加样式
                g2_config["columnStyle"] = {
                    "fill": colors[0],
                    "fillOpacity": 0.7,
                    "stroke": colors[0].replace("0.7", "1.0"),
                    "lineWidth": 1
                }
            
            if chart_type == "line":
                # 为线图添加样式
                g2_config["lineStyle"] = {
                    "stroke": colors[0].replace("0.7", "1.0"),
                    "lineWidth": 2
                }
                # 点的样式
                g2_config["point"] = {
                    "size": 5,
                    "shape": 'circle',
                    "style": {
                        "fill": colors[0],
                        "stroke": colors[0].replace("0.7", "1.0"),
                        "lineWidth": 1
                    }
                }
            
            # 提取数据
            if chart_data is not None:
                processed_data = []
                
                try:
                    # 修复数据结构问题
                    if hue_field:
                        # 处理多系列数据 - 使用更简洁的方式
                        processed_data = []
                        
                        # 获取所有唯一标签
                        all_labels = chart_data["labels"]
                        
                        # 对于堆叠图，我们需要更简单的数据结构
                        if is_stacked and chart_type in ["bar", "column"]:
                            # 直接将每个标签和数据集组合成一个数据点
                            for i, label in enumerate(all_labels):
                                for dataset_index, dataset in enumerate(chart_data["datasets"]):
                                    # 确保数据集有label和data
                                    if "label" in dataset and "data" in dataset and i < len(dataset["data"]):
                                        # 只添加有值的数据点
                                        if dataset["data"][i] > 0:
                                            color_index = dataset_index % len(colors)
                                            processed_data.append({
                                                x_field: label,
                                                y_field: dataset["data"][i],
                                                hue_field: dataset["label"],
                                                "color": colors[color_index]
                                            })
                        else:
                            # 对于分组图，每个标签和数据集组合成一个数据点
                            for dataset_index, dataset in enumerate(chart_data["datasets"]):
                                # 确保数据集有label和data
                                if "label" in dataset and "data" in dataset:
                                    color_index = dataset_index % len(colors)
                                    for i, label in enumerate(all_labels):
                                        if i < len(dataset["data"]):
                                            processed_data.append({
                                                x_field: label,
                                                y_field: dataset["data"][i],
                                                hue_field: dataset["label"],
                                                "color": colors[color_index]
                                            })
                    else:
                        # 单系列数据
                        processed_data = []
                        if chart_data["datasets"] and "data" in chart_data["datasets"][0]:
                            for i, label in enumerate(chart_data["labels"]):
                                # 确保索引在有效范围内
                                if i < len(chart_data["datasets"][0]["data"]):
                                    processed_data.append({
                                        x_field: label,
                                        y_field: chart_data["datasets"][0]["data"][i],
                                        "color": colors[0]  # 添加颜色信息
                                    })
                
                except Exception as e:
                    print(f"处理G2数据时出错: {str(e)}")
                    # 创建一个备用数据结构，确保不会崩溃
                    processed_data = [
                        {x_field: "数据1", y_field: 10, "color": colors[0]},
                        {x_field: "数据2", y_field: 20, "color": colors[1]}
                    ]
                
                g2_config["data"] = processed_data
        
        # 添加图例配置
        g2_config["legend"] = {
            "position": "right"
        }
        
        # 添加工具提示配置
        g2_config["tooltip"] = {
            "showMarkers": True,
            "showCrosshairs": chart_type == "line",
            "shared": True
        }
        
        # 添加交互配置
        g2_config["interactions"] = [
            {"type": "element-active"},
            {"type": "legend-active"},
            {"type": "legend-filter"}
        ]
        
        return g2_config


def extract_config_from_code(code: str) -> Dict[str, Any]:
    """
    从代码中提取图表配置的便捷函数
    
    参数:
        code: 可视化代码字符串
        
    返回:
        图表配置字典
    """
    extractor = ChartConfigExtractor()
    return extractor.extract_from_code(code)


def convert_to_chartjs_config(config: Dict[str, Any], df=None) -> Dict[str, Any]:
    """
    将配置转换为Chart.js格式的便捷函数
    
    参数:
        config: 图表配置
        df: 可选的DataFrame对象
        
    返回:
        Chart.js配置
    """
    extractor = ChartConfigExtractor()
    
    # 如果提供了DataFrame，先处理数据
    chart_data = None
    if df is not None:
        chart_data = extractor.resolve_chart_data(df, config)
    
    return extractor.convert_to_chartjs_config(config, chart_data)


def convert_to_antv_config(config: Dict[str, Any], df=None) -> Dict[str, Any]:
    """
    将配置转换为AntV G2格式的便捷函数
    
    参数:
        config: 图表配置
        df: 可选的DataFrame对象
        
    返回:
        AntV G2配置
    """
    extractor = ChartConfigExtractor()
    
    # 如果提供了DataFrame，先处理数据
    chart_data = None
    if df is not None:
        chart_data = extractor.resolve_chart_data(df, config)
    
    return extractor.convert_to_antv_config(config, chart_data)