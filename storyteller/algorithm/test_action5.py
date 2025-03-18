import sys
import os
import json
import pandas as pd

# 获取项目根目录路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)

# 导入所需模块
from storyteller.algorithm.mcts_node import MCTSNode, Report, ReportGenerationState, Chapter, Chart
from storyteller.algorithm.mcts_action import SelectNextVisualizationTaskAction, GenerateVisualizationAction
import copy

# 创建一个测试报告对象
test_report = Report(
    original_query="不同消费者的消费偏好有什么不同",
    dataset_path="/Users/zhangzhiyang/Storytelling/storyteller/dataset/shopping.csv",
    data_context="数据集包含3900条购物记录，涵盖18个字段。重要的类别列包括性别（2类）、商品类别（4类）、购买地点（50类）、商品尺码（4类）、商品颜色（25类）、购买季节（4类）、订阅状态（2类）、运输类型（6类）、支付方式（6类）和购买频率（7类）。重要的数值列如用户年龄范围为18到70岁，购买金额范围为20到100美元，用户评分范围为2.5到5.0，之前购买次数范围为1到50次。"
)

# 添加章节
test_report.add_chapter(Chapter(title="不同年龄段的消费者的消费偏好分析"))
test_report.add_chapter(Chapter(title="男性与女性消费者的消费行为对比"))

# 为章节添加可视化任务
test_report.chapters[0].visualization_tasks = [
    {
        "task_id": "task_1_1",
        "task_name": "Characterize Distribution",
        "description": "展示不同年龄段消费者的分布情况",
        "chart_type": ["Bar Chart"],
        "relevant_columns": ["Age", "Total_Spending"]
    }
]

test_report.chapters[1].visualization_tasks = [
    {
        "task_id": "task_2_1",
        "task_name": "Comparison",
        "description": "对比男性与女性消费者的平均购物金额",
        "chart_type": ["Bar Chart"],
        "relevant_columns": ["Gender", "Total_Spending"]
    }
]

# 创建一个测试节点
test_node = MCTSNode(
    node_type=ReportGenerationState.CHAPTER_DEFINED,
    parent_node=None,
    parent_action=None,
    depth=0,
    report=test_report,
    original_query=test_report.original_query
)

# 初始化 Action
select_next_task_action = SelectNextVisualizationTaskAction()
generate_visualization_action = GenerateVisualizationAction()

# 定义 LLM 参数
llm_kwargs = {
    "model": "gpt-4o",
    "temperature": 0.7,
    "top_p": 1.0,
    "n": 1,
    "max_tokens": 1024
}

# 测试生成可视化图表
print("开始测试生成可视化图表...")

# 初始化所有章节的任务状态
for chapter in test_node.report.chapters:
    chapter.initialize_tasks_status()

# 选择第一个任务
print("\n选择第一个任务:")
next_task_nodes = select_next_task_action.create_children_nodes(test_node, llm_kwargs)

if next_task_nodes:
    selected_node = next_task_nodes[0]
    selected_task = selected_node.selected_task
    
    print(f"  选择了章节: {selected_task['chapter_title']}")
    print(f"  任务ID: {selected_task['task_id']}")
    print(f"  任务描述: {selected_task['description']}")
    
    # 生成可视化图表
    print("\n生成可视化图表:")
    visualization_nodes = generate_visualization_action.create_children_nodes(selected_node, llm_kwargs)
    
    if visualization_nodes:
        result_node = visualization_nodes[0]
        chapter_idx = selected_task['chapter_idx']
        chapter = result_node.report.chapters[chapter_idx]
        
        # 检查是否生成了图表
        if chapter.charts:
            print(f"  成功生成图表: {len(chapter.charts)} 个")
            for i, chart in enumerate(chapter.charts):
                print(f"    图表 {i+1}:")
                print(f"      URL: {chart.url}")
                print(f"      说明: {chart.caption}")
                print(f"      位置: {chart.chart_position}")
                print(f"      类型: {chart.type}")
        else:
            print("  没有生成图表")
        
        # 检查任务状态
        task_id = selected_task['task_id']
        if task_id in chapter.tasks_status:
            status = chapter.tasks_status[task_id]["status"]
            print(f"  任务状态: {status}")
        else:
            print("  找不到任务状态")
    else:
        print("  生成可视化图表失败")
else:
    print("  没有待处理的任务")

print("\n🎉 测试完成!") 