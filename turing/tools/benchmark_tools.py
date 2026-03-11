"""基准评测工具

提供评测相关的 Agent 工具：
- run_benchmark — 运行 HumanEval 评测套件
- eval_code — 对代码片段执行多维度评估
- benchmark_trend — 查看评测分数演化趋势

全局 BenchmarkRunner 在 Agent 启动时通过 ``set_benchmark_runner()`` 注入。
"""

from __future__ import annotations

from turing.tools.registry import tool

_benchmark_runner = None


def set_benchmark_runner(runner):
    """注入全局 BenchmarkRunner 实例（Agent 启动时调用）。"""
    global _benchmark_runner
    _benchmark_runner = runner


@tool(
    name="run_benchmark",
    description="运行 HumanEval 风格的代码生成评测。评估 Turing 在函数级代码生成的准确率，并与 Claude Opus / GPT-4o / DeepSeek 等对比。",
    parameters={
        "type": "object",
        "properties": {
            "max_tasks": {
                "type": "integer",
                "description": "最大评测任务数（默认全部）",
            },
            "retry": {
                "type": "integer",
                "description": "每个任务最大尝试次数（含自修复），默认 2",
            },
        },
        "required": [],
    },
)
def run_benchmark(max_tasks: int = None, retry: int = 2) -> dict:
    """运行 HumanEval 评测套件并返回对比报告。"""
    if _benchmark_runner is None:
        return {"error": "评测系统未初始化"}
    return _benchmark_runner.run_humaneval(max_tasks=max_tasks, retry=retry)


@tool(
    name="eval_code",
    description="对代码片段执行多维度评估：语法检查、功能测试、代码质量（lint + 复杂度 + 安全）。",
    parameters={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "待评估的代码",
            },
            "tests": {
                "type": "string",
                "description": "测试用例代码（可选）",
            },
            "language": {
                "type": "string",
                "description": "编程语言，默认 python",
            },
        },
        "required": ["code"],
    },
)
def eval_code(code: str, tests: str = "", language: str = "python") -> dict:
    """对代码执行多维度质量评估。"""
    if _benchmark_runner is None:
        from turing.benchmark.evaluator import CodeEvaluator
        evaluator = CodeEvaluator()
    else:
        evaluator = _benchmark_runner.evaluator

    result = {}
    # 质量评估
    result["quality"] = evaluator.check_quality(code)

    # 如果有测试代码，运行测试
    if tests:
        result["test_result"] = evaluator.run_tests(code, tests, language)

    return result


@tool(
    name="benchmark_trend",
    description="查看评测分数的历史演化趋势，量化进步幅度。",
    parameters={
        "type": "object",
        "properties": {
            "suite_name": {
                "type": "string",
                "description": "评测套件名，默认 humaneval",
            },
        },
        "required": [],
    },
)
def benchmark_trend(suite_name: str = "humaneval") -> dict:
    """获取评测分数演化趋势。"""
    if _benchmark_runner is None:
        return {"error": "评测系统未初始化"}
    return _benchmark_runner.get_evolution_trend(suite_name)
