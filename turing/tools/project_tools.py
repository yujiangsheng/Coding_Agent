"""项目理解工具

为 Turing 补齐项目结构理解能力（对标 Gemini 的大规模代码库导航）：
- detect_project       — 自动检测项目类型、语言、框架、构建系统
- analyze_dependencies — 解析依赖文件，列出直接/间接依赖

Gemini 和 Claude Opus 都能自动理解项目上下文，无需用户手动说明。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from turing.tools.registry import tool


@tool(
    name="detect_project",
    description="自动检测项目类型、编程语言、框架、包管理器和构建系统。让 Turing 像 Gemini 一样在任务开始前理解项目全貌。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "项目根目录路径（默认当前目录）",
            },
        },
        "required": [],
    },
)
def detect_project(path: str = ".") -> dict:
    """自动检测项目类型、语言、框架、测试框架等。"""
    p = Path(path).resolve()
    if not p.is_dir():
        return {"error": f"路径不存在或不是目录: {path}"}

    result = {
        "root": str(p),
        "languages": [],
        "frameworks": [],
        "package_manager": None,
        "build_system": None,
        "test_framework": None,
        "has_ci": False,
        "has_docker": False,
        "has_git": (p / ".git").exists(),
        "entry_points": [],
        "config_files": [],
    }

    # --- 语言检测 ---
    ext_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".go": "Go", ".rs": "Rust", ".java": "Java",
        ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
        ".kt": "Kotlin", ".cs": "C#", ".cpp": "C++", ".c": "C",
    }
    lang_counts = {}
    for f in p.rglob("*"):
        if f.is_file() and not any(part.startswith(".") for part in f.parts):
            lang = ext_map.get(f.suffix.lower())
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

    result["languages"] = sorted(lang_counts.keys(), key=lambda l: lang_counts[l], reverse=True)
    result["language_stats"] = {k: v for k, v in sorted(lang_counts.items(), key=lambda x: -x[1])}

    # --- Python 项目 ---
    if (p / "pyproject.toml").exists():
        result["config_files"].append("pyproject.toml")
        result["build_system"] = "pyproject.toml"
        content = (p / "pyproject.toml").read_text(errors="ignore")
        if "django" in content.lower():
            result["frameworks"].append("Django")
        if "flask" in content.lower():
            result["frameworks"].append("Flask")
        if "fastapi" in content.lower():
            result["frameworks"].append("FastAPI")
        if "poetry" in content.lower():
            result["package_manager"] = "Poetry"
        elif "hatch" in content.lower():
            result["package_manager"] = "Hatch"
        if "pytest" in content.lower():
            result["test_framework"] = "pytest"

    if (p / "requirements.txt").exists():
        result["config_files"].append("requirements.txt")
        if not result["package_manager"]:
            result["package_manager"] = "pip"
        content = (p / "requirements.txt").read_text(errors="ignore").lower()
        for fw, name in [("django", "Django"), ("flask", "Flask"), ("fastapi", "FastAPI"),
                         ("torch", "PyTorch"), ("tensorflow", "TensorFlow")]:
            if fw in content and name not in result["frameworks"]:
                result["frameworks"].append(name)

    if (p / "setup.py").exists():
        result["config_files"].append("setup.py")
        if not result["build_system"]:
            result["build_system"] = "setuptools"

    if (p / "Pipfile").exists():
        result["package_manager"] = "Pipenv"
        result["config_files"].append("Pipfile")

    # --- JS/TS 项目 ---
    if (p / "package.json").exists():
        result["config_files"].append("package.json")
        try:
            pkg = json.loads((p / "package.json").read_text(errors="ignore"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            for fw, name in [("react", "React"), ("vue", "Vue"), ("angular", "Angular"),
                             ("next", "Next.js"), ("nuxt", "Nuxt"), ("express", "Express"),
                             ("svelte", "Svelte"), ("nestjs", "NestJS")]:
                if any(fw in d.lower() for d in deps):
                    result["frameworks"].append(name)

            if "jest" in deps:
                result["test_framework"] = "Jest"
            elif "vitest" in deps:
                result["test_framework"] = "Vitest"
            elif "mocha" in deps:
                result["test_framework"] = "Mocha"

            if (p / "yarn.lock").exists():
                result["package_manager"] = "Yarn"
            elif (p / "pnpm-lock.yaml").exists():
                result["package_manager"] = "pnpm"
            elif (p / "bun.lockb").exists():
                result["package_manager"] = "Bun"
            else:
                result["package_manager"] = "npm"
        except (json.JSONDecodeError, OSError):
            result["package_manager"] = "npm"

    if (p / "tsconfig.json").exists():
        result["config_files"].append("tsconfig.json")

    # --- Go ---
    if (p / "go.mod").exists():
        result["config_files"].append("go.mod")
        result["package_manager"] = "Go Modules"
        result["build_system"] = "go build"
        result["test_framework"] = "go test"

    # --- Rust ---
    if (p / "Cargo.toml").exists():
        result["config_files"].append("Cargo.toml")
        result["package_manager"] = "Cargo"
        result["build_system"] = "Cargo"
        result["test_framework"] = "cargo test"

    # --- Java ---
    if (p / "pom.xml").exists():
        result["config_files"].append("pom.xml")
        result["build_system"] = "Maven"
    elif (p / "build.gradle").exists() or (p / "build.gradle.kts").exists():
        result["config_files"].append("build.gradle")
        result["build_system"] = "Gradle"

    # --- CI/CD ---
    ci_configs = {
        ".github/workflows": "GitHub Actions",
        ".gitlab-ci.yml": "GitLab CI",
        "Jenkinsfile": "Jenkins",
        ".circleci": "CircleCI",
        ".travis.yml": "Travis CI",
        "azure-pipelines.yml": "Azure Pipelines",
        "bitbucket-pipelines.yml": "Bitbucket Pipelines",
    }
    ci_details = []
    for ci_path, ci_name in ci_configs.items():
        ci_full = p / ci_path
        if ci_full.exists():
            result["has_ci"] = True
            result["config_files"].append(ci_path)
            ci_info = {"provider": ci_name, "path": ci_path}
            # 提取 GitHub Actions workflow 名称
            if ci_name == "GitHub Actions" and ci_full.is_dir():
                workflows = list(ci_full.glob("*.yml")) + list(ci_full.glob("*.yaml"))
                ci_info["workflows"] = [w.name for w in workflows[:10]]
            ci_details.append(ci_info)
    result["ci_details"] = ci_details

    # --- Docker ---
    docker_files = []
    if (p / "Dockerfile").exists():
        result["has_docker"] = True
        docker_files.append("Dockerfile")
    if (p / "docker-compose.yml").exists() or (p / "docker-compose.yaml").exists():
        result["has_docker"] = True
        docker_files.append("docker-compose.yml")
    if (p / ".dockerignore").exists():
        docker_files.append(".dockerignore")
    result["docker_files"] = docker_files

    # --- Monorepo ---
    is_monorepo = False
    monorepo_tool = None
    if (p / "lerna.json").exists():
        is_monorepo = True
        monorepo_tool = "Lerna"
    elif (p / "nx.json").exists():
        is_monorepo = True
        monorepo_tool = "Nx"
    elif (p / "pnpm-workspace.yaml").exists():
        is_monorepo = True
        monorepo_tool = "pnpm workspaces"
    elif (p / "package.json").exists():
        try:
            pkg = json.loads((p / "package.json").read_text(errors="ignore"))
            if "workspaces" in pkg:
                is_monorepo = True
                monorepo_tool = "npm/yarn workspaces"
        except Exception:
            pass
    result["is_monorepo"] = is_monorepo
    if monorepo_tool:
        result["monorepo_tool"] = monorepo_tool

    # --- 入口点 ---
    entry_candidates = ["main.py", "app.py", "manage.py", "index.js", "index.ts",
                         "src/index.js", "src/index.ts", "src/main.py", "main.go", "src/main.rs"]
    for entry in entry_candidates:
        if (p / entry).exists():
            result["entry_points"].append(entry)

    return result


@tool(
    name="analyze_dependencies",
    description="解析项目依赖文件，列出直接依赖（含版本约束）。支持 requirements.txt、package.json、go.mod、Cargo.toml、pyproject.toml。",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "项目根目录路径（默认当前目录）",
            },
        },
        "required": [],
    },
)
def analyze_dependencies(path: str = ".") -> dict:
    """解析依赖文件（requirements.txt/package.json/go.mod 等）。"""
    p = Path(path).resolve()
    if not p.is_dir():
        return {"error": f"路径不存在或不是目录: {path}"}

    result = {
        "root": str(p),
        "dependency_files": [],
        "dependencies": {},
        "dev_dependencies": {},
        "total_count": 0,
    }

    # --- Python: requirements.txt ---
    req_file = p / "requirements.txt"
    if req_file.exists():
        result["dependency_files"].append("requirements.txt")
        for line in req_file.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            # 解析 package>=version 格式
            match = re.match(r"^([a-zA-Z0-9_.-]+)\s*(.*)", line)
            if match:
                name = match.group(1)
                version = match.group(2).strip() or "*"
                result["dependencies"][name] = version

    # --- Python: pyproject.toml ---
    pyproject_file = p / "pyproject.toml"
    if pyproject_file.exists():
        result["dependency_files"].append("pyproject.toml")
        content = pyproject_file.read_text(errors="ignore")
        # 简单解析 dependencies 列表
        in_deps = False
        in_dev_deps = False
        for line in content.splitlines():
            if re.match(r"\[.*dependencies\]", line) and "dev" not in line.lower() and "optional" not in line.lower():
                in_deps = True
                in_dev_deps = False
                continue
            if re.match(r"\[.*dev.*dependencies\]", line, re.IGNORECASE):
                in_deps = False
                in_dev_deps = True
                continue
            if line.startswith("[") and not line.startswith("[["):
                in_deps = False
                in_dev_deps = False
                continue

            if in_deps or in_dev_deps:
                # "package>=1.0" 或 package = ">=1.0" 格式
                m = re.match(r'["\']?([a-zA-Z0-9_.-]+)([><=!~].+)?["\']?', line.strip())
                if m:
                    name = m.group(1)
                    ver = (m.group(2) or "*").strip().strip('"').strip("'")
                    if in_deps:
                        result["dependencies"][name] = ver
                    else:
                        result["dev_dependencies"][name] = ver

    # --- Node.js: package.json ---
    pkg_file = p / "package.json"
    if pkg_file.exists():
        result["dependency_files"].append("package.json")
        try:
            pkg = json.loads(pkg_file.read_text(errors="ignore"))
            for name, ver in pkg.get("dependencies", {}).items():
                result["dependencies"][name] = ver
            for name, ver in pkg.get("devDependencies", {}).items():
                result["dev_dependencies"][name] = ver
        except (json.JSONDecodeError, OSError):
            pass

    # --- Go: go.mod ---
    gomod_file = p / "go.mod"
    if gomod_file.exists():
        result["dependency_files"].append("go.mod")
        in_require = False
        for line in gomod_file.read_text(errors="ignore").splitlines():
            if line.strip().startswith("require ("):
                in_require = True
                continue
            if in_require and line.strip() == ")":
                in_require = False
                continue
            if in_require or line.strip().startswith("require "):
                parts = line.strip().replace("require ", "").split()
                if len(parts) >= 2:
                    result["dependencies"][parts[0]] = parts[1]

    # --- Rust: Cargo.toml ---
    cargo_file = p / "Cargo.toml"
    if cargo_file.exists():
        result["dependency_files"].append("Cargo.toml")
        in_deps = False
        in_dev = False
        for line in cargo_file.read_text(errors="ignore").splitlines():
            if line.strip() == "[dependencies]":
                in_deps = True
                in_dev = False
                continue
            if line.strip() == "[dev-dependencies]":
                in_deps = False
                in_dev = True
                continue
            if line.startswith("["):
                in_deps = False
                in_dev = False
                continue
            m = re.match(r'(\S+)\s*=\s*["\']?(.+?)["\']?\s*$', line.strip())
            if m and (in_deps or in_dev):
                name, ver = m.group(1), m.group(2)
                if in_deps:
                    result["dependencies"][name] = ver
                else:
                    result["dev_dependencies"][name] = ver

    result["total_count"] = len(result["dependencies"]) + len(result["dev_dependencies"])
    return result


# ────────────────── 任务规划工具 ──────────────────


@tool(
    name="task_plan",
    description="将复杂任务拆解为结构化的子任务列表，包含依赖关系、预估风险、"
                "验证标准。输出可直接作为执行计划使用。",
    parameters={
        "type": "object",
        "properties": {
            "task_description": {
                "type": "string",
                "description": "任务描述",
            },
            "project_path": {
                "type": "string",
                "description": "项目路径（可选，用于检测项目上下文）",
            },
            "max_steps": {
                "type": "integer",
                "description": "最大步骤数（默认 10）",
            },
        },
        "required": ["task_description"],
    },
)
def task_plan(task_description: str, project_path: str = ".", max_steps: int = 10) -> dict:
    """生成结构化任务执行计划。"""
    from pathlib import Path

    # 通过关键词检测任务类型
    desc_lower = task_description.lower()
    task_type = "general"
    if any(kw in desc_lower for kw in ["bug", "fix", "error", "issue", "crash"]):
        task_type = "bug_fix"
    elif any(kw in desc_lower for kw in ["refactor", "重构", "restructure", "clean"]):
        task_type = "refactor"
    elif any(kw in desc_lower for kw in ["feature", "add", "implement", "新增", "功能"]):
        task_type = "feature"
    elif any(kw in desc_lower for kw in ["test", "测试", "coverage"]):
        task_type = "testing"
    elif any(kw in desc_lower for kw in ["deploy", "ci", "cd", "pipeline"]):
        task_type = "devops"

    # 通用步骤模板
    templates = {
        "bug_fix": [
            {"step": "复现问题", "action": "根据描述复现 bug，确认错误行为", "risk": "low", "verify": "确认能稳定复现"},
            {"step": "定位根因", "action": "使用 smart_context + search_code 追踪错误堆栈", "risk": "low", "verify": "找到问题代码位置"},
            {"step": "分析影响", "action": "用 impact_analysis 评估修改影响范围", "risk": "low", "verify": "确认无级联风险"},
            {"step": "实施修复", "action": "edit_file 修改代码", "risk": "medium", "verify": "代码逻辑正确"},
            {"step": "运行测试", "action": "run_tests 验证修复", "risk": "low", "verify": "全部测试通过"},
            {"step": "回归验证", "action": "确认修复不引入新问题", "risk": "low", "verify": "无新增失败"},
        ],
        "feature": [
            {"step": "需求分析", "action": "明确输入输出、边界条件、依赖关系", "risk": "low", "verify": "需求清晰完整"},
            {"step": "项目理解", "action": "repo_map + detect_project 了解代码结构", "risk": "low", "verify": "了解相关模块"},
            {"step": "接口设计", "action": "设计函数签名、数据结构、模块划分", "risk": "medium", "verify": "设计合理可扩展"},
            {"step": "实现功能", "action": "edit_file / write_file 编写代码", "risk": "medium", "verify": "代码实现完整"},
            {"step": "编写测试", "action": "generate_tests 生成测试用例", "risk": "low", "verify": "覆盖关键路径"},
            {"step": "集成验证", "action": "run_tests + lint_code 验证质量", "risk": "low", "verify": "测试通过、无 lint 问题"},
        ],
        "refactor": [
            {"step": "健康评估", "action": "complexity_report + code_structure 分析当前状态", "risk": "low", "verify": "识别问题热点"},
            {"step": "测试基线", "action": "run_tests 建立测试基线", "risk": "low", "verify": "记录当前测试结果"},
            {"step": "重构规划", "action": "确定重构策略和步骤顺序", "risk": "medium", "verify": "计划合理可回退"},
            {"step": "逐步重构", "action": "小步迭代，每步都运行测试", "risk": "high", "verify": "每步测试通过"},
            {"step": "最终验证", "action": "run_tests + complexity_report 对比改善", "risk": "low", "verify": "质量指标提升"},
        ],
        "testing": [
            {"step": "覆盖分析", "action": "确定当前测试覆盖 gap", "risk": "low", "verify": "识别未覆盖代码"},
            {"step": "用例设计", "action": "设计边界条件和异常路径测试", "risk": "low", "verify": "用例覆盖充分"},
            {"step": "生成测试", "action": "generate_tests 生成测试代码", "risk": "low", "verify": "测试代码可运行"},
            {"step": "运行验证", "action": "run_tests 执行并修复失败用例", "risk": "low", "verify": "全部测试通过"},
        ],
        "devops": [
            {"step": "环境分析", "action": "detect_project 获取项目配置信息", "risk": "low", "verify": "了解当前 CI/CD 状态"},
            {"step": "配置编写", "action": "编写 CI/CD 配置文件", "risk": "medium", "verify": "配置语法正确"},
            {"step": "本地验证", "action": "本地模拟测试 pipeline", "risk": "low", "verify": "本地测试通过"},
        ],
        "general": [
            {"step": "理解需求", "action": "明确任务目标和约束", "risk": "low", "verify": "需求理解准确"},
            {"step": "收集上下文", "action": "search_code + read_file 收集相关代码", "risk": "low", "verify": "上下文充分"},
            {"step": "制定方案", "action": "选择最优实现路径", "risk": "medium", "verify": "方案可行"},
            {"step": "执行实施", "action": "按计划修改代码", "risk": "medium", "verify": "功能实现正确"},
            {"step": "验证结果", "action": "测试和检查验证", "risk": "low", "verify": "任务完成"},
        ],
    }

    steps = templates.get(task_type, templates["general"])[:max_steps]

    # 添加依赖关系
    for i, step in enumerate(steps):
        step["id"] = i + 1
        step["depends_on"] = [i] if i > 0 else []

    # 检测项目上下文
    project_info = {}
    p = Path(project_path).resolve()
    if p.exists():
        has_tests = any(p.rglob("test_*.py")) or any(p.rglob("*_test.py")) or (p / "tests").exists()
        has_git = (p / ".git").exists()
        project_info = {"has_tests": has_tests, "has_git": has_git}

    return {
        "task_type": task_type,
        "task_description": task_description,
        "steps": steps,
        "total_steps": len(steps),
        "project_context": project_info,
        "hint": f"检测到任务类型: {task_type}，已生成 {len(steps)} 步执行计划",
    }
