import markdown
from bs4 import BeautifulSoup
import os
import argparse
from pathlib import Path
import random
import urllib.parse
import json

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
    current_key_insights = []  # 用于存储关键指标
    
    for tag in soup.find_all():
        if tag.name == 'h2':
            # 如果已经有当前章节，先保存它
            if current_section:
                if current_key_insights:
                    current_section["key_insights"] = current_key_insights
                sections.append(current_section)
            # 开始新的章节
            title_text = tag.get_text(strip=True)
            
            # 处理字典格式的标题
            if title_text.startswith("{'title': '") and title_text.endswith("'}"):
                title_text = title_text[len("{'title': '"):-2]
            
            current_section = {
                "title": title_text,
                "charts": [],
                "summary": "",
                "key_insights": []
            }
            current_charts = []
            current_caption = ""
            current_key_insights = []  # 重置关键指标列表
        elif tag.name == 'blockquote':
            current_caption = tag.get_text(strip=True)
        elif tag.name == 'img':
            img_path = tag.get('src', '')
            # Convert relative path to absolute path based on markdown file location
            if img_path and not os.path.isabs(img_path):
                img_path = os.path.join(md_dir, img_path)
            
            # 尝试查找对应的JSON配置文件
            config_path = None
            vegalite_config_path = None
            
            if img_path.lower().endswith('.png'):
                # 构建可能的JSON配置文件路径
                img_dir = os.path.dirname(img_path)
                img_filename = os.path.basename(img_path)
                img_basename = os.path.splitext(img_filename)[0]
                
                # 设置潜在的配置文件所在目录
                # 首先尝试在同级的chart_configs目录查找
                config_dir = os.path.join(os.path.dirname(img_dir), "chart_configs")
                
                # 查找Vega-Lite配置文件
                vegalite_config_dir = os.path.join(os.path.dirname(img_dir), "vegalite_configs")
                
                # 尝试多种可能的配置文件名
                possible_config_paths = [
                    os.path.join(config_dir, f"{img_basename}.json"),
                    os.path.join(config_dir, f"{img_basename}_edited.json"),
                    # 尝试在同目录查找
                    os.path.join(img_dir, f"{img_basename}.json"),
                    os.path.join(img_dir, f"{img_basename}_config.json")
                ]
                
                # 尝试多种可能的Vega-Lite配置文件名
                possible_vegalite_paths = [
                    os.path.join(vegalite_config_dir, f"{img_basename}.json"),
                    os.path.join(vegalite_config_dir, f"{escape_filename(img_basename)}.json"),
                    os.path.join(vegalite_config_dir, f"{escape_filename(current_caption)}.json")
                ]
                
                for path in possible_config_paths:
                    if os.path.exists(path):
                        config_path = path
                        print(f"找到图表配置文件: {config_path}")
                        break
                
                for path in possible_vegalite_paths:
                    if os.path.exists(path):
                        vegalite_config_path = path
                        print(f"找到Vega-Lite配置文件: {vegalite_config_path}")
                        break
            
            chart_info = {
                "img": img_path,
                "caption": current_caption
            }
            
            # 如果找到了配置文件，添加到图表信息中
            if config_path:
                chart_info["config"] = config_path
            
            # 如果找到了Vega-Lite配置文件，添加到图表信息中
            if vegalite_config_path:
                chart_info["vegalite_config"] = vegalite_config_path
                
            current_section["charts"].append(chart_info)
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
        elif tag.name == 'h3' and tag.get_text(strip=True) == "Key Insights":
            # 获取所有后续的li标签，直到遇到下一个h2或h3
            next_tag = tag.find_next()
            while next_tag and next_tag.name not in ['h2', 'h3']:
                if next_tag.name == 'li' or next_tag.name == 'p':
                    insight_text = next_tag.get_text(strip=True)
                    if insight_text:  # 确保不是空字符串
                        current_key_insights.append(insight_text)
                next_tag = next_tag.find_next()
        # 检查是否有包含"关键指标"或"Key Metrics"的段落
        elif tag.name == 'p':
            text = tag.get_text(strip=True)
            if "关键指标:" in text or "关键指标：" in text or "Key Metrics:" in text:
                # 提取冒号后面的内容作为关键指标
                sep = ":" if ":" in text else "："
                insight_text = text.split(sep, 1)[1].strip()
                if insight_text:
                    current_key_insights.append(insight_text)

    # 不要忘记添加最后一个章节
    if current_section:
        if current_key_insights:
            current_section["key_insights"] = current_key_insights
        sections.append(current_section)
    return sections

