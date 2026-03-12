"""Turing 智能体主循环

实现完整的 Agent Loop（v2.0）：

1. 接收用户输入
2. 从长期记忆 / 持久记忆中检索相关经验
3. 匹配策略模板，注入任务指导（策略预播种）
4. Chain-of-Thought 推理：复杂度评估 + 分层任务分解
5. 调用 LLM 生成响应（多 Provider 支持：Ollama / OpenAI / Anthropic / DeepSeek）
6. 解析并执行工具调用（只读并行 + 副作用顺序）
7. 语义错误分析 + 参数自动修正 + ETF 验证循环
8. 智能上下文管理（优先级滑动窗口 + 摘要折叠）
9. 任务完成后 LLM 深度反思，积累经验
10. 触发策略进化 / 知识蒸馏 / 十五维评分更新

事件流模型：chat() 方法是一个 Generator，通过 yield 产出
类型化事件字典（thinking / tool_call / tool_result / text /
reflection / done / error），方便 CLI / Web UI 流式渲染。

核心类::

    TuringAgent
        ├── chat(user_input) → Generator[dict]   # 主入口
        ├── start_session()                        # 初始化会话
        ├── save_conversation() / load_conversation()  # 会话持久化
        ├── _assess_and_plan()     # CoT 推理规划
        ├── _cot_decompose()       # LLM 结构化分解
        ├── _execute_parallel()    # 只读工具并发
        ├── _execute_with_retry()  # 重试 + 语义修正
        ├── _post_task_reflect()   # LLM 深度反思
        └── _check_context_overflow()  # 上下文管理
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Generator

_logger = logging.getLogger(__name__)

from turing.config import Config
from turing.prompt import SYSTEM_PROMPT, get_system_prompt
from turing.memory.manager import MemoryManager
from turing.rag.engine import RAGEngine
from turing.evolution.tracker import EvolutionTracker
from turing.evolution.metacognition import MetacognitiveEngine
from turing.llm import ModelRouter, create_provider
from turing.tools.registry import get_ollama_tool_schemas, execute_tool
from turing.safety import SafetyGuard, SandboxExecutor, Permission

# 注入全局工具依赖
from turing.tools import memory_tools, external_tools, evolution_tools, metacognition_tools, mcp_tools, agent_tools

# 确保所有工具被注册（import 即触发 @tool 装饰器）
import turing.tools.file_tools       # noqa: F401
import turing.tools.command_tools    # noqa: F401
import turing.tools.search_tools     # noqa: F401
import turing.tools.memory_tools     # noqa: F401
import turing.tools.external_tools   # noqa: F401
import turing.tools.evolution_tools  # noqa: F401
import turing.tools.git_tools        # noqa: F401
import turing.tools.test_tools       # noqa: F401
import turing.tools.quality_tools    # noqa: F401
import turing.tools.project_tools    # noqa: F401
import turing.tools.refactor_tools   # noqa: F401
import turing.tools.ast_tools       # noqa: F401
import turing.tools.metacognition_tools  # noqa: F401
import turing.tools.benchmark_tools       # noqa: F401
import turing.tools.mcp_tools             # noqa: F401
import turing.tools.agent_tools           # noqa: F401
import turing.tools.github_tools          # noqa: F401


class TuringAgent:
    """Turing 编程智能体

    完整的 Agent Loop，包含：
    - 记忆预加载
    - 多轮工具调用
    - 工作记忆管理
    - 任务后反思与经验积累
    """

    def __init__(self, config: Config | None = None):
        self.config = config or Config.load()
        self.model = self.config.get("model.name", "qwen3-coder:30b")
        self.temperature = self.config.get("model.temperature", 0.3)
        self.max_iterations = self.config.get("model.max_iterations", 50)
        self.stream_output = self.config.get("model.stream_output", True)
        data_dir = self.config.get("memory.data_dir", "turing_data")

        # ===== P0: 安全防护系统（对标 Claude Code 权限系统 + Devin 沙箱）=====
        sandbox_mode = self.config.get("security.sandbox_mode", "host")
        self.safety = SafetyGuard(
            mode=self.config.get("security.confirmation_mode", "interactive"),
            auto_approve=self.config.get("security.auto_approve", False),
        )
        self.sandbox = SandboxExecutor(
            mode=sandbox_mode,
            image=self.config.get("security.docker_image", "python:3.11-slim"),
            workspace_mount=self.config.get("security.workspace_root") or None,
        )

        # ===== 多 Provider LLM 路由（v2.0 — 对标 Claude Code / Cursor 的多模型支持）=====
        self.llm_router = self._init_llm_router()

        # 初始化子系统
        self.memory = MemoryManager(data_dir)
        self.rag = RAGEngine(data_dir)
        self.evolution = EvolutionTracker(data_dir, self.memory.persistent)
        self.metacognition = MetacognitiveEngine(data_dir)

        # 初始化评测系统
        from turing.benchmark.runner import BenchmarkRunner
        self.benchmark = BenchmarkRunner(self, data_dir=f"{data_dir}/benchmark")

        # 注入全局依赖到工具层
        memory_tools.set_memory_manager(self.memory)
        external_tools.set_rag_engine(self.rag)
        evolution_tools.set_evolution_tracker(self.evolution)
        metacognition_tools.set_metacognitive_engine(self.metacognition)

        from turing.tools import benchmark_tools
        benchmark_tools.set_benchmark_runner(self.benchmark)

        # v6.0: 注入 LLM Router 到 test_tools（供 _generate_smart_tests 使用）
        from turing.tools import test_tools as _test_tools_mod
        _test_tools_mod.set_llm_router(self.llm_router)

        # 注入 Agent 实例到子 Agent 工具
        agent_tools.set_agent_instance(self)

        # ===== MCP 集成（v2.1 — 对标 Claude Code 工具扩展协议）=====
        self.mcp = self._init_mcp()

        # 会话消息历史
        self._messages: list[dict] = []
        self._task_log: dict = {"actions": [], "outcome": None, "start_time": 0}
        self._initialized = False

        # Token 用量统计（v3.1）
        self._token_stats: dict = {
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "llm_calls": 0,
        }
        self._session_id: str | None = None
        self._data_dir = data_dir
        self._recent_tool_calls: list[str] = []  # 用于循环检测
        self._current_phase: str = "planning"     # 当前执行阶段
        self._etf_retry_count: int = 0             # ETF 循环重试计数
        self._error_history: list[dict] = []       # 错误历史（语义分析）
        self._allowed_tools: set | None = None      # 工具白名单（子 Agent 用）
        self._last_counted_msg_idx: int = 0          # token 增量统计游标（v6.0）

        # 验证工具注册完整性
        self._validate_tool_registration()

    def _init_llm_router(self) -> ModelRouter:
        """初始化多 Provider LLM 路由器

        支持三种配置模式：
        1. config.yaml 中有 llm.providers 配置 → 多 Provider 模式
        2. 环境变量 OPENAI_API_KEY / ANTHROPIC_API_KEY → 自动注册
        3. 默认 → 纯 Ollama 本地模式
        """
        import os
        raw_config = self.config._data

        # 模式 1：配置文件中已有 llm 块
        if "llm" in raw_config and "providers" in raw_config["llm"]:
            return ModelRouter(raw_config)

        # 模式 2：自动检测环境变量
        router = ModelRouter()
        # 始终注册 Ollama 作为基础 provider
        router.add_provider("ollama", create_provider(
            "ollama", model=self.model, context_length=self.config.get("model.context_length", 32768),
        ))
        router._default = "ollama"
        router._fallback_chain = ["ollama"]

        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            try:
                router.add_provider("openai", create_provider(
                    "openai", model="gpt-4o", api_key=openai_key, context_length=128000,
                ))
                router._fallback_chain.insert(0, "openai")
            except Exception:
                pass

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            try:
                router.add_provider("anthropic", create_provider(
                    "anthropic", model="claude-sonnet-4-20250514", api_key=anthropic_key,
                    context_length=200000,
                ))
                router._fallback_chain.insert(0, "anthropic")
            except Exception:
                pass

        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if deepseek_key:
            try:
                router.add_provider("deepseek", create_provider(
                    "deepseek", model="deepseek-chat", api_key=deepseek_key,
                    context_length=128000,
                ))
            except Exception:
                pass

        # 设置路由规则：复杂任务优先用强模型
        best = router._fallback_chain[0] if router._fallback_chain else "ollama"
        router._routing_rules = {
            "simple": "ollama",
            "medium": "ollama",
            "complex": best,
        }
        return router

    def _init_mcp(self):
        """初始化 MCP 集成

        从 config.yaml 的 mcp.servers 块加载 MCP 服务器配置，
        连接所有已启用的服务器，将外部工具注册到 Turing 工具注册表。

        配置示例::

            mcp:
              servers:
                filesystem:
                  transport: stdio
                  command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
                github:
                  transport: sse
                  url: http://localhost:3000
                  headers:
                    Authorization: "Bearer xxx"
        """
        from turing.mcp.manager import MCPManager

        manager = MCPManager()
        mcp_config = self.config.get("mcp.servers", {})
        if mcp_config:
            manager.load_from_config(mcp_config)
            results = manager.connect_all()
            for name, status in results.items():
                if "error" in status:
                    import warnings
                    warnings.warn(f"MCP 服务器 [{name}] 连接失败: {status}")

        # 注入 MCPManager 到 MCP 工具模块
        mcp_tools.set_mcp_manager(manager)
        return manager

    def start_session(self):
        """启动新会话"""
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._task_log = {"actions": [], "outcome": None, "start_time": time.time()}
        self._initialized = True
        self._recent_tool_calls = []
        self._current_phase = "planning"
        self._etf_retry_count = 0
        self._error_history = []

        # 自我演化：会话启动时自动检查并触发进化
        self._auto_evolve()

        # 自动索引项目结构（v2.0 — 对标 Cursor / Windsurf 的项目感知）
        self._auto_index_project()

        # P1: 自动加载项目规约文件（v3.2 — 对标 Claude Code CLAUDE.md / Copilot .instructions.md）
        self._load_project_spec()

        # P1: 加载项目级权限规则（v3.2 — 对标 Claude Code .claude/settings.json）
        self._load_project_rules()

    def _validate_tool_registration(self):
        """验证所有预期工具都已成功注册"""
        from turing.tools.registry import get_all_tools
        registered = {t.name for t in get_all_tools()}
        expected = {
            "read_file", "write_file", "edit_file", "generate_file",
            "multi_edit", "move_file", "copy_file", "delete_file", "find_files",
            "run_command", "run_background", "check_background", "stop_background",
            "search_code", "list_directory", "repo_map", "smart_context",
            "memory_read", "memory_write",
            "memory_reflect", "rag_search", "web_search", "fetch_url", "learn_from_ai_tool",
            "gap_analysis", "git_status", "git_diff", "git_log", "git_blame",
            "git_commit", "git_branch", "git_stash", "git_reset",
            "run_tests", "generate_tests", "lint_code", "format_code",
            "type_check", "detect_project", "analyze_dependencies",
            "batch_edit", "rename_symbol", "impact_analysis",
            "code_structure", "call_graph", "complexity_report",
            "metacognitive_profile", "metacognitive_advice",
            "synthesize_experiences", "cross_task_transfer",
            "self_diagnose", "cognitive_adapt",
            "recovery_advice", "recommend_tools",
            "run_self_training", "build_recovery_playbook",
            "run_benchmark", "eval_code", "benchmark_trend",
            "mcp_list_servers", "mcp_list_tools", "mcp_call_tool",
        }
        missing = expected - registered
        if missing:
            import warnings
            warnings.warn(f"Turing: 以下工具未成功注册: {missing}")

    def _auto_evolve(self):
        """会话启动时自动触发轻量级自我演化

        条件触发，避免每次启动都有开销：
        - 首次运行 → 执行自训练模拟器构建基础经验
        - 有足够 bootstrap 策略但经验不足时 → 合成经验
        - 有多类型经验时 → 触发跨任务知识迁移
        - 定期触发认知自适应和恢复剧本更新
        """
        try:
            stats = self.evolution.get_stats()
            task_count = stats.get("total_reflections", 0)

            # 首次运行或经验极少时执行自训练
            if task_count < 10:
                self.evolution.run_self_training()
            elif task_count < 30:
                # 经验不足时合成
                result = self.evolution.synthesize_experiences()
                if result.get("synthesized", 0) > 0:
                    self.evolution.cross_task_transfer()

            # 每 10 个任务触发一次认知自适应 + 恢复剧本更新
            if task_count > 0 and task_count % 10 == 0:
                self.metacognition.adapt()
                self.evolution.build_recovery_playbook()

            # 每 20 个任务或首次运行触发竞争力自评
            if task_count == 0 or (task_count > 0 and task_count % 20 == 0):
                from turing.evolution.competitive import CompetitiveIntelligence
                ci = CompetitiveIntelligence(
                    getattr(self.evolution, "_data_dir", "turing_data")
                )
                ci.analyze()
        except Exception:
            _logger.debug("自演化失败", exc_info=True)

    def _auto_index_project(self):
        """会话启动时自动索引项目结构（v3.1 — 按需上下文检索）

        仅注入轻量级项目摘要（顶层目录），实际代码上下文通过
        _inject_relevant_context() 在用户提问时按需检索。
        """
        try:
            from turing.tools.registry import execute_tool
            result = execute_tool("repo_map", {})
            repo_map = result.get("map", "") if isinstance(result, dict) else ""
            if repo_map and len(repo_map) > 50:
                # 只保留顶层结构摘要（≤1000 字符），避免占满上下文
                lines = repo_map.splitlines()
                summary_lines = [l for l in lines if l.count("/") <= 2 or l.count("│") <= 2]
                summary = "\n".join(summary_lines[:40])
                if len(summary) > 1000:
                    summary = summary[:1000] + "\n..."
                self._messages.append({
                    "role": "system",
                    "content": f"[项目结构摘要]\n{summary}",
                })
        except Exception:
            _logger.debug("项目索引失败", exc_info=True)

    def _load_project_spec(self):
        """自动加载项目规约文件（v3.2 — 对标 Claude Code 的 CLAUDE.md）

        按优先级搜索项目根目录中的规约文件：
        TURING.md > .turing.md > CLAUDE.md > AGENTS.md > .copilot-instructions.md
        找到后注入为 system 消息，让模型遵循项目级编码约定。
        """
        spec_files = [
            "TURING.md", ".turing.md", "CLAUDE.md",
            "AGENTS.md", ".copilot-instructions.md",
            ".github/copilot-instructions.md",
        ]
        workspace = self.config.get("security.workspace_root", ".")
        for fname in spec_files:
            spec_path = Path(workspace) / fname
            if spec_path.is_file():
                try:
                    content = spec_path.read_text(encoding="utf-8")[:4000]
                    self._messages.append({
                        "role": "system",
                        "content": (
                            f"[项目规约 — {fname}]\n"
                            "以下是本项目的编码约定和指令，请严格遵循：\n\n"
                            f"{content}"
                        ),
                    })
                except Exception:
                    pass
                break  # 只加载第一个找到的

    def _load_project_rules(self):
        """加载项目级安全/权限规则（v3.2 — 对标 Claude Code .claude/settings.json）

        支持 .turing-rules（YAML）定义项目级权限覆盖：
        - allow_tools: 始终允许的工具列表
        - deny_tools: 始终拒绝的工具列表
        - confirm_patterns: 需要确认的命令模式
        - auto_approve_paths: 自动批准的路径模式
        """
        import yaml as _yaml
        workspace = self.config.get("security.workspace_root", ".")
        rules_files = [".turing-rules", ".turing-rules.yaml", ".turing-rules.yml"]
        for fname in rules_files:
            rules_path = Path(workspace) / fname
            if rules_path.is_file():
                try:
                    rules = _yaml.safe_load(rules_path.read_text(encoding="utf-8")) or {}
                    # v10.0: 仅允许限制性规则，防止恶意仓库解除安全防护
                    safe_rules = {}
                    if "deny_tools" in rules and isinstance(rules["deny_tools"], list):
                        safe_rules["deny_tools"] = rules["deny_tools"]
                    if "confirm_patterns" in rules and isinstance(rules["confirm_patterns"], list):
                        safe_rules["confirm_patterns"] = rules["confirm_patterns"]
                    # 禁止 allow_tools / auto_approve_paths 等放行性规则
                    if safe_rules:
                        self.safety.load_project_rules(safe_rules)
                        _logger.info("已加载项目安全规则（仅限制性规则）: %s", fname)
                except Exception:
                    pass
                break

    def _inject_relevant_context(self, user_input: str):
        """按需检索与用户问题相关的代码上下文（v3.1 — 对标 Cursor / Windsurf）

        利用 RAG 引擎检索最相关的代码片段，仅在需要时注入，
        避免一次性灌入大量无关代码浪费上下文窗口。
        """
        try:
            # v10.0: RAG.search() 返回 {"results": [...], "count": N}，需取 results 列表
            rag_response = self.rag.search(user_input, top_k=5)
            items = rag_response.get("results", []) if isinstance(rag_response, dict) else []
            if items:
                snippets = []
                for r in items:
                    src = r.get("source_file", "?")
                    text = r.get("content", "")
                    if text and len(text.strip()) > 20:
                        snippets.append(f"## {src}\n```\n{text[:800]}\n```")
                if snippets:
                    context = "\n\n".join(snippets[:5])
                    self._messages.append({
                        "role": "system",
                        "content": f"[按需代码上下文 — 基于 RAG 检索]\n{context}",
                    })
                    return len(snippets)
        except Exception:
            _logger.debug("RAG 上下文注入失败", exc_info=True)
        return 0

    def _auto_collect_dependencies(self, user_input: str) -> int:
        """自动追踪用户提及文件的 import 依赖，注入结构摘要（v3.3）

        当用户提到具体文件路径时，自动分析该文件的 import 链，
        将直接依赖的模块结构摘要注入上下文，让 LLM 更好理解代码关系。
        对标 Cursor / Windsurf 的项目级上下文感知能力。
        """
        import ast as _ast
        import re as _re

        # 从用户输入中提取文件路径
        file_patterns = _re.findall(
            r'[\w./\-]+\.(?:py|js|ts|go|rs|java|jsx|tsx)', user_input
        )
        if not file_patterns:
            return 0

        workspace = Path(self.config.get("security.workspace_root", ".")).resolve()
        dep_summaries = []
        seen_deps = set()

        for fpath in file_patterns[:3]:  # 最多处理 3 个文件
            target = (workspace / fpath).resolve()
            # 安全: 必须在 workspace 内
            if not str(target).startswith(str(workspace) + "/") and target != workspace:
                continue
            if not target.is_file() or target.suffix != ".py":
                continue

            try:
                source = target.read_text(encoding="utf-8", errors="ignore")
                tree = _ast.parse(source)
            except Exception:
                continue

            # 提取 import 的本地模块
            for node in _ast.walk(tree):
                module = None
                if isinstance(node, _ast.Import):
                    for alias in node.names:
                        module = alias.name
                elif isinstance(node, _ast.ImportFrom) and node.module:
                    module = node.module

                if not module:
                    continue

                # 解析为文件路径
                parts = module.split(".")
                for base in [target.parent, workspace]:
                    candidate = base / "/".join(parts)
                    resolved = None
                    if candidate.with_suffix(".py").exists():
                        resolved = candidate.with_suffix(".py")
                    elif (candidate / "__init__.py").exists():
                        resolved = candidate / "__init__.py"
                    if resolved and resolved not in seen_deps:
                        seen_deps.add(resolved)
                        # 提取该依赖的轻量级结构摘要（类名 + 函数签名）
                        summary = self._extract_structure_summary(resolved)
                        if summary:
                            rel = str(resolved.relative_to(workspace))
                            dep_summaries.append(f"### {rel}\n{summary}")
                        break

                if len(dep_summaries) >= 8:
                    break
            if len(dep_summaries) >= 8:
                break

        if dep_summaries:
            context = "\n\n".join(dep_summaries[:8])
            self._messages.append({
                "role": "system",
                "content": f"[智能依赖上下文 — AST import 链自动追踪]\n{context}",
            })
        return len(dep_summaries)

    @staticmethod
    def _extract_structure_summary(filepath: Path) -> str:
        """提取文件的轻量级结构摘要（类名 + 函数签名），用于依赖上下文。"""
        import ast as _ast
        try:
            source = filepath.read_text(encoding="utf-8", errors="ignore")
            tree = _ast.parse(source)
        except Exception:
            return ""

        parts = []
        for node in _ast.iter_child_nodes(tree):
            if isinstance(node, _ast.ClassDef):
                methods = []
                for item in node.body:
                    if isinstance(item, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                        args = [a.arg for a in item.args.args if a.arg != "self"][:5]
                        methods.append(f"  def {item.name}({', '.join(args)})")
                parts.append(f"class {node.name}:\n" + "\n".join(methods[:8]))
            elif isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args if a.arg != "self"][:5]
                prefix = "async def" if isinstance(node, _ast.AsyncFunctionDef) else "def"
                parts.append(f"{prefix} {node.name}({', '.join(args)})")
        return "\n".join(parts[:15])  # 限制输出大小

    def _resolve_at_mentions(self, user_input: str) -> list[str]:
        """解析用户输入中的 @file / @folder 引用（v3.2 — 对标 Cursor @-mention 语法）

        支持格式：
        - @path/to/file.py — 注入文件完整内容
        - @path/to/folder/ — 注入目录结构
        - @docs — 搜索项目文档

        将引用的文件内容注入为 system 消息，返回已解析的文件路径列表。
        """
        import re as _re
        # 匹配 @后面的路径（非空白字符序列）
        mentions = _re.findall(r"@([\w./\-]+\.\w+|[\w./\-]+/)", user_input)
        if not mentions:
            return []

        workspace = Path(self.config.get("security.workspace_root", ".")).resolve()
        resolved = []
        snippets = []

        for mention in mentions[:5]:  # 限制最多 5 个引用
            target = (workspace / mention).resolve()
            # v8.0: 路径遍历防护 — 必须在 workspace 内
            if not str(target).startswith(str(workspace) + "/") and target != workspace:
                continue
            if target.is_file():
                try:
                    content = target.read_text(encoding="utf-8")[:5000]
                    snippets.append(f"## @{mention}\n```\n{content}\n```")
                    resolved.append(str(mention))
                except Exception:
                    pass
            elif target.is_dir():
                try:
                    entries = sorted(target.iterdir())[:30]
                    listing = "\n".join(
                        f"{'📁 ' if e.is_dir() else '📄 '}{e.name}"
                        for e in entries
                    )
                    snippets.append(f"## @{mention}\n{listing}")
                    resolved.append(str(mention))
                except Exception:
                    pass

        if snippets:
            self._messages.append({
                "role": "system",
                "content": f"[@-mention 引用的文件内容]\n\n" + "\n\n".join(snippets),
            })
        return resolved

    def chat(self, user_input: str) -> Generator[dict, None, None]:
        """处理一次用户输入，流式返回事件

        事件类型：
        - {"type": "thinking", "content": "..."}  思考过程
        - {"type": "tool_call", "name": "...", "args": {...}}  工具调用
        - {"type": "tool_result", "name": "...", "result": {...}}  工具结果
        - {"type": "text", "content": "..."}  文本回复
        - {"type": "reflection", "data": {...}}  反思结果
        - {"type": "done"}  完成
        - {"type": "error", "content": "..."}  错误
        """
        if not self._initialized:
            self.start_session()

        # ===== 阶段 -1：按任务类型精炼 System Prompt（v3.1 — 分段加载）=====
        detected_type = self._detect_task_type(user_input)
        if detected_type and detected_type != "general":
            refined_prompt = get_system_prompt(task_type=detected_type)
            if self._messages and self._messages[0].get("role") == "system":
                self._messages[0]["content"] = refined_prompt

        # ===== 阶段 0：记忆预加载 =====
        relevant_memories = self.memory.retrieve(
            query=user_input,
            layers=["long_term", "persistent"],
            top_k=5,
        )
        if relevant_memories:
            memory_context = self.memory.format_memories(relevant_memories)
            self._messages.append({
                "role": "system",
                "content": f"## 相关记忆（来自历史经验）\n{memory_context}",
            })
            yield {"type": "thinking", "content": f"检索到 {len(relevant_memories)} 条相关记忆"}

        # ===== 阶段 0.3：按需代码上下文检索（v3.1 — 替代全量 repo_map）=====
        n_ctx = self._inject_relevant_context(user_input)
        if n_ctx:
            yield {"type": "thinking", "content": f"按需检索到 {n_ctx} 个相关代码片段"}

        # ===== 阶段 0.32：智能依赖上下文（v3.3 — AST import 链自动追踪）=====
        n_deps = self._auto_collect_dependencies(user_input)
        if n_deps:
            yield {"type": "thinking", "content": f"自动追踪 {n_deps} 个依赖文件的结构"}

        # ===== 阶段 0.35：@-mention 上下文引用（v3.2 — 对标 Cursor @file 语法）=====
        at_refs = self._resolve_at_mentions(user_input)
        if at_refs:
            yield {"type": "thinking", "content": f"解析 @-mention 引用: {len(at_refs)} 个文件"}

        # ===== 阶段 0.5：策略注入 =====
        strategy_context = self._load_relevant_strategy(user_input)
        if strategy_context:
            self._messages.append({
                "role": "system",
                "content": strategy_context,
            })
            yield {"type": "thinking", "content": "已加载匹配的策略模板指导本次任务"}

        # ===== 阶段 0.55：工具推荐 =====
        try:
            tool_rec = self.evolution.recommend_tools(user_input)
            if tool_rec.get("primary_tools"):
                primary = ", ".join(t["tool"] for t in tool_rec["primary_tools"][:5])
                explore = ", ".join(tool_rec.get("explore_tools", [])[:3])
                hint = f"## 工具推荐\n推荐工具: {primary}"
                if explore:
                    hint += f"\n探索工具（从未使用，建议尝试）: {explore}"
                self._messages.append({"role": "system", "content": hint})
        except Exception:
            pass

        # ===== 阶段 0.6：元认知初始化 =====
        meta_init = self.metacognition.begin_task(user_input)
        if meta_init.get("recommended_depth") == "deep":
            yield {"type": "thinking", "content": f"元认知评估: 复杂度={meta_init['estimated_complexity']:.2f}, "
                   f"置信度={meta_init['initial_confidence']:.2f}, "
                   f"建议推理深度={meta_init['recommended_depth']}"}
        if meta_init.get("cognitive_advisory"):
            self._messages.append({
                "role": "system",
                "content": f"## 元认知建议\n{meta_init['cognitive_advisory']}",
            })

        # 存入工作记忆
        self.memory.write("working", f"用户请求: {user_input}", tags=["task_start"])

        # ===== 阶段 0.8：任务复杂度评估与规划 =====
        plan = self._assess_and_plan(user_input)
        if plan:
            self.memory.write("working", f"执行计划: {plan}", tags=["plan"])
            yield {"type": "thinking", "content": f"制定计划: {plan}"}

        # 添加用户消息
        self._messages.append({"role": "user", "content": user_input})

        # ===== 主循环 =====
        tool_schemas = get_ollama_tool_schemas()
        # 子 Agent 工具白名单过滤
        if self._allowed_tools is not None:
            tool_schemas = [s for s in tool_schemas
                           if s.get("function", {}).get("name") in self._allowed_tools]
        # 获取元认知估计的任务复杂度（用于模型路由）
        task_complexity = meta_init.get("estimated_complexity", 0.5)

        # 动态迭代上限：根据任务复杂度自适应调整（v3.1）
        if task_complexity < 0.3:
            effective_max_iter = min(self.max_iterations, 15)
        elif task_complexity < 0.7:
            effective_max_iter = min(self.max_iterations, 30)
        else:
            effective_max_iter = self.max_iterations

        for iteration in range(effective_max_iter):
            # 动态温度：根据执行阶段调整
            current_temp = self._get_dynamic_temperature()

            # v3.2: Architect-Editor 双模型路由
            # 规划阶段（首次迭代 + debugging）使用强模型，执行阶段使用快模型
            if iteration == 0 or self._current_phase == "debugging":
                iter_complexity = max(task_complexity, 0.8)  # 路由到 Architect 模型
            else:
                iter_complexity = min(task_complexity, 0.4)  # 路由到 Editor 模型

            try:
                if self.stream_output:
                    # 流式输出：通过 LLM Router 路由
                    msg = self._stream_chat(tool_schemas, temperature=current_temp,
                                            task_complexity=iter_complexity)
                    if msg is None:
                        yield {"type": "error", "content": "模型调用失败（流式）"}
                        return
                else:
                    msg = self.llm_router.chat(
                        messages=self._messages,
                        tools=tool_schemas if tool_schemas else None,
                        temperature=current_temp,
                        task_complexity=iter_complexity,
                    )
            except Exception as e:
                yield {"type": "error", "content": f"模型调用失败: {e}"}
                return

            # Token 用量统计（v3.1, v6.0: 增量计数避免 O(N²) 重编码）
            self._token_stats["llm_calls"] += 1
            try:
                import tiktoken
                enc = tiktoken.get_encoding("cl100k_base")
                # 只对新增消息估算输入 tokens（上次统计后的消息）
                new_msgs = self._messages[self._last_counted_msg_idx:]
                new_input_text = "".join(
                    m.get("content", "") or ""
                    for m in new_msgs
                    if isinstance(m.get("content"), str)
                )
                self._token_stats["total_input_tokens"] += len(enc.encode(new_input_text))
                self._last_counted_msg_idx = len(self._messages)
                # 估算输出 tokens
                out_text = msg.get("content", "") or ""
                self._token_stats["total_output_tokens"] += len(enc.encode(out_text))
            except Exception:
                pass

            # v3.2: 成本预算控制 — 超出 token 预算时提前终止
            token_budget = self.config.get("model.token_budget", 0)
            if token_budget and token_budget > 0:
                total_used = self._token_stats["total_input_tokens"] + self._token_stats["total_output_tokens"]
                if total_used > token_budget:
                    yield {"type": "text", "content": (
                        f"⚠️ Token 预算已耗尽 ({total_used:,}/{token_budget:,})，任务自动终止。\n"
                        "可通过 config.yaml 的 model.token_budget 调整预算上限。"
                    )}
                    self._task_log["outcome"] = "budget_exceeded"
                    yield {"type": "done", "token_stats": self.get_token_stats()}
                    return

            self._messages.append(msg)

            # 提取文本内容
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls", None)

            # 如果有文本输出
            if content:
                yield {"type": "text", "content": content}

            # 没有工具调用 → 任务完成
            if not tool_calls:
                self._task_log["outcome"] = "success"
                # 反思
                reflection = self._post_task_reflect(user_input)
                if reflection:
                    yield {"type": "reflection", "data": reflection}
                yield {"type": "done", "token_stats": self.get_token_stats()}
                return

            # 执行工具调用（支持并行执行只读工具）
            parallel_calls, sequential_calls = self._classify_tool_calls(tool_calls)

            # 并行执行只读工具
            if len(parallel_calls) > 1:
                parallel_results = self._execute_parallel(parallel_calls)
                for tc, result in parallel_results:
                    func = tc.get("function", {})
                    tool_name = func.get("name", "")
                    tool_args = func.get("arguments", {})

                    yield {"type": "tool_call", "name": tool_name, "args": tool_args}
                    yield {"type": "tool_result", "name": tool_name, "result": result}

                    self._task_log["actions"].append({
                        "tool": tool_name, "args": tool_args,
                        "iteration": iteration,
                        "success": "error" not in result,
                    })

                    result_str = json.dumps(result, ensure_ascii=False, default=str)
                    if len(result_str) > 15000:
                        result_str = self._summarize_tool_result(tool_name, result_str)
                    self._messages.append({"role": "tool", "content": result_str})
            elif parallel_calls:
                # 单个只读调用，按顺序执行
                sequential_calls = parallel_calls + sequential_calls

            # 顺序执行有副作用的工具
            for tc in sequential_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                tool_args = func.get("arguments", {})

                # 循环检测：连续重复相同调用则中断
                call_sig = f"{tool_name}:{json.dumps(tool_args, sort_keys=True, default=str)}"
                self._recent_tool_calls.append(call_sig)
                if len(self._recent_tool_calls) > 3:
                    last_3 = self._recent_tool_calls[-3:]
                    if len(set(last_3)) == 1:
                        yield {"type": "text", "content": "检测到重复工具调用循环，已自动中断。"}
                        self._task_log["outcome"] = "loop_detected"
                        yield {"type": "done", "token_stats": self.get_token_stats()}
                        return
                # 保留最近 10 个调用签名
                self._recent_tool_calls = self._recent_tool_calls[-10:]

                yield {"type": "tool_call", "name": tool_name, "args": tool_args}

                # ===== P0: 安全确认检查 =====
                perm, perm_msg = self.safety.check_permission(tool_name, tool_args)
                if perm == Permission.DENY:
                    result = {"error": f"安全策略拒绝执行: {perm_msg}"}
                    yield {"type": "tool_result", "name": tool_name, "result": result}
                    continue
                if perm == Permission.CONFIRM:
                    approved = self.safety.request_confirmation(
                        tool_name, tool_args, perm_msg
                    )
                    if not approved:
                        result = {"error": "用户拒绝执行该操作"}
                        yield {"type": "tool_result", "name": tool_name, "result": result}
                        self._messages.append({"role": "tool", "content": json.dumps(result, ensure_ascii=False)})
                        continue

                # 元认知检查点：工具选择监控
                self.metacognition.checkpoint("tool_selection", {
                    "tool": tool_name, "args": tool_args,
                    "iteration": iteration,
                })

                # 执行（含自动重试 + 语义错误分析）
                result = self._execute_with_retry(tool_name, tool_args)

                # 语义错误分析：检测错误模式并切换阶段
                if "error" in result:
                    self._error_history.append({
                        "tool": tool_name, "error": result["error"],
                        "iteration": iteration,
                    })
                    # 元认知检查点：错误监控
                    meta_reg = self.metacognition.checkpoint("error_encountered", {
                        "error": result["error"], "tool": tool_name,
                        "retry_count": len(self._error_history),
                    })
                    if meta_reg and meta_reg.get("regulations"):
                        for reg in meta_reg["regulations"]:
                            if reg.get("action") == "debias":
                                self._messages.append({
                                    "role": "system",
                                    "content": f"## 元认知纠偏\n{reg['suggestion']}",
                                })
                                yield {"type": "thinking", "content": f"元认知偏差检测: {reg['reason']}"}
                    # 连续错误 → 切换到 debugging 阶段
                    if len(self._error_history) >= 2:
                        self._current_phase = "debugging"
                        error_analysis = self._analyze_error_pattern()
                        if error_analysis:
                            self._messages.append({
                                "role": "system",
                                "content": f"## 错误模式分析\n{error_analysis}\n请基于上述分析调整方案。",
                            })
                            yield {"type": "thinking", "content": f"错误分析: {error_analysis}"}

                        # 失败恢复引擎：获取恢复建议
                        recovery = self.evolution.get_recovery_advice(
                            result.get("error", ""), tool_name
                        )
                        if recovery.get("advice"):
                            self._messages.append({
                                "role": "system",
                                "content": f"## 失败恢复建议\n{recovery['advice']}",
                            })
                            yield {"type": "thinking", "content": f"恢复建议: {recovery['error_category']}"}
                else:
                    # 成功后清除错误历史并切换回 execution 阶段
                    self._error_history = []
                    self._current_phase = "execution"

                    # ETF 循环跟踪：编辑操作后检测是否需要验证
                    if tool_name in ("edit_file", "write_file", "generate_file", "batch_edit"):
                        self._etf_retry_count = 0

                        # === Auto-Commit（对标 Aider 自动提交，支持 undo）===
                        self._auto_checkpoint(tool_name, tool_args)

                        # === ETF 三重验证（v3.2 — 对标 Claude Code 编辑后自动质量检查）===
                        edited_path = result.get("path", tool_args.get("path", ""))
                        if edited_path and edited_path.endswith(".py"):
                            # 1) Auto Lint-Fix
                            lint_result = self._auto_lint_fix(edited_path)
                            if lint_result:
                                yield {"type": "tool_result", "name": "auto_lint_fix", "result": lint_result}
                            # 2) Auto Type-Check
                            type_result = self._auto_type_check(edited_path)
                            if type_result:
                                yield {"type": "tool_result", "name": "auto_type_check", "result": type_result}

                        # 注入 ETF 提示（含三重验证指引）
                        if not any("请运行测试或验证" in m.get("content", "") for m in self._messages[-3:]):
                            etf_hints = ["代码已修改。请执行 ETF 三重验证循环："]
                            etf_hints.append("1. run_tests 运行相关测试")
                            etf_hints.append("2. 检查 lint 和类型检查结果")
                            etf_hints.append("3. 如果任何步骤失败，分析原因并修复后重新验证")
                            self._messages.append({
                                "role": "system",
                                "content": "\n".join(etf_hints),
                            })

                yield {"type": "tool_result", "name": tool_name, "result": result}

                self._task_log["actions"].append({
                    "tool": tool_name,
                    "args": tool_args,
                    "iteration": iteration,
                    "success": "error" not in result,
                })

                # 将结果反馈给模型（大输出自动摘要）
                result_str = json.dumps(result, ensure_ascii=False, default=str)
                if len(result_str) > 15000:
                    result_str = self._summarize_tool_result(tool_name, result_str)
                self._messages.append({
                    "role": "tool",
                    "content": result_str,
                })

            # 元认知中期检查
            if iteration > 0 and iteration % 3 == 0:
                meta_mid = self.metacognition.checkpoint("mid_task_review", {
                    "iteration": iteration,
                    "progress": f"{len(self._task_log['actions'])} actions done",
                })
                if meta_mid and meta_mid.get("regulations"):
                    for reg in meta_mid["regulations"]:
                        if reg.get("action") in ("decompose_task", "increase_verification"):
                            self._messages.append({
                                "role": "system",
                                "content": f"## 元认知调控\n{reg['suggestion']}",
                            })

            # 工作记忆容量检查
            self._check_context_overflow()

        # 超过最大迭代
        self._task_log["outcome"] = "max_iterations_reached"
        reflection = self._post_task_reflect(user_input)
        if reflection:
            yield {"type": "reflection", "data": reflection}
        yield {"type": "text", "content": f"已达到最大迭代次数（{self.max_iterations}），任务可能未完全完成。"}
        yield {"type": "done", "token_stats": self.get_token_stats()}

    def _post_task_reflect(self, user_request: str) -> dict | None:
        """任务后自动反思 —— 使用 LLM 进行深度反思"""
        try:
            mechanical = {
                "task": user_request,
                "outcome": self._task_log.get("outcome", "unknown"),
                "actions_count": len(self._task_log["actions"]),
                "tools_used": list(set(
                    a["tool"] for a in self._task_log["actions"]
                )),
            }

            # ===== LLM 深度反思 =====
            llm_reflection = self._llm_reflect(user_request, mechanical)
            if llm_reflection:
                mechanical["lessons"] = llm_reflection.get("lessons", "")
                mechanical["what_went_well"] = llm_reflection.get("what_went_well", "")
                mechanical["what_could_improve"] = llm_reflection.get("what_could_improve", "")
                mechanical["task_type"] = llm_reflection.get("task_type", "general")

            # 写入长期记忆
            self.memory.write(
                "long_term",
                json.dumps(mechanical, ensure_ascii=False),
                tags=["task_reflection", mechanical["outcome"]],
            )

            # 记录到演化追踪器
            self.evolution.add_reflection(mechanical)

            # 检查策略进化
            self.evolution.check_strategy_evolution(mechanical)

            # 检查知识蒸馏
            self.evolution.check_distillation()

            # 元认知任务结束评估
            meta_assessment = self.metacognition.end_task(
                outcome=mechanical["outcome"],
                reflection=mechanical,
            )
            if meta_assessment and "metacognitive_quality" in meta_assessment:
                mechanical["metacognitive_quality"] = meta_assessment["metacognitive_quality"]
                mechanical["meta_lessons"] = meta_assessment.get("lessons_meta", [])

            return mechanical
        except Exception:
            return None

    def _llm_reflect(self, user_request: str, mechanical: dict) -> dict | None:
        """调用 LLM 对任务执行过程进行深度反思（Phase 4 增强版）

        增强维度：
        - 工具选择质量评估
        - 推理链质量自评
        - 可复用经验提取
        """
        reflect_temp = self.config.get("model.reflect_temperature", 0.6)
        tools_used = ", ".join(mechanical.get("tools_used", []))
        outcome = mechanical.get("outcome", "unknown")
        actions_count = mechanical.get("actions_count", 0)
        elapsed = time.time() - self._task_log.get("start_time", time.time())

        # 收集错误历史用于反思
        error_summary = ""
        if self._error_history:
            error_summary = f"\n- 执行过程中遇到 {len(self._error_history)} 个错误"

        # 收集元认知信息
        meta_summary = ""
        if self.metacognition._current:
            state = self.metacognition._current
            meta_summary = (
                f"\n- 元认知信号: 置信度={state.confidence:.2f}, "
                f"认知负荷={state.cognitive_load:.2f}, "
                f"策略切换={state.strategy_switches}次, "
                f"偏差警报={len(state.bias_alerts)}个"
            )
            if state.bias_alerts:
                meta_summary += f"\n- 检测到偏差: {', '.join(state.bias_alerts[:3])}"

        reflect_prompt = (
            f"你刚完成了一个编程任务，请进行深度反思。\n"
            f"- 任务: {user_request}\n"
            f"- 结果: {outcome}\n"
            f"- 使用的工具: {tools_used}\n"
            f"- 工具调用次数: {actions_count}\n"
            f"- 耗时: {elapsed:.1f}s{error_summary}{meta_summary}\n\n"
            f"请用 JSON 格式回答（不要用 markdown 代码块，直接输出 JSON）：\n"
            f'{{"task_type": "bug_fix/feature/refactor/debug/explain/general 之一",'
            f' "lessons": "一句话总结可复用的经验教训",'
            f' "what_went_well": "做得好的地方",'
            f' "what_could_improve": "可以改进的地方",'
            f' "tool_selection_quality": "good/adequate/poor",'
            f' "reasoning_depth": "deep/medium/shallow",'
            f' "cognitive_bias_detected": "如果有认知偏差，描述之，否则填 null",'
            f' "confidence_trajectory": "overconfident/calibrated/underconfident",'
            f' "adaptation_quality": "是否及时根据情况调整了策略，good/adequate/poor",'
            f' "reusable_pattern": "如果有可复用的解题模式，描述之，否则填 null"}}'
        )

        # 最多重试 2 次（v8.0: 增加超时防护）
        import concurrent.futures as _cf
        _REFLECT_TIMEOUT = 30  # 秒

        for attempt in range(2):
            try:
                with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
                    _fut = _pool.submit(
                        self.llm_router.chat,
                        messages=[
                            {"role": "system", "content": "你是一个善于自我反思的编程智能体。输出纯 JSON。"},
                            {"role": "user", "content": reflect_prompt},
                        ],
                        temperature=reflect_temp,
                        task_complexity=0.3,
                    )
                    resp = _fut.result(timeout=_REFLECT_TIMEOUT)
                content = resp.get("content", "")
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                # 尝试从内容中提取第一个 JSON 对象
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    content = content[start:end]
                return json.loads(content)
            except json.JSONDecodeError:
                continue  # 重试
            except Exception:
                break  # 不可恢复错误，不重试

        # 回退到机械式反思
        return {
            "task_type": "general",
            "lessons": f"完成了 {outcome} 的任务，使用了 {tools_used}",
            "what_went_well": "任务完成" if outcome == "success" else "",
            "what_could_improve": "反思 LLM 调用失败，需检查模型连接",
        }

    def _detect_task_type(self, user_input: str) -> str:
        """根据用户输入快速检测任务类型，用于 System Prompt 分段加载"""
        input_lower = user_input.lower()
        type_keywords = {
            "bug_fix": ["bug", "fix", "修复", "报错", "error", "crash", "异常"],
            "feature": ["feature", "功能", "新增", "添加", "implement", "实现", "开发"],
            "refactor": ["refactor", "重构", "优化", "clean", "改进", "性能"],
            "debug": ["debug", "调试", "排查", "排错", "定位", "timeout", "超时"],
            "explain": ["explain", "解释", "什么是", "原理", "how does", "为什么"],
            "test": ["test", "测试", "coverage", "覆盖率", "unittest", "pytest"],
            "review": ["review", "审查", "code review", "代码审查", "pr"],
        }
        for task_type, keywords in type_keywords.items():
            if any(k in input_lower for k in keywords):
                return task_type
        return "general"

    def _load_relevant_strategy(self, user_input: str) -> str | None:
        """根据用户输入的任务描述，加载匹配的已进化策略模板"""
        strategies = self.memory.persistent.list_strategies()
        if not strategies:
            return None

        # 用关键词匹配任务类型
        input_lower = user_input.lower()
        type_keywords = {
            "bug_fix": ["bug", "fix", "修复", "报错", "error", "crash", "异常"],
            "feature": ["feature", "功能", "新增", "添加", "implement", "实现", "开发"],
            "refactor": ["refactor", "重构", "优化", "clean", "改进", "性能"],
            "debug": ["debug", "调试", "排查", "排错", "定位", "timeout", "超时"],
            "explain": ["explain", "解释", "什么是", "原理", "how does", "为什么"],
        }

        matched_type = None
        for task_type, keywords in type_keywords.items():
            if task_type in strategies and any(k in input_lower for k in keywords):
                matched_type = task_type
                break

        if not matched_type:
            return None

        strategy = self.memory.persistent.load_strategy(matched_type)
        if not strategy:
            return None

        # 格式化策略为 prompt 注入文本
        lines = [f"## 策略模板（{matched_type}，基于 {strategy.get('total_experiences', 0)} 条历史经验）"]
        lines.append(f"历史成功率: {strategy.get('success_rate', 0):.0%}")

        tools = strategy.get("recommended_tools", [])
        if tools:
            lines.append(f"推荐工具: {', '.join(tools)}")

        steps = strategy.get("recommended_steps", [])
        if steps:
            lines.append("推荐步骤:")
            for i, s in enumerate(steps, 1):
                lines.append(f"  {i}. {s}")

        lessons = strategy.get("key_lessons", [])
        if lessons:
            lines.append("核心经验:")
            for l in lessons[-5:]:
                lines.append(f"  - {l}")

        pitfalls = strategy.get("common_pitfalls", [])
        if pitfalls:
            lines.append("常见陷阱（注意避免）:")
            for p in pitfalls:
                lines.append(f"  ⚠️ {p}")

        # Phase 2: 注入工具路由建议
        routing = strategy.get("tool_routing", {})
        if routing:
            lines.append("推荐工具路由:")
            for phase, phase_tools in routing.items():
                if isinstance(phase_tools, list):
                    lines.append(f"  {phase}: {', '.join(phase_tools)}")

        # Phase 2: 注入验证工具建议
        verification = strategy.get("verification_tools", [])
        if verification:
            lines.append(f"验证工具: {', '.join(verification)}")

        return "\n".join(lines)

    def _assess_and_plan(self, user_input: str) -> str | None:
        """使用 LLM 进行 Chain-of-Thought 推理和分层任务分解

        对标 Claude Opus 的深度推理链：
        - 简单任务：快速关键词匹配生成简要计划
        - 复杂任务：调用 LLM 进行结构化推理和分解
        """
        input_lower = user_input.lower()

        # 简单任务快速通道
        simple_signals = [
            "解释", "explain", "什么是", "what is", "查看", "show", "读",
            "hello", "hi", "你好", "帮我看看",
        ]
        if any(s in input_lower for s in simple_signals) and len(user_input) < 60:
            self._current_phase = "execution"
            return None

        # 复杂度评估信号
        complex_signals = [
            "重构", "refactor", "批量", "batch", "多个文件", "multiple files",
            "架构", "architecture", "迁移", "migrate", "全部", "all",
            "设计", "design", "实现", "implement", "系统", "system",
        ]
        is_complex = any(s in input_lower for s in complex_signals) or len(user_input) > 120

        if is_complex:
            # 使用 LLM 进行 Chain-of-Thought 推理分解
            self._current_phase = "planning"
            plan = self._cot_decompose(user_input)
            if plan:
                return plan

        # 中等复杂度任务
        if len(user_input) > 60:
            self._current_phase = "execution"
            return "中等任务 → 1) 理解需求 2) 定位代码 3) 实施修改 4) 验证（ETF循环）"

        self._current_phase = "execution"
        return None

    def _cot_decompose(self, user_input: str) -> str | None:
        """Chain-of-Thought 分层任务分解（对标 Claude Opus 深度推理）

        通过 LLM 进行结构化推理，将复杂任务拆解为可执行子步骤。
        """
        reflect_temp = self.config.get("model.reflect_temperature", 0.6)
        cot_prompt = (
            "你是一个任务规划专家。请对以下编程任务进行 Chain-of-Thought 推理分析。\n\n"
            f"任务: {user_input}\n\n"
            "请用以下结构（纯文本，不要 JSON/Markdown）进行分析：\n\n"
            "【问题分解】将任务拆分为 3-7 个原子子任务，标注依赖关系\n"
            "【风险评估】可能引入的 bug 和跨文件影响\n"
            "【方案选择】最优实现方案及理由\n"
            "【验证计划】每步完成后的验证方法\n"
            "【执行顺序】按依赖关系排列的步骤序列\n\n"
            "注意：简洁输出，每段不超过 3 行。"
        )
        try:
            # v9.0: ThreadPoolExecutor + 30s timeout 防止 LLM 无限等待
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
            def _do_cot():
                return self.llm_router.chat(
                    messages=[
                        {"role": "system", "content": "你是一个编程任务规划专家。输出简洁的分析。"},
                        {"role": "user", "content": cot_prompt},
                    ],
                    temperature=reflect_temp,
                    task_complexity=0.3,
                )
            with ThreadPoolExecutor(max_workers=1) as pool:
                resp = pool.submit(_do_cot).result(timeout=30)
            content = resp.get("content", "").strip()
            if content and len(content) > 20:
                self._current_phase = "execution"
                # 截取关键部分避免过长
                if len(content) > 800:
                    content = content[:800] + "..."
                return f"[CoT推理] {content}"
        except Exception:
            pass

        self._current_phase = "execution"
        return (
            "复杂任务 → 1) 搜索理解全貌 2) 分析跨文件影响 "
            "3) 制定分步计划 4) 逐步执行并验证（ETF循环）5) 回归测试"
        )

    def _get_dynamic_temperature(self) -> float:
        """根据当前执行阶段动态调整温度（对标 Claude/Codex 的自适应策略）

        - planning 阶段：较高温度以产生更多方案
        - execution 阶段：较低温度以保证代码准确
        - debugging 阶段：中等温度以平衡创意和准确性
        - reflection 阶段：较高温度以产生深度洞察
        """
        phase_temperatures = {
            "planning": min(self.temperature + 0.3, 0.8),
            "execution": self.temperature,
            "debugging": min(self.temperature + 0.15, 0.6),
            "reflection": self.config.get("model.reflect_temperature", 0.6),
        }
        return phase_temperatures.get(self._current_phase, self.temperature)

    # ===== Phase 8: 并行工具执行 =====

    # 只读工具集合：可安全并行执行
    _READONLY_TOOLS = frozenset({
        "read_file", "search_code", "list_directory", "repo_map", "smart_context",
        "find_files", "memory_read", "check_background",
        "rag_search", "web_search", "git_status", "git_diff", "git_log",
        "git_blame", "detect_project", "analyze_dependencies",
        "impact_analysis", "code_structure", "call_graph",
        "complexity_report", "gap_analysis",
        "mcp_list_servers", "mcp_list_tools",
    })

    def _classify_tool_calls(self, tool_calls: list[dict]) -> tuple[list, list]:
        """将工具调用分为可并行的只读调用和必须顺序的副作用调用"""
        parallel = []
        sequential = []
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "")
            if name in self._READONLY_TOOLS:
                parallel.append(tc)
            else:
                sequential.append(tc)
        return parallel, sequential

    def _execute_parallel(self, tool_calls: list[dict]) -> list[tuple[dict, dict]]:
        """并行执行多个只读工具调用（对标 Codex/Claude 的并发执行能力）

        使用 ThreadPoolExecutor 并行执行独立的只读操作，
        显著减少多文件读取、搜索等场景的延迟。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _run_one(tc):
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", {})
            result = self._execute_with_retry(name, args)
            return (tc, result)

        results = []
        max_workers = min(len(tool_calls), 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_one, tc): tc for tc in tool_calls}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    tc = futures[future]
                    results.append((tc, {"error": f"并行执行异常: {e}"}))

        # 按原始顺序排列结果
        order = {id(tc): i for i, tc in enumerate(tool_calls)}
        results.sort(key=lambda x: order.get(id(x[0]), 0))
        return results

    def _execute_with_retry(self, tool_name: str, tool_args: dict, max_retries: int = 1) -> dict:
        """执行工具调用，支持自动重试 + 语义错误分析

        对于超时和临时错误自动重试一次。
        对于语义错误，尝试智能修正参数。
        """
        for attempt in range(max_retries + 1):
            result = execute_tool(tool_name, tool_args)
            if "error" not in result:
                return result
            err = result.get("error", "")

            # 可重试的错误类型
            retryable = ("超时" in err or "timeout" in err.lower() or "临时" in err)
            if retryable and attempt < max_retries:
                if "timeout" in tool_name or tool_name == "run_command":
                    tool_args["timeout"] = tool_args.get("timeout", 30) * 2
                continue

            # 语义错误自动修正（对标 Claude 的智能参数调整）
            if attempt < max_retries:
                corrected = self._try_auto_correct(tool_name, tool_args, err)
                if corrected:
                    tool_args = corrected
                    continue

            break
        return result

    def _try_auto_correct(self, tool_name: str, tool_args: dict, error: str) -> dict | None:
        """尝试自动修正工具调用参数（语义错误恢复）"""
        # 常见的路径错误修正
        if tool_name in ("read_file", "edit_file") and "文件不存在" in error:
            path = tool_args.get("path", "")
            # 尝试去除多余的目录前缀
            import os
            basename = os.path.basename(path)
            if basename != path:
                # 搜索文件实际位置
                try:
                    import subprocess
                    result = subprocess.run(
                        ["find", ".", "-name", basename, "-type", "f"],
                        capture_output=True, text=True, timeout=5
                    )
                    found = result.stdout.strip().split("\n")
                    if found and found[0]:
                        corrected = {**tool_args, "path": found[0]}
                        return corrected
                except Exception:
                    pass

        # edit_file 匹配失败时的空白修正
        if tool_name == "edit_file" and "未找到 old_str" in error:
            old_str = tool_args.get("old_str", "")
            # 尝试规范化空白
            normalized = " ".join(old_str.split())
            if normalized != old_str:
                return {**tool_args, "old_str": normalized}

        return None

    def _auto_lint_fix(self, filepath: str) -> dict | None:
        """编辑后自动运行 lint 并修复（对标 Aider 的 auto-lint-fix）

        静默修复风格问题，如果有不能自动修复的问题则报告。
        """
        import subprocess
        import shutil

        # 只在有 ruff/flake8 时执行
        linter = shutil.which("ruff") or shutil.which("flake8")
        if not linter:
            return None

        linter_name = Path(linter).name
        try:
            if linter_name == "ruff":
                # Ruff: 先自动修复，再检查残留
                subprocess.run(
                    [linter, "check", "--fix", "--quiet", filepath],
                    capture_output=True, text=True, timeout=15,
                )
                check = subprocess.run(
                    [linter, "check", "--quiet", filepath],
                    capture_output=True, text=True, timeout=15,
                )
                if check.returncode == 0:
                    return {"auto_lint": "ok", "linter": "ruff", "file": filepath}
                remaining = check.stdout.strip().split("\n")
                return {
                    "auto_lint": "partial",
                    "linter": "ruff",
                    "auto_fixed": True,
                    "remaining_issues": len(remaining),
                    "details": "\n".join(remaining[:10]),
                }
            else:
                # flake8: 只检查（无自动修复）
                check = subprocess.run(
                    [linter, filepath],
                    capture_output=True, text=True, timeout=15,
                )
                if check.returncode == 0:
                    return {"auto_lint": "ok", "linter": "flake8", "file": filepath}
                issues = check.stdout.strip().split("\n")
                return {
                    "auto_lint": "issues_found",
                    "linter": "flake8",
                    "count": len(issues),
                    "details": "\n".join(issues[:10]),
                }
        except Exception:
            return None

    def _auto_type_check(self, filepath: str) -> dict | None:
        """编辑后自动运行类型检查（v3.2 — ETF 三重验证之二）

        静默运行 mypy/pyright 检查类型错误，信息反馈给模型以便修复。
        """
        import subprocess
        import shutil

        checker = shutil.which("mypy") or shutil.which("pyright")
        if not checker:
            return None

        checker_name = Path(checker).name
        try:
            check = subprocess.run(
                [checker, filepath, "--no-error-summary"] if checker_name == "mypy"
                else [checker, filepath],
                capture_output=True, text=True, timeout=30,
            )
            if check.returncode == 0:
                return {"auto_type_check": "ok", "checker": checker_name, "file": filepath}

            issues = check.stdout.strip().split("\n")
            return {
                "auto_type_check": "issues_found",
                "checker": checker_name,
                "count": len(issues),
                "details": "\n".join(issues[:10]),
            }
        except Exception:
            return None

    def _auto_checkpoint(self, tool_name: str, tool_args: dict):
        """每次编辑后自动 git 提交（对标 Aider 的 auto-commit + /undo）

        让每次编辑后可以通过 git_reset 精确回退到任意步骤。
        """
        import subprocess
        # 检查是否在 git 仓库内
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                return  # 不在 git 仓库中，跳过
        except Exception:
            return

        edited_path = tool_args.get("path", "")
        if not edited_path or edited_path == "unknown":
            return
        try:
            subprocess.run(["git", "add", "--", edited_path], capture_output=True, timeout=5)
            subprocess.run(
                ["git", "commit", "-m",
                 f"turing: {tool_name} on {Path(edited_path).name}",
                 "--allow-empty"],
                capture_output=True, timeout=5,
            )
        except Exception:
            _logger.debug("自动 git 提交失败", exc_info=True)

    def undo(self, steps: int = 1) -> dict:
        """撤销最近的编辑操作（对标 Aider /undo）

        通过 git reset --soft 回退最近 N 个 auto-checkpoint 提交。
        """
        from turing.tools.git_tools import git_reset
        return git_reset(count=steps, hard=False)

    def _analyze_error_pattern(self) -> str | None:
        """分析连续错误的模式，提供改进建议（对标 Claude 的语义错误分析）"""
        if len(self._error_history) < 2:
            return None

        recent = self._error_history[-5:]
        errors = [e["error"] for e in recent]
        tools = [e["tool"] for e in recent]

        # 检测常见错误模式
        if all("文件不存在" in e for e in errors):
            return "多次文件路径错误。建议：先用 list_directory 确认文件结构，再操作。"

        if all("未找到 old_str" in e for e in errors):
            return "多次编辑匹配失败。建议：先用 read_file 获取最新文件内容，确保 old_str 精确匹配。"

        if all("超时" in e or "timeout" in e.lower() for e in errors):
            return "多次执行超时。建议：拆分为更小的操作，或增加超时时间。"

        if len(set(tools)) == 1:
            return f"工具 {tools[0]} 连续失败。建议：换用替代工具或重新评估方案。"

        if len(recent) >= 3:
            return ("连续多次操作失败。建议：退一步重新分析问题，"
                    "检查假设是否正确，考虑替代方案。")

        return None

    def _summarize_tool_result(self, tool_name: str, result_str: str) -> str:
        """语义压缩工具结果（v3.5 — 增强型内容感知压缩）

        对不同工具使用不同的压缩策略，保留语义关键信息。
        v3.5 新增：AST/结构化输出保留签名、依赖图保留拓扑、自动修复保留 diff。
        """
        max_len = 12000
        if len(result_str) <= max_len:
            return result_str

        # 对不同工具使用不同压缩策略
        if tool_name in ("search_code", "list_directory"):
            # 搜索结果：保留前部分（最相关）+ 统计摘要
            lines = result_str.split("\n")
            total_matches = len([l for l in lines if l.strip()])
            kept = "\n".join(lines[:100])
            return (f"{kept}\n\n...(总计约 {total_matches} 条结果，"
                    f"已展示前 100 条，完整结果已截断)...")

        elif tool_name == "read_file":
            # 文件内容：保留开头（导入+声明）+ 搜索上下文附近 + 结尾
            return result_str[:5000] + "\n...(文件中部省略)...\n" + result_str[-4000:]

        elif tool_name in ("run_command", "run_tests", "auto_fix"):
            # 命令/测试/自动修复输出：保留错误信息和结尾摘要
            lines = result_str.split("\n")
            error_lines = [l for l in lines if any(
                kw in l.lower() for kw in ["error", "fail", "traceback", "exception", "错误"]
            )]
            if error_lines:
                error_context = "\n".join(error_lines[:30])
                tail = "\n".join(lines[-20:])
                return (f"[关键错误信息]\n{error_context}\n\n"
                        f"[输出尾部]\n{tail}")
            return result_str[:6000] + "\n...(截断)...\n" + result_str[-4000:]

        elif tool_name in ("git_diff", "git_log", "pr_summary"):
            # Git 输出：保留文件变更摘要 + 关键差异
            return result_str[:8000] + "\n...(截断)...\n" + result_str[-3000:]

        elif tool_name in ("code_structure", "call_graph", "dependency_graph"):
            # AST/结构化输出：保留签名列表和拓扑摘要
            lines = result_str.split("\n")
            sig_lines = [l for l in lines if any(
                kw in l for kw in ["def ", "class ", "→", "->", "Layer", "Core", "Leaf", "Circular"]
            )]
            if sig_lines:
                summary = "\n".join(sig_lines[:80])
                return (f"[结构化摘要]\n{summary}\n\n"
                        f"[原始 {len(result_str)} 字符，保留 {len(sig_lines)} 条关键行]")
            return result_str[:8000] + "\n...(截断)...\n" + result_str[-3000:]

        elif tool_name == "context_compress":
            # 压缩结果本身不应再被压缩
            return result_str[:10000]

        else:
            return result_str[:8000] + "\n...(截断)...\n" + result_str[-3000:]

    def _extract_task_keywords(self) -> set:
        """从最近用户消息中提取任务关键词，用于语义优先级评分"""
        keywords = set()
        for m in reversed(self._messages):
            if m.get("role") == "user":
                text = m.get("content", "")
                # 提取文件路径
                import re
                keywords.update(re.findall(r'[\w/]+\.(?:py|js|ts|rs|go|java|c|cpp|h|yaml|json|md)', text))
                # 提取函数/类名（CamelCase 或 snake_case）
                keywords.update(re.findall(r'\b[A-Z][a-zA-Z0-9]{2,}\b', text))
                keywords.update(re.findall(r'\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b', text))
                # 取最近3条用户消息
                if len(keywords) > 5:
                    break
        return {k.lower() for k in keywords if len(k) > 2}

    def _compute_semantic_relevance(self, content: str, task_keywords: set) -> float:
        """计算消息内容与当前任务的语义相关度 (0.0-1.0)"""
        if not task_keywords or not content:
            return 0.0
        content_lower = content.lower()
        hits = sum(1 for kw in task_keywords if kw in content_lower)
        return min(1.0, hits / max(len(task_keywords), 1))

    def _fuse_consecutive_tool_results(self):
        """合并连续的、关于同一文件的 tool 结果消息"""
        if len(self._messages) < 4:
            return
        import re
        new_messages = []
        i = 0
        while i < len(self._messages):
            m = self._messages[i]
            if m.get("role") != "tool":
                new_messages.append(m)
                i += 1
                continue
            # 收集连续 tool 消息
            group = [m]
            j = i + 1
            while j < len(self._messages) and self._messages[j].get("role") == "tool":
                group.append(self._messages[j])
                j += 1
            if len(group) <= 1:
                new_messages.append(m)
                i += 1
                continue
            # 按文件路径分组
            file_groups: dict = {}
            ungrouped = []
            for tm in group:
                content = tm.get("content", "")
                paths = re.findall(r'[\w./]+\.(?:py|js|ts|json|yaml|md)', content)
                key = paths[0] if paths else None
                if key and key in file_groups:
                    file_groups[key].append(tm)
                elif key:
                    file_groups[key] = [tm]
                else:
                    ungrouped.append(tm)
            # 合并同一文件的结果
            for path, msgs in file_groups.items():
                if len(msgs) == 1:
                    new_messages.append(msgs[0])
                else:
                    merged_content = f"[合并 {len(msgs)} 条关于 {path} 的结果]\n"
                    for mm in msgs:
                        c = mm.get("content", "")
                        merged_content += c[:500] + "\n---\n"
                    new_messages.append({**msgs[-1], "content": merged_content})
            new_messages.extend(ungrouped)
            i = j
        self._messages = new_messages

    def _check_context_overflow(self):
        """Token-aware 智能上下文管理（v3.1 — 语义优先级 + 消息融合）

        v3.1 改进（在 v3.0 基础上）：
        - 任务关键词提取 + 语义相关度评分（TF 命中率）
        - 连续同文件 tool 结果自动合并（消息融合）
        - 自适应 token 预算（按模型上下文窗口动态调整）
        - 任务关键路径保护（含当前任务关键词的消息优先保留）

        消息优先级评分（语义增强版）：
        - system prompt      → 100（不可丢弃）
        - 最近 user 消息     → 90（当前任务上下文）
        - error tool result  → 80（调试关键）
        - 任务相关消息       → +20 语义加成
        - 最近 assistant     → 70
        - 成功 tool result   → 40（可压缩）
        - 早期 user/assistant → 30
        - 早期 tool          → 10（可丢弃）
        """

        # 使用 tiktoken 精确计算 token 或 fallback 到字符估算
        _tiktoken_enc = None
        try:
            import tiktoken
            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        except (ImportError, Exception):
            pass

        def _estimate_tokens(text: str) -> int:
            if _tiktoken_enc is not None:
                return len(_tiktoken_enc.encode(text, disallowed_special=()))
            # fallback: 中英混合 ~3.5 字符/token
            return max(1, int(len(text) / 3.5))

        def _msg_tokens(msg: dict) -> int:
            t = _estimate_tokens(json.dumps(msg, ensure_ascii=False, default=str))
            return t

        # Token 限制（模型上下文窗口的 75%：给 response 留空间）
        # 动态从 LLM Router 获取当前 provider 的上下文长度
        try:
            model_ctx = self.llm_router.get_context_length()
        except Exception:
            model_ctx = self.config.get("model.context_length", 32768)
        token_limit = int(model_ctx * 0.75)

        total_tokens = sum(_msg_tokens(m) for m in self._messages)
        if total_tokens <= token_limit:
            return

        # ── 第0层：消息融合（合并连续同文件 tool 结果）──
        self._fuse_consecutive_tool_results()

        self.memory.compress_working_memory(keep_recent=5)

        # ── 提取任务关键词用于语义打分 ──
        task_keywords = self._extract_task_keywords()

        # ── 消息优先级打分（语义增强版）──
        msg_count = len(self._messages)

        def _priority(idx: int, msg: dict) -> int:
            role = msg.get("role", "")
            content = msg.get("content", "")
            recency = idx / max(msg_count, 1)  # 0.0 = oldest, 1.0 = newest

            if role == "system":
                return 100 if idx == 0 else 50

            # 语义相关度加成（最高 +20）
            relevance = self._compute_semantic_relevance(content, task_keywords)
            semantic_bonus = int(relevance * 20)

            is_recent = recency > 0.7
            if role == "user":
                base = 90 if is_recent else 30
            elif role == "assistant":
                if msg.get("tool_calls"):
                    base = 75 if is_recent else 35
                else:
                    base = 70 if is_recent else 30
            elif role == "tool":
                has_error = any(kw in content.lower() for kw in [
                    "error", "fail", "traceback", "exception", "错误", "失败"
                ])
                if has_error:
                    base = 80 if is_recent else 50
                else:
                    base = 40 if is_recent else 10
            else:
                base = 20
            return min(99, base + semantic_bonus)

        # ── 第一层：压缩大的 tool 结果 ──
        for i, m in enumerate(self._messages):
            if m.get("role") == "tool":
                content = m.get("content", "")
                pri = _priority(i, m)
                # 低优先级 + 大结果 → 激进压缩
                compress_threshold = 1500 if pri < 50 else 3000
                if len(content) > compress_threshold:
                    key_lines = []
                    for line in content.split("\n"):
                        ll = line.lower()
                        if any(kw in ll for kw in [
                            "error", "fail", "success", "status", "result",
                            "错误", "成功", "失败", "ok", "traceback", "assert"
                        ]):
                            key_lines.append(line)
                    if key_lines:
                        summary = "\n".join(key_lines[:15])
                        self._messages[i] = {
                            **m,
                            "content": f"[压缩摘要]\n{summary}\n[原始 {len(content)} 字符]",
                        }
                    else:
                        keep = compress_threshold // 2
                        self._messages[i] = {
                            **m,
                            "content": content[:keep] + "\n...(压缩)...\n" + content[-(keep // 2):],
                        }

        # ── 第二层：折叠低优先级早期对话 ──
        total_tokens = sum(_msg_tokens(m) for m in self._messages)
        if total_tokens > token_limit and len(self._messages) > 10:
            scored = [(i, _priority(i, m), m) for i, m in enumerate(self._messages)]
            # 保护 system prompt (idx=0) 和最近 8 条
            protected_indices = {0} | {i for i in range(max(1, msg_count - 8), msg_count)}

            # 收集可丢弃的早期消息
            droppable = [(i, pri, m) for i, pri, m in scored
                         if i not in protected_indices and pri < 50]
            droppable.sort(key=lambda x: x[1])  # 按优先级升序

            # 提取摘要再丢弃
            drop_indices = set()
            summary_parts = []
            tokens_freed = 0

            for i, pri, m in droppable:
                if total_tokens - tokens_freed <= token_limit:
                    break
                role = m.get("role", "")
                content = m.get("content", "")
                if role == "user":
                    summary_parts.append(f"用户: {content[:80]}")
                elif role == "assistant" and content:
                    summary_parts.append(f"助手: {content[:60]}")
                drop_indices.add(i)
                tokens_freed += _msg_tokens(m)

            if drop_indices:
                fold_text = f"[早期对话摘要 ({len(drop_indices)} 条消息已折叠)]\n"
                if summary_parts:
                    fold_text += "\n".join(summary_parts[:10]) + "\n"

                new_messages = []
                fold_inserted = False
                for i, m in enumerate(self._messages):
                    if i in drop_indices:
                        if not fold_inserted:
                            new_messages.append({"role": "system", "content": fold_text})
                            fold_inserted = True
                    else:
                        new_messages.append(m)
                self._messages = new_messages

        # ── 第三层：合并多余 system 消息 ──
        system_count = sum(1 for m in self._messages if m.get("role") == "system")
        if system_count > 3:
            core = self._messages[0]
            others = []
            non_system = []
            for i, m in enumerate(self._messages[1:], 1):
                if m.get("role") == "system":
                    others.append(m)
                else:
                    non_system.append(m)
            # 保留最近 2 个 system hint
            kept_hints = others[-2:] if len(others) > 2 else others
            self._messages = [core] + kept_hints + non_system

        # ── 第四层：极端裁切 ──
        total_tokens = sum(_msg_tokens(m) for m in self._messages)
        if total_tokens > token_limit and len(self._messages) > 6:
            # 保留 system prompt + 最近 N 条（动态计算 N）
            core = [self._messages[0]]
            # 从后往前累计 token，直到逼近限制
            core_tokens = _msg_tokens(core[0])
            recent = []
            for m in reversed(self._messages[1:]):
                mt = _msg_tokens(m)
                if core_tokens + mt > token_limit:
                    break
                recent.insert(0, m)
                core_tokens += mt
            self._messages = core + recent

    def get_memory_stats(self) -> dict:
        """获取记忆系统统计"""
        return self.memory.get_stats()

    def get_token_stats(self) -> dict:
        """获取本轮会话的 token 用量统计（v3.1）"""
        return dict(self._token_stats)

    def compact(self) -> dict:
        """主动压缩上下文（v3.2 — 对标 Claude Code 的 /compact 命令）

        优先使用 LLM 生成高质量对话摘要，失败时降级为机械提取。
        """
        if len(self._messages) <= 3:
            return {"status": "skip", "reason": "对话太短，无需压缩"}

        old_count = len(self._messages)
        old_chars = sum(len(json.dumps(m, ensure_ascii=False, default=str)) for m in self._messages)

        # 尝试使用 LLM 生成高质量摘要
        summary_text = self._llm_summarize_conversation()

        if not summary_text:
            # 降级：机械提取摘要
            summary_text = self._mechanical_summary()

        # 重建消息：system prompt + 摘要 + 最近 4 条消息
        system_prompt = self._messages[0]
        recent = [m for m in self._messages[-4:] if m.get("role") != "system"]

        self._messages = [
            system_prompt,
            {"role": "system", "content": summary_text},
        ] + recent

        new_chars = sum(len(json.dumps(m, ensure_ascii=False, default=str)) for m in self._messages)

        return {
            "status": "ok",
            "messages_before": old_count,
            "messages_after": len(self._messages),
            "chars_before": old_chars,
            "chars_after": new_chars,
            "compression_ratio": f"{(1 - new_chars / max(old_chars, 1)):.0%}",
        }

    def _llm_summarize_conversation(self) -> str | None:
        """使用 LLM 生成对话摘要（v3.2 — 对标 Claude Code 的智能压缩）"""
        try:
            # 收集对话内容（限制输入大小）
            conv_text = []
            for m in self._messages[1:]:  # 跳过 system prompt
                role = m.get("role", "")
                content = m.get("content", "") or ""
                if isinstance(content, str) and content.strip():
                    conv_text.append(f"[{role}] {content[:300]}")
            dialog = "\n".join(conv_text[-30:])  # 最近 30 条

            summary_prompt = [
                {"role": "system", "content": "你是一个对话摘要助手。"},
                {"role": "user", "content": (
                    "请将以下编程对话历史压缩为简洁的摘要，保留：\n"
                    "1. 用户的核心需求和目标\n"
                    "2. 已完成的操作（修改了哪些文件、执行了什么命令）\n"
                    "3. 当前进展状态和未完成的任务\n"
                    "4. 遇到的关键错误及其解决方案\n\n"
                    f"对话历史:\n{dialog}\n\n"
                    "请用中文输出结构化的摘要（500字以内）："
                )},
            ]

            result = self.llm_router.chat(
                messages=summary_prompt,
                temperature=0.2,
                task_complexity=0.2,
            )
            summary = result.get("content", "")
            if summary and len(summary) > 50:
                return f"[LLM 智能压缩摘要]\n{summary}"
        except Exception:
            pass
        return None

    def _mechanical_summary(self) -> str:
        """机械提取对话摘要（降级模式）"""
        tools_used = set()
        user_requests = []
        errors = []
        file_edits = []

        for m in self._messages[1:]:
            role = m.get("role", "")
            content = m.get("content", "") or ""
            if role == "user":
                user_requests.append(content[:200])
            elif role == "tool":
                if "error" in content.lower():
                    errors.append(content[:100])
                if '"path"' in content or '"status": "ok"' in content:
                    file_edits.append(content[:80])
            for tc in m.get("tool_calls", []):
                func = tc.get("function", {})
                tools_used.add(func.get("name", ""))

        lines = ["[上下文压缩摘要]"]
        lines.append(f"对话轮次: {len(user_requests)}")
        lines.append(f"使用工具: {', '.join(sorted(tools_used))}")
        if user_requests:
            lines.append("用户请求:")
            for i, req in enumerate(user_requests[-5:], 1):
                lines.append(f"  {i}. {req}")
        if file_edits:
            lines.append(f"文件操作: {len(file_edits)} 次编辑")
        if errors:
            lines.append(f"遇到错误: {len(errors)} 个")
        return "\n".join(lines)

    def get_evolution_stats(self) -> dict:
        """获取演化统计"""
        stats = self.evolution.get_stats()
        stats["metacognition"] = self.metacognition.get_metacognitive_profile()
        return stats

    def index_project(self, project_path: str) -> dict:
        """索引项目到 RAG 知识库"""
        return self.rag.index_directory(project_path, source="codebase")

    # ===== Phase 3: 流式输出 =====

    def _stream_chat(self, tool_schemas: list, temperature: float = None,
                      task_complexity: float = 0.5) -> dict | None:
        """流式调用 LLM（通过 ModelRouter），逐 token 输出

        返回组装后的完整消息（与非流式兼容）。
        """
        temp = temperature if temperature is not None else self.temperature
        try:
            return self.llm_router.stream_chat(
                messages=self._messages,
                tools=tool_schemas if tool_schemas else None,
                temperature=temp,
                task_complexity=task_complexity,
            )
        except Exception as e:
            import logging as _log
            _log.getLogger(__name__).error("流式 LLM 调用失败: %s", e, exc_info=True)
            return {"_stream_error": str(e)}

    # ===== Phase 3: 会话持久化 =====

    def save_conversation(self, session_id: str | None = None) -> str:
        """将当前会话消息历史保存到磁盘

        返回保存的会话 ID。
        """
        import hashlib
        from pathlib import Path

        if session_id is None:
            session_id = self._session_id or hashlib.sha256(
                str(time.time()).encode()
            ).hexdigest()[:12]

        self._session_id = session_id
        conv_dir = Path(self._data_dir) / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)

        # 保存消息（排除 system prompt 避免冗余）
        saveable = []
        for m in self._messages:
            if m.get("role") == "system" and SYSTEM_PROMPT in m.get("content", ""):
                continue
            saveable.append(m)

        data = {
            "session_id": session_id,
            "model": self.model,
            "messages": saveable,
            "task_log": self._task_log,
            "saved_at": time.time(),
        }

        filepath = conv_dir / f"{session_id}.json"
        # v9.0: 原子写入 — 先写临时文件再 rename
        import os
        import tempfile
        fd, tmp_path = tempfile.mkstemp(dir=str(conv_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp_path, str(filepath))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return session_id

    def load_conversation(self, session_id: str) -> bool:
        """从磁盘加载历史会话

        返回是否加载成功。
        """
        import re as _re_conv
        from pathlib import Path

        # v8.0: session_id 消毒 — 仅允许字母数字和连字符/下划线
        if not _re_conv.match(r'^[a-zA-Z0-9_\-]+$', session_id):
            _logger.warning("Invalid session_id rejected: %s", session_id)
            return False

        conv_dir = (Path(self._data_dir) / "conversations").resolve()
        filepath = (conv_dir / f"{session_id}.json").resolve()

        # 路径约束 — 必须在 conversations 目录内
        if not str(filepath).startswith(str(conv_dir) + "/"):
            return False

        if not filepath.exists():
            return False

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            _logger.warning("Corrupt conversation file: %s", filepath)
            return False

        # 恢复会话
        self.start_session()
        self._session_id = session_id
        self._messages.extend(data.get("messages", []))
        self._task_log = data.get("task_log", {"actions": [], "outcome": None})
        return True

    def list_conversations(self) -> list[dict]:
        """列出所有保存的会话"""
        from pathlib import Path

        conv_dir = Path(self._data_dir) / "conversations"
        if not conv_dir.exists():
            return []

        sessions = []
        for f in sorted(conv_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                # 提取摘要
                user_msgs = [m for m in data.get("messages", []) if m.get("role") == "user"]
                sessions.append({
                    "session_id": data.get("session_id", f.stem),
                    "saved_at": data.get("saved_at"),
                    "message_count": len(data.get("messages", [])),
                    "first_message": user_msgs[0].get("content", "")[:100] if user_msgs else "",
                })
            except (json.JSONDecodeError, OSError):
                continue

        return sessions

    # ===== P1: 子 Agent 编排（对标 Devin 多角色协作 / Copilot Agent 子任务委派）=====

    def spawn_sub_agent(self, sub_task: str, tools_subset: list[str] | None = None,
                        max_iterations: int = 15) -> dict:
        """分派子任务到子 Agent 执行

        用于将复杂任务分解后的子步骤委派给独立 Agent 实例，
        子 Agent 拥有独立的消息历史和迭代限制。

        Args:
            sub_task: 子任务描述
            tools_subset: 限制子 Agent 可用的工具列表（None = 全部）
            max_iterations: 子 Agent 最大迭代次数

        Returns:
            {"status": "ok/error", "result": "...", "actions": [...]}
        """
        # v7.0: 子 Agent 嵌套深度限制（防止无限递归耗尽资源）
        current_depth = getattr(self, "_depth", 0)
        if current_depth >= 3:
            return {"status": "error", "error": "子 Agent 嵌套深度超限 (max=3)，拒绝继续分派"}

        # 创建轻量级子 Agent（共享 config/memory/llm，但独立消息历史）
        sub = TuringAgent.__new__(TuringAgent)
        sub.config = self.config
        sub.model = self.model
        sub.temperature = self.temperature
        sub.max_iterations = max_iterations
        sub.stream_output = False
        sub.llm_router = self.llm_router
        sub.memory = self.memory
        sub.rag = self.rag
        sub.evolution = self.evolution
        sub.metacognition = self.metacognition
        sub.benchmark = self.benchmark
        sub.mcp = self.mcp
        sub.safety = self.safety
        sub.sandbox = self.sandbox
        sub._data_dir = self._data_dir
        sub._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        sub._task_log = {"actions": [], "outcome": None, "start_time": time.time()}
        sub._initialized = True
        sub._session_id = None
        sub._recent_tool_calls = []
        sub._current_phase = "execution"
        sub._etf_retry_count = 0
        sub._error_history = []
        sub._allowed_tools = set(tools_subset) if tools_subset else None
        sub._depth = current_depth + 1
        sub._last_counted_msg_idx = 0

        # 收集子 Agent 执行结果
        final_text = []
        tool_results = []
        try:
            for event in sub.chat(sub_task):
                if event["type"] == "text":
                    final_text.append(event["content"])
                elif event["type"] == "tool_result":
                    tool_results.append({
                        "tool": event["name"],
                        "success": "error" not in event.get("result", {}),
                    })
                elif event["type"] == "error":
                    return {
                        "status": "error",
                        "error": event["content"],
                        "actions": sub._task_log["actions"],
                    }
        except Exception as e:
            return {"status": "error", "error": str(e)}

        return {
            "status": "ok",
            "result": "\n".join(final_text),
            "outcome": sub._task_log.get("outcome", "unknown"),
            "actions_count": len(sub._task_log["actions"]),
            "tools_used": list(set(a["tool"] for a in sub._task_log["actions"])),
        }
