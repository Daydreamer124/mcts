import copy
import json
import re,os,traceback
from typing import Dict, List, Any, Optional
from storyteller.algorithm.utils.DatasetContextGenerator import DatasetContextGenerator  # 引入数据集解析器
from storyteller.algorithm.mcts_node import *
from storyteller.llm_call.openai_llm import call_openai
from storyteller.llm_call.prompt_factory import get_prompt
from typing import List, Dict, Any
import pandas as pd
from enum import Enum
import base64
from PIL import Image
import io,requests
from openai import OpenAI
from .utils.html2image import convert_html_file_to_image
from storyteller.algorithm.mcts_node import ReportGenerationState
from llmx import llm, TextGenerator
from lida.components.manager import Manager




class DataStorytellingAction:
    def __init__(self, action_id: str, description: str):
        self.action_id = action_id
        self.description = description# 默认的下一个状态
        
        # 添加 MCTS 统计属性
        self.Q = 0.0  # 累积奖励
        self.N = 0    # 访问次数
  

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = self
            child_node.depth = node.depth + 1
        
            raise NotImplementedError
        
    
class Query2Chapters(DataStorytellingAction):
    def __init__(self):
        super().__init__("A1", "定义章节结构") 


    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """
        根据用户查询和数据上下文，尝试不同的章节划分策略
        """
        # 使用 clarified_query（如果有）或原始查询
        query = node.report.clarified_query if node.report.clarified_query else node.report.original_query
        
        # 构建提示，包含查询和数据上下文
        prompt = get_prompt("Query2Chapters", {
            "QUERY": query,
            "DATA_CONTEXT": node.report.data_context
        })
        
        # 调用 LLM 生成章节划分方案
        responses = call_openai(prompt, **llm_kwargs)
        nodes = []
        
        # 如果响应为空，返回当前节点作为子节点，防止流程中断
        if not responses:
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = self
            child_node.depth = node.depth + 1
            
            # 如果没有章节，添加一个默认章节
            if not child_node.report.chapters:
                child_node.report.add_chapter(Chapter(title=query))
            
            nodes.append(child_node)
            return nodes
        
        # 处理每个响应，创建子节点
        for response in responses:
            try:
                # 清理响应，移除 Markdown 代码块标记
                cleaned_response = self._clean_json_response(response)
                
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
                    for title in chapter_data["chapters"]:
                        child_node.report.add_chapter(Chapter(title=title))
                
                # 关键修改：设置子节点状态为 a1
                child_node.node_type = ReportGenerationState.a1
                
                # 添加到节点列表
                nodes.append(child_node)
                
            except json.JSONDecodeError as e:
                print(f"无法解析 JSON 响应: {response}")
                print(f"错误详情: {e}")
                continue
            except Exception as e:
                print(f"处理章节划分响应时出错: {e}")
                continue
        
        # 如果处理完所有响应后节点列表仍为空，添加默认节点
        if not nodes:
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = self
            child_node.depth = node.depth + 1
            
            # 如果没有章节，添加一个默认章节
            if not child_node.report.chapters:
                child_node.report.add_chapter(Chapter(title=query))
            
            nodes.append(child_node)
        
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



