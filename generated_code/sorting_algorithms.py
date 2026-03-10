def bubble_sort(arr):
    """
    冒泡排序算法实现
    时间复杂度: O(n^2)
    空间复杂度: O(1)
    """
    n = len(arr)
    for i in range(n):
        # 优化：如果某一轮没有交换，说明已经有序
        swapped = False
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        if not swapped:
            break
    return arr


def quick_sort(arr):
    """
    快速排序算法实现
    时间复杂度: 平均 O(n log n), 最坏 O(n^2)
    空间复杂度: O(log n)
    """
    if len(arr) <= 1:
        return arr
    
    def partition(low, high):
        # 选择最后一个元素作为基准
        pivot = arr[high]
        i = low - 1
        
        for j in range(low, high):
            if arr[j] <= pivot:
                i += 1
                arr[i], arr[j] = arr[j], arr[i]
        
        arr[i + 1], arr[high] = arr[high], arr[i + 1]
        return i + 1
    
    def quick_sort_helper(low, high):
        if low < high:
            pi = partition(low, high)
            quick_sort_helper(low, pi - 1)
            quick_sort_helper(pi + 1, high)
    
    quick_sort_helper(0, len(arr) - 1)
    return arr


def merge_sort(arr):
    """
    归并排序算法实现
    时间复杂度: O(n log n)
    空间复杂度: O(n)
    """
    if len(arr) <= 1:
        return arr
    
    def merge(left, right):
        result = []
        i = j = 0
        
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
    
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    
    return merge(left, right)


def heap_sort(arr):
    """
    堆排序算法实现
    时间复杂度: O(n log n)
    空间复杂度: O(1)
    """
    def heapify(n, i):
        largest = i
        left = 2 * i + 1
        right = 2 * i + 2
        
        if left < n and arr[left] > arr[largest]:
            largest = left
            
        if right < n and arr[right] > arr[largest]:
            largest = right
            
        if largest != i:
            arr[i], arr[largest] = arr[largest], arr[i]
            heapify(n, largest)
    
    n = len(arr)
    
    # 构建最大堆
    for i in range(n // 2 - 1, -1, -1):
        heapify(n, i)
    
    # 逐个提取元素
    for i in range(n - 1, 0, -1):
        arr[0], arr[i] = arr[i], arr[0]
        heapify(i, 0)
    
    return arr


def insertion_sort(arr):
    """
    插入排序算法实现
    时间复杂度: O(n^2)
    空间复杂度: O(1)
    """
    for i in range(1, len(arr)):
        key = arr[i]
        j = i - 1
        
        # 将大于key的元素向后移动
        while j >= 0 and arr[j] > key:
            arr[j + 1] = arr[j]
            j -= 1
            
        arr[j + 1] = key
    
    return arr


def selection_sort(arr):
    """
    选择排序算法实现
    时间复杂度: O(n^2)
    空间复杂度: O(1)
    """
    n = len(arr)
    
    for i in range(n):
        min_idx = i
        for j in range(i + 1, n):
            if arr[j] < arr[min_idx]:
                min_idx = j
        arr[i], arr[min_idx] = arr[min_idx], arr[i]
    
    return arr


# 测试函数
def test_sorting_algorithms():
    """测试所有排序算法"""
    import random
    
    # 生成测试数据
    test_data = [random.randint(1, 100) for _ in range(20)]
    print("原始数据:", test_data)
    
    # 测试各种排序算法
    algorithms = [
        ("冒泡排序", bubble_sort),
        ("快速排序", quick_sort),
        ("归并排序", merge_sort),
        ("堆排序", heap_sort),
        ("插入排序", insertion_sort),
        ("选择排序", selection_sort)
    ]
    
    for name, func in algorithms:
        data_copy = test_data.copy()
        sorted_data = func(data_copy)
        print(f"{name}: {sorted_data}")


if __name__ == "__main__":
    test_sorting_algorithms()