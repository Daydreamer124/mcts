from typing import List, Optional, Dict, Any, Union, TYPE_CHECKING
from copy import deepcopy
from enum import Enum

# 条件导入，只在类型检查时导入
if TYPE_CHECKING:
    from .mcts_action import DataStorytellingAction

class ReportGenerationState(Enum):
    EMPTY = "Empty"  # 初始状态
    CHAPTER_DEFINED = "Chapter-Defined"  # 已定义章节结构
    CHAPTER_PARTIALLY_COMPLETED = "Chapter-Partially-Completed"  # 部分章节内容生成
    CHAPTER_COMPLETED = "Chapter-Completed"  # 单个章节完成
    CONTENT_COMPLETED = "Content-Completed"  # 所有章节内容已生成
    OPTIMIZED = "Optimized"  # 整体报告优化完成
    FINALIZED = "Finalized"  # 最终报告生成完成，终止状态


# Chart 单个图表
class Chart:
    def __init__(self,
                url: str, 
                caption: str,
                chart_position: str = "center"):
        """
        初始化图表对象
        
        参数:
            url: 图表的URL地址
            caption: 图表的说明文字
            chart_position: 图表在页面中的位置，默认为居中
        """
        self.type = "chart"  # 类型标识，表明这是单个图表
        self.url = url  # 存储图表的URL
        self.caption = caption  # 存储图表的说明文字
        self.chart_position = chart_position  # 图表在报告中的位置

    def to_dict(self):
        """
        将图表对象转换为字典格式，便于JSON序列化
        
        返回:
            包含图表信息的字典
        """
        return {
            "type": self.type,
            "url": self.url,
            "chart_position": self.chart_position,
            "caption": self.caption
        }

# ChartGroup 多个Chart组合
class ChartGroup:
    def __init__(self, 
                 charts_list: List[Chart], 
                 caption: Optional[str] = None, 
                 chart_position: str = "side-by-side", 
                 caption_position: str = "below"):
        """
        初始化图表组合对象
        
        参数:
            charts_list: 图表对象列表
            caption: 整个图表组的共享说明文字，可选
        """
        self.type = "chart_group"
        self.charts_list = charts_list
        self.caption = caption
        self.chart_position = chart_position

    def to_dict(self):
        """
        将图表组合对象转换为字典格式，便于JSON序列化
        
        返回:
            包含图表组合信息的字典
        """
        return {
            "type": self.type,
            "charts_list": [chart.to_dict() for chart in self.charts_list],  # 将每个图表也转换为字典
            "caption": self.caption,
            "chart_position": self.chart_position
        }

# Chapter 章节
class Chapter:
    def __init__(self, title: str, summary: Optional[str] = None):
        """
        初始化章节对象
        
        参数:
            title: 章节标题
            summary: 章节摘要，可选
        """
        self.title = title  # 存储章节标题
        self.summary = summary  # 存储章节摘要
        self.charts: List[Union[Chart, ChartGroup]] = []  # 初始化空的图表/图表组合列表
        self.visualization_tasks = []  # 可视化任务列表
        self.tasks_status = {}  # 任务状态字典，用于跟踪任务的完成状态
        
    def add_chart(self, chart: Chart):
        """
        向章节添加单个图表
        
        参数:
            chart: 要添加的图表对象
        """
        self.charts.append(chart)  # 将图表添加到列表中

    def add_chart_group(self, chart_group: ChartGroup):
        """
        向章节添加图表组合
        
        参数:
            chart_group: 要添加的图表组合对象
        """
        self.charts.append(chart_group)  # 将图表组合添加到列表中
        
    def initialize_tasks_status(self):
        """初始化所有可视化任务的状态为 'pending'"""
        if hasattr(self, 'visualization_tasks'):
            for i, task in enumerate(self.visualization_tasks):
                task_id = task.get('task_id', f"task_{i+1}")
                self.tasks_status[task_id] = {
                    "task": task,
                    "status": "pending"  # 可能的状态: pending, in_progress, completed
                }
                
    def get_next_pending_task(self):
        """获取下一个待处理的任务"""
        for task_id, task_info in self.tasks_status.items():
            if task_info["status"] == "pending":
                return task_id, task_info["task"]
        return None, None
        
    def mark_task_in_progress(self, task_id):
        """将任务标记为正在处理"""
        if task_id in self.tasks_status:
            self.tasks_status[task_id]["status"] = "in_progress"
            
    def mark_task_completed(self, task_id):
        """将任务标记为已完成"""
        if task_id in self.tasks_status:
            self.tasks_status[task_id]["status"] = "completed"
            
    def all_tasks_completed(self):
        """检查是否所有任务都已完成"""
        return all(task_info["status"] == "completed" for task_info in self.tasks_status.values())

    def to_dict(self):
        """
        将章节对象转换为字典格式，便于JSON序列化
        
        返回:
            包含章节信息的字典
        """
        return {
            "title": self.title,
            "summary": self.summary,
            "charts": [chart.to_dict() for chart in self.charts]  # 将每个图表/图表组合也转换为字典
        }

