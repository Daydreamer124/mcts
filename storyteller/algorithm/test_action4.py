import sys
import os
import json

# 获取项目根目录路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)

# 导入所需模块
from storyteller.algorithm.mcts_node import MCTSNode, Report, ReportGenerationState, Chapter
from storyteller.algorithm.mcts_action import ChapterVisTaskAction, SelectNextVisualizationTaskAction
from storyteller.llm_call.openai_llm import call_openai
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

# 为章节添加可视化任务
test_report.chapters[0].visualization_tasks = [
    {
        "task_id": "task_1_1",
        "task_name": "Characterize Distribution",
        "description": "展示不同年龄段消费者的分布情况",
        "chart_type": ["Bar Chart", "Point Chart"],
        "relevant_columns": ["Age", "Total_Spending"]
    },
    {
        "task_id": "task_1_2",
        "task_name": "Comparison",
        "description": "比较不同年龄段消费者的平均消费金额",
        "chart_type": ["Bar Chart", "Line Chart"],
        "relevant_columns": ["Age", "Average_Spending"]
    }
]

test_report.chapters[1].visualization_tasks = [
    {
        "task_id": "task_2_1",
        "task_name": "Comparison",
        "description": "对比男性与女性消费者的平均购物金额",
        "chart_type": ["Bar Chart", "Line Chart"],
        "relevant_columns": ["Gender", "Total_Spending"]
    },
    {
        "task_id": "task_2_2",
        "task_name": "Find Extremum",
        "description": "找到最高和最低消费的性别群体",
        "chart_type": ["Point Chart", "Bar Chart"],
        "relevant_columns": ["Gender", "Max_Spending", "Min_Spending"]
    }
]

test_report.chapters[2].visualization_tasks = [
    {
        "task_id": "task_3_1",
        "task_name": "Part to Whole",
        "description": "展示不同商品类别的消费占比",
        "chart_type": ["Arc Chart"],
        "relevant_columns": ["Product_Category", "Total_Spending"]
    },
    {
        "task_id": "task_3_2",
        "task_name": "Correlate",
        "description": "分析商品类别与消费者年龄的关系",
        "chart_type": ["Bar Chart", "Line Chart"],
        "relevant_columns": ["Product_Category", "Age", "Total_Spending"]
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

# 初始化 SelectNextVisualizationTaskAction
select_next_task_action = SelectNextVisualizationTaskAction()

# 定义 LLM 参数
llm_kwargs = {
    "model": "gpt-4o",
    "temperature": 0.7,
    "top_p": 1.0,
    "n": 1,
    "max_tokens": 1024
}

# 测试选择任务
print("开始测试选择可视化任务...")

# 初始化所有章节的任务状态
for chapter in test_node.report.chapters:
    chapter.initialize_tasks_status()

# 模拟多次选择任务的过程
current_node = test_node
for i in range(6):  # 我们有6个任务
    print(f"\n第 {i+1} 次选择任务:")
    
    # 选择下一个任务
    next_task_nodes = select_next_task_action.create_children_nodes(current_node, llm_kwargs)
    
    if not next_task_nodes:
        print("  没有更多待处理的任务")
        break
    
    # 获取选择的任务
    selected_node = next_task_nodes[0]
    selected_task = selected_node.selected_task
    
    print(f"  选择了章节: {selected_task['chapter_title']}")
    print(f"  任务ID: {selected_task['task_id']}")
    print(f"  任务名称: {selected_task['task_name']}")
    print(f"  任务描述: {selected_task['description']}")
    print(f"  图表类型: {', '.join(selected_task['chart_type'])}")
    print(f"  相关列: {', '.join(selected_task['relevant_columns'])}")
    
    # 模拟任务完成
    chapter_idx = selected_task['chapter_idx']
    task_id = selected_task['task_id']
    selected_node.report.chapters[chapter_idx].mark_task_completed(task_id)
    
    # 更新当前节点
    current_node = selected_node

# 检查所有任务是否都已完成
all_completed = True
for chapter in current_node.report.chapters:
    if not chapter.all_tasks_completed():
        all_completed = False
        break

print(f"\n所有任务是否都已完成: {'是' if all_completed else '否'}")

print("\n🎉 测试完成!") 