import sys
import os
import json

# 获取项目根目录路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)

# 导入所需模块
from storyteller.algorithm.mcts_node import MCTSNode, Report, ReportGenerationState, Chapter
from storyteller.algorithm.mcts_action import ChapterDivisionAction
from storyteller.llm_call.openai_llm import call_openai

# 创建一个测试报告对象 - 不设置 clarified_query，使用原始查询
test_report = Report(
    original_query="不同消费者的消费偏好有什么不同",
    dataset_path="storyteller/dataset/shopping.csv",
    data_context="数据集包含3900条购物记录，涵盖18个字段。重要的类别列包括性别（2类）、商品类别（4类）、购买地点（50类）、商品尺码（4类）、商品颜色（25类）、购买季节（4类）、订阅状态（2类）、运输类型（6类）、支付方式（6类）和购买频率（7类）。重要的数值列如用户年龄范围为18到70岁，购买金额范围为20到100美元，用户评分范围为2.5到5.0，之前购买次数范围为1到50次。",
    clarified_query=""  # 不设置澄清后的查询
)

# 创建一个测试节点
test_node = MCTSNode(
    node_type=ReportGenerationState.CHAPTER_DEFINED,
    parent_node=None,
    parent_action=None,
    depth=0,
    report=test_report,
    original_query=test_report.original_query
)

# 初始化 ChapterDivisionAction
chapter_division_action = ChapterDivisionAction()

# 定义 LLM 参数
llm_kwargs = {
    "model": "gpt-4o",
    "temperature": 0.7,
    "top_p": 1.0,
    "n": 2,  # 生成 2 个不同的章节划分方案
    "max_tokens": 1024
}

# 执行 create_children_nodes
print("开始生成章节划分方案...")
chapter_nodes = chapter_division_action.create_children_nodes(test_node, llm_kwargs)
print(f"生成了 {len(chapter_nodes)} 个章节划分方案")

# 打印结果
print("\n🔹【章节划分结果】🔹")
for idx, chapter_node in enumerate(chapter_nodes):
    print(f"\n📌 章节划分方案 {idx+1}:")
    for chapter_idx, chapter in enumerate(chapter_node.report.chapters):
        print(f"  - 章节 {chapter_idx+1}: {chapter.title}")
        if hasattr(chapter, 'summary') and chapter.summary:
            print(f"    摘要: {chapter.summary}")

# 测试进一步扩展
if chapter_nodes:
    print("\n🔹【测试进一步扩展】🔹")
    # 选择第一个章节划分方案
    selected_node = chapter_nodes[0]
    print(f"选择章节划分方案 1 进行进一步扩展")
    print(f"该方案包含 {len(selected_node.report.chapters)} 个章节:")
    for idx, chapter in enumerate(selected_node.report.chapters):
        print(f"  - 章节 {idx+1}: {chapter.title}")
    
    # 这里可以添加下一步动作的测试，例如 ChapterVisTaskAction
    print("\n下一步可以对每个章节应用 ChapterVisTaskAction 生成可视化任务") 