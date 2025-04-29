import markdown
from bs4 import BeautifulSoup
import os
import argparse
from pathlib import Path
import random
import urllib.parse  # 添加URL编码支持
import json  # 导入json模块

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
            
            if img_path.lower().endswith('.png'):
                # 构建可能的JSON配置文件路径
                img_dir = os.path.dirname(img_path)
                img_filename = os.path.basename(img_path)
                img_basename = os.path.splitext(img_filename)[0]
                
                # 设置潜在的配置文件所在目录
                # 首先尝试在同级的chart_configs目录查找
                config_dir = os.path.join(os.path.dirname(img_dir), "chart_configs")
                
                # 尝试多种可能的配置文件名
                possible_config_paths = [
                    os.path.join(config_dir, f"{img_basename}.json"),
                    os.path.join(config_dir, f"{img_basename}_edited.json"),
                    # 尝试在同目录查找
                    os.path.join(img_dir, f"{img_basename}.json"),
                    os.path.join(img_dir, f"{img_basename}_config.json")
                ]
                
                for path in possible_config_paths:
                    if os.path.exists(path):
                        config_path = path
                        print(f"找到图表配置文件: {config_path}")
                        break
            
            chart_info = {
                "img": img_path,
                "caption": current_caption
            }
            
            # 如果找到了配置文件，添加到图表信息中
            if config_path:
                chart_info["config"] = config_path
                
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

# 添加一个通用函数来处理Chart.js配置
def prepare_chartjs_config(sections):
    """
    为sections中的所有图表准备Chart.js配置
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
            config_path = chart.get("config", "")
            img_path = chart.get("img", "")
            
            if config_path:
                # 如果有配置文件，使用Chart.js渲染
                chart_id = f"chart_{chart_id_counter}"
                chart_id_counter += 1
                
                # 读取JSON配置文件内容
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_content = json.load(f)
                except Exception as e:
                    print(f"读取配置文件失败: {config_path}, 错误: {e}")
                    config_content = {}
                
                # 获取相对路径并保存图片路径
                relative_img_path = convert_to_relative_path(img_path)
                
                # 保存配置信息
                chart_configs.append({
                    "chartId": chart_id,
                    "configContent": config_content,  # 直接存储JSON对象
                    "imgPath": relative_img_path      # 存储相对路径
                })
                
                # 在图表对象上添加chart_id属性，以便模板函数使用
                chart["chart_id"] = chart_id
    
    return chart_configs, chart_id_counter

# 添加生成通用Chart.js脚本的函数
def generate_chartjs_script(chart_configs):
    """
    根据图表配置生成通用的Chart.js初始化脚本
    """
    if not chart_configs:
        return ""
        
    chart_script = """
<script>
// 存储图表配置的对象
const chartConfigs = {};
// 存储图表实例的对象
const chartInstances = {};

// 初始化图表的函数
function initializeChart(chartId, configObj, fallbackImgPath) {
    // 获取canvas元素
    const canvas = document.getElementById(chartId);
    
    if (!canvas) {
        console.error(`Canvas element with ID ${chartId} not found`);
        return;
    }
    
    // 保存回退图片路径
    canvas.setAttribute('data-fallback-img', fallbackImgPath);
    
    try {
        console.log(`Initializing chart ${chartId}`);
        
        // 创建Chart.js图表
        const chart = new Chart(canvas, {
            type: configObj.chart_type || 'bar',
            data: configObj.data || {},
            options: configObj.options || {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    title: {
                        display: true,
                        text: configObj.title || ''
                    }
                }
            }
        });
        
        // 存储图表实例以便后续引用
        chartInstances[chartId] = chart;
        
        // 标记为已初始化
        canvas.setAttribute('data-initialized', 'true');
        
        return chart;
    } catch (error) {
        console.error(`Error creating chart ${chartId}:`, error);
        fallbackToImage(chartId);
        return null;
    }
}

