import copy
import json
import re,os
from typing import Dict, List, Any, Optional
from storyteller.algorithm.ulits.DatasetContextGenerator import DatasetContextGenerator  # 引入数据集解析器
from storyteller.algorithm.mcts_node import *
from storyteller.llm_call.openai_llm import call_openai
from storyteller.llm_call.prompt_factory import get_prompt
from typing import List, Dict, Any
from copy import deepcopy
import pandas as pd


import copy
import json
from typing import Dict, Any, List
from storyteller.llm_call.prompt_factory import get_prompt
from storyteller.llm_call.openai_llm import call_openai
from storyteller.algorithm.mcts_node import *


class DataStorytellingAction:
    def __init__(self, action_id: str, description: str, applicable_states: List[ReportGenerationState]):
        self.action_id = action_id
        self.description = description
        self.applicable_states = applicable_states

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        raise NotImplementedError


class QueryDataProcessorAction(DataStorytellingAction):
    def __init__(self):
        super().__init__("A1", "Query and Data Processor", [ReportGenerationState.EMPTY])
        self.dataset_generator = DatasetContextGenerator(api_key=os.getenv("OPENAI_API_KEY"))

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """解析 Query ，并处理数据集（仅提供上下文信息）"""
        nodes = []

        # 1️⃣ **调用 DatasetContextGenerator 解析数据集**
        dataset_info = self.dataset_generator.generate_context(node.report.dataset_path, dataset_description=node.report.dataset_description)

        # 2️⃣ **更新 MCTS 报告对象**
        node.report.data_context = dataset_info["dataset_summary"]  # 生成的数据集摘要
        node.report.full_column_names = dataset_info["full_column_names"]  # LLM 生成的完整列名

        # 3️⃣ **生成 LLM 提示（用于 Query 处理）**
        query_prompt = get_prompt("query_processor", {"QUERY": node.report.original_query})
        query_responses = call_openai(query_prompt, **llm_kwargs)

        # 4️⃣ **遍历 LLM 响应，为每个 Query 解析结果创建子节点**
        for query_response in query_responses:
            child_node = copy.deepcopy(node)
            child_node.node_type = ReportGenerationState.CHAPTER_DEFINED  
            child_node.parent_node = node
            child_node.parent_action = self
            child_node.depth = node.depth + 1
            child_node.report.clarified_query = query_response.strip()
            child_node.Q = 0  # 先设为 0，延迟评估
            nodes.append(child_node)
        return nodes
    

class ChapterDivisionAction(DataStorytellingAction):
    def __init__(self):
        super().__init__("A2", "定义报告的章节划分", [ReportGenerationState.CHAPTER_DEFINED])

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """
        根据用户查询和数据上下文，将查询按不同维度分解成章节形式
        
        例如：
        - 原始查询："不同消费者的消费偏好有什么不同？"
        - 可能的章节划分：
          1. 不同年龄段的消费者的消费偏好有什么不同？
          2. 不同性别的消费者的消费偏好有什么不同？
          3. 会员和非会员消费者消费偏好有什么不同？
          
        或者按消费偏好维度划分：
          1. 消费金额有什么不同？
          2. 消费的物品类别有什么不同？
          3. 消费频率有什么不同？
        """
        # 使用 clarified_query（如果有）或原始查询
        query = node.report.clarified_query if node.report.clarified_query else node.report.original_query
        
        # 构建提示，包含查询和数据上下文
        prompt = get_prompt("chapter_division", {
            "QUERY": query,
            "DATA_CONTEXT": node.report.data_context
        })
        
        # 调用 LLM 生成章节划分方案
        responses = call_openai(prompt, **llm_kwargs)
        nodes = []
        
        # 处理每个响应，创建子节点
        for response in responses:
            try:
                # 清理响应，移除 Markdown 代码块标记
                cleaned_response = self._clean_json_response(response)
                
                print(f"原始响应: {response}")
                print(f"清理后的响应: {cleaned_response}")
                
                # 解析 JSON 响应
                chapter_data = json.loads(cleaned_response)
                
                # 创建子节点
                child_node = copy.deepcopy(node)
                child_node.parent_node = node
                child_node.parent_action = self
                child_node.depth = node.depth + 1
                
                # 清空现有章节（如果有）
                child_node.report.chapters = []
                
                # 添加章节
                if "chapters" in chapter_data:
                    # 新格式：包含章节标题和描述
                    for chapter_info in chapter_data["chapters"]:
                        title = chapter_info["title"]
                        summary = chapter_info.get("summary", "")
                        child_node.report.add_chapter(Chapter(title=title, summary=summary))
                elif "chapter_titles" in chapter_data:
                    # 旧格式：只有章节标题
                    for title in chapter_data["chapter_titles"]:
                        child_node.report.add_chapter(Chapter(title=title))
                
                # 添加到节点列表
                nodes.append(child_node)
                
            except json.JSONDecodeError as e:
                print(f"无法解析 JSON 响应: {response}")
                print(f"错误详情: {e}")
                continue
            except Exception as e:
                print(f"处理章节划分响应时出错: {e}")
                continue
        
        return nodes

    def _clean_json_response(self, response: str) -> str:
        """
        清理 LLM 返回的 JSON 响应，移除 Markdown 代码块标记
        
        参数:
            response: LLM 返回的原始响应
            
        返回:
            清理后的 JSON 字符串
        """
        # 移除 Markdown 代码块开始标记（```json 或 ```）
        response = re.sub(r'^```(?:json)?\s*', '', response)
        
        # 移除 Markdown 代码块结束标记（```）
        response = re.sub(r'\s*```$', '', response)
        
        # 移除可能的前导和尾随空白字符
        response = response.strip()
        
        return response


