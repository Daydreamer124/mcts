import openai
import time
import os
from typing import List, Optional
from storyteller.llm_call.cost_recorder import CostRecorder
from loguru import logger

# 读取 .env 环境变量
from dotenv import load_dotenv
load_dotenv(override=True)

# 默认成本统计对象
DEFAULT_COST_RECORDER = CostRecorder(model="gpt-4o-mini")

# API 调用相关参数
MAX_RETRY_TIMES = 5  # 最大重试次数
N_CALLING_STRATEGY_SINGLE = "single"  # 一次性调用 `n` 结果
N_CALLING_STRATEGY_MULTIPLE = "multiple"  # `n` 轮独立调用

def call_openai(
    prompt: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
    top_p: float = 1.0,
    n: int = 1,
    max_tokens: int = 1024,
    stop: List[str] = None,
    base_url: str = None,
    api_key: str = None,
    n_strategy: str = N_CALLING_STRATEGY_SINGLE,
    cost_recorder: Optional[CostRecorder] = DEFAULT_COST_RECORDER
) -> List[str]:
    """调用 OpenAI API"""
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY")
    if api_key is None:
        raise ValueError("OpenAI API Key 未提供！")

    # 确保 base_url 以 /v1 结尾
    if base_url and not base_url.endswith('/v1'):
        base_url = f"{base_url}/v1"

    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url if base_url else "https://api.openai.com/v1"
    )

    retry_count = 0
    last_error = None

    while retry_count < MAX_RETRY_TIMES:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                n=n,
                top_p=top_p,
                stop=stop,
            )
            
            # 处理响应
            if isinstance(response, str):
                return [response.strip()]
            elif hasattr(response, 'choices'):
                return [choice.message.content.strip() for choice in response.choices]
            elif isinstance(response, dict):
                return [response.get("choices", [{}])[0].get("message", {}).get("content", "").strip()]
            else:
                raise ValueError(f"未知的响应类型: {type(response)}")
                
        except Exception as e:
            last_error = e
            print(f"⚠️ API 调用失败 ({retry_count + 1}/{MAX_RETRY_TIMES}): {str(e)}")
            if hasattr(e, 'response'):
                print(f"响应状态码: {e.response.status_code}")
                print(f"响应内容: {e.response.text}")
            retry_count += 1
            if retry_count < MAX_RETRY_TIMES:
                time.sleep(10)
            else:
                raise last_error

    raise last_error