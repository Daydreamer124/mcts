class Report:
    def __init__(self):
        self._current_iteration = 1  # 使用下划线前缀表示私有属性
        # ... 其他初始化代码 ...
    
    @property
    def current_iteration(self):
        return self._current_iteration
    
    @current_iteration.setter
    def current_iteration(self, value):
        if value is None or value < 1:
            print(f"警告: 尝试设置无效的迭代号: {value}")
            value = 1
        self._current_iteration = value
        
    def __deepcopy__(self, memo):
        """确保深拷贝时正确复制 current_iteration"""
        new_report = Report()
        memo[id(self)] = new_report
        new_report._current_iteration = self._current_iteration
        # 复制其他属性...
        return new_report 