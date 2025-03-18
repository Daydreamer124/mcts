from pathlib import Path
from typing import Union, Dict, Any
import yaml
import json
import traceback
from storyteller.algorithm.mcts_solver import VisualizationMCTSSolver
from storyteller.runner.visualization_task import VisualizationTask
from storyteller.algorithm.mcts_node import MCTSNodeType

class VisualizationRunner:
    def __init__(self, config_path: str):
        """
        初始化 VisualizationRunner
        Args:
            config_path: YAML 配置文件路径
        """
        # 加载配置文件
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        # 创建保存结果的目录
        Path(self.config["save_root_dir"]).mkdir(parents=True, exist_ok=True)

    def run_task(self, task: VisualizationTask):
        """运行一个可视化任务"""
        try:
            solver = VisualizationMCTSSolver(
                task=task,
                dataset_path=self.config["dataset_path"],
                dataset_context_path=self.config["dataset_context_path"],
                save_root_dir=self.config["save_root_dir"],
                max_rollout_steps=self.config["max_rollout_steps"],
                max_depth=self.config["max_depth"],
                exploration_constant=self.config["exploration_constant"],
                llm_kwargs=self.config["llm_kwargs"]
            )

            best_node = solver.solve()
            print(f"\n✅ 任务 {task.task_id} 已成功执行完成！")
            print("\n最终决策路径：")
            
            # 打印决策路径
            for node in best_node.path_nodes:
                if node.node_type == MCTSNodeType.ADD_COLUMN:
                    print(f"\n📊 添加列: {node.added_column}")
                    print(f"- 分析目的: {node.visualization_purpose}")
                    print(f"- 分析理由: {node.column_reasoning}")
                elif node.node_type == MCTSNodeType.REPLACE_COLUMN:
                    print(f"\n🔄 替换列: {node.replaced_column} -> {node.new_column}")
                    print(f"- 替换目的: {node.visualization_purpose}")
                    print(f"- 替换理由: {node.replace_reasoning}")
            
            print("\n最终选择的列：")
            print(f"📈 {', '.join(best_node.current_columns)}")
            
            return best_node
            
        except Exception as e:
            print(f"❌ 任务 {task.task_id} 执行出错: {e}")
            traceback.print_exc()
            return None


def run_from_config(config_path: str):
    """从配置文件运行可视化任务"""
    runner = VisualizationRunner(config_path)
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    task = VisualizationTask(
        task_id=config["task"]["task_id"],
        question=config["task"]["question"],
        hint=config["task"].get("hint", ""),
        selected_columns=config["task"]["selected_columns"],
        candidate_columns=config["task"]["candidate_columns"],
    )
    
    return runner.run_task(task)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python mcts_runner.py <config.yaml>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    run_from_config(config_path)