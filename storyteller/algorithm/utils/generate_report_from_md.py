import markdown
from bs4 import BeautifulSoup
import os
import argparse
from pathlib import Path
import random
import urllib.parse
import json
import re

def parse_markdown(md_path):
    """
    解析Markdown文件，提取章节和图表信息
    直接使用更高效的直接解析方法
    """
    print(f"\n开始解析Markdown文件: {md_path}")
    return parse_markdown_direct(md_path)

def parse_markdown_direct(md_path):
    """使用直接解析Markdown的方式提取数据结构"""
    print(f"\n使用直接解析方式提取Markdown内容: {md_path}")
    
    with open(md_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # 获取Markdown文件所在目录
    md_dir = os.path.dirname(os.path.abspath(md_path))

    # 初始化数据结构
    sections = []
    current_section = None
    current_caption = ""
    in_chart_group = False
    current_group_charts = []
    current_group_caption = ""
    
    # 按行处理Markdown内容
    lines = md_content.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # 识别章节标题 (## 开头)
        if line.startswith('## '):
            # 保存之前的章节（如果有）
            if current_section:
                sections.append(current_section)
            
            # 提取章节标题
            title = line[3:].strip()
            # 处理字典格式的标题
            if title.startswith("{'title': '") and title.endswith("'}"):
                title = title[len("{'title': '"):-2]
            
            # 创建新章节
            current_section = {
                "title": title,
                "charts": [],
                "summary": "",
                "key_insights": []
            }
            current_caption = ""
            in_chart_group = False
            current_group_charts = []
            current_group_caption = ""
            
            print(f"发现章节: {title}")
        
        # 识别引用块 (> 开头)，处理为caption
        elif line.startswith('>'):
            caption_text = line[1:].strip()
            
            # 如果已经在处理图表组，或者下一个非空行是chart-group-start，则将caption设置为图表组的caption
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1  # 跳过空行
                
            is_next_group_start = j < len(lines) and "<!-- chart-group-start -->" in lines[j].strip()
            
            if in_chart_group or is_next_group_start:
                current_group_caption = caption_text
                print(f"设置图表组caption: {caption_text[:30]}...")
            else:
                current_caption = caption_text
                print(f"设置单图表caption: {caption_text[:30]}...")
        
        # 识别图表组开始标记
        elif '<!-- chart-group-start -->' in line:
            in_chart_group = True
            current_group_charts = []
            print("检测到图表组开始标记")
                
        # 识别图表组结束标记
        elif '<!-- chart-group-end -->' in line:
            if in_chart_group and current_group_charts and current_section:
                # 创建图表组对象
                chart_group = {
                    "is_chart_group": True,
                    "charts": current_group_charts,
                    "group_caption": current_group_caption
                }
                
                # 添加到章节
                current_section["charts"].append(chart_group)
                print(f"添加图表组，包含 {len(current_group_charts)} 个图表, caption: '{current_group_caption[:50]}...'")
            
            in_chart_group = False
            current_group_charts = []
            current_group_caption = ""
        
        # 识别图片 (![alt](src) 格式)
        elif line.startswith('![') and '](' in line and line.endswith(')'):
            # 提取图片信息
            alt_start = line.find('![') + 2
            alt_end = line.find('](')
            src_start = alt_end + 2
            src_end = line.rfind(')')
            
            if alt_start < alt_end and src_start < src_end:
                alt_text = line[alt_start:alt_end]
                src = line[src_start:src_end]
                
                # 构建完整路径
                if not os.path.isabs(src):
                    img_path = os.path.join(md_dir, src)
                else:
                    img_path = src
                
                # 创建图表信息
                chart_info = {
                    "img": img_path,
                    "caption": current_caption if not in_chart_group else "",
                    "alt_text": alt_text
                }
                
                # 添加到适当的位置
                if in_chart_group:
                    chart_info["in_group"] = True
                    current_group_charts.append(chart_info)
                    print(f"添加图片到组: {src}")
                elif current_section:
                    current_section["charts"].append(chart_info)
                    print(f"添加单个图片: {src}")
        
        # 识别Chapter Summary部分
        elif line == "### Chapter Summary":
            summary_lines = []
            j = i + 1
            while j < len(lines) and lines[j].strip() and not lines[j].startswith('#'):
                summary_lines.append(lines[j].strip())
                j += 1
            
            if summary_lines and current_section:
                current_section["summary"] = " ".join(summary_lines)
                print(f"设置章节摘要: {current_section['summary'][:50]}...")
                # 跳过已处理的行
                i = j - 1
        
        i += 1
    
    # 添加最后一个章节
    if current_section:
        sections.append(current_section)
    
    # 打印统计信息
    print(f"\n解析完成: 找到 {len(sections)} 个章节")
    for i, section in enumerate(sections, 1):
        charts_count = len(section.get("charts", []))
        print(f"章节 {i}: '{section.get('title', '无标题')}' - 包含 {charts_count} 个图表/图表组")
        
        for j, chart in enumerate(section.get("charts", []), 1):
            if isinstance(chart, dict) and chart.get("is_chart_group", False):
                group_charts = chart.get("charts", [])
                group_caption = chart.get("group_caption", "")
                print(f"  - 图表组 {j}: 包含 {len(group_charts)} 个图表, caption: '{group_caption[:30]}...'")
            else:
                img_path = chart.get("img", "")
                caption = chart.get("caption", "")
                print(f"  - 图表 {j}: {os.path.basename(img_path)}, caption: '{caption[:30]}...'")
    
    return sections

# 辅助函数：将文件名中的特殊字符转换为下划线，避免在查找文件时出错
def escape_filename(name):
    if not name:
        return "unnamed"
    # 将特殊字符转换为下划线，保留字母、数字和常见标点
    import re
    return re.sub(r'[^\w\-\.]', '_', name)

# 辅助函数：将绝对路径转换为相对路径
def convert_to_relative_path(path):
    """
    将绝对路径转换为相对路径，改进版：
    1. 如果不是绝对路径，直接返回
    2. 尝试从常见目录名如'storyteller'、'mcts'等提取相对路径
    3. 如果无法提取，使用文件名作为相对路径
    """
    if not path:
        return ""
        
    # 如果不是绝对路径，直接返回
    if not os.path.isabs(path):
        return path
        
    # 尝试查找常见目录部分，构建相对路径
    common_dirs = ['storyteller', 'mcts', 'data', 'reports', 'images']
    parts = path.split(os.sep)
    
    for common_dir in common_dirs:
        try:
            index = parts.index(common_dir)
            # 从该目录开始构建相对路径
            relative_path = "/".join(parts[index:])
            print(f"转换路径: {path} -> {relative_path}")
            return relative_path
        except ValueError:
            continue
    
    # 如果找不到常见目录，至少返回文件名作为相对路径
    filename = os.path.basename(path)
    print(f"未找到常见目录，使用文件名: {path} -> {filename}")
    return filename

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
        for chart_item in section.get("charts", []):
            # 检查是否是图表组
            if isinstance(chart_item, dict) and chart_item.get("is_chart_group", False):
                # 处理图表组内的所有图表
                for group_chart in chart_item.get("charts", []):
                    process_chart_config(group_chart, chart_configs, chart_id_counter)
                    if "chart_id" in group_chart:
                        chart_id_counter += 1
            else:
                # 处理单个图表
                process_chart_config(chart_item, chart_configs, chart_id_counter)
                if "chart_id" in chart_item:
                    chart_id_counter += 1
    
    return chart_configs, chart_id_counter

def process_chart_config(chart, chart_configs, chart_id_counter):
    """处理单个图表的配置"""
    vegalite_config_path = chart.get("vegalite_config", "")
    img_path = chart.get("img", "")
    
    if vegalite_config_path:
        # 如果有配置文件，使用Vega-Lite渲染
        chart_id = f"vegalite_chart_{chart_id_counter}"
        
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
            print(f"读取Vega-Lite配置文件失败: {vegalite_config_path}")
            print(f"错误详情: {str(e)}")
            print(f"确保文件存在且是有效的JSON格式")

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
    
    # 使用特殊的布局模板
    """ if template_type == "sidebar":
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
 """
    # 默认使用dashboard模板
    if template_type == "sidebar":
        return generate_dashboard_template(sections)

def highlight_keywords(text, keywords=None):
    """
    对文本中的关键词进行高亮处理
    
    参数:
    - text: 要处理的文本
    - keywords: 关键词列表，如果为None则使用默认关键词
    
    返回:
    - 处理后的文本，带有HTML高亮标记
    """
    if not text:
        return ""
    
    # 如果没有提供关键词，使用默认关键词
    if keywords is None:
        keywords = [
            "增长", "下降", "上升", "趋势", "显著", "明显", 
            "突出", "重要", "关键", "异常", "高于", "低于",
            "最高", "最低", "增加", "减少", "变化", "稳定",
            "波动", "集中", "分散", "极值", "outlier", "异常值"
        ]
    
    from html import escape
    
    # 先进行HTML转义，避免注入
    escaped_text = escape(text)
    
    # 对每个关键词进行高亮处理
    for keyword in keywords:
        # 使用正则表达式进行大小写不敏感的替换
        import re
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        escaped_text = pattern.sub(f'<span class="highlight">{keyword}</span>', escaped_text)
    
    return escaped_text

def generate_dashboard_template(sections):
    from html import escape
    
    # 处理图表配置，使用Vega-Lite而不是AntV G2
    chart_configs, chart_id_counter = prepare_vegalite_config(sections)
    
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
                    <div class="metric-content">{highlight_keywords(insight)}</div>
                </div>
                '''
            panels_html += '</div>\n'
        
        # 为每个图表创建仪表盘卡片
        if charts:
            panels_html += '<div class="charts-grid">\n'
            for chart in charts:
                # 检查是否是图表组
                if isinstance(chart, dict) and chart.get("is_chart_group", False):
                    # 处理图表组
                    group_charts = chart.get("charts", [])
                    group_caption = chart.get("group_caption", "")
                    
                    print(f"生成图表组模板，包含 {len(group_charts)} 个图表, caption: '{group_caption[:50]}...'")
                    
                    # 创建图表组容器
                    panels_html += f'''
                    <div class="chart-group-container chart-card">
                        <div class="chart-group-grid chart-group-{len(group_charts)}">
                    '''
                    
                    # 添加组内所有图表
                    for group_chart in group_charts:
                        img = group_chart.get("img", "")
                        alt_text = group_chart.get("alt_text", "图表")
                        is_vegalite = group_chart.get("is_vegalite", False)
                        
                        panels_html += '<div class="chart-group-item">\n'
                        
                        # 获取相对路径
                        relative_img_path = convert_to_relative_path(img)
                        
                        if is_vegalite:
                            chart_id = group_chart.get("chart_id", "")
                            panels_html += f'<div class="chart-wrapper"><div id="{chart_id}" data-fallback="{relative_img_path}" class="chart-container"></div></div>\n'
                        else:
                            panels_html += f'<div class="chart-wrapper"><img src="{relative_img_path}" alt="{escape(alt_text)}"></div>\n'
                        
                        panels_html += '</div>\n'
                    
                    # 结束图表组网格并正确显示caption
                    panels_html += f'''
                        </div>
                        <div class="chart-caption group-caption">{highlight_keywords(group_caption)}</div>
                    </div>
                    '''
                    
                else:
                    # 处理单个图表
                    caption = chart.get("caption", "")
                    img = chart.get("img", "")
                    alt_text = chart.get("alt_text", "图表")
                    is_vegalite = chart.get("is_vegalite", False)
                    
                    panels_html += '<div class="chart-card">\n'
                    
                    if is_vegalite:
                        chart_id = chart.get("chart_id", "")
                        relative_img_path = convert_to_relative_path(img)
                        panels_html += f'<div class="chart-wrapper"><div id="{chart_id}" data-fallback="{relative_img_path}" class="chart-container"></div></div>\n'
                    else:
                        relative_img_path = convert_to_relative_path(img)
                        panels_html += f'<div class="chart-wrapper"><img src="{relative_img_path}" alt="{escape(alt_text)}"></div>\n'
                    
                    panels_html += f'<div class="chart-caption">{highlight_keywords(caption)}</div>\n'
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
        
        /* 图表网格布局 */
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 2rem;
            margin-bottom: 1.5rem;
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
        
        /* 图表组样式 */
        .chart-group-container {{
            margin-bottom: 1.5rem;
        }}
        
        .chart-group-grid {{
            display: grid;
            gap: 1rem;
            padding: 1rem;
        }}
        
        /* 根据组内图表数量自动调整布局 */
        .chart-group-1 {{ grid-template-columns: 1fr; }}
        .chart-group-2 {{ grid-template-columns: 1fr 1fr; }}
        .chart-group-3 {{ grid-template-columns: 1fr 1fr 1fr; }}
        .chart-group-4 {{ grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; }}
        .chart-group-5, .chart-group-6 {{ grid-template-columns: repeat(3, 1fr); }}
        
        .chart-group-item {{
            border: 1px solid #eee;
            border-radius: 4px;
            overflow: hidden;
        }}
        
        .chart-caption {{
            padding: 1rem;
            font-size: 0.875rem;
            color: var(--text-light);
            border-top: 1px solid var(--border-color);
            background-color: #fcfcfc;
            min-height: 3rem;  /* 确保caption有最小高度，即使为空 */
        }}
        
        /* 图表组标题样式增强 */
        .group-caption {{
            font-weight: 500;
            color: var(--accent-color);
            border-left: 3px solid var(--accent-color);
            padding-left: 0.75rem;
            background-color: #f0f4ff;
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
            
            .chart-group-2, .chart-group-3, .chart-group-4, .chart-group-5, .chart-group-6 {{ 
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
        <h1 class="dashboard-title">数据分析仪表盘</h1>
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

    # 获取输入文件的绝对路径
    md_path = os.path.abspath(args.markdown_file)
    
    if not os.path.exists(md_path):
        print(f"错误: 找不到输入文件 {md_path}")
        exit(1)
    
    # 确定输出路径 - 如果未指定目录，则放在与markdown同一目录
    output_path = args.output
    if not os.path.dirname(output_path):
        md_dir = os.path.dirname(md_path)
        output_path = os.path.join(md_dir, output_path)
    
    try:
        print(f"开始解析并生成报告...")
        print(f"输入文件: {md_path}")
        print(f"输出文件: {output_path}")
        print(f"使用模板: {args.template}")
        
        # 解析Markdown文件
        sections = parse_markdown(md_path)
        
        if not sections:
            print("警告: 未找到任何章节数据。请检查Markdown文件格式。")
            exit(1)
            
        # 统计图表和图表组数量
        total_charts = 0
        total_groups = 0
        
        for section in sections:
            for chart in section.get("charts", []):
                if isinstance(chart, dict) and chart.get("is_chart_group", False):
                    total_groups += 1
                    total_charts += len(chart.get("charts", []))
                else:
                    total_charts += 1
        
        print(f"解析结果: {len(sections)}个章节, {total_charts}个图表, {total_groups}个图表组")
        
        # 生成HTML内容
        print("生成HTML报告...")
        html = fill_template(sections, args.template)
    
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # 写入HTML文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
    
        print(f"✅ 报告已成功生成: {output_path}")
        print(f"  - 包含 {len(sections)} 个章节")
        print(f"  - 包含 {total_charts} 个图表 ({total_groups} 个图表组)")
        print(f"  - 使用了 {args.template} 模板")
        
    except Exception as e:
        print(f"❌ 生成报告时发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)
