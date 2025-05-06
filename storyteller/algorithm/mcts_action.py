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
from storyteller.algorithm.utils.universalsc import run_universal_self_consistency  # 导入universalsc功能
from storyteller.algorithm.utils.unified_framework import unified_generation_framework  # 导入统一框架
import time
from tqdm import tqdm
import glob




class DataStorytellingAction:
    def __init__(self, action_id: str, description: str):
        self.action_id = action_id
        self.description = description# 默认的下一个状态
        
        # 添加 MCTS 统计属性
        #self.Q = 0.0  # 累积奖励
        #self.N = 0    # 访问次数
  

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = self
            child_node.depth = node.depth + 1
        
            raise NotImplementedError
        
    
class Query2Chapters(DataStorytellingAction):
    def __init__(self):
        super().__init__("A1", "定义章节结构") 
        self.use_unified_framework = True  # 是否使用统一框架

    def generate_chapter_prompt(self, node, **kwargs):
        """生成章节提示词"""
        query = node.report.clarified_query if node.report.clarified_query else node.report.original_query
        data_context = node.report.data_context
        
        # 使用预设的提示模板
        prompt_args = {
            "QUERY": query,
            "DATA_CONTEXT": data_context
        }
        
        return get_prompt("Query2Chapters", prompt_args)
    
    def apply_chapters(self, node, action, cluster, **kwargs):
        """将章节应用到子节点"""
        try:
            cluster_id = cluster.get("cluster_id", "未知")
            chapters = cluster.get("chapters", [])
            
            if not chapters:
                print(f"⚠️ 聚类 {cluster_id} 没有章节内容，跳过")
                return None
            
            print(f"📘 为聚类 {cluster_id} 应用章节方案")
            print(f"   章节结构: {chapters}")
            
            # 创建子节点
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = action
            child_node.depth = node.depth + 1
            
            # 清空现有章节
            child_node.report.chapters = []
            
            # 添加章节
            for title in chapters:
                child_node.report.add_chapter(Chapter(title=title))
            
            # 设置节点状态
            child_node.node_type = ReportGenerationState.a1
            
            print(f"✅ 成功添加聚类 {cluster_id} 的章节方案")
            return [child_node]
            
        except Exception as e:
            print(f"❌ 应用章节时出错: {str(e)}")
            traceback.print_exc()
            return None

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """
        根据用户查询和数据上下文，使用统一框架生成多样化章节结构
        """
        if self.use_unified_framework:
            return unified_generation_framework(
                node=node,
                action=self,
                llm_kwargs=llm_kwargs,
                action_type="chapters",
                prompt_generator=self.generate_chapter_prompt,
                node_applier=self.apply_chapters,
                n=4
            )
        else:
            # 使用原有方法的实现（保留以便兼容）
            # 使用 clarified_query（如果有）或原始查询
            query = node.report.clarified_query if node.report.clarified_query else node.report.original_query
            data_context = node.report.data_context
            print(data_context)
            # 运行USC流程获取聚类结果
            clusters = run_universal_self_consistency(query, data_context, llm_kwargs, n=4)
            print(f"✅ 完成章节聚类，得到 {len(clusters)} 个聚类")
            
            # 从每个聚类中创建子节点
            nodes = []
            for cluster in clusters:
                cluster_id = cluster.get("cluster_id", "未知")
                chapters = cluster.get("chapters", [])
                
                # 跳过没有章节的聚类
                if not chapters:
                    print(f"⚠️ 聚类 {cluster_id} 没有章节内容，跳过")
                    continue
        
                print(f"📘 为聚类 {cluster_id} 创建子节点")
                print(f"   章节结构: {chapters}")
                
                # 创建子节点
                child_node = copy.deepcopy(node)
                child_node.parent_node = node
                child_node.parent_action = self
                child_node.depth = node.depth + 1
                
                # 清空现有章节
                child_node.report.chapters = []
                
                # 添加章节
                for title in chapters:
                        child_node.report.add_chapter(Chapter(title=title))
                
                # 设置节点状态
                child_node.node_type = ReportGenerationState.a1
                
                # 添加到节点列表
                nodes.append(child_node)
                print(f"✅ 成功添加聚类 {cluster_id} 的章节方案")
        
        return nodes



