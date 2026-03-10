def bubble_sort(arr):
    """
    冒泡排序算法实现
    时间复杂度: O(n^2)
    空间复杂度: O(1)
    """
    n = len(arr)
    # 外层循环控制排序轮数
    for i in range(n):
        # 内层循环进行相邻元素比较
        for j in range(0, n - i - 1):
            # 如果前一个元素大于后一个元素，则交换它们
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr

def selection_sort(arr):
    """
    选择排序算法实现
    时间复杂度: O(n^2)
    空间复杂度: O(1)
    """
    n = len(arr)
    # 遍历数组的每个位置
    for i in range(n):
        # 假设当前位置i的元素是最小的
        min_idx = i
        # 在剩余未排序的部分中寻找最小元素
        for j in range(i + 1, n):
            if arr[j] < arr[min_idx]:
                min_idx = j
        # 将找到的最小元素与当前位置的元素交换
        arr[i], arr[min_idx] = arr[min_idx], arr[i]
    return arr

def insertion_sort(arr):
    """
    插入排序算法实现
    时间复杂度: O(n^2)
    空间复杂度: O(1)
    """
    # 从第二个元素开始遍历（第一个元素可以看作已排序）
    for i in range(1, len(arr)):
        key = arr[i]  # 当前要插入的元素
        j = i - 1     # 已排序部分的最后一个元素索引
        
        # 将大于key的元素向后移动
        while j >= 0 and arr[j] > key:
            arr[j + 1] = arr[j]
            j -= 1
            
        # 插入key到正确位置
        arr[j + 1] = key
    return arr

def merge_sort(arr):
    """
    归并排序算法实现（递归版本）
    时间复杂度: O(n log n)
    空间复杂度: O(n)
    """
    if len(arr) <= 1:
        return arr
    
    # 分割数组
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    
    # 合并已排序的子数组
    return merge(left, right)

def merge(left, right):
    """合并两个已排序的数组"""
    result = []
    i = j = 0
    
    # 比较两个数组的元素，将较小的元素添加到结果中
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    
    # 添加剩余元素
    result.extend(left[i:])
    result.extend(right[j:])
    
    return result

def quick_sort(arr):
    """
    快速排序算法实现（递归版本）
    时间复杂度: 平均 O(n log n), 最坏 O(n^2)
    空间复杂度: O(log n)
    """
    if len(arr) <= 1:
        return arr
    
    pivot = arr[len(arr) // 2]  # 选择中间元素作为基准
    left = [x for x in arr if x < pivot]      # 小于基准的元素
    middle = [x for x in arr if x == pivot]   # 等于基准的元素
    right = [x for x in arr if x > pivot]     # 大于基准的元素
    
    return quick_sort(left) + middle + quick_sort(right)

def heap_sort(arr):
    """
    堆排序算法实现
    时间复杂度: O(n log n)
    空间复杂度: O(1)
    """
    def heapify(arr, n, i):
        """维护堆的性质"""
        largest = i  # 初始化最大值为根节点
        left = 2 * i + 1     # 左子节点
        right = 2 * i + 2    # 右子节点
        
        # 如果左子节点存在且大于根节点
        if left < n and arr[left] > arr[largest]:
            largest = left
            
        # 如果右子节点存在且大于当前最大值
        if right < n and arr[right] > arr[largest]:
            largest = right
            
        # 如果最大值不是根节点，则交换并继续堆化
        if largest != i:
            arr[i], arr[largest] = arr[largest], arr[i]
            heapify(arr, n, largest)
    
    n = len(arr)
    
    # 构建最大堆
    for i in range(n // 2 - 1, -1, -1):
        heapify(arr, n, i)
    
    # 逐个提取元素
    for i in range(n - 1, 0, -1):
        arr[0], arr[i] = arr[i], arr[0]  # 将当前最大值移到末尾
        heapify(arr, i, 0)  # 重新堆化剩余元素
    
    return arr

def python_sort(arr):
    """
    使用Python内置的sorted函数进行排序
    时间复杂度: O(n log n)
    空间复杂度: O(n)
    """
    return sorted(arr)

# 测试函数
def test_sorting_algorithms():
    """测试所有排序算法"""
    # 测试数据
    test_cases = [
        [64, 34, 25, 12, 22, 11, 90],
        [5, 2, 8, 1, 9],
        [1],
        [],
        [3, 3, 3, 3],
        [5, 4, 3, 2, 1]
    ]
    
    algorithms = [
        ("冒泡排序", bubble_sort),
        ("选择排序", selection_sort),
        ("插入排序", insertion_sort),
        ("归并排序", merge_sort),
        ("快速排序", quick_sort),
        ("堆排序", heap_sort),
        ("Python内置排序", python_sort)
    ]
    
    for i, test_case in enumerate(test_cases):
        print(f"\n测试用例 {i+1}: {test_case}")
        original = test_case.copy()
        
        for name, algorithm in algorithms:
            # 创建副本以避免修改原数组
            arr_copy = original.copy()
            result = algorithm(arr_copy)
            print(f"{name}: {result}")

if __name__ == "__main__":
    # 运行测试
    test_sorting_algorithms()
    
    # 示例：对一个数组进行排序
    example_array = [64, 34, 25, 12, 22, 11, 90]
    print(f"\n原始数组: {example_array}")
    print(f"排序后: {quick_sort(example_array.copy())}")