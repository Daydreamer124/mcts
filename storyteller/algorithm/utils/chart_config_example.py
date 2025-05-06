"""
ChartConfigExtractor示例程序

这个脚本展示如何使用ChartConfigExtractor从可视化代码中提取图表配置信息。
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
    from storyteller.algorithm.utils.chart_config_extractor import ChartConfigExtractor, convert_to_chartjs_config, convert_to_antv_config
except ImportError:
    # 如果无法从包中导入，尝试直接导入
    from chart_config_extractor import ChartConfigExtractor, convert_to_chartjs_config, convert_to_antv_config

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
import pandas as pd
import seaborn as sns

def plot(data: pd.DataFrame):
    plt.figure(figsize=(10, 6))
    sns.boxplot(x='Gender', y='Review_Rating', data=data, palette='Set2')
    plt.title('Comparison of review ratings between male and female customers', wrap=True)
    plt.xlabel('Gender')
    plt.ylabel('Review Rating')
    plt.legend(title='Gender', labels=['Male', 'Female'])
    return plt;

chart = plot(data)
"""
    
    print("\n==== 测试分箱操作 ====")
    print("1. 从代码中提取配置...")
    extractor = ChartConfigExtractor()
    config = extractor.extract_from_code(bin_code)
    
    print("\n提取的配置:")
    print(json.dumps(config, indent=2, ensure_ascii=False))
    
    # 如果没有Review_Rating列，添加一个模拟列
    if 'Review_Rating' not in df.columns:
        print("\n添加模拟的Review_Rating列用于测试")
        df['Review_Rating'] = np.random.randint(1, 6, len(df))
    
    # 直接测试数据处理，不依赖derived_columns是否存在
    print("\n2. 使用提取的配置处理数据...")
    chart_data = extractor.extract_chart_data(df, config)
    
    print("\n处理后的Chart.js数据:")
    print(json.dumps(chart_data, indent=2, ensure_ascii=False))
    
    # 转换为Chart.js配置
    print("\n3. 转换为Chart.js配置...")
    chartjs_config = extractor.convert_to_chartjs_config(config, chart_data)
    
    print("\nChart.js配置:")
    print(json.dumps(chartjs_config, indent=2, ensure_ascii=False))
    
    # 转换为AntV配置
    print("\n4. 转换为AntV配置...")
    antv_config = extractor.convert_to_antv_config(config, chart_data)
    
    print("\nAntV配置:")
    print(json.dumps(antv_config, indent=2, ensure_ascii=False))

def test_scatter_chart():
    """测试散点图数据处理"""
    # 创建示例数据
    df = create_sample_data()
    
    # 定义要测试的散点图代码
    scatter_code = """
import matplotlib.pyplot as plt
import pandas as pd

def plot(data: pd.DataFrame):
    plt.figure(figsize=(10, 6))
    plt.scatter(data['Age'], data['Purchase_Amount__USD_'], alpha=0.6, edgecolors='w', linewidth=0.5)
    plt.xlabel('Age')
    plt.ylabel('Purchase Amount (USD)')
    plt.title('Age vs. purchase amount correlation', wrap=True)
    plt.grid(True)
    plt.legend(['Purchase Amount'], loc='upper right')
    return plt;

chart = plot(data)
"""
    
    print("\n==== 测试散点图 ====")
    print("1. 从代码中提取配置...")
    extractor = ChartConfigExtractor()
    config = extractor.extract_from_code(scatter_code)
    
    print("\n提取的配置:")
    print(json.dumps(config, indent=2, ensure_ascii=False))
    
    # 测试数据处理
    print("\n2. 使用提取的配置处理数据...")
    chart_data = extractor.extract_chart_data(df, config)
    
    print("\n处理后的Chart.js数据:")
    print(json.dumps(chart_data, indent=2, ensure_ascii=False))
    
    # 转换为Chart.js配置
    print("\n3. 转换为Chart.js配置...")
    chartjs_config = extractor.convert_to_chartjs_config(config, chart_data)
    
    print("\nChart.js配置:")
    print(json.dumps(chartjs_config, indent=2, ensure_ascii=False))
    
    # 转换为AntV配置
    print("\n4. 转换为AntV配置...")
    antv_config = extractor.convert_to_antv_config(config, chart_data)
    
    print("\nAntV配置:")
    print(json.dumps(antv_config, indent=2, ensure_ascii=False))

def main():
    """主函数"""
    # 测试分箱提取和处理
    test_binning_extraction()
    
    # 测试散点图处理
    test_scatter_chart()

if __name__ == "__main__":
    main() 