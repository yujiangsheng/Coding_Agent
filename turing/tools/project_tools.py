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
    ci_files = [".github/workflows", ".gitlab-ci.yml", "Jenkinsfile", ".circleci",
                ".travis.yml", "azure-pipelines.yml"]
    for ci in ci_files:
        if (p / ci).exists():
            result["has_ci"] = True
            result["config_files"].append(ci)
            break

    # --- Docker ---
    if (p / "Dockerfile").exists() or (p / "docker-compose.yml").exists() or (p / "docker-compose.yaml").exists():
        result["has_docker"] = True

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
