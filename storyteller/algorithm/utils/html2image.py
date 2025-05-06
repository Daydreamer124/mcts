import asyncio
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright
import os
from typing import Optional

async def html_to_image(html_content: str, output_path: Optional[str] = None, width: int = 1280, height: int = None) -> str:
    """
    将HTML内容转换为图片
    
    参数:
        html_content: HTML字符串
        output_path: 输出图片路径（可选）
        width: 视口宽度
        height: 视口高度（如果为None则自动计算）
    
    返回:
        str: 生成的图片路径
    """
    async with async_playwright() as p:
        # 启动浏览器
        browser = await p.chromium.launch()
        page = await browser.new_page()
        
        # 设置视口大小
        await page.set_viewport_size({"width": width, "height": height or 800})
        
        # 加载HTML内容
        await page.set_content(html_content, wait_until="networkidle")
        
        # 如果没有指定高度，获取内容实际高度
        if height is None:
            height = await page.evaluate('document.documentElement.scrollHeight')
            await page.set_viewport_size({"width": width, "height": height})
        
        # 确定输出路径
        if output_path is None:
            output_dir = os.path.join(os.path.dirname(__file__), "../../../output/temp")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, "report_snapshot.png")
        
        # 截图
        await page.screenshot(
            path=output_path,
            full_page=True,
            type="png"
        )
        
        await browser.close()
        return output_path

def convert_html_to_image(html_content: str, output_path: Optional[str] = None) -> str:
    """同步版本的HTML转图片函数"""
    return asyncio.run(html_to_image(html_content, output_path))

