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

def convert_html_file_to_image(html_file, output_path=None):
    """将HTML文件转换为图片"""
    # 确定输出路径
    if output_path is None:
        output_path = os.path.splitext(html_file)[0] + ".png"
    
    # 使用 playwright 的同步 API
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        
        # 加载HTML文件
        page.goto(f"file://{os.path.abspath(html_file)}")
        
        try:
            # 增加等待时间，并添加错误处理
            page.wait_for_selector("img", state="visible", timeout=30000)  # 增加到30秒
            # 额外等待以确保所有内容都加载完成
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"警告：等待图片加载时出现问题: {e}")
            # 即使没有找到图片元素，也继续执行
            pass
        
        # 截图
        page.screenshot(path=output_path, full_page=True)
        browser.close()
    
    return output_path 