# 辅助函数，将文件名中的特殊字符转换为下划线，避免在查找文件时出错
def escape_filename(name):
    if not name:
        return "unnamed"
    # 将特殊字符转换为下划线，保留字母、数字和常见标点
    import re
    return re.sub(r'[^\w\-\.]', '_', name)

# 移动辅助函数到前面，这样其他函数可以引用它
# 辅助函数：将绝对路径转换为相对路径
def convert_to_relative_path(path):
    # 检测路径是否为绝对路径
    if os.path.isabs(path):
        # 从绝对路径中提取关键部分，通常是"storyteller"目录后的部分
        parts = path.split(os.sep)
        try:
            storyteller_index = parts.index("storyteller")
            # 从storyteller开始构建相对路径
            relative_path = "/".join(parts[storyteller_index:])
            return relative_path
        except ValueError:
            # 如果找不到storyteller目录，返回原路径
            return path
    return path

# 添加一个通用函数来处理Vega-Lite配置
def prepare_vegalite_config(sections):
    """
    为sections中的所有图表准备Vega-Lite配置
    返回：
    - chart_configs: 包含所有图表配置的列表
    - chart_id_counter: 用于生成唯一图表ID的计数器
    """
    # 用于存储所有图表配置的数组
    chart_configs = []
    
    # 为每个图表创建唯一的ID
    chart_id_counter = 0
    
    for section in sections:
        for chart in section.get("charts", []):
            vegalite_config_path = chart.get("vegalite_config", "")
            img_path = chart.get("img", "")
            
            if vegalite_config_path:
                # 如果有配置文件，使用Vega-Lite渲染
                chart_id = f"vegalite_chart_{chart_id_counter}"
                chart_id_counter += 1
                
                # 读取JSON配置文件内容
                try:
                    with open(vegalite_config_path, 'r', encoding='utf-8') as f:
                        vegalite_spec = json.load(f)
                    
                    # 获取相对路径并保存图片路径
                    relative_img_path = convert_to_relative_path(img_path)
                    
                    # 保存配置信息
                    chart_configs.append({
                        "chartId": chart_id,
                        "vegaliteSpec": vegalite_spec,
                        "imgPath": relative_img_path
                    })
                    
                    # 在图表对象上添加chart_id属性，以便模板函数使用
                    chart["chart_id"] = chart_id
                    # 标记为Vega-Lite图表
                    chart["is_vegalite"] = True
                    
                except Exception as e:
                    print(f"读取Vega-Lite配置文件失败: {vegalite_config_path}, 错误: {e}")
                    continue
    
    return chart_configs, chart_id_counter

