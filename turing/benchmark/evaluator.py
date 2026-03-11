"""代码评估器

对生成的代码执行多维度质量评估：
- 功能正确性：执行测试用例
- 代码质量：lint + type check
- 安全性：基础安全模式检测
- 复杂度：圈复杂度定量分析
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any


class CodeEvaluator:
    """多维度代码质量评估器"""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    # ────────────── 功能正确性 ──────────────

    def run_tests(self, code: str, tests: str, language: str = "python") -> dict:
        """在沙盒中执行代码 + 测试用例，返回通过率和详情。

        Args:
            code: 待测试的代码
            tests: 测试用例代码
            language: 编程语言（目前支持 python）

        Returns:
            {"passed": bool, "total": N, "pass_count": N, "fail_count": N,
             "errors": [...], "output": "..."}
        """
        if language != "python":
            return {"passed": False, "error": f"暂不支持 {language} 评测"}

        with tempfile.TemporaryDirectory(prefix="turing_eval_") as tmpdir:
            code_path = Path(tmpdir) / "solution.py"
            test_path = Path(tmpdir) / "test_solution.py"

            code_path.write_text(code, encoding="utf-8")

            # 测试文件需要导入 solution
            test_code = f"import sys; sys.path.insert(0, '{tmpdir}')\n"
            test_code += "from solution import *\n\n"
            test_code += tests
            test_path.write_text(test_code, encoding="utf-8")

            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", str(test_path), "-v", "--tb=short", "--no-header"],
                    capture_output=True, text=True, timeout=self.timeout,
                    cwd=tmpdir,
                )
                output = result.stdout + result.stderr
                passed = result.returncode == 0

                # 解析 pytest 输出
                pass_count = output.count(" PASSED")
                fail_count = output.count(" FAILED")
                error_count = output.count(" ERROR")
                total = pass_count + fail_count + error_count

                # 提取失败详情
                errors = []
                if not passed:
                    for line in output.split("\n"):
                        if "FAILED" in line or "AssertionError" in line or "Error" in line:
                            errors.append(line.strip())

                return {
                    "passed": passed,
                    "total": max(total, 1),
                    "pass_count": pass_count,
                    "fail_count": fail_count,
                    "error_count": error_count,
                    "errors": errors[:10],
                    "output": output[-2000:] if len(output) > 2000 else output,
                }
            except subprocess.TimeoutExpired:
                return {"passed": False, "error": f"执行超时（{self.timeout}s）", "total": 0, "pass_count": 0}
            except Exception as e:
                return {"passed": False, "error": str(e), "total": 0, "pass_count": 0}

    def check_execution(self, code: str, entry_point: str = "", test_cases: list[dict] | None = None) -> dict:
        """执行代码并检查基本功能正确性（HumanEval 风格）。

        Args:
            code: 完整的 Python 代码
            entry_point: 入口函数名
            test_cases: [{"input": ..., "expected": ...}] 格式的测试用例

        Returns:
            {"passed": bool, "results": [...]}
        """
        if not test_cases:
            # 仅检查代码是否可执行
            return self._check_syntax_and_run(code)

        with tempfile.TemporaryDirectory(prefix="turing_eval_") as tmpdir:
            code_path = Path(tmpdir) / "solution.py"
            code_path.write_text(code, encoding="utf-8")

            results = []
            all_passed = True

            for i, tc in enumerate(test_cases):
                test_input = tc.get("input", "")
                expected = tc.get("expected")
                check_code = tc.get("check", "")

                if check_code:
                    # 自定义检查代码
                    runner = f"import sys; sys.path.insert(0, '{tmpdir}')\n"
                    runner += "from solution import *\n"
                    runner += check_code
                else:
                    # 自动生成函数调用测试
                    runner = f"import sys; sys.path.insert(0, '{tmpdir}')\n"
                    runner += "from solution import *\n"
                    runner += f"result = {entry_point}({test_input})\n"
                    runner += f"assert result == {repr(expected)}, f'Expected {repr(expected)}, got {{result}}'\n"
                    runner += "print('PASS')\n"

                runner_path = Path(tmpdir) / f"test_{i}.py"
                runner_path.write_text(runner, encoding="utf-8")

                try:
                    r = subprocess.run(
                        [sys.executable, str(runner_path)],
                        capture_output=True, text=True, timeout=self.timeout,
                        cwd=tmpdir,
                    )
                    passed = r.returncode == 0
                    if not passed:
                        all_passed = False
                    results.append({
                        "test_index": i,
                        "passed": passed,
                        "output": (r.stdout + r.stderr)[-500:],
                    })
                except subprocess.TimeoutExpired:
                    all_passed = False
                    results.append({"test_index": i, "passed": False, "error": "timeout"})
                except Exception as e:
                    all_passed = False
                    results.append({"test_index": i, "passed": False, "error": str(e)})

            return {
                "passed": all_passed,
                "total": len(test_cases),
                "pass_count": sum(1 for r in results if r["passed"]),
                "results": results,
            }

    def _check_syntax_and_run(self, code: str) -> dict:
        """检查语法和基本可执行性"""
        # 1. 语法检查
        try:
            ast.parse(code)
        except SyntaxError as e:
            return {"passed": False, "error": f"语法错误: {e}", "phase": "syntax"}

        # 2. 执行检查
        with tempfile.TemporaryDirectory(prefix="turing_eval_") as tmpdir:
            code_path = Path(tmpdir) / "solution.py"
            code_path.write_text(code, encoding="utf-8")
            try:
                r = subprocess.run(
                    [sys.executable, str(code_path)],
                    capture_output=True, text=True, timeout=self.timeout,
                    cwd=tmpdir,
                )
                return {
                    "passed": r.returncode == 0,
                    "output": (r.stdout + r.stderr)[-1000:],
                    "phase": "execution",
                }
            except subprocess.TimeoutExpired:
                return {"passed": False, "error": "执行超时", "phase": "execution"}

    # ────────────── 代码质量 ──────────────

    def check_quality(self, code: str, filepath: str = "solution.py") -> dict:
        """代码质量多维度评估。

        Returns:
            {"syntax_valid": bool, "lint_issues": N, "complexity": {...},
             "security_issues": [...], "quality_score": float}
        """
        result: dict[str, Any] = {}

        # 语法检查
        try:
            tree = ast.parse(code)
            result["syntax_valid"] = True
        except SyntaxError as e:
            result["syntax_valid"] = False
            result["syntax_error"] = str(e)
            result["quality_score"] = 0.0
            return result

        # 代码复杂度
        result["complexity"] = self._analyze_complexity(tree)

        # lint 检查（如果有 ruff）
        result["lint_issues"] = self._run_lint(code, filepath)

        # 基础安全检查
        result["security_issues"] = self._check_security(code, tree)

        # 综合评分
        score = 1.0
        if result["lint_issues"] > 0:
            score -= min(result["lint_issues"] * 0.05, 0.3)
        if result["security_issues"]:
            score -= len(result["security_issues"]) * 0.1
        avg_cc = result["complexity"].get("avg_complexity", 1)
        if avg_cc > 10:
            score -= 0.2
        elif avg_cc > 5:
            score -= 0.1
        result["quality_score"] = max(0.0, round(score, 2))

        return result

    def _analyze_complexity(self, tree: ast.AST) -> dict:
        """简化的圈复杂度分析"""
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = 1  # 基础复杂度
                for child in ast.walk(node):
                    if isinstance(child, (ast.If, ast.While, ast.For)):
                        cc += 1
                    elif isinstance(child, ast.BoolOp):
                        cc += len(child.values) - 1
                    elif isinstance(child, ast.ExceptHandler):
                        cc += 1
                functions.append({"name": node.name, "complexity": cc, "lineno": node.lineno})

        if not functions:
            return {"total_functions": 0, "avg_complexity": 1, "max_complexity": 1}

        complexities = [f["complexity"] for f in functions]
        return {
            "total_functions": len(functions),
            "avg_complexity": round(sum(complexities) / len(complexities), 1),
            "max_complexity": max(complexities),
            "high_complexity": [f for f in functions if f["complexity"] > 10],
        }

    def _run_lint(self, code: str, filepath: str) -> int:
        """运行 lint 检查，返回问题数"""
        import shutil
        linter = shutil.which("ruff")
        if not linter:
            return 0

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            f.flush()
            try:
                r = subprocess.run(
                    [linter, "check", "--quiet", f.name],
                    capture_output=True, text=True, timeout=10,
                )
                issues = [l for l in r.stdout.strip().split("\n") if l.strip()]
                return len(issues)
            except Exception:
                return 0
            finally:
                Path(f.name).unlink(missing_ok=True)

    def _check_security(self, code: str, tree: ast.AST) -> list[str]:
        """基础安全模式检测"""
        issues = []
        code_lower = code.lower()

        # 危险函数调用检测
        dangerous_patterns = {
            "eval(": "使用了 eval()，存在代码注入风险",
            "exec(": "使用了 exec()，存在代码注入风险",
            "os.system(": "使用了 os.system()，建议使用 subprocess",
            "__import__": "使用了 __import__()，可能绕过导入控制",
            "pickle.loads": "使用了 pickle.loads()，存在反序列化风险",
        }
        for pattern, msg in dangerous_patterns.items():
            if pattern in code:
                issues.append(msg)

        # SQL 注入风险检测
        if "execute(" in code and ("format(" in code or "%" in code or "f'" in code_lower):
            issues.append("可能存在 SQL 注入风险：字符串拼接用于数据库查询")

        return issues


class BenchmarkScorer:
    """基准评测评分器，对标业界标准"""

    @staticmethod
    def pass_at_k(results: list[bool], k: int = 1) -> float:
        """计算 pass@k 指标（HumanEval 标准）。

        pass@k = 1 - C(n-c, k) / C(n, k)
        其中 n = 总尝试次数, c = 通过次数
        """
        import math
        n = len(results)
        c = sum(results)
        if n < k:
            return 1.0 if c > 0 else 0.0
        if c == 0:
            return 0.0
        if c >= k:
            return 1.0

        def comb(a, b):
            if b > a or b < 0:
                return 0
            return math.comb(a, b)

        return 1.0 - comb(n - c, k) / comb(n, k)

    @staticmethod
    def score_suite(results: list[dict]) -> dict:
        """计算评测套件总分。

        Args:
            results: [{"task_id": ..., "passed": bool, "quality_score": float, ...}]

        Returns:
            {"pass_rate": float, "pass_at_1": float, "avg_quality": float, ...}
        """
        if not results:
            return {"pass_rate": 0.0, "total": 0}

        total = len(results)
        passed = sum(1 for r in results if r.get("passed", False))
        pass_bools = [r.get("passed", False) for r in results]
        quality_scores = [r.get("quality_score", 0.0) for r in results if "quality_score" in r]

        return {
            "total": total,
            "passed": passed,
            "pass_rate": round(passed / total, 4),
            "pass_at_1": BenchmarkScorer.pass_at_k(pass_bools, 1),
            "avg_quality": round(sum(quality_scores) / len(quality_scores), 3) if quality_scores else 0.0,
        }
