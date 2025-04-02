import sys
import os, json
from datetime import datetime

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from pathlib import Path
from typing import Dict, Any
import yaml
import traceback
from storyteller.algorithm.mcts_solver import DataStorytellingMCTSSolver
from storyteller.algorithm.mcts_node import  MCTSNode, ChartGroup

class DataStorytellingRunner:
    def __init__(self, config_path: str):
        """初始化运行器"""
        # 加载配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        # 创建日志目录
        self.log_dir = os.path.join(os.path.dirname(config_path), 'logs')
        os.makedirs(self.log_dir, exist_ok=True)

    def run(self):
        """运行 MCTS 进行数据故事生成"""
        try:
            print("\n🚀 开始运行 DataStorytelling MCTS...")
            solver = DataStorytellingMCTSSolver(
                original_query=self.config["query"],
                dataset_path=self.config["dataset_path"],
                output_dir=self.config["save_root_dir"],
                max_iterations=self.config["max_iterations"],
                max_depth=self.config["max_depth"],
                exploration_constant=self.config["exploration_constant"],
                data_context=self.config.get("data_context", ""),
                llm_kwargs=self.config.get("llm_kwargs", {})
            )

            # 运行 MCTS 生成数据故事
            best_node = solver.solve()
            print("\n✅ 数据故事 MCTS 运行完成！")

            # 🔍 打印最终决策路径
            self.print_decision_path(best_node)
            
            # 生成最终报告（使用完整版本的报告生成）
            self.generate_final_report(best_node)

            return best_node

        except Exception as e:
            print(f"❌ 运行过程中出现错误: {e}")
            traceback.print_exc()
            return None

    def print_decision_path(self, final_node: MCTSNode):
        """打印最终的决策路径"""
        print("\n📖 **最终决策路径:**")
        print("=" * 50)

        path = []
        current_node = final_node
        while current_node:
            path.append(current_node)
            current_node = current_node.parent_node
        
        # 按照从根节点到最终节点的顺序打印路径
        for step, node in enumerate(reversed(path)):
            if node.parent_action:  # 如果有动作，打印动作
                print(f"\n🔹 步骤 {step + 1}: {node.parent_action.description}")
                print(f"   ⤷ 进入状态: {node.node_type.name}")
            else:  # 根节点没有动作，只打印状态
                print(f"\n🔹 初始状态: {node.node_type.name}")

        # 打印最终报告的章节信息
        print("\n📊 **最终报告章节:**")
        if hasattr(final_node, 'report') and final_node.report and final_node.report.chapters:
            for chapter in final_node.report.chapters:
                print(f"\n📌 {chapter.title}")
        else:
            print("   ⚠️ 警告: 报告章节列表为空")

        print("\n📊 **数据故事生成完成！**")

    def clean_caption(self, caption: str) -> str:
        """清理图表说明文字，移除任何 HTML 标记"""
        if not caption:
            return ""
        
        # 如果包含完整的 HTML 文档，提取有用的文本内容
        if '<!doctype html>' in caption.lower():
            # 返回空字符串，因为这种情况下可能是错误的 caption
            return ""
        
        # 移除任何 HTML 标签
        import re
        clean_text = re.sub(r'<[^>]+>', '', caption)
        return clean_text.strip()

    def generate_markdown_report(self, final_node: MCTSNode) -> str:
        """生成 Markdown 格式的报告"""
        markdown = []
        output_dir = os.path.abspath(self.config["save_root_dir"])
        
        # 1. 报告标题
        markdown.append("# 数据分析报告\n")
        
        # 2. 报告摘要（开头）
        if hasattr(final_node.report, 'key_abstract') and final_node.report.key_abstract:
            markdown.append("## 摘要\n")
            markdown.append(final_node.report.key_abstract + "\n")
        
        # 3. 章节内容
        for chapter in final_node.report.chapters:
            markdown.append(f"\n## {chapter.title}\n")
            
            # 添加图表和说明
            for chart in getattr(chapter, 'charts', []):
                if hasattr(chart, 'caption') and chart.caption:
                    markdown.append(f"\n> {chart.caption}\n")
                if hasattr(chart, 'url') and chart.url:
                    # 规范化图片路径
                    img_path = os.path.relpath(chart.url, output_dir)
                    img_path = img_path.replace('\\', '/')  # 统一使用正斜杠
                    markdown.append(f"\n![{chapter.title}]({img_path})\n")
            
            # 添加章节总结
            if hasattr(chapter, 'summary') and chapter.summary:
                markdown.append("\n### 章节小结\n")
                markdown.append(chapter.summary + "\n")
        
        # 4. 报告总结（结尾）
        if hasattr(final_node.report, 'brief_conclusion') and final_node.report.brief_conclusion:
            markdown.append("\n## 总结与建议\n")
            markdown.append(final_node.report.brief_conclusion + "\n")
        
        return "\n".join(markdown)

    def generate_html_report(self, markdown_content: str) -> str:
        """生成 HTML 格式的报告"""
        # 1. 生成基本的 HTML 结构
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据分析报告</title>
    <script src="https://cdn.jsdelivr.net/npm/markdown-it@13.0.1/dist/markdown-it.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.8;
            max-width: 1000px;
            margin: 0 auto;
            padding: 2rem;
            color: #333;
            text-align: left;
        }}
        h1 {{ 
            color: #2c3e50; 
            border-bottom: 2px solid #eee; 
            padding-bottom: 0.3em;
            text-align: center;
        }}
        h2 {{ 
            color: #34495e; 
            margin-top: 2em;
            text-align: left;
        }}
        h3 {{ 
            color: #455a64;
            text-align: left;
        }}
        p {{ 
            margin: 1em 0;
            text-indent: 2em;
        }}
        img {{ 
            max-width: 50%;
            height: auto; 
            display: block; 
            margin: 2em auto;
            border: 1px solid #eee;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        em {{ 
            display: block;
            text-align: left;
            color: #666;
            margin: 1em 0;
            font-style: italic;
            text-indent: 2em;
            max-width: 100%;
        }}
        .chart-caption {{ 
            text-align: left;
            color: #666;
            margin: 1em 0;
            max-width: 100%;
            text-indent: 2em;
        }}
        blockquote {{
            border-left: 4px solid #42b983;
            margin: 1em 0;
            padding: 0.5em 1em;
            color: #666;
            background: #f8f8f8;
        }}
        ul, ol {{
            padding-left: 2em;
            margin: 1em 0;
        }}
        li {{
            margin: 0.5em 0;
            text-align: left;
            text-indent: 0;
        }}
        .summary p {{
            text-indent: 0;
        }}
    </style>