class Chapters2Tasks(DataStorytellingAction):
    def __init__(self):
        super().__init__("A2", "根据章节方案划分章节任务方案")
        self.use_unified_framework = True  # 是否使用统一框架

    def generate_tasks_prompt(self, node, **kwargs):
        """生成任务提示词"""
        # 获取数据集信息
        data_context = node.report.data_context
        query = node.report.clarified_query if node.report.clarified_query else node.report.original_query
        
        # 构建章节列表
        chapters_list = []
        for i, chapter in enumerate(node.report.chapters):
            # 安全获取标题
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
            
            chapters_list.append(title_text)
        
        # 生成 LLM 提示词
        prompt_args = {
            "QUERY": query,
            "DATA_CONTEXT": data_context,
            "CHAPTERS": json.dumps(chapters_list, ensure_ascii=False)
        }
        
        return get_prompt("Chapters2Tasks", prompt_args)
    
    def apply_tasks(self, node, action, cluster, **kwargs):
        """将任务应用到子节点"""
        try:
            # 创建子节点
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = action
            child_node.depth = node.depth + 1
            
            # 获取聚类中的章节任务
            cluster_id = cluster.get("cluster_id", "未知")
            chapters_info = cluster.get("chapters", [])
            
            if not chapters_info:
                print(f"⚠️ 聚类 {cluster_id} 没有任务内容，跳过")
                return None
            
            print(f"📋 为聚类 {cluster_id} 应用任务方案")
            
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
            
            # 跟踪哪些章节已经分配了任务
            chapters_with_tasks = set()
            
            # 处理每个章节
            for chapter_info in chapters_info:
                raw_title = chapter_info.get("title", "")
                
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
                    
                    # 记录已分配任务的章节
                    chapters_with_tasks.add(chapter_idx)
                    
                    # 打印调试信息
                    print(f"✅ 为章节 {chapter_idx+1} ({chapter.title}) 生成了 {len(tasks)} 个可视化任务")
                else:
                    print(f"❌ 找不到匹配的章节: {title_text}")
            
            # 检查所有章节是否都有任务
            all_chapters_have_tasks = True
            for i, chapter in enumerate(child_node.report.chapters):
                if i not in chapters_with_tasks:
                    print(f"⚠️ 章节 {i+1} ({chapter.title}) 没有任务")
                    all_chapters_have_tasks = False
            
            # 只有当所有章节都有任务时，才返回这个节点
            if all_chapters_have_tasks:
                # 设置节点状态
                child_node.node_type = ReportGenerationState.a2
                print(f"✅ 成功应用聚类 {cluster_id} 的任务方案")
                return [child_node]
            else:
                print(f"⚠️ 聚类 {cluster_id} 的任务方案不完整，跳过")
                return None
                
        except Exception as e:
            print(f"❌ 应用任务时出错: {str(e)}")
            traceback.print_exc()
            return None

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """为每个章节生成多种任务方案"""
        if self.use_unified_framework:
            return unified_generation_framework(
                node=node,
                action=self,
                llm_kwargs=llm_kwargs,
                action_type="tasks",
                prompt_generator=self.generate_tasks_prompt,
                node_applier=self.apply_tasks,
                n=3  # 生成3个不同的任务方案变体
            )
        else:
            # 使用原有方法的实现（保留以便兼容）
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
            self.similarity_threshold = 0.90  # 相似度阈值
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
            #child_node.report.current_iteration += 1
            current_iteration = child_node.report.current_iteration
            print(f"✅ 当前迭代号: {current_iteration}")
            
            # 确定当前迭代号和保存路径
            iteration_dir = os.path.join("storyteller", "output", "iterations", f"iteration_{current_iteration}")
            os.makedirs(iteration_dir, exist_ok=True)
            charts_dir = os.path.join(iteration_dir, "charts")
            os.makedirs(charts_dir, exist_ok=True)
           
            # 创建一个额外的 JSON 配置目录
            json_dir = os.path.join(iteration_dir, "chart_configs")
            os.makedirs(json_dir, exist_ok=True)
             
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
                    #goal = Goal(question=task_id, visualization=chart_type, rationale=description) !!原先是这个
                    goal = Goal(question=task_id, visualization=description, rationale=description)
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
                        model="gpt-4o"
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
                            
                            # 额外生成 Chart.js 配置 JSON 文件
                            try:
                                # 提取图表使用的实际数据
                                # chart_data = self._extract_actual_data(visualization)
                                chart_config = self._extract_chart_config(visualization, task_id, description, df, use_antv=True)
                                
                                # 将提取的实际数据添加到配置中
                                #if chart_data:
                                #    chart_config['data'] = chart_data
                                #    print(f"✓ 成功提取图表实际数据")
                                
                                # 获取 JSON 配置目录
                                json_dir = os.path.join(os.path.dirname(charts_dir), "chart_configs")
                                os.makedirs(json_dir, exist_ok=True)
                                
                                # 保存 JSON 配置
                                json_file_name = f"{file_name}.json"
                                json_path = os.path.join(json_dir, json_file_name)
                                with open(json_path, "w", encoding="utf-8") as f:
                                    json.dump(chart_config, f, ensure_ascii=False, indent=2)
                                print(f"✓ 图表配置 JSON 已保存到: {json_path}")
                            except Exception as e:
                                print(f"⚠️ 保存图表配置 JSON 时出错: {str(e)}")
                                traceback.print_exc()
                                json_path = None
                                
                            # 额外保存图表数据为CSV，以便后续分析
                            try:
                                csv_dir = os.path.join(os.path.dirname(charts_dir), "chart_data")
                                os.makedirs(csv_dir, exist_ok=True)
                                csv_file_name = f"{file_name}.csv"
                                csv_path = os.path.join(csv_dir, csv_file_name)
                                
                                # 尝试从可视化对象中提取实际使用的数据
                                if hasattr(visualization, '_data') and isinstance(visualization._data, pd.DataFrame):
                                    visualization._data.to_csv(csv_path, index=False)
                                    print(f"✓ 图表数据已保存到: {csv_path}")
                                elif hasattr(visualization, 'data') and isinstance(visualization.data, pd.DataFrame):
                                    visualization.data.to_csv(csv_path, index=False)
                                    print(f"✓ 图表数据已保存到: {csv_path}")
                                # else:
                                    # 尝试从代码中提取和分析数据
                                    #last_df_var = self._find_last_dataframe_variable(visualization.code)
                                    #if last_df_var:
                                        # 这里我们无法直接访问代码中的变量
                                        # 所以只能保存一个指示文件，提示chart_config使用什么变量
                                        #with open(csv_path + ".info", "w") as f:
                                        #    f.write(f"Last DataFrame variable: {last_df_var}")
                                        #print(f"✓ 图表数据变量信息已保存: {last_df_var}")
                            except Exception as e:
                                print(f"⚠️ 保存图表数据 CSV 时出错: {str(e)}")
                                traceback.print_exc()
                            
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
                        for vis_task in chapter.visualization_tasks:
                            if vis_task.get('task_id') == task_id:
                                # 确保初始化 visualization_success 字段
                                vis_task['visualization_success'] = False
                                
                                # 新增：保存失败图表的代码（如果有）
                                if hasattr(visualization, 'code'):
                                    # 创建失败图表目录（如果不存在）
                                    failed_code_dir = os.path.join(charts_dir, "failed_code")
                                    os.makedirs(failed_code_dir, exist_ok=True)
                                    
                                    # 保存失败图表代码到文件
                                    code_file_path = os.path.join(failed_code_dir, f"{file_name}_failed.py")
                                    try:
                                        with open(code_file_path, 'w', encoding='utf-8') as f:
                                            f.write(visualization.code)
                                        print(f"✅ 已保存失败图表代码到: {code_file_path}")
                                        
                                        # 在任务中记录代码路径
                                        vis_task['failed_code_path'] = code_file_path
                                    except Exception as e:
                                        print(f"❌ 保存失败图表代码时出错: {str(e)}")
                                
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


    def _extract_chart_config(self, visualization, task_id, description, df, use_antv=False):
        """从可视化代码中提取图表配置
        
        参数:
            visualization: 包含可视化代码的字典
            task_id: 任务ID
            description: 任务描述
            df: 数据DataFrame
            use_antv: 是否使用AntV G2配置（默认为False，使用Chart.js）
            
        返回:
            图表配置字典
        """
        chart_config = {}
        
        try:
            # 确保有可视化代码
            if not hasattr(visualization, 'code'):
                raise ValueError("可视化对象没有代码属性")
            
            code = visualization.code
            print("\n📋 分析可视化代码:")
            print("-" * 50)
            print(code)
            print("-" * 50)
            
            # 打印DataFrame信息，帮助理解数据结构
            print("\n📊 DataFrame信息:")
            print(f"形状: {df.shape}")
            print(f"列名: {df.columns.tolist()}")
            print(f"数据类型:\n{df.dtypes}")
            print("\n前5行数据:")
            print(df.head(5).to_string())
            print("-" * 50)
            
            # 获取数据上下文信息
            data_context = None
            try:
                # 尝试读取数据摘要JSON文件
                json_path = os.path.join("storyteller", "dataset", "data_context.json")
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data_summary = json.load(f)
                        data_context = data_summary.get("dataset_description", "")
                        print(f"✅ 从JSON文件读取到数据上下文: {data_context[:100]}...")
            except Exception as e:
                print(f"⚠️ 读取数据上下文时出错: {str(e)}")
            
            # 导入AST解析器和配置转换函数
            if use_antv:
                from storyteller.algorithm.utils.chart_config_extractor import ChartConfigExtractor, convert_to_antv_config as convert_config
                config_type = "AntV G2"
            else:
                from storyteller.algorithm.utils.chart_config_extractor import ChartConfigExtractor, convert_to_chartjs_config as convert_config
                config_type = "Chart.js"
            
            # 创建提取器并解析代码
            extractor = ChartConfigExtractor()
            ast_config = extractor.extract_from_code(code)
            
            print(f"\n🔍 AST解析结果 (用于{config_type}):")
            for key, value in ast_config.items():
                print(f"- {key}: {value}")
            
            # 如果解析失败，回退到原有的静态分析
            #if "error" in ast_config:
            #    print(f"⚠️ AST解析失败，回退到静态分析: {ast_config['error']}")
            #    return self._extract_chart_config_fallback(visualization, task_id, description, df, use_antv)
            
            # 提取AST配置并修正字段信息
            if "error" not in ast_config:
                # 使用extractor实例直接调用resolve_chart_data，并传入data_context
                try:
                    chart_data = extractor.resolve_chart_data(df, ast_config)
                    print(f"✓ 使用AST解析器的resolve_chart_data方法生成图表数据")
                    # 保存原始代码以便后续处理
                    ast_config["code"] = code
                except Exception as e:
                    print(f"⚠️ 使用resolve_chart_data方法时出错: {e}")
                    chart_data = None
            
            # 转换为目标配置（Chart.js或AntV G2），传入data_context
            chart_config = convert_config(ast_config, df)
            
            # 设置标题
            if not chart_config.get("title") or chart_config["title"] == "Chart":
                chart_config["title"] = description
            
            # 根据图表库类型输出不同的日志信息
            if use_antv:
                print(f"\n✓ 成功生成AntV G2配置:")
                print(f"- 图表类型: {chart_config['type']}")
                print(f"- 图表标题: {chart_config['title']}")
                print(f"- X轴字段: {chart_config['xField']}")
                print(f"- Y轴字段: {chart_config['yField']}")
                print(f"- 数据点数量: {len(chart_config['data'])}")
                series_field = chart_config.get('seriesField', None)
                if series_field:
                    print(f"- 分组字段: {series_field}")
                    print(f"- 是否堆叠: {'是' if chart_config.get('isStack', False) else '否'}")
            else:
                print(f"\n✓ 成功生成Chart.js配置:")
                print(f"- 图表类型: {chart_config['type']}")
                print(f"- 图表标题: {chart_config['title']}")
                print(f"- X轴字段: {chart_config.get('x_field', '')}")
                print(f"- Y轴字段: {chart_config.get('y_field', '')}")
                print(f"- 数据点数量: {len(chart_config['data']['labels'])}")
                print(f"- 数据集数量: {len(chart_config['data']['datasets'])}")
                print(f"- 是否堆叠柱状图: {'是' if chart_config.get('options', {}).get('scales', {}).get('y', {}).get('stacked', False) else '否'}")
            
        except Exception as e:
            print(f"⚠️ 提取图表配置时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 回退到原有方法
            # chart_config = self._extract_chart_config_fallback(visualization, task_id, description, df, use_antv)
        
        return chart_config

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
                    # 检查任务是否是生成成功的或者因相似度跳过的
                    if task.get('visualization_success', False) == True:
                        continue
                        
                    # 检查任务是否因相似度高而被跳过的，如果是则不需要修复
                    if task.get('skipped_due_to_similarity', False) == True:
                        print(f"⚠️ 任务 '{task.get('task_id', '')}' 因相似度过高而被跳过，不需要修复")
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
                        text_gen = llm(provider="openai", model="gpt-4o")
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
                        edit_instruction = "修改图表错误，比如修改为更合适的图表类型，让图表更加美观，清晰"
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

                                
                                # 额外生成 Chart.js 配置 JSON 文件
                                try:
                                    # 借用 Tasks2Charts 类中的方法来提取图表配置
                                    from storyteller.algorithm.mcts_action import Tasks2Charts
                                    tasks2charts = Tasks2Charts()
                                    
                                    # 提取图表使用的实际数据
                                    chart_data = tasks2charts._extract_actual_data(edited_visualization)
                                    chart_config = tasks2charts._extract_chart_config(edited_visualization, task_id, description, df)
                                    
                                    # 将提取的实际数据添加到配置中
                                    if chart_data:
                                        chart_config['data'] = chart_data
                                        print(f"✓ 成功提取图表实际数据")
                                    
                                    # 获取 JSON 配置目录
                                    json_dir = os.path.join(os.path.dirname(chart_dir), "chart_configs")
                                    os.makedirs(json_dir, exist_ok=True)
                                    
                                    # 保存 JSON 配置
                                    json_file_name = f"{task_id}_edited.json"
                                    json_path = os.path.join(json_dir, json_file_name)
                                    with open(json_path, "w", encoding="utf-8") as f:
                                        json.dump(chart_config, f, ensure_ascii=False, indent=2)
                                    print(f"✓ 图表配置 JSON 已保存到: {json_path}")
                                    
                                    # 额外保存图表数据为CSV，以便后续分析
                                    try:
                                        csv_dir = os.path.join(os.path.dirname(chart_dir), "chart_data")
                                        os.makedirs(csv_dir, exist_ok=True)
                                        csv_file_name = f"{task_id}_edited.csv"
                                        csv_path = os.path.join(csv_dir, csv_file_name)
                                        
                                        # 尝试从可视化对象中提取实际使用的数据
                                        if hasattr(edited_visualization, '_data') and isinstance(edited_visualization._data, pd.DataFrame):
                                            edited_visualization._data.to_csv(csv_path, index=False)
                                            print(f"✓ 修改后的图表数据已保存到: {csv_path}")
                                        elif hasattr(edited_visualization, 'data') and isinstance(edited_visualization.data, pd.DataFrame):
                                            edited_visualization.data.to_csv(csv_path, index=False)
                                            print(f"✓ 修改后的图表数据已保存到: {csv_path}")
                                        # else:
                                            # 尝试从代码中提取和分析数据
                                            #last_df_var = tasks2charts._find_last_dataframe_variable(edited_visualization.code)
                                            #if last_df_var:
                                                # 这里我们无法直接访问代码中的变量
                                                # 所以只能保存一个指示文件，提示chart_config使用什么变量
                                                #with open(csv_path + ".info", "w") as f:
                                                #    f.write(f"Last DataFrame variable: {last_df_var}")
                                                #print(f"✓ 修改后的图表数据变量信息已保存: {last_df_var}")
                                    except Exception as e:
                                        print(f"⚠️ 保存修改后的图表数据 CSV 时出错: {str(e)}")
                                        traceback.print_exc()
                                except Exception as e:
                                    print(f"⚠️ 保存图表配置 JSON 时出错: {str(e)}")
                                    traceback.print_exc()
                                    json_path = None

                            # 创建新的图表对象
                            from storyteller.algorithm.mcts_node import Chart
                            edited_chart = Chart(
                                url=edited_chart_path,
                                caption="",  # 使用空字符串作为初始说明
                                chart_type=selected_chart.chart_type,
                                task_id=task_id  # 使用原始任务ID/描述
                            )
                            edited_chart.needs_caption = True  # 设置需要生成说明文字的标志
                           
                            # 添加JSON配置路径属性
                            if 'json_path' in locals() and json_path:
                                edited_chart.json_config_path = json_path
                                print(f"- JSON 配置路径: {json_path}")
                                                        
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

    def call_vision_api(self, prompt, image_base64_list, **kwargs):
        """统一处理视觉API调用，支持单个或多个图像"""
        import os
        import requests
        import json
        
        # 获取环境变量
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        api_key = os.environ.get("OPENAI_API_KEY", "")
        
        # 日志记录
        print(f"🔄 环境变量状态: OPENAI_BASE_URL={base_url}, OPENAI_API_KEY={'已设置' if api_key else '未设置'}")
        
        # 构造完整的API URL
        if base_url.endswith('/chat/completions'):
            url = base_url  # 已经是完整URL
        elif base_url.endswith('/v1'):
            url = f"{base_url}/chat/completions"  # 添加chat/completions端点
        else:
            # 确保URL以斜杠结尾
            if not base_url.endswith('/'):
                base_url += '/'
            url = f"{base_url}v1/chat/completions"  # 添加v1/chat/completions路径
            
        print(f"🔄 使用API URL: {url}")
        
        # 设置请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else ""
        }
        
        # 准备图像内容
        image_contents = []
        for img_base64 in (image_base64_list if isinstance(image_base64_list, list) else [image_base64_list]):
            image_contents.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_base64}"
                }
            })
        
        # 构建消息
        messages = [
            {"role": "system", "content": "You are a data visualization expert."},
            {"role": "user", "content": [{"type": "text", "text": prompt}, *image_contents]}
        ]
        
        # 设置API调用参数
        model = kwargs.get("model", "gpt-4o")
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)
        
        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        print(f"🔄 调用视觉API，模型: {model}, 温度: {temperature}")
        
        # 调用API
        try:
            response = requests.post(url, headers=headers, data=json.dumps(data))
            response_json = response.json()
            
            if 'choices' in response_json and response_json['choices']:
                return response_json['choices'][0]['message']['content'].strip()
            else:
                print(f"❌ API返回错误或无响应: {response_json}")
        except Exception as e:
            print(f"❌ API调用失败: {str(e)}")
            traceback.print_exc()
        
        return None
    
    def generate_chapter_caption_schemes(self, node, chapter, chapter_idx, charts, num_schemes=3, llm_kwargs=None):
        """为单个章节的所有图表生成多套说明方案，具有重试机制"""
        # 过滤出成功生成的图表
        successful_charts = []
        for chart in charts:
            # 查找对应的visualization_task
            chart_task_id = getattr(chart, 'task_id', '')
            task_success = False
            
            # 从可视化任务中查找与图表关联的任务状态
            if hasattr(chapter, 'visualization_tasks'):
                for task in chapter.visualization_tasks:
                    if task.get('task_id') == chart_task_id:
                        task_success = task.get('visualization_success', False)
                        break
            
            # 只添加成功生成的图表
            if task_success:
                successful_charts.append(chart)
        
        # 如果章节内没有成功生成的图表，直接返回空
        if not successful_charts:
            print(f"⚠️ 章节 {chapter_idx+1} 没有成功生成的图表需要处理")
            return []
        
        print(f"\n🔄 为章节 {chapter_idx+1} 生成 {num_schemes} 套说明方案")
        print(f"章节标题: {getattr(chapter, 'title', f'章节{chapter_idx+1}')}")
        print(f"需处理的图表数量: {len(successful_charts)} (从 {len(charts)} 总图表中筛选)")
        
        # 准备图表信息文本和图像
        charts_info = ""
        chart_images = []
        
        for i, chart in enumerate(successful_charts):
            charts_info += f"\n图表{i}:"
            charts_info += f"\n- 类型: {chart.chart_type}"
            charts_info += f"\n- 任务: {chart.task_id}"
            
            # 获取图表图像数据
            image_base64 = self._get_image_base64(chart.url)
            if image_base64:
                chart_images.append(image_base64)
            else:
                print(f"❌ 无法获取图表 {i} 的图像数据")
        
        if not chart_images:
            print("❌ 没有可用的图表图像数据")
            return []
            
        # 实现重试机制
        max_retries = 3
        for retry in range(max_retries):
            try:
                # 使用模板文件生成提示词
                prompt_args = {
                    "QUERY": node.original_query,
                    "CHAPTER_TITLE": getattr(chapter, 'title', f'章节{chapter_idx+1}'),
                    "DATA_CONTEXT": node.report.data_context,
                    "NUM_SCHEMES": str(num_schemes),
                    "CHARTS_INFO": charts_info,
                    "RETRY_NUM": str(retry + 1)  # 告诉模型这是第几次尝试
                }
                
                # 增强提示词
                prompt = get_prompt("chapter_captions", prompt_args)
                if retry > 0:
                    # 对于重试，增加更明确的JSON格式要求
                    prompt += f"\n\n【重要】这是第{retry+1}次尝试，请务必确保返回有效的JSON格式。您的响应必须包含完整的JSON结构，格式如下：\n"
                    prompt += """
{
  "schemes": [
    {
      "scheme_id": 1,
      "captions": [
        {
          "chart_idx": 0,
          "caption": "图表0的说明文字"
        },
        {
          "chart_idx": 1,
          "caption": "图表1的说明文字"
        }
      ]
    },
    {
      "scheme_id": 2,
      "captions": [
        {
          "chart_idx": 0,
          "caption": "另一种图表0的说明文字"
        },
        {
          "chart_idx": 1,
          "caption": "另一种图表1的说明文字"
        }
      ]
    }
  ]
}
"""
                
                # 调用视觉API
                print(f"🔄 正在调用API生成章节 {chapter_idx+1} 的说明方案... (尝试 {retry+1}/{max_retries})")
                # 降低温度，提高确定性
                api_kwargs = llm_kwargs.copy() if llm_kwargs else {}
                api_kwargs['temperature'] = max(0.1, 0.7 - retry * 0.2)  # 逐渐降低温度
                response_text = self.call_vision_api(prompt, chart_images, **api_kwargs)
                
                if not response_text:
                    print(f"❌ 章节 {chapter_idx+1} 没有收到有效响应 (尝试 {retry+1}/{max_retries})")
                    if retry < max_retries - 1:
                        print("将在1秒后重试...")
                        import time
                        time.sleep(1)
                        continue
                    else:
                        return []
                
                # 解析JSON响应
                print(f"🔍 LLM响应片段: {response_text[:200]}...")
                result = self.extract_json_from_text(response_text)
                
                if result and "schemes" in result:
                    schemes = result["schemes"]
                    print(f"✅ 成功为章节 {chapter_idx+1} 生成 {len(schemes)} 套说明方案")
                    return schemes
                
                print(f"❌ 无法解析章节 {chapter_idx+1} 的图表说明方案 (尝试 {retry+1}/{max_retries})")
                if retry < max_retries - 1:
                    print("将在1秒后重试...")
                    import time
                    time.sleep(1)
                else:
                    print("已达到最大重试次数，无法生成有效的说明方案")
                    return []
                    
            except Exception as e:
                print(f"❌ 生成章节图表说明方案出错: {str(e)} (尝试 {retry+1}/{max_retries})")
                traceback.print_exc()
                if retry < max_retries - 1:
                    print("将在1秒后重试...")
                    import time
                    time.sleep(1)
                else:
                    print("已达到最大重试次数，无法生成有效的说明方案")
                    return []
        
        # 所有重试都失败
        return []
    
    def extract_json_from_text(self, text):
        """从LLM响应中提取JSON，具有更强的容错能力"""
        try:
            # 先尝试查找JSON块
            match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
            if match:
                json_str = match.group(1)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON块解析失败: {str(e)}，尝试修复并重新解析")
                    # 尝试修复常见的JSON格式问题
                    json_str = self._fix_json(json_str)
                    return json.loads(json_str)
            
            # 如果没有JSON块，尝试寻找整个文本中的JSON对象
            match = re.search(r'(\{[\s\S]*\})', text)
            if match:
                json_str = match.group(1)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    print(f"⚠️ JSON对象解析失败: {str(e)}，尝试修复并重新解析")
                    # 尝试修复常见的JSON格式问题
                    json_str = self._fix_json(json_str)
                    return json.loads(json_str)
            
            # 如果上述方法都失败，尝试从文本中提取schemes部分
            schemes_match = re.search(r'"schemes"\s*:\s*(\[[\s\S]*?\])', text)
            if schemes_match:
                schemes_str = schemes_match.group(1)
                print(f"✓ 提取到schemes数组，尝试构建完整JSON")
                try:
                    # 构建一个新的JSON
                    new_json = f'{{"schemes": {schemes_str}}}'
                    return json.loads(new_json)
                except json.JSONDecodeError as e:
                    print(f"⚠️ 提取的schemes解析失败: {str(e)}")
            
            # 如果没有找到完整结构，尝试手动提取每个caption
            captions = re.findall(r'(?:chart_idx|图表索引)["\s:]+(\d+)[\s"]*(?:,|\})[\s\S]*?(?:caption|说明文字)["\s:]+([^"]*?)[",$}]', text)
            if captions:
                print(f"✓ 手动提取到 {len(captions)} 个caption条目")
                manual_scheme = {
                    "scheme_id": 1,
                    "captions": []
                }
                
                for chart_idx_str, caption in captions:
                    try:
                        chart_idx = int(chart_idx_str)
                        manual_scheme["captions"].append({
                            "chart_idx": chart_idx,
                            "caption": caption.strip()
                        })
                    except ValueError:
                        pass
                
                if manual_scheme["captions"]:
                    return {"schemes": [manual_scheme]}
            
            return None
        except Exception as e:
            print(f"❌ JSON解析错误: {str(e)}")
            traceback.print_exc()
            return None
    
    def _fix_json(self, json_str):
        """修复常见的JSON格式问题"""
        # 修复缺少逗号的问题
        json_str = re.sub(r'}\s*{', '},{', json_str)
        json_str = re.sub(r']\s*\[', '],[', json_str)
        
        # 修复多余的逗号
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        
        # 确保属性名有引号
        json_str = re.sub(r'([{,]\s*)(\w+)(\s*:)', r'\1"\2"\3', json_str)
        
        # 修复转义问题
        json_str = json_str.replace('\\"', '"').replace('\\\\', '\\')
        
        return json_str
    
    def generate_combined_nodes(self, node, all_chapter_schemes, max_nodes=3):
        """生成子节点组合 - 使用简单策略：全部章节使用第n套方案"""
        if not all_chapter_schemes:
            return []
        
        children_nodes = []
        
        # 计算每个章节最多有几套方案
        max_schemes = max([len(chapter_data["schemes"]) for chapter_data in all_chapter_schemes], default=0)
        
        # 策略：所有章节使用同一套方案编号（全部用方案1，全部用方案2...）
        for scheme_idx in range(min(max_schemes, max_nodes)):
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = self
            child_node.depth = node.depth + 1
            child_node.node_type = ReportGenerationState.a5
            
            caption_applied = False  # 跟踪是否应用了任何说明
            
            # 对每个章节应用相同编号的方案
            for chapter_data in all_chapter_schemes:
                chapter_idx = chapter_data["chapter_idx"]
                schemes = chapter_data["schemes"]
                
                # 如果此章节有对应编号的方案
                if 0 <= scheme_idx < len(schemes):
                    scheme = schemes[scheme_idx]
                    chapter = child_node.report.chapters[chapter_idx]
                    
                    print(f"🔄 为子节点{scheme_idx+1}应用章节{chapter_idx+1}的方案{scheme.get('scheme_id', scheme_idx+1)}")
                    
                    # 应用此方案中的所有图表说明
                    for caption_info in scheme.get("captions", []):
                        chart_idx = caption_info.get("chart_idx")
                        caption = caption_info.get("caption", "")
                        
                    if hasattr(chapter, 'charts') and 0 <= chart_idx < len(chapter.charts):
                        chart = chapter.charts[chart_idx]
                        chart.caption = caption
                        chart.needs_caption = False
                        caption_applied = True
                            
                            # 更新任务状态
                        if hasattr(chapter, 'visualization_tasks'):
                            for task in chapter.visualization_tasks:
                                if task.get('task_id') == chart.task_id:
                                    task['status'] = 'completed'
                                    task['caption_generated'] = True
                                    break
                            
            if caption_applied:  # 只有当应用了说明时才添加节点
                child_node.caption_strategy = f"统一方案{scheme_idx+1}"
                children_nodes.append(child_node)
                print(f"✅ 成功创建子节点 {scheme_idx+1}，使用统一方案 {scheme_idx+1}")
        
        return children_nodes

    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """为图表生成说明文字，按章节处理并生成多个子节点"""
        # 收集需要处理的章节及其图表
        chapters_with_charts = []
        for chapter_idx, chapter in enumerate(node.report.chapters):
            if not hasattr(chapter, 'charts') or not chapter.charts:
                continue
                
            # 收集需要生成说明的图表
            charts_needing_captions = []
            for chart in chapter.charts:
                if not hasattr(chart, 'caption') or not chart.caption:
                    # 查找该图表对应的任务状态
                    chart_task_id = getattr(chart, 'task_id', '')
                    task_success = False
                    
                    # 从可视化任务中查找与图表关联的任务状态
                    if hasattr(chapter, 'visualization_tasks'):
                        for task in chapter.visualization_tasks:
                            if task.get('task_id') == chart_task_id:
                                task_success = task.get('visualization_success', False)
                                break
                # 只处理成功生成的图表
                if task_success:
                    charts_needing_captions.append(chart)
                else:
                    print(f"⚠️ 跳过图表 {chart_task_id}，因为它的生成状态为失败")
            if charts_needing_captions:
                chapters_with_charts.append({
                    "chapter_idx": chapter_idx,
                    "chapter": chapter,
                    "charts": charts_needing_captions
                })
                print(f"✅ 章节 {chapter_idx+1} 有 {len(charts_needing_captions)} 个图表需要生成说明")
        
        if not chapters_with_charts:
            # 没有需要处理的图表，返回原节点
            print("没有需要生成说明的图表，返回原节点")
            node.node_type = ReportGenerationState.a5
            return [node]
        
        # 对每个章节生成多套说明方案
        all_chapter_schemes = []
        for chapter_info in chapters_with_charts:
            chapter_idx = chapter_info["chapter_idx"]
            chapter = chapter_info["chapter"]
            charts = chapter_info["charts"]
            
            # 为该章节所有图表生成多套说明方案
            chapter_schemes = self.generate_chapter_caption_schemes(
                node,
                chapter, 
                chapter_idx,
                charts, 
                num_schemes=3,  # 为每个章节生成3种不同的说明方案
                llm_kwargs=llm_kwargs
            )
            
            if chapter_schemes:
                all_chapter_schemes.append({
                    "chapter_idx": chapter_idx,
                    "schemes": chapter_schemes
                })
                print(f"✅ 章节 {chapter_idx} 成功生成 {len(chapter_schemes)} 套说明方案")
            else:
                print(f"❌ 章节 {chapter_idx} 生成说明方案失败")
        
        # 生成子节点组合 - 使用简单策略：全部章节使用第n套方案
        children_nodes = self.generate_combined_nodes(node, all_chapter_schemes)
        
        if not children_nodes:
            # 如果没有成功生成子节点，创建一个基本节点
            print("❌ 无法生成有效的子节点组合，将返回基本节点")
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = self
            child_node.depth = node.depth + 1
            child_node.node_type = ReportGenerationState.a5
            return [child_node]
        
        print(f"✅ 成功生成 {len(children_nodes)} 个子节点")
        return children_nodes


