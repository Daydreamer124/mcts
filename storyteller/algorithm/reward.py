from functools import lru_cache
import json
import re
from typing import Dict, Any
from storyteller.algorithm.mcts_node import MCTSNode, MCTSNodeType
from storyteller.algorithm.mcts_action import AddColumnAction, ReplaceColumnAction
from storyteller.llm_call.openai_llm import call_openai

class RewardModel:
    def __init__(self, **kwargs):
        pass

    def compute_reward(self, end_node: MCTSNode) -> float:
        raise NotImplementedError

class VisualizationRewardModel(RewardModel):
    def __init__(self, llm_kwargs: Dict[str, Any] = None):
        self.llm_kwargs = llm_kwargs or {"temperature": 0.2, "n": 1}

    def compute_reward(self, end_node: MCTSNode) -> float:
        """
        对可视化图表和描述进行奖励计算。
        """
        parent_node = end_node.parent_node
        if not parent_node:  # 如果是根节点
            return 0.1
            
        action = parent_node.parent_action
        base_reward = 0.0

        # 基础奖励：根据动作类型和当前列数计算
        current_columns_count = len(end_node.current_columns)
        if current_columns_count <= 3:
            base_reward = 0.3  # 列数合理时给予基础奖励
        else:
            base_reward = -0.2  # 列数过多时给予惩罚

        # 动作类型奖励
        if isinstance(action, AddColumnAction):
            if current_columns_count <= 2:  # 列数少时，添加列是好的
                base_reward += 0.2
            else:  # 列数多时，添加列不可取
                base_reward -= 0.3
        elif isinstance(action, ReplaceColumnAction):
            if current_columns_count >= 3:  # 列数多时，替换列是好的
                base_reward += 0.2
        
        # 根据列的组合评估可视化效果
        column_types = end_node._get_column_types()
        measure_count = sum(1 for ctype in column_types.values() if ctype == 'numeric')
        dimension_count = sum(1 for ctype in column_types.values() if ctype == 'categorical')
        
        # 评估列组合的合理性
        if measure_count == 1 and dimension_count == 1:
            base_reward += 0.3  # 适合条形图/折线图
        elif measure_count == 2 and dimension_count == 0:
            base_reward += 0.3  # 适合散点图
        elif measure_count == 1 and dimension_count == 2:
            base_reward += 0.2  # 适合分组条形图
        else:
            base_reward -= 0.2  # 其他组合可能不太合适

        # 计算具体动作的奖励
        action_reward = 0.0
        if isinstance(action, AddColumnAction):
            action_reward = self.reward_for_add_column(parent_node, end_node)
        elif isinstance(action, ReplaceColumnAction):
            action_reward = self.reward_for_replace_column(parent_node, end_node)

        # 综合奖励
        return base_reward + action_reward

    def reward_for_add_column(self, parent_node: MCTSNode, end_node: MCTSNode) -> float:
        """
        如果图表增加列后丰富性和描述质量更高，则给高奖励。
        """
        evaluation_prompt = f"""
        你是一个数据可视化质量评估专家。
        
        【原始问题】：
        {end_node.original_question}

        【之前的图表列】：
        {', '.join(parent_node.current_columns)}

        【新增的列】：
        {end_node.added_column}

        【新增列后的图表描述】：
        {end_node.visualization_description}

        请评估新增列后的图表描述：
        - 是否更清晰或更深入地解答了原始问题？
        - 新增列后的图表是否明显更有价值？

        请仅输出JSON格式：
        ```json
        {{
            "score": 0.85,
            "reasoning": "评估的理由说明..."
        }}
        ```
        """
        reward_score = self._call_llm_for_reward(evaluation_prompt)
        return reward_score

    def reward_for_replace_column(self, parent_node: MCTSNode, end_node: MCTSNode) -> float:
        """
        替换列后图表描述质量与原问题相关性更高则奖励更高。
        """
        evaluation_prompt = f"""
        你是一个数据可视化质量评估专家。
        
        【原始问题】：
        {end_node.original_question}

        【之前的图表列】：
        {', '.join(parent_node.current_columns)}

        【替换列操作】：
        将列 "{end_node.replaced_column}" 替换为 "{end_node.new_column}"

        【替换列后的图表描述】：
        {end_node.visualization_description}

        请评估替换列后的图表描述：
        - 替换后的图表是否更清晰或更深入地解答了原始问题？
        - 替换后的图表是否明显更有价值？

        请仅输出JSON格式：
        ```json
        {{
            "score": 0.85,
            "reasoning": "评估的理由说明..."
        }}
        ```
        """
        reward_score = self._call_llm_for_reward(evaluation_prompt)
        return reward_score

    @lru_cache(maxsize=256)
    def _call_llm_for_reward(self, prompt: str) -> float:
        """
        调用OpenAI API评估Prompt，返回评分（0-1）。
        带缓存机制，相同prompt不会重复调用API。
        """
        responses = call_openai(prompt, **self.llm_kwargs)
        response = responses[0] if responses else ""

        try:
            json_content = re.search(r"```json\n(.*?)```", response, re.DOTALL)
            if json_content:
                parsed_json = json.loads(json_content.group(1))
                score = float(parsed_json.get("score", 0.1))
                score = max(0.0, min(score, 1.0))  # 确保score在[0, 1]
                return score
            else:
                print("未能解析到JSON评分内容，默认给分0.1")
                return 0.1
        except Exception as e:
            print(f"LLM reward 解析错误: {e}，默认给分0.1")
            return 0.1