# Report 完整报告
class Report:
    def __init__(self, 
                 original_query: str,  # 原始查询
                 dataset_path: str,    # 数据集路径
                 data_context: str = "",   # 数据摘要（可选）
                 clarified_query: str = "", # 澄清后的查询（可选）
                 dataset_description: str = "", # 数据描述（可选）
                 task_list: List[str] = None, # 任务列表（可选）
                 narrative_strategy: str = "data-driven",  # 叙事策略
                 layout_strategy: str = "thematic",        # 布局策略
                 chapters: Optional[List[Chapter]] = None): # 章节列表
        """
        初始化报告对象
        
        参数:
            original_query: 原始用户查询
            dataset_path: 数据集路径
            data_context: 数据摘要
            clarified_query: 澄清后的查询
            data_description: 数据描述
            task_list: 任务列表
            narrative_strategy: 叙事策略
            layout_strategy: 布局策略
            chapters: 章节列表
        """
        self.original_query = original_query  # 存储原始查询
        self.dataset_path = dataset_path      # 存储数据集路径
        self.data_context = data_context      # 存储数据摘要
        self.clarified_query = clarified_query  # 存储澄清后的查询
        self.dataset_description = dataset_description  # 存储数据描述
        self.task_list = task_list if task_list else []  # 存储任务列表
        self.narrative_strategy = narrative_strategy  # 存储叙事策略
        self.layout_strategy = layout_strategy        # 存储布局策略
        self.chapters = chapters if chapters else []  # 存储章节列表
        self.full_column_names = []  # 完整列名（由 action 生成）
        
    def add_chapter(self, chapter: Chapter) -> None:
        """
        向报告添加章节
        
        参数:
            chapter: 要添加的章节对象
        """
        self.chapters.append(chapter)  # 将章节添加到列表中
        
    def get_chapter_by_title(self, title: str) -> Optional[Chapter]:
        """
        根据标题获取章节
        
        参数:
            title: 章节标题
            
        返回:
            找到的章节对象，如果没找到则返回None
        """
        for chapter in self.chapters:
            if chapter.title == title:
                return chapter
        return None
        
    def get_chapter_titles(self) -> List[str]:
        """获取所有章节标题"""
        return [chapter.title for chapter in self.chapters]
        
    def get_chart_count(self) -> int:
        """获取报告中的图表总数"""
        return sum(len(chapter.charts) for chapter in self.chapters)

    def to_dict(self) -> Dict[str, Any]:
        """
        将报告对象转换为字典格式，便于JSON序列化
        
        返回:
            包含报告信息的字典
        """
        return {
            "original_query": self.original_query,
            "data_context": self.data_context,
            "clarified_query": self.clarified_query,
            "dataset_description": self.dataset_description,
            "task_list": self.task_list,
            "dataset_path": self.dataset_path,
            "narrative_strategy": self.narrative_strategy,
            "layout_strategy": self.layout_strategy,
            "chapters": [chapter.to_dict() for chapter in self.chapters],  # 将每个章节也转换为字典
        }
        
    def __str__(self) -> str:
        """字符串表示"""
        return f"Report(query='{self.original_query}', chapters={len(self.chapters)})"

