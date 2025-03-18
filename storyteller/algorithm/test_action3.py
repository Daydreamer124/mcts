import sys
import os
import json
import re

# 获取项目根目录路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)

# 导入所需模块
from storyteller.algorithm.mcts_node import MCTSNode, Report, ReportGenerationState, Chapter
from storyteller.algorithm.mcts_action import ChapterVisTaskAction
from storyteller.llm_call.openai_llm import call_openai
from storyteller.llm_call.prompt_factory import get_prompt
import copy

# 创建一个测试报告对象
test_report = Report(
    original_query="不同消费者的消费偏好有什么不同",
    dataset_path="storyteller/dataset/shopping.csv",
    data_context="数据集包含3900条购物记录，涵盖18个字段。重要的类别列包括性别（2类）、商品类别（4类）、购买地点（50类）、商品尺码（4类）、商品颜色（25类）、购买季节（4类）、订阅状态（2类）、运输类型（6类）、支付方式（6类）和购买频率（7类）。重要的数值列如用户年龄范围为18到70岁，购买金额范围为20到100美元，用户评分范围为2.5到5.0，之前购买次数范围为1到50次。"
)

# 添加章节
test_report.add_chapter(Chapter(title="不同年龄段的消费者的消费偏好分析"))
test_report.add_chapter(Chapter(title="男性与女性消费者的消费行为对比"))
test_report.add_chapter(Chapter(title="消费者在商品类别选择上的偏好差异"))

# 创建一个测试节点
test_node = MCTSNode(
    node_type=ReportGenerationState.CHAPTER_DEFINED,
    parent_node=None,
    parent_action=None,
    depth=0,
    report=test_report,
    original_query=test_report.original_query
)

# 辅助函数：清理 JSON 响应
def clean_json_response(response):
    # 移除 Markdown 代码块标记
    response = re.sub(r'^```(?:json)?\s*', '', response)
    response = re.sub(r'\s*```$', '', response)
    return response.strip()

# 定义 LLM 参数
llm_kwargs = {
    "model": "gpt-4o",
    "temperature": 0.7,
    "top_p": 1.0,
    "n": 1,  # 生成 1 个可视化任务方案
    "max_tokens": 1024
}

# 测试修改后的 ChapterVisTaskAction
class ModifiedChapterVisTaskAction:
    def __init__(self):
        self.action_id = "A3"
        self.description = "确定每个章节的可视化任务"
        
    def create_children_nodes(self, node, llm_kwargs):
        """为所有章节生成可视化任务"""
        # 创建子节点
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = self
        child_node.depth = node.depth + 1
        
        # 准备章节列表
        chapters_json = json.dumps([{"title": chapter.title} for chapter in node.report.chapters], ensure_ascii=False)
        
        # 构建提示
        try:
            prompt = get_prompt("chapter_vistask", {
                "QUERY": node.report.original_query,
                "DATA_CONTEXT": node.report.data_context,
                "CHAPTERS": chapters_json
            })
            
            print("成功生成提示")
            print("提示内容:")
            print(prompt)
        except Exception as e:
            print(f"生成提示时出错: {e}")
            print(f"模板参数: {{'QUERY': '{node.report.original_query[:30]}...', 'DATA_CONTEXT': '{node.report.data_context[:30]}...', 'CHAPTERS': '{chapters_json}'}}")
            raise
        
        # 调用 LLM 生成可视化任务
        responses = call_openai(prompt, **llm_kwargs)
        
        # 处理响应
        if responses:
            try:
                # 清理响应
                cleaned_response = clean_json_response(responses[0])
                
                print("清理后的响应：")
                print(cleaned_response)
                
                # 解析 JSON
                task_data = json.loads(cleaned_response)
                
                # 处理所有章节的可视化任务
                if "chapters" in task_data:
                    chapters_data = task_data["chapters"]
                    
                    # 遍历每个章节的数据
                    for chapter_data in chapters_data:
                        chapter_title = chapter_data.get("title", "")
                        chapter_tasks = chapter_data.get("tasks", [])
                        
                        # 查找对应的章节
                        for chapter_idx, chapter in enumerate(child_node.report.chapters):
                            if chapter.title == chapter_title:
                                # 设置当前章节的可视化任务
                                setattr(child_node.report.chapters[chapter_idx], "visualization_tasks", chapter_tasks)
                                
                                # 将任务添加到报告的任务列表中
                                child_node.report.task_list.extend(chapter_tasks)
                                break
                
            except json.JSONDecodeError as e:
                print(f"无法解析 JSON 响应: {responses[0]}")
                print(f"错误详情: {e}")
                print(f"原始响应: {responses[0]}")
            except Exception as e:
                print(f"处理可视化任务响应时出错: {e}")
                print(f"原始响应: {responses[0]}")
        
        return [child_node]

# 初始化修改后的 ChapterVisTaskAction
modified_action = ModifiedChapterVisTaskAction()

# 执行 create_children_nodes
print("开始为所有章节生成可视化任务...")
vis_task_nodes = modified_action.create_children_nodes(test_node, llm_kwargs)
print(f"生成了 {len(vis_task_nodes)} 个可视化任务方案")

# 打印结果
if vis_task_nodes:
    result_node = vis_task_nodes[0]
    print("\n🔹【可视化任务结果】🔹")
    
    # 打印报告的任务列表
    print(f"\n📌 报告任务列表:")
    for task_idx, task in enumerate(result_node.report.task_list):
        print(f"  任务 {task_idx+1}: {task}")
    
    # 打印每个章节的可视化任务
    print(f"\n📌 各章节可视化任务:")
    for chapter_idx, chapter in enumerate(result_node.report.chapters):
        print(f"\n  章节 {chapter_idx+1}: {chapter.title}")
        
        if hasattr(chapter, 'visualization_tasks'):
            print(f"    可视化任务:")
            for task_idx, task in enumerate(chapter.visualization_tasks):
                print(f"      任务 {task_idx+1}: {task['description'] if 'description' in task else task['task_name']}")
                print(f"        可视化类型: {task['chart_type'] if 'chart_type' in task else '未指定'}")
                print(f"        数据字段: {', '.join(task['relevant_columns']) if 'relevant_columns' in task else '未指定'}")
                if 'insight_goal' in task:
                    print(f"        洞察目标: {task['insight_goal']}")
        else:
            print("    没有可视化任务")
else:
    print("无法生成可视化任务方案")

print("\n🎉 测试完成!") 