import os
import unittest
import markdown

class TestHTMLReport(unittest.TestCase):
    def test_html_report_generation(self):
        """测试 HTML 报告生成功能，使用已有的图表"""
        # 使用实际的迭代目录
        iteration_dir = os.path.join("storyteller", "output", "iterations", "iteration_1")
        charts_dir = os.path.join(iteration_dir, "charts")
        
        # 确保目录存在
        if not os.path.exists(charts_dir):
            self.skipTest("找不到图表目录")
        
        # 获取所有图表文件
        chart_files = [f for f in os.listdir(charts_dir) if f.endswith('.png')]
        if not chart_files:
            self.skipTest("图表目录中没有图表文件")
            
        print(f"\n找到以下图表文件：")
        for chart in chart_files:
            print(f"- {chart}")
        
        # 创建测试用的 Markdown 内容
        markdown_content = "# 测试报告\n\n"
        for chart in chart_files:
            title = os.path.splitext(chart)[0].replace('_', ' ')
            # HTML 文件在 storyteller/output/test/，图表在 storyteller/output/iterations/iteration_1/charts/
            # 所以需要使用相对路径 ../iterations/iteration_1/charts/
            chart_path = f"../iterations/iteration_1/charts/{chart}"
            markdown_content += f"\n## {title}\n\n"
            markdown_content += f"![{title}]({chart_path})\n\n"
        
        # 转换 Markdown 为 HTML
        html_body = markdown.markdown(
            markdown_content,
            extensions=['extra', 'nl2br', 'sane_lists']
        )
        
        # 生成 HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>图表显示测试</title>
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
        
        # 保存 HTML 文件
        test_dir = os.path.join("storyteller", "output", "test")
        os.makedirs(test_dir, exist_ok=True)
        html_file = os.path.join(test_dir, "test_charts.html")
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"\n✅ 测试 HTML 文件已生成：{html_file}")
        print("请在浏览器中打开查看图表显示效果")

if __name__ == '__main__':
    unittest.main() 