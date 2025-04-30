import ast
import json
import re
from typing import Dict, Any, List, Optional, Union, Tuple
import pandas as pd

class ChartConfigExtractor(ast.NodeVisitor):
    """
    使用AST(抽象语法树)解析matplotlib和seaborn可视化代码，
    提取图表配置信息，以便转换为Chart.js配置。
    """
    
    def __init__(self, dataframe_var_name="df"):
        self.default_dataframe_var = dataframe_var_name
        self.current_dataframe_vars = set([dataframe_var_name])  # 跟踪所有DataFrame变量
        self.reset()
    
    def reset(self):
        """重置图表配置状态"""
        self.chart_type = "bar"  # 默认为柱状图
        self.title = ""
        self.x_column = ""  # 数据列名称
        self.y_column = ""
        self.x_label = ""   # 轴标签
        self.y_label = ""
        self.hue_column = "" # 分组列
        self.data_columns = []
        self.current_dataframe_vars = set([self.dataframe_var_name])
        self.color = None
        self.colors = []
        self.bins = None
        self.legend = True
        self.grid = False
        self.uses_seaborn = False
        self.uses_plotly = False
        self.plotting_var = None
        self.is_stacked = False
        self.seen_vars = {}
        self.agg_method = None   # 聚合方法 (sum, mean, count等)
        
        # 添加饼图特定字段
        self.pie_data = []       # 饼图数据
        self.pie_labels = []     # 饼图标签
        self.pie_category_field = "category"  # 饼图类别字段名称
        self.pie_value_field = "value"        # 饼图数值字段名称
    
    def visit_FunctionDef(self, node):
        """
        处理函数定义，识别数据处理和可视化函数
        """
        # 记录函数定义
        func_name = node.name
        arg_names = []
        
        # 提取函数参数
        for arg in node.args.args:
            if hasattr(arg, 'annotation') and arg.annotation:
                # 检查是否有类型注解，寻找DataFrame类型
                if hasattr(arg.annotation, 'id') and arg.annotation.id == 'DataFrame':
                    # 这是一个DataFrame参数
                    self.current_dataframe_vars.add(arg.arg)
                    print(f"识别到函数 {func_name} 的DataFrame参数: {arg.arg}")
                
                # 检查是否有DataFrame类型提示（pd.DataFrame）
                elif hasattr(arg.annotation, 'value') and hasattr(arg.annotation.value, 'id'):
                    if arg.annotation.value.id == 'pd' and hasattr(arg.annotation, 'attr') and arg.annotation.attr == 'DataFrame':
                        self.current_dataframe_vars.add(arg.arg)
                        print(f"识别到函数 {func_name} 的pd.DataFrame参数: {arg.arg}")
            
            arg_names.append(arg.arg)
        
        # 根据函数返回值，尝试预判绘图类型
        for node_stmt in node.body:
            if isinstance(node_stmt, ast.Return):
                if isinstance(node_stmt.value, ast.Name) and node_stmt.value.id == 'plt':
                    # 这是一个返回plt的函数，可能是绘图函数
                    print(f"识别到函数 {func_name} 返回plt对象")
                
                # 识别返回图形或轴对象的函数
                elif isinstance(node_stmt.value, ast.Tuple) and len(node_stmt.value.elts) >= 2:
                    if (hasattr(node_stmt.value.elts[0], 'id') and node_stmt.value.elts[0].id in ['fig', 'figure']) or \
                       (hasattr(node_stmt.value.elts[1], 'id') and node_stmt.value.elts[1].id in ['ax', 'axes']):
                        print(f"识别到函数 {func_name} 返回(fig, ax)元组")
        
        # 存储函数信息
        self.functions[func_name] = {
            'args': arg_names,
            'is_plotting_func': any(['plt' in stmt.value.id if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Name) else False for stmt in node.body if isinstance(stmt, ast.Return)])
        }
        
        # 继续访问函数体
        self.generic_visit(node)
    
    def visit_Assign(self, node):
        """
        处理变量赋值，跟踪数据处理变量和流程
        """
        # 仅处理简单赋值(单一目标)
        if len(node.targets) == 1:
            # 处理变量赋值
            if isinstance(node.targets[0], ast.Name):
                var_name = node.targets[0].id
                
                # 检查是否赋值给新变量的是已知的DataFrame变量
                if isinstance(node.value, ast.Name) and node.value.id in self.current_dataframe_vars:
                    self.current_dataframe_vars.add(var_name)
                    print(f"发现新的DataFrame变量赋值: {var_name} = {node.value.id}")
                
                # 检查是否是通过pd.DataFrame()创建的新DataFrame
                elif isinstance(node.value, ast.Call) and hasattr(node.value.func, 'value') and hasattr(node.value.func, 'attr'):
                    if hasattr(node.value.func.value, 'id') and node.value.func.value.id == 'pd' and node.value.func.attr == 'DataFrame':
                        self.current_dataframe_vars.add(var_name)
                        print(f"发现通过pd.DataFrame()创建的新变量: {var_name}")
                
                # 检查是否是DataFrame方法的调用链
                elif isinstance(node.value, ast.Call):
                    # 处理嵌套方法调用链，如 df.groupby().sum()
                    self._process_method_chain(var_name, node.value)
                    
                    # 特别关注数据处理方法
                    df_var, method, args, kwargs = self._extract_method_call_info(node.value)
                    if df_var in self.current_dataframe_vars:
                        print(f"发现DataFrame方法调用: {var_name} = {df_var}.{method}(...)")
                        self.current_dataframe_vars.add(var_name)
                        
                        # 记录此变量用于数据处理
                        self.variable_assignments[var_name] = {
                            'source_df': df_var,
                            'method': method,
                            'args': args,
                            'kwargs': kwargs
                        }
                        
                        # 分析groupby和pivot_table方法，提取列名
                        if method == 'groupby':
                            self._extract_groupby_columns(var_name, args, kwargs)
                        elif method == 'pivot_table':
                            self._extract_pivot_columns(var_name, args, kwargs)
                        elif method == 'plot':
                            self._extract_plot_columns(var_name, args, kwargs)
            
            # 处理子脚本赋值，如 df['new_col'] = values
            elif isinstance(node.targets[0], ast.Subscript) and hasattr(node.targets[0].value, 'id'):
                df_var = node.targets[0].value.id
                if df_var in self.current_dataframe_vars:
                    # 提取列名
                    col_name = self._extract_subscript_key(node.targets[0])
                    if col_name:
                        print(f"发现DataFrame新列创建: {df_var}['{col_name}']")
                        if col_name not in self.data_columns:
                            self.data_columns.append(col_name)
        
        # 继续递归遍历
        self.generic_visit(node)
    
    def _process_method_chain(self, var_name, call_node):
        """处理方法调用链，如df.groupby().sum()"""
        # 初始化方法链
        chain = []
        
        # 遍历方法调用链
        current = call_node
        while isinstance(current, ast.Call):
            if hasattr(current.func, 'attr'):
                # 添加方法名称
                method_name = current.func.attr
                chain.append(method_name)
                
                # 检测聚合方法调用
                if method_name in ['mean', 'sum', 'count', 'median', 'min', 'max', 'avg', 'average']:
                    self.agg_method = method_name
                    print(f"检测到聚合方法: {self.agg_method}")
                
                # 检测value_counts方法，这是一个特殊的计数聚合
                if method_name == 'value_counts':
                    self.agg_method = 'count'
                    print(f"检测到value_counts方法，设置聚合方法为: count")
                    
                    # 尝试获取调用value_counts的列
                    if hasattr(current.func.value, 'attr'):
                        # 直接属性访问，如df.column_name
                        column_name = current.func.value.attr
                        print(f"检测到对列'{column_name}'应用value_counts操作")
                        self.x_column = column_name
                        self.y_column = 'count'
                        if column_name not in self.data_columns:
                            self.data_columns.append(column_name)
                    elif hasattr(current.func.value, 'value') and hasattr(current.func.value, 'slice'):
                        # 下标访问，如df['column_name']
                        if hasattr(current.func.value.slice, 'value') and isinstance(current.func.value.slice.value, ast.Str):
                            column_name = current.func.value.slice.value.s
                            print(f"检测到对df['{column_name}']应用value_counts操作")
                            self.x_column = column_name
                            self.y_column = 'count'
                            if column_name not in self.data_columns:
                                self.data_columns.append(column_name)
                
                # 如果是特定方法，尝试提取列名
                if method_name in ['groupby', 'agg', 'aggregate', 'sum', 'mean', 'count', 'pivot_table', 'pivot', 'plot']:
                    self._extract_column_from_call(current)
                
                # 处理下一个链节点
                current = current.func.value
            else:
                break
        
        # 方法链是反向的，需要翻转
        chain.reverse()
        
        # 查找链中的基础DataFrame变量
        if isinstance(current, ast.Name) and current.id in self.current_dataframe_vars:
            base_df = current.id
            print(f"识别方法调用链: {base_df}.{'.'.join(chain)} -> {var_name}")
            
            # 记录最终变量作为潜在的绘图数据源
            if chain and chain[-1] in ['plot', 'bar', 'hist', 'line', 'scatter', 'pie']:
                self.plotting_var = var_name
    
    def _extract_method_call_info(self, call_node):
        """从方法调用提取详细信息"""
        df_var = None
        method = None
        args = []
        kwargs = {}
        
        # 提取方法名和DataFrame变量
        if hasattr(call_node.func, 'attr'):
            method = call_node.func.attr
            if hasattr(call_node.func.value, 'id'):
                df_var = call_node.func.value.id
        
        # 提取位置参数
        for arg in call_node.args:
            if isinstance(arg, ast.Constant):
                args.append(arg.value)
            elif isinstance(arg, ast.Str):  # Python 3.7及之前
                args.append(arg.s)
            elif isinstance(arg, ast.Name):
                args.append(arg.id)
            elif isinstance(arg, ast.Subscript) and hasattr(arg.value, 'id'):
                # 处理df[col]形式的参数
                col = self._extract_subscript_key(arg)
                if col:
                    args.append(f"{arg.value.id}['{col}']")
                    # 记录数据列
                    if arg.value.id in self.current_dataframe_vars and col not in self.data_columns:
                        self.data_columns.append(col)
            else:
                args.append(self._get_node_source(arg))
        
        # 提取关键字参数
        for kw in call_node.keywords:
            if isinstance(kw.value, ast.Constant):
                kwargs[kw.arg] = kw.value.value
            elif isinstance(kw.value, ast.Str):  # Python 3.7及之前
                kwargs[kw.arg] = kw.value.s
            elif isinstance(kw.value, ast.Name):
                kwargs[kw.arg] = kw.value.id
            elif isinstance(kw.value, ast.Subscript) and hasattr(kw.value.value, 'id'):
                # 处理df[col]形式的参数
                col = self._extract_subscript_key(kw.value)
                if col:
                    kwargs[kw.arg] = f"{kw.value.value.id}['{col}']"
                    # 记录数据列
                    if kw.value.value.id in self.current_dataframe_vars and col not in self.data_columns:
                        self.data_columns.append(col)
            else:
                kwargs[kw.arg] = self._get_node_source(kw.value)
        
        return df_var, method, args, kwargs
    
    def _extract_groupby_columns(self, var_name, args, kwargs):
        """从groupby操作中提取列名"""
        group_columns = []
        
        # 处理位置参数
        for arg in args:
            if isinstance(arg, str):
                # 直接字符串参数
                if arg.startswith("[") and arg.endswith("]"):
                    # 可能是列表字符串，尝试解析
                    try:
                        cols = json.loads(arg.replace("'", '"'))
                        if isinstance(cols, list):
                            group_columns.extend(cols)
                    except Exception:
                        pass
                elif not arg.startswith(self.default_dataframe_var):
                    # 单列名
                    group_columns.append(arg)
        
        # 处理by关键字参数
        if 'by' in kwargs:
            by_val = kwargs['by']
            if isinstance(by_val, str):
                if by_val.startswith("[") and by_val.endswith("]"):
                    # 尝试解析列表
                    try:
                        cols = json.loads(by_val.replace("'", '"'))
                        if isinstance(cols, list):
                            group_columns.extend(cols)
                    except Exception:
                        pass
                elif not by_val.startswith(self.default_dataframe_var):
                    # 单列名
                    group_columns.append(by_val)
        
        # 设置x和hue列
        if group_columns:
            print(f"从groupby提取列名: {group_columns}")
            # 添加到已知数据列
            for col in group_columns:
                if col not in self.data_columns:
                    self.data_columns.append(col)
            
            # 设置X轴和色调列
            if not self.x_column and len(group_columns) > 0:
                self.x_column = group_columns[0]
                print(f"设置x轴列: {self.x_column}")
            
            if not self.hue_column and len(group_columns) > 1:
                self.hue_column = group_columns[1]
                print(f"设置hue列: {self.hue_column}")
    
    def _extract_pivot_columns(self, var_name, args, kwargs):
        """从pivot_table操作中提取列名"""
        # 处理关键字参数
        if 'index' in kwargs and isinstance(kwargs['index'], str):
            if not kwargs['index'].startswith(self.default_dataframe_var):
                # 添加到已知列
                if kwargs['index'] not in self.data_columns:
                    self.data_columns.append(kwargs['index'])
                # 设置x轴列
                if not self.x_column:
                    self.x_column = kwargs['index']
                    print(f"从pivot_table.index设置x轴列: {self.x_column}")
        
        if 'columns' in kwargs and isinstance(kwargs['columns'], str):
            if not kwargs['columns'].startswith(self.default_dataframe_var):
                # 添加到已知列
                if kwargs['columns'] not in self.data_columns:
                    self.data_columns.append(kwargs['columns'])
                # 设置hue列
                if not self.hue_column:
                    self.hue_column = kwargs['columns']
                    print(f"从pivot_table.columns设置hue列: {self.hue_column}")
        
        if 'values' in kwargs and isinstance(kwargs['values'], str):
            if not kwargs['values'].startswith(self.default_dataframe_var):
                # 添加到已知列
                if kwargs['values'] not in self.data_columns:
                    self.data_columns.append(kwargs['values'])
                # 设置y轴列
                if not self.y_column:
                    self.y_column = kwargs['values']
                    print(f"从pivot_table.values设置y轴列: {self.y_column}")
    
    def _extract_plot_columns(self, var_name, args, kwargs):
        """从plot操作中提取列名"""
        # 检查x和y参数
        if 'x' in kwargs and isinstance(kwargs['x'], str):
            if not kwargs['x'].startswith(self.default_dataframe_var):
                # 添加到已知列
                if kwargs['x'] not in self.data_columns:
                    self.data_columns.append(kwargs['x'])
                # 设置x轴列
                if not self.x_column:
                    self.x_column = kwargs['x']
                    print(f"从plot参数提取x轴列: {self.x_column}")
        
        if 'y' in kwargs and isinstance(kwargs['y'], str):
            if not kwargs['y'].startswith(self.default_dataframe_var):
                # 添加到已知列
                if kwargs['y'] not in self.data_columns:
                    self.data_columns.append(kwargs['y'])
                # 设置y轴列
                if not self.y_column:
                    self.y_column = kwargs['y']
                    print(f"从plot参数提取y轴列: {self.y_column}")
    
    def _extract_column_from_call(self, call_node):
        """从方法调用中提取数据列引用"""
        # 处理位置参数
        for arg in call_node.args:
            if isinstance(arg, ast.Subscript) and hasattr(arg.value, 'id'):
                df_var = arg.value.id
                if df_var in self.current_dataframe_vars:
                    col = self._extract_subscript_key(arg)
                    if col and col not in self.data_columns:
                        self.data_columns.append(col)
                        print(f"从方法调用提取列名: {col}")
        
        # 处理关键字参数
        for kw in call_node.keywords:
            # 特别关注x, y, hue参数
            if kw.arg in ['x', 'y', 'hue'] and isinstance(kw.value, ast.Constant):
                col = kw.value.value
                if col and col not in self.data_columns:
                    self.data_columns.append(col)
                    print(f"从{kw.arg}参数提取列名: {col}")
                    
                    # 设置相应的轴或分组列
                    if kw.arg == 'x' and not self.x_column:
                        self.x_column = col
                    elif kw.arg == 'y' and not self.y_column:
                        self.y_column = col
                    elif kw.arg == 'hue' and not self.hue_column:
                        self.hue_column = col
            
            # 处理df[col]形式的参数
            elif isinstance(kw.value, ast.Subscript) and hasattr(kw.value.value, 'id'):
                df_var = kw.value.value.id
                if df_var in self.current_dataframe_vars:
                    col = self._extract_subscript_key(kw.value)
                    if col and col not in self.data_columns:
                        self.data_columns.append(col)
                        print(f"从{kw.arg}参数提取列名: {col}")
    
    def visit_Call(self, node):
        """
        处理函数调用，提取图表相关的配置
        """
        # 检查是否是属性调用(如 plt.plot, sns.barplot等)
        if isinstance(node.func, ast.Attribute):
            self._process_attribute_call(node)
        # 检查是否是自定义函数调用(如chart = plot(data))
        elif isinstance(node.func, ast.Name):
            self._process_function_call(node)
        
        # 继续递归遍历
        self.generic_visit(node)
    
    def _process_function_call(self, node):
        """处理函数调用，包括自定义函数"""
        func_name = node.func.id
        
        # 检查是否是我们定义过的函数
        if func_name in self.functions:
            print(f"检测到自定义函数调用: {func_name}")
            
            # 如果是绘图函数，尝试识别输入的DataFrame参数
            if self.functions[func_name].get('is_plotting_func', False):
                # 检查函数参数中是否有DataFrame
                arg_names = self.functions[func_name]['args']
                for i, arg in enumerate(node.args):
                    if i < len(arg_names) and isinstance(arg, ast.Name):
                        # 如果参数是变量名，检查是否为已知的DataFrame变量
                        if arg.id in self.current_dataframe_vars:
                            df_param_name = arg_names[i]
                            print(f"函数{func_name}接收DataFrame参数 {arg.id} 作为 {df_param_name}")
                            # 这是绘图使用的DataFrame
                            self.plotting_var = arg.id
        
        # 简单函数调用处理
        elif func_name == 'savefig':
            # 处理保存图表函数
            pass
    
    def _extract_subscript_key(self, subscript_node):
        """从下标访问中提取键值"""
        if hasattr(subscript_node, 'slice'):
            if isinstance(subscript_node.slice, ast.Index):  # Python 3.8及之前
                if isinstance(subscript_node.slice.value, ast.Str):
                    return subscript_node.slice.value.s
                elif isinstance(subscript_node.slice.value, ast.Constant):
                    if isinstance(subscript_node.slice.value.value, str):
                        return subscript_node.slice.value.value
            elif isinstance(subscript_node.slice, ast.Constant):  # Python 3.9+
                if isinstance(subscript_node.slice.value, str):
                    return subscript_node.slice.value
        return None
    
    def _process_attribute_call(self, node):
        """处理属性调用，如plt.plot, sns.barplot等"""
        # 检查调用对象
        obj = getattr(node.func, 'value', None)
        if obj is None:
            return
        
        # 获取对象名称和方法名称
        obj_name = self._get_node_name(obj)
        method_name = node.func.attr
        
        # 处理matplotlib的调用
        if obj_name == 'plt':
            self._handle_plt_call(method_name, node.args, node.keywords)
        # 处理seaborn的调用
        elif obj_name == 'sns':
            self.uses_seaborn = True
            self._handle_sns_call(method_name, node.args, node.keywords)
        # 处理plotly express的调用
        elif obj_name == 'px':
            self.uses_plotly = True
            self._handle_px_call(method_name, node.args, node.keywords)
        # 处理axes对象的调用(如ax.set_xlabel)
        elif obj_name == 'ax' or obj_name == 'axes' or method_name.startswith('set_'):
            self._handle_axes_call(method_name, node.args, node.keywords)
        # 处理figure对象的调用
        elif obj_name == 'fig' or obj_name == 'figure':
            self._handle_figure_call(method_name, node.args, node.keywords)
        # 处理DataFrame变量的方法调用
        elif obj_name in self.current_dataframe_vars:
            self._handle_dataframe_call(obj_name, method_name, node.args, node.keywords)
    
    def _handle_dataframe_call(self, df_name, method_name, args, keywords):
        """处理DataFrame方法调用，如df.plot()"""
        # 检查是否是聚合方法
        if method_name in ['mean', 'sum', 'count', 'median', 'min', 'max', 'avg', 'average']:
            self.agg_method = 'mean' if method_name in ['avg', 'average'] else method_name
            print(f"检测到DataFrame聚合方法: {method_name} -> {self.agg_method}")
        
        # 特别关注绘图方法
        if method_name == 'plot':
            print(f"检测到DataFrame绘图方法: {df_name}.plot()")
            self._extract_from_df_plot(df_name, args, keywords)
        elif method_name in ['bar', 'barh', 'hist', 'pie', 'scatter', 'line']:
            print(f"检测到DataFrame绘图方法: {df_name}.{method_name}()")
            self.chart_type = 'bar' if method_name in ['bar', 'barh', 'hist'] else method_name
            self._extract_from_df_plot(df_name, args, keywords)
    
    def _extract_from_df_plot(self, df_name, args, keywords):
        """从DataFrame.plot()调用中提取配置"""
        # 设置默认图表类型
        kind = 'bar'  # 默认为条形图
        
        # 检查关键字参数
        for kw in keywords:
            if kw.arg == 'kind':
                if isinstance(kw.value, ast.Constant):
                    kind = kw.value.value
                    print(f"从plot参数提取图表类型: {kind}")
                    if kind in ['bar', 'barh', 'hist']:
                        self.chart_type = 'bar'
                    elif kind == 'box':
                        self.chart_type = 'boxplot'
                        print("检测到DataFrame.plot(kind='box')，设置图表类型为箱线图")
                    else:
                        self.chart_type = kind
            elif kw.arg == 'x':
                if isinstance(kw.value, ast.Constant):
                    self.x_column = kw.value.value
                    if self.x_column not in self.data_columns:
                        self.data_columns.append(self.x_column)
                    print(f"从plot参数提取x轴列: {self.x_column}")
            elif kw.arg == 'y':
                if isinstance(kw.value, ast.Constant):
                    self.y_column = kw.value.value
                    if self.y_column not in self.data_columns:
                        self.data_columns.append(self.y_column)
                    print(f"从plot参数提取y轴列: {self.y_column}")
            elif kw.arg == 'title':
                if isinstance(kw.value, ast.Constant):
                    self.title = kw.value.value
                    print(f"从plot参数提取标题: {self.title}")
            elif kw.arg == 'stacked':
                if isinstance(kw.value, ast.Constant) and kw.value.value == True:
                    self.is_stacked = True
                    print(f"从plot参数提取堆叠设置: {self.is_stacked}")
            elif kw.arg == 'figsize':
                self.figsize = self._get_tuple_value(kw.value)
            elif kw.arg == 'color' or kw.arg == 'colors':
                # 保存颜色信息
                self.colors = self._extract_colors(kw.value)
            elif kw.arg == 'hue':
                # 提取hue分组列
                if isinstance(kw.value, ast.Constant):
                    self.hue_column = kw.value.value
                    print(f"从plot参数提取hue列: {self.hue_column}")
                    if self.hue_column not in self.data_columns:
                        self.data_columns.append(self.hue_column)
        
        # 设置plotting_var
        self.plotting_var = df_name
        
        # 如果使用了堆叠或hue，则认为可能是堆叠图
        if self.is_stacked or self.hue_column:
            print(f"检测到可能的堆叠图表: stacked={self.is_stacked}, hue={self.hue_column}")
    
    def _extract_colors(self, node):
        """从颜色参数提取颜色列表"""
        colors = []
        
        if isinstance(node, ast.List) and hasattr(node, 'elts'):
            # 列表字面量
            for elt in node.elts:
                if isinstance(elt, ast.Constant):
                    colors.append(elt.value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # 单个颜色字符串
            colors.append(node.value)
        
        print(f"提取到颜色: {colors}")
        return colors

    def extract_from_code(self, code: str) -> Dict[str, Any]:
        """
        从代码中提取图表配置
        
        参数:
            code: 可视化代码字符串
            
        返回:
            包含图表配置的字典
        """
        self.reset()
        try:
            # 通过简单的代码分析检测聚合方法
            if '.mean()' in code or '.mean(' in code:
                self.agg_method = 'mean'
                print(f"通过代码字符串检测到聚合方法: mean")
            elif '.sum()' in code or '.sum(' in code:
                self.agg_method = 'sum'
                print(f"通过代码字符串检测到聚合方法: sum")
            elif '.count()' in code or '.count(' in code:
                self.agg_method = 'count'
                print(f"通过代码字符串检测到聚合方法: count")
            elif '.value_counts()' in code or '.value_counts(' in code:
                self.agg_method = 'count'
                print(f"通过代码字符串检测到聚合方法: value_counts (映射为count)")
                
                # 尝试检测value_counts所应用的列
                import re
                # 匹配多种形式的value_counts调用
                patterns = [
                    r"(\w+)\['([^']+)'\]\.value_counts\(\)",  # df['column'].value_counts()
                    r"(\w+)\[\"([^\"]+)\"\]\.value_counts\(\)",  # df["column"].value_counts()
                    r"(\w+)\.(\w+)\.value_counts\(\)"  # df.column.value_counts()
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, code)
                    if match:
                        df_var, col_name = match.groups()
                        if not self.current_dataframe_vars or df_var in self.current_dataframe_vars:
                            print(f"检测到对列'{col_name}'应用value_counts")
                            self.x_column = col_name
                            self.y_column = 'count'
                            if col_name not in self.data_columns:
                                self.data_columns.append(col_name)
                        break
                
                # 检测是否有对新创建列的值统计
                # 例如: data['New_Column'] = ... 然后 new_var = data['New_Column'].value_counts()
                created_columns = re.findall(r"(\w+)\[[\'\"]([^\'\"]+)[\'\"]\]\s*=", code)
                for df_var, col_name in created_columns:
                    if col_name not in self.data_columns:
                        self.data_columns.append(col_name)
                        print(f"检测到创建新列: {df_var}['{col_name}']")
                    
                    # 检查该列是否被用于value_counts
                    if f"{df_var}['{col_name}'].value_counts()" in code or f'{df_var}["{col_name}"].value_counts()' in code:
                        print(f"检测到对新创建列'{col_name}'应用value_counts")
                        self.x_column = col_name
                        self.y_column = 'count'
            elif '.median()' in code or '.median(' in code:
                self.agg_method = 'median'
                print(f"通过代码字符串检测到聚合方法: median")
            elif '.avg()' in code or '.avg(' in code or '.average()' in code or '.average(' in code:
                self.agg_method = 'mean'
                print(f"通过代码字符串检测到聚合方法: average (映射为mean)")
            
            # 检测饼图
            if '.pie(' in code or 'kind="pie"' in code or "kind='pie'" in code or 'plt.pie(' in code:
                self.chart_type = 'pie'
                print("检测到代码中可能包含饼图")
                
                # 检测饼图标签
                pie_labels_match = re.search(r"labels\s*=\s*\[([^\]]+)\]", code)
                if pie_labels_match:
                    try:
                        # 尝试将标签字符串分离并处理
                        labels_str = pie_labels_match.group(1)
                        # 分割并清理标签
                        labels = [label.strip().strip('"\'') for label in labels_str.split(',')]
                        self.pie_labels = labels
                        print(f"检测到饼图标签: {labels}")
                    except Exception as e:
                        print(f"处理饼图标签时出错: {str(e)}")
                
                # 检测饼图数据
                # 检查是否有列表形式的数据
                pie_data_match = re.search(r"pie\s*\(\s*\[([^\]]+)\]", code)
                if pie_data_match:
                    try:
                        data_str = pie_data_match.group(1)
                        # 分割并尝试将字符串转为数值
                        data_values = []
                        for val in data_str.split(','):
                            try:
                                data_values.append(float(val.strip()))
                            except:
                                pass
                        if data_values:
                            self.pie_data = data_values
                            print(f"检测到饼图数据值: {data_values}")
                    except Exception as e:
                        print(f"处理饼图数据时出错: {str(e)}")
                        
                # 根据标题推断是否为性别分布图
                if 'gender' in code.lower() or ('gender' in self.title.lower() if self.title else False):
                    print("检测到可能是性别分布图")
                    # 如果没有检测到标签和数据，使用默认值
                    if not self.pie_labels:
                        self.pie_labels = ["Male", "Female"]
                    if not self.pie_data and "gender" in self.data_columns:
                        # 假设有默认比例
                        self.pie_data = [60, 40]
                    
                    # 确保x_column是gender相关的
                    if not self.x_column or "gender" not in self.x_column.lower():
                        self.x_column = "Gender"
            
            # 检测常见的分布图模式
            distribution_patterns = [
                (r"age_bins", r"age_distribution", "年龄分布图", "Age_Range"),
                (r"price_bins", r"price_distribution", "价格分布图", "Price_Range"),
                (r"income_bins", r"income_distribution", "收入分布图", "Income_Range"),
                (r"duration_bins", r"duration_distribution", "持续时间分布图", "Duration_Range"),
                (r"rating_bins", r"rating_distribution", "评分分布图", "Rating_Range")
            ]
            
            # 首先尝试特定模式
            pattern_found = False
            for pattern, dist_pattern, desc, range_col in distribution_patterns:
                if re.search(pattern, code.lower()):
                    print(f"检测到可能是{desc}")
                    # 尝试找到分布变量
                    if re.search(dist_pattern, code.lower()):
                        print(f"✓ 确认为{desc}")
                        self.chart_type = 'bar'
                        if not self.x_column:
                            self.x_column = range_col
                        if not self.y_column:
                            self.y_column = 'count'
                        if range_col not in self.data_columns:
                            self.data_columns.append(range_col)
                        pattern_found = True
                        break
            
            # 如果没有找到特定模式，尝试通用模式（检测任何*_bins模式）
            if not pattern_found:
                generic_bins_match = re.search(r"(\w+)_bins", code.lower())
                if generic_bins_match:
                    field_base = generic_bins_match.group(1)
                    print(f"检测到通用分布图模式: {field_base}_bins")
                    field_distribution = f"{field_base}_distribution"
                    if field_base + "_distribution" in code.lower():
                        print(f"✓ 确认为{field_base}分布图")
                        range_col = f"{field_base.capitalize()}_Range"
                        if not self.x_column:
                            self.x_column = range_col
                        if not self.y_column:
                            self.y_column = 'count'
                        if range_col not in self.data_columns:
                            self.data_columns.append(range_col)
            
            # 尝试确定是否是堆叠图表的简单检查
            if "stacked=True" in code or ".plot(kind='bar', stacked=True" in code or ".plot(stacked=True" in code:
                self.is_stacked = True
                print("通过代码字符串检测到堆叠图表")
            
            # 检查是否使用KMeans聚类
            if "KMeans" in code or "kmeans" in code:
                print("检测到可能使用了KMeans聚类")
                # 将聚类标记添加到数据列中
                if "Cluster" not in self.data_columns:
                    self.data_columns.append("Cluster")
                    
            tree = ast.parse(code)
            self.visit(tree)
            
            # 构建配置字典
            config = {
                "chart_type": self.chart_type,
                "title": self.title,
                "x_field": self.x_column or self.x_label,
                "y_field": self.y_column or self.y_label,
                "x_label": self.x_label,
                "y_label": self.y_label,
                "data_columns": self.data_columns,
                "hue_column": self.hue_column,
                "is_stacked": self.is_stacked,
                "color": self.color,
                "colors": self.colors,
                "bins": self.bins,
                "show_legend": self.legend,
                "grid": self.grid,
                "uses_seaborn": self.uses_seaborn,
                "uses_plotly": self.uses_plotly,
                "dataframe_vars": list(self.current_dataframe_vars),
                "plotting_var": self.plotting_var,
                "agg_method": self.agg_method  # 添加聚合方法到配置中
            }
            
            # 添加饼图特定配置
            if self.chart_type == 'pie':
                # 添加饼图的类别字段和值字段
                config["pie_category_field"] = self.pie_category_field
                config["pie_value_field"] = self.pie_value_field
                
                # 如果检测到饼图数据和标签，创建标准格式的数据
                if self.pie_labels and self.pie_data and len(self.pie_labels) == len(self.pie_data):
                    pie_formatted_data = []
                    for i, (label, value) in enumerate(zip(self.pie_labels, self.pie_data)):
                        pie_formatted_data.append({
                            self.pie_category_field: label,
                            self.pie_value_field: value
                        })
                    config["pie_formatted_data"] = pie_formatted_data
            
            return config
        except Exception as e:
            print(f"解析错误: {str(e)}")
            return {"error": str(e), "chart_type": "bar", "x_field": "Age_Range", "y_field": "count", "agg_method": "count"}
    
    def _handle_plt_call(self, method_name, args, keywords):
        """处理matplotlib.pyplot调用"""
        # 处理图表类型方法
        if method_name in ['bar', 'barh', 'hist', 'scatter', 'plot', 'line']:
            self.chart_type = 'line' if method_name == 'plot' else method_name
            print(f"检测到matplotlib图表类型: {self.chart_type}")
        elif method_name == 'pie':
            self.chart_type = 'pie'
            print("检测到饼图")
            # 提取饼图的x和y数据，饼图使用不同的逻辑
            if args and len(args) > 0:
                # 饼图一般第一个参数是值数组
                print("检测到饼图数据参数")
                # 查找labels关键字参数
                for kw in keywords:
                    if kw.arg == 'labels':
                        # 这是标签数组
                        if hasattr(kw.value, 'elts'):
                            # 列表字面量
                            labels = [self._get_node_value(elt) for elt in kw.value.elts]
                            self.x_column = "labels"  # 使用特殊标记表示这是标签数组
                            print(f"从饼图提取标签: {labels}")
                            # 将标签添加到数据列
                            for label in labels:
                                if isinstance(label, str) and label not in self.data_columns:
                                    self.data_columns.append(label)
                    elif kw.arg == 'autopct':
                        # 存在autopct参数，表示需要显示百分比
                        print("饼图配置: 显示百分比")
        elif method_name == 'boxplot':
            self.chart_type = 'boxplot'
            print("检测到箱线图")
            
            # 检查数据参数
            if args and len(args) > 0:
                # 箱线图通常第一个参数是数据数组
                print("检测到箱线图数据参数")
            
            # 检查标签和其他配置
            for kw in keywords:
                if kw.arg == 'labels':
                    if hasattr(kw.value, 'elts'):
                        labels = [self._get_node_value(elt) for elt in kw.value.elts]
                        print(f"从箱线图提取标签: {labels}")
                        # 将标签添加到数据列
                        for label in labels:
                            if isinstance(label, str) and label not in self.data_columns:
                                self.data_columns.append(label)
                elif kw.arg == 'vert' and hasattr(kw.value, 'value'):
                    # vert=False表示水平箱线图
                    if not kw.value.value:
                        print("检测到水平箱线图配置")
        # 处理标题
        elif method_name == 'title':
            if args and len(args) > 0:
                self.title = self._get_node_value(args[0])
                print(f"从plt.title提取标题: {self.title}")
        # 处理X轴标签
        elif method_name == 'xlabel':
            if args and len(args) > 0:
                self.x_label = self._get_node_value(args[0])
                print(f"从plt.xlabel提取X轴标签: {self.x_label}")
        # 处理Y轴标签
        elif method_name == 'ylabel':
            if args and len(args) > 0:
                self.y_label = self._get_node_value(args[0])
                print(f"从plt.ylabel提取Y轴标签: {self.y_label}")
        # 处理图例
        elif method_name == 'legend':
            self.legend = True
            # 检查图例位置参数
            for kw in keywords:
                if kw.arg == 'title':
                    print(f"从plt.legend提取图例标题: {self._get_node_value(kw.value)}")
        # 处理网格线
        elif method_name == 'grid':
            if len(args) > 0 and hasattr(args[0], 'value'):
                self.grid = args[0].value
            else:
                self.grid = True
            print(f"设置网格线显示: {self.grid}")

    def _handle_axes_call(self, method_name, args, keywords):
        """处理matplotlib axes对象方法调用"""
        # 处理常见的axes方法
        if method_name == 'set_xlabel':
            if args and len(args) > 0:
                self.x_label = self._get_node_value(args[0])
                print(f"从ax.set_xlabel提取X轴标签: {self.x_label}")
        elif method_name == 'set_ylabel':
            if args and len(args) > 0:
                self.y_label = self._get_node_value(args[0])
                print(f"从ax.set_ylabel提取Y轴标签: {self.y_label}")
        elif method_name == 'set_title':
            if args and len(args) > 0:
                self.title = self._get_node_value(args[0])
                print(f"从ax.set_title提取标题: {self.title}")
        elif method_name == 'bar':
            self.chart_type = 'bar'
            print("从ax.bar设置图表类型: bar")
        elif method_name == 'pie':
            self.chart_type = 'pie'
            print("从ax.pie设置图表类型: pie")
            # 处理饼图特有参数
            for kw in keywords:
                if kw.arg == 'labels':
                    if hasattr(kw.value, 'elts'):
                        labels = [self._get_node_value(elt) for elt in kw.value.elts]
                        print(f"从ax.pie提取标签: {labels}")
                        self.data_columns.extend(labels)
        elif method_name == 'boxplot':
            self.chart_type = 'boxplot'
            print("从ax.boxplot设置图表类型: boxplot")
            # 处理箱线图特有参数
            for kw in keywords:
                if kw.arg == 'labels':
                    if hasattr(kw.value, 'elts'):
                        labels = [self._get_node_value(elt) for elt in kw.value.elts]
                        print(f"从ax.boxplot提取标签: {labels}")
                        self.data_columns.extend(labels)
        elif method_name == 'scatter':
            self.chart_type = 'scatter'
            print("从ax.scatter设置图表类型: scatter")
        elif method_name == 'plot':
            self.chart_type = 'line'
            print("从ax.plot设置图表类型: line")
        elif method_name == 'legend':
            self.legend = True
            print("从ax.legend设置显示图例")
            # 检查图例标题
            for kw in keywords:
                if kw.arg == 'title':
                    print(f"从ax.legend提取图例标题: {self._get_node_value(kw.value)}")
        elif method_name == 'grid':
            self.grid = True
            if args and len(args) > 0 and hasattr(args[0], 'value'):
                self.grid = args[0].value
            print(f"从ax.grid设置网格显示: {self.grid}")

    def _handle_figure_call(self, method_name, args, keywords):
        """处理matplotlib figure对象方法调用"""
        if method_name == 'suptitle':
            if args and len(args) > 0:
                self.title = self._get_node_value(args[0])
                print(f"从fig.suptitle提取标题: {self.title}")
        elif method_name == 'set_size_inches':
            if args and len(args) > 0:
                self.figsize = self._get_tuple_value(args[0])
                print(f"从fig.set_size_inches提取图形大小: {self.figsize}")

    def _handle_sns_call(self, method_name, args, keywords):
        """处理seaborn调用"""
        # 处理seaborn图表类型
        if method_name in ['barplot', 'countplot']:
            self.chart_type = 'bar'
            print(f"检测到seaborn {method_name}，设置图表类型: bar")
        elif method_name in ['lineplot', 'relplot']:
            self.chart_type = 'line'
            print(f"检测到seaborn {method_name}，设置图表类型: line")
        elif method_name == 'scatterplot':
            self.chart_type = 'scatter'
            print(f"检测到seaborn {method_name}，设置图表类型: scatter")
        elif method_name in ['histplot', 'displot']:
            self.chart_type = 'bar'
            print(f"检测到seaborn {method_name}，设置图表类型: bar (histogram)")
            # 检查是否指定了堆叠类型
            for kw in keywords:
                if kw.arg == 'multiple' and self._get_node_value(kw.value) == 'stack':
                    self.is_stacked = True
                    print("检测到seaborn堆叠设置，设置堆叠为: True")
        elif method_name in ['boxplot', 'boxenplot']:
            self.chart_type = 'boxplot'
            print(f"检测到seaborn {method_name}，设置图表类型: boxplot")
        
        # 从关键字参数中提取x, y, hue
        for kw in keywords:
            if kw.arg == 'x':
                self.x_column = self._get_node_value(kw.value)
                print(f"从seaborn参数提取x轴列: {self.x_column}")
                if self.x_column and self.x_column not in self.data_columns:
                    self.data_columns.append(self.x_column)
            elif kw.arg == 'y':
                self.y_column = self._get_node_value(kw.value)
                print(f"从seaborn参数提取y轴列: {self.y_column}")
                if self.y_column and self.y_column not in self.data_columns:
                    self.data_columns.append(self.y_column)
            elif kw.arg == 'hue':
                self.hue_column = self._get_node_value(kw.value)
                print(f"从seaborn参数提取hue列: {self.hue_column}")
                if self.hue_column and self.hue_column not in self.data_columns:
                    self.data_columns.append(self.hue_column)
            elif kw.arg == 'data':
                # 提取数据源变量
                if isinstance(kw.value, ast.Name) and kw.value.id in self.current_dataframe_vars:
                    self.plotting_var = kw.value.id
                    print(f"从seaborn参数提取数据源变量: {self.plotting_var}")

    def _handle_px_call(self, method_name, args, keywords):
        """处理plotly express调用"""
        # 标记使用了plotly
        self.uses_plotly = True
        
        # 处理plotly图表类型
        if method_name in ['bar', 'histogram']:
            self.chart_type = 'bar'
            print(f"检测到plotly {method_name}，设置图表类型: bar")
        elif method_name == 'line':
            self.chart_type = 'line'
            print(f"检测到plotly {method_name}，设置图表类型: line")
        elif method_name == 'scatter':
            self.chart_type = 'scatter'
            print(f"检测到plotly {method_name}，设置图表类型: scatter")
        elif method_name == 'pie':
            self.chart_type = 'pie'
            print(f"检测到plotly {method_name}，设置图表类型: pie")
        
        # 从关键字参数中提取x, y, color
        for kw in keywords:
            if kw.arg == 'x':
                self.x_column = self._get_node_value(kw.value)
                print(f"从plotly参数提取x轴列: {self.x_column}")
                if self.x_column and self.x_column not in self.data_columns:
                    self.data_columns.append(self.x_column)
            elif kw.arg == 'y':
                self.y_column = self._get_node_value(kw.value)
                print(f"从plotly参数提取y轴列: {self.y_column}")
                if self.y_column and self.y_column not in self.data_columns:
                    self.data_columns.append(self.y_column)
            elif kw.arg == 'color':
                self.hue_column = self._get_node_value(kw.value)
                print(f"从plotly参数提取color(hue)列: {self.hue_column}")
                if self.hue_column and self.hue_column not in self.data_columns:
                    self.data_columns.append(self.hue_column)
            elif kw.arg == 'data_frame':
                # 提取数据源变量
                if isinstance(kw.value, ast.Name) and kw.value.id in self.current_dataframe_vars:
                    self.plotting_var = kw.value.id
                    print(f"从plotly参数提取数据源变量: {self.plotting_var}")
            elif kw.arg == 'title':
                self.title = self._get_node_value(kw.value)
                print(f"从plotly参数提取标题: {self.title}")
            elif kw.arg == 'barmode' and self._get_node_value(kw.value) == 'stack':
                self.is_stacked = True
                print("检测到plotly堆叠设置，设置堆叠为: True")

    def _get_tuple_value(self, node):
        """提取元组值"""
        if isinstance(node, ast.Tuple) and hasattr(node, 'elts'):
            return tuple(self._get_node_value(elt) for elt in node.elts)
        elif isinstance(node, ast.List) and hasattr(node, 'elts'):
            return tuple(self._get_node_value(elt) for elt in node.elts)
        return None

    def _get_node_value(self, node):
        """从AST节点中提取值"""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Str):  # Python 3.7及之前
            return node.s
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Tuple) and hasattr(node, 'elts'):
            return tuple(self._get_node_value(elt) for elt in node.elts)
        elif isinstance(node, ast.List) and hasattr(node, 'elts'):
            return tuple(self._get_node_value(elt) for elt in node.elts)
        else:
            # 返回节点源代码的字符串表示
            return self._get_node_source(node)
    
    def _get_node_source(self, node):
        """获取节点的源代码表示"""
        if hasattr(node, 'id'):
            return node.id
        elif hasattr(node, 'value') and isinstance(node.value, ast.Constant):
            return str(node.value.value)
        elif hasattr(node, 'value') and isinstance(node.value, ast.Str):
            return node.value.s
        else:
            return str(node.__class__.__name__)

    def _get_node_name(self, node):
        """从AST节点中提取名称"""
        if hasattr(node, 'id'):
            return node.id
        elif hasattr(node, 'attr'):
            return node.attr
        elif hasattr(node, 'value') and isinstance(node.value, (ast.Str, ast.Constant)):
            return self._get_node_value(node.value)
        return None

    def resolve_chart_data(self, df: pd.DataFrame):
        """
        给定AST提取的图表信息，从真实DataFrame中生成label和value数据。
        自动处理字段缺失、字段不匹配、以及count/mean/sum等聚合操作。
        
        参数:
            df: 包含实际数据的DataFrame
            
        返回:
            tuple: (labels, values) 或 (labels, datasets) 用于图表数据
        """
        from difflib import get_close_matches
        import re

        # 打印图表识别信息和数据信息
        print("\n======== 开始解析图表数据 ========")
        print(f"DataFrame形状: {df.shape}")
        print(f"DataFrame列: {list(df.columns)}")
        print(f"图表类型: {self.chart_type}")
        print(f"X列: {self.x_column}")
        print(f"Y列: {self.y_column}")
        print(f"Hue列: {self.hue_column}")
        print(f"是否为堆叠图: {self.is_stacked}")
        print(f"检测到的聚合方法: {self.agg_method}")
        
        # 初始化字段和聚合方法
        x_field = self.x_column
        y_field = self.y_column
        hue_field = self.hue_column
        
        # 默认聚合方法
        default_agg = "sum"
        
        # 初始化title相关变量
        title = self.title or ""
        title_lower = title.lower() if title else ""
        
        # 优先使用直接从代码中检测到的聚合方法
        if self.agg_method:
            default_agg = self.agg_method
            print(f"使用从代码中检测到的聚合方法: {default_agg}")
        # 仅当未直接识别到聚合方法时，才尝试从标题进行推断
        else:
            # 从标题判断是否应使用均值
            is_average_chart = any(kw in title_lower for kw in ["average", "mean", "avg", "平均"])
            
            if is_average_chart:
                default_agg = "mean"
                print(f"根据标题'{title}'判断: 这是一个平均值图表, 默认使用mean聚合")
        
        # 字段修复和验证
        corrected_fields = self._correct_field_names(df)
        if corrected_fields['x_field'] != x_field:
            print(f"⚠️ 修复X字段: {x_field} → {corrected_fields['x_field']}")
            x_field = corrected_fields['x_field']
        
        if y_field and corrected_fields['y_field'] != y_field:
            print(f"⚠️ 修复Y字段: {y_field} → {corrected_fields['y_field']}")
            y_field = corrected_fields['y_field']
            
        if hue_field and corrected_fields['hue_field'] != hue_field:
            print(f"⚠️ 修复Hue字段: {hue_field} → {corrected_fields['hue_field']}")
            hue_field = corrected_fields['hue_field']
        
        # 检查特殊情况 - 处理Gender与Purchase Amount相关图表
        gender_purchase_data = self._check_gender_purchase(df, x_field, y_field, title_lower)
        if gender_purchase_data:
            print("🔍 检测到Gender与Purchase相关图表, 使用特殊处理")
            return gender_purchase_data
        
        # 根据图表类型和字段情况确定处理方式
        if self.chart_type == "pie":
            return self._prepare_pie_chart_data(df, x_field, y_field, default_agg)
        
        # 如果有hue分组
        if hue_field and hue_field in df.columns:
            return self._prepare_grouped_chart_data(df, x_field, y_field, hue_field, default_agg)
            
        # 堆叠图特殊处理
        if self.is_stacked and (not hue_field) and x_field in df.columns:
            potential_hue = self._find_potential_hue_field(df, x_field, y_field)
            if potential_hue:
                print(f"🔍 发现潜在的Hue字段: {potential_hue}")
                return self._prepare_grouped_chart_data(df, x_field, y_field, potential_hue, default_agg)
        
        # 常规图表数据处理 - 单系列
        return self._prepare_single_series_data(df, x_field, y_field, default_agg)

    def _correct_field_names(self, df):
        """
        尝试修正字段名称，处理不精确匹配或不存在的字段
        """
        from difflib import get_close_matches
        import re
        
        result = {
            'x_field': self.x_column,
            'y_field': self.y_column,
            'hue_field': self.hue_column
        }
        
        columns = list(df.columns)
        
        # 特殊字段映射
        special_mappings = {
            'purchase amount': 'Purchase_Amount__USD_',
            'purchase amount (usd)': 'Purchase_Amount__USD_', 
            'average purchase': 'Purchase_Amount__USD_',
            'amount': 'Purchase_Amount__USD_',
            'consumption': 'Purchase_Amount__USD_',
            'product category': 'Category',
            'age group': 'Age_Group',
            'age range': 'Age_Range',
            'price range': 'Price_Range',
            'income range': 'Income_Range',
            'number of customers': 'count',
            'count': 'count',
            'review rating': 'Review_Rating',
            'subscription status': 'Subscription_Status'
        }
        
        # 处理 X 字段
        if self.x_column and self.x_column not in df.columns:
            # 尝试从特殊映射中查找
            x_lower = self.x_column.lower()
            if x_lower in special_mappings and special_mappings[x_lower] in df.columns:
                result['x_field'] = special_mappings[x_lower]
            else:
                # 检查是否是类似 "X Range" 这样的标签，对应 "X_Range" 这样的列
                # 例如 "Age Range" → "Age_Range"
                range_match = re.match(r"(\w+)\s+Range", self.x_column)
                if range_match:
                    range_col = f"{range_match.group(1)}_Range"
                    if range_col in df.columns:
                        result['x_field'] = range_col
                        print(f"✓ 将X轴标签 '{self.x_column}' 映射到列 '{range_col}'")
                else:
                    # 使用模糊匹配查找最接近的列名
                    matches = get_close_matches(self.x_column, columns, n=1, cutoff=0.6)
                    if matches:
                        result['x_field'] = matches[0]
                    else:
                        # 如果找不到合适匹配，尝试一些常见的分类列
                        for common_pattern in [r'\w+_Range', r'\w+_Group', r'Category', r'Gender', r'Subscription_Status']:
                            for col in columns:
                                if re.match(common_pattern, col):
                                    result['x_field'] = col
                                    print(f"找不到匹配列，使用备选分类列: {col}")
                                    break
                            if result['x_field'] != self.x_column:
                                break
        
        # 处理 Y 字段
        if self.y_column and self.y_column not in df.columns:
            # 检查是否是"Number of X"或"Count of X"格式
            number_of_match = re.match(r"number\s+of\s+(\w+)", self.y_column.lower()) or re.match(r"count\s+of\s+(\w+)", self.y_column.lower())
            
            if (self.y_column.lower() == 'number of customers' or self.y_column.lower() == 'count' or number_of_match) and self.agg_method == 'count':
                # 保持y_field为"count"，表示这是一个计数聚合而不是实际列
                result['y_field'] = 'count'
                print(f"✓ 将Y轴 '{self.y_column}' 标识为计数聚合")
            # 尝试从特殊映射中查找
            elif self.y_column.lower() in special_mappings and special_mappings[self.y_column.lower()] in df.columns:
                result['y_field'] = special_mappings[self.y_column.lower()]
            else:
                # 使用模糊匹配查找最接近的列名
                matches = get_close_matches(self.y_column, columns, n=1, cutoff=0.6)
                if matches:
                    result['y_field'] = matches[0]
                else:
                    # 如果找不到合适匹配，尝试一些常见的数值列
                    for common_col in ['Purchase_Amount__USD_', 'Previous_Purchases', 'Review_Rating']:
                        if common_col in df.columns:
                            result['y_field'] = common_col
                            break
        
        # 处理 Hue 字段
        if self.hue_column and self.hue_column not in df.columns:
            # 尝试从特殊映射中查找
            hue_lower = self.hue_column.lower()
            if hue_lower in special_mappings and special_mappings[hue_lower] in df.columns:
                result['hue_field'] = special_mappings[hue_lower]
            else:
                # 使用模糊匹配
                matches = get_close_matches(self.hue_column, columns, n=1, cutoff=0.6)
                if matches:
                    result['hue_field'] = matches[0]
        
        return result
        
    def _check_gender_purchase(self, df, x_field, y_field, title_lower):
        """
        检查是否为Gender与Purchase Amount相关图表，
        这类图表需要特殊处理以确保数据准确
        """
        # 检查是否包含 Gender 和消费相关词
        is_gender_chart = (x_field == 'Gender' or x_field == 'gender') and x_field in df.columns
        has_purchase_keywords = any(word in title_lower for word in ['purchase', 'consumption', 'spending', 'amount'])
        
        if is_gender_chart and has_purchase_keywords:
            print("✓ 检测到性别消费对比图表")
            
            # 确定消费金额列
            purchase_col = None
            purchase_candidates = ['Purchase_Amount__USD_', 'Purchase Amount', 'Amount']
            
            # 如果y_field已指定且在列中
            if y_field and y_field in df.columns and df[y_field].dtype in ['float64', 'int64']:
                purchase_col = y_field
            # 否则尝试从候选列中找
            else:
                for col in purchase_candidates:
                    if col in df.columns:
                        purchase_col = col
                        break
            
            if purchase_col:
                # 计算各性别的总支出
                gender_totals = df.groupby('Gender')[purchase_col].sum()
                print(f"✓ 性别消费额: {gender_totals}")
                
                labels = gender_totals.index.tolist()
                values = gender_totals.values.tolist()
                
                # 使用适当的颜色
                colors = []
                for gender in labels:
                    if gender.lower() == 'male':
                        colors.append('rgba(54, 162, 235, 0.7)')  # 蓝色
                    elif gender.lower() == 'female':
                        colors.append('rgba(255, 99, 132, 0.7)')  # 粉色
                    else:
                        colors.append('rgba(255, 206, 86, 0.7)')  # 黄色
                
                return {
                    'labels': labels,
                    'datasets': [{
                        'label': purchase_col,
                        'data': values,
                        'backgroundColor': colors,
                        'borderColor': [c.replace('0.7', '1.0') for c in colors],
                        'borderWidth': 1
                    }]
                }
        
        return None
    
    def _prepare_pie_chart_data(self, df, x_field, y_field, agg_method):
        """准备饼图数据"""
        print("✓ 准备饼图数据")
        
        if not x_field or x_field not in df.columns:
            print("⚠️ 饼图缺少有效的分类字段，尝试查找合适的分类列")
            # 尝试查找合适的分类列
            for col in df.columns:
                if df[col].dtype == 'object' and df[col].nunique() <= 10:
                    x_field = col
                    print(f"✓ 找到适合饼图的分类列: {x_field}")
                    break
        
        if not x_field or x_field not in df.columns:
            raise ValueError("找不到适合饼图的分类字段")
            
        # 如果有数值列，按该列汇总
        if y_field and y_field in df.columns and df[y_field].dtype in ['float64', 'int64']:
            if agg_method == 'mean':
                category_values = df.groupby(x_field)[y_field].mean()
                print(f"✓ 使用mean()聚合{y_field}字段")
            else:
                category_values = df.groupby(x_field)[y_field].sum()
                print(f"✓ 使用sum()聚合{y_field}字段")
        else:
            # 否则使用计数
            category_values = df[x_field].value_counts()
            print(f"✓ 使用计数作为饼图数据")
        
        # 准备调色板
        palette = [
            'rgba(255, 99, 132, 0.7)',
            'rgba(54, 162, 235, 0.7)',
            'rgba(255, 206, 86, 0.7)',
            'rgba(75, 192, 192, 0.7)',
            'rgba(153, 102, 255, 0.7)',
            'rgba(255, 159, 64, 0.7)',
            'rgba(199, 199, 199, 0.7)'
        ]
        
        # 确保调色板足够长
        while len(palette) < len(category_values):
            i = len(palette)
            palette.append(f'rgba({(i*37) % 255}, {(i*83) % 255}, {(i*127) % 255}, 0.7)')
        
        return {
            'labels': [str(label) for label in category_values.index.tolist()],
            'datasets': [{
                'data': category_values.values.tolist(),
                'backgroundColor': palette[:len(category_values)],
                'hoverOffset': 4
            }]
        }
    
    def _find_potential_hue_field(self, df, x_field, y_field):
        """查找潜在的分组(hue)字段"""
        
        candidate_columns = []
        
        # 检查所有分类列
        for col in df.columns:
            # 跳过X字段本身
            if col == x_field:
                continue
                
            # 检查是否是分类列
            if df[col].dtype == 'object' or df[col].dtype.name.startswith('category'):
                # 如果唯一值数量合适(2-7)
                n_unique = df[col].nunique()
                if 2 <= n_unique <= 7:
                    candidate_columns.append((col, n_unique))
        
        # 如果有候选列，选择唯一值数量最接近5的
        if candidate_columns:
            candidate_columns.sort(key=lambda x: abs(x[1] - 5))
            return candidate_columns[0][0]
            
        return None
    
    def _prepare_grouped_chart_data(self, df, x_field, y_field, hue_field, agg_method):
        """
        准备分组数据(多系列)
        用于带hue字段的图表或堆叠图
        """
        print(f"✓ 准备分组数据 - X: {x_field}, Y: {y_field}, 分组: {hue_field}")
        
        # 确保所有字段都在DataFrame中
        if x_field not in df.columns:
            raise ValueError(f"X字段 '{x_field}' 在DataFrame中不存在")
        if hue_field not in df.columns:
            raise ValueError(f"分组字段 '{hue_field}' 在DataFrame中不存在")
            
        # 如果是数值性Y字段
        if y_field and y_field in df.columns and df[y_field].dtype in ['float64', 'int64']:
            # 创建透视表
            if agg_method == 'mean':
                pivot_data = pd.pivot_table(
                    df, index=x_field, columns=hue_field, values=y_field, aggfunc='mean'
                ).fillna(0)
            else:
                pivot_data = pd.pivot_table(
                    df, index=x_field, columns=hue_field, values=y_field, aggfunc='sum'
                ).fillna(0)
            
            print(f"✓ 透视表形状: {pivot_data.shape}")
        else:
            # 如果没有Y字段或Y字段不是数值，使用计数
            pivot_data = pd.crosstab(df[x_field], df[hue_field])
            print(f"✓ 交叉表形状: {pivot_data.shape}")
        
        # 准备数据
        labels = [str(x) for x in pivot_data.index.tolist()]
        
        # 准备调色板
        palette = [
            'rgba(255, 99, 132, 0.7)',
            'rgba(54, 162, 235, 0.7)',
            'rgba(255, 206, 86, 0.7)',
            'rgba(75, 192, 192, 0.7)',
            'rgba(153, 102, 255, 0.7)',
            'rgba(255, 159, 64, 0.7)'
        ]
        
        # 创建数据集
        datasets = []
        for i, category in enumerate(pivot_data.columns):
            color = palette[i % len(palette)]
            datasets.append({
                'label': str(category),
                'data': pivot_data[category].tolist(),
                'backgroundColor': color,
                'borderColor': color.replace('0.7', '1.0'),
                'borderWidth': 1
            })
        
        return {
            'labels': labels,
            'datasets': datasets
        }
    
    def _prepare_single_series_data(self, df, x_field, y_field, agg_method):
        """
        准备单系列数据
        适用于没有分组的普通图表
        """
        print(f"✓ 准备单系列数据 - X: {x_field}, Y: {y_field}")
        
        # 确保X字段在DataFrame中
        if x_field not in df.columns:
            raise ValueError(f"X字段 '{x_field}' 在DataFrame中不存在")
        
        # 特殊处理：分布统计图（计数类型的图表）
        if self.agg_method == 'count' and (y_field == 'count' or not y_field):
            # 这里处理任何列的分布计数图，不仅限于Age_Range
            print(f"✓ 为{x_field}列生成分布统计图")
            
            # 对该列进行值计数
            value_counts = df[x_field].value_counts().sort_index()
            labels = [str(x) for x in value_counts.index.tolist()]
            values = value_counts.values.tolist()
            
            print(f"  - 数据标签: {labels}")
            print(f"  - 数据值: {values}")
            
            # 创建单个数据集
            return {
                'labels': labels,
                'datasets': [{
                    'label': self.y_label or 'Number of Items',
                    'data': values,
                    'backgroundColor': 'rgba(54, 162, 235, 0.7)',
                    'borderColor': 'rgba(54, 162, 235, 1.0)',
                    'borderWidth': 1
                }]
            }
        
        # 如果有Y字段且为数值性
        if y_field and y_field in df.columns and df[y_field].dtype in ['float64', 'int64']:
            # 按X分组并聚合Y
            if agg_method == 'mean':
                grouped = df.groupby(x_field)[y_field].mean()
            elif agg_method == 'median':
                grouped = df.groupby(x_field)[y_field].median()
            elif agg_method == 'min':
                grouped = df.groupby(x_field)[y_field].min()
            elif agg_method == 'max':
                grouped = df.groupby(x_field)[y_field].max()
            else:  # 默认使用sum
                grouped = df.groupby(x_field)[y_field].sum()
                
            labels = [str(x) for x in grouped.index.tolist()]
            values = grouped.values.tolist()
            
            # 计算数据分析，用于调整Y轴范围
            data_min = min(values)
            data_max = max(values)
            data_range = data_max - data_min
            
            # 如果数据值稳定在一个较窄的范围内，不从0开始Y轴
            should_begin_at_zero = False
            y_min = None
            
            # 检查是否是平均值或低波动图表
            is_avg_chart = any(kw in y_field.lower() for kw in ["average", "mean", "avg"]) if y_field else False 
            title = self.title or ""
            is_avg_title = any(kw in title.lower() for kw in ["average", "mean", "avg"])
            
            # 系列名包含"平均"或标题包含"平均"，通常是小范围波动的平均值图表
            if is_avg_chart or is_avg_title or agg_method == 'mean':
                should_begin_at_zero = False
                # 设置Y轴最小值为数据最小值的90%
                y_min = data_min * 0.9 if data_min > 0 else data_min * 1.1
                print(f"✓ 检测到平均值图表，Y轴不从0开始，最小值设为: {y_min:.2f}")
            # 如果数据范围小于数据最大值的30%，也考虑不从0开始
            elif data_min > 0 and data_range < data_max * 0.3:
                should_begin_at_zero = False
                # 设置Y轴最小值为数据最小值的90%
                y_min = data_min * 0.9
                print(f"✓ 检测到小范围波动图表，Y轴不从0开始，最小值设为: {y_min:.2f}")
            else:
                should_begin_at_zero = True
                print("✓ 标准图表，Y轴从0开始")
        elif y_field == 'count':
            # 这是一个计数聚合的特殊情况，使用value_counts
            value_counts = df[x_field].value_counts().sort_index()
            labels = [str(x) for x in value_counts.index.tolist()]
            values = value_counts.values.tolist()
            should_begin_at_zero = True
            y_min = 0
            print(f"✓ 为{x_field}列生成计数聚合数据")
        else:
            # 如果没有有效的Y字段，使用X字段的值计数
            value_counts = df[x_field].value_counts().sort_index()
            labels = [str(x) for x in value_counts.index.tolist()]
            values = value_counts.values.tolist()
            should_begin_at_zero = True
            y_min = 0
        
        # 创建单个数据集
        result = {
            'labels': labels,
            'datasets': [{
                'label': y_field or x_field,
                'data': values,
                'backgroundColor': 'rgba(54, 162, 235, 0.7)',
                'borderColor': 'rgba(54, 162, 235, 1.0)',
                'borderWidth': 1
            }]
        }
        
        # 添加Y轴配置
        if not should_begin_at_zero and y_min is not None:
            result['scales'] = {
                'y': {
                    'beginAtZero': False,
                    'min': y_min
                }
            }
        
        return result

    def _get_chart_type(self, method_name):
        """从方法名转换为标准图表类型"""
        chart_type_map = {
            'scatter': 'scatter',
            'bar': 'bar',
            'barh': 'bar',  # 水平条形图
            'pie': 'pie',
            'plot': 'line',
            'hist': 'bar',
            'boxplot': 'boxplot'
        }
        return chart_type_map.get(method_name, 'unknown')
    
    def _get_seaborn_chart_type(self, method_name):
        """从seaborn方法名转换为标准图表类型"""
        chart_type_map = {
            'scatterplot': 'scatter',
            'barplot': 'bar',
            'lineplot': 'line',
            'histplot': 'bar',   # 直方图映射为bar
            'displot': 'bar',    # 分布图映射为bar
            'countplot': 'bar',  # 计数图映射为bar
            'boxplot': 'boxplot',
            'heatmap': 'heatmap'
        }
        return chart_type_map.get(method_name, 'unknown')