class Chapters2Tasks(DataStorytellingAction):
    def __init__(self):
        super().__init__("A2", "根据章节方案划分章节任务方案")

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """为每个章节生成多种任务方案"""
        children_nodes = []
        
        try:
            # 获取数据集信息
            data_context = node.report.data_context
            
            # 为每个章节方案创建2-3个不同的任务方案子节点
            # 创建基础节点的多个副本
            for variant_idx in range(3):  # 生成3个不同的任务方案变体
                # 创建子节点
                child_node = copy.deepcopy(node)
                child_node.parent_node = node
                child_node.parent_action = self
                child_node.depth = node.depth + 1
                
                # 生成 LLM 提示词
                prompt_text = get_prompt("Chapters2Tasks", {
                    "QUERY": node.original_query,
                    "DATA_CONTEXT": data_context,
                    "CHAPTERS": json.dumps([{
                        "title": getattr(chapter, 'title', f"章节{i+1}") if not isinstance(chapter, dict) else chapter.get('title', f"章节{i+1}")
                    } for i, chapter in enumerate(child_node.report.chapters)], ensure_ascii=False)
                })
                
                # 使用不同的温度，以获得更多样化的任务方案
                llm_kwargs_temp = llm_kwargs.copy()
                llm_kwargs_temp['temperature'] = 0.3 + variant_idx * 0.25  # 0.3, 0.55, 0.8
                
                print(f"\n🔄 生成任务方案变体 {variant_idx+1}/3 (温度: {llm_kwargs_temp['temperature']})")
                
                responses = call_openai(prompt_text, **llm_kwargs_temp)
                if not responses:
                    print(f"❌ 变体 {variant_idx+1} 没有收到有效响应")
                    continue
                
                response_text = responses[0]
                
                try:
                    # 清理响应文本，提取 JSON 部分
                    json_text = self.extract_json_from_text(response_text)
                    print(f"原始响应: {json_text}")
                    
                    # 解析 JSON
                    response_json = json.loads(json_text)
                    
                    # 处理每个章节的可视化任务
                    if "chapters" in response_json:
                        # 创建章节标题到索引的映射
                        chapter_title_to_index = {}
                        for i, chapter in enumerate(child_node.report.chapters):
                            # 安全获取标题文本
                            if isinstance(chapter, dict):
                                # 如果章节是字典类型
                                if 'title' in chapter:
                                    # 如果章节字典有'title'键
                                    if isinstance(chapter['title'], dict):
                                        # 如果'title'键对应的值也是字典
                                        title_text = chapter['title'].get('title', '') or chapter['title'].get('text', f"章节{i+1}")
                                    else:
                                        # 如果'title'键对应的值是字符串
                                        title_text = chapter['title']
                                else:
                                    # 如果章节字典没有'title'键，使用默认值
                                    title_text = f"章节{i+1}"
                            else:
                                # 如果章节是对象类型
                                title_attr = getattr(chapter, 'title', None)
                                if isinstance(title_attr, dict):
                                    # 如果title属性是字典
                                    title_text = title_attr.get('title', '') or title_attr.get('text', f"章节{i+1}")
                                else:
                                    # 如果title属性是字符串或其他类型
                                    title_text = title_attr if title_attr else f"章节{i+1}"
                            
                            # 确保title_text是字符串类型
                            if not isinstance(title_text, str):
                                title_text = str(title_text)
                                
                            # 存储小写标题文本到索引的映射
                            chapter_title_to_index[title_text.lower()] = i
                        
                        # 处理每个章节
                        for chapter_info in response_json["chapters"]:
                            raw_title = chapter_info.get("title", "")
                            # 调试打印
                            #print(f"DEBUG - 获取到的 title 类型: {type(raw_title)}")
                            #print(f"DEBUG - title 内容: {raw_title}")
                            
                            # 安全获取标题文本
                            if isinstance(raw_title, dict):
                                # 如果是字典，尝试提取文本
                                title_text = raw_title.get('title', '') or raw_title.get('text', '')
                            else:
                                # 如果不是字典，直接使用
                                title_text = raw_title
                            
                            # 确保title_text是字符串类型
                            if not isinstance(title_text, str):
                                title_text = str(title_text) if title_text is not None else ""
                                
                            tasks = chapter_info.get("tasks", [])
                            
                            # 查找匹配的章节
                            chapter_idx = -1
                            title_lower = title_text.lower()  # 现在可以安全调用lower()
                            
                            # 精确匹配
                            if title_lower in chapter_title_to_index:
                                chapter_idx = chapter_title_to_index[title_lower]
                            else:
                                # 模糊匹配
                                for i, chapter in enumerate(child_node.report.chapters):
                                    # 安全获取章节标题
                                    if isinstance(chapter, dict):
                                        if 'title' in chapter:
                                            if isinstance(chapter['title'], dict):
                                                search_title = chapter['title'].get('title', '') or chapter['title'].get('text', f"章节{i+1}")
                                            else:
                                                search_title = chapter['title']
                                        else:
                                            search_title = f"章节{i+1}"
                                    else:
                                        title_attr = getattr(chapter, 'title', None)
                                        if isinstance(title_attr, dict):
                                            search_title = title_attr.get('title', '') or title_attr.get('text', f"章节{i+1}")
                                        else:
                                            search_title = title_attr if title_attr else f"章节{i+1}"
                                    
                                    # 确保search_title是字符串类型
                                    if not isinstance(search_title, str):
                                        search_title = str(search_title)
                                        
                                    search_title_lower = search_title.lower()
                                    if title_lower in search_title_lower or search_title_lower in title_lower:
                                        chapter_idx = i
                                        break
                            
                            if chapter_idx >= 0 and chapter_idx < len(child_node.report.chapters):
                                chapter = child_node.report.chapters[chapter_idx]
                                
                                # 清空现有任务列表
                                chapter.visualization_tasks = []
                                
                                # 添加任务
                                for task in tasks:
                                    task_id = task.get("task_id", "")
                                    description = task.get("task_description", "")
                                    chart_type = task.get("chart_type", ["Bar Chart"])
                                    
                                    # 创建任务对象
                                    task_obj = {
                                        "task_id": task_id,
                                        "task_description": description,
                                        "chart_type": chart_type,
                                        "status": "pending",  # 添加状态字段
                                        "visualization_success": False  # 添加可视化成功标志
                                    }
                                    
                                    # 添加到章节的任务列表
                                    if not hasattr(chapter, 'visualization_tasks'):
                                        chapter.visualization_tasks = []
                                    chapter.visualization_tasks.append(task_obj)
                                    
                                    # 打印任务状态
                                    print(f"   - 任务ID: '{task_id}'")
                                    print(f"   - 任务描述: '{description}'")
                                    print(f"   - 图表类型: {chart_type}")
                                    print(f"   - 状态: {task_obj.get('status')}")
                                
                                # 打印调试信息
                                print(f"✅ 变体 {variant_idx+1} - 章节 {chapter_idx+1} ({chapter.title}) 生成了 {len(tasks)} 个可视化任务")
                                print(f"当前章节任务列表: {[t.get('task_id') for t in chapter.visualization_tasks]}")
                            else:
                                print(f"❌ 找不到匹配的章节: {title_text}")
                        
                        # 检查所有章节是否都有任务
                        all_chapters_have_tasks = True
                        for i, chapter in enumerate(child_node.report.chapters):
                            if not hasattr(chapter, 'visualization_tasks') or not chapter.visualization_tasks:
                                print(f"⚠️ 变体 {variant_idx+1} - 章节 {i+1} ({chapter.title}) 没有任务")
                                all_chapters_have_tasks = False
                            else:
                                print(f"✓ 变体 {variant_idx+1} - 章节 {i+1} ({chapter.title}) 有 {len(chapter.visualization_tasks)} 个任务")
                        
                        # 只有当所有章节都有任务时，才添加这个变体
                        if all_chapters_have_tasks:
                            children_nodes.append(child_node)
                            print(f"✅ 任务方案变体 {variant_idx+1} 已添加到候选列表")
                    
                except json.JSONDecodeError as e:
                    print(f"❌ JSON 解析错误: {str(e)}")
                    print(f"⚠️ 变体 {variant_idx+1} 无法解析 JSON，跳过")
            
            # 如果没有生成任何有效的方案，返回原始节点的副本
            if not children_nodes:
                print("⚠️ 没有生成任何有效的任务方案，返回原始节点")
                fallback_node = copy.deepcopy(node)
                fallback_node.parent_node = node
                fallback_node.parent_action = self
                fallback_node.depth = node.depth + 1
                children_nodes.append(fallback_node)
            
            print(f"🔢 总共生成了 {len(children_nodes)} 个有效的任务方案变体")
            
        except Exception as e:
            print(f"❌ 生成可视化任务时出错: {str(e)}")
            traceback.print_exc()
            # 确保即使出错也返回至少一个子节点
            if not children_nodes:
                fallback_node = copy.deepcopy(node)
                fallback_node.parent_node = node
                fallback_node.parent_action = self
                fallback_node.depth = node.depth + 1
                children_nodes.append(fallback_node)
        
        # 为所有生成的节点设置正确的状态
        for child_node in children_nodes:
            child_node.node_type = ReportGenerationState.a2
        
        return children_nodes

    def extract_json_from_text(self, response_text):
        """从文本中提取 JSON 部分"""
        try:
            # 尝试直接解析整个响应
            json.loads(response_text)
            return response_text
        except:
            # 如果直接解析失败，尝试提取 JSON 部分
            import re
            
            # 移除 markdown 代码块标记
            response_text = re.sub(r'^```(?:json)?\s*', '', response_text)
            response_text = re.sub(r'\s*```$', '', response_text)
            
            # 查找 JSON 对象
            json_pattern = r'\{.*\}'
            json_match = re.search(json_pattern, response_text, re.DOTALL)
            
            if json_match:
                return json_match.group(0)
            
            return response_text



