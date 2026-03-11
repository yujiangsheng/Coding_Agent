"""基准评测数据集

定义评测任务格式和内置数据集。支持 HumanEval 风格和 SWE-bench 风格。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class HumanEvalTask:
    """HumanEval 风格的代码生成任务"""
    task_id: str
    prompt: str               # 函数签名 + docstring
    entry_point: str           # 要实现的函数名
    canonical_solution: str    # 标准答案（用于参考，不参与评测）
    test: str                  # 测试用例代码
    difficulty: str = "medium" # easy / medium / hard


@dataclass
class SWEBenchTask:
    """SWE-bench 风格的代码修改任务"""
    task_id: str
    description: str           # 问题描述（Issue 内容）
    repo_path: str             # 仓库路径
    base_commit: str           # 基准 commit
    test_cmd: str              # 测试命令
    test_patch: str            # 测试补丁
    expected_patch: str = ""   # 期望补丁（参考）
    difficulty: str = "medium"


class BenchmarkDataset:
    """评测数据集管理器"""

    def __init__(self, data_dir: str = "turing_data/benchmark"):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def load_humaneval(self, path: str | None = None) -> list[HumanEvalTask]:
        """加载 HumanEval 格式数据集。

        支持 JSONL 格式，每行一个任务：
        {"task_id": "HumanEval/0", "prompt": "...", "entry_point": "...",
         "canonical_solution": "...", "test": "..."}
        """
        filepath = Path(path) if path else self._data_dir / "humaneval.jsonl"
        if not filepath.exists():
            return self._get_builtin_tasks()

        tasks = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                tasks.append(HumanEvalTask(
                    task_id=data["task_id"],
                    prompt=data["prompt"],
                    entry_point=data["entry_point"],
                    canonical_solution=data.get("canonical_solution", ""),
                    test=data.get("test", ""),
                    difficulty=data.get("difficulty", "medium"),
                ))
        return tasks

    def save_results(self, suite_name: str, results: list[dict]) -> str:
        """保存评测结果"""
        import time
        results_dir = self._data_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        timestamp = int(time.time())
        filepath = results_dir / f"{suite_name}_{timestamp}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({
                "suite": suite_name,
                "timestamp": timestamp,
                "total": len(results),
                "results": results,
            }, f, ensure_ascii=False, indent=2)
        return str(filepath)

    def load_results_history(self, suite_name: str) -> list[dict]:
        """加载历史评测结果，用于跟踪演化趋势"""
        results_dir = self._data_dir / "results"
        if not results_dir.exists():
            return []
        history = []
        for f in sorted(results_dir.glob(f"{suite_name}_*.json")):
            with open(f, "r", encoding="utf-8") as fp:
                history.append(json.load(fp))
        return history

    def _get_builtin_tasks(self) -> list[HumanEvalTask]:
        """内置的精选评测任务集，涵盖多种编程能力维度"""
        return [
            # ── 基础算法 ──
            HumanEvalTask(
                task_id="turing_eval/0",
                prompt='def two_sum(nums: list[int], target: int) -> list[int]:\n    """给定整数数组和目标值，返回两个数的索引使其和等于目标值。\n    假设恰好有一个解，同一元素不能使用两次。\n    >>> two_sum([2, 7, 11, 15], 9)\n    [0, 1]\n    """\n',
                entry_point="two_sum",
                canonical_solution="    lookup = {}\n    for i, n in enumerate(nums):\n        if target - n in lookup:\n            return [lookup[target - n], i]\n        lookup[n] = i\n",
                test="def test_two_sum():\n    assert two_sum([2, 7, 11, 15], 9) == [0, 1]\n    assert two_sum([3, 2, 4], 6) == [1, 2]\n    assert two_sum([3, 3], 6) == [0, 1]\n",
                difficulty="easy",
            ),
            HumanEvalTask(
                task_id="turing_eval/1",
                prompt='def longest_common_prefix(strs: list[str]) -> str:\n    """找到字符串数组的最长公共前缀。如果没有，返回空字符串。\n    >>> longest_common_prefix(["flower", "flow", "flight"])\n    \'fl\'\n    >>> longest_common_prefix(["dog", "racecar", "car"])\n    \'\'\n    """\n',
                entry_point="longest_common_prefix",
                canonical_solution='    if not strs:\n        return ""\n    prefix = strs[0]\n    for s in strs[1:]:\n        while not s.startswith(prefix):\n            prefix = prefix[:-1]\n            if not prefix:\n                return ""\n    return prefix\n',
                test='def test_lcp():\n    assert longest_common_prefix(["flower", "flow", "flight"]) == "fl"\n    assert longest_common_prefix(["dog", "racecar", "car"]) == ""\n    assert longest_common_prefix(["a"]) == "a"\n    assert longest_common_prefix([]) == ""\n    assert longest_common_prefix(["", "b"]) == ""\n',
                difficulty="easy",
            ),
            HumanEvalTask(
                task_id="turing_eval/2",
                prompt='def is_valid_parentheses(s: str) -> bool:\n    """判断字符串包含的括号 \'()\', \'{}\', \'[]\' 是否有效（正确闭合和嵌套）。\n    >>> is_valid_parentheses("([]){}")\n    True\n    >>> is_valid_parentheses("([)]")\n    False\n    """\n',
                entry_point="is_valid_parentheses",
                canonical_solution='    stack = []\n    mapping = {")": "(", "}": "{", "]": "["}\n    for c in s:\n        if c in mapping:\n            if not stack or stack[-1] != mapping[c]:\n                return False\n            stack.pop()\n        elif c in "({[":\n            stack.append(c)\n    return len(stack) == 0\n',
                test='def test_valid():\n    assert is_valid_parentheses("()") == True\n    assert is_valid_parentheses("()[]{}") == True\n    assert is_valid_parentheses("(]") == False\n    assert is_valid_parentheses("([)]") == False\n    assert is_valid_parentheses("{[]}") == True\n    assert is_valid_parentheses("") == True\n',
                difficulty="easy",
            ),
            # ── 数据结构 ──
            HumanEvalTask(
                task_id="turing_eval/3",
                prompt='class LRUCache:\n    """设计一个最近最少使用（LRU）缓存，支持 get 和 put 操作，均为 O(1) 时间复杂度。\n\n    capacity: 缓存容量\n    get(key): 获取值，不存在返回 -1\n    put(key, value): 插入或更新，超容量时淘汰最久未使用的\n\n    >>> cache = LRUCache(2)\n    >>> cache.put(1, 1)\n    >>> cache.put(2, 2)\n    >>> cache.get(1)\n    1\n    >>> cache.put(3, 3)  # 淘汰 key=2\n    >>> cache.get(2)\n    -1\n    """\n',
                entry_point="LRUCache",
                canonical_solution='    def __init__(self, capacity: int):\n        from collections import OrderedDict\n        self.cache = OrderedDict()\n        self.capacity = capacity\n\n    def get(self, key: int) -> int:\n        if key not in self.cache:\n            return -1\n        self.cache.move_to_end(key)\n        return self.cache[key]\n\n    def put(self, key: int, value: int) -> None:\n        if key in self.cache:\n            self.cache.move_to_end(key)\n        self.cache[key] = value\n        if len(self.cache) > self.capacity:\n            self.cache.popitem(last=False)\n',
                test='def test_lru():\n    cache = LRUCache(2)\n    cache.put(1, 1)\n    cache.put(2, 2)\n    assert cache.get(1) == 1\n    cache.put(3, 3)\n    assert cache.get(2) == -1\n    cache.put(4, 4)\n    assert cache.get(1) == -1\n    assert cache.get(3) == 3\n    assert cache.get(4) == 4\n',
                difficulty="medium",
            ),
            # ── 字符串处理 ──
            HumanEvalTask(
                task_id="turing_eval/4",
                prompt='def group_anagrams(strs: list[str]) -> list[list[str]]:\n    """将字母异位词分组。\n    字母异位词是由重新排列源单词的所有字母得到的新单词。\n    返回的分组内部按字母序排序，分组之间按首个单词的字母序排序。\n    >>> sorted([sorted(g) for g in group_anagrams(["eat","tea","tan","ate","nat","bat"])])\n    [[\'ate\', \'eat\', \'tea\'], [\'bat\'], [\'nat\', \'tan\']]\n    """\n',
                entry_point="group_anagrams",
                canonical_solution='    from collections import defaultdict\n    groups = defaultdict(list)\n    for s in strs:\n        key = "".join(sorted(s))\n        groups[key].append(s)\n    return [sorted(g) for g in sorted(groups.values(), key=lambda g: sorted(g)[0])]\n',
                test='def test_group():\n    result = group_anagrams(["eat","tea","tan","ate","nat","bat"])\n    normalized = sorted([sorted(g) for g in result])\n    assert normalized == [["ate","eat","tea"],["bat"],["nat","tan"]]\n    assert group_anagrams([""]) == [[""]]\n    assert group_anagrams(["a"]) == [["a"]]\n',
                difficulty="medium",
            ),
            # ── 动态规划 ──
            HumanEvalTask(
                task_id="turing_eval/5",
                prompt='def longest_increasing_subsequence(nums: list[int]) -> int:\n    """返回最长严格递增子序列的长度。\n    >>> longest_increasing_subsequence([10,9,2,5,3,7,101,18])\n    4\n    >>> longest_increasing_subsequence([0,1,0,3,2,3])\n    4\n    """\n',
                entry_point="longest_increasing_subsequence",
                canonical_solution='    import bisect\n    if not nums:\n        return 0\n    tails = []\n    for n in nums:\n        pos = bisect.bisect_left(tails, n)\n        if pos == len(tails):\n            tails.append(n)\n        else:\n            tails[pos] = n\n    return len(tails)\n',
                test='def test_lis():\n    assert longest_increasing_subsequence([10,9,2,5,3,7,101,18]) == 4\n    assert longest_increasing_subsequence([0,1,0,3,2,3]) == 4\n    assert longest_increasing_subsequence([7,7,7,7]) == 1\n    assert longest_increasing_subsequence([]) == 0\n    assert longest_increasing_subsequence([1]) == 1\n    assert longest_increasing_subsequence([1,2,3,4,5]) == 5\n',
                difficulty="medium",
            ),
            # ── 图算法 ──
            HumanEvalTask(
                task_id="turing_eval/6",
                prompt='def course_schedule(num_courses: int, prerequisites: list[list[int]]) -> bool:\n    """判断是否可能完成所有课程（拓扑排序检测有向图是否有环）。\n    prerequisites[i] = [a, b] 表示学 a 之前必须先学 b。\n    >>> course_schedule(2, [[1,0]])\n    True\n    >>> course_schedule(2, [[1,0],[0,1]])\n    False\n    """\n',
                entry_point="course_schedule",
                canonical_solution='    from collections import defaultdict, deque\n    graph = defaultdict(list)\n    in_degree = [0] * num_courses\n    for a, b in prerequisites:\n        graph[b].append(a)\n        in_degree[a] += 1\n    queue = deque(i for i in range(num_courses) if in_degree[i] == 0)\n    visited = 0\n    while queue:\n        node = queue.popleft()\n        visited += 1\n        for nei in graph[node]:\n            in_degree[nei] -= 1\n            if in_degree[nei] == 0:\n                queue.append(nei)\n    return visited == num_courses\n',
                test='def test_schedule():\n    assert course_schedule(2, [[1,0]]) == True\n    assert course_schedule(2, [[1,0],[0,1]]) == False\n    assert course_schedule(4, [[1,0],[2,1],[3,2]]) == True\n    assert course_schedule(1, []) == True\n    assert course_schedule(3, [[0,1],[1,2],[2,0]]) == False\n',
                difficulty="medium",
            ),
            # ── 高级算法 ──
            HumanEvalTask(
                task_id="turing_eval/7",
                prompt='def median_of_two_sorted(nums1: list[int], nums2: list[int]) -> float:\n    """找两个有序数组的中位数，要求时间复杂度 O(log(m+n))。\n    >>> median_of_two_sorted([1, 3], [2])\n    2.0\n    >>> median_of_two_sorted([1, 2], [3, 4])\n    2.5\n    """\n',
                entry_point="median_of_two_sorted",
                canonical_solution='    if len(nums1) > len(nums2):\n        nums1, nums2 = nums2, nums1\n    m, n = len(nums1), len(nums2)\n    lo, hi = 0, m\n    while lo <= hi:\n        i = (lo + hi) // 2\n        j = (m + n + 1) // 2 - i\n        left1 = nums1[i - 1] if i > 0 else float("-inf")\n        right1 = nums1[i] if i < m else float("inf")\n        left2 = nums2[j - 1] if j > 0 else float("-inf")\n        right2 = nums2[j] if j < n else float("inf")\n        if left1 <= right2 and left2 <= right1:\n            if (m + n) % 2 == 0:\n                return (max(left1, left2) + min(right1, right2)) / 2\n            return float(max(left1, left2))\n        elif left1 > right2:\n            hi = i - 1\n        else:\n            lo = i + 1\n    return 0.0\n',
                test='def test_median():\n    assert median_of_two_sorted([1, 3], [2]) == 2.0\n    assert median_of_two_sorted([1, 2], [3, 4]) == 2.5\n    assert median_of_two_sorted([], [1]) == 1.0\n    assert median_of_two_sorted([2], []) == 2.0\n    assert median_of_two_sorted([1,2,3,4,5], [6,7,8,9,10]) == 5.5\n',
                difficulty="hard",
            ),
            # ── 系统设计 / 实用工具 ──
            HumanEvalTask(
                task_id="turing_eval/8",
                prompt='def serialize_deserialize_tree(root_values: list) -> list:\n    """序列化和反序列化二叉树。\n\n    输入一个层序遍历的列表（None 表示空节点），\n    构建二叉树后序列化再反序列化，返回层序遍历结果。\n    返回的列表应与输入等价（去除尾部的 None）。\n\n    >>> serialize_deserialize_tree([1, 2, 3, None, None, 4, 5])\n    [1, 2, 3, None, None, 4, 5]\n    """\n',
                entry_point="serialize_deserialize_tree",
                canonical_solution='    from collections import deque\n    class TreeNode:\n        def __init__(self, val=0, left=None, right=None):\n            self.val = val; self.left = left; self.right = right\n\n    def build(vals):\n        if not vals or vals[0] is None: return None\n        root = TreeNode(vals[0])\n        q = deque([root]); i = 1\n        while q and i < len(vals):\n            node = q.popleft()\n            if i < len(vals) and vals[i] is not None:\n                node.left = TreeNode(vals[i]); q.append(node.left)\n            i += 1\n            if i < len(vals) and vals[i] is not None:\n                node.right = TreeNode(vals[i]); q.append(node.right)\n            i += 1\n        return root\n\n    def serialize(root):\n        if not root: return []\n        result, q = [], deque([root])\n        while q:\n            node = q.popleft()\n            if node: result.append(node.val); q.append(node.left); q.append(node.right)\n            else: result.append(None)\n        while result and result[-1] is None: result.pop()\n        return result\n\n    return serialize(build(root_values))\n',
                test='def test_tree():\n    assert serialize_deserialize_tree([1, 2, 3, None, None, 4, 5]) == [1, 2, 3, None, None, 4, 5]\n    assert serialize_deserialize_tree([]) == []\n    assert serialize_deserialize_tree([1]) == [1]\n    assert serialize_deserialize_tree([1, 2]) == [1, 2]\n',
                difficulty="hard",
            ),
            # ── 函数式编程 ──
            HumanEvalTask(
                task_id="turing_eval/9",
                prompt='def flatten_nested(data: list) -> list:\n    """将任意深度嵌套的列表展平为一维列表。\n    >>> flatten_nested([1, [2, [3, 4], 5], [6, 7]])\n    [1, 2, 3, 4, 5, 6, 7]\n    >>> flatten_nested([[[[1]]]])\n    [1]\n    """\n',
                entry_point="flatten_nested",
                canonical_solution='    result = []\n    for item in data:\n        if isinstance(item, list):\n            result.extend(flatten_nested(item))\n        else:\n            result.append(item)\n    return result\n',
                test='def test_flatten():\n    assert flatten_nested([1, [2, [3, 4], 5], [6, 7]]) == [1, 2, 3, 4, 5, 6, 7]\n    assert flatten_nested([[[[1]]]]) == [1]\n    assert flatten_nested([]) == []\n    assert flatten_nested([1, 2, 3]) == [1, 2, 3]\n    assert flatten_nested([[1], [2], [3]]) == [1, 2, 3]\n',
                difficulty="easy",
            ),
            # ── 文本处理 ──
            HumanEvalTask(
                task_id="turing_eval/10",
                prompt='def calculate(expression: str) -> int:\n    """实现一个基本计算器，支持 +, -, *, / 和括号。\n    整数除法截断到零。\n    >>> calculate("3+2*2")\n    7\n    >>> calculate("(1+(4+5+2)-3)+(6+8)")\n    23\n    >>> calculate("14-3/2")\n    13\n    """\n',
                entry_point="calculate",
                canonical_solution='    def helper(s, idx):\n        stack, num, sign = [], 0, "+"\n        while idx < len(s):\n            c = s[idx]\n            if c.isdigit():\n                num = num * 10 + int(c)\n            if c == "(":\n                num, idx = helper(s, idx + 1)\n            if c in "+-*/" or idx == len(s) - 1 or c == ")":\n                if sign == "+": stack.append(num)\n                elif sign == "-": stack.append(-num)\n                elif sign == "*": stack.append(stack.pop() * num)\n                elif sign == "/": stack.append(int(stack.pop() / num))\n                num, sign = 0, c\n            if c == ")":\n                return sum(stack), idx\n            idx += 1\n        return sum(stack), idx\n    return helper(expression.replace(" ", ""), 0)[0]\n',
                test='def test_calc():\n    assert calculate("3+2*2") == 7\n    assert calculate("(1+(4+5+2)-3)+(6+8)") == 23\n    assert calculate("14-3/2") == 13\n    assert calculate("1+1") == 2\n    assert calculate(" 2-1 + 2 ") == 3\n',
                difficulty="hard",
            ),
            # ── 并发/异步 ──
            HumanEvalTask(
                task_id="turing_eval/11",
                prompt='def merge_k_sorted(lists: list[list[int]]) -> list[int]:\n    """合并 k 个有序列表为一个有序列表。\n    >>> merge_k_sorted([[1,4,5],[1,3,4],[2,6]])\n    [1, 1, 2, 3, 4, 4, 5, 6]\n    """\n',
                entry_point="merge_k_sorted",
                canonical_solution='    import heapq\n    result = []\n    heap = []\n    for i, lst in enumerate(lists):\n        if lst:\n            heapq.heappush(heap, (lst[0], i, 0))\n    while heap:\n        val, li, idx = heapq.heappop(heap)\n        result.append(val)\n        if idx + 1 < len(lists[li]):\n            heapq.heappush(heap, (lists[li][idx + 1], li, idx + 1))\n    return result\n',
                test='def test_merge_k():\n    assert merge_k_sorted([[1,4,5],[1,3,4],[2,6]]) == [1,1,2,3,4,4,5,6]\n    assert merge_k_sorted([]) == []\n    assert merge_k_sorted([[]]) == []\n    assert merge_k_sorted([[1]]) == [1]\n',
                difficulty="medium",
            ),
        ]