# MCTSNode 类定义
class MCTSNode:
    def __init__(self, 
                 node_type: str,                              # 节点类型/状态
                 parent_node: Optional["MCTSNode"] = None,    # 父节点
                 parent_action: Optional["DataStorytellingAction"] = None,  # 父动作
                 depth: int = 0,                              # 节点深度
                 report: Optional[Report] = None,             # 报告对象
                 original_query: str = "",                    # 原始查询
                 llm_kwargs: Optional[Dict[str, Any]] = None): # 语言模型参数
        """
        初始化MCTS节点，代表报告生成的一个状态
        
        参数:
            node_type: 节点类型，表示报告生成的阶段
            parent_node: 父节点，表示前一个状态
            parent_action: 从父节点到当前节点的动作
            depth: 节点在树中的深度
            report: 当前节点的报告对象
            original_query: 原始查询
            llm_kwargs: 语言模型参数
        """
        self.node_type = node_type        # 存储节点类型
        self.parent_node = parent_node    # 存储父节点
        self.parent_action = parent_action # 存储父动作
        self.depth = depth                # 存储节点深度

        # 当前节点所代表的报告对象
        if report:
            # 如果提供了报告对象，则深拷贝它
            self.report = deepcopy(report)
        elif parent_node:
            # 如果没有提供报告对象但有父节点，则从父节点复制报告对象
            self.report = deepcopy(parent_node.report)
        else:
            # 如果既没有报告对象也没有父节点，则抛出错误
            raise ValueError("Either report or parent_node.report must be provided.")

        self.original_query = original_query  # 存储原始查询
        self.llm_kwargs = llm_kwargs if llm_kwargs else {}  # 存储语言模型参数，如果没有提供则初始化为空字典

        self.children: List["MCTSNode"] = []  # 初始化空的子节点列表

        # MCTS算法统计信息
        self.Q = 0.0  # 累积奖励值（节点质量）
        self.N = 0    # 节点访问次数
        
    def add_child(self, child_node: "MCTSNode") -> None:
        """添加子节点"""
        self.children.append(child_node)
        
    def get_chapter_count(self) -> int:
        """获取报告中的章节数量"""
        return len(self.report.chapters)
        
    def get_chart_count(self) -> int:
        """获取报告中的图表总数"""
        return sum(len(chapter.charts) for chapter in self.report.chapters)
    
    def get_report_summary(self) -> Dict[str, Any]:
        """获取报告摘要信息"""
        return {
            "query": self.original_query,
            "chapter_count": self.get_chapter_count(),
            "chart_count": self.get_chart_count(),
            "node_type": self.node_type,
            "depth": self.depth
        }

    def expand(self, action_space: List["DataStorytellingAction"]):
        """
        扩展当前节点，生成子节点
        
        参数:
            action_space: 可用动作列表
        """
        # 如果已经有子节点，则不再扩展
        if self.children:
            return

        # 对每个可用动作，创建一个子节点
        for action in action_space:
            # 复制当前报告状态
            child_report = deepcopy(self.report)
            # 执行动作，修改报告状态
            action.execute(child_report=child_report, llm_kwargs=self.llm_kwargs)
            # 创建子节点
            child_node = MCTSNode(
                node_type=action.next_node_type,  # 下一个节点类型
                parent_node=self,                # 父节点为当前节点
                parent_action=action,            # 父动作为当前动作
                depth=self.depth + 1,            # 深度加1
                report=child_report,             # 报告状态为修改后的状态
                original_query=self.original_query, # 原始查询保持不变
                llm_kwargs=self.llm_kwargs       # 语言模型参数保持不变
            )
            # 将子节点添加到子节点列表
            self.children.append(child_node)

    def is_terminal(self):
        """
        判断是否为终止节点
        
        返回:
            如果节点类型为"END"，则返回True，否则返回False
        """
        return self.node_type == "END"
        
    def __str__(self) -> str:
        """字符串表示"""
        return f"MCTSNode(type={self.node_type}, depth={self.depth}, chapters={self.get_chapter_count()})"
        
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典表示"""
        return {
            "node_type": self.node_type,
            "depth": self.depth,
            "report": self.report.to_dict(),
            "children_count": len(self.children),
            "Q": self.Q,
            "N": self.N
        } 