class Tasks2Charts(DataStorytellingAction):
    def __init__(self):
        super().__init__("A3", "生成可视化")
        # 初始化图表相似度检测工具
        try:
            from storyteller.algorithm.utils.ChartSimilarity import ChartSimilarity
            self.similarity_tool = ChartSimilarity()
            self.similarity_threshold = 0.88  # 相似度阈值
            self.use_similarity_check = self.similarity_tool.initialized
            print("✅ 图表相似度检测工具初始化成功")
        except Exception as e:
            print(f"⚠️ 图表相似度检测工具初始化失败: {str(e)}")
            self.use_similarity_check = False
            
    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = self
        child_node.depth = node.depth + 1

        try:
            # 递增迭代号 - 确保每次创建新节点时迭代号加1
            child_node.report.current_iteration += 1
            current_iteration = child_node.report.current_iteration
            print(f"✅ 当前迭代号: {current_iteration}")
            
            # 确定当前迭代号和保存路径
            iteration_dir = os.path.join("storyteller", "output", "iterations", f"iteration_{current_iteration}")
            os.makedirs(iteration_dir, exist_ok=True)
            charts_dir = os.path.join(iteration_dir, "charts")
            os.makedirs(charts_dir, exist_ok=True)
            
            # 获取数据集
            dataset_path = node.report.dataset_path
            df = pd.read_csv(dataset_path)

            # 遍历所有章节
            for chapter_idx, chapter in enumerate(child_node.report.chapters):
                print(f"\n📊 正在处理第 {chapter_idx + 1} 章...")
                print(f"章节标题: {getattr(chapter, 'title', f'章节{chapter_idx+1}')}")
                print(f"章节的可视化任务数量: {len(getattr(chapter, 'visualization_tasks', []))}")
                
                # 初始化章节图表列表（如果不存在）
                if not hasattr(chapter, 'charts'):
                    chapter.charts = []
                
                # 收集所有章节的图表用于相似度检查
                all_charts = []
                for ch in child_node.report.chapters:
                    if hasattr(ch, 'charts'):
                        all_charts.extend(ch.charts)
                
                # 遍历章节中的所有可视化任务
                for task in chapter.visualization_tasks:
                    print(f"\n🔍 处理任务:")
                    print(f"- 任务ID: {task.get('task_id', '')}")
                    print(f"- 任务描述: {task.get('task_description', '')}")
                    print(f"- 图表类型: {task.get('chart_type', ['Bar Chart'])[0]}")
                    
                    task_id = task.get('task_id', "")
                    description = task.get('task_description')
                    chart_type = task.get('chart_type', ["Bar Chart"])[0]

                    # 使用任务ID作为文件名，如果为空则使用任务描述
                    file_name = task_id if task_id else description
                    if not file_name:
                        file_name = f"chart_{chapter_idx}_{len(chapter.charts)}"
                    # 清理文件名中的非法字符
                    file_name = re.sub(r'[<>:"/\\|?*]', '_', file_name)
                    chart_path = os.path.join(charts_dir, f"{file_name}.png")

                    
                    from lida.datamodel import Goal, Summary
                    from lida.components.manager import Manager
                    # 创建 Goal 对象 - 使用 description 替代 task_name
                    goal = Goal(question=task_id, visualization=chart_type, rationale=description)

                    # 创建 Summary 对象
                    # 读取数据摘要 JSON 文件
                    data_summary = {}
                    json_path = os.path.join("storyteller", "dataset", "data_context.json")
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

                    # 创建 Summary 对象，使用从 JSON 文件中提取的信息
                    summary = Summary(
                        name=data_summary.get("name", "购物数据分析"),
                        file_name=dataset_path,
                        dataset_description=str(data_summary.get("dataset_description", "购物数据集")),
                        field_names=list(data_summary.get("fields_info", {}).keys()) if "fields_info" in data_summary else df.columns.tolist(),
                        fields=[info.get("dtype", "unknown") for info in data_summary.get("fields_info", {}).values()] if "fields_info" in data_summary else [str(dtype) for dtype in df.dtypes.tolist()]
                    )
                    
                    # 创建自定义的文本生成器
                    #text_gen = llm(provider="openai", model="gpt-4-32k")
                    text_gen = llm(
                        provider="openai", 
                        model="gpt-4-32k"
                    )

                    # 创建 LIDA 管理器
                    manager = Manager(text_gen=text_gen)

                    # 生成可视化
                    print(f"正在为任务 '{description}' 生成可视化图表...")
                    visualization = manager.visualize(summary, goal, library="matplotlib")

                    # 处理可视化结果
                    if isinstance(visualization, list) and len(visualization) > 0:
                        visualization = visualization[0]

                    if hasattr(visualization, 'status') and visualization.status:
                        print("✓ 成功生成可视化结果")

                        # 保存图表
                        if hasattr(visualization, 'savefig'):
                            visualization.savefig(chart_path)
                            print(f"✓ 图表已保存到: {chart_path}")
                            
                            # 检查图表相似度
                            if self.use_similarity_check and all_charts:
                                # 收集已有图表的路径列表
                                existing_chart_paths = []
                                for chart in all_charts:
                                    if hasattr(chart, 'url') and chart.url:
                                        existing_chart_paths.append(chart.url)
                                
                                if existing_chart_paths:
                                    # 使用batch_compare计算相似度
                                    is_too_similar, max_similarity, similar_chart_path, all_similarities = self.similarity_tool.batch_compare(
                                        chart_path, existing_chart_paths, self.similarity_threshold
                                    )
                                    
                                    if is_too_similar:
                                        # 找到最相似的图表对象
                                        similar_chart = None
                                        for chart in all_charts:
                                            if hasattr(chart, 'url') and chart.url == similar_chart_path:
                                                similar_chart = chart
                                                break
                                        
                                        similar_task_id = getattr(similar_chart, 'task_id', '未知任务') if similar_chart else '未知任务'
                                        
                                        print(f"⚠️ 警告: 生成的图表与现有图表相似度过高 ({max_similarity:.4f})")
                                        print(f"   - 相似图表: {similar_task_id}")
                                        
                                        # 创建samechart文件夹
                                        samechart_dir = os.path.join(charts_dir, "samechart")
                                        os.makedirs(samechart_dir, exist_ok=True)
                                        
                                        # 移动相似的图表到samechart文件夹
                                        samechart_path = os.path.join(samechart_dir, f"{file_name}.png")
                                        
                                        try:
                                            import shutil
                                            # 移动图表到samechart目录(而非复制)
                                            shutil.move(chart_path, samechart_path)
                                            print(f"✓ 相似图表已移动到: {samechart_path}")
                                            
                                            # 在控制台输出相似度信息
                                            print(f"📊 图表相似度信息:")
                                            print(f"   - 相似度值: {max_similarity:.4f}")
                                            print(f"   - 相似图表任务: {similar_task_id}")
                                            print(f"   - 当前任务: {task_id}")
                                            
                                            # 标记任务为已完成但图表被跳过
                                            for vis_task in chapter.visualization_tasks:
                                                if vis_task.get('task_id') == task_id:
                                                    vis_task['visualization_success'] = False
                                                    vis_task['skipped_due_to_similarity'] = True
                                                    print(f"⚠️ 任务 '{task_id}' 因图表相似度过高而被跳过")
                                                    break
                                                    
                                            # 跳过当前任务的后续处理
                                            continue
                                            
                                        except Exception as e:
                                            print(f"⚠️ 移动相似图表时出错: {str(e)}")
                                            # 如果移动失败，继续使用原始路径

                        # 创建图表对象
                        print(f"\n📊 创建图表对象:")
                        print(f"- 图表路径: {chart_path}")
                        print(f"- 图表类型: {chart_type}")
                        print(f"- 任务ID: {task_id}")
                        
                        chart = Chart(
                            url=chart_path,
                            caption="",  # 使用空字符串作为初始说明
                            chart_type=chart_type,
                            task_id=task_id  # task_id 实际上就是任务描述
                        )
                        
                        # 存储可视化代码，以便后续修改
                        if hasattr(visualization, 'code'):
                            chart.code = visualization.code
                        
                        # 添加图表到章节
                        if not hasattr(chapter, 'charts'):
                            chapter.charts = []
                            print("初始化章节的图表列表")
                        
                        chapter.charts.append(chart)
                        # 更新所有图表列表
                        all_charts.append(chart)
                        print(f"✓ 图表已添加到章节，当前章节图表数量: {len(chapter.charts)}")
                        
                        # 如果处理成功，也标记为已完成
                        for vis_task in chapter.visualization_tasks:
                            if vis_task.get('task_id') == task_id:
                                vis_task['visualization_success'] = True
                                print(f"✅ 任务 '{task_id}' 已成功完成")
                                break
                    else:
                        print("✗ 生成可视化图表失败")
                        # 即使失败也标记为完成，避免无限循环
                        # 注意：我们已经在当前循环中有了 chapter_idx，不需要从 task 中获取
                        for vis_task in chapter.visualization_tasks:
                            if vis_task.get('task_id') == task_id:
                                # 确保初始化 visualization_success 字段
                                vis_task['visualization_success'] = False
                                print(f"⚠️ 任务 '{description}' 虽然失败但已标记为已完成，避免无限循环")
                                break
            # 设置正确的状态
            child_node.node_type = ReportGenerationState.a3
            return [child_node]

        except Exception as e:
            print(f"❌ 处理节点时出错: {str(e)}")
            traceback.print_exc()
            # 确保即使异常也设置正确的状态
            child_node.node_type = ReportGenerationState.a3
            return [child_node]