# 生成Vega-Lite渲染脚本
def generate_vegalite_script(chart_configs):
    """
    根据图表配置生成Vega-Lite渲染脚本
    """
    if not chart_configs:
        return ""
        
    chart_script = """
<script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
<script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
<script>
// 存储图表实例的对象
const vegaChartInstances = {};

// 初始化图表的函数
function initializeVegaChart(chartId, vegaSpec, fallbackImgPath) {
    const container = document.getElementById(chartId);
    
    if (!container) {
        console.error(`Container for chart ${chartId} not found`);
        return;
    }
    
    try {
        console.log(`Initializing Vega-Lite chart ${chartId}`);
        
        // 使用vega-embed渲染图表
        vegaEmbed('#' + chartId, vegaSpec, {
            renderer: 'canvas',
            actions: true
        }).then(result => {
            console.log(`Chart ${chartId} rendered successfully`);
            vegaChartInstances[chartId] = result;
            container.setAttribute('data-initialized', 'true');
        }).catch(error => {
            console.error(`Error rendering chart ${chartId}:`, error);
            fallbackToImage(chartId, fallbackImgPath);
        });
        
    } catch (error) {
        console.error(`Error creating chart ${chartId}:`, error);
        fallbackToImage(chartId, fallbackImgPath);
        return null;
    }
}

// 回退到静态图片
function fallbackToImage(chartId, fallbackImgPath) {
    const container = document.getElementById(chartId);
    if (!container || !fallbackImgPath) return;
    
    console.log(`Falling back to image for ${chartId}: ${fallbackImgPath}`);
    
    // 创建图片元素
    const img = document.createElement('img');
    img.src = fallbackImgPath;
    img.alt = 'Chart fallback image';
    img.style.width = '100%';
    img.style.height = '100%';
    img.style.objectFit = 'contain';
    
    // 替换容器内容
    container.innerHTML = '';
    container.appendChild(img);
}

// 页面加载完成后初始化所有图表
document.addEventListener('DOMContentLoaded', function() {
"""
    # 添加所有图表配置并初始化
    for i, config in enumerate(chart_configs):
        # 将Python字典转换为JSON字符串
        json_str = json.dumps(config['vegaliteSpec'])
        chart_script += f"    const vegaSpec_{i} = {json_str};\n"
        chart_script += f"    initializeVegaChart('{config['chartId']}', vegaSpec_{i}, '{config['imgPath']}');\n"
    
    chart_script += """
    // 添加一个定时器检查图表是否正确渲染
    setTimeout(function() {
        document.querySelectorAll('div[id^="vegalite_chart_"]').forEach(container => {
            const chartId = container.id;
            // 检查该图表是否已标记为初始化
            if (!container.getAttribute('data-initialized')) {
                console.log(`Chart ${chartId} was not initialized properly, falling back to image`);
                const imgPath = container.getAttribute('data-fallback');
                if (imgPath) {
                    fallbackToImage(chartId, imgPath);
                }
            }
        });
    }, 2000); // 延长等待时间到2秒
});
</script>
"""
    return chart_script

def fill_template(sections, template_type="dashboard"):
    from pathlib import Path

    def highlight_keywords(text):
        if not text:
            return ""
        # 这里可以添加关键词高亮逻辑
        return text

    from html import escape
    
    # 使用特殊的布局模板
    if template_type == "sidebar":
        return generate_sidebar_template(sections)
    elif template_type == "grid":
        return generate_grid_template(sections)
    elif template_type == "magazine":
        return generate_magazine_template(sections)
    elif template_type == "dashboard":
        return generate_dashboard_template(sections)
    else:
        # 默认使用dashboard模板
        return generate_dashboard_template(sections)