def convert_to_chartjs_config(ast_config: Dict[str, Any], df=None) -> Dict[str, Any]:
    """
    将AST提取的配置转换为Chart.js配置
    
    参数:
        ast_config: AST提取的配置字典
        df: 可选的DataFrame对象，用于提取实际数据
        
    返回:
        Chart.js配置字典
    """
    # 检查错误情况，尝试设置默认值
    if "error" in ast_config:
        print(f"配置提取过程中发生错误: {ast_config['error']}")
        print("将使用默认设置...")
        chart_type = ast_config.get("chart_type", "bar")
        x_field = ast_config.get("x_field", "Age_Range")
        y_field = ast_config.get("y_field", "count")
        title = ast_config.get("title", "Chart")
        agg_method = ast_config.get("agg_method", "count")
    else:
        # 确保图表类型与Chart.js兼容
        chart_type = ast_config.get("chart_type", "bar")
        # 将不兼容的类型映射到Chart.js支持的类型
        chart_type_mapping = {
            "histogram": "bar",
            "hist": "bar",
            "barh": "bar",
            "line": "line",
            "scatter": "scatter",
            "pie": "pie",
            "doughnut": "doughnut",
            "boxplot": "bar",  # 特殊处理
            "heatmap": "bar"   # 特殊处理
        }
        
        chart_type = chart_type_mapping.get(chart_type, chart_type)
        
        title = ast_config.get("title", "")
        x_field = ast_config.get("x_field")
        y_field = ast_config.get("y_field")
        agg_method = ast_config.get("agg_method")  # 获取检测到的聚合方法
    
    hue_field = ast_config.get("hue_column")
    is_stacked = ast_config.get("is_stacked", False)
    data_columns = ast_config.get("data_columns", [])
    colors = ast_config.get("colors", [])
    
    print(f"\n========== 开始转换为Chart.js配置 ==========")
    print(f"原始图表类型: {ast_config.get('chart_type', 'bar')}")
    print(f"映射后图表类型: {chart_type}")
    print(f"标题: {title}")
    print(f"X字段: {x_field}")
    print(f"Y字段: {y_field}")
    print(f"Hue字段: {hue_field}")
    print(f"是否为堆叠图: {is_stacked}")
    print(f"聚合方法: {agg_method}")
    
    # 创建临时ChartConfigExtractor实例，用于调用resolve_chart_data
    extractor = ChartConfigExtractor()
    extractor.chart_type = chart_type
    extractor.title = title
    extractor.x_column = x_field
    extractor.y_column = y_field  
    extractor.hue_column = hue_field
    extractor.is_stacked = is_stacked
    extractor.colors = colors
    extractor.agg_method = agg_method  # 设置聚合方法
    
    # 默认配置
    config = {
        "chart_type": chart_type,
        "title": title or "Chart",
        "data": {
            "labels": [],
            "datasets": []
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {
                    "display": True,
                    "text": title or "Chart"
                },
                "legend": {
                    "position": "top",
                    "display": True
                },
                "tooltip": {
                    "enabled": True
                }
            }
        }
    }
    
    # 如果识别到聚合方法，添加到配置中
    if agg_method:
        config["agg_method"] = agg_method
        
        # 为标题添加聚合方法指示，如果标题中尚未包含
        if title and not any(method in title.lower() for method in ['sum', 'mean', 'average', 'count', 'median']):
            agg_display = {
                'mean': 'Average',
                'sum': 'Total',
                'count': 'Count',
                'median': 'Median'
            }.get(agg_method, agg_method.capitalize())
            
            # 更新标题显示聚合方法
            config["title"] = f"{agg_display} {title}"
            config["options"]["plugins"]["title"]["text"] = config["title"]
    
    # 如果不是饼图，添加x和y字段和scales配置
    if chart_type not in ["pie", "doughnut"]:
        config["x_field"] = x_field or "undefined"
        config["y_field"] = y_field or "undefined"
        
        # 为非饼图添加scales配置
        config["options"]["scales"] = {
            "y": {
                "beginAtZero": True,  # 默认值，后续可能会修改
                "title": {
                    "display": True,
                    "text": ast_config.get("y_label") or y_field or "Value"
                }
            },
            "x": {
                "title": {
                    "display": True,
                    "text": ast_config.get("x_label") or x_field or "Category"
                }
            }
        }
        
        # 设置堆叠选项
        if is_stacked and chart_type == "bar":
            config["options"]["scales"]["x"]["stacked"] = True
            config["options"]["scales"]["y"]["stacked"] = True
            config["is_stacked"] = True
            print("配置Bar图表为堆叠模式")
    
    # 特殊处理箱线图
    if chart_type == "boxplot":
        config["chart_type"] = "bar"  # Chart.js没有原生箱线图
        config["is_range_chart"] = True
        print("将箱线图转换为数据范围图表")
        
        # 添加箱线图特有的配置
        # 添加统计图表的特殊tooltip
        config["options"]["plugins"]["tooltip"] = {
            "callbacks": {
                "label": """
                function(context) {
                    var label = context.dataset.label || '';
                    if (label) {
                        label += ': ';
                    }
                    if (context.parsed.y !== null) {
                        var rangeData = context.dataset.rangeData[context.dataIndex];
                        if (rangeData) {
                            return [
                                label + 'Min: ' + rangeData.min.toFixed(2),
                                label + 'Q1: ' + rangeData.q1.toFixed(2),
                                label + 'Median: ' + rangeData.median.toFixed(2),
                                label + 'Mean: ' + rangeData.mean.toFixed(2),
                                label + 'Q3: ' + rangeData.q3.toFixed(2),
                                label + 'Max: ' + rangeData.max.toFixed(2)
                            ];
                        }
                    }
                    return label + context.parsed.y;
                }
                """
            }
        }
        
        # 箱线图需要特殊的渲染插件
        config["options"]["plugins"]["boxplotRender"] = {
            "enabled": True,
            "colorScale": ["rgba(220,220,220,0.5)", "rgba(70,130,180,0.5)"]
        }
        
        # 添加特殊的渲染代码到Chart.js配置中
        config["plugins"] = ["""
            {
                id: 'boxplotRender',
                beforeDraw: function(chart, args, options) {
                    if (!options.enabled) return;
                    
                    const ctx = chart.ctx;
                    const datasets = chart.data.datasets;
                    
                    datasets.forEach(function(dataset, datasetIndex) {
                        if (dataset.rangeData) {
                            const meta = chart.getDatasetMeta(datasetIndex);
                            
                            dataset.rangeData.forEach(function(rangeData, index) {
                                if (!rangeData) return;
                                
                                const bar = meta.data[index];
                                if (!bar) return;
                                
                                const { min, q1, median, q3, max } = rangeData;
                                
                                // 获取坐标
                                const x = bar.x;
                                const width = bar.width;
                                const boxWidth = width * 0.8;
                                
                                // 获取Y轴坐标
                                const yAxis = chart.scales.y;
                                const yMin = yAxis.getPixelForValue(min);
                                const yQ1 = yAxis.getPixelForValue(q1);
                                const yMedian = yAxis.getPixelForValue(median);
                                const yQ3 = yAxis.getPixelForValue(q3);
                                const yMax = yAxis.getPixelForValue(max);
                                
                                // 绘制箱体
                                ctx.save();
                                ctx.fillStyle = dataset.backgroundColor;
                                ctx.strokeStyle = dataset.borderColor;
                                ctx.lineWidth = 1;
                                
                                // 绘制从最小值到最大值的线
                                ctx.beginPath();
                                ctx.moveTo(x, yMin);
                                ctx.lineTo(x, yMax);
                                ctx.stroke();
                                
                                // 绘制箱体 (Q1-Q3)
                                ctx.fillRect(x - boxWidth/2, yQ3, boxWidth, yQ1 - yQ3);
                                ctx.strokeRect(x - boxWidth/2, yQ3, boxWidth, yQ1 - yQ3);
                                
                                // 绘制中位数线
                                ctx.beginPath();
                                ctx.moveTo(x - boxWidth/2, yMedian);
                                ctx.lineTo(x + boxWidth/2, yMedian);
                                ctx.lineWidth = 2;
                                ctx.stroke();
                                
                                // 绘制最大值和最小值的横线
                                ctx.beginPath();
                                ctx.moveTo(x - boxWidth/4, yMin);
                                ctx.lineTo(x + boxWidth/4, yMin);
                                ctx.stroke();
                                
                                ctx.beginPath();
                                ctx.moveTo(x - boxWidth/4, yMax);
                                ctx.lineTo(x + boxWidth/4, yMax);
                                ctx.stroke();
                                
                                ctx.restore();
                            });
                        }
                    });
                }
            }
        """]
        
        # 修改图表配置
        config["options"]["scales"]["y"]["grace"] = "10%"  # 在最小值和最大值上增加空间
    
    # 使用DataFrame数据
    if df is not None:
        try:
            # 尝试使用resolve_chart_data获取数据
            chart_data = extractor.resolve_chart_data(df)
            
            if chart_data:
                print(f"✓ 成功提取图表数据")
                if 'labels' in chart_data:
                    print(f"  - 标签数量: {len(chart_data['labels'])}")
                if 'datasets' in chart_data:
                    print(f"  - 数据集数量: {len(chart_data['datasets'])}")
                
                # 使用生成的图表数据
                config["data"] = chart_data
            else:
                print("⚠️ 无法生成图表数据")
        except Exception as e:
            print(f"⚠️ 提取数据时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 回退: 如果是分布图表，尝试直接创建分布计数数据
            if agg_method == 'count' and x_field in df.columns:
                try:
                    # 直接对该列进行计数
                    value_counts = df[x_field].value_counts().sort_index()
                    labels = [str(x) for x in value_counts.index.tolist()]
                    values = value_counts.values.tolist()
                    
                    config["data"] = {
                        'labels': labels,
                        'datasets': [{
                            'label': y_field or 'Count',
                            'data': values,
                            'backgroundColor': 'rgba(54, 162, 235, 0.7)',
                            'borderColor': 'rgba(54, 162, 235, 1.0)',
                            'borderWidth': 1
                        }]
                    }
                    
                    print(f"✓ 使用备用方法为{x_field}列生成计数数据")
                except Exception as e2:
                    print(f"⚠️ 备用数据生成也失败: {str(e2)}")
    
    return config

def convert_to_antv_config(ast_config: Dict[str, Any], df=None) -> Dict[str, Any]:
    """
    将AST提取的配置转换为AntV G2配置
    
    参数:
        ast_config: AST提取的配置字典
        df: 可选的DataFrame对象，用于提取实际数据
        
    返回:
        AntV G2配置字典
    """
    # 获取基本信息
    chart_type = ast_config.get("chart_type", "bar")
    title = ast_config.get("title", "")
    x_field = ast_config.get("x_field")
    y_field = ast_config.get("y_field")
    hue_field = ast_config.get("hue_column")
    is_stacked = ast_config.get("is_stacked", False)
    data_columns = ast_config.get("data_columns", [])
    colors = ast_config.get("colors", [])
    agg_method = ast_config.get("agg_method")  # 获取检测到的聚合方法
    
    print(f"\n========== 开始转换为AntV G2配置 ==========")
    print(f"原始图表类型: {chart_type}")
    print(f"标题: {title}")
    print(f"X字段: {x_field}")
    print(f"Y字段: {y_field}")
    print(f"Hue字段: {hue_field}")
    print(f"是否为堆叠图: {is_stacked}")
    print(f"聚合方法: {agg_method}")
    
    # 图表类型映射 (Chart.js到AntV G2)
    chart_type_mapping = {
        "bar": "interval",      # 柱状图
        "line": "line",         # 折线图
        "scatter": "point",     # 散点图
        "pie": "pie",           # 饼图
        "doughnut": "pie",      # 环图
        "boxplot": "box",       # 箱线图
        "heatmap": "heatmap",   # 热力图
        "histogram": "histogram" # 直方图
    }
    
    antv_type = chart_type_mapping.get(chart_type, "interval")
    
    # 创建临时ChartConfigExtractor实例，用于调用resolve_chart_data
    extractor = ChartConfigExtractor()
    extractor.chart_type = chart_type
    extractor.title = title
    extractor.x_column = x_field
    extractor.y_column = y_field  
    extractor.hue_column = hue_field
    extractor.is_stacked = is_stacked
    extractor.colors = colors
    extractor.agg_method = agg_method  # 设置聚合方法
    
    # 如果识别到聚合方法，且标题中未包含该聚合方法的指示，更新标题
    display_title = title
    if agg_method and title and not any(method in title.lower() for method in ['sum', 'mean', 'average', 'count', 'median']):
        agg_display = {
            'mean': 'Average',
            'sum': 'Total',
            'count': 'Count',
            'median': 'Median'
        }.get(agg_method, agg_method.capitalize())
        
        # 更新显示标题
        display_title = f"{agg_display} {title}"
    
    # 默认配置
    config = {
        "type": antv_type,               # 图表类型
        "title": display_title or "Chart",
        "data": [],                      # 数据项将稍后填充
        "xField": x_field or "",         # x轴字段
        "yField": y_field or "",         # y轴字段
        "autoFit": True,                 # 自动适应容器大小
        "animation": True,
        "legend": {
            "position": "top-right"
        }
    }
    
    # 添加Chart.js风格的默认半透明颜色
    chartjs_colors = [
        'rgba(255, 99, 132, 0.7)',   # 红色
        'rgba(54, 162, 235, 0.7)',   # 蓝色
        'rgba(255, 206, 86, 0.7)',   # 黄色
        'rgba(75, 192, 192, 0.7)',   # 绿色/青色
        'rgba(153, 102, 255, 0.7)',  # 紫色
        'rgba(255, 159, 64, 0.7)',   # 橙色
        'rgba(199, 199, 199, 0.7)'   # 灰色
    ]
    
    # 根据图表类型设置颜色
    if antv_type == "interval" or antv_type == "line" or antv_type == "point":
        if hue_field:
            # 多系列图表的颜色配置
            config["color"] = chartjs_colors
            config["colorField"] = "series"  # 确保多系列图表能应用颜色
        else:
            # 单系列颜色
            config["color"] = chartjs_colors[0]
    elif antv_type == "pie":
        # 饼图使用全部颜色
        config["color"] = chartjs_colors
    
    # 添加聚合方法到配置
    if agg_method:
        config["agg_method"] = agg_method
    
    # 特殊图表类型配置
    if antv_type == "pie":
        # 获取饼图特定字段
        pie_category_field = ast_config.get("pie_category_field", "category")
        pie_value_field = ast_config.get("pie_value_field", "value")
        
        # 设置饼图配置
        config["angleField"] = pie_value_field
        config["colorField"] = pie_category_field
        
        # 添加标签配置
        config["label"] = {
            "type": "outer",
            "content": "value"
        }
        
        # 设置交互配置
        config["interactions"] = [
            { "type": "element-active" }
        ]
        
        # 检查是否有预先格式化的饼图数据
        if "pie_formatted_data" in ast_config and ast_config["pie_formatted_data"]:
            config["data"] = ast_config["pie_formatted_data"]
            print(f"使用AST中提取的饼图格式化数据: {len(config['data'])}项")
    elif antv_type == "interval" and is_stacked:
        # 堆叠柱状图配置
        config["isStack"] = True
        config["seriesField"] = hue_field or "series"
        config["colorField"] = hue_field or "series"
        
        # 添加标签
        config["label"] = {
            "position": "middle"
        }
    elif hue_field:
        # 分组图表
        config["seriesField"] = hue_field
        config["colorField"] = hue_field
    elif antv_type == "line":
        # 折线图特殊配置
        config["point"] = {
            "size": 4,
            "shape": "circle"
        }
        config["connectNulls"] = True  # 连接空值点
    elif antv_type == "point":
        # 散点图特殊配置
        config["size"] = 4
        config["shape"] = "circle"
    
    # 使用DataFrame数据
    if df is not None:
        try:
            # 尝试使用ChartJS数据结构并转换
            chart_data = extractor.resolve_chart_data(df)
            
            if chart_data:
                print(f"✓ 成功提取图表数据")
                print(f"  - 标签数量: {len(chart_data['labels'])}")
                print(f"  - 数据集数量: {len(chart_data['datasets'])}")
                
                # 将Chart.js格式的数据转换为AntV格式
                data = []
                
                # 获取标签和数据集
                labels = chart_data.get('labels', [])
                datasets = chart_data.get('datasets', [])
                
                if len(datasets) == 1:
                    # 单系列数据
                    dataset = datasets[0]
                    values = dataset.get('data', [])
                    
                    # 检查是否有自定义背景色
                    if 'backgroundColor' in dataset:
                        bg_color = dataset.get('backgroundColor')
                        if isinstance(bg_color, str):
                            config["color"] = bg_color
                    
                    for i, label in enumerate(labels):
                        if i < len(values):
                            data_item = {
                                x_field: label,
                                y_field: values[i]
                            }
                            data.append(data_item)
                else:
                    # 多系列数据 (用于分组或堆叠图表)
                    # 提取自定义颜色
                    custom_colors = []
                    for dataset in datasets:
                        bg_color = dataset.get('backgroundColor', '')
                        if isinstance(bg_color, str):
                            custom_colors.append(bg_color)
                    
                    # 如果所有数据集都有自定义颜色，使用这些颜色
                    if custom_colors and len(custom_colors) == len(datasets):
                        config["color"] = custom_colors
                        
                        # 确保有正确的颜色字段设置
                        if not config.get("colorField") and config.get("seriesField"):
                            config["colorField"] = config["seriesField"]
                        elif not config.get("colorField"):
                            config["colorField"] = "series"
                    
                    for dataset in datasets:
                        series_name = dataset.get('label', '')
                        values = dataset.get('data', [])
                        
                        for i, label in enumerate(labels):
                            if i < len(values):
                                data_item = {
                                    x_field: label,
                                    y_field: values[i],
                                    'series': series_name  # 添加系列字段
                                }
                                data.append(data_item)
                    
                    # 设置系列字段
                    if not config.get("seriesField") and len(datasets) > 1:
                        config["seriesField"] = "series"
                
                # 更新配置中的数据
                config["data"] = data
                
                # 如果chart_data中包含scales配置，处理Y轴配置
                if 'scales' in chart_data and 'y' in chart_data['scales']:
                    y_scales = chart_data['scales']['y']
                    
                    # 处理Y轴起始于0的设置
                    if 'beginAtZero' in y_scales and not y_scales['beginAtZero']:
                        # AntV G2中设置不从0开始
                        config['yAxis'] = {
                            'nice': True,
                            'minLimit': y_scales.get('min', None)
                        }
                        print(f"✓ 设置Y轴不从0开始，最小值: {y_scales.get('min')}")
        except Exception as e:
            print(f"⚠️ 转换数据时出错: {e}")
            import traceback
            traceback.print_exc()
    
    return config