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
DEFAULT_COST_RECORDER = CostRecorder(model="gpt-4o")

# API 调用相关参数
MAX_RETRY_TIMES = 5  # 最大重试次数
N_CALLING_STRATEGY_SINGLE = "single"  # 一次性调用 `n` 结果
N_CALLING_STRATEGY_MULTIPLE = "multiple"  # `n` 轮独立调用

def call_openai(
    prompt: str,
    model: str = "gpt-4o",
    temperature: float = 0.0,
    top_p: float = 1.0,
    n: int = 1,
    max_tokens: int = 512,
    stop: List[str] = None,
    base_url: str = None,
    api_key: str = None,
    n_strategy: str = N_CALLING_STRATEGY_SINGLE,
    cost_recorder: Optional[CostRecorder] = DEFAULT_COST_RECORDER
) -> List[str]:
    """
    调用 OpenAI GPT-4 / GPT-3.5 Turbo 进行文本生成
    
    参数:
    - prompt (str): 要输入的提示词
    - model (str): 选择的 OpenAI 模型 (默认 `gpt-4o`)
    - temperature (float): 生成的随机性 (0.0 ~ 1.0, 越高结果越随机)
    - top_p (float): 样本截取概率 (默认 1.0)
    - n (int): 生成 `n` 个结果
    - max_tokens (int): 最大输出 token 数
    - stop (List[str]): 停止字符
    - base_url (str): 自定义 API 地址 (如 `Azure OpenAI`)
    - api_key (str): 自定义 API Key (默认使用环境变量)
    - n_strategy (str): 选择 `single`(一次性请求 `n` 结果) 或 `multiple`(`n` 轮单独调用)
    - cost_recorder (CostRecorder): 成本记录器 (可选)

    返回:
    - List[str]: GPT 生成的多个响应 (长度 `n`)
    """
    if api_key is None:
        api_key = os.getenv("OPENAI_API_KEY")  # 读取环境变量 API Key
    if api_key is None:
        raise ValueError("OpenAI API Key 未提供！请设置 `api_key` 或 `.env` 配置")

    openai.api_key = api_key
    client = openai.OpenAI()

    if base_url is not None:
        client.base_url = base_url

    retry_count = 0
    contents = []

    while retry_count < MAX_RETRY_TIMES:
        try:
            if n == 1 or (n > 1 and n_strategy == N_CALLING_STRATEGY_SINGLE):
                # **单次请求，返回 `n` 个结果**
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                    n=n,
                    top_p=top_p,
                    stop=stop,
                )

                # 记录成本
                if cost_recorder is not None:
                    cost_recorder.update_cost(response.usage.prompt_tokens, response.usage.completion_tokens)

                contents = [choice.message.content.strip() for choice in response.choices]
                break  # 成功后退出循环

            elif n > 1 and n_strategy == N_CALLING_STRATEGY_MULTIPLE:
                # **多轮 `n` 次独立调用**
                contents = []
                for _ in range(n):
                    response = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temperature,
                        max_tokens=max_tokens,
                        n=1,
                        top_p=top_p,
                        stop=stop,
                    )

                    if cost_recorder is not None:
                        cost_recorder.update_cost(response.usage.prompt_tokens, response.usage.completion_tokens)

                    contents.append(response.choices[0].message.content.strip())
                break

            else:
                raise ValueError(f"Invalid n_strategy: {n_strategy} for n: {n}")

        except Exception as e:
            logger.warning(f"⚠️ OpenAI API 调用失败: {e}，重试 {retry_count + 1}/{MAX_RETRY_TIMES} 次")
            retry_count += 1
            if retry_count == MAX_RETRY_TIMES:
                raise e
            time.sleep(10)  # 休眠 10 秒再试

    return contents