def generate_sidebar_template(sections):
    from html import escape
    
    # 处理图表配置，使用Vega-Lite
    chart_configs, chart_id_counter = prepare_vegalite_config(sections)
    
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
      
        # 添加关键指标（如果有的话）
        key_insights = section.get("key_insights", [])
        if key_insights:
            main_content += f'      <div class="insights-container">\n'
            for insight in key_insights:
                main_content += f'        <div class="key-insight"><div class="key-insight-content">{escape(insight)}</div></div>\n'
            main_content += f'      </div>\n'
      
        # 添加图表
        for chart in section["charts"]:
            img = chart.get("img", "")
            caption = chart.get("caption", "")
            vegalite_config = chart.get("vegalite_config", "")
            is_vegalite = chart.get("is_vegalite", False)
            
            if is_vegalite:
                chart_id = chart.get("chart_id", "")
                
                # 添加data-fallback属性以供回退使用
                relative_img_path = convert_to_relative_path(img)
                main_content += f'''      <div class="chart-card">
        <div class="chart-wrapper">
          <div id="{chart_id}" data-fallback="{relative_img_path}" class="chart-container"></div>
        </div>
        <div class="caption">{escape(caption)}</div>
      </div>\n'''
            else:
                # 获取相对路径
                relative_img_path = convert_to_relative_path(img)
                main_content += f'''      <div class="chart-card">
        <div class="chart-wrapper">
          <img src="{relative_img_path}" width="100%">
        </div>
        <div class="caption">{escape(caption)}</div>
      </div>\n'''
            
        # 添加章节小结
        summary = section.get("summary", "")
        if summary:
            main_content += f'      <div class="summary"><div class="summary-icon">📊</div><div class="summary-content"><p><strong>Chapter Summary：</strong> {escape(summary)}</p></div></div>\n'
            
        main_content += '    </section>\n\n'
    
    # 生成Vega-Lite脚本
    chart_script = generate_vegalite_script(chart_configs)
    
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
    
    .chart-card {{
      margin: 2rem 0;
      border-radius: 0.5rem;
      overflow: hidden;
      box-shadow: var(--shadow-md);
      transition: all 0.3s ease;
      display: flex;
      flex-direction: column;
    }}
    
    .chart-card:hover {{
      transform: translateY(-4px);
      box-shadow: var(--shadow-lg);
    }}
    
    .chart-wrapper {{
      position: relative;
      height: 400px;
      width: 100%;
      overflow: hidden;
    }}
    
    .chart-wrapper img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }}
    
    .chart-container {{
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
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
    
    .key-insight {{
      background-color: rgba(79, 70, 229, 0.1);
      border-radius: 8px;
      padding: 1rem 1.2rem;
      margin: 1.5rem 0;
      position: relative;
      border-left: 4px solid var(--primary-color);
    }}
    
    .key-insight:before {{
      content: "💡";
      font-size: 1.2rem;
      position: absolute;
      left: -12px;
      top: -12px;
      background: white;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: var(--shadow-sm);
    }}
    
    .key-insight-content {{
      font-weight: 500;
      color: var(--primary-dark);
    }}
    
    .insights-container {{
      margin-bottom: 2rem;
    }}
    
    /* Vega-Lite特定样式 */
    .vega-embed {{
      width: 100%;
      height: 100%;
    }}
    .vega-embed .vega-actions {{
      top: 0;
      right: 0;
      padding: 6px;
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
{chart_script}</body>
</html>'''
    
    return html


def generate_grid_template(sections):
    from html import escape
    import urllib.parse
    import os.path
    
    # 处理图表配置
    chart_configs, chart_id_counter = prepare_vegalite_config(sections)
    
    # 生成图表卡片内容
    cards_html = ""
    
    for i, section in enumerate(sections, 1):
        title = section["title"]
        cards_html += f'<div class="section-title"><h2>{i}. {escape(title)}</h2></div>\n'
        
        # 添加关键指标（如果有的话）
        key_insights = section.get("key_insights", [])
        if key_insights:
            cards_html += f'<div class="insights-grid">\n'
            for insight in key_insights:
                cards_html += f'  <div class="insight-card">\n'
                cards_html += f'    <div class="insight-icon">💡</div>\n'
                cards_html += f'    <div class="insight-content">{escape(insight)}</div>\n'
                cards_html += f'  </div>\n'
            cards_html += f'</div>\n'
        
        cards_html += '<div class="card-grid">\n'
        
        for chart in section["charts"]:
            img = chart.get("img", "")
            caption = chart.get("caption", "")
            config = chart.get("config", "")
            is_vegalite = chart.get("is_vegalite", False)
            
            cards_html += f'  <div class="card">\n'
            
            # 获取相对路径
            relative_img_path = convert_to_relative_path(img)
            
            if is_vegalite:
                # 如果是Vega-Lite图表，使用div容器
                chart_id = chart.get("chart_id", "")
                cards_html += f'    <div class="chart-wrapper"><div id="{chart_id}" data-fallback="{relative_img_path}" class="chart-container"></div></div>\n'
            elif config:
                # 如果有配置文件但不是Vega-Lite，使用Canvas渲染
                chart_id = chart.get("chart_id", "")
                cards_html += f'    <div class="chart-wrapper">\n'
                cards_html += f'      <canvas id="{chart_id}"></canvas>\n'
                cards_html += f'    </div>\n'
            else:
                # 没有配置文件，使用静态图片
                cards_html += f'    <div class="chart-wrapper"><img src="{relative_img_path}" alt="{escape(caption)}"></div>\n'
            
            cards_html += f'    <div class="card-caption">{escape(caption)}</div>\n'
            cards_html += '  </div>\n'
            
        cards_html += '</div>\n'
        
        # 添加章节小结
        summary = section.get("summary", "")
        if summary:
            cards_html += f'<div class="summary"><p><strong>Chapter Summary：</strong> {escape(summary)}</p></div>\n'
    
    # 生成Chart.js脚本
    chart_script = generate_vegalite_script(chart_configs)
    
    # 组装HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>数据分析报告</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
  <style>
    body {{ font-family: 'Inter', sans-serif; background-color: #f8f9fa; color: #333; max-width: 1200px; margin: 0 auto; padding: 2rem; }}
    h1 {{ text-align: center; color: #303f9f; margin-bottom: 2rem; font-size: 2.2rem; }}
    .section-title {{ width: 100%; margin: 2rem 0 1rem 0; }}
    h2 {{ color: #303f9f; border-bottom: 2px solid #5c6bc0; padding-bottom: 0.5rem; }}
    .card-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(450px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }}
    .card {{ 
      background: white; 
      border-radius: 8px; 
      overflow: hidden; 
      box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
      transition: transform 0.3s, box-shadow 0.3s;
      display: flex;
      flex-direction: column;
    }}
    .card:hover {{ transform: translateY(-5px); box-shadow: 0 6px 12px rgba(0,0,0,0.15); }}
    
    .chart-wrapper {{ 
      flex: 1;
      position: relative;
      min-height: 300px;
      width: 100%;
      overflow: hidden;
    }}
    
    .chart-container {{ 
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
    }}
    
    .card img {{ 
      width: 100%; 
      height: 100%;
      object-fit: contain;
      display: block; 
    }}
    
    .card-caption {{ 
      padding: 1rem; 
      font-size: 0.95rem; 
      color: #555; 
      border-top: 1px solid #eee;
      background-color: #fcfcfc;
    }}
    
    .summary {{ background-color: white; border-left: 4px solid #5c6bc0; padding: 1.5rem; margin: 0 0 3rem 0; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
    
    .insights-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }}
    .insight-card {{ 
      background: white; 
      border-radius: 8px; 
      padding: 1.2rem 1.5rem 1.2rem 1rem; 
      box-shadow: 0 4px 6px rgba(0,0,0,0.07); 
      border-left: 4px solid #4f46e5; 
      display: flex;
      align-items: flex-start;
      transition: transform 0.3s, box-shadow 0.3s;
    }}
    .insight-card:hover {{ transform: translateY(-3px); box-shadow: 0 6px 12px rgba(0,0,0,0.1); }}
    .insight-icon {{ font-size: 1.5rem; margin-right: 1rem; color: #4f46e5; }}
    .insight-content {{ font-size: 0.95rem; color: #333; font-weight: 500; line-height: 1.5; }}
    @media (max-width: 768px) {{
      .card-grid {{ grid-template-columns: 1fr; }}
    }}
    /* Vega-Lite特定样式 */
    .vega-embed {{
      width: 100%;
      height: 100%;
    }}
    .vega-embed .vega-actions {{
      top: 0;
      right: 0;
      padding: 6px;
    }}
  </style>
</head>
<body>
  <h1>数据分析报告</h1>
{cards_html}{chart_script}</body>
</html>'''
    
    return html


def generate_dark_template(sections):
    from html import escape
    
    # 处理图表配置
    chart_configs, chart_id_counter = prepare_vegalite_config(sections)
    
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
  <script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
  <script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
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
    .chart-container {
      height: 400px;
      position: relative;
      margin: 1rem 0;
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
    .key-insight {
      background-color: #2a2a2a;
      border-radius: 8px;
      padding: 1.2rem;
      margin: 1.5rem 0;
      border-left: 4px solid #61dafb;
      position: relative;
      box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    }
    .key-insight:before {
      content: "💡";
      font-size: 1.2rem;
      position: absolute;
      left: -12px;
      top: -12px;
      background: #333;
      width: 28px;
      height: 28px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
    .key-insight-content {
      color: #e0e0e0;
      font-weight: 500;
      padding-left: 0.5rem;
    }
    .insights-container {
      margin: 2rem 0;
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
        
        # 添加关键指标（如果有的话）
        key_insights = section.get("key_insights", [])
        if key_insights:
            html_body += f'<div class="insights-container">\n'
            for insight in key_insights:
                html_body += f'<div class="key-insight"><div class="key-insight-content">{escape(insight)}</div></div>\n'
            html_body += f'</div>\n'
            
        for chart in section["charts"]:
            caption = chart.get("caption", "")
            img = chart.get("img", "")
            config = chart.get("config", "")
            
            html_body += f'<div class="chart-card">\n'
            html_body += f'<div class="chart-caption">{escape(caption)}</div>\n'
            
            if config:
                chart_id = chart.get("chart_id", "")
                html_body += f'<div class="chart-container">\n'
                html_body += f'<canvas id="{chart_id}"></canvas>\n'
                html_body += f'</div>\n'
            else:
                # 获取相对路径
                relative_img_path = convert_to_relative_path(img)
                html_body += f'<img src="{relative_img_path}" alt="{escape(caption)}">\n'
                
            html_body += f'</div>\n'
            
        summary = section.get("summary", "")
        if summary:
            html_body += f"<div class='summary'><strong>Chapter Summary：</strong> {highlight_keywords_dark(summary)}</div>\n"

    # 生成Chart.js脚本
    chart_script = generate_vegalite_script(chart_configs)
    
    html_tail = chart_script + "</body></html>"

    return html_head + html_body + html_tail


def generate_magazine_template(sections):
    from html import escape
    
    # 处理图表配置
    chart_configs, chart_id_counter = prepare_vegalite_config(sections)
    
    magazine_content = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>数据分析报告</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/vega@5"></script>
        <script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script>
        <script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>
        <style>
            :root {
                --primary-color: #0066cc;
                --secondary-color: #00994d;
                --text-color: #333333;
                --bg-color: #f0f2f5;
                --paper-color: #ffffff;
                --border-color: #e2e8f0;
                --highlight-bg: #e6f3ff;
                --chart-bg-1: #e6ffe6;
                --chart-bg-2: #f0f9ff;
            }
            
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Inter', sans-serif;
                color: var(--text-color);
                background-color: var(--bg-color);
                line-height: 1.6;
                padding: 2rem;
                min-height: 100vh;
            }
            
            .paper-container {
                max-width: 1200px;
                margin: 0 auto;
                background: var(--paper-color);
                box-shadow: 0 4px 24px rgba(0, 0, 0, 0.1);
                border-radius: 8px;
                padding: 3rem;
                position: relative;
                overflow: hidden;
            }
            
            .paper-container::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 2px;
                background: linear-gradient(90deg, var(--primary-color), var(--secondary-color));
            }
            
            .magazine-header {
                background: linear-gradient(135deg, var(--primary-color), #0099cc);
                color: white;
                padding: 2.5rem;
                border-radius: 8px;
                margin-bottom: 3rem;
                text-align: left;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            }
            
            .magazine-title {
                font-family: 'Inter', sans-serif;
                font-weight: 700;
                font-size: 2.4rem;
                margin-bottom: 0.5rem;
            }
            
            .magazine-subtitle {
                font-size: 1.1rem;
                opacity: 0.9;
            }
            
            .magazine-article {
                margin-bottom: 4rem;
                padding-bottom: 2rem;
                border-bottom: 1px solid var(--border-color);
            }
            
            .article-header {
                margin-bottom: 2rem;
            }
            
            h2 {
                font-family: 'Inter', sans-serif;
                font-size: 1.8rem;
                color: var(--primary-color);
                margin-bottom: 1.5rem;
                border-bottom: 2px solid var(--border-color);
                padding-bottom: 0.5rem;
            }
            
            .article-content {
                display: grid;
                gap: 2rem;
            }
            
            .layout-left-right {
                grid-template-columns: 1fr 2fr;
            }
            
            .layout-right-left {
                grid-template-columns: 2fr 1fr;
            }
            
            .layout-equal {
                grid-template-columns: 1fr 1fr;
            }
            
            .layout-full {
                grid-template-columns: 1fr;
            }
            
            .narrative-section {
                background: var(--highlight-bg);
                padding: 1.5rem;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }
            
            .chapter-summary {
                font-size: 1rem;
                line-height: 1.7;
                color: var(--text-color);
            }
            
            .charts-section {
                display: grid;
                gap: 1.5rem;
            }
            
            .charts-horizontal {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .charts-vertical {
                grid-template-columns: 1fr;
            }
            
            .chart-container-wrapper {
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                overflow: hidden;
                transition: transform 0.2s ease;
            }
            
            .chart-container-wrapper:hover {
                transform: translateY(-2px);
            }
            
            .chart-wrapper {
                position: relative;
                height: 350px;
                padding: 1rem;
            }
            
            .chart-container {
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
            }
            
            .figure-caption {
                padding: 0.8rem 1rem;
                font-size: 0.9rem;
                color: var(--text-color);
                background: var(--chart-bg-2);
                border-top: 1px solid var(--border-color);
            }
            
            .key-insight {
                background-color: rgba(79, 70, 229, 0.1);
                border-radius: 8px;
                padding: 1rem 1.2rem;
                margin: 1rem 0;
                position: relative;
                border-left: 4px solid var(--primary-color);
            }
            
            .key-insight:before {
                content: "💡";
                font-size: 1.2rem;
                position: absolute;
                left: -12px;
                top: -12px;
                background: white;
                width: 28px;
                height: 28px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            
            .key-insight-content {
                font-weight: 500;
                color: var(--text-color);
            }
            
            .insights-container {
                margin-bottom: 2rem;
            }
            
            /* Vega-Lite特定样式 */
            .vega-embed {
                width: 100%;
                height: 100%;
                padding: 0.5rem;
            }
            
            .vega-embed .vega-actions {
                top: 0.5rem;
                right: 0.5rem;
                padding: 0.5rem;
                background: rgba(255,255,255,0.95);
                border-radius: 4px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            
            @media (max-width: 1024px) {
                .article-content {
                    grid-template-columns: 1fr !important;
                }
                
                .charts-horizontal {
                    grid-template-columns: 1fr;
                }
                
                body {
                    padding: 1rem;
                }
                
                .magazine-header {
                    padding: 1.5rem;
                }
                
                h2 {
                    font-size: 1.5rem;
                }
            }
        </style>
    </head>
    <body>
        <div class="paper-container">
            <header class="magazine-header">
                <h1 class="magazine-title">Data Analysis Report</h1>
                <p class="magazine-subtitle">A comprehensive analysis of customer behavior and purchasing patterns</p>
            </header>
    '''
    
    for i, section in enumerate(sections, 1):
        title = section["title"]
        summary = section.get("summary", "")
        charts = section.get("charts", [])
        
        magazine_content += f'''
        <article class="magazine-article">
            <div class="article-header">
                <h2>{escape(title)}</h2>
            </div>
        '''
        
        # 根据图表数量选择布局
        if len(charts) == 1:
            layout_class = "layout-left-right"
        elif len(charts) == 2:
            layout_class = "layout-equal"
        else:
            layout_class = "layout-full"
            
        magazine_content += f'<div class="article-content {layout_class}">\n'
        
        # 添加叙述部分
        magazine_content += '''
            <div class="narrative-section">
                <div class="chapter-summary">
        '''
        magazine_content += escape(summary) if summary else ""
        magazine_content += '''
                </div>
        '''
        
        # 添加关键指标（如果有的话）
        key_insights = section.get("key_insights", [])
        if key_insights:
            magazine_content += '<div class="insights-container">\n'
            for insight in key_insights:
                magazine_content += f'''
                    <div class="key-insight">
                        <div class="key-insight-content">{escape(insight)}</div>
                    </div>
                '''
            magazine_content += '</div>\n'
            
        magazine_content += '</div>\n'
        
        # 添加图表部分
        if charts:
            magazine_content += '<div class="charts-section charts-vertical">\n'
            for chart in charts:
                img = chart.get("img", "")
                caption = chart.get("caption", "")
                is_vegalite = chart.get("is_vegalite", False)
                
                magazine_content += '<div class="chart-container-wrapper">\n'
                magazine_content += '<div class="chart-wrapper">\n'
                
                if is_vegalite:
                    chart_id = chart.get("chart_id", "")
                    relative_img_path = convert_to_relative_path(img)
                    magazine_content += f'<div id="{chart_id}" data-fallback="{relative_img_path}" class="chart-container"></div>\n'
                else:
                    relative_img_path = convert_to_relative_path(img)
                    magazine_content += f'<img src="{relative_img_path}" alt="{escape(caption)}">\n'
                
                magazine_content += '</div>\n'
                magazine_content += f'<div class="figure-caption">{escape(caption)}</div>\n'
                magazine_content += '</div>\n'
            
            magazine_content += '</div>\n'
        
        magazine_content += '</div>\n</article>\n'
    
    # 添加Vega-Lite脚本
    chart_script = generate_vegalite_script(chart_configs)
    
    magazine_content += '''
        </div>
    ''' + chart_script + '''
    </body>
    </html>
    '''
    
    return magazine_content


def generate_dashboard_template(sections):
    from html import escape
    
    # 处理图表配置，使用Vega-Lite而不是AntV G2
    chart_configs, chart_id_counter = prepare_vegalite_config(sections)
    
    def highlight_keywords(text):
        if not text:
            return ""
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
        
        # 添加关键指标（如果有的话）
        key_insights = section.get("key_insights", [])
        if key_insights:
            panels_html += '<div class="metrics-grid">\n'
            for insight in key_insights:
                panels_html += f'''
                <div class="metric-card">
                    <div class="metric-icon">📊</div>
                    <div class="metric-content">{escape(insight)}</div>
                </div>
                '''
            panels_html += '</div>\n'
        
        # 为每个图表创建仪表盘卡片
        if charts:
            panels_html += '<div class="charts-grid">\n'
            for chart in charts:
                caption = chart.get("caption", "")
                img = chart.get("img", "")
                vegalite_config = chart.get("vegalite_config", "")
                is_vegalite = chart.get("is_vegalite", False)
                
                panels_html += f'''
                <div class="chart-card">
                '''
                
                if is_vegalite:
                    chart_id = chart.get("chart_id", "")
                    # Vega-Lite使用div容器
                    # 添加data-fallback属性以供回退使用
                    relative_img_path = convert_to_relative_path(img)
                    panels_html += f'<div class="chart-wrapper"><div id="{chart_id}" data-fallback="{relative_img_path}" class="chart-container"></div></div>\n'
                else:
                    # 获取相对路径
                    relative_img_path = convert_to_relative_path(img)
                    panels_html += f'<div class="chart-wrapper"><img src="{relative_img_path}" alt="{escape(caption)}"></div>\n'
                
                panels_html += f'<div class="chart-caption">{escape(caption)}</div>\n'
                panels_html += '</div>\n'
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
    
    # 生成Vega-Lite脚本
    chart_script = generate_vegalite_script(chart_configs)
    
    # 构建完整的HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据分析仪表盘 (Vega-Lite)</title>
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
        
        /* 修改为charts-grid，避免与chart-container冲突 */
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 2rem;
        }}
        
        .chart-card {{
            border-radius: 8px;
            overflow: hidden;
            background-color: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
            display: flex;
            flex-direction: column;
        }}
        
        .chart-wrapper {{
            flex: 1;
            position: relative;
            min-height: 350px;
        }}
        
        .chart-container {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
        }}
        
        .chart-card img {{
            width: 100%;
            height: auto;
            display: block;
            max-height: 400px;
            object-fit: contain;
        }}
        
        .chart-caption {{
            padding: 1rem;
            font-size: 0.875rem;
            color: var(--text-light);
            border-top: 1px solid var(--border-color);
            background-color: #fcfcfc;
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
            margin-right: 1rem;
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
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }}
        
        .metric-card {{
            background-color: rgba(67, 97, 238, 0.05);
            border-radius: 8px;
            padding: 1rem;
            display: flex;
            align-items: flex-start;
            border-left: 3px solid var(--accent-color);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .metric-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 6px 12px rgba(0,0,0,0.08);
        }}
        
        .metric-icon {{
            font-size: 1.4rem;
            margin-right: 0.8rem;
            color: var(--accent-color);
        }}
        
        .metric-content {{
            font-size: 0.9rem;
            font-weight: 500;
            color: var(--text-color);
            line-height: 1.5;
        }}
        
        @media (max-width: 768px) {{
            body {{
                padding: 1rem;
            }}
            
            .charts-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        
        /* Vega-Lite特定样式 */
        .vega-embed {{
            width: 100%;
            height: 100%;
        }}
        .vega-embed .vega-actions {{
            top: 0;
            right: 0;
            padding: 6px;
        }}
    </style>
</head>
<body>
    <div class="dashboard-header">
        <h1 class="dashboard-title">数据分析仪表盘 (Vega-Lite)</h1>
        <div class="dashboard-controls">
            <button class="dashboard-control">导出报告</button>
            <button class="dashboard-control">刷新数据</button>
        </div>
    </div>
    
    <div class="dashboard-panels">
        {panels_html}
    </div>
    {chart_script}
</body>
</html>'''
    
    return html


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate styled report from Markdown.')
    parser.add_argument('markdown_file', type=str, help='Path to the input Markdown file')
    parser.add_argument('--output', type=str, default='report_generated.html', help='Output HTML file name')
    parser.add_argument('--template', type=str, choices=['sidebar', 'grid', 'magazine', 'dashboard'], default='dashboard', help='Template style to use')
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
    
    print(f"✅ 报告已生成: {output_path}")
    print("  - 使用Vega-Lite渲染图表")