// 回退到静态图片
function fallbackToImage(chartId) {
    const canvas = document.getElementById(chartId);
    if (!canvas) return;
    
    const fallbackImgPath = canvas.getAttribute('data-fallback-img');
    if (!fallbackImgPath) return;
    
    const container = canvas.parentElement;
    if (!container) return;
    
    console.log(`Falling back to image for ${chartId}: ${fallbackImgPath}`);
    
    // 创建图片元素
    const img = document.createElement('img');
    img.src = fallbackImgPath;
    img.alt = 'Chart fallback image';
    img.style.width = '100%';
    
    // 替换canvas
    container.innerHTML = '';
    container.appendChild(img);
}

// 页面加载完成后初始化所有图表
document.addEventListener('DOMContentLoaded', function() {
"""
    
    # 首先添加所有图表配置
    for i, config in enumerate(chart_configs):
        # 将Python字典转换为JSON字符串
        json_str = json.dumps(config['configContent'])
        chart_script += f"    chartConfigs.chart_{i} = {json_str};\n"
    
    # 然后为每个图表添加初始化代码
    for i, config in enumerate(chart_configs):
        chart_script += f"    initializeChart('{config['chartId']}', chartConfigs.chart_{i}, '{config['imgPath']}');\n"
    
    chart_script += """
    // 添加一个定时器检查图表是否正确渲染
    setTimeout(function() {
        document.querySelectorAll('canvas[id^="chart_"]').forEach(canvas => {
            const chartId = canvas.id;
            // 检查该图表是否已标记为初始化
            if (!canvas.getAttribute('data-initialized') || !chartInstances[chartId]) {
                console.log(`Chart ${chartId} was not initialized properly, falling back to image`);
                fallbackToImage(chartId);
            }
        });
    }, 2000); // 延长等待时间到2秒
});
</script>
"""
    return chart_script

# 添加一个通用函数来处理AntV G2配置
def prepare_antv_config(sections):
    """
    为sections中的所有图表准备AntV G2配置
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
            config_path = chart.get("config", "")
            img_path = chart.get("img", "")
            
            if config_path:
                # 如果有配置文件，使用AntV G2渲染
                chart_id = f"antv_chart_{chart_id_counter}"
                chart_id_counter += 1
                
                # 读取JSON配置文件内容
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config_content = json.load(f)
                except Exception as e:
                    print(f"读取配置文件失败: {config_path}, 错误: {e}")
                    config_content = {}
                
                # 获取相对路径并保存图片路径
                relative_img_path = convert_to_relative_path(img_path)
                
                # 保存配置信息
                chart_configs.append({
                    "chartId": chart_id,
                    "configContent": config_content,  # 直接存储JSON对象
                    "imgPath": relative_img_path      # 存储相对路径
                })
                
                # 在图表对象上添加chart_id属性，以便模板函数使用
                chart["chart_id"] = chart_id
                # 标记为AntV图表
                chart["is_antv"] = True
    
    return chart_configs, chart_id_counter