class ReviseVis(DataStorytellingAction):
    def __init__(self):
        super().__init__("A4", "对所有可视化图表进行Revise判断")
    
    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """修改可视化图表"""
        # 创建子节点
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = self
        child_node.depth = node.depth + 1
        
        try:
            # 遍历所有章节
            for chapter_idx, chapter in enumerate(child_node.report.chapters):
                # 检查章节是否有可视化任务
                if not hasattr(chapter, 'visualization_tasks') or not chapter.visualization_tasks:
                    print(f"⚠️ 章节 {chapter_idx + 1} 没有可视化任务，跳过")
                    continue
                    
                for task in chapter.visualization_tasks:
                    # 安全地检查 visualization_success 字段
                    if task.get('visualization_success', False) == True:
                        continue
                        
                    task_id = task.get('task_id', "")
                    description = task.get('task_description', "")
                    
                    print(f"正在修改任务 '{task_id}' 的图表...")
            
                    selected_chart = None
                    print(f"\n🔍 在章节中查找图表:")
                    print(f"- 章节标题: {getattr(chapter, 'title', f'章节{chapter_idx+1}')}")
                    print(f"- 章节中的图表数量: {len(getattr(chapter, 'charts', []))}")
                    
                    for c in chapter.charts:
                        print(f"- 检查图表: task_id={getattr(c, 'task_id', 'None')}")
                        if hasattr(c, 'task_id') and c.task_id == task_id:
                            selected_chart = c
                            print(f"✓ 找到匹配的图表")
                            break
                    
                    # 如果没有找到匹配的图表，跳过此任务
                    if not selected_chart:
                        print(f"⚠️ 找不到与任务 '{task_id}' 匹配的图表，跳过")
                        continue
                
                    try:
                        # 获取数据文件路径
                        dataset_path = node.report.dataset_path
                        
                        # 读取数据
                        df = pd.read_csv(dataset_path)
                        
                        # 创建 LIDA 管理器
                        from lida.components.manager import Manager
                        from lida.datamodel import Summary
                        
                        # 创建自定义的文本生成器
                        text_gen = llm(provider="openai", model="gpt-4-32k")
                        manager = Manager(text_gen=text_gen)
                        
                        # 读取数据摘要 JSON 文件
                        data_summary = {}
                        json_path = os.path.join("storyteller", "dataset", "data_context.json")
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
                            name=data_summary.get("name", "数据分析"),
                            file_name=dataset_path,  # 使用原始数据文件路径
                            dataset_description=str(data_summary.get("dataset_description", "购物数据集")),
                            field_names=list(data_summary.get("fields_info", {}).keys()) if "fields_info" in data_summary else df.columns.tolist(),
                            fields=[info.get("dtype", "unknown") for info in data_summary.get("fields_info", {}).values()] if "fields_info" in data_summary else [str(dtype) for dtype in df.dtypes.tolist()]
                        )
                        
                        # 生成编辑指令
                        edit_instruction = "修改图表错误，让图表更加美观，清晰"
                        #print(f"生成的编辑指令: {edit_instruction}")
                        
                        # 使用 LIDA 的 edit 功能修改图表
                        print(f"正在修改任务 '{description}' 的图表...")
                        edited_visualization = manager.edit(
                            code=selected_chart.code,
                            summary=summary,
                            instructions=edit_instruction,
                            library="matplotlib"
                        )
                        
                        # 处理编辑后的可视化结果
                        if edited_visualization is None:
                            print("✗ 编辑可视化图表失败: 返回结果为None")
                        elif isinstance(edited_visualization, list) and len(edited_visualization) > 0:
                            edited_visualization = edited_visualization[0]
                            print("✓ 使用第一个编辑结果进行处理")
                        
                        # 检查是否为有效的编辑结果
                        if hasattr(edited_visualization, 'status') and edited_visualization.status:
                            print("✓ 成功修改可视化图表")
                            
                            # 找到当前图表所在的迭代目录
                            original_chart_path = selected_chart.url
                            chart_dir = os.path.dirname(original_chart_path)
                            
                            # 将修改后的图表保存到同一目录下
                            edited_chart_name = f"{task_id}_edited.png"
                            edited_chart_path = os.path.join(chart_dir, edited_chart_name)
                            
                            # 保存修改后的图表
                            if hasattr(edited_visualization, 'savefig'):
                                edited_visualization.savefig(edited_chart_path)
                                print(f"✓ 修改后的图表已保存到: {edited_chart_path}")
                            
                            # 创建新的图表对象
                            from storyteller.algorithm.mcts_node import Chart
                            edited_chart = Chart(
                                url=edited_chart_path,
                                caption="",  # 使用空字符串作为初始说明
                                chart_type=selected_chart.chart_type,
                                task_id=task_id  # 使用原始任务ID/描述
                            )
                            edited_chart.needs_caption = True  # 设置需要生成说明文字的标志
                            
                            # 更新章节中的图表
                            for i, c in enumerate(chapter.charts):
                                if hasattr(c, 'task_id') and c.task_id == task_id:
                                    chapter.charts[i] = edited_chart
                                    break
                        else:
                            error_msg = edited_visualization.error if hasattr(edited_visualization, 'error') else "未知错误"
                            print(f"✗ 修改可视化图表失败: {error_msg}")
                    except Exception as e:
                        print(f"✗ 修改可视化图表时发生错误: {str(e)}")
                        import traceback
                        traceback.print_exc()
            
             # 设置正确的状态
            child_node.node_type = ReportGenerationState.a4
            return [child_node]
                
        except Exception as e:
            print(f"❌ 处理节点时出错: {str(e)}")
            # 如果没有找到任务，返回空列表
            print("❌ 没有找到待处理的任务")
            # 确保即使异常也设置正确的状态
            child_node.node_type = ReportGenerationState.a4
            return [child_node]
   
 

