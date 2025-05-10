"""
ChartConfigExtractor示例程序

这个脚本展示如何使用ChartConfigExtractor从可视化代码中提取图表配置信息，并转换为AntV G2配置。
"""

import os
import sys
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# 获取当前文件的目录
current_dir = os.path.dirname(os.path.abspath(__file__))

# 添加项目根目录到Python路径（假设当前文件在storyteller/algorithm/utils/目录下）
project_root = os.path.abspath(os.path.join(current_dir, '../../..'))
if project_root not in sys.path:
    sys.path.append(project_root)

# 导入ChartConfigExtractor
try:
    from storyteller.algorithm.utils.chart_config_extractor import ChartConfigExtractor
except ImportError:
    # 如果无法从包中导入，尝试直接导入
    from chart_config_extractor import ChartConfigExtractor

# 创建示例数据
def create_sample_data():
    """创建示例购物数据"""
    np.random.seed(42)
    
    # 创建一个DataFrame
    df = pd.DataFrame({
        'Age': np.random.randint(18, 70, 100),
        'Gender': np.random.choice(['Male', 'Female'], 100),
        'Purchase_Amount__USD_': np.random.normal(50, 20, 100).round(2),
        'Item_Category': np.random.choice(['Electronics', 'Clothing', 'Food', 'Books'], 100),
        'Payment_Method': np.random.choice(['Credit Card', 'Cash', 'PayPal'], 100),
        'Customer_Satisfaction': np.random.randint(1, 6, 100)
    })
    
    return df

# 加载数据集
def load_dataset(filepath=None):
    """加载数据集或创建示例数据"""
    try:
        if filepath and os.path.exists(filepath):
            print(f"加载数据集: {filepath}")
            return pd.read_csv(filepath)
        else:
            print("未找到指定数据集，使用示例数据")
            return create_sample_data()
    except Exception as e:
        print(f"加载数据集时出错: {str(e)}")
        print("使用示例数据")
        return create_sample_data()

def test_binning_extraction():
    """测试分箱操作的提取和处理"""
    # 创建示例数据
    df = create_sample_data()
    
    # 定义要测试的分箱代码
    bin_code = """
import matplotlib.pyplot as plt
import numpy as np

def plot(data):
    plt.figure(figsize=(10, 6))
    plt.hist(data['Purchase_Amount__USD_'], bins=30, edgecolor='black')
    plt.title('Distribution of Purchase Amounts')
    plt.xlabel('Purchase Amount (USD)')
    plt.ylabel('Count')
    return plt

chart = plot(data)
"""
    
    print("\n==== 测试直方图 ====")
    print("1. 从代码中提取配置...")
    
    # 创建临时的数据上下文文件
    context = {
        "columns": [
            {"name": "Purchase_Amount__USD_", "type": "numeric"},
            {"name": "Age", "type": "numeric"},
            {"name": "Gender", "type": "categorical"},
            {"name": "Item_Category", "type": "categorical"}
        ]
    }
    
    context_file = "temp_context.json"
    with open(context_file, "w") as f:
        json.dump(context, f)
    
    extractor = ChartConfigExtractor(data_context_path=context_file)
    config = extractor.extract_from_code(bin_code)
    
    print("\n提取的配置:")
    print(json.dumps(config, indent=2, ensure_ascii=False))
    
    # 处理数据
    print("\n2. 使用提取的配置处理数据...")
    chart_data = extractor.resolve_chart_data(df, config)
    
    print("\n处理后的数据:")
    print(json.dumps(chart_data[:5], indent=2, ensure_ascii=False))  # 只显示前5条数据
    
    # 转换为AntV配置
    print("\n3. 转换为AntV配置...")
    antv_config = extractor.convert_to_antv_config(config, chart_data)
    
    print("\nAntV配置:")
    print(json.dumps(antv_config, indent=2, ensure_ascii=False))
    
    # 清理临时文件
    os.remove(context_file)

