"""基准评测框架

提供自动化基准评测能力，对标 SWE-bench / HumanEval / MBPP 等主流评测基准，
量化 Turing 与顶级 AI coding 工具的差距并跟踪演化进度。

模块组成:
- BenchmarkRunner — 评测调度器，管理任务队列和并发执行
- CodeEvaluator — 代码评估器，支持执行测试、静态分析、功能验证
- BenchmarkDataset — 评测数据集抽象，支持 HumanEval / 自定义格式

Usage::

    from turing.benchmark import BenchmarkRunner

    runner = BenchmarkRunner(agent)
    results = runner.run_suite("humaneval")
    print(results["pass_rate"])
"""

from turing.benchmark.runner import BenchmarkRunner
from turing.benchmark.evaluator import CodeEvaluator
from turing.benchmark.datasets import BenchmarkDataset, HumanEvalTask

__all__ = [
    "BenchmarkRunner",
    "CodeEvaluator",
    "BenchmarkDataset",
    "HumanEvalTask",
]