# 添加生成AntV G2脚本的函数
def generate_antv_script(chart_configs):
    """
    根据图表配置生成通用的AntV G2初始化脚本
    """
    if not chart_configs:
        return ""
        
    chart_script = """
<script src=\"https://unpkg.com/@antv/g2@4.2.8/dist/g2.min.js\"></script>
<script>
// 存储图表配置的对象
const antvConfigs = {};
// 存储图表实例的对象
const antvInstances = {};

// 初始化图表的函数
function initializeAntvChart(chartId, configObj, fallbackImgPath) {
    // 获取container元素
    const container = document.getElementById(chartId);
    
    if (!container) {
        console.error(`Container element with ID ${chartId} not found`);
        return;
    }
    
    // 保存回退图片路径
    container.setAttribute('data-fallback-img', fallbackImgPath);
    
    try {
        console.log(`Initializing AntV chart ${chartId}`);
        
        // 配置项解构
        const {
            type,
            data,
            xField,
            yField,
            seriesField,
            isStack,
            title,
            color,
            autoFit,
            ...restConfig
        } = configObj;
        
        // 创建AntV G2图表
        const chart = new G2.Chart({
            container: chartId,
            autoFit: autoFit || true,
            height: 400,
            padding: [30, 40, 60, 60]
        });
        
        // 设置数据
        chart.data(data || []);
        
        // 动态选择geometry
        let geometry;
        if (type === 'line') {
            geometry = chart.line();
        } else if (type === 'point') {
            geometry = chart.point();
        } else if (type === 'interval') {
            geometry = chart.interval();
        } else if (type === 'pie') {
            // 饼图特殊处理
            geometry = chart.interval().position('1*value').adjust('stack');
        } else {
            geometry = chart.interval();
        }
        
        // 配置position
        if (type !== 'pie') {
            if (xField && yField) {
                geometry.position(`${xField}*${yField}`);
            }
        }
        // 配置color
        if (seriesField && color && Array.isArray(color)) {
            geometry.color(seriesField, color);
        } else if (seriesField) {
            geometry.color(seriesField);
        } else if (color && Array.isArray(color)) {
            geometry.color(color[0]);
        } else if (color) {
            geometry.color(color);
        }
        // 堆叠
        if (isStack && type === 'interval') {
            geometry.adjust('stack');
        }
        // 其他配置
        if (title) {
            chart.annotation().text({
                position: ['50%', '0%'],
                content: title,
                style: {
                    fontSize: 18,
                    fontWeight: 'bold',
                    fill: '#333',
                    textAlign: 'center',
                },
                offsetY: -20
            });
        }
        // 渲染
        chart.render();
        
        // 存储图表实例以便后续引用
        antvInstances[chartId] = chart;
        
        // 标记为已初始化
        container.setAttribute('data-initialized', 'true');
        
        return chart;
    } catch (error) {
        console.error(`Error creating AntV chart ${chartId}:`, error);
        fallbackToImage(chartId);
        return null;
    }
}

// 回退到静态图片
function fallbackToImage(chartId) {
    const container = document.getElementById(chartId);
    if (!container) return;
    
    const fallbackImgPath = container.getAttribute('data-fallback-img');
    if (!fallbackImgPath) return;
    
    console.log(`Falling back to image for ${chartId}: ${fallbackImgPath}`);
    
    // 创建图片元素
    const img = document.createElement('img');
    img.src = fallbackImgPath;
    img.alt = 'Chart fallback image';
    img.style.width = '100%';
    
    // 替换容器内容
    container.innerHTML = '';
    container.appendChild(img);
}

// 页面加载完成后初始化所有图表
document.addEventListener('DOMContentLoaded', function() {
"""
    # 首先添加所有图表配置
    for i, config in enumerate(chart_configs):
        # 将Python字典转换为JSON字符串
        json_str = json.dumps(config['configContent'])
        chart_script += f"    antvConfigs.chart_{i} = {json_str};\n"
    # 然后为每个图表添加初始化代码
    for i, config in enumerate(chart_configs):
        chart_script += f"    initializeAntvChart('{config['chartId']}', antvConfigs.chart_{i}, '{config['imgPath']}');\n"
    chart_script += """
    // 添加一个定时器检查图表是否正确渲染
    setTimeout(function() {
        document.querySelectorAll('div[id^="antv_chart_"]').forEach(container => {
            const chartId = container.id;
            // 检查该图表是否已标记为初始化
            if (!container.getAttribute('data-initialized') || !antvInstances[chartId]) {
                console.log(`AntV chart ${chartId} was not initialized properly, falling back to image`);
                fallbackToImage(chartId);
            }
        });
    }, 2000); // 延长等待时间到2秒
});
</script>
"""
    return chart_script

def fill_template(sections, template_type="dashboard", use_antv=False):
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
        return generate_dashboard_template(sections, use_antv)
    else:
        # 默认使用dashboard模板
        return generate_dashboard_template(sections, use_antv)


