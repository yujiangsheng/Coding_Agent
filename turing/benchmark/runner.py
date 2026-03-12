"""基准评测运行器

自动化执行评测任务，调度 Agent 生成代码并使用 CodeEvaluator 验证。
支持多种评测模式：
- HumanEval 模式：独立函数生成 + 测试验证
- SWE-bench 模式：仓库级代码修改 + 回归测试
- 自定义模式：用户自定义任务 + 评判规则

可追踪历史分数，量化演化进度。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from turing.benchmark.datasets import BenchmarkDataset, HumanEvalTask, SWEBenchTask
from turing.benchmark.evaluator import BenchmarkScorer, CodeEvaluator

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """基准评测调度器"""

    def __init__(self, agent=None, data_dir: str = "turing_data/benchmark"):
        self.agent = agent
        self.dataset = BenchmarkDataset(data_dir)
        self.evaluator = CodeEvaluator(timeout=30)
        self.scorer = BenchmarkScorer()
        self._data_dir = Path(data_dir)

    def run_humaneval(
        self,
        tasks: list[HumanEvalTask] | None = None,
        max_tasks: int | None = None,
        retry: int = 1,
    ) -> dict:
        """运行 HumanEval 风格评测。

        Args:
            tasks: 评测任务列表（None 则使用内置任务集）
            max_tasks: 限制评测任务数
            retry: 每个任务最多尝试次数

        Returns:
            {"pass_rate": float, "pass_at_1": float, "results": [...],
             "duration": float, "comparison": {...}}
        """
        if tasks is None:
            tasks = self.dataset.load_humaneval()
        if max_tasks:
            tasks = tasks[:max_tasks]

        results = []
        start_time = time.time()

        for task in tasks:
            task_result = self._run_single_humaneval(task, retry=retry)
            results.append(task_result)
            logger.info(
                f"[{task.task_id}] {'✓' if task_result['passed'] else '✗'} "
                f"({task_result.get('duration', 0):.1f}s)"
            )

        duration = time.time() - start_time
        scores = self.scorer.score_suite(results)

        # 对比业界基准
        comparison = self._compare_with_benchmarks(scores["pass_rate"])

        report = {
            **scores,
            "duration": round(duration, 1),
            "results": results,
            "comparison": comparison,
        }

        # 保存结果
        self.dataset.save_results("humaneval", results)

        return report

    def _run_single_humaneval(self, task: HumanEvalTask, retry: int = 1) -> dict:
        """执行单个 HumanEval 任务"""
        task_start = time.time()
        best_result = {"task_id": task.task_id, "passed": False, "attempts": 0}

        for attempt in range(retry):
            best_result["attempts"] = attempt + 1

            # 使用 Agent 生成代码
            code = self._generate_code(task)
            if not code:
                continue

            best_result["generated_code"] = code

            # 评估功能正确性
            eval_result = self.evaluator.run_tests(code, task.test)
            best_result["test_result"] = eval_result

            if eval_result.get("passed"):
                best_result["passed"] = True
                # 代码质量评估
                quality = self.evaluator.check_quality(code)
                best_result["quality_score"] = quality.get("quality_score", 0.0)
                break
            else:
                # 自修复：将失败信息反馈给 Agent 再试
                if attempt < retry - 1 and self.agent:
                    code = self._self_repair(task, code, eval_result)
                    if code:
                        repair_eval = self.evaluator.run_tests(code, task.test)
                        if repair_eval.get("passed"):
                            best_result["passed"] = True
                            best_result["generated_code"] = code
                            best_result["self_repaired"] = True
                            quality = self.evaluator.check_quality(code)
                            best_result["quality_score"] = quality.get("quality_score", 0.0)
                            break

        best_result["duration"] = round(time.time() - task_start, 2)
        return best_result

    def _generate_code(self, task: HumanEvalTask) -> str | None:
        """调用 Agent 或 LLM provider 生成代码"""
        if self.agent is None:
            return None

        prompt = (
            f"请实现以下 Python 函数。只输出完整的函数实现代码，不要解释。\n\n"
            f"{task.prompt}"
        )

        try:
            # 如果 agent 有 llm_router，直接用 LLM 生成（更快）
            if hasattr(self.agent, "llm_router"):
                resp = self.agent.llm_router.chat(
                    messages=[
                        {"role": "system", "content": "你是一个专业的 Python 程序员。只输出代码，不要 markdown 格式。"},
                        {"role": "user", "content": prompt},
                    ],
                    task_complexity=0.5,
                )
                code = resp.get("content", "")
            elif hasattr(self.agent, "model"):
                import ollama
                resp = ollama.chat(
                    model=self.agent.model,
                    messages=[
                        {"role": "system", "content": "你是一个专业的 Python 程序员。只输出代码，不要 markdown 格式。"},
                        {"role": "user", "content": prompt},
                    ],
                    options={"temperature": 0.2},
                )
                code = resp.get("message", {}).get("content", "")
            else:
                return None

            return self._extract_code(code, task.entry_point)
        except Exception as e:
            logger.warning(f"代码生成失败 [{task.task_id}]: {e}")
            return None

    def _self_repair(self, task: HumanEvalTask, code: str, eval_result: dict) -> str | None:
        """自修复：将测试失败信息反馈给 LLM 重新生成"""
        if self.agent is None:
            return None

        errors = eval_result.get("errors", [])
        error_msg = "\n".join(errors[:5])

        repair_prompt = (
            f"以下代码未能通过测试，请修复:\n\n"
            f"```python\n{code}\n```\n\n"
            f"测试失败信息:\n{error_msg}\n\n"
            f"请输出修复后的完整代码，不要解释。"
        )

        try:
            if hasattr(self.agent, "llm_router"):
                resp = self.agent.llm_router.chat(
                    messages=[
                        {"role": "system", "content": "你是一个专业的 Python 程序员。只输出代码。"},
                        {"role": "user", "content": repair_prompt},
                    ],
                    task_complexity=0.6,
                )
                code = resp.get("content", "")
            elif hasattr(self.agent, "model"):
                import ollama
                resp = ollama.chat(
                    model=self.agent.model,
                    messages=[
                        {"role": "system", "content": "你是一个专业的 Python 程序员。只输出代码。"},
                        {"role": "user", "content": repair_prompt},
                    ],
                    options={"temperature": 0.3},
                )
                code = resp.get("message", {}).get("content", "")
            else:
                return None

            return self._extract_code(code, task.entry_point)
        except Exception:
            return None

    def _extract_code(self, raw: str, entry_point: str) -> str:
        """从 LLM 输出中提取纯净代码"""
        code = raw.strip()

        # 移除 markdown 代码块
        if "```" in code:
            parts = code.split("```")
            for part in parts:
                if part.strip().startswith("python"):
                    code = part.strip()[len("python"):].strip()
                    break
                elif f"def {entry_point}" in part or f"class {entry_point}" in part:
                    code = part.strip()
                    break

        # 移除 think 标签
        if "<think>" in code:
            import re
            code = re.sub(r"<think>.*?</think>", "", code, flags=re.DOTALL).strip()

        # 确保包含入口函数/类
        if f"def {entry_point}" not in code and f"class {entry_point}" not in code:
            # 可能只返回了函数体，尝试包装
            return code

        return code

    def _compare_with_benchmarks(self, pass_rate: float) -> dict:
        """与业界已知基准分数对比

        数据来源于公开的 HumanEval 评测结果（截至 2025 年）。
        """
        benchmarks = {
            "Claude Opus 4": 0.925,
            "GPT-4o": 0.905,
            "Claude Sonnet 4": 0.895,
            "DeepSeek-V3": 0.880,
            "GPT-4.5": 0.870,
            "Gemini 2.5 Pro": 0.860,
            "Qwen3-Coder-30B": 0.720,
            "CodeLlama-34B": 0.620,
        }
        comparison = {}
        for name, score in benchmarks.items():
            gap = pass_rate - score
            comparison[name] = {
                "benchmark_score": score,
                "gap": round(gap, 4),
                "status": "超越" if gap > 0 else ("持平" if abs(gap) < 0.01 else "落后"),
            }
        return comparison

    def get_evolution_trend(self, suite_name: str = "humaneval") -> dict:
        """获取评测分数的演化趋势"""
        history = self.dataset.load_results_history(suite_name)
        if not history:
            return {"trend": [], "improvement": 0.0}

        trend = []
        for record in history:
            results = record.get("results", [])
            passed = sum(1 for r in results if r.get("passed"))
            total = len(results)
            trend.append({
                "timestamp": record.get("timestamp"),
                "pass_rate": round(passed / max(total, 1), 4),
                "total": total,
            })

        if len(trend) >= 2:
            improvement = trend[-1]["pass_rate"] - trend[0]["pass_rate"]
        else:
            improvement = 0.0

        return {
            "trend": trend,
            "improvement": round(improvement, 4),
            "latest": trend[-1] if trend else None,
        }

    def generate_report(self, results: dict) -> str:
        """生成可读的评测报告"""
        lines = ["# Turing 基准评测报告\n"]

        lines.append(f"## 总览")
        lines.append(f"- 总任务数: {results.get('total', 0)}")
        lines.append(f"- 通过数: {results.get('passed', 0)}")
        lines.append(f"- **通过率: {results.get('pass_rate', 0):.1%}**")
        lines.append(f"- **pass@1: {results.get('pass_at_1', 0):.1%}**")
        lines.append(f"- 平均质量: {results.get('avg_quality', 0):.2f}")
        lines.append(f"- 总耗时: {results.get('duration', 0):.1f}s\n")

        # 与业界对比
        comparison = results.get("comparison", {})
        if comparison:
            lines.append("## 与顶级 AI 工具对比\n")
            lines.append("| 工具 | 基准分 | 差距 | 状态 |")
            lines.append("|------|--------|------|------|")
            for name, data in comparison.items():
                status_icon = "✅" if data["status"] == "超越" else ("⬜" if data["status"] == "持平" else "❌")
                lines.append(
                    f"| {name} | {data['benchmark_score']:.1%} | "
                    f"{data['gap']:+.1%} | {status_icon} {data['status']} |"
                )

        # 任务详情
        task_results = results.get("results", [])
        if task_results:
            lines.append("\n## 任务详情\n")
            lines.append("| 任务 | 结果 | 耗时 | 自修复 |")
            lines.append("|------|------|------|--------|")
            for r in task_results:
                icon = "✅" if r.get("passed") else "❌"
                repair = "✓" if r.get("self_repaired") else ""
                lines.append(
                    f"| {r.get('task_id', '?')} | {icon} | "
                    f"{r.get('duration', 0):.1f}s | {repair} |"
                )

        return "\n".join(lines)

    # ===== SWE-bench 评测 =====

    def run_swebench(
        self,
        tasks: list[SWEBenchTask] | None = None,
        max_tasks: int | None = None,
    ) -> dict:
        """运行 SWE-bench 风格评测（仓库级代码修改 + 回归测试）。

        Args:
            tasks: SWE-bench 任务列表（None 则使用内置示例）
            max_tasks: 限制评测任务数

        Returns:
            {"resolve_rate": float, "results": [...], "duration": float}
        """
        if tasks is None:
            tasks = self._get_builtin_swebench_tasks()
        if max_tasks:
            tasks = tasks[:max_tasks]

        results = []
        start_time = time.time()

        for task in tasks:
            task_result = self._run_single_swebench(task)
            results.append(task_result)
            logger.info(
                f"[{task.task_id}] {'✓' if task_result['resolved'] else '✗'} "
                f"({task_result.get('duration', 0):.1f}s)"
            )

        duration = time.time() - start_time
        resolved = sum(1 for r in results if r.get("resolved"))

        report = {
            "total": len(results),
            "resolved": resolved,
            "resolve_rate": round(resolved / max(len(results), 1), 4),
            "duration": round(duration, 1),
            "results": results,
        }

        self.dataset.save_results("swebench", results)
        return report

    def _run_single_swebench(self, task: SWEBenchTask) -> dict:
        """执行单个 SWE-bench 任务（v4.0 — 隔离执行）"""
        import shlex
        import subprocess
        import tempfile

        task_start = time.time()
        result = {
            "task_id": task.task_id,
            "resolved": False,
            "description": task.description[:200],
        }

        repo_path = Path(task.repo_path)
        if not repo_path.is_dir():
            result["error"] = f"仓库路径不存在: {task.repo_path}"
            result["duration"] = round(time.time() - task_start, 2)
            return result

        # ── 隔离：使用 git worktree 创建独立工作目录 ──
        work_dir = None
        worktree_name = f"turing-bench-{task.task_id[:12]}"
        try:
            work_dir = tempfile.mkdtemp(prefix="turing_swe_")
            wt_result = subprocess.run(
                ["git", "worktree", "add", work_dir, task.base_commit],
                cwd=str(repo_path), capture_output=True, text=True, timeout=30,
            )
            if wt_result.returncode != 0:
                # Fallback: 克隆到临时目录
                import shutil
                shutil.rmtree(work_dir, ignore_errors=True)
                work_dir = tempfile.mkdtemp(prefix="turing_swe_")
                subprocess.run(
                    ["git", "clone", "--quiet", str(repo_path), work_dir],
                    capture_output=True, timeout=120,
                )
                subprocess.run(
                    ["git", "checkout", task.base_commit],
                    cwd=work_dir, capture_output=True, timeout=30,
                )
            # 后续操作使用隔离目录
            isolated_path = Path(work_dir)
        except Exception as e:
            result["error"] = f"创建隔离环境失败: {e}"
            result["duration"] = round(time.time() - task_start, 2)
            if work_dir:
                import shutil
                shutil.rmtree(work_dir, ignore_errors=True)
            return result

        # 以下操作均在 isolated_path（隔离目录）中执行
        try:
            # 2. 应用测试补丁
            if task.test_patch:
                try:
                    proc = subprocess.run(
                        ["git", "apply", "--check", "-"],
                        input=task.test_patch.encode(),
                        cwd=str(isolated_path), capture_output=True, timeout=15,
                    )
                    if proc.returncode == 0:
                        subprocess.run(
                            ["git", "apply", "-"],
                            input=task.test_patch.encode(),
                            cwd=str(isolated_path), capture_output=True, timeout=15,
                        )
                except Exception:
                    pass

            # 3. 使用 Agent 生成修复
            if self.agent is None:
                result["error"] = "Agent 未配置"
                result["duration"] = round(time.time() - task_start, 2)
                return result

            try:
                prompt = (
                    f"请修复以下问题。仓库路径: {isolated_path}\n\n"
                    f"问题描述:\n{task.description}\n\n"
                    f"请直接修改相关文件来修复问题。"
                )
                for event in self.agent.chat(prompt):
                    pass
            except Exception as e:
                result["error"] = f"Agent 执行失败: {e}"
                result["duration"] = round(time.time() - task_start, 2)
                return result

            # 4. 运行测试验证（使用 shlex.split 安全解析命令）
            try:
                test_args = shlex.split(task.test_cmd)
                proc = subprocess.run(
                    test_args,
                    cwd=str(isolated_path),
                    capture_output=True, timeout=120,
                    text=True,
                )
                result["test_output"] = proc.stdout[-2000:] if proc.stdout else ""
                result["test_returncode"] = proc.returncode
                result["resolved"] = proc.returncode == 0
            except subprocess.TimeoutExpired:
                result["error"] = "测试超时"
            except Exception as e:
                result["error"] = f"测试执行失败: {e}"

            result["duration"] = round(time.time() - task_start, 2)
            return result

        finally:
            # 清理隔离环境
            if work_dir:
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", work_dir],
                        cwd=str(repo_path), capture_output=True, timeout=15,
                    )
                except Exception:
                    import shutil
                    shutil.rmtree(work_dir, ignore_errors=True)

    def _get_builtin_swebench_tasks(self) -> list[SWEBenchTask]:
        """内置的 SWE-bench 示例任务（需要本地仓库）"""
        return []  # 需要用户提供具体仓库路径和任务定义