class Charts2Captions(DataStorytellingAction):
    def __init__(self):
        super().__init__("A5", "根据所有可视化图表生成所有对应Caption")
    
    def _get_image_base64(self, image_path: str) -> str:
        """将图片转换为 base64 编码"""
        try:
            with Image.open(image_path) as img:
                # 将图片转换为 bytes
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format=img.format)
                img_byte_arr = img_byte_arr.getvalue()
                # 转换为 base64
                return base64.b64encode(img_byte_arr).decode('utf-8')
        except Exception as e:
            print(f"❌ 图片转换失败: {str(e)}")
            return None

    def clean_response(self, response: str) -> str:
        """清理 API 返回的响应内容"""
        # 如果响应包含完整的 HTML 文档，说明可能是错误的响应
        if '<!doctype html>' in response.lower():
            return ""
        
        # 移除任何 HTML 标签
        import re
        clean_text = re.sub(r'<[^>]+>', '', response)
        
        # 清理多余的空白字符
        clean_text = ' '.join(clean_text.split())
        
        return clean_text.strip()

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """为图表生成说明文字"""
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = self
        child_node.depth = node.depth + 1
        
        try:
            # 遍历所有章节
            for chapter_idx, chapter in enumerate(child_node.report.chapters):
                print(f"\n📑 正在处理第 {chapter_idx + 1} 章...")
                print(f"章节标题: {getattr(chapter, 'title', f'章节{chapter_idx+1}')}")
                
                # 检查章节是否有图表
                if not hasattr(chapter, 'charts') or not chapter.charts:
                    print(f"⚠️ 章节 {chapter_idx + 1} 没有图表，跳过")
                    continue
                
                print(f"章节中的图表数量: {len(chapter.charts)}")
                
                # 遍历章节中的所有图表
                for chart in chapter.charts:
                    # 检查图表是否已经有说明文字
                    if hasattr(chart, 'caption') and chart.caption:
                        print(f"图表已有说明文字，跳过")
                        continue
                        
                    print(f"\n📊 正在为图表生成说明文字...")
                    print(f"📌 图表路径: {chart.url}")
                    print(f"📌 图表类型: {chart.chart_type}")
                    print(f"📌 任务ID: {chart.task_id}")
                    
                    # 获取图片的 base64 编码
                    base64_image = self._get_image_base64(chart.url)
                    if not base64_image:
                        print("❌ 图片处理失败，跳过该图表")
                        continue

                    # 准备 prompt
                    prompt_args = {
                        "QUERY": node.original_query,
                        "CHAPTER_TITLE": getattr(chapter, 'title', f"章节{chapter_idx+1}") if not isinstance(chapter, dict) else chapter.get('title', f"章节{chapter_idx+1}"),
                        "CHART_TYPE": chart.chart_type,
                        "TASK_DESCRIPTION": chart.task_id,  # 使用 task_id 作为任务描述
                        "DATA_CONTEXT": node.report.data_context
                    }
                    prompt = get_prompt("chart_caption", prompt_args)
                    
                    # try:
                    #     client = OpenAI(
                    #         api_key=llm_kwargs.get("api_key"),
                    #         base_url=llm_kwargs.get("base_url")
                    #     )
                        
                    #     response = client.chat.completions.create(
                    #         model="gpt-4o-turbo",
                    #         messages=[
                    #             {
                    #                 "role": "system",
                    #                 "content": "You are a data visualization expert. Your task is to analyze this chart and provide insight with the following information."
                    #             },
                    #             {
                    #                 "role": "user",
                    #                 "content": [
                    #                     {"type": "text", "text": prompt},
                    #                     {
                    #                         "type": "image_url",
                    #                         "image_url": {
                    #                             "url": f"data:image/png;base64,{base64_image}"
                    #                         }
                    #                     }
                    #                 ]
                    #             }
                    #         ],
                    #         temperature=0.3,
                    #         max_tokens=2048
                    #     )
                    try:
                        url = "https://gpt-api.hkust-gz.edu.cn/v1/chat/completions"
                        headers = {
                            "Content-Type": "application/json",
                            "Authorization": "7ca9f48d315049bbad0b355afcd5f3a147a8395e46f249e3b7890ffa9ca5122c" #Please change your KEY. If your key is XXX, the Authorization is "Authorization": "Bearer XXX"
                        }
                        data = {
                            "model": "gpt-4-turbo", #使用支持图像识别的模型
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "You are a data visualization expert."
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text":prompt
                                        },
                                        {
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/png;base64,{base64_image}"
                                            }
                                        }
                                    ]
                                }   
                            ],
                            "temperature": 0.8,
                            "max_tokens": 2048 #max_tokens is Required.Since the default value of max_tokens is 16, which results in the inability of the GPT to display complete answers.
                        #stream is not available in gpt-4 vision.
                        }
                        response = requests.post(url, headers=headers, data=json.dumps(data))
                        print(response.json())
                        # 处理响应
                        if isinstance(response, str):
                            caption = response.strip()
                        else:
                            # 获取响应JSON并提取内容
                            #caption = response.choices[0].message.content.strip()  一展用法
                            response_json = response.json() #学校api用法
                            caption = response_json['choices'][0]['message']['content'].strip() ##学校api用法
                        
                        # 清理响应内容
                        clean_caption = self.clean_response(caption)
                        
                        print("\n🧹 清理后的说明文字:")
                        print("-" * 50)
                        print(clean_caption)
                        print("-" * 50)
                        
                        if clean_caption:  # 只有在有效的说明文字时才更新
                            # 更新图表说明
                            chart.caption = clean_caption
                            chart.needs_caption = False
                            
                            # 更新任务状态
                            for task in chapter.visualization_tasks:
                                if task.get('task_id') == chart.task_id:
                                    task['status'] = 'completed'
                                    task['caption_generated'] = True
                                    print(f"\n✅ 任务 '{chart.task_id}' 的图表说明已生成，任务完成")
                                    break
                            
                            print("✅ 成功生成图表说明文字")
                        else:
                            print("\n❌ 生成的说明文字无效，跳过更新")
                    except Exception as e:
                        print(f"\n❌ API 调用失败: {str(e)}")
                        traceback.print_exc()
                
        except Exception as e:
            print(f"\n❌ 生成说明文字时出错: {str(e)}")
            traceback.print_exc()
        
        # 设置正确的状态
        child_node.node_type = ReportGenerationState.a5
        
        return [child_node]


