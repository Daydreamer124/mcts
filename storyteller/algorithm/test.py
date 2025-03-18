import sys
import os,json

# 获取项目根目录路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(project_root)

# 现在可以导入 storyteller 模块了
from storyteller.algorithm.mcts_node import MCTSNode, Report
from storyteller.llm_call.openai_llm import call_openai
from storyteller.llm_call.prompt_factory import get_prompt
from storyteller.algorithm.mcts_action import QueryDataProcessorAction
#from storyteller.algorithm.ulits.DatasetContextGenerator import DatasetContextGenerator  # 确保 DatasetContextGenerator 存在
from storyteller.algorithm.mcts_node import ReportGenerationState

# ✅ 1️⃣ **创建一个模拟的数据集路径**
mock_dataset_path = "storyteller/dataset/shopping.csv"

# ✅ 2️⃣ **创建一个测试报告对象**
mock_report = Report(
    original_query="不同消费者的消费偏好有什么不同",
    dataset_path=mock_dataset_path,
    data_context="",
    clarified_query="",
    dataset_description="",
    task_list=[]
)

# ✅ 3️⃣ **创建 MCTSNode（蒙特卡洛搜索树节点）**
mock_node = MCTSNode(
    node_type=ReportGenerationState.EMPTY,  # 节点类型/状态
    parent_node=None,                      # 父节点
    parent_action=None,                    # 父动作
    depth=0,                               # 深度
    report=mock_report,                    # 报告对象
    original_query="不同消费者的消费偏好有什么不同"  # 原始查询
)

# ✅ 4️⃣ **初始化 QueryDataProcessorAction**
querydata_processor_action = QueryDataProcessorAction()

# ✅ 5️⃣ **定义 LLM 参数（模拟）**
llm_kwargs = {
    "model": "gpt-4o",
    "temperature": 0.7,
    "top_p": 1.0,
    "n": 3,  # 生成 3 个不同的 Query 解析方案
    "max_tokens": 512
}

# ✅ 6️⃣ **执行 create_children_nodes**
children_nodes = querydata_processor_action.create_children_nodes(mock_node, llm_kwargs)

# ✅ 7️⃣ **打印测试结果**
print("\n🔹【测试结果】🔹")
print(f"📌 原始 Query: {mock_report.original_query}")
print(f"📌 生成的数据集摘要: {mock_node.report.data_context}")
print(f"📌 生成的完整列名: {json.dumps(mock_node.report.full_column_names, indent=2, ensure_ascii=False)}")
print("\n📌 生成的 Query 解析结果:")
for idx, child in enumerate(children_nodes):
    print(f"  - 解析方案 {idx+1}: {child.report.clarified_query}")

# 测试代码
if __name__ == "__main__":
    # 使用已经创建和处理过的 mock_node
    print("成功创建MCTS节点:", mock_node)
    print("报告内容:", mock_node.report.to_dict())