class Captions2Summaries(DataStorytellingAction):
    def __init__(self):
        super().__init__("A6", "根据每个章节的Caption生成每个章节的总结")
        self.use_unified_framework = True  # 是否使用统一框架
    
    def generate_summary_prompt(self, node, chapter_idx=None, **kwargs):
        """生成章节总结提示词"""
        # 如果指定了章节索引，生成特定章节的提示词
        if chapter_idx is not None and 0 <= chapter_idx < len(node.report.chapters):
            chapter = node.report.chapters[chapter_idx]
            chapter_title = getattr(chapter, 'title', f"章节{chapter_idx+1}") if not isinstance(chapter, dict) else chapter.get('title', f"章节{chapter_idx+1}")
            
            # 收集本章节所有图表及其说明
            visualization_tasks = []
            if hasattr(chapter, 'visualization_tasks'):
                for task in chapter.visualization_tasks:
                    task_info = {
                        'description': task.get('task_description', ''),
                        'charts': []
                    }
                    
                    # 检查章节是否有图表
                    if hasattr(chapter, 'charts') and chapter.charts:
                        # 查找与任务关联的图表
                        for chart in chapter.charts:
                            if hasattr(chart, 'task_id') and chart.task_id == task.get('task_id'):
                                # 检查该图表任务是否成功完成
                                task_success = False
                                for t in chapter.visualization_tasks:
                                    if t.get('task_id') == chart.task_id and t.get('visualization_success', False):
                                        task_success = True
                                        break
                                
                                if task_success:
                                    caption = getattr(chart, 'caption', '无说明文字')
                                    task_info['charts'].append({
                                        'caption': caption
                                    })
                    
                    # 只添加有图表的任务
                    if task_info['charts']:
                        visualization_tasks.append(task_info)
            
            # 准备提示词参数
            prompt_args = {
                "QUERY": node.original_query,
                "CHAPTER_TITLE": chapter_title,
                "visualization_tasks": json.dumps(visualization_tasks, ensure_ascii=False, indent=2)
            }
            
            return get_prompt("chapter_summary", prompt_args)
        
        # 如果没有指定章节，返回基本信息
        return {
            "QUERY": node.report.clarified_query if node.report.clarified_query else node.report.original_query,
            "DATA_CONTEXT": node.report.data_context
        }
    
    def apply_summaries(self, node, action, cluster, **kwargs):
        """将章节总结应用到子节点"""
        # 创建子节点
        child_node = copy.deepcopy(node)
        child_node.parent_node = node
        child_node.parent_action = action
        child_node.depth = node.depth + 1
        
        try:
            # 从聚类中获取每个章节的总结
            if "chapter_summaries" in cluster:
                chapter_summaries = cluster["chapter_summaries"]
                
                # 应用章节总结
                success_count = 0
                for chapter_summary in chapter_summaries:
                    chapter_idx = chapter_summary.get("chapter_idx", -1)
                    summary = chapter_summary.get("summary", "")
                    
                    if 0 <= chapter_idx < len(child_node.report.chapters):
                        chapter = child_node.report.chapters[chapter_idx]
                        chapter.summary = summary
                        success_count += 1
                        print(f"✅ 已应用第 {chapter_idx + 1} 章的总结")
                
                # 设置节点状态
                if success_count > 0:
                    child_node.node_type = ReportGenerationState.FINALIZED
                    return [child_node]
            
            # 如果没有从聚类中获取到总结，尝试自行处理
            print("⚠️ 未从聚类中获取到章节总结，尝试自行处理...")
            success = self.process_all_chapters(child_node, **kwargs)
            
            if success:
                # 设置节点状态
                child_node.node_type = ReportGenerationState.FINALIZED
                return [child_node]
            else:
                print("❌ 处理章节总结失败")
                return None
                
        except Exception as e:
            print(f"❌ 应用章节总结时出错: {str(e)}")
            traceback.print_exc()
            return None
    
    def generate_chapter_summaries(self, node, llm_kwargs, n=3):
        """为每个章节生成多个候选总结"""
        all_chapter_summaries = []
        
        # 遍历所有章节
        for chapter_idx, chapter in enumerate(node.report.chapters):
            # 安全地获取章节标题
            chapter_title = getattr(chapter, 'title', f"章节{chapter_idx+1}") if not isinstance(chapter, dict) else chapter.get('title', f"章节{chapter_idx+1}")
            
            print(f"\n📑 正在为第 {chapter_idx + 1} 章生成多个候选总结...")
            print(f"章节标题: {chapter_title}")
            
            # 检查该章节是否有图表及说明
            has_captions = False
            if hasattr(chapter, 'charts') and chapter.charts:
                for chart in chapter.charts:
                    if hasattr(chart, 'caption') and chart.caption:
                        has_captions = True
                        break
            
            if not has_captions:
                print(f"⚠️ 章节 {chapter_idx + 1} 没有图表或说明文字，跳过")
                continue
                
            # 生成该章节的提示词
            prompt = self.generate_summary_prompt(node, chapter_idx=chapter_idx)
            
            # 收集该章节的多个候选总结
            chapter_summaries = []
            
            for i in range(n):
                # 为每个候选使用不同的温度
                llm_kwargs_temp = llm_kwargs.copy()
                llm_kwargs_temp['temperature'] = 0.3 + i * 0.2  # 0.3, 0.5, 0.7
                
                print(f"🔄 生成第 {chapter_idx + 1} 章的候选总结 {i+1}/{n} (温度: {llm_kwargs_temp['temperature']})")
                
                responses = call_openai(prompt, **llm_kwargs_temp)
                if responses:
                    summary = responses[0].strip()
                    
                    # 收集候选总结
                    chapter_summaries.append({
                        "chapter_idx": chapter_idx,
                        "summary": summary,
                        "variant_id": i
                    })
                    
                    print(f"✅ 成功生成第 {chapter_idx + 1} 章的候选总结 {i+1}")
                else:
                    print(f"❌ 第 {chapter_idx + 1} 章的候选总结 {i+1} 生成失败")
            
            # 如果成功生成了候选总结，添加到列表中
            if chapter_summaries:
                all_chapter_summaries.append({
                    "chapter_idx": chapter_idx,
                    "chapter_title": chapter_title,
                    "candidate_summaries": chapter_summaries
                })
        
        return all_chapter_summaries
    
    def cluster_chapter_summaries(self, all_chapter_summaries, llm_kwargs):
        """对每个章节的候选总结进行聚类，并选择最优总结"""
        if not all_chapter_summaries:
            return []
        
        try:
            # 准备聚类数据
            formatting_data = []
            for chapter_data in all_chapter_summaries:
                chapter_idx = chapter_data["chapter_idx"]
                chapter_title = chapter_data["chapter_title"]
                candidates = chapter_data["candidate_summaries"]
                
                # 转换为聚类所需的格式
                formatted_candidates = [
                    {
                        "index": candidate["variant_id"],
                        "chapter_idx": chapter_idx,
                        "summary": candidate["summary"]
                    }
                    for candidate in candidates
                ]
                
                formatting_data.append({
                    "chapter_idx": chapter_idx,
                    "chapter_title": chapter_title,
                    "candidates": formatted_candidates
                })
            
            # 使用模板文件生成聚类提示词
            prompt_args = {
                "CHAPTER_SUMMARIES_DATA": json.dumps(formatting_data, ensure_ascii=False, indent=2)
            }
            
            clustering_prompt = get_prompt("chapter_summary_clustering", prompt_args)
            
            # 调用 LLM 进行聚类
            print("\n🔍 正在对章节总结进行聚类分析...")
            responses = call_openai(clustering_prompt, **llm_kwargs)
            
            if not responses:
                print("❌ 聚类分析没有收到有效响应")
                return []
            
            # 解析响应
            clustering_response = responses[0]
            
            # 提取 JSON 部分
            import re
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', clustering_response)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = clustering_response
            
            try:
                # 解析 JSON
                clustering_result = json.loads(json_str)
                
                # 检查是否有有效的聚类结果
                if "clusters" in clustering_result and clustering_result["clusters"]:
                    print(f"✅ 成功获取 {len(clustering_result['clusters'])} 个聚类")
                    return clustering_result["clusters"]
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON 解析错误: {str(e)}")
                print(f"❌ 原始响应:\n{clustering_response}")
        
        except Exception as e:
            print(f"❌ 聚类章节总结时出错: {str(e)}")
            traceback.print_exc()
        
        return []
    
    def process_all_chapters(self, node, **kwargs):
        """处理所有章节，为每个章节生成总结"""
        llm_kwargs = kwargs.get("llm_kwargs", {})
        
        try:
            # 如果是使用统一框架并且有多个候选总结
            if self.use_unified_framework:
                # 为每个章节生成多个候选总结
                all_chapter_summaries = self.generate_chapter_summaries(node, llm_kwargs)
                
                if not all_chapter_summaries:
                    print("❌ 没有成功生成任何章节的候选总结")
                    return False
                
                # 对候选总结进行聚类并选择最优总结
                clusters = self.cluster_chapter_summaries(all_chapter_summaries, llm_kwargs)
                
                if not clusters:
                    print("❌ 没有获取到有效的聚类结果")
                    return False
                
                # 应用第一个聚类的结果
                cluster = clusters[0]
                print(f"✅ 应用聚类 {cluster.get('cluster_id', '未知')} 的总结结果")
                
                # 应用章节总结
                chapter_summaries = cluster.get("chapter_summaries", [])
                success_count = 0
                
                for chapter_summary in chapter_summaries:
                    chapter_idx = chapter_summary.get("chapter_idx", -1)
                    summary = chapter_summary.get("summary", "")
                    
                    if 0 <= chapter_idx < len(node.report.chapters):
                        chapter = node.report.chapters[chapter_idx]
                        chapter.summary = summary
                        success_count += 1
                        print(f"✅ 已应用第 {chapter_idx + 1} 章的总结")
                
                return success_count > 0
            else:
                # 原有的逻辑（未使用统一框架）
                success_count = 0

                # 遍历所有章节
                for chapter_idx, chapter in enumerate(node.report.chapters):
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
                    success_count += 1

                return success_count > 0
                
        except Exception as e:
            print(f"❌ 生成章节摘要时出错: {str(e)}")
            traceback.print_exc()
            return False
                
    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        if self.use_unified_framework:
            # 为每个章节生成多个候选总结
            all_chapter_summaries = self.generate_chapter_summaries(node, llm_kwargs)
            
            if not all_chapter_summaries:
                print("❌ 没有成功生成任何章节的候选总结，创建默认节点")
                child_node = copy.deepcopy(node)
                child_node.parent_node = node
                child_node.parent_action = self
                child_node.depth = node.depth + 1
                child_node.node_type = ReportGenerationState.FINALIZED
                return [child_node]
            
            # 对候选总结进行聚类并选择最优总结
            clusters = self.cluster_chapter_summaries(all_chapter_summaries, llm_kwargs)
            
            if not clusters:
                print("❌ 没有获取到有效的聚类结果，创建默认节点")
                child_node = copy.deepcopy(node)
                child_node.parent_node = node
                child_node.parent_action = self
                child_node.depth = node.depth + 1
                child_node.node_type = ReportGenerationState.FINALIZED
                return [child_node]
            
            # 为每个聚类创建一个子节点
            children_nodes = []
            
            for cluster_idx, cluster in enumerate(clusters):
                cluster_id = cluster.get("cluster_id", f"cluster_{cluster_idx+1}")
                
                print(f"🔄 正在为聚类 {cluster_id} 创建子节点")
                
                # 创建子节点
                child_node = copy.deepcopy(node)
                child_node.parent_node = node
                child_node.parent_action = self
                child_node.depth = node.depth + 1
                
                # 应用章节总结
                chapter_summaries = cluster.get("chapter_summaries", [])
                success_count = 0
                
                for chapter_summary in chapter_summaries:
                    chapter_idx = chapter_summary.get("chapter_idx", -1)
                    summary = chapter_summary.get("summary", "")
                    
                    if 0 <= chapter_idx < len(child_node.report.chapters):
                        chapter = child_node.report.chapters[chapter_idx]
                        chapter.summary = summary
                        success_count += 1
                        print(f"✅ 为聚类 {cluster_id} 应用第 {chapter_idx + 1} 章的总结")
                
                if success_count > 0:
                    # 设置节点状态
                    child_node.node_type = ReportGenerationState.a6
                    child_node.summary_cluster_id = cluster_id
                    children_nodes.append(child_node)
                    print(f"✅ 成功创建聚类 {cluster_id} 的子节点")
            
            # 如果没有创建任何子节点，创建一个默认节点
            if not children_nodes:
                print("❌ 没有创建任何有效的子节点，创建默认节点")
                child_node = copy.deepcopy(node)
                child_node.parent_node = node
                child_node.parent_action = self
                child_node.depth = node.depth + 1
                child_node.node_type = ReportGenerationState.a6
                return [child_node]
            
            return children_nodes
        else:
            # 原有实现（保留以便兼容）
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = self
            child_node.depth = node.depth + 1
            
            # 处理所有章节的总结
            self.process_all_chapters(child_node, llm_kwargs=llm_kwargs)
        
        # 设置最终状态
        child_node.node_type = ReportGenerationState.a6
        
        return [child_node]
    