class Captions2Summaries(DataStorytellingAction):
    def __init__(self):
        super().__init__("A6", "根据每个章节的Caption生成每个章节的总结")
    
    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = self
        child_node.depth = node.depth + 1
        
        try:
            # 遍历所有章节
            for chapter_idx, chapter in enumerate(child_node.report.chapters):
                # 安全地获取章节标题
                chapter_title = getattr(chapter, 'title', f"章节{chapter_idx+1}") if not isinstance(chapter, dict) else chapter.get('title', f"章节{chapter_idx+1}")
                
                print(f"\n📑 正在处理第 {chapter_idx + 1} 章: {chapter_title}")
                
                # 检查章节是否有可视化任务
                if not hasattr(chapter, 'visualization_tasks') or not chapter.visualization_tasks:
                    print(f"⚠️ 章节 {chapter_idx + 1} 没有可视化任务，跳过")
                    continue
                
                # 收集本章节所有图表及其说明
                visualization_tasks = []
                for task in chapter.visualization_tasks:
                    task_info = {
                        'description': task.get('task_description', ''),
                        'charts': []
                    }
                    
                    # 检查章节是否有图表
                    if not hasattr(chapter, 'charts') or not chapter.charts:
                        continue
                        
                    # 查找与任务关联的图表
                    for chart in chapter.charts:
                        if hasattr(chart, 'task_id') and chart.task_id == task.get('task_id'):
                            caption = getattr(chart, 'caption', '无说明文字')
                            task_info['charts'].append({
                                'caption': caption
                            })
                    
                    # 只添加有图表的任务
                    if task_info['charts']:
                        visualization_tasks.append(task_info)
                
                # 如果没有收集到任何有效的可视化任务，跳过此章节
                if not visualization_tasks:
                    print(f"⚠️ 章节 {chapter_idx + 1} 没有有效的可视化任务图表，跳过")
                    continue
                
                # 准备 prompt
                prompt_args = {
                    "QUERY": node.original_query,
                    "CHAPTER_TITLE": chapter_title,
                    "visualization_tasks": json.dumps(visualization_tasks, ensure_ascii=False, indent=2)
                }
                
                prompt = get_prompt("chapter_summary", prompt_args)
                
                # 调用 LLM 生成摘要
                responses = call_openai(prompt, **llm_kwargs)
                if not responses:
                    print(f"❌ 章节 {chapter_idx + 1} 没有收到有效响应")
                    continue
                
                summary = responses[0].strip()
                
                print(f"\n📝 第 {chapter_idx + 1} 章的摘要:")
                print("-" * 50)
                print(summary)
                print("-" * 50)
                
                # 保存摘要到章节
                chapter.summary = summary
                print(f"✅ 已生成第 {chapter_idx + 1} 章的摘要")
                
        except Exception as e:
            print(f"❌ 生成章节摘要时出错: {str(e)}")
            traceback.print_exc()
        
        # 设置最终状态
        child_node.node_type = ReportGenerationState.FINALIZED
        
        return [child_node]
    

    

