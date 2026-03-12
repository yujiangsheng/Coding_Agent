"""测试执行工具（v2.0 — 增强测试分析）

为 Turing 补齐自动化测试能力（对标 Claude Code / Cursor 的测试驱动开发）：
- run_tests       — 自动检测并运行项目测试，支持覆盖率和失败细节提取（v2.0 增强）
- generate_tests  — 为指定函数/文件生成测试用例框架

v2.0 增强：
- **覆盖率支持**：pytest 自动加 --cov，返回覆盖率百分比
- **失败细节提取**：从输出中解析失败测试名、断言消息、堆栈跟踪
- **结构化结果**：返回 failures_detail 列表，每项含测试名和失败原因
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from turing.tools.registry import tool


def _detect_test_framework(path: str = ".") -> dict:
    """检测项目使用的测试框架"""
    p = Path(path).resolve()

    # Python
    if (p / "pytest.ini").exists() or (p / "pyproject.toml").exists() or (p / "setup.cfg").exists():
        # Check for pytest in pyproject.toml or requirements
        for f in ["pyproject.toml", "requirements.txt", "setup.cfg"]:
            fp = p / f
            if fp.exists() and "pytest" in fp.read_text(encoding="utf-8", errors="replace"):
                return {"framework": "pytest", "language": "python", "command": "python3 -m pytest"}
        # Fallback to unittest
        return {"framework": "unittest", "language": "python", "command": "python3 -m unittest discover"}

    if (p / "requirements.txt").exists() or (p / "setup.py").exists():
        req = (p / "requirements.txt")
        if req.exists() and "pytest" in req.read_text(encoding="utf-8", errors="replace"):
            return {"framework": "pytest", "language": "python", "command": "python3 -m pytest"}
        return {"framework": "unittest", "language": "python", "command": "python3 -m unittest discover"}

    # JavaScript/TypeScript
    pkg_json = p / "package.json"
    if pkg_json.exists():
        import json
        try:
            pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
            scripts = pkg.get("scripts", {})
            deps = {**pkg.get("devDependencies", {}), **pkg.get("dependencies", {})}
            if "vitest" in deps:
                return {"framework": "vitest", "language": "javascript", "command": "npx vitest run"}
            if "jest" in deps or "test" in scripts and "jest" in scripts.get("test", ""):
                return {"framework": "jest", "language": "javascript", "command": "npx jest"}
            if "mocha" in deps:
                return {"framework": "mocha", "language": "javascript", "command": "npx mocha"}
            if "test" in scripts:
                return {"framework": "npm-test", "language": "javascript", "command": "npm test"}
        except Exception:
            pass

    # Go
    if (p / "go.mod").exists():
        return {"framework": "go-test", "language": "go", "command": "go test ./..."}

    # Rust
    if (p / "Cargo.toml").exists():
        return {"framework": "cargo-test", "language": "rust", "command": "cargo test"}

    # Java / Kotlin
    if (p / "pom.xml").exists():
        return {"framework": "maven", "language": "java", "command": "mvn test"}
    if (p / "build.gradle").exists() or (p / "build.gradle.kts").exists():
        return {"framework": "gradle", "language": "java", "command": "./gradlew test"}

    return {"framework": "unknown", "language": "unknown", "command": None}


@tool(
    name="run_tests",
    description="自动检测项目的测试框架并运行测试。支持 pytest、unittest、jest、vitest、go test、cargo test 等。可指定具体测试文件或测试名运行部分测试。支持覆盖率报告（pytest --cov）。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "项目根目录（默认当前目录）",
            },
            "test_file": {
                "type": "string",
                "description": "指定测试文件路径（可选，默认运行全部测试）",
            },
            "test_name": {
                "type": "string",
                "description": "指定测试函数/方法名（可选，用于运行单个测试）",
            },
            "verbose": {
                "type": "boolean",
                "description": "是否显示详细输出（默认 true）",
            },
            "coverage": {
                "type": "boolean",
                "description": "是否启用覆盖率报告（默认 false，仅 pytest 支持）",
            },
        },
        "required": [],
    },
)
def run_tests(
    path: str = ".",
    test_file: str = None,
    test_name: str = None,
    verbose: bool = True,
    coverage: bool = False,
) -> dict:
    """自动检测测试框架并运行测试，支持覆盖率报告和失败详情提取。"""
    info = _detect_test_framework(path)
    framework = info["framework"]
    base_cmd = info["command"]

    if base_cmd is None:
        return {"error": "未检测到测试框架。请确认项目中包含测试配置文件。", "detected": info}

    # 构建测试命令
    cmd = base_cmd
    if framework == "pytest":
        if verbose:
            cmd += " -v"
        if coverage:
            cmd += " --cov --cov-report=term-missing"
        if test_file:
            cmd += f" {test_file}"
            if test_name:
                cmd += f"::{test_name}"
        elif test_name:
            cmd += f" -k {test_name}"
    elif framework == "unittest":
        if test_file:
            module = test_file.replace("/", ".").replace(".py", "")
            cmd = f"python3 -m unittest {module}"
            if test_name:
                cmd += f".{test_name}"
    elif framework in ("jest", "vitest"):
        if test_file:
            cmd += f" {test_file}"
        if test_name:
            cmd += f" -t '{test_name}'"
        if coverage and framework == "jest":
            cmd += " --coverage"
    elif framework == "go-test":
        if verbose:
            cmd += " -v"
        if coverage:
            cmd += " -cover"
        if test_file:
            cmd = f"go test -run {test_name or '.'} {test_file}"
    elif framework == "cargo-test":
        if test_name:
            cmd += f" {test_name}"

    # 执行
    from turing.config import Config
    cfg = Config.load()
    workspace = cfg.get("security.workspace_root", None) or path

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=120, cwd=workspace,
        )
        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr
        if len(output) > 50000:
            output = output[:25000] + "\n...(截断)...\n" + output[-25000:]

        # ── 分析测试结果 ──
        passed = failed = errors = 0
        failures_detail = []
        coverage_pct = None

        if framework == "pytest":
            # 解析 passed/failed 计数
            for line in output.split("\n"):
                if " passed" in line and line.strip().startswith("="):
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p == "passed" and i > 0:
                            try: passed = int(parts[i-1])
                            except ValueError: pass
                        elif p == "failed" and i > 0:
                            try: failed = int(parts[i-1])
                            except ValueError: pass
                        elif p in ("error", "errors") and i > 0:
                            try: errors = int(parts[i-1])
                            except ValueError: pass

            # 提取失败测试的详细信息
            failure_blocks = re.findall(
                r'_{3,}\s+([\w:.\[\]]+)\s+_{3,}\n(.*?)(?=\n_{3,}|\n={3,})',
                output, re.DOTALL
            )
            for test_id, block in failure_blocks:
                # 提取 AssertionError / 最后一行错误
                assertion = ""
                for bl in block.strip().split("\n"):
                    bl_stripped = bl.strip()
                    if bl_stripped.startswith(("AssertionError", "assert ", "E ", "> ")):
                        assertion = bl_stripped
                    elif "Error" in bl_stripped or "Exception" in bl_stripped:
                        assertion = bl_stripped
                failures_detail.append({
                    "test": test_id.strip(),
                    "reason": assertion[:200] if assertion else block.strip()[-200:],
                })

            # 提取覆盖率（TOTAL 行的百分比）
            cov_match = re.search(r'TOTAL\s+\d+\s+\d+\s+(\d+)%', output)
            if cov_match:
                coverage_pct = int(cov_match.group(1))

        elif framework in ("jest", "vitest"):
            # Jest/Vitest 解析
            pass_m = re.search(r'Tests:\s+(\d+)\s+passed', output)
            fail_m = re.search(r'Tests:\s+(\d+)\s+failed', output)
            if pass_m: passed = int(pass_m.group(1))
            if fail_m: failed = int(fail_m.group(1))

        test_result = {
            "framework": framework,
            "command": cmd,
            "exit_code": result.returncode,
            "passed": passed if passed else ("all" if result.returncode == 0 else 0),
            "failed": failed if failed else (0 if result.returncode == 0 else "unknown"),
            "errors": errors,
            "success": result.returncode == 0,
            "output": output.strip(),
        }

        if failures_detail:
            test_result["failures_detail"] = failures_detail[:20]
        if coverage_pct is not None:
            test_result["coverage_percent"] = coverage_pct

        return test_result
    except subprocess.TimeoutExpired:
        return {"error": "测试运行超时（>120s）", "framework": framework}
    except Exception as e:
        return {"error": f"测试执行失败: {e}", "framework": framework}


@tool(
    name="generate_tests",
    description="为指定的源代码文件生成测试用例。支持两种模式：模板模式（快速生成测试框架）和 LLM 智能模式（生成包含边界条件、异常路径的完整测试）。",
    parameters={
        "type": "object",
        "properties": {
            "source_file": {
                "type": "string",
                "description": "要测试的源代码文件路径",
            },
            "output_file": {
                "type": "string",
                "description": "测试文件输出路径（可选，自动推断）",
            },
            "functions": {
                "type": "string",
                "description": "要测试的函数名列表，逗号分隔（可选，默认全部公开函数）",
            },
            "smart": {
                "type": "boolean",
                "description": "是否使用 LLM 智能生成测试（含边界条件和异常路径），默认 false",
            },
        },
        "required": ["source_file"],
    },
)
def generate_tests(
    source_file: str,
    output_file: str = None,
    functions: str = None,
    smart: bool = False,
) -> dict:
    """为源文件生成测试脚手架。"""
    p = Path(source_file)
    if not p.exists():
        return {"error": f"源文件不存在: {source_file}"}

    suffix = p.suffix
    content = p.read_text(encoding="utf-8", errors="replace")

    # 提取函数/方法名
    target_funcs = []
    if functions:
        target_funcs = [f.strip() for f in functions.split(",")]
    else:
        # 自动提取公开函数
        if suffix == ".py":
            import re
            for m in re.finditer(r'^(?:def|async def)\s+(\w+)\s*\(', content, re.MULTILINE):
                name = m.group(1)
                if not name.startswith("_"):
                    target_funcs.append(name)
            # Also extract class methods
            for m in re.finditer(r'^\s+(?:def|async def)\s+(\w+)\s*\(self', content, re.MULTILINE):
                name = m.group(1)
                if not name.startswith("_"):
                    target_funcs.append(name)
        elif suffix in (".js", ".ts", ".jsx", ".tsx"):
            import re
            for m in re.finditer(r'(?:export\s+)?(?:function|const)\s+(\w+)', content):
                name = m.group(1)
                if not name.startswith("_"):
                    target_funcs.append(name)

    if not target_funcs:
        return {"error": "未能提取可测试的函数。请用 functions 参数手动指定。"}

    # 推断测试文件路径
    if not output_file:
        if suffix == ".py":
            output_file = str(p.parent / f"test_{p.name}")
        elif suffix in (".js", ".ts"):
            output_file = str(p.parent / f"{p.stem}.test{suffix}")
        else:
            output_file = str(p.parent / f"test_{p.name}")

    # ===== LLM 智能测试生成（v3.1）=====
    if smart:
        return _generate_smart_tests(p, content, suffix, target_funcs, output_file)

    # 生成测试框架代码
    if suffix == ".py":
        module_name = str(p.with_suffix("")).replace("/", ".").replace("\\", ".")
        test_code = f'"""自动生成的测试用例 — {p.name}"""\n\n'
        test_code += f"import pytest\n"
        test_code += f"from {module_name} import {', '.join(target_funcs[:20])}\n\n\n"
        for func in target_funcs:
            test_code += f"class Test{func.title().replace('_', '')}:\n"
            test_code += f'    """Tests for {func}()"""\n\n'
            test_code += f"    def test_{func}_basic(self):\n"
            test_code += f'        """基本功能测试"""\n'
            test_code += f"        # TODO: 实现测试\n"
            test_code += f"        result = {func}()\n"
            test_code += f"        assert result is not None\n\n"
            test_code += f"    def test_{func}_edge_case(self):\n"
            test_code += f'        """边界条件测试"""\n'
            test_code += f"        # TODO: 实现边界测试\n"
            test_code += f"        pass\n\n\n"

    elif suffix in (".js", ".ts", ".jsx", ".tsx"):
        rel_import = "./" + p.stem
        test_code = f"// 自动生成的测试用例 — {p.name}\n\n"
        test_code += f"import {{ {', '.join(target_funcs[:20])} }} from '{rel_import}';\n\n"
        for func in target_funcs:
            test_code += f"describe('{func}', () => {{\n"
            test_code += f"  test('basic functionality', () => {{\n"
            test_code += f"    // TODO: implement test\n"
            test_code += f"    const result = {func}();\n"
            test_code += f"    expect(result).toBeDefined();\n"
            test_code += f"  }});\n\n"
            test_code += f"  test('edge case', () => {{\n"
            test_code += f"    // TODO: implement edge case test\n"
            test_code += f"  }});\n"
            test_code += f"}});\n\n"
    else:
        return {"error": f"不支持为 {suffix} 文件生成测试。支持: .py, .js, .ts"}

    # 写入测试文件
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(test_code, encoding="utf-8")

    return {
        "status": "ok",
        "test_file": str(out_path),
        "functions_covered": target_funcs,
        "function_count": len(target_funcs),
        "language": "python" if suffix == ".py" else "javascript",
        "hint": "已生成测试框架，请补充具体的测试逻辑和断言。",
    }


def _generate_smart_tests(source_path: Path, content: str, suffix: str,
                          target_funcs: list, output_file: str) -> dict:
    """使用 LLM 智能生成包含边界条件和异常路径的测试（v3.1）"""
    try:
        from turing.llm.provider import create_provider
        from turing.config import Config
        cfg = Config.load()

        # 从配置创建 provider
        llm_cfg = cfg.get("llm", {})
        default_name = llm_cfg.get("default", "ollama")
        provider_cfg = llm_cfg.get("providers", {}).get(default_name, {})
        provider_type = provider_cfg.pop("type", default_name)
        provider = create_provider(provider_type, **provider_cfg)
        provider_cfg["type"] = provider_type  # 恢复

        # 限制源代码长度
        src_snippet = content[:6000]
        if len(content) > 6000:
            src_snippet += "\n# ... (source truncated)"

        lang = "Python" if suffix == ".py" else "JavaScript/TypeScript"
        framework = "pytest" if suffix == ".py" else "jest"
        funcs_str = ", ".join(target_funcs[:15])

        prompt = f"""Generate comprehensive test code for the following {lang} source file.

