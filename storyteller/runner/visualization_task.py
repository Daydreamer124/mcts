from typing import List, Optional

class VisualizationTask:
    def __init__(self,
                 task_id: str,                          # 每个任务的唯一标识符
                 question: str,                          # 用户提出的开放性问题
                 hint: Optional[str] = "",               # 提示信息（可选）
                 selected_columns: Optional[List[str]] = None,   # 初始图表中已有的列
                 candidate_columns: Optional[List[str]] = None, # 可用于图表分析的候选列
                 initial_visualization_type: Optional[str] = None, # 初始图表类型 (如折线图、柱状图)
                 ):
        self.task_id = task_id
        self.question = question
        self.hint = hint if hint else ""
        self.selected_columns = selected_columns if selected_columns else []
        self.candidate_columns = candidate_columns if candidate_columns else []
        self.initial_visualization_type = initial_visualization_type
        self.initial_data_query = None