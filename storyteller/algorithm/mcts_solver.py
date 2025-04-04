import random
import math
import copy
import os
import json
import sys
import subprocess
from typing import List, Dict, Any, Optional
from datetime import datetime
from urllib.parse import quote

from storyteller.algorithm.mcts_node import MCTSNode, Report, ReportGenerationState
from storyteller.algorithm.mcts_action import (
    DataStorytellingAction,
    Query2Chapters,
    Chapters2Tasks,
    Tasks2Charts,
    ReviseVis,
    Charts2Captions,
    Captions2Summaries,
)
NODE_TYPE_TO_VALID_ACTIONS = {
    ReportGenerationState.EMPTY: [
        Query2Chapters
    ],
    ReportGenerationState.a1: [
        Chapters2Tasks
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
from storyteller.algorithm.reward import StorytellingRewardModel
from .utils.html2image import convert_html_file_to_image

class DataStorytellingMCTSSolver:
    def __init__(self, 
                 original_query: str,
                 dataset_path: str,
                 output_dir: str,
                 max_iterations: int = 100,
                 max_depth: int = 10,
                 exploration_constant: float = 1.414,
                 data_context: str = "",
                 llm_kwargs: dict = None):
        """
        MCTS 解决器，用于数据故事自动生成。

        参数:
            original_query: 用户输入的问题
            dataset_path: 数据集路径
            output_dir: 输出目录
            max_iterations: 最大搜索迭代次数
            max_depth: 最大搜索深度
            exploration_constant: UCB1 公式中的探索常数
            data_context: 数据集的上下文信息
            llm_kwargs: 传递给 LLM（大模型）的参数
        """
        self.original_query = original_query
        self.dataset_path = dataset_path
        self.output_dir = output_dir
        self.max_iterations = max_iterations
        self.max_depth = max_depth
        self.exploration_constant = exploration_constant
        self.data_context = json.load(open(data_context, 'r', encoding='utf-8'))
        self.llm_kwargs = llm_kwargs or {}

        # 创建奖励模型
        self.reward_model = StorytellingRewardModel(llm_kwargs=self.llm_kwargs)

        # 定义动作空间
        self.action_space = [
            Query2Chapters(),
            Chapters2Tasks(),
            Tasks2Charts(),
            ReviseVis(),
            Charts2Captions(),
            Captions2Summaries()
        ]

        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)

        # 初始化根节点 - 使用原有的 MCTSNode 初始化方式
        self.root = MCTSNode(
            node_type=ReportGenerationState.EMPTY,
            report=Report(
                original_query=self.original_query, 
                dataset_path=self.dataset_path, 
                data_context=self.data_context
            ),
            original_query=self.original_query,
            llm_kwargs=self.llm_kwargs
        )

        # 添加最佳节点追踪
        self.best_node = self.root
        self.best_score = float('-inf')


    def select(self, node: MCTSNode) -> MCTSNode:
        """
        选择阶段：使用 UCB1 公式选择最有希望的 `Node` 进行扩展。

        参数:
            node: 当前 MCTS 节点

        返回:
            选中的 `Node`
        """
        while node.children:
            if any(child.N == 0 for child in node.children):
                return next(child for child in node.children if child.N == 0)

            # 选择 UCB1 评分最高的子节点
            node = max(node.children, key=lambda c: (c.Q / c.N) + self.exploration_constant * math.sqrt(math.log(node.N) / c.N))
        return node
    def expand(self, node: MCTSNode) -> None:
        """展开叶子节点，添加所有可能的子节点"""
        print("🔄 扩展节点...")
        print(f"\n调试信息:")
        
        # 如果节点已经有子节点，先清空它们
        if node.children:
            print(f"⚠️ 节点 {node.node_type} 在扩展前已有 {len(node.children)} 个子节点，将清空这些子节点")
            node.children = []
        
        # 获取当前节点状态
        current_state = node.node_type
        print(f"当前状态: {current_state}")
        
        # 获取当前状态可用的动作类型
        valid_action_types = NODE_TYPE_TO_VALID_ACTIONS.get(current_state, [])
        
        if not valid_action_types:
            print(f"⚠️ 状态 {current_state.name} 没有有效的动作类型")
            return
        
        print(f"找到 {len(valid_action_types)} 个可用动作类型")
        
        # 遍历每个动作类型
        for action_class in valid_action_types:
            try:
                # 实例化动作类
                action_instance = action_class()
                print(f"尝试执行动作: {action_class.__name__}")
                
                # 创建子节点
                children = action_instance.create_children_nodes(node, self.llm_kwargs)
                
                if not children:
                    print(f"⚠️ 动作 {action_class.__name__} 没有生成任何子节点，尝试创建一个默认子节点")
                    # 创建一个默认子节点，确保每个动作都能生成至少一个子节点
                    default_child = copy.deepcopy(node)
                    default_child.parent_node = node
                    default_child.parent_action = action_instance
                    default_child.depth = node.depth + 1
                    
                    # 根据动作类型设置正确的状态
                    if action_class == Query2Chapters:
                        default_child.node_type = ReportGenerationState.a1
                    elif action_class == Chapters2Tasks:
                        default_child.node_type = ReportGenerationState.a2
                    elif action_class == Tasks2Charts:
                        default_child.node_type = ReportGenerationState.a3
                    elif action_class == ReviseVis:
                        default_child.node_type = ReportGenerationState.a4
                    elif action_class == Charts2Captions:
                        default_child.node_type = ReportGenerationState.a5
                    elif action_class == Captions2Summaries:
                        default_child.node_type = ReportGenerationState.FINALIZED
                    
                    children = [default_child]
                    print(f"✅ 为动作 {action_class.__name__} 创建了一个默认子节点")
                else:
                    print(f"✅ 动作 {action_class.__name__} 生成了 {len(children)} 个子节点")
                
                # 添加子节点到当前节点
                node.children.extend(children)
                
                # 确保所有新创建的子节点继承当前的迭代号
                current_iteration = self.root.report.current_iteration
                for child in children:
                    child.report.current_iteration = current_iteration
                
            except Exception as e:
                print(f"❌ 执行动作 {action_class.__name__} 时出错: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # 检查是否生成了子节点
        if not node.children:
            print("⚠️ 扩展后没有生成任何子节点")
        else:
            print(f"✅ 共生成 {len(node.children)} 个子节点")
        
        # 随机打乱子节点顺序
        random.shuffle(node.children)

    def simulate(self, node: MCTSNode) -> tuple[MCTSNode, float]:
        """模拟阶段：从当前节点开始随机执行动作，直到达到终止状态"""
        print("🔄 模拟阶段...")
        
        # 创建副本并保持正确的迭代号
        current = copy.deepcopy(node)
        current.report.current_iteration = self.root.report.current_iteration
        
        # 循环直到达到终止状态
        while not current.is_terminal() and current.depth < self.max_depth:
            # 获取当前状态下的合法动作
            self.expand(current)
            
            # 检查是否有子节点
            if not current.children:
                print("⚠️ 当前节点扩展后没有子节点，停止模拟")
                break
            
            # 随机选择一个子节点
            current = random.choice(current.children)
            print(f"➡️ 模拟进入状态: {current.node_type.name} (深度 {current.depth})")
        
        # 如果达到终止状态，进行质量评估
        if current.is_terminal():
            print("✅ 模拟生成了完整报告！")
            
            # 生成完整的报告
            markdown_report = self._generate_markdown_report(current)
            html_report = self._generate_html_report(markdown_report, self.output_dir)
            
            # 保存报告到当前迭代目录
            iteration_dir = os.path.join(self.output_dir, "iterations", f"iteration_{current.report.current_iteration}")
            os.makedirs(iteration_dir, exist_ok=True)
            
            # 保存 Markdown 报告
            markdown_path = os.path.join(iteration_dir, "report.md")
            with open(markdown_path, 'w', encoding='utf-8') as f:
                f.write(markdown_report)
            print(f"✅ Markdown 报告已保存到: {markdown_path}")
            
            # 保存 HTML 报告
            html_path = os.path.join(iteration_dir, "report.html")
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_report)
            print(f"✅ HTML 报告已保存到: {html_path}")
            
            # 获取 process_all_reports.py 的路径
            script_dir = os.path.dirname(os.path.abspath(__file__))
            process_script = os.path.join(script_dir, "utils", "process_all_reports.py")
            
            # 使用 process_all_reports.py 生成所有模板风格的报告
            try:
                print(f"正在为 {iteration_dir} 生成所有风格的报告...")
                subprocess.run([
                    'python', 
                    process_script,  # 使用完整路径
                    '--all',
                    '--dir', iteration_dir
                ], check=True)
                print(f"已生成所有模板风格的报告到 {iteration_dir}")
                
                # 获取所有生成的HTML文件
                html_files = [f for f in os.listdir(iteration_dir) if f.endswith('.html')]
                if html_files:
                    # 随机选择一个HTML文件
                    selected_html = random.choice(html_files)
                    selected_html_path = os.path.join(iteration_dir, selected_html)
                    print(f"\n🎲 随机选择 {selected_html} 转换为PNG...")
                    
                    # 转换为PNG
                    png_path = os.path.splitext(selected_html_path)[0] + ".png"
                    convert_html_file_to_image(selected_html_path, png_path)
                    print(f"✅ PNG文件已生成: {png_path}")
                
            except Exception as e:
                print(f"生成多样式报告时出错: {e}")
            
            try:
                # 计算基础奖励
                base_reward = self.reward_model._compute_base_reward(current)
                self.reward_model.last_base_reward = base_reward
                print(f"✓ 基础奖励计算完成: {base_reward:.2f}")
                
                try:
                    # 计算质量奖励
                    quality_reward = self.reward_model._compute_quality_reward(current, html_path, png_path)
                    self.reward_model.last_quality_reward = quality_reward
                    print(f"✓ 质量奖励计算完成: {quality_reward:.2f}")
                except Exception as e:
                    print(f"❌ 质量奖励计算失败: {str(e)}")
                    quality_reward = 5.0  # 使用默认值
                    self.reward_model.last_quality_reward = quality_reward
                
                # 总奖励为基础奖励和质量奖励的和
                reward = base_reward + quality_reward
                print(f"✓ 总奖励: {reward:.2f}")
                
            except Exception as e:
                print(f"❌ 奖励计算出错: {str(e)}")
                # 如果计算奖励出错，返回基础奖励
                reward = self.reward_model._compute_base_reward(current)
                self.reward_model.last_base_reward = reward
                self.reward_model.last_quality_reward = 5.0
        else:
            # 未达到终止状态，返回基础奖励
            reward = self.reward_model._compute_base_reward(current)
            self.reward_model.last_base_reward = reward
            self.reward_model.last_quality_reward = 5.0
        
        return current, reward

    def backpropagate(self, node: MCTSNode, reward: float):
        """
        回溯阶段：更新路径上所有节点的统计信息
        """
        while node is not None:
            node.N += 1
            node.Q += reward  # 使用同样的奖励值更新整条路径
            node = node.parent_node

    def solve(self) -> MCTSNode:
        """执行 MCTS 搜索"""
        # 首先测试 HTML 报告生成
        # print("\n🧪 测试 HTML 报告生成...")
        # test_html = self.test_html_report()
        # print(f"测试报告已生成: {test_html}")
        # print("-" * 50)
        
        # 设置日志文件路径
        log_file = os.path.join("storyteller", "output", "log.txt")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # 保存原始的标准输出
        original_stdout = sys.stdout
        
        # 打开日志文件
        log_f = open(log_file, 'w', encoding='utf-8')
        
        class TeeOutput:
            def __init__(self, file):
                self.file = file
                self.stdout = original_stdout
            
            def write(self, message):
                self.stdout.write(message)
                self.file.write(message)
                self.file.flush()
            
            def flush(self):
                self.stdout.flush()
                self.file.flush()
        
        # 设置输出重定向
        sys.stdout = TeeOutput(log_f)
        
        try:
            print("\n🔍 MCTS 搜索开始")
            print("=" * 50)
            print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 创建历史记录目录
            history_dir = os.path.join(self.output_dir, "iterations")
            os.makedirs(history_dir, exist_ok=True)
            
            start_time = datetime.now()
            best_node = None
            best_score = float('-inf')
            
            for iteration in range(self.max_iterations):
                # 设置当前迭代号
                self.root.report.current_iteration = iteration + 1
                print(f"Debug: 设置根节点迭代号为 {self.root.report.current_iteration}")
                
                # 创建当前迭代的目录
                iteration_dir = os.path.join(history_dir, f"iteration_{iteration + 1}")
                os.makedirs(iteration_dir, exist_ok=True)
                os.makedirs(os.path.join(iteration_dir, "charts"), exist_ok=True)
                
                print(f"\n🌀 **MCTS 迭代 {iteration + 1}/{self.max_iterations}**")
                
                # 选择
                leaf = self.select(self.root)
                print(f"👉 选择 `Node` (深度 {leaf.depth}) | 状态: {leaf.node_type}")
                
                # 扩展
                self.expand(leaf)
                
                # 如果扩展成功并生成了子节点，从子节点中选择一个进行模拟
                if leaf.children:
                    # 随机选择一个子节点进行模拟
                    child_for_simulation = random.choice(leaf.children)
                    # 模拟
                    final_node, simulated_reward = self.simulate(child_for_simulation)
                else:
                    # 如果没有子节点，可以直接对当前节点进行模拟
                    final_node, simulated_reward = self.simulate(leaf)
                
                # 保存这次迭代的结果
                iteration_dir = os.path.join(history_dir, f"iteration_{iteration + 1}")
                os.makedirs(iteration_dir, exist_ok=True)
                
                # 保存HTML报告
                html_path = self._save_html_report(final_node, 
                    output_path=os.path.join(iteration_dir, "report.html"))
                
                # 保存报告截图
                image_path = convert_html_file_to_image(html_path,
                    output_path=os.path.join(iteration_dir, "report.png"))
                
                # 保存评分信息
                score_info = {
                    "iteration": iteration + 1,
                    "score": float(simulated_reward),
                    "score_breakdown": {
                        "base_reward": self.reward_model.last_base_reward,
                        "quality_reward": self.reward_model.last_quality_reward
                    },
                    "is_best": simulated_reward > best_score,
                    "node_type": final_node.node_type.name,
                    "depth": final_node.depth,
                    "chapter_count": len(final_node.report.chapters),
                    "chart_count": sum(len(chapter.charts) for chapter in final_node.report.chapters),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "elapsed_time": str(datetime.now() - start_time)
                }
                
                with open(os.path.join(iteration_dir, "score.json"), 'w', encoding='utf-8') as f:
                    json.dump(score_info, f, indent=2, ensure_ascii=False)
                
                print(f"✅ 迭代 {iteration + 1} 报告已保存到: {iteration_dir}")
                print(f"   得分: {simulated_reward:.2f}")
                
                # 如果找到更好的完整报告
                if simulated_reward > best_score:
                    best_score = simulated_reward
                    best_node = copy.deepcopy(final_node)
                    print(f"📈 找到更好的完整报告！得分: {best_score:.2f}")
                
                # 回溯
                self.backpropagate(leaf, simulated_reward)
                print(f"   📊 `Q` 值更新: {leaf.Q}, 访问次数: {leaf.N}")
                print("-" * 50)
                
                # 生成并保存完整的markdown报告
                markdown_report = self._generate_markdown_report(final_node)
                with open(os.path.join(iteration_dir, "report.md"), 'w', encoding='utf-8') as f:
                    f.write(markdown_report)
                
                # 生成并保存HTML报告
                html_report = self._generate_html_report(markdown_report, iteration_dir)
                with open(os.path.join(iteration_dir, "report.html"), 'w', encoding='utf-8') as f:
                    f.write(html_report)
            
            # 保存搜索历史统计信息
            history_summary = {
                "total_iterations": self.max_iterations,
                "completed_iterations": iteration + 1,
                "best_score": float(best_score),
                "best_iteration": max(range(1, iteration + 2), 
                    key=lambda i: os.path.exists(os.path.join(history_dir, f"iteration_{i}", "score.json")) and 
                        json.load(open(os.path.join(history_dir, f"iteration_{i}", "score.json")))["score"]),
                "final_depth": best_node.depth if best_node else 0,
                "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "completion_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_duration": str(datetime.now() - start_time)
            }
            
            with open(os.path.join(history_dir, "search_summary.json"), 'w', encoding='utf-8') as f:
                json.dump(history_summary, f, indent=2, ensure_ascii=False)

            print("\n✅ MCTS 搜索完成！")
            print("=" * 50)
            
            if best_node.node_type.name == "FINALIZED":
                print(f"🎯 返回最佳完整报告 | 得分: {best_score:.2f}")
                return best_node
            else:
                print("⚠️ 未找到完整报告，返回根节点")
                return self.root
            
        finally:
            # 恢复原始输出
            sys.stdout = original_stdout
            # 关闭日志文件
            log_f.close()

    def _save_html_report(self, node: MCTSNode, output_path: str = None) -> str:
        """
        生成并保存HTML报告
        
        参数:
            node: 当前节点
            output_path: 指定输出路径（可选）
            
        返回:
            str: HTML文件路径
        """
        try:
            # 生成Markdown报告
            markdown_content = self._generate_markdown_report(node)
            
            # 生成HTML报告
            html_content = self._generate_html_report(markdown_content, os.path.dirname(output_path) if output_path else self.output_dir)
            
            # 确定保存路径
            if output_path is None:
                # 使用iterations目录而不是temp
                default_dir = os.path.join(self.output_dir, "iterations", "default")
                os.makedirs(default_dir, exist_ok=True)
                output_path = os.path.join(default_dir, "temp_report.html")
            
            # 创建输出目录（如果不存在）
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 保存HTML文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return output_path
        
        except Exception as e:
            print(f"❌ 保存HTML报告时出错: {str(e)}")
            raise e

    def _generate_markdown_report(self, node: MCTSNode) -> str:
        """生成 Markdown 报告"""
        markdown = []
        
        # 1. 报告标题
        markdown.append("# 数据分析报告\n")
        
        # 2. 报告摘要
        if hasattr(node.report, 'key_abstract') and node.report.key_abstract:
            markdown.append("## 摘要\n")
            markdown.append(node.report.key_abstract + "\n")
        
        # 3. 章节内容
        for chapter in node.report.chapters:
            # 移除标题中的字典格式
            chapter_title = chapter.title
            if isinstance(chapter_title, str) and chapter_title.startswith("{'title': '") and chapter_title.endswith("'}"):
                chapter_title = chapter_title[len("{'title': '"):-2]
            
            markdown.append(f"\n## {chapter_title}\n")
            
            # 添加图表和说明
            for chart in getattr(chapter, 'charts', []):
                # 先添加图表说明
                if hasattr(chart, 'caption') and chart.caption:
                    markdown.append(f"\n> {chart.caption}\n")
                
                # 处理图表URL
                if hasattr(chart, 'url') and chart.url:
                    try:
                        # 获取图片文件名
                        img_filename = os.path.basename(chart.url)
                        print(f"处理图片: {img_filename}")
                        print(f"原始URL: {chart.url}")
                        
                        # 使用相对路径，确保路径正确
                        markdown.append(f"\n![{chapter_title}](charts/{img_filename})\n")
                    except Exception as e:
                        print(f"❌ 处理图片路径时出错: {str(e)}")
                        continue
            
            # 添加章节总结
            if hasattr(chapter, 'summary') and chapter.summary:
                markdown.append("\n### Chapter Summary\n")
                markdown.append(chapter.summary + "\n")
        
        # 4. 报告总结
        if hasattr(node.report, 'brief_conclusion') and node.report.brief_conclusion:
            markdown.append("\n## 总结与建议\n")
            markdown.append(node.report.brief_conclusion + "\n")
        
        return "\n".join(markdown)

    def _generate_html_report(self, markdown_content: str, output_dir: str) -> str:
        """
        将 Markdown 内容转换为 HTML 报告，并生成所有模板风格的报告
        """
        import markdown
        import os
        import re
        import subprocess
        import json
        import random
        
        # 创建 HTML 文件路径
        html_file = os.path.join(output_dir, "report.html")
        md_file = os.path.join(output_dir, "report.md")
        
        # 修复标题格式问题，将JSON/字典格式的标题转换为纯文本
        def fix_titles(content):
            # 匹配 ## {'title': 'Something'} 格式
            pattern1 = r'(#+)\s*({\'title\':\s*\'(.*?)\'})' 
            content = re.sub(pattern1, r'\1 \3', content)
            
            # 匹配 ## {"title": "Something"} 格式
            pattern2 = r'(#+)\s*({\"title\":\s*\"(.*?)\"})' 
            content = re.sub(pattern2, r'\1 \3', content)
            
            return content
        
        # 修复标题
        markdown_content = fix_titles(markdown_content)
        
        # 保存修复后的markdown内容到文件
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        # 修复图片路径
        def fix_image_paths(content):
            # 保持原始路径不变，让浏览器处理 URL 编码
            return content
        
        # 修复 Markdown 中的图片路径
        markdown_content = fix_image_paths(markdown_content)
        
        # 转换 Markdown 为 HTML
        html_body = markdown.markdown(
            markdown_content,
            extensions=['extra', 'nl2br', 'sane_lists']
        )
        
        # HTML 模板
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>数据分析报告</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    line-height: 1.8;
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 2rem;
                    background-color: #f9f9f9;
                }}
                h1 {{ 
                    color: #2c3e50;
                    text-align: center;
                    border-bottom: 3px solid #42b983;
                    padding-bottom: 0.5em;
                }}
                h2 {{
                    color: #34495e;
                    margin-top: 2em;
                    padding-left: 0.5em;
                    border-left: 5px solid #42b983;
                }}
                img {{
                    max-width: 100%;
                    height: auto;
                    display: block;
                    margin: 2em auto;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                blockquote {{
                    border-left: 4px solid #42b983;
                    margin: 1.5em 0;
                    padding: 1em;
                    color: #2c3e50;
                    background: white;
                    border-radius: 0 4px 4px 0;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                }}
                .chart-wrapper {{
                    background: white;
                    padding: 1em;
                    margin: 2em 0;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
            </style>
        </head>
        <body>
            <div class="content">
                {html_body}
            </div>
            <script>
                // 将所有图片包装在 chart-wrapper div 中
                document.querySelectorAll('img').forEach(img => {{
                    const wrapper = document.createElement('div');
                    wrapper.className = 'chart-wrapper';
                    img.parentNode.insertBefore(wrapper, img);
                    wrapper.appendChild(img);
                }});
            </script>
        </body>
        </html>
        """
        
        # 获取 process_all_reports.py 的路径
        script_dir = os.path.dirname(os.path.abspath(__file__))
        process_script = os.path.join(script_dir, "utils", "process_all_reports.py")
        
        # 使用 process_all_reports.py 生成所有模板风格的报告
        try:
            print(f"正在为 {output_dir} 生成所有风格的报告...")
            subprocess.run([
                'python', 
                process_script,  # 使用完整路径
                '--all',
                '--dir', output_dir
            ], check=True)
            print(f"已生成所有模板风格的报告到 {output_dir}")
            
            # 获取所有生成的HTML文件
            html_files = [f for f in os.listdir(output_dir) if f.endswith('.html')]
            if html_files:
                # 随机选择一个HTML文件
                selected_html = random.choice(html_files)
                selected_html_path = os.path.join(output_dir, selected_html)
                print(f"\n🎲 随机选择 {selected_html} 转换为PNG...")
                
                # 转换为PNG
                png_path = os.path.splitext(selected_html_path)[0] + ".png"
                convert_html_file_to_image(selected_html_path, png_path)
                print(f"✅ PNG文件已生成: {png_path}")
            
        except Exception as e:
            print(f"生成多样式报告时出错: {e}")
        
        return html_content