def test_scatter_chart():
    """测试散点图数据处理"""
    # 创建示例数据
    df = create_sample_data()
    
    # 定义要测试的散点图代码
    scatter_code = """
import matplotlib.pyplot as plt

def plot(data):
    plt.figure(figsize=(10, 6))
    plt.scatter(data['Age'], data['Purchase_Amount__USD_'], alpha=0.6)
    plt.title('Age vs Purchase Amount')
    plt.xlabel('Age')
    plt.ylabel('Purchase Amount (USD)')
    return plt

chart = plot(data)
"""
    
    print("\n==== 测试散点图 ====")
    print("1. 从代码中提取配置...")
    
    # 创建临时的数据上下文文件
    context = {
        "columns": [
            {"name": "Purchase_Amount__USD_", "type": "numeric"},
            {"name": "Age", "type": "numeric"},
            {"name": "Gender", "type": "categorical"},
            {"name": "Item_Category", "type": "categorical"}
        ]
    }
    
    context_file = "temp_context.json"
    with open(context_file, "w") as f:
        json.dump(context, f)
    
    extractor = ChartConfigExtractor(data_context_path=context_file)
    config = extractor.extract_from_code(scatter_code)
    
    print("\n提取的配置:")
    print(json.dumps(config, indent=2, ensure_ascii=False))
    
    # 处理数据
    print("\n2. 使用提取的配置处理数据...")
    chart_data = extractor.resolve_chart_data(df, config)
    
    print("\n处理后的数据:")
    print(json.dumps(chart_data[:5], indent=2, ensure_ascii=False))  # 只显示前5条数据
    
    # 转换为AntV配置
    print("\n3. 转换为AntV配置...")
    antv_config = extractor.convert_to_antv_config(config, chart_data)
    
    print("\nAntV配置:")
    print(json.dumps(antv_config, indent=2, ensure_ascii=False))
    
    # 清理临时文件
    os.remove(context_file)

def test_bar_chart():
    """测试柱状图数据处理"""
    # 创建示例数据
    df = create_sample_data()
    
    # 定义要测试的柱状图代码
    bar_code = """
import matplotlib.pyplot as plt

def plot(data):
    plt.figure(figsize=(10, 6))
    data.groupby('Item_Category')['Purchase_Amount__USD_'].mean().plot(kind='bar')
    plt.title('Average Purchase Amount by Category')
    plt.xlabel('Category')
    plt.ylabel('Average Purchase Amount (USD)')
    return plt

chart = plot(data)
"""
    
    print("\n==== 测试柱状图 ====")
    print("1. 从代码中提取配置...")
    
    # 创建临时的数据上下文文件
    context = {
        "columns": [
            {"name": "Purchase_Amount__USD_", "type": "numeric"},
            {"name": "Age", "type": "numeric"},
            {"name": "Gender", "type": "categorical"},
            {"name": "Item_Category", "type": "categorical"}
        ]
    }
    
    context_file = "temp_context.json"
    with open(context_file, "w") as f:
        json.dump(context, f)
    
    extractor = ChartConfigExtractor(data_context_path=context_file)
    config = extractor.extract_from_code(bar_code)
    
    print("\n提取的配置:")
    print(json.dumps(config, indent=2, ensure_ascii=False))
    
    # 处理数据
    print("\n2. 使用提取的配置处理数据...")
    chart_data = extractor.resolve_chart_data(df, config)
    
    print("\n处理后的数据:")
    print(json.dumps(chart_data, indent=2, ensure_ascii=False))
    
    # 转换为AntV配置
    print("\n3. 转换为AntV配置...")
    antv_config = extractor.convert_to_antv_config(config, chart_data)
    
    print("\nAntV配置:")
    print(json.dumps(antv_config, indent=2, ensure_ascii=False))
    
    # 清理临时文件
    os.remove(context_file)

def main():
    """主函数"""
    # 测试直方图
    test_binning_extraction()
    
    # 测试散点图
    test_scatter_chart()
    
    # 测试柱状图
    test_bar_chart()

if __name__ == "__main__":
    main() 