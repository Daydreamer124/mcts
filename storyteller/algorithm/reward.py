import math
from typing import Dict, Any
from storyteller.algorithm.mcts_node import MCTSNode, ReportGenerationState
from storyteller.algorithm.evaluator import evaluate_report
from storyteller.algorithm.utils.html2image import convert_html_to_image
import base64

class StorytellingRewardModel:
    def __init__(self, llm_kwargs: Dict[str, Any] = None):
        """
        数据故事 MCTS 奖励函数
        
        参数:
            llm_kwargs: LLM调用参数
        """
        self.llm_kwargs = llm_kwargs or {}
        # 添加记录最后一次评分的属性
        self.last_base_reward = 0.0
        self.last_quality_reward = 0.0
        self.last_extra_reward = 0.0

    def compute_reward(self, node: MCTSNode, html_path: str, image_path: str) -> float:
        """计算节点的奖励值"""
        # 基础奖励
        base_reward = self._compute_base_reward(node)
        self.last_base_reward = base_reward
        
        # 进阶奖励 - 确保能看到图表的报告质量评估
        quality_reward = self._compute_quality_reward(node, html_path, image_path)
        self.last_quality_reward = quality_reward
        
        # 额外奖励
        extra_reward = self._compute_extra_reward(node)
        self.last_extra_reward = extra_reward
        
        # 输出详细评分信息，帮助调试
        print(f"📊 评分明细 - 基础: {base_reward:.2f}, 质量: {quality_reward:.2f}, 额外: {extra_reward:.2f}")
        
        return base_reward + quality_reward + extra_reward
        
    def _compute_base_reward(self, node: MCTSNode) -> float:
        """
        计算基础奖励（满分100分）
        """
        reward = 0.0
        report = node.report
        
        # 1. 章节数量检查（20分）
        num_chapters = len(report.chapters)
        if 3 <= num_chapters <= 6:
            reward += 20
        else:
            reward += max(0, 20 - abs(4 - num_chapters) * 5)  # 每偏离1个章节扣5分

        # 2. 章节完成度（30分）
        if num_chapters > 0:
            completed_ratio = sum(1 for chapter in report.chapters if chapter.all_tasks_completed()) / num_chapters
            reward += completed_ratio * 30

        # 3. 可视化完整度（30分）
        total_tasks = sum(len(chapter.visualization_tasks) for chapter in report.chapters)
        if total_tasks > 0:
            completed_viz = sum(len(chapter.charts) for chapter in report.chapters)
            reward += min(completed_viz / total_tasks * 30, 30)

        # 4. 摘要完整度（20分）
        if num_chapters > 0:
            summary_ratio = sum(1 for chapter in report.chapters if chapter.summary) / num_chapters
            reward += summary_ratio * 20
        
        return reward
        
    def _compute_quality_reward(self, node: MCTSNode, html_path: str, image_path: str) -> float:
        """计算质量奖励（0-10分）"""
        try:
            # 如果报告未完成，返回基础分数
            if node.node_type != ReportGenerationState.FINALIZED:
                return 5.0
                
            # 准备评估所需参数
            dataset_context = node.report.data_context or ""
            query = node.report.original_query
            
            # 读取HTML内容
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
                
            # 读取图片并转为base64
            with open(image_path, 'rb') as f:
                image_base64 = base64.b64encode(f.read()).decode()
            
            # 调用评估函数
            quality_score = evaluate_report(
                dataset_context=dataset_context,
                query=query,
                html_report=html_content,
                report_image=image_base64,
                llm_kwargs=self.llm_kwargs
            )
            
            return quality_score
            
        except Exception as e:
            print(f"❌ 质量评估出错: {str(e)}")
            return 5.0
            
    def _generate_html_report(self, node: MCTSNode) -> str:
        """生成 HTML 格式的报告"""
        # TODO: 实现 HTML 报告生成逻辑
        # 可以调用 mcts_runner.py 中的相关函数
        return str(node.report)  # 临时返回报告的字符串表示