Functions to test: {funcs_str}

Source code:
```{suffix.lstrip('.')}
{src_snippet}
```

Requirements:
1. Use {framework} as the test framework
2. Include tests for: normal cases, edge cases, boundary values, error/exception handling
3. Use descriptive test names that explain WHAT is being tested
4. Include docstrings/comments explaining test intent
5. Mock external dependencies where appropriate
6. Output ONLY the complete test file code, no explanations

Output the test code directly, wrapped in a single code block."""

        resp = provider.chat(
            messages=[
                {"role": "system", "content": f"You are a senior QA engineer. Generate production-quality {lang} tests."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        generated = resp.get("content", "")

        # 提取代码块
        import re as _re
        code_match = _re.search(r'```(?:\w+)?\n(.*?)```', generated, _re.DOTALL)
        test_code = code_match.group(1) if code_match else generated

        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(test_code, encoding="utf-8")

        return {
            "status": "ok",
            "mode": "smart_llm",
            "test_file": str(out_path),
            "functions_covered": target_funcs,
            "function_count": len(target_funcs),
            "language": "python" if suffix == ".py" else "javascript",
            "hint": "已通过 LLM 智能生成完整测试（含边界条件和异常路径）。",
        }
    except Exception as e:
        return {"error": f"LLM 智能测试生成失败: {e}", "hint": "可尝试不使用 smart=true 生成模板测试。"}


# ────────────────── 测试覆盖率工具 ──────────────────


@tool(
    name="test_coverage",
    description="运行测试并生成覆盖率报告。支持 pytest-cov（Python）和 Istanbul/c8（JS/TS）。"
                "返回总覆盖率和低覆盖文件列表。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "项目路径（默认当前目录）",
            },
            "source_dir": {
                "type": "string",
                "description": "源代码目录（如 'src' 或 'turing'，用于 --cov 参数）",
            },
            "threshold": {
                "type": "integer",
                "description": "覆盖率阈值百分比（低于此值的文件会被标记，默认 80）",
            },
        },
        "required": [],
    },
)
def test_coverage(path: str = ".", source_dir: str = None, threshold: int = 80) -> dict:
    """运行测试覆盖率分析。"""
    import subprocess
    import re as _re

    p = Path(path).resolve()
    framework = _detect_test_framework(str(p))

    if framework == "pytest":
        cov_target = source_dir or "."
        cmd = ["python3", "-m", "pytest", "--tb=short", "-q",
               f"--cov={cov_target}", "--cov-report=term-missing"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, cwd=str(p)
            )
        except subprocess.TimeoutExpired:
            return {"error": "覆盖率测试超时（120s）"}
        except FileNotFoundError:
            return {"error": "pytest 或 pytest-cov 未安装"}

        output = result.stdout + "\n" + result.stderr
        # 解析覆盖率表格
        # 格式: Name    Stmts   Miss  Cover   Missing
        files_coverage = []
        total_coverage = None
        for line in output.split("\n"):
            # 匹配文件行: turing/agent.py  500  100  80%  10-20, 30
            m = _re.match(
                r'^(\S+\.py)\s+(\d+)\s+(\d+)\s+(\d+)%\s*(.*)',
                line.strip()
            )
            if m:
                fname, stmts, miss, cover, missing = m.groups()
                cover_int = int(cover)
                entry = {
                    "file": fname,
                    "statements": int(stmts),
                    "missing": int(miss),
                    "coverage": cover_int,
                }
                if missing.strip():
                    entry["missing_lines"] = missing.strip()
                if cover_int < threshold:
                    entry["below_threshold"] = True
                files_coverage.append(entry)

            # 匹配 TOTAL 行
            m_total = _re.match(r'^TOTAL\s+(\d+)\s+(\d+)\s+(\d+)%', line.strip())
            if m_total:
                total_coverage = int(m_total.group(3))

        below_threshold = [f for f in files_coverage if f.get("below_threshold")]

        return {
            "status": "ok",
            "framework": "pytest-cov",
            "total_coverage": total_coverage,
            "threshold": threshold,
            "files": files_coverage,
            "below_threshold_count": len(below_threshold),
            "below_threshold_files": [f["file"] for f in below_threshold],
            "passed": total_coverage is not None and total_coverage >= threshold,
            "raw_output": output[-2000:] if len(output) > 2000 else output,
        }

    elif framework in ("jest", "vitest"):
        cmd = "npx jest --coverage" if framework == "jest" else "npx vitest run --coverage"
        try:
            result = subprocess.run(
                cmd.split(), capture_output=True, text=True,
                timeout=120, cwd=str(p)
            )
        except subprocess.TimeoutExpired:
            return {"error": "覆盖率测试超时"}

        return {
            "status": "ok",
            "framework": framework,
            "raw_output": result.stdout[-3000:],
        }

    return {"error": f"不支持的测试框架或未检测到测试: {framework or 'none'}"}