def convert_html_file_to_image(html_file, output_path=None, debug=False):
    """
    将HTML文件转换为图片，特别优化以确保AntV G2图表正确渲染
    
    参数:
        html_file: HTML文件路径
        output_path: 输出图片路径（可选）
        debug: 是否打印调试信息
    
    返回:
        str: 生成的图片路径
    """
    # 确定输出路径
    if output_path is None:
        output_path = os.path.splitext(html_file)[0] + ".png"
    
    if debug:
        print(f"开始处理HTML文件: {html_file}")
        print(f"输出路径: {output_path}")
    
    # 使用 playwright 的同步 API
    with sync_playwright() as playwright:
        # 启动带有参数的浏览器，禁用沙箱可以减少一些问题
        browser = playwright.chromium.launch(
            args=['--no-sandbox', '--disable-setuid-sandbox'],
            headless=True  # 无头浏览器模式
        )
        
        # 创建页面对象
        context = browser.new_context(
            viewport={'width': 1280, 'height': 800},
            device_scale_factor=1.5  # 提高渲染清晰度
        )
        page = context.new_page()
        
        try:
        # 加载HTML文件
            page.goto(f"file://{os.path.abspath(html_file)}", 
                      wait_until="domcontentloaded",  # 等待DOM内容加载
                      timeout=60000)  # 增加超时时间到60秒
            
            if debug:
                print("HTML文件已加载")
            
            # 等待DOM完全加载
            page.wait_for_load_state("load", timeout=60000)
            if debug:
                print("页面完全加载")
            
            # 确保外部脚本加载完成
            page.wait_for_load_state("networkidle", timeout=60000)
            if debug:
                print("网络请求已完成")
            
            # 检查页面中是否有AntV G2图表容器
            has_antv_charts = page.evaluate("""
                () => !!document.querySelector('div[id^="antv_chart_"]')
            """)
            
            if has_antv_charts:
                if debug:
                    print("发现AntV G2图表容器")
                
                # 等待AntV G2图表容器
                try:
                    page.wait_for_selector('div[id^="antv_chart_"]', state="attached", timeout=30000)
                    if debug:
                        print("AntV G2图表容器已附加到DOM")
                except Exception as e:
                    if debug:
                        print(f"等待图表容器时出错: {e}")
                
                # 检查并等待图表初始化完成
                try:
                    # 注入监听脚本，用于检测图表初始化和渲染完成
                    page.add_script_tag(content="""
                    window.chartsInitialized = false;
                    window.chartsRendered = false;
                    
                    // 创建一个Promise，当所有图表渲染完成时解析
                    window.waitForChartsRendered = new Promise((resolve) => {
                        // 检查window.chartInstances对象
                        function checkChartInstances() {
                            if (window.chartInstances && Object.keys(window.chartInstances).length > 0) {
                                const charts = Object.values(window.chartInstances);
                                window.chartsInitialized = true;
                                console.log('图表实例已初始化: ' + charts.length + '个');
                                
                                // 检查每个图表容器是否有内容
                                const chartContainers = document.querySelectorAll('div[id^="antv_chart_"]');
                                let allRendered = true;
                                
                                chartContainers.forEach(container => {
                                    // 检查容器中是否有canvas元素或其他G2渲染的元素
                                    const hasContent = container.querySelector('canvas') !== null;
                                    if (!hasContent) {
                                        allRendered = false;
                                        console.log('图表容器 ' + container.id + ' 未渲染内容');
                                    }
                                });
                                
                                window.chartsRendered = allRendered;
                                if (allRendered) {
                                    console.log('所有图表已完成渲染');
                                    resolve(true);
                                } else {
                                    console.log('部分图表未渲染，尝试触发重绘');
                                    // 尝试重绘
                                    triggerChartRender();
                                    // 延迟再次检查
                                    setTimeout(checkAgain, 2000);
                                }
                            } else {
                                console.log('未找到图表实例，等待DOMContentLoaded事件');
                                // 等待DOMContentLoaded事件，可能图表初始化在此事件后
                                if (document.readyState === 'complete') {
                                    // 如果DOM已经加载完成但没有找到图表实例，尝试强制初始化
                                    triggerChartRender();
                                    setTimeout(checkAgain, 2000);
                                } else {
                                    document.addEventListener('DOMContentLoaded', function() {
                                        setTimeout(checkAgain, 1000);
                                    });
                                }
                            }
                        }
                        
                        // 重新检查图表渲染状态
                        function checkAgain() {
                            const chartContainers = document.querySelectorAll('div[id^="antv_chart_"]');
                            let allRendered = true;
                            
                            if (chartContainers.length === 0) {
                                console.log('未找到图表容器，可能图表未正确初始化');
                                resolve(false);
                                return;
                            }
                            
                            chartContainers.forEach(container => {
                                const hasContent = container.querySelector('canvas') !== null;
                                if (!hasContent) {
                                    allRendered = false;
                                    console.log('图表容器 ' + container.id + ' 仍未渲染内容');
                                }
                            });
                            
                            window.chartsRendered = allRendered;
                            if (allRendered) {
                                console.log('所有图表已完成渲染');
                                resolve(true);
                            } else {
                                console.log('部分图表仍未渲染，使用备用方法');
                                // 尝试最后的备用方法
                                forceRenderCharts();
                                // 无论成功与否，最终解析Promise
                                setTimeout(() => resolve(false), 2000);
                            }
                        }
                        
                        // 触发图表重绘
                        function triggerChartRender() {
                            try {
                                // 模拟窗口resize事件，通常会触发图表重绘
                                window.dispatchEvent(new Event('resize'));
                                console.log('已触发窗口resize事件');
                                
                                // 如果存在chartInstances对象，尝试调用render方法
                                if (window.chartInstances) {
                                    Object.values(window.chartInstances).forEach(function(chart) {
                                        if (chart && typeof chart.render === 'function') {
                                            chart.render();
                                            console.log('已调用图表render方法');
                                        }
                                    });
                                }
                            } catch (e) {
                                console.error('尝试重绘图表时出错:', e);
                            }
                        }
                        
                        // 强制渲染图表的最后尝试
                        function forceRenderCharts() {
                            try {
                                // 搜索页面中的所有初始化图表的函数
                                const initFunctions = [];
                                for (let key in window) {
                                    if (typeof window[key] === 'function' && 
                                        key.toLowerCase().includes('chart') && 
                                        key.toLowerCase().includes('init')) {
                                        initFunctions.push(window[key]);
                                        console.log('找到可能的图表初始化函数: ' + key);
                                    }
                                }
                                
                                // 尝试调用这些函数
                                initFunctions.forEach(func => {
                                    try {
                                        func();
                                        console.log('已调用可能的初始化函数');
                                    } catch (e) {
                                        console.error('调用初始化函数失败:', e);
                                    }
                                });
                                
                                // 最后一次触发resize事件
                                window.dispatchEvent(new Event('resize'));
                            } catch (e) {
                                console.error('强制渲染图表失败:', e);
                            }
                        }
                        
                        // 立即开始检查
                        checkChartInstances();
                    });
                    """)
                    
                    # 等待足够长的时间让图表渲染
            page.wait_for_timeout(3000)
                    
                    # 检查图表是否已初始化和渲染
                    charts_initialized = page.evaluate("window.chartsInitialized")
                    charts_rendered = page.evaluate("window.chartsRendered")
                    
                    if debug:
                        if charts_initialized:
                            print("图表已初始化完成")
                        else:
                            print("未检测到图表初始化完成")
                        
                        if charts_rendered:
                            print("图表已完全渲染")
                        else:
                            print("图表渲染可能未完成")
                    
                    # 等待渲染完成Promise解析结果
                    try:
                        wait_result = page.evaluate("window.waitForChartsRendered")
                        if debug and wait_result:
                            print("等待图表渲染的Promise已解析: " + str(wait_result))
                    except Exception as e:
                        if debug:
                            print(f"等待图表渲染Promise时出错: {e}")
                    
                    # 额外注入脚本触发图表重绘（再次尝试）
                    page.add_script_tag(content="""
                    try {
                        // 尝试获取所有G2图表容器
                        var chartContainers = document.querySelectorAll('div[id^="antv_chart_"]');
                        console.log('找到 ' + chartContainers.length + ' 个图表容器');
                        
                        // 如果有图表容器，尝试手动触发渲染
                        if (chartContainers.length > 0) {
                            // 创建并触发resize事件，这通常会导致图表重绘
                            window.dispatchEvent(new Event('resize'));
                            console.log('已触发窗口resize事件');
                        }
                        
                        // 如果存在chartInstances对象，尝试调用render方法
                        if (window.chartInstances) {
                            Object.values(window.chartInstances).forEach(function(chart) {
                                if (chart && typeof chart.render === 'function') {
                                    chart.render();
                                    console.log('已调用图表render方法');
                                }
                            });
                        }
                    } catch (e) {
                        console.error('尝试重绘图表时出错:', e);
                    }
                    """)
                    
                    # 再次等待以确保重绘完成
                    page.wait_for_timeout(5000)
                    
                except Exception as e:
                    if debug:
                        print(f"等待图表初始化时出错: {e}")
            else:
                if debug:
                    print("页面中未找到AntV G2图表容器")
            
            # 等待图片元素（如果有的话）
            try:
                has_images = page.evaluate("!!document.querySelector('img')")
                if has_images:
                    if debug:
                        print("页面包含图片元素，等待图片加载")
                    page.wait_for_selector("img", state="visible", timeout=30000)
        except Exception as e:
                if debug:
                    print(f"等待图片元素时出错: {e}")
            
            # 最后的等待，确保所有渲染都完成
            page.wait_for_timeout(5000)
            if debug:
                print("最终等待完成，准备截图")
            
            # 获取页面实际高度并设置视口
            height = page.evaluate("document.documentElement.scrollHeight")
            page.set_viewport_size({"width": 1280, "height": height})
        
        # 截图
        page.screenshot(path=output_path, full_page=True)
            if debug:
                print(f"截图完成: {output_path}")
            
        except Exception as e:
            print(f"截图过程中出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
        browser.close()
    
    return output_path 

def test_html_to_image():
    """测试函数：测试将HTML文件转换为图片"""
    import argparse
    
    parser = argparse.ArgumentParser(description='测试HTML转图片功能')
    parser.add_argument('--html', type=str, required=True, help='HTML文件路径')
    parser.add_argument('--out', type=str, help='输出图片路径')
    parser.add_argument('--debug', action='store_true', help='打印调试信息')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.html):
        print(f"错误: 指定的HTML文件不存在: {args.html}")
        return
    
    print(f"开始转换HTML文件: {args.html}")
    output_path = convert_html_file_to_image(args.html, args.out, debug=args.debug)
    print(f"转换完成! 图片保存在: {output_path}")
    
    # 尝试自动打开图片
    try:
        import platform
        import subprocess
        
        system = platform.system()
        if system == 'Darwin':  # macOS
            subprocess.call(['open', output_path])
        elif system == 'Windows':
            subprocess.call(['start', output_path], shell=True)
        elif system == 'Linux':
            subprocess.call(['xdg-open', output_path])
    except Exception as e:
        print(f"无法自动打开图片: {e}")

if __name__ == "__main__":
    test_html_to_image() 