def generate_sidebar_template(sections):
    from html import escape
    
    # 处理图表配置
    chart_configs, chart_id_counter = prepare_chartjs_config(sections)
    
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
            config = chart.get("config", "")
            
            if config:
                chart_id = chart.get("chart_id", "")
                
                main_content += f'''      <div class="chart-container">
        <canvas id="{chart_id}"></canvas>
        <p class="caption">{escape(caption)}</p>
      </div>\n'''
            else:
                # 获取相对路径
                relative_img_path = convert_to_relative_path(img)
                main_content += f'''      <div class="chart-container">
        <img src="{relative_img_path}" width="100%">
        <p class="caption">{escape(caption)}</p>
      </div>\n'''
            
        # 添加章节小结
        summary = section.get("summary", "")
        if summary:
            main_content += f'      <div class="summary"><div class="summary-icon">📊</div><div class="summary-content"><p><strong>Chapter Summary：</strong> {escape(summary)}</p></div></div>\n'
            
        main_content += '    </section>\n\n'
    
    # 生成Chart.js脚本
    chart_script = generate_chartjs_script(chart_configs)
    
    # 组装HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>数据分析报告</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
      height: 400px;
    }}
    
    .chart-container:hover {{
      transform: translateY(-4px);
      box-shadow: var(--shadow-lg);
    }}
    
    .chart-container img {{
      border-radius: 0.5rem 0.5rem 0 0;
      display: block;
      width: 100%;
    }}
    
    .chart-container canvas {{
      width: 100% !important;
      height: 100% !important;
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
    chart_configs, chart_id_counter = prepare_chartjs_config(sections)
    
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
            
            cards_html += f'  <div class="card">\n'
            
            if config:
                # 如果有配置文件，使用Chart.js渲染
                chart_id = chart.get("chart_id", "")
                
                cards_html += f'    <div class="chart-container">\n'
                cards_html += f'      <canvas id="{chart_id}"></canvas>\n'
                cards_html += f'</div>\n'
            else:
                # 没有配置文件，使用静态图片
                # 转换为相对路径
                relative_img_path = convert_to_relative_path(img)
                cards_html += f'    <img src="{relative_img_path}" alt="{escape(caption)}">\n'
            
            cards_html += f'    <div class="card-caption">{escape(caption)}</div>\n'
            cards_html += '  </div>\n'
            
        cards_html += '</div>\n'
        
        # 添加章节小结
        summary = section.get("summary", "")
        if summary:
            cards_html += f'<div class="summary"><p><strong>Chapter Summary：</strong> {escape(summary)}</p></div>\n'
    
    # 生成Chart.js脚本
    chart_script = generate_chartjs_script(chart_configs)
    
    # 组装HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>数据分析报告</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{ font-family: 'Inter', sans-serif; background-color: #f8f9fa; color: #333; max-width: 1200px; margin: 0 auto; padding: 2rem; }}
    h1 {{ text-align: center; color: #303f9f; margin-bottom: 2rem; font-size: 2.2rem; }}
    .section-title {{ width: 100%; margin: 2rem 0 1rem 0; }}
    h2 {{ color: #303f9f; border-bottom: 2px solid #5c6bc0; padding-bottom: 0.5rem; }}
    .card-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(450px, 1fr)); gap: 1.5rem; margin-bottom: 2rem; }}
    .card {{ background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: transform 0.3s, box-shadow 0.3s; }}
    .card:hover {{ transform: translateY(-5px); box-shadow: 0 6px 12px rgba(0,0,0,0.15); }}
    .card img {{ width: 100%; height: auto; display: block; }}
    .chart-container {{ height: 300px; position: relative; margin-bottom: 0; }}
    .card-caption {{ padding: 1rem; font-size: 0.95rem; color: #555; }}
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
    chart_configs, chart_id_counter = prepare_chartjs_config(sections)
    
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
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
    chart_script = generate_chartjs_script(chart_configs)
    
    html_tail = chart_script + "</body></html>"

    return html_head + html_body + html_tail


def generate_magazine_template(sections):
    from html import escape
    
    # 处理图表配置
    chart_configs, chart_id_counter = prepare_chartjs_config(sections)
    
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
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
            
            .chart-container {
                height: 400px;
                position: relative;
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
            
            # 添加关键指标（如果有的话）
            key_insights = section.get("key_insights", [])
            if key_insights:
                magazine_content += f'''
                <div class="insights-section">
                    <h3 class="insights-title">关键发现</h3>
                    <div class="insights-list">
                '''
                
                for insight in key_insights:
                    magazine_content += f'''
                        <div class="insight-item">
                            <div class="insight-icon">💡</div>
                            <div class="insight-text">{escape(insight)}</div>
                        </div>
                    '''
                
                magazine_content += '</div></div>\n'
            
            for chart in charts:
                img = chart.get("img", "")
                caption = chart.get("caption", "")
                config = chart.get("config", "")
                
                magazine_content += f'<figure>\n'
                
                if config:
                    chart_id = chart.get("chart_id", "")
                    magazine_content += f'<div class="chart-container">\n'
                    magazine_content += f'<canvas id="{chart_id}"></canvas>\n'
                    magazine_content += f'</div>\n'
                else:
                    # 获取相对路径
                    relative_img_path = convert_to_relative_path(img)
                    magazine_content += f'<img src="{relative_img_path}" alt="图表">\n'
                
                magazine_content += f'<figcaption class="figure-caption">{escape(caption)}</figcaption>\n'
                magazine_content += f'</figure>\n'
            
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
            
            # 添加关键指标（如果有的话）
            key_insights = section.get("key_insights", [])
            if key_insights:
                magazine_content += '<div class="insights-list">\n'
                for insight in key_insights:
                    magazine_content += f'''
                    <div class="insight-item">
                        <div class="insight-icon">💡</div>
                        <div class="insight-text">{escape(insight)}</div>
                    </div>
                    '''
                magazine_content += '</div>\n'
            
            for chart in charts:
                img = chart.get("img", "")
                caption = chart.get("caption", "")
                config = chart.get("config", "")
                
                magazine_content += f'<figure>\n'
                
                if config:
                    chart_id = chart.get("chart_id", "")
                    magazine_content += f'<div class="chart-container">\n'
                    magazine_content += f'<canvas id="{chart_id}"></canvas>\n'
                    magazine_content += f'</div>\n'
                else:
                    # 获取相对路径
                    relative_img_path = convert_to_relative_path(img)
                    magazine_content += f'<img src="{relative_img_path}" alt="图表">\n'
                
                magazine_content += f'<figcaption class="figure-caption">{escape(caption)}</figcaption>\n'
                magazine_content += f'</figure>\n'
            
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
            
            # 添加关键指标（如果有的话）
            key_insights = section.get("key_insights", [])
            if key_insights:
                magazine_content += '<div class="insights-feature">\n'
                for insight in key_insights:
                    magazine_content += f'''
                    <div class="insight-feature-item">
                        <div class="insight-icon">💡</div>
                        <div class="insight-text">{escape(insight)}</div>
                    </div>
                    '''
                magazine_content += '</div>\n'
            
            magazine_content += '''
            </div>
            '''
            
            if charts and len(charts) > 0:
                featured_chart = charts[0]
                img = featured_chart.get('img', '')
                caption = featured_chart.get('caption', '')
                config = featured_chart.get('config', '')
                
                magazine_content += f'<div class="feature-hero">\n'
                
                if config:
                    chart_id = featured_chart.get("chart_id", "")
                    magazine_content += f'<div class="chart-container">\n'
                    magazine_content += f'<canvas id="{chart_id}"></canvas>\n'
                    magazine_content += f'</div>\n'
                else:
                    # 获取相对路径
                    relative_img_path = convert_to_relative_path(img)
                    magazine_content += f'<img src="{relative_img_path}" alt="特色图表">\n'
                
                magazine_content += f'<figcaption class="figure-caption">{escape(caption)}</figcaption>\n'
                magazine_content += f'</div>\n'
                
                # 添加其余图表
                if len(charts) > 1:
                    magazine_content += '<div class="secondary-visuals">\n'
                    for chart in charts[1:]:
                        img = chart.get("img", "")
                        caption = chart.get("caption", "")
                        config = chart.get("config", "")
                        
                        magazine_content += f'<figure>\n'
                        
                        if config:
                            chart_id = chart.get("chart_id", "")
                            magazine_content += f'<div class="chart-container">\n'
                            magazine_content += f'<canvas id="{chart_id}"></canvas>\n'
                            magazine_content += f'</div>\n'
                        else:
                            # 获取相对路径
                            relative_img_path = convert_to_relative_path(img)
                            magazine_content += f'<img src="{relative_img_path}" alt="图表">\n'
                        
                        magazine_content += f'<figcaption class="figure-caption">{escape(caption)}</figcaption>\n'
                        magazine_content += f'</figure>\n'
                    magazine_content += '</div>\n'
            
            magazine_content += '</article>'
    
    # 添加Chart.js脚本
    chart_script = generate_chartjs_script(chart_configs)
    magazine_content += chart_script
    
    magazine_content += '''
    </body>
    </html>
    '''
    
    return magazine_content


def generate_dashboard_template(sections, use_antv=False):
    from html import escape
    
    # 处理图表配置
    if use_antv:
        chart_configs, chart_id_counter = prepare_antv_config(sections)
    else:
        chart_configs, chart_id_counter = prepare_chartjs_config(sections)
    
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
            panels_html += '<div class="chart-container">\n'
            for chart in charts:
                caption = chart.get("caption", "")
                img = chart.get("img", "")
                config = chart.get("config", "")
                is_antv = chart.get("is_antv", False)
                
                panels_html += f'''
                <div class="chart-card">
                '''
                
                if config:
                    chart_id = chart.get("chart_id", "")
                    if use_antv or is_antv:
                        # AntV G2使用div容器
                        panels_html += f'<div class="chart-wrapper" id="{chart_id}"></div>\n'
                    else:
                        # Chart.js使用canvas
                        panels_html += f'<div class="chart-wrapper">\n'
                        panels_html += f'<canvas id="{chart_id}"></canvas>\n'
                        panels_html += f'</div>\n'
                else:
                    # 获取相对路径
                    relative_img_path = convert_to_relative_path(img)
                    panels_html += f'<img src="{relative_img_path}" alt="{escape(caption)}">\n'
                
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
    
    # 生成图表脚本
    if use_antv:
        chart_script = generate_antv_script(chart_configs)
    else:
        chart_script = generate_chartjs_script(chart_configs)
    
    # 构建完整的HTML
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据分析仪表盘</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    {'' if use_antv else '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>'}
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
        
        .chart-wrapper {{
            height: 400px;
            position: relative;
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
            
            .chart-container {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="dashboard-header">
        <h1 class="dashboard-title">数据分析仪表盘{' (AntV G2)' if use_antv else ' (Chart.js)'}</h1>
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
    parser.add_argument('--use-antv', action='store_true', help='Use AntV G2 for chart rendering instead of Chart.js')
    args = parser.parse_args()

    # Get absolute path for the markdown file
    md_path = os.path.abspath(args.markdown_file)
    
    # Determine output path - place HTML in same directory as markdown file if no path specified
    output_path = args.output
    if not os.path.dirname(output_path):
        md_dir = os.path.dirname(md_path)
        output_path = os.path.join(md_dir, output_path)
    
    sections = parse_markdown(md_path)
    html = fill_template(sections, args.template, args.use_antv)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ Report generated: {output_path}")
    if args.use_antv:
        print("  - Using AntV G2 for chart rendering")
    else:
        print("  - Using Chart.js for chart rendering")
