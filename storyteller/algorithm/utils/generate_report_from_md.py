import markdown
from bs4 import BeautifulSoup
import os
import argparse
from pathlib import Path
import random

def parse_markdown(md_path):
    with open(md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()
    html = markdown.markdown(md_content, extensions=['extra'])
    soup = BeautifulSoup(html, 'html.parser')

    # Get the directory of the markdown file for relative paths
    md_dir = os.path.dirname(os.path.abspath(md_path))

    sections = []
    current_section = {}
    current_charts = []
    current_caption = ""
    
    for tag in soup.find_all():
        if tag.name == 'h2':
            # 如果已经有当前章节，先保存它
            if current_section:
                sections.append(current_section)
            # 开始新的章节
            current_section = {
                "title": tag.get_text(strip=True),
                "charts": [],
                "summary": ""
            }
            current_charts = []
            current_caption = ""
        elif tag.name == 'blockquote':
            current_caption = tag.get_text(strip=True)
        elif tag.name == 'img':
            img_path = tag.get('src', '')
            # Convert relative path to absolute path based on markdown file location
            if img_path and not os.path.isabs(img_path):
                img_path = os.path.join(md_dir, img_path)
            current_section["charts"].append({
                "img": img_path,
                "caption": current_caption
            })
        elif tag.name == 'h3' and tag.get_text(strip=True) == "Chapter Summary":
            # 获取所有后续的p标签，直到遇到下一个h2或h3
            summary_parts = []
            next_tag = tag.find_next()
            while next_tag and next_tag.name not in ['h2', 'h3']:
                if next_tag.name == 'p':
                    summary_parts.append(next_tag.get_text(strip=True))
                next_tag = next_tag.find_next()
            if summary_parts:
                current_section["summary"] = " ".join(summary_parts)

    # 不要忘记添加最后一个章节
    if current_section:
        sections.append(current_section)
    return sections


def fill_template(sections, template_type="orange"):
    from pathlib import Path

    def highlight_keywords(text):
        if not text:
            return ""
        # 这里可以添加关键词高亮逻辑
        return text

    from html import escape
    
    # 定义不同的模板样式
    templates = {
        "orange": {
            "background": "#fffaf5",
            "title_color": "#d35400",
            "title_border": "#e67e22",
            "heading_gradient_start": "#f6b26b",
            "heading_gradient_end": "#f39c12",
            "card_border": "#f39c12",
            "highlight_color": "#d35400",
            "summary_bg": "#fff2e6",
            "summary_border": "#f39c12"
        },
        "blue": {
            "background": "#f5f9ff",
            "title_color": "#2980b9",
            "title_border": "#3498db",
            "heading_gradient_start": "#6badf6",
            "heading_gradient_end": "#3498db",
            "card_border": "#3498db",
            "highlight_color": "#2980b9",
            "summary_bg": "#e6f2ff",
            "summary_border": "#3498db"
        },
        "green": {
            "background": "#f5fff7",
            "title_color": "#27ae60",
            "title_border": "#2ecc71",
            "heading_gradient_start": "#6bf6a3",
            "heading_gradient_end": "#2ecc71",
            "card_border": "#2ecc71",
            "highlight_color": "#27ae60",
            "summary_bg": "#e6ffe8",
            "summary_border": "#2ecc71"
        },
        "purple": {
            "background": "#f9f5ff",
            "title_color": "#8e44ad",
            "title_border": "#9b59b6",
            "heading_gradient_start": "#c6a6f6",
            "heading_gradient_end": "#9b59b6",
            "card_border": "#9b59b6",
            "highlight_color": "#8e44ad",
            "summary_bg": "#f0e6ff",
            "summary_border": "#9b59b6"
        }
    }
    
    # 使用选定的模板
    if template_type not in templates and template_type not in ["sidebar", "grid", "dark", "magazine", "dashboard"]:
        template_type = "orange"  # 默认使用橙色模板
    
    # 使用特殊的布局模板
    if template_type == "sidebar":
        return generate_sidebar_template(sections)
    elif template_type == "grid":
        return generate_grid_template(sections)
    elif template_type == "dark":
        return generate_dark_template(sections)
    elif template_type == "magazine":
        return generate_magazine_template(sections)
    elif template_type == "dashboard":
        return generate_dashboard_template(sections)
    
    theme = templates[template_type]

    html_head = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Generated Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background-color: {theme["background"]}; color: #333; max-width: 1000px; margin: auto; padding: 2rem; }}
        h1 {{ text-align: center; color: {theme["title_color"]}; border-bottom: 3px solid {theme["title_border"]}; padding-bottom: 0.5rem; }}
        h2 {{ background: linear-gradient(to right, {theme["heading_gradient_start"]}, {theme["heading_gradient_end"]}); color: white; padding: 0.8rem 1rem; border-radius: 6px; margin-top: 3rem; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .chart-card {{ background: #fff; border-left: 6px solid {theme["card_border"]}; border-radius: 8px; padding: 1rem 1.5rem; box-shadow: 0 4px 10px rgba(0,0,0,0.05); margin-bottom: 2rem; }}
        .chart-card img {{ width: 100%; border-radius: 6px; margin: 1rem 0; }}
        .chart-caption {{ font-style: italic; color: #7f8c8d; }}
        .chart-caption .highlight {{ color: {theme["highlight_color"]}; font-weight: bold; }}
        .summary {{ background-color: {theme["summary_bg"]}; border-left: 5px solid {theme["summary_border"]}; padding: 1rem 1.5rem; border-radius: 6px; margin-top: 2rem; font-size: 0.96rem; line-height: 1.6; }}
    </style>
</head>
<body>
    <h1>Data Analysis Report</h1>
"""

    html_body = ""
    for section in sections:
        title = section["title"]
        html_body += f"<h2>{escape(title)}</h2>\n"
        for chart in section["charts"]:
            caption = chart.get("caption", "")
            img = chart.get("img", "")
            html_body += f"""
            <div class="chart-card">
                <div class="chart-caption">{escape(caption)}</div>
                <img src="{img}" alt="{escape(caption)}">
            </div>
"""
        summary = section.get("summary", "")
        if summary:
            html_body += f"<div class='summary'><strong>章节小结：</strong> {highlight_keywords(summary)}</div>\n"

    html_tail = "</body></html>"

    return html_head + html_body + html_tail


def generate_sidebar_template(sections):
    from html import escape
    
    # 生成导航链接
    nav_links = ""
    main_content = ""
    
    for i, section in enumerate(sections, 1):
        section_id = f"sec{i}"
        title = section["title"]
        
        # 添加导航链接
        nav_links += f'    <a href="#{section_id}" class="nav-link"><span class="nav-number">{i}</span><span class="nav-text">{escape(title)}</span></a>\n'
        
        # 添加内容部分
        main_content += f'''    <section id="{section_id}" class="content-section">
      <h2><span class="section-number">{i}</span>{escape(title)}</h2>\n'''
      
        # 添加图表
        for chart in section["charts"]:
            img = chart.get("img", "")
            caption = chart.get("caption", "")
            main_content += f'''      <div class="chart-container">
        <img src="{img}" width="100%">
        <p class="caption">{escape(caption)}</p>
      </div>\n'''
            
        # 添加章节小结
        summary = section.get("summary", "")
        if summary:
            main_content += f'      <div class="summary"><div class="summary-icon">📊</div><div class="summary-content"><p><strong>Chapter Summary：</strong> {escape(summary)}</p></div></div>\n'
            
        main_content += '    </section>\n\n'
    
    # 组装HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>数据分析报告</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --primary-color: #4f46e5;
      --primary-light: #818cf8;
      --primary-dark: #3730a3;
      --bg-color: #ffffff;
      --sidebar-bg: #f9fafb;
      --text-color: #1f2937;
      --text-light: #6b7280;
      --border-color: #e5e7eb;
      --hover-color: #f3f4f6;
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
      --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
      --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
    }}
    
    * {{
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }}
    
    body {{
      font-family: 'Inter', sans-serif;
      background-color: var(--bg-color);
      color: var(--text-color);
      margin: 0;
      display: flex;
      line-height: 1.5;
    }}
    
    nav {{
      width: 280px;
      background: var(--sidebar-bg);
      height: 100vh;
      padding: 2rem 0;
      position: sticky;
      top: 0;
      overflow-y: auto;
      border-right: 1px solid var(--border-color);
      box-shadow: var(--shadow-sm);
      transition: all 0.3s ease;
      z-index: 10;
    }}
    
    .nav-header {{
      padding: 0 1.5rem 1.5rem;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 1.5rem;
    }}
    
    .nav-title {{
      font-size: 1.2rem;
      font-weight: 600;
      color: var(--primary-color);
      margin-bottom: 0.5rem;
    }}
    
    .nav-subtitle {{
      font-size: 0.875rem;
      color: var(--text-light);
    }}
    
    nav a {{
      display: flex;
      align-items: center;
      padding: 0.75rem 1.5rem;
      text-decoration: none;
      color: var(--text-color);
      font-weight: 500;
      border-left: 3px solid transparent;
      transition: all 0.2s;
    }}
    
    nav a:hover {{
      background-color: var(--hover-color);
    }}
    
    nav a.active {{
      color: var(--primary-color);
      background-color: rgba(79, 70, 229, 0.1);
      border-left-color: var(--primary-color);
    }}
    
    .nav-number {{
      display: flex;
      align-items: center;
      justify-content: center;
      width: 24px;
      height: 24px;
      background-color: #e5e7eb;
      color: var(--text-color);
      border-radius: 50%;
      font-size: 0.75rem;
      margin-right: 0.75rem;
      flex-shrink: 0;
      transition: all 0.2s;
    }}
    
    a:hover .nav-number {{
      background-color: var(--primary-light);
      color: white;
    }}
    
    a.active .nav-number {{
      background-color: var(--primary-color);
      color: white;
    }}
    
    .nav-text {{
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    
    main {{
      flex: 1;
      padding: 2rem 3rem 4rem;
      max-width: 1200px;
      margin: 0 auto;
    }}
    
    .content-header {{
      margin-bottom: 3rem;
      text-align: center;
    }}
    
    .main-title {{
      font-size: 2.25rem;
      font-weight: 700;
      color: var(--primary-dark);
      margin-bottom: 0.5rem;
      letter-spacing: -0.025em;
    }}
    
    .main-subtitle {{
      font-size: 1.1rem;
      color: var(--text-light);
    }}
    
    .content-section {{
      margin-bottom: 4rem;
      padding-bottom: 2.5rem;
      border-bottom: 1px solid var(--border-color);
    }}
    
    .content-section:last-child {{
      border-bottom: none;
    }}
    
    h2 {{
      display: flex;
      align-items: center;
      font-size: 1.5rem;
      font-weight: 600;
      color: var(--primary-dark);
      margin-bottom: 1.5rem;
      padding-bottom: 0.75rem;
      border-bottom: 2px solid var(--primary-light);
    }}
    
    .section-number {{
      display: flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      background-color: var(--primary-color);
      color: white;
      border-radius: 50%;
      font-size: 0.875rem;
      margin-right: 0.75rem;
    }}
    
    .chart-container {{
      margin: 2rem 0;
      border-radius: 0.5rem;
      overflow: hidden;
      box-shadow: var(--shadow-md);
      transition: all 0.3s ease;
    }}
    
    .chart-container:hover {{
      transform: translateY(-4px);
      box-shadow: var(--shadow-lg);
    }}
    
    .chart-container img {{
      border-radius: 0.5rem 0.5rem 0 0;
      display: block;
    }}
    
    .caption {{
      background-color: #f9fafb;
      padding: 1rem;
      font-size: 0.875rem;
      color: var(--text-light);
      border-top: 1px solid var(--border-color);
    }}
    
    .summary {{
      display: flex;
      margin-top: 2rem;
      padding: 1.25rem;
      background-color: #f0f9ff;
      border-radius: 0.5rem;
      box-shadow: var(--shadow-sm);
    }}
    
    .summary-icon {{
      font-size: 1.5rem;
      margin-right: 1rem;
      color: var(--primary-color);
    }}
    
    .summary-content {{
      flex: 1;
    }}
    
    .summary p {{
      margin: 0;
      font-size: 0.95rem;
      line-height: 1.6;
    }}
    
    .summary strong {{
      color: var(--primary-dark);
    }}
    
    /* 响应式设计 */
    @media (max-width: 768px) {{
      body {{
        flex-direction: column;
      }}
      
      nav {{
        width: 100%;
        height: auto;
        position: relative;
        padding: 1rem 0;
      }}
      
      main {{
        padding: 1.5rem;
      }}
      
      .main-title {{
        font-size: 1.75rem;
      }}
    }}
    
    /* 动态激活当前导航项的 JavaScript */
    <script>
      document.addEventListener('DOMContentLoaded', function() {{
        const sections = document.querySelectorAll('.content-section');
        const navLinks = document.querySelectorAll('.nav-link');
        
        // 初始状态下激活第一个导航项
        navLinks[0].classList.add('active');
        
        // 滚动时更新激活状态
        window.addEventListener('scroll', function() {{
          let current = '';
          
          sections.forEach(function(section) {{
            const sectionTop = section.offsetTop;
            const sectionHeight = section.clientHeight;
            if(scrollY >= (sectionTop - 200)) {{
              current = section.getAttribute('id');
            }}
          }});
          
          navLinks.forEach(function(link) {{
            link.classList.remove('active');
            if(link.getAttribute('href').substring(1) === current) {{
              link.classList.add('active');
            }}
          }});
        }});
      }});
    </script>
  </style>
</head>
<body>
  <nav>
    <div class="nav-header">
      <div class="nav-title">目录</div>
      <div class="nav-subtitle">数据分析章节</div>
    </div>
{nav_links}  </nav>
  <main>
    <div class="content-header">
      <h1 class="main-title">数据分析报告</h1>
      <p class="main-subtitle">详细的数据分析与发现</p>
    </div>
{main_content}  </main>
  
  <script>
    // 滚动时激活当前导航项
    document.addEventListener('DOMContentLoaded', function() {{
      const sections = document.querySelectorAll('.content-section');
      const navLinks = document.querySelectorAll('.nav-link');
      
      // 初始状态下激活第一个导航项
      if (navLinks.length > 0) {{
        navLinks[0].classList.add('active');
      }}
      
      // 滚动时更新激活状态
      window.addEventListener('scroll', function() {{
        let current = '';
        
        sections.forEach(function(section) {{
          const sectionTop = section.offsetTop;
          const sectionHeight = section.clientHeight;
          if(scrollY >= (sectionTop - 200)) {{
            current = section.getAttribute('id');
          }}
        }});
        
        navLinks.forEach(function(link) {{
          link.classList.remove('active');
          if(link.getAttribute('href').substring(1) === current) {{
            link.classList.add('active');
          }}
        }});
      }});
    }});
  </script>
</body>
</html>'''
    
    return html


def generate_grid_template(sections):
    from html import escape
    
    # 生成图表卡片内容
    cards_html = ""
    
    for i, section in enumerate(sections, 1):
        title = section["title"]
        cards_html += f'<div class="section-title"><h2>{i}. {escape(title)}</h2></div>\n'
        cards_html += '<div class="card-grid">\n'
        
        # 添加图表卡片
        for chart in section["charts"]:
            img = chart.get("img", "")
            caption = chart.get("caption", "")
            cards_html += f'''  <div class="card">
    <img src="{img}" alt="{escape(caption)}">
    <div class="card-caption">{escape(caption)}</div>
  </div>\n'''
            
        cards_html += '</div>\n'
        
        # 添加章节小结
        summary = section.get("summary", "")
        if summary:
            cards_html += f'<div class="summary"><p><strong>Chapter Summary：</strong> {escape(summary)}</p></div>\n'
    
    # 组装HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>数据分析报告</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
  <style>
    body {{ font-family: 'Inter', sans-serif; background-color: #f8f9fa; color: #333; max-width: 1200px; margin: 0 auto; padding: 2rem; }}
    h1 {{ text-align: center; color: #303f9f; margin-bottom: 2rem; font-size: 2.2rem; }}
    .section-title {{ width: 100%; margin: 2rem 0 1rem 0; }}
    h2 {{ color: #303f9f; border-bottom: 2px solid #5c6bc0; padding-bottom: 0.5rem; }}
    .card-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(450px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }}
    .card {{ background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: transform 0.3s, box-shadow 0.3s; }}
    .card:hover {{ transform: translateY(-5px); box-shadow: 0 6px 12px rgba(0,0,0,0.15); }}
    .card img {{ width: 100%; height: auto; display: block; }}
    .card-caption {{ padding: 1rem; font-size: 0.95rem; color: #555; }}
    .summary {{ background-color: white; border-left: 4px solid #5c6bc0; padding: 1.5rem; margin: 0 0 3rem 0; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
    @media (max-width: 768px) {{
      .card-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <h1>数据分析报告</h1>
{cards_html}</body>
</html>'''
    
    return html


def generate_dark_template(sections):
    from html import escape
    
    def highlight_keywords_dark(text):
        if not text:
            return ""
        # 这里可以添加关键词高亮逻辑
        return text
    
    html_head = '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>数据分析报告</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
  <style>
    body { 
      font-family: 'Inter', sans-serif; 
      background-color: #1a1a1a; 
      color: #e0e0e0; 
      max-width: 1000px; 
      margin: auto; 
      padding: 2rem;
      line-height: 1.6;
    }
    h1 { 
      text-align: center; 
      color: #61dafb; 
      border-bottom: 3px solid #3498db; 
      padding-bottom: 0.5rem;
      margin-bottom: 2rem;
    }
    h2 { 
      background-color: #2c2c2c; 
      color: #61dafb; 
      padding: 1rem 1.5rem; 
      border-radius: 8px; 
      margin-top: 3rem; 
      border-left: 5px solid #3498db;
      font-weight: 600;
    }
    .chart-card { 
      background: #2c2c2c; 
      border-radius: 8px; 
      padding: 1.5rem; 
      box-shadow: 0 4px 20px rgba(0,0,0,0.3); 
      margin-bottom: 2rem; 
      border: 1px solid #444;
    }
    .chart-card img { 
      width: 100%; 
      border-radius: 6px; 
      margin: 1rem 0; 
      border: 1px solid #444;
    }
    .chart-caption { 
      color: #a0a0a0; 
      margin-bottom: 1rem;
      font-size: 0.95rem;
    }
    .highlight { 
      color: #61dafb; 
      font-weight: bold; 
    }
    .summary { 
      background-color: #2c2c2c; 
      border-left: 5px solid #3498db; 
      padding: 1.5rem; 
      border-radius: 6px; 
      margin-top: 2rem; 
      font-size: 0.95rem;
      box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    }
  </style>
</head>
<body>
  <h1>数据分析报告</h1>
'''

    html_body = ""
    for section in sections:
        title = section["title"]
        html_body += f"<h2>{escape(title)}</h2>\n"
        for chart in section["charts"]:
            caption = chart.get("caption", "")
            img = chart.get("img", "")
            html_body += f"""
        <div class="chart-card">
            <div class="chart-caption">{escape(caption)}</div>
            <img src="{img}" alt="{escape(caption)}">
        </div>
"""
        summary = section.get("summary", "")
        if summary:
            html_body += f"<div class='summary'><strong>Chapter Summary：</strong> {highlight_keywords_dark(summary)}</div>\n"

    html_tail = "</body></html>"

    return html_head + html_body + html_tail


def generate_magazine_template(sections):
    from html import escape
    
    # 添加高亮关键词的辅助函数
    def highlight_keywords(text):
        if not text:
            return ""
        # 这里可以添加关键词高亮逻辑
        return text
    
    magazine_content = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>数据分析杂志</title>
        <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;700;900&family=Source+Sans+Pro:wght@300;400;600&display=swap" rel="stylesheet">
        <style>
            :root {
                --accent-color: #e63946;
                --heading-color: #1d3557;
                --text-color: #333;
                --bg-color: #fff;
                --light-bg: #f1faee;
                --border-color: #eee;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Source Sans Pro', sans-serif;
                color: var(--text-color);
                background-color: var(--bg-color);
                line-height: 1.6;
                max-width: 1200px;
                margin: 0 auto;
                padding: 0 2rem;
            }
            
            .magazine-header {
                padding: 3rem 0;
                text-align: center;
                border-bottom: 1px solid var(--border-color);
                margin-bottom: 3rem;
            }
            
            .magazine-title {
                font-family: 'Playfair Display', serif;
                font-weight: 900;
                font-size: 3.5rem;
                color: #000;
                margin-bottom: 1rem;
                letter-spacing: -0.5px;
            }
            
            .magazine-subtitle {
                font-family: 'Source Sans Pro', sans-serif;
                font-weight: 300;
                font-size: 1.2rem;
                color: #777;
                max-width: 700px;
                margin: 0 auto;
            }
            
            h2 {
                font-family: 'Playfair Display', serif;
                font-weight: 700;
                font-size: 2.5rem;
                color: var(--heading-color);
                margin-bottom: 1.5rem;
                line-height: 1.2;
            }
            
            .magazine-article {
                margin-bottom: 5rem;
                padding-bottom: 3rem;
                border-bottom: 1px solid var(--border-color);
            }
            
            .magazine-article:last-child {
                border-bottom: none;
            }
            
            .chapter-summary {
                font-size: 1.2rem;
                line-height: 1.7;
                margin-bottom: 2rem;
                color: #555;
                padding: 2rem;
                background: var(--light-bg);
                border-radius: 8px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            }
            
            .gallery {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 2rem;
                margin: 2rem 0;
            }
            
            figure {
                margin: 0;
                background: var(--light-bg);
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 8px 30px rgba(0,0,0,0.12);
                transition: transform 0.3s;
            }
            
            figure:hover {
                transform: translateY(-5px);
            }
            
            figure img {
                width: 100%;
                display: block;
            }
            
            .figure-caption {
                padding: 1rem;
                font-size: 0.95rem;
                color: #666;
                background: white;
                border-top: 1px solid var(--border-color);
            }
            
            .side-by-side {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 3rem;
                align-items: start;
            }
            
            .visual-content {
                display: grid;
                gap: 2rem;
            }
            
            .feature-header {
                margin-bottom: 2rem;
            }
            
            .feature-hero {
                position: relative;
                margin-bottom: 2rem;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 10px 30px rgba(0,0,0,0.15);
            }
            
            .feature-hero img {
                width: 100%;
                display: block;
            }
            
            .feature-content {
                padding: 2rem;
                background: var(--light-bg);
                border-radius: 8px;
            }
            
            .secondary-visuals {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 2rem;
                margin-top: 2rem;
            }
            
            .highlight {
                color: var(--accent-color);
                font-weight: 600;
            }
            
            @media (max-width: 768px) {
                .side-by-side {
                    grid-template-columns: 1fr;
                }
                
                .magazine-title {
                    font-size: 2.5rem;
                }
                
                h2 {
                    font-size: 2rem;
                }
            }
        </style>
    </head>
    <body>
        <header class="magazine-header">
            <h1 class="magazine-title">Data Analysis Report</h1>
            <p class="magazine-subtitle">A comprehensive analysis of the dataset</p>
        </header>
    '''
    
    for section in sections:
        title = section.get("title", "")
        summary = section.get("summary", "")
        charts = section.get("charts", [])
        
        # 随机选择布局风格
        layout_styles = ["full-width", "side-by-side", "feature"]
        layout_style = random.choice(layout_styles)
        
        if layout_style == "full-width":
            magazine_content += f'''
            <article class="magazine-article full-width">
                <h2>{escape(title)}</h2>
                <div class="chapter-summary">
                    {highlight_keywords(summary)}
                </div>
                <div class="gallery">
            '''
            
            for chart in charts:
                img = chart.get("img", "")
                caption = chart.get("caption", "")
                magazine_content += f'''
                    <figure>
                        <img src="{img}" alt="图表">
                        <figcaption class="figure-caption">{escape(caption)}</figcaption>
                    </figure>
                '''
            
            magazine_content += '</div></article>'
            
        elif layout_style == "side-by-side":
            magazine_content += f'''
            <article class="magazine-article side-by-side">
                <div class="text-content">
                    <h2>{escape(title)}</h2>
                    <div class="chapter-summary">
                        {highlight_keywords(summary)}
                    </div>
                </div>
                <div class="visual-content">
            '''
            
            for chart in charts:
                img = chart.get("img", "")
                caption = chart.get("caption", "")
                magazine_content += f'''
                    <figure>
                        <img src="{img}" alt="图表">
                        <figcaption class="figure-caption">{escape(caption)}</figcaption>
                    </figure>
                '''
            
            magazine_content += '</div></article>'
            
        elif layout_style == "feature":
            magazine_content += f'''
            <article class="magazine-article feature">
                <div class="feature-header">
                    <h2>{escape(title)}</h2>
                </div>
                <div class="feature-content">
                    <div class="chapter-summary">
                        {highlight_keywords(summary)}
                    </div>
                </div>
            '''
            
            if charts and len(charts) > 0:
                featured_chart = charts[0]
                magazine_content += f'''
                <div class="feature-hero">
                    <img src="{featured_chart.get('img', '')}" alt="特色图表">
                    <figcaption class="figure-caption">{escape(featured_chart.get('caption', ''))}</figcaption>
                </div>
                '''
                
                # 添加其余图表
                if len(charts) > 1:
                    magazine_content += '<div class="secondary-visuals">\n'
                    for chart in charts[1:]:
                        img = chart.get("img", "")
                        caption = chart.get("caption", "")
                        magazine_content += f'''
                        <figure>
                            <img src="{img}" alt="图表">
                            <figcaption class="figure-caption">{escape(caption)}</figcaption>
                        </figure>
                        '''
                    magazine_content += '</div>\n'
            
            magazine_content += '</article>'
    
    magazine_content += '''
    </body>
    </html>
    '''
    
    return magazine_content


def generate_dashboard_template(sections):
    from html import escape
    
    def highlight_keywords(text):
        if not text:
            return ""
        # 这里可以添加关键词高亮逻辑
        return text
    
    # 生成仪表盘图表面板
    panels_html = ""
    
    for i, section in enumerate(sections):
        title = section.get("title", "")
        charts = section.get("charts", [])
        summary = section.get("summary", "")
        
        panels_html += f'''
        <div class="dashboard-panel">
            <div class="panel-header">
                <h2>{escape(title)}</h2>
                <div class="panel-actions">
                    <button class="panel-action" title="刷新"><i class="icon">↻</i></button>
                    <button class="panel-action" title="更多选项"><i class="icon">⋮</i></button>
                </div>
            </div>
            <div class="panel-body">
        '''
        
        # 为每个图表创建仪表盘卡片
        if charts:
            panels_html += '<div class="chart-container">\n'
            for chart in charts:
                caption = chart.get("caption", "")
                img = chart.get("img", "")
                panels_html += f'''
                <div class="chart-card">
                    <img src="{img}" alt="{escape(caption)}">
                    <div class="chart-caption">{escape(caption)}</div>
                </div>
                '''
            panels_html += '</div>\n'
        
        # 添加仪表盘注释部分
        if summary:
            panels_html += f'''
            <div class="panel-footer">
                <div class="insight-box">
                    <div class="insight-icon">💡</div>
                    <div class="insight-text">
                        <strong>Chapter Summary：</strong> {highlight_keywords(summary)}
                    </div>
                </div>
            </div>
            '''
        
        panels_html += '''
            </div>
        </div>
        '''
    
    # 构建完整的HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据分析仪表盘</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-color: #f5f7fa;
            --panel-bg: #ffffff;
            --accent-color: #4361ee;
            --secondary-color: #3f37c9;
            --success-color: #4cc9f0;
            --warning-color: #f72585;
            --text-color: #2b2d42;
            --text-light: #6c757d;
            --border-color: #e9ecef;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            padding: 2rem;
            line-height: 1.5;
        }}
        
        .dashboard-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
        }}
        
        .dashboard-title {{
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--text-color);
        }}
        
        .dashboard-controls {{
            display: flex;
            gap: 1rem;
        }}
        
        .dashboard-control {{
            background-color: var(--panel-bg);
            border: none;
            border-radius: 4px;
            padding: 0.5rem 1rem;
            font-size: 0.875rem;
            font-weight: 500;
            color: var(--text-color);
            cursor: pointer;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            transition: all 0.2s;
        }}
        
        .dashboard-control:hover {{
            background-color: var(--accent-color);
            color: white;
        }}
        
        .dashboard-panels {{
            display: flex;
            flex-direction: column;
            gap: 2rem;
        }}
        
        .dashboard-panel {{
            background-color: var(--panel-bg);
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            overflow: hidden;
        }}
        
        .panel-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.25rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
        }}
        
        .panel-header h2 {{
            font-size: 1.15rem;
            font-weight: 600;
            color: var(--text-color);
            margin: 0;
        }}
        
        .panel-actions {{
            display: flex;
            gap: 0.5rem;
        }}
        
        .panel-action {{
            background: none;
            border: none;
            padding: 0.25rem;
            cursor: pointer;
            border-radius: 4px;
            color: var(--text-light);
            font-size: 1rem;
            transition: all 0.2s;
        }}
        
        .panel-action:hover {{
            background-color: rgba(0,0,0,0.05);
            color: var(--accent-color);
        }}
        
        .panel-body {{
            padding: 1.5rem;
        }}
        
        .chart-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 2rem;
        }}
        
        .chart-card {{
            border-radius: 8px;
            overflow: hidden;
            background-color: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }}
        
        .chart-card img {{
            width: 100%;
            height: auto;
            display: block;
        }}
        
        .chart-caption {{
            padding: 1rem;
            font-size: 0.875rem;
            color: var(--text-light);
            border-top: 1px solid var(--border-color);
        }}
        
        .panel-footer {{
            padding: 1rem 1.5rem;
            background-color: rgba(0,0,0,0.02);
            border-top: 1px solid var(--border-color);
        }}
        
        .insight-box {{
            display: flex;
            gap: 1rem;
            align-items: flex-start;
        }}
        
        .insight-icon {{
            font-size: 1.5rem;
            color: var(--accent-color);
        }}
        
        .insight-text {{
            font-size: 0.875rem;
            color: var(--text-color);
            line-height: 1.5;
        }}
        
        .highlight {{
            color: var(--accent-color);
            font-weight: 500;
        }}
        
        .icon {{
            display: inline-block;
            font-style: normal;
        }}
        
        @media (max-width: 768px) {{
            body {{
                padding: 1rem;
            }}
            
            .chart-container {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="dashboard-header">
        <h1 class="dashboard-title">数据分析仪表盘</h1>
        <div class="dashboard-controls">
            <button class="dashboard-control">导出报告</button>
            <button class="dashboard-control">刷新数据</button>
        </div>
    </div>
    
    <div class="dashboard-panels">
        {panels_html}
    </div>
</body>
</html>'''
    
    return html


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate styled report from Markdown.')
    parser.add_argument('markdown_file', type=str, help='Path to the input Markdown file')
    parser.add_argument('--output', type=str, default='report_generated.html', help='Output HTML file name')
    parser.add_argument('--template', type=str, choices=['orange', 'blue', 'green', 'purple', 'sidebar', 'grid', 'dark', 'magazine', 'dashboard'], default='orange', help='Template style to use')
    args = parser.parse_args()

    # Get absolute path for the markdown file
    md_path = os.path.abspath(args.markdown_file)
    
    # Determine output path - place HTML in same directory as markdown file if no path specified
    output_path = args.output
    if not os.path.dirname(output_path):
        md_dir = os.path.dirname(md_path)
        output_path = os.path.join(md_dir, output_path)
    
    sections = parse_markdown(md_path)
    html = fill_template(sections, args.template)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ Report generated: {output_path}")