# 修正 save_chart 方法，将其作为类方法而不是独立函数
class ChartUtils:
    @staticmethod
    def save_chart(node: MCTSNode, chart_data: dict) -> str:
        """保存图表并返回URL"""
        # 获取当前迭代号，添加调试信息
        current_iteration = node.report.current_iteration
        print(f"Debug: 保存图表时的迭代号: {current_iteration}")
        print(f"Debug: 节点类型: {node.node_type}")
        print(f"Debug: 节点深度: {node.depth}")
        
        # 确保使用正确的迭代号
        if current_iteration is None or current_iteration < 1:
            print("警告: current_iteration 无效，使用默认值 1")
            current_iteration = 1
        
        # 构建保存路径
        iteration_dir = os.path.join("storyteller", "output", "iterations", f"iteration_{current_iteration}")
        charts_dir = os.path.join(iteration_dir, "charts")
        os.makedirs(charts_dir, exist_ok=True)
        
        print(f"Debug: 图表将保存到: {charts_dir}")
        
        return charts_dir

# 将字典定义保留为模块级变量
NODE_TYPE_TO_VALID_ACTIONS = {
    ReportGenerationState.EMPTY: [
        Query2Chapters
    ],
    ReportGenerationState.a1: [
        Chapters2Tasks,
    ],
    ReportGenerationState.a2: [
        Tasks2Charts
    ],
    ReportGenerationState.a3: [
        ReviseVis,
        Charts2Captions
    ],
    ReportGenerationState.a4: [
        Charts2Captions
    ],
    ReportGenerationState.a5: [
        Captions2Summaries
    ],
    ReportGenerationState.FINALIZED: []  # 终止状态
}

