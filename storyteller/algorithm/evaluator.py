import json
from storyteller.llm_call.openai_llm import call_openai
from storyteller.llm_call.prompt_factory import get_prompt
from typing import Dict, Any

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

def evaluate_report(
    dataset_context: str, 
    query: str, 
    html_report: str, 
    report_image: str = None,  # 添加图片参数
    llm_kwargs: Dict[str, Any] = None
) -> float:
    """
    评估数据可视化报告质量
    
    参数:
        dataset_context: 数据集上下文
        query: 用户查询
        html_report: 报告HTML内容
        report_image: 报告截图的base64编码（可选）
        llm_kwargs: LLM调用参数
    
    返回:
        float: 加权评分 (0-10分)
    """
    # 构建提示
    prompt_args = {
        "DATASET_CONTEXT": dataset_context,
        "QUERY": query,
        "REPORT": html_report,
        "REPORT_IMAGE": f"<image>{report_image}</image>" if report_image else ""
    }
    
    # 使用模板生成提示词
    prompt = get_prompt("report_evaluation", prompt_args)
    
    # 调用LLM进行评估
    try:
        responses = call_openai(prompt, **(llm_kwargs or {}))
        if not responses:
            print("❌ 没有收到有效响应")
            return 0.0
            
        response_text = responses[0].strip()
        
        # 处理可能的JSON格式
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "")
        response_text = response_text.strip()
        
        result = json.loads(response_text)
        
        # 计算加权分数
        weighted_score = (
            0.4 * result["representation"]["score"] +
            0.3 * result["presentation"]["score"] +
            0.2 * result["aesthetics"]["score"] +
            0.1 * result["narrative"]["score"]
        )
        
        print("\n📊 报告评估结果:")
        print(f"- 数据表达: {result['representation']['score']}/10")
        print(f"- 信息传递: {result['presentation']['score']}/10")
        print(f"- 设计美学: {result['aesthetics']['score']}/10")
        print(f"- 叙事结构: {result['narrative']['score']}/10")
        print(f"✨ 加权总分: {weighted_score:.2f}/10")
        
        return round(weighted_score, 2)
        
    except Exception as e:
        print(f"❌ 评估出错: {str(e)}")
        return 0.0 