class ChapterVisTaskAction(DataStorytellingAction):
    def __init__(self):
        super().__init__("A3", "确定每个章节的可视化任务", [ReportGenerationState.CHAPTER_DEFINED])

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """为所有章节生成可视化任务"""
        # 创建子节点
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = self
        child_node.depth = node.depth + 1
        
        # 准备章节列表
        chapters_json = json.dumps([{"title": chapter.title} for chapter in node.report.chapters], ensure_ascii=False)
        
        # 构建提示
        prompt = get_prompt("chapter_vistask", {
            "QUERY": node.report.original_query,
            "DATA_CONTEXT": node.report.data_context,
            "CHAPTERS": chapters_json
        })
        
        # 调用 LLM 生成可视化任务
        responses = call_openai(prompt, **llm_kwargs)
        
        # 处理响应
        if responses:
            try:
                # 清理响应
                cleaned_response = self._clean_json_response(responses[0])
                
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
    
    def _clean_json_response(self, response: str) -> str:
        """
        清理 LLM 返回的 JSON 响应，移除 Markdown 代码块标记
        
        参数:
            response: LLM 返回的原始响应
            
        返回:
            清理后的 JSON 字符串
        """
        # 移除 Markdown 代码块开始标记（```json 或 ```）
        response = re.sub(r'^```(?:json)?\s*', '', response)
        
        # 移除 Markdown 代码块结束标记（```）
        response = re.sub(r'\s*```$', '', response)
        
        # 移除可能的前导和尾随空白字符
        response = response.strip()
        
        return response


class SelectNextVisualizationTaskAction(DataStorytellingAction):
    def __init__(self):
        super().__init__("A4", "选择下一个需要可视化的任务", [ReportGenerationState.CHAPTER_DEFINED])

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """
        A4 负责选择下一个未完成的可视化任务，并标记为 `in_progress`
        
        步骤:
        1. 确保所有章节的任务状态已初始化
        2. 遍历所有章节，查找第一个 'pending' 状态的任务
        3. 将该任务标记为 'in_progress'
        4. 创建子节点，并记录选定的任务信息
        5. 返回子节点列表
        """
        # 确保所有章节的任务状态已初始化
        for chapter in node.report.chapters:
            if not hasattr(chapter, 'tasks_status') or not chapter.tasks_status:
                chapter.initialize_tasks_status()
        
        # 创建子节点列表
        nodes = []
        
        # 遍历所有章节，查找第一个 'pending' 状态的任务
        for chapter_idx, chapter in enumerate(node.report.chapters):
            # 获取下一个待处理的任务
            task_id, task = chapter.get_next_pending_task()
            
            if task_id and task:
                # 标记任务为 'in_progress'
                chapter.mark_task_in_progress(task_id)
                
                # 创建子节点
                child_node = copy.deepcopy(node)
                child_node.parent_node = node
                child_node.parent_action = self
                child_node.depth = node.depth + 1
                
                # 记录选定的任务信息
                child_node.selected_task = {
                    "chapter_idx": chapter_idx,
                    "chapter_title": chapter.title,
                    "task_id": task_id,
                    "task_name": task.get("task_name", ""),
                    "description": task.get("description", ""),
                    "chart_type": task.get("chart_type", []),
                    "relevant_columns": task.get("relevant_columns", [])
                }
                
                # 添加到子节点列表
                nodes.append(child_node)
                
                # 只返回一个任务，避免同时执行多个
                return nodes
        
        # 所有任务都已完成或没有任务，返回空列表
        return nodes



