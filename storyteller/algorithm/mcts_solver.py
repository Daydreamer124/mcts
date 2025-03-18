from storyteller.algorithm.mcts_node import MCTSNode, MCTSNodeType
from storyteller.algorithm.mcts_action import get_valid_action_space_for_node
from storyteller.algorithm.reward import VisualizationRewardModel
from storyteller.runner.visualization_task import VisualizationTask
from storyteller.algorithm.reward import VisualizationRewardModel
import random
import math
from pathlib import Path

class VisualizationMCTSSolver:
    def __init__(self, task: VisualizationTask,
                 dataset_path: str,
                 dataset_context_path: str,
                 save_root_dir: str,
                 max_rollout_steps: int,
                 max_depth: int,
                 exploration_constant: float,
                 llm_kwargs: dict):
        
        self.task = task
        self.dataset_path = dataset_path
        self.dataset_context_path = dataset_context_path
        self.max_rollout_steps = max_rollout_steps
        self.max_depth = max_depth
        self.exploration_constant = exploration_constant
        self.llm_kwargs = llm_kwargs
        self.reward_model = VisualizationRewardModel(llm_kwargs=self.llm_kwargs)
        self.save_root_dir = save_root_dir

    def select(self, node: MCTSNode) -> MCTSNode:
        current = node
        while current.children:
            if any(child.N == 0 for child in current.children):
                return next(child for child in current.children if child.N == 0)
            current = max(current.children, key=lambda c: (c.Q / c.N) + self.exploration_constant * math.sqrt(math.log(current.N) / c.N))
        return current

    def expand(self, node: MCTSNode):
        valid_actions = get_valid_action_space_for_node(node)
        for action in valid_actions:
            child_nodes = action.create_children_nodes(node, self.llm_kwargs)
            node.children.extend(child_nodes)

    def simulate(self, node: MCTSNode) -> MCTSNode:
        current = node
        # 只要不是终止节点就继续模拟
        while not current.is_terminal():
            self.expand(current)
            if current.children:
                current = random.choice(current.children)
            else:
                break
        
        # 不再强制设置为终止节点
        # if not current.is_terminal():
        #     current.node_type = MCTSNodeType.END
        
        return current

    def backpropagate(self, node: MCTSNode):
        reward = self.reward_model.compute_reward(node)
        current = node
        while current:
            current.N += 1
            current.Q += reward
            current = current.parent_node

    def generate_markdown_report(self, final_node: MCTSNode) -> str:
        sections = [n.report_markdown_content for n in final_node.path_nodes if n.report_markdown_content]
        return "# 数据可视化分析报告\n\n" + "\n---\n".join(sections)

    def solve(self):
        root_node = MCTSNode(
            node_type=MCTSNodeType.ROOT,
            parent_node=None,
            parent_action=None,
            depth=0,
            current_columns=self.task.selected_columns,
            candidate_columns=self.task.candidate_columns,
            dataset_path=self.dataset_path,
            dataset_context_path=self.dataset_context_path,
            original_question=self.task.question,
            hint=self.task.hint,
            llm_kwargs=self.llm_kwargs
        )

        root_node.path_nodes = [root_node]

        for step in range(self.max_rollout_steps):
            print(f"[Step {step+1}/{self.max_rollout_steps}] 执行MCTS迭代...")
            
            leaf_node = self.select(root_node)
            if not leaf_node.is_terminal():
                self.expand(leaf_node)
                if leaf_node.children:
                    leaf_node = random.choice(leaf_node.children)

            simulation_node = self.simulate(leaf_node)
            self.backpropagate(simulation_node)

        # 修改这里：找到整个树中得分最高的路径
        def find_best_path(node: MCTSNode) -> MCTSNode:
            if not node.children:
                return node
            
            best_child = max(node.children, key=lambda n: n.Q / n.N if n.N else float('-inf'))
            return find_best_path(best_child)

        best_final_node = find_best_path(root_node)
        return best_final_node