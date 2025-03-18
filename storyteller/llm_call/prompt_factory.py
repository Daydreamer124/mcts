from pathlib import Path
from typing import Dict, Any

# 设置模板目录路径
TEMPLATE_DIR = Path("storyteller/templates")

# 存储模板的字典
TEMPLATE_DICT = {}

# 加载所有模板文件
for template_file in TEMPLATE_DIR.glob("*.txt"):
    with open(template_file, "r", encoding="utf-8") as f:
        TEMPLATE_DICT[template_file.stem] = f.read()

def get_prompt(template_name: str, template_args: Dict[str, str]) -> str:
    template = TEMPLATE_DICT[template_name]
    return template.format(**template_args)