class ReviseNarrativeStrategy(DataStorytellingAction):
    def __init__(self):
        super().__init__("NarrativeStrategy", "调整报告叙事策略，重新排序章节")
        self.use_unified_framework = True  # 使用统一框架
    
    def generate_narrative_prompt(self, node, **kwargs):
        """生成叙事策略提示词"""
        # 准备章节信息
        chapters_info = []
        for i, chapter in enumerate(node.report.chapters):
            chapter_info = {
                "index": i,
                "title": getattr(chapter, 'title', f"章节{i+1}"),
                "summary": getattr(chapter, 'summary', "") if hasattr(chapter, 'summary') else ""
            }
            chapters_info.append(chapter_info)
        
        # 使用模板生成提示词
        prompt_args = {
            "QUERY": node.report.clarified_query if node.report.clarified_query else node.report.original_query,
            "CHAPTERS": json.dumps(chapters_info, ensure_ascii=False, indent=2)
        }
        
        return get_prompt("revise_narrative", prompt_args)
    
    def apply_narrative_strategy(self, node, action, cluster, **kwargs):
        """将叙事策略应用到子节点"""
        try:
            # 创建子节点
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = action
            child_node.depth = node.depth + 1
            
            # 获取叙事策略和章节顺序
            cluster_id = cluster.get("cluster_id", "未知")
            strategy = cluster.get("strategy", "")
            strategy_reason = cluster.get("strategy_reason", "")
            chapter_order = cluster.get("chapter_order", [])
            
            if not chapter_order:
                print(f"⚠️ 聚类 {cluster_id} 没有章节顺序信息，跳过")
                return None
            
            print(f"📘 应用聚类 {cluster_id} 的叙事策略方案")
            print(f"   策略: {strategy}")
            print(f"   原因: {strategy_reason}")
            
            # 验证章节顺序
            if len(chapter_order) != len(node.report.chapters):
                print(f"⚠️ 章节数量不匹配: 期望 {len(node.report.chapters)}, 实际 {len(chapter_order)}")
                return None
                
            # 根据新顺序重排章节
            new_chapters = []
            for chapter_info in chapter_order:
                original_index = chapter_info.get("original_index")
                if not isinstance(original_index, int) or original_index < 0 or original_index >= len(node.report.chapters):
                    print(f"⚠️ 无效的章节索引: {original_index}")
                    continue
                
                new_chapters.append(copy.deepcopy(node.report.chapters[original_index]))
                print(f"   - 移动章节 '{chapter_info.get('title', '')}' 到新位置")
                print(f"     原因: {chapter_info.get('reason', '未提供')}")
            
            # 如果没有成功重排所有章节，跳过此聚类
            if len(new_chapters) != len(node.report.chapters):
                print(f"⚠️ 章节重排不完整，跳过此聚类")
                return None
            
            # 更新报告的章节顺序和叙事策略
            child_node.report.chapters = new_chapters
            child_node.report.narrative_strategy = {
                "strategy": strategy,
                "strategy_reason": strategy_reason,
                "cluster_id": cluster_id
            }
            
            # 设置节点状态
            child_node.node_type = ReportGenerationState.REVISECHAPTERSORDERS
            
            print(f"✅ 成功应用聚类 {cluster_id} 的叙事策略方案")
            return [child_node]
            
        except Exception as e:
            print(f"❌ 应用叙事策略时出错: {str(e)}")
            traceback.print_exc()
            return None
    
    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """生成多个叙事策略方案并聚类选择最优方案"""
        return unified_generation_framework(
            node=node,
            action=self,
            llm_kwargs=llm_kwargs,
            action_type="narrative",
            prompt_generator=self.generate_narrative_prompt,
            node_applier=self.apply_narrative_strategy,
            n=3  # 生成3个不同的叙事策略方案
        )



