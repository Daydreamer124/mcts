import pandas as pd
import numpy as np
import json
import re
import openai
import os
from typing import Dict, Union, List, Optional
from openai import OpenAI


class DatasetContextGenerator:
    """数据集上下文信息生成器"""
    
    def __init__(self, api_key: str, base_url: str = None):
        """
        初始化数据集上下文生成器
        参数：
        - api_key (str): OpenAI API Key
        - base_url (str, optional): OpenAI API 基础 URL
        """
        self.api_key = api_key
        self.base_url = base_url
        openai.api_key = api_key  # 设置 OpenAI API Key
        if base_url:
            openai.api_base = base_url  # 设置 OpenAI API 基础 URL

    def generate_context(
            self,
            data: Union[pd.DataFrame, str],
            dataset_name: str = "",
            dataset_description: str = "",
            n_samples: int = 5
        ) -> Dict:
        """
        生成 JSON 格式的数据集上下文信息
        
        参数：
        - data (pd.DataFrame | str): 数据集或 CSV 文件路径
        - dataset_name (str): 数据集名称
        - dataset_description (str): **用户提供的数据集描述，默认为空**
        - n_samples (int): 生成列全名时参考的样本行数
        
        返回：
        - Dict: JSON 结构化数据集信息
        """
        if isinstance(data, str):
            dataset_name = dataset_name or data.split("/")[-1]
            try:
                # 首先尝试 UTF-8 编码
                data = pd.read_csv(data)
            except UnicodeDecodeError:
                # 如果 UTF-8 失败，尝试 latin1 编码
                print(f"UTF-8 编码失败，尝试使用 latin1 编码读取文件: {data}")
                data = pd.read_csv(data, encoding='latin1')
            
            # 打印实际行数和列数
            print(f"数据集 {dataset_name} 实际行数: {len(data)}, 列数: {len(data.columns)}")
            print(f"数据集列名: {data.columns.tolist()}")
            
            # 检查是否有重复行
            duplicates = data.duplicated().sum()
            if duplicates > 0:
                print(f"数据集包含 {duplicates} 行重复数据")
                
                # 可选：删除重复行
                # data = data.drop_duplicates()
                # print(f"删除重复行后，数据集行数: {len(data)}")

        total_rows, total_columns = data.shape
        column_names = data.columns.tolist()
        sample_data = data.head(n_samples).to_dict(orient="records")

        # **1️⃣ 计算类别列 & 数值列**
        data_types, categorical_columns, category_distribution, numerical_columns = self._analyze_columns(data)

        # **2️⃣ 一次 LLM 调用生成【完整列名】+【数据集摘要】+【英文列名映射】**
        llm_result = self._generate_column_names_and_summary_with_english_mapping(
            dataset_name, total_rows, total_columns, column_names, sample_data, data_types, categorical_columns, numerical_columns
        )

        full_column_names = llm_result.get("full_column_names", {col: col for col in column_names})
        dataset_summary = llm_result.get("dataset_summary", "暂无摘要信息")
        english_column_mapping = llm_result.get("english_column_mapping", {})

        # 字段语义类型映射
        field_semantic_types = self._generate_field_semantic_types(data, categorical_columns, numerical_columns)

        # **3️⃣ 组织 JSON 结构**
        dataset_context = {
            "name": dataset_name,
            "dataset_description": dataset_description or dataset_summary,  # 用户提供或LLM生成
            "total_rows": total_rows,
            "total_columns": total_columns,
            "fields_info": {
                col: {
                    "dtype": data_types.get(col, "unknown"),
                    "num_unique_values": categorical_columns.get(col, 0) if col in categorical_columns else (0 if col not in numerical_columns else None),
                    "missing_values": int(data[col].isna().sum()),
                    "semantic_type": field_semantic_types.get(col, "UNKNOWN"),
                    "english_name": english_column_mapping.get(col, col)  # 使用LLM生成的英文列名
                }
                for col in column_names
            },
            "categorical_details": {
                col: {
                    "unique_values": {str(k): int(v*data.shape[0]) for k, v in category_distribution.get(col, {}).items()},
                    "total_categories": categorical_columns.get(col, 0)
                }
                for col in categorical_columns
            },
            "numerical_details": {
                col: numerical_columns[col]
                for col in numerical_columns
            },
            "english_column_mapping": english_column_mapping  # 添加整体的英文列名映射
        }

        return dataset_context
    
    def _generate_column_names_and_summary_with_english_mapping(
            self,
            dataset_name: str,
            total_rows: int,
            total_columns: int,
            column_names: List[str],
            sample_data: List[Dict],
            data_types: Dict[str, str],
            categorical_columns: Dict[str, int],
            numerical_columns: Dict[str, Dict[str, float]]
        ) -> Dict:
        """**一次性调用 LLM 生成完整列名 + 数据集摘要 + 英文列名映射**"""
        prompt = f"""
        数据集名称：{dataset_name}
        该数据集包含 {total_rows} 行，{total_columns} 列。
        
        **原始列名**：
        {json.dumps(column_names, indent=2, ensure_ascii=False)}

        **前 5 行数据样本**：
        {json.dumps(sample_data, indent=2, ensure_ascii=False)}

        **各列的数据类型**：
        {json.dumps(data_types, indent=2, ensure_ascii=False)}

        **类别列及类别数**：
        {json.dumps(categorical_columns, indent=2, ensure_ascii=False)}

        **数值列的统计信息**：
        {json.dumps(numerical_columns, indent=2, ensure_ascii=False)}

        **请完成以下任务**：
        1️⃣ **为每一列生成完整列名**，如：
        - "age" → "用户年龄（years）"
        - "revenue" → "订单收入（USD）"

        2️⃣ **生成数据集摘要**，需描述：
        - 数据集的主要内容
        - 重要的类别列及其类别数量
        - 重要的数值列的取值范围

        3️⃣ **为所有中文列名创建准确的英文映射**，这对于数据可视化非常重要。必须为每个列名生成对应的英文名称，确保映射合理且与数据内容相符。例如：
        - "年龄" → "Age"
        - "性别" → "Gender"
        - "收入" → "Income"
        - "区域" → "Region"
        - "省份" → "Province"
        - "市" → "City" 

        **请直接返回 JSON 格式**：
        ```json
        {{
            "full_column_names": {{
                "age": "用户年龄（years）",
                "revenue": "订单收入（USD）"
            }},
            "dataset_summary": "数据集包含某某信息...",
            "english_column_mapping": {{
                "年龄": "Age",
                "性别": "Gender",
                "区域": "Region",
                "省份": "Province",
                "市": "City"
            }}
        }}
        ```
        """

        response = self._call_openai_api(prompt)
        default = {
            "full_column_names": {col: col for col in column_names}, 
            "dataset_summary": "暂无摘要信息",
            "english_column_mapping": {}
        }
        return self._parse_json(response, default=default)

    def _generate_field_semantic_types(self, data: pd.DataFrame, categorical_columns: Dict, numerical_columns: Dict) -> Dict:
        """为每个字段生成语义类型"""
        semantic_types = {}
        
        for col in data.columns:
            if col in categorical_columns:
                # 特殊类型检测
                if col.lower() in ['id', 'code', 'no', 'number', '编号', '代码', '序号'] or 'id' in col.lower():
                    semantic_types[col] = "ID"
                elif col.lower() in ['date', 'time', 'datetime', 'timestamp', '日期', '时间'] or '日期' in col.lower() or '时间' in col.lower():
                    semantic_types[col] = "DATETIME"
                else:
                    semantic_types[col] = "CATEGORY"
            elif col in numerical_columns:
                # ID检测
                if col.lower() in ['id', 'code', 'no', 'number', '编号', '代码', '序号'] or 'id' in col.lower():
                    semantic_types[col] = "ID"
                else:
                    semantic_types[col] = "NUMERIC"
            else:
                semantic_types[col] = "UNKNOWN"
                
        return semantic_types

    def _call_openai_api(self, prompt: str) -> str:
        """调用 OpenAI API（兼容新版 API）"""
        try:
            # 尝试使用新版 API
            from openai import OpenAI
            client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url if self.base_url else "https://api.chsdw.top/v1"  # 添加 /v1
            )
            
            try:
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "你是一个数据分析专家，负责生成数据集的描述性总结。"},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0,
                    max_tokens=8000
                )
                
                # 处理响应
                if isinstance(response, str):
                    return response.strip()
                elif hasattr(response, 'choices'):
                    return response.choices[0].message.content.strip()
                elif isinstance(response, dict):
                    return response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                else:
                    print(f"未知的响应类型: {type(response)}")
                    print(f"响应内容: {response}")
                    return str(response)
                
            except Exception as api_error:
                print(f"API 调用错误: {str(api_error)}")
                if hasattr(api_error, 'response'):
                    print(f"响应状态码: {api_error.response.status_code}")
                    print(f"响应内容: {api_error.response.text}")
                raise
            
        except Exception as e:
            print(f"API 调用完全失败: {str(e)}")
            raise

    def _parse_json(self, text: str, default: dict) -> dict:
        """解析 LLM 生成的 JSON，确保格式正确"""
        try:
            json_match = re.search(r"```json\n(.*)\n```", text, re.DOTALL)
            json_text = json_match.group(1) if json_match else text
            parsed_json = json.loads(json_text)
            return parsed_json if isinstance(parsed_json, dict) else default
        except Exception:
            return default

    def _analyze_columns(self, data: pd.DataFrame):
        """分析数据列类型、类别列统计、数值列统计"""
        data_types = {}
        categorical_columns = {}
        category_distribution = {}
        numerical_columns = {}

        for col in data.columns:
            dtype = str(data[col].dtype)
            data_types[col] = dtype  # 记录数据类型

            if self._is_categorical(data[col]):
                unique_values_count = data[col].nunique()
                categorical_columns[col] = unique_values_count
                category_distribution[col] = data[col].value_counts(normalize=True).head(5).to_dict()  # 前 5 类占比
            
            elif np.issubdtype(data[col].dtype, np.number):
                numerical_columns[col] = {
                    "min": float(data[col].min()),
                    "max": float(data[col].max()),
                    "mean": float(data[col].mean()),
                    "std": float(data[col].std()),
                    "quartiles": {
                        "25%": float(data[col].quantile(0.25)),
                        "50%": float(data[col].quantile(0.50)),
                        "75%": float(data[col].quantile(0.75))
                    }
                }
        
        return data_types, categorical_columns, category_distribution, numerical_columns

    def _is_categorical(self, series):
        """判断一个列是否为类别型"""
        # 如果是对象类型（通常是字符串）
        if series.dtype == 'object':
            return True
        
        # 如果是数值类型，但唯一值较少（比如小于列长度的10%）
        if np.issubdtype(series.dtype, np.number):
            unique_count = series.nunique()
            return unique_count < len(series) * 0.1 and unique_count < 20
        
        return False