</head>
<body>
    <div id="content"></div>
    <script>
        // 初始化 markdown-it
        var md = window.markdownit({{
            html: true,
            breaks: true,
            linkify: true
        }});
        
        // 直接使用 markdown 内容
        var content = {json.dumps(markdown_content)};
        document.getElementById('content').innerHTML = md.render(content);

        // 为摘要部分添加 class
        var summarySection = document.querySelector('h2');
        if (summarySection && summarySection.textContent.trim() === '摘要') {{
            var summaryDiv = document.createElement('div');
            summaryDiv.className = 'summary';
            var nextElement = summarySection.nextElementSibling;
            while (nextElement && nextElement.tagName !== 'H2') {{
                var clone = nextElement.cloneNode(true);
                summaryDiv.appendChild(clone);
                nextElement = nextElement.nextElementSibling;
            }}
            summarySection.parentNode.insertBefore(summaryDiv, summarySection.nextSibling);
        }}
    </script>
</body>
</html>"""

        return html

    def generate_final_report(self, final_node: MCTSNode):
        """生成最终的完整报告"""
        output_dir = self.config["save_root_dir"]
        
        try:
            # 找到最佳迭代
            history_dir = os.path.join(output_dir, "iterations")
            best_iteration = None
            best_score = -float('inf')
            
            for d in os.listdir(history_dir):
                if not d.startswith("iteration_"):
                    continue
                
                score_file = os.path.join(history_dir, d, "score.json")
                if os.path.exists(score_file):
                    with open(score_file, 'r', encoding='utf-8') as f:
                        score_data = json.load(f)
                        if score_data["score"] > best_score:
                            best_score = score_data["score"]
                            best_iteration = d
            
            if not best_iteration:
                print("⚠️ 未找到有效的迭代结果")
                return
            
            # 找到最佳迭代的目录
            best_iteration_dir = os.path.join(history_dir, best_iteration)
            
            # 复制最佳迭代的报告
            best_report_path = os.path.join(best_iteration_dir, "report.md")
            if os.path.exists(best_report_path):
                with open(best_report_path, 'r', encoding='utf-8') as f:
                    best_report_content = f.read()
                
                # 修正图片路径引用
                best_report_content = best_report_content.replace(
                    "](charts/", 
                    f"]({os.path.join('iterations', best_iteration, 'charts')}/"
                )
                
                # 保存最终报告
                with open(os.path.join(output_dir, "report.md"), 'w', encoding='utf-8') as f:
                    f.write(best_report_content)
                print(f"\n📝 Markdown 报告已保存到: {os.path.join(output_dir, 'report.md')}")
                
                # 生成HTML报告
                html_content = self.generate_html_report(best_report_content)
                with open(os.path.join(output_dir, "report.html"), 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print(f"📊 HTML 报告已保存到: {os.path.join(output_dir, 'report.html')}")
                
                print(f"✨ 最佳报告来自迭代 {best_iteration}，得分: {best_score:.2f}")
        
        except Exception as e:
            print(f"❌ 保存报告时出错: {e}")
            traceback.print_exc()

def run_from_config(config_path: str):
    """从配置文件运行数据故事生成"""
    runner = DataStorytellingRunner(config_path)
    return runner.run()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python mcts_runner.py <config.yaml>")
        sys.exit(1)

    config_path = sys.argv[1]
    run_from_config(config_path)