# class ChartsGeneratorAction(MCTSAction):
#     def execute(self, report: Report, llm_kwargs: Dict[str, Any]):
#         current_chapter = report.chapters[-1]
#         configs = getattr(current_chapter, "chart_configs", [])
#         for cfg in configs:
#             chart_url = generate_chart(cfg=cfg)  # 你的图表生成函数
#             current_chapter.add_chart(Chart(url=chart_url, caption=""))


class GenerateVisualizationAction(DataStorytellingAction):
    def __init__(self):
        super().__init__("A5", "生成可视化图表", [ReportGenerationState.CHAPTER_DEFINED])
        
    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """
        A5 负责根据选定的可视化任务生成图表
        
        步骤:
        1. 获取 A4 选择的任务信息
        2. 使用 LIDA 生成可视化图表
        3. 将生成的图表添加到相应的章节中
        4. 将任务标记为已完成
        5. 创建子节点并返回
        """
        # 检查是否有选定的任务
        if not hasattr(node, 'selected_task'):
            print("没有选定的可视化任务，无法生成图表")
            return []
        
        # 获取选定的任务信息
        selected_task = node.selected_task
        chapter_idx = selected_task["chapter_idx"]
        task_id = selected_task["task_id"]
        task_name = selected_task["task_name"]
        description = selected_task["description"]
        chart_type = selected_task["chart_type"][0] if selected_task["chart_type"] else "Bar Chart"  # 默认使用条形图
        
        # 创建子节点
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = self
        child_node.depth = node.depth + 1
        
        try:
            # 获取数据文件路径
            dataset_path = node.report.dataset_path
            
            # 读取数据
            df = pd.read_csv(dataset_path)
            
            # 创建 LIDA 管理器
            from lida.components.manager import Manager
            from lida.datamodel import Goal, Summary, TextGenerationConfig
            from lida.utils import read_dataframe
            from lida.components.executor import ChartExecutor

            manager = Manager()
            
            # 读取数据摘要 JSON 文件
            data_summary = {}
            json_path = os.path.join(os.path.dirname(dataset_path), "data_context.json")
            print(f"尝试读取数据摘要 JSON: {json_path}")
            
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data_summary = json.load(f)
                print("✓ 成功读取数据摘要 JSON")
            except Exception as e:
                print(f"✗ 读取数据摘要 JSON 失败: {str(e)}")
                # 如果无法读取 JSON 文件，使用默认值
                data_summary = {
                    "name": node.report.original_query,
                    "dataset_description": node.report.data_context,
                    "fields_info": {col: {"dtype": str(dtype)} for col, dtype in zip(df.columns, df.dtypes)}
                }
            
            # 创建 Goal 对象，参考示例代码
            goal = Goal(
                question=task_name,  # 使用任务描述作为问题
                visualization=chart_type,  # 映射图表类型
                rationale=description  # 使用任务描述作为理由
            )
            
            # 创建 Summary 对象，直接从 JSON 文件中提取必要参数
            summary = Summary(
                name=data_summary.get("name", "购物数据分析"),
                file_name=dataset_path,  # 使用原始数据文件路径
                dataset_description=data_summary.get("dataset_description", "购物数据集"),
                field_names=list(data_summary.get("fields_info", {}).keys()) if "fields_info" in data_summary else df.columns.tolist(),
                fields=[info.get("dtype", "unknown") for info in data_summary.get("fields_info", {}).values()] if "fields_info" in data_summary else [str(dtype) for dtype in df.dtypes.tolist()]
            )
            
            # 生成可视化
            print(f"正在为任务 '{description}' 生成可视化图表...")
            visualization = manager.visualize(summary, goal, library="matplotlib")
            
            # 处理可视化结果
            if isinstance(visualization, list) and len(visualization) > 0:
                visualization = visualization[0]
                print("✓ 使用第一个可视化结果进行处理")
            
            # 检查是否为 ChartExecutorResponse 或具有相同属性的对象
            if hasattr(visualization, 'status') and visualization.status:
                print("✓ 成功生成可视化结果")
                
                # 保存图表
                chart_filename = f"chart_{task_id}.png"
                chart_path = os.path.join("storyteller/output/charts", chart_filename)
                
                # 确保输出目录存在
                os.makedirs(os.path.dirname(chart_path), exist_ok=True)
                
                # 保存图表
                if hasattr(visualization, 'savefig'):
                    visualization.savefig(chart_path)
                    print(f"✓ 图表已保存到: {chart_path}")
                
                # 创建图表对象 - 使用现有的 Chart 类结构
                from storyteller.algorithm.mcts_node import Chart
                chart = Chart(
                    url=chart_path,
                    caption=description,
                    chart_position="center",
                    code=visualization.code if hasattr(visualization, 'code') else None,
                    chart_type=chart_type,
                    task_id=task_id
                )
                
                # 将图表添加到章节
                child_node.report.chapters[chapter_idx].add_chart(chart)
                
                # 将任务标记为已完成
                child_node.report.chapters[chapter_idx].mark_task_completed(task_id)
                
                print(f"✓ 成功为任务 '{description}' 生成可视化图表")
            else:
                error_msg = visualization.error if hasattr(visualization, 'error') else "未知错误"
                print(f"✗ 生成可视化图表失败: {error_msg}")
            
        except Exception as e:
            print(f"✗ 生成可视化图表时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return [child_node]
    
   
class ReviseVisualizationAction(DataStorytellingAction):
    def __init__(self):
        super().__init__("A6", "修改可视化图表", [ReportGenerationState.CHAPTER_DEFINED])
        
    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """
        A6 负责修改已生成的可视化图表
        
        步骤:
        1. 获取 A5 生成的图表
        2. 使用 LIDA 的 edit 功能修改图表
        3. 将修改后的图表更新到相应的章节中
        4. 创建子节点并返回
        """
        # 检查是否有选定的任务
        if not hasattr(node, 'selected_task'):
            print("没有选定的可视化任务，无法修改图表")
            return []
        
        # 获取选定的任务信息
        selected_task = node.selected_task
        chapter_idx = selected_task["chapter_idx"]
        task_id = selected_task["task_id"]
        chapter = node.report.chapters[chapter_idx]
        
        # 查找对应的图表
        target_chart = None
        chart_idx = -1
        for i, chart in enumerate(chapter.charts):
            if hasattr(chart, 'task_id') and chart.task_id == task_id:
                target_chart = chart
                chart_idx = i
                break
        
        if target_chart is None:
            print(f"找不到任务 {task_id} 对应的图表，无法修改")
            return []
        
        # 检查图表是否有代码
        if not hasattr(target_chart, 'code') or not target_chart.code:
            print(f"图表没有关联的代码，无法使用 LIDA 编辑功能")
            return []
        
        # 创建子节点
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = self
        child_node.depth = node.depth + 1
        
        try:
            # 获取数据文件路径
            dataset_path = node.report.dataset_path
            
            # 读取数据
            df = pd.read_csv(dataset_path)
            
            # 创建 LIDA 管理器
            from lida.components.manager import Manager
            from lida.datamodel import Summary
            
            manager = Manager()
            
            # 读取数据摘要 JSON 文件
            data_summary = {}
            json_path = os.path.join(os.path.dirname(dataset_path), "data_context.json")
            print(f"尝试读取数据摘要 JSON: {json_path}")
            
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data_summary = json.load(f)
                print("✓ 成功读取数据摘要 JSON")
            except Exception as e:
                print(f"✗ 读取数据摘要 JSON 失败: {str(e)}")
                # 如果无法读取 JSON 文件，使用默认值
                data_summary = {
                    "name": node.report.original_query,
                    "dataset_description": node.report.data_context,
                    "fields_info": {col: {"dtype": str(dtype)} for col, dtype in zip(df.columns, df.dtypes)}
                }
            
            # 创建 Summary 对象，直接从 JSON 文件中提取必要参数
            summary = Summary(
                name=data_summary.get("name", "购物数据分析"),
                file_name=dataset_path,  # 使用原始数据文件路径
                dataset_description=data_summary.get("dataset_description", "购物数据集"),
                field_names=list(data_summary.get("fields_info", {}).keys()) if "fields_info" in data_summary else df.columns.tolist(),
                fields=[info.get("dtype", "unknown") for info in data_summary.get("fields_info", {}).values()] if "fields_info" in data_summary else [str(dtype) for dtype in df.dtypes.tolist()]
            )
            
            # 生成编辑指令
            edit_instruction = "请根据任务描述修改图表，使图表更符合任务要求。"
            print(f"生成的编辑指令: {edit_instruction}")
            
            # 使用 LIDA 的 edit 功能修改图表
            print(f"正在修改任务 '{selected_task['description']}' 的图表...")
            edited_visualization = manager.edit(
                code=target_chart.code,
                summary=summary,
                instructions=edit_instruction,
                library="matplotlib"
            )
            
            # 处理编辑后的可视化结果
            if isinstance(edited_visualization, list) and len(edited_visualization) > 0:
                edited_visualization = edited_visualization[0]
                print("✓ 使用第一个编辑结果进行处理")
            
            # 检查是否为有效的编辑结果
            if hasattr(edited_visualization, 'status') and edited_visualization.status:
                print("✓ 成功修改可视化图表")
                
                # 保存修改后的图表
                chart_filename = f"chart_{task_id}_edited.png"
                chart_path = os.path.join("storyteller/output/charts", chart_filename)
                
                # 确保输出目录存在
                os.makedirs(os.path.dirname(chart_path), exist_ok=True)
                
                # 保存图表
                if hasattr(edited_visualization, 'savefig'):
                    edited_visualization.savefig(chart_path)
                    print(f"✓ 修改后的图表已保存到: {chart_path}")
                
                # 创建新的图表对象
                from storyteller.algorithm.mcts_node import Chart
                edited_chart = Chart(
                    url=chart_path,
                    caption=target_chart.caption + " (已优化)",
                    chart_position=target_chart.chart_position,
                    code=edited_visualization.code if hasattr(edited_visualization, 'code') else None,
                    chart_type=target_chart.chart_type,
                    task_id=task_id
                )
                
                # 更新章节中的图表
                child_node.report.chapters[chapter_idx].charts[chart_idx] = edited_chart
                
                print(f"✓ 成功修改任务 '{selected_task['description']}' 的图表")
            else:
                error_msg = edited_visualization.error if hasattr(edited_visualization, 'error') else "未知错误"
                print(f"✗ 修改可视化图表失败: {error_msg}")
        
        except Exception as e:
            print(f"✗ 修改可视化图表时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return [child_node]
   
class GenerateCaptionAction(DataStorytellingAction):
    def __init__(self):
        super().__init__("A7", "生成图表说明与洞察", [ReportGenerationState.CHAPTER_DEFINED])
        
    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """
        A7 负责分析可视化图表并生成洞察性的图表说明
        
        步骤:
        1. 获取选定的任务和对应的图表
        2. 结合章节标题、可视化任务和用户查询分析图表
        3. 生成洞察性的图表说明
        4. 更新图表的说明文字
        5. 创建子节点并返回
        """
        # 检查是否有选定的任务
        if not hasattr(node, 'selected_task'):
            print("没有选定的可视化任务，无法生成图表说明")
            return []
        
        # 获取选定的任务信息
        selected_task = node.selected_task
        chapter_idx = selected_task["chapter_idx"]
        task_id = selected_task["task_id"]
        chapter = node.report.chapters[chapter_idx]
        
        # 查找对应的图表
        target_chart = None
        chart_idx = -1
        for i, chart in enumerate(chapter.charts):
            if hasattr(chart, 'task_id') and chart.task_id == task_id:
                target_chart = chart
                chart_idx = i
                break
        
        if target_chart is None:
            print(f"找不到任务 {task_id} 对应的图表，无法生成说明")
            return []
        
        # 创建子节点
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = self
        child_node.depth = node.depth + 1
        
        try:
            # 获取图表URL
            chart_url = target_chart.url
            
            # 将图表转换为base64编码
            import base64
            with open(chart_url, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            
            # 使用模板生成提示词
            prompt_args = {
                "QUERY": node.original_query,
                "CHAPTER_TITLE": chapter.title,
                "TASK_NAME": selected_task.get('task_name', '未知任务')
            }
            
            # 使用 get_prompt 获取提示词
            prompt_text = get_prompt("chart_caption_vision", prompt_args)
            
            print(f"正在为图表生成说明与洞察...")
            
            # 使用 OpenAI 的多模态 API
            from openai import OpenAI
            client = OpenAI()
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的数据可视化分析师，擅长解读图表并提供洞察。"
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt_text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.3
            )
            
            # 获取响应内容
            caption = response.choices[0].message.content.strip()
            
            print(f"✓ 成功生成图表说明")
            
            # 更新图表说明
            updated_chart = copy.deepcopy(target_chart)
            updated_chart.caption = caption
            
            # 更新章节中的图表
            child_node.report.chapters[chapter_idx].charts[chart_idx] = updated_chart
            
            print(f"✓ 成功更新图表说明")
        
        except Exception as e:
            print(f"✗ 生成图表说明时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return [child_node]

class GenerateChapterSummaryAction(DataStorytellingAction):
    def __init__(self):
        super().__init__("A8", "生成章节总结", [ReportGenerationState.CHAPTER_DEFINED])
        
    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """
        A8 负责生成章节的总结
        
        步骤:
        1. 获取章节信息和所有图表的说明
        2. 结合用户查询、章节标题和图表说明生成章节总结
        3. 更新章节的总结文本
        4. 创建子节点并返回
        """
        # 检查是否有选定的任务
        if not hasattr(node, 'selected_task'):
            print("没有选定的任务，无法确定要总结的章节")
            return []
        
        # 获取选定的任务信息
        selected_task = node.selected_task
        chapter_idx = selected_task["chapter_idx"]
        chapter = node.report.chapters[chapter_idx]
        
        # 检查章节是否有图表
        if not chapter.charts:
            print(f"章节 '{chapter.title}' 没有图表，无法生成总结")
            return []
        
        # 创建子节点
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = self
        child_node.depth = node.depth + 1
        
        try:
            # 收集所有图表的说明
            charts_captions = []
            for i, chart in enumerate(chapter.charts):
                caption = chart.caption if hasattr(chart, 'caption') and chart.caption else "无说明"
                task_id = chart.task_id if hasattr(chart, 'task_id') else f"图表_{i+1}"
                charts_captions.append(f"图表 {i+1} ({task_id}):\n{caption}")
            
            # 将所有图表说明合并为一个文本
            charts_captions_text = "\n\n".join(charts_captions)
            
            # 使用模板生成提示词
            prompt_args = {
                "QUERY": node.original_query,
                "CHAPTER_TITLE": chapter.title,
                "CHARTS_CAPTIONS": charts_captions_text
            }
            
            # 使用 get_prompt 获取提示词
            prompt = get_prompt("chapter_summary", prompt_args)
            
            print(f"正在为章节 '{chapter.title}' 生成总结...")
            
            # 使用 call_openai 调用 LLM
            responses = call_openai(prompt, **llm_kwargs)
            if responses and len(responses) > 0:
                summary = responses[0].strip()
                print(f"✓ 成功生成章节总结")
                
                # 更新章节总结
                child_node.report.chapters[chapter_idx].summary = summary
                
                print(f"✓ 成功更新章节 '{chapter.title}' 的总结")
            else:
                print(f"✗ 生成章节总结失败: 没有收到有效响应")
        
        except Exception as e:
            print(f"✗ 生成章节总结时发生错误: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return [child_node]