class TransitionAction(DataStorytellingAction):
    def __init__(self):
        super().__init__("Transition", "添加章节间过渡文本，提高报告连贯性")
        self.use_unified_framework = True  # 使用统一框架
    
    def generate_transition_prompt(self, node, **kwargs):
        """生成过渡文本提示词"""
        # 准备章节信息
        chapters_info = []
        for i, chapter in enumerate(node.report.chapters):
            chapter_info = {
                "index": i,
                "title": getattr(chapter, 'title', f"章节{i+1}"),
                "summary": getattr(chapter, 'summary', "") if hasattr(chapter, 'summary') else "",
                "charts_captions": [
                    getattr(chart, 'caption', "") for chart in getattr(chapter, 'charts', [])
                ]
            }
            chapters_info.append(chapter_info)
        
        # 使用模板生成提示词
        prompt_args = {
            "QUERY": node.report.clarified_query if node.report.clarified_query else node.report.original_query,
            "CHAPTERS": json.dumps(chapters_info, ensure_ascii=False, indent=2),
            "NARRATIVE_STRATEGY": json.dumps(getattr(node.report, 'narrative_strategy', {}), ensure_ascii=False, indent=2)
        }
        
        return get_prompt("add_transitions", prompt_args)
    
    def apply_transitions(self, node, action, cluster, **kwargs):
        """将过渡文本应用到子节点"""
        try:
            # 创建子节点
            child_node = copy.deepcopy(node)
            child_node.parent_node = node
            child_node.parent_action = action
            child_node.depth = node.depth + 1
            
            # 获取过渡文本方案
            cluster_id = cluster.get("cluster_id", "未知")
            transitions = cluster.get("transitions", [])
            
            if not transitions:
                print(f"⚠️ 聚类 {cluster_id} 没有过渡文本信息，跳过")
                return None
            
            print(f"📝 应用聚类 {cluster_id} 的过渡文本方案")
            
            # 应用过渡文本
            success_count = 0
            for transition in transitions:
                chapter_idx = transition.get("chapter_idx")
                transition_text = transition.get("transition_text", "")
                
                if not isinstance(chapter_idx, int) or chapter_idx < 0 or chapter_idx >= len(child_node.report.chapters):
                    print(f"⚠️ 无效的章节索引: {chapter_idx}")
                    continue
                
                # 添加过渡文本到章节
                chapter = child_node.report.chapters[chapter_idx]
                if not hasattr(chapter, 'transition'):
                    chapter.transition = ""
                
                chapter.transition = transition_text
                success_count += 1
                print(f"   ✅ 为第 {chapter_idx + 1} 章添加过渡文本")
            
            # 如果没有成功添加任何过渡文本，跳过此聚类
            if success_count == 0:
                print(f"⚠️ 没有成功添加任何过渡文本，跳过此聚类")
                return None
            
            # 设置节点状态
            child_node.node_type = ReportGenerationState.FINALIZED
            
            print(f"✅ 成功应用聚类 {cluster_id} 的过渡文本方案，共 {success_count} 个过渡")
            return [child_node]
            
        except Exception as e:
            print(f"❌ 应用过渡文本时出错: {str(e)}")
            traceback.print_exc()
            return None
    
    def create_children_nodes(self, node: "MCTSNode", llm_kwargs: Dict[str, Any]) -> List["MCTSNode"]:
        """生成多个过渡文本方案并聚类选择最优方案"""
        return unified_generation_framework(
            node=node,
            action=self,
            llm_kwargs=llm_kwargs,
            action_type="transition",
            prompt_generator=self.generate_transition_prompt,
            node_applier=self.apply_transitions,
            n=3  # 生成3个不同的过渡文本方案
        )

    

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

    def get_current_iteration_dir(self):
        """获取当前迭代的输出目录"""
        try:
            # 检查是否有当前迭代目录属性
            if hasattr(self, 'current_iteration_dir') and self.current_iteration_dir:
                return self.current_iteration_dir
            
            # 检查是否有输出根目录属性
            if hasattr(self, 'output_dir') and self.output_dir:
                # 找到最新的迭代目录
                iteration_dirs = glob.glob(os.path.join(self.output_dir, "iteration_*"))
                if iteration_dirs:
                    # 按创建时间排序，获取最新的
                    latest_dir = max(iteration_dirs, key=os.path.getctime)
                    return latest_dir
            
            # 如果没有设置输出目录，使用默认的输出目录
            default_output_dir = os.path.join("output", "mcts")
            os.makedirs(default_output_dir, exist_ok=True)
            
            # 查找最新的迭代目录
            iteration_dirs = glob.glob(os.path.join(default_output_dir, "iteration_*"))
            if iteration_dirs:
                latest_dir = max(iteration_dirs, key=os.path.getctime)
                return latest_dir
            
            # 如果没有找到迭代目录，创建一个新的
            new_dir = os.path.join(default_output_dir, f"iteration_{int(time.time())}")
            os.makedirs(new_dir, exist_ok=True)
            return new_dir
            
        except Exception as e:
            print(f"⚠️ 获取当前迭代目录时出错: {str(e)}")
            # 返回临时目录
            temp_dir = os.path.join("output", "temp_charts")
            os.makedirs(temp_dir, exist_ok=True)
            return temp_dir




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
        Captions2Summaries,
    ],
    ReportGenerationState.a6: [
        ReviseNarrativeStrategy,
        TransitionAction
    ],
    ReportGenerationState.REVISECHAPTERSORDERS: [
        TransitionAction
    ], 
    ReportGenerationState.FINALIZED: []  # 终止状态，添加过渡后的最终状态
}



