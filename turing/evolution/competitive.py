"""竞争力分析引擎 — Turing 自我对标与持续改进核心

将竞争力差距分析内化为自我演化的一部分，让 Turing 能够：

1. **持续自评** — 动态对标 Claude Code / Cursor / Copilot / Devin / Aider / Codex 等工具
2. **能力矩阵** — 多维度能力对比（代码理解、自主性、工具链、安全、UX 等）
3. **差距追踪** — 跟踪历次分析的差距变化趋势，验证改进效果
4. **改进路线图** — 生成优先级排序的可实施改进项
5. **元认知联动** — 将竞争力洞察注入元认知决策和策略进化
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


# ===== 竞争对手能力数据库 =====

COMPETITOR_PROFILES: dict[str, dict[str, Any]] = {
    "claude_code": {
        "name": "Claude Code (Anthropic)",
        "category": "terminal_agent",
        "strengths": {
            "code_understanding": 0.95,       # 深度代码理解
            "autonomous_execution": 0.90,      # 自主多步执行
            "reasoning_depth": 0.95,           # 推理深度
            "context_window": 0.95,            # 200K token
            "tool_use": 0.90,                  # bash/file/search 工具
            "safety": 0.90,                    # 权限系统 + 沙箱
            "project_awareness": 0.85,         # CLAUDE.md + 项目理解
            "multi_file_edit": 0.90,           # 多文件编辑
            "test_driven": 0.90,               # 自动运行测试
            "git_integration": 0.85,           # Git 完整工作流
            "error_recovery": 0.85,            # 错误修复循环
            "memory_persistence": 0.50,        # 仅 CLAUDE.md 静态记忆
            "self_evolution": 0.10,            # 无自我演化
            "local_privacy": 0.30,             # 云端模型
            "real_time_completion": 0.30,      # 非补全模式
            "cost_control": 0.50,              # 无预算控制
        },
        "key_differentiators": [
            "200K 超大上下文窗口",
            "Sonnet/Opus 双模型强推理能力",
            "bash 工具直接执行系统命令",
            "权限分级（ask/auto-edit/full-auto）",
            "extended thinking 深度推理",
        ],
    },
    "cursor": {
        "name": "Cursor",
        "category": "ide_agent",
        "strengths": {
            "code_understanding": 0.85,
            "autonomous_execution": 0.80,
            "reasoning_depth": 0.80,
            "context_window": 0.80,
            "tool_use": 0.85,
            "safety": 0.70,
            "project_awareness": 0.90,         # .cursorrules + 项目索引
            "multi_file_edit": 0.90,
            "test_driven": 0.75,
            "git_integration": 0.80,
            "error_recovery": 0.80,
            "memory_persistence": 0.60,        # 项目级记忆
            "self_evolution": 0.10,
            "local_privacy": 0.40,
            "real_time_completion": 0.95,      # Tab 实时补全
            "cost_control": 0.60,
        },
        "key_differentiators": [
            "IDE 深度集成的实时代码补全",
            "Composer 多文件编排",
            "代码库索引 + 语义搜索",
            ".cursorrules 项目级定制",
            "inline diff 预览",
        ],
    },
    "copilot": {
        "name": "GitHub Copilot",
        "category": "ide_agent",
        "strengths": {
            "code_understanding": 0.80,
            "autonomous_execution": 0.75,
            "reasoning_depth": 0.75,
            "context_window": 0.75,
            "tool_use": 0.80,
            "safety": 0.70,
            "project_awareness": 0.80,
            "multi_file_edit": 0.80,
            "test_driven": 0.70,
            "git_integration": 0.85,
            "error_recovery": 0.75,
            "memory_persistence": 0.55,
            "self_evolution": 0.05,
            "local_privacy": 0.40,
            "real_time_completion": 0.95,
            "cost_control": 0.70,
        },
        "key_differentiators": [
            "VS Code / JetBrains 原生集成",
            "Agent 模式多工具并发",
            "GitHub 生态深度绑定（PR/Issue/Actions）",
            "copilot-instructions.md 项目定制",
            "多模型切换（GPT-4o/Claude/Gemini）",
        ],
    },
    "devin": {
        "name": "Devin (Cognition AI)",
        "category": "autonomous_agent",
        "strengths": {
            "code_understanding": 0.80,
            "autonomous_execution": 0.95,      # 全自主开发
            "reasoning_depth": 0.80,
            "context_window": 0.75,
            "tool_use": 0.90,
            "safety": 0.65,
            "project_awareness": 0.80,
            "multi_file_edit": 0.90,
            "test_driven": 0.85,
            "git_integration": 0.90,
            "error_recovery": 0.80,
            "memory_persistence": 0.70,
            "self_evolution": 0.30,
            "local_privacy": 0.20,             # 云端沙箱
            "real_time_completion": 0.20,
            "cost_control": 0.40,
        },
        "key_differentiators": [
            "全自主端到端开发（浏览器+终端+编辑器）",
            "持久化沙箱环境",
            "自主 PR 提交和 review",
            "计划-执行-验证闭环",
            "支持异步任务（Slack 通知）",
        ],
    },
    "aider": {
        "name": "Aider",
        "category": "terminal_agent",
        "strengths": {
            "code_understanding": 0.75,
            "autonomous_execution": 0.70,
            "reasoning_depth": 0.70,
            "context_window": 0.80,
            "tool_use": 0.65,
            "safety": 0.60,
            "project_awareness": 0.75,
            "multi_file_edit": 0.85,
            "test_driven": 0.70,
            "git_integration": 0.90,           # 自动 commit
            "error_recovery": 0.75,
            "memory_persistence": 0.40,
            "self_evolution": 0.05,
            "local_privacy": 0.50,             # 支持本地模型
            "real_time_completion": 0.10,
            "cost_control": 0.75,
        },
        "key_differentiators": [
            "Architect/Editor 双模型模式（Turing 已借鉴）",
            "自动 Git commit 每次编辑",
            "repo map 仓库结构索引",
            "支持 60+ 模型提供商",
            "diff 格式精准编辑",
        ],
    },
    "codex_cli": {
        "name": "OpenAI Codex CLI",
        "category": "terminal_agent",
        "strengths": {
            "code_understanding": 0.85,
            "autonomous_execution": 0.85,
            "reasoning_depth": 0.85,
            "context_window": 0.80,
            "tool_use": 0.85,
            "safety": 0.80,                   # 网络沙箱
            "project_awareness": 0.75,
            "multi_file_edit": 0.85,
            "test_driven": 0.80,
            "git_integration": 0.80,
            "error_recovery": 0.80,
            "memory_persistence": 0.40,
            "self_evolution": 0.05,
            "local_privacy": 0.30,
            "real_time_completion": 0.20,
            "cost_control": 0.60,
        },
        "key_differentiators": [
            "网络沙箱隔离执行",
            "o3/o4-mini 推理模型",
            "并行文件操作",
            "AGENTS.md 项目定制",
            "全自动 suggest/auto-edit/full-auto 三档",
        ],
    },
    "windsurf": {
        "name": "Windsurf (Codeium)",
        "category": "ide_agent",
        "strengths": {
            "code_understanding": 0.80,
            "autonomous_execution": 0.80,
            "reasoning_depth": 0.75,
            "context_window": 0.80,
            "tool_use": 0.80,
            "safety": 0.65,
            "project_awareness": 0.85,
            "multi_file_edit": 0.85,
            "test_driven": 0.70,
            "git_integration": 0.75,
            "error_recovery": 0.75,
            "memory_persistence": 0.60,
            "self_evolution": 0.10,
            "local_privacy": 0.35,
            "real_time_completion": 0.90,
            "cost_control": 0.55,
        },
        "key_differentiators": [
            "Cascade 流式多步 Agent",
            "Supercomplete 上下文感知补全",
            "Memory 持久化项目记忆",
            "IDE 原生集成（Fork from VS Code）",
            "多模型路由",
        ],
    },
}

# ===== Turing 自身能力评估维度 =====

CAPABILITY_DIMENSIONS: dict[str, dict[str, str]] = {
    "code_understanding": {
        "name": "代码理解深度",
        "description": "对代码结构、语义、依赖的理解能力",
    },
    "autonomous_execution": {
        "name": "自主执行能力",
        "description": "独立完成多步骤编程任务的能力",
    },
    "reasoning_depth": {
        "name": "推理深度",
        "description": "CoT 推理、问题分解、根因分析能力",
    },
    "context_window": {
        "name": "上下文管理",
        "description": "处理大规模上下文、智能压缩和窗口管理",
    },
    "tool_use": {
        "name": "工具链完备性",
        "description": "内置工具数量和覆盖范围",
    },
    "safety": {
        "name": "安全防护",
        "description": "权限控制、沙箱隔离、审计安全",
    },
    "project_awareness": {
        "name": "项目感知",
        "description": "项目结构理解、规约加载、自动索引",
    },
    "multi_file_edit": {
        "name": "多文件编辑",
        "description": "跨文件编辑、符号重命名、影响分析",
    },
    "test_driven": {
        "name": "测试驱动",
        "description": "自动运行测试、ETF 验证循环",
    },
    "git_integration": {
        "name": "Git 集成",
        "description": "Git 完整工作流（diff/blame/log/commit）",
    },
    "error_recovery": {
        "name": "错误恢复",
        "description": "错误检测、自动修复、恢复策略",
    },
    "memory_persistence": {
        "name": "记忆持久化",
        "description": "跨会话记忆、经验积累、知识复用",
    },
    "self_evolution": {
        "name": "自我演化",
        "description": "策略进化、元认知、知识蒸馏、自我诊断",
    },
    "local_privacy": {
        "name": "本地隐私",
        "description": "本地部署、数据不上传、隐私保护",
    },
    "real_time_completion": {
        "name": "实时补全",
        "description": "IDE 集成的实时代码补全",
    },
    "cost_control": {
        "name": "成本控制",
        "description": "Token 预算、prompt caching、模型路由",
    },
}


class CompetitiveIntelligence:
    """竞争力分析引擎 — Turing 自我对标核心

    持续评估 Turing 在各能力维度上相对竞争对手的位置，
    生成差距报告和改进路线图，并将洞察注入元认知和策略进化。
    """

    def __init__(self, data_dir: str = "turing_data"):
        self._data_dir = data_dir
        self._analysis_path = Path(data_dir) / "evolution" / "competitive_analysis.json"
        self._analysis_path.parent.mkdir(parents=True, exist_ok=True)
        self._history: list[dict] = self._load_history()

    # ===== Turing 自身能力评估 =====

    @staticmethod
    def _ensure_tools_loaded():
        """确保所有工具模块已导入并注册"""
        import importlib
        modules = [
            "turing.tools.file_tools", "turing.tools.command_tools",
            "turing.tools.search_tools", "turing.tools.git_tools",
            "turing.tools.test_tools", "turing.tools.quality_tools",
            "turing.tools.project_tools", "turing.tools.refactor_tools",
            "turing.tools.ast_tools", "turing.tools.memory_tools",
            "turing.tools.external_tools", "turing.tools.evolution_tools",
            "turing.tools.metacognition_tools", "turing.tools.benchmark_tools",
            "turing.tools.mcp_tools", "turing.tools.agent_tools",
            "turing.tools.github_tools",
        ]
        for mod in modules:
            try:
                importlib.import_module(mod)
            except Exception:
                pass

    def _assess_turing_capabilities(self) -> dict[str, float]:
        """动态评估 Turing 当前各维度能力值

        基于实际已实现的功能来评分，而非静态配置。
        每个维度 0.0-1.0。
        """
        # 确保所有工具模块已加载（独立运行时可能未导入）
        self._ensure_tools_loaded()

        from turing.tools.registry import get_all_tools
        own_tools = {t.name for t in get_all_tools()}
        tool_count = len(own_tools)

        scores: dict[str, float] = {}

        # 1. 代码理解深度 — dependency_graph 增强
        code_tools = {"code_structure", "call_graph", "complexity_report",
                      "impact_analysis", "read_file", "search_code",
                      "dependency_graph"}
        scores["code_understanding"] = min(
            len(code_tools & own_tools) / len(code_tools) * 0.7 + 0.22, 0.92
        )

        # 2. 自主执行能力 — task_plan + delegate_task + auto_fix + verify_hypothesis 增强
        exec_tools = {"run_command", "edit_file", "write_file", "read_file",
                      "search_code", "list_directory", "run_background",
                      "task_plan", "delegate_task", "auto_fix", "verify_hypothesis"}
        scores["autonomous_execution"] = min(
            len(exec_tools & own_tools) / len(exec_tools) * 0.7 + 0.22, 0.90
        )

        # 3. 推理深度 — CoT + 多路径推理 + verify_hypothesis + 分层分解 + 动态温度
        has_verify = "verify_hypothesis" in own_tools
        scores["reasoning_depth"] = 0.88 if has_verify else 0.85

        # 4. 上下文管理 — context_budget + context_compress + RAG + 智能压缩
        has_ctx_budget = "context_budget" in own_tools
        has_ctx_compress = "context_compress" in own_tools
        has_rag = "rag_search" in own_tools
        base_ctx = 0.45
        if has_rag:
            base_ctx += 0.15
        if has_ctx_budget:
            base_ctx += 0.10
        if has_ctx_compress:
            base_ctx += 0.10
        scores["context_window"] = min(base_ctx, 0.80)

        # 5. 工具链完备性
        scores["tool_use"] = min(tool_count / 85, 0.94)

        # 6. 安全防护 — SafetyGuard + 沙箱 + security_scan + 审计
        has_sec_scan = "security_scan" in own_tools
        scores["safety"] = 0.88 if has_sec_scan else 0.80

        # 7. 项目感知 — repo_map + detect_project(含 CI/CD 详情 + monorepo) + RAG
        project_tools = {"repo_map", "detect_project", "rag_search",
                         "list_directory", "analyze_dependencies"}
        scores["project_awareness"] = min(
            len(project_tools & own_tools) / len(project_tools) * 0.7 + 0.20, 0.88
        )

        # 8. 多文件编辑
        edit_tools = {"edit_file", "write_file", "rename_symbol",
                      "impact_analysis", "batch_edit", "multi_edit"}
        scores["multi_file_edit"] = min(
            len(edit_tools & own_tools) / len(edit_tools) * 0.7 + 0.20, 0.88
        )

        # 9. 测试驱动 — run_tests + ETF + test_coverage
        test_tool_set = {"run_tests", "lint_code", "type_check",
                         "generate_tests", "test_coverage"}
        scores["test_driven"] = min(
            len(test_tool_set & own_tools) / len(test_tool_set) * 0.7 + 0.18, 0.88
        )

        # 10. Git 集成 — pr_summary 增强
        git_tool_set = {"git_status", "git_diff", "git_log", "git_blame",
                        "git_commit", "git_branch", "pr_summary"}
        scores["git_integration"] = min(
            len(git_tool_set & own_tools) / len(git_tool_set) * 0.7 + 0.18, 0.88
        )

        # 11. 错误恢复 — ETF + checkpoint 系统 + 恢复剧本
        has_checkpoint = "checkpoint_save" in own_tools and "checkpoint_restore" in own_tools
        scores["error_recovery"] = 0.88 if has_checkpoint else 0.80

        # 12. 记忆持久化 — 四层记忆（独特优势）
        memory_tools = {"memory_read", "memory_write", "memory_reflect", "rag_search"}
        base = len(memory_tools & own_tools) / len(memory_tools) * 0.5
        scores["memory_persistence"] = min(base + 0.40, 0.88)

        # 13. 自我演化 — 独特能力（竞品几乎没有）
        evo_tools = {"learn_from_ai_tool", "gap_analysis", "self_diagnose",
                     "synthesize_experiences", "cross_task_transfer", "cognitive_adapt",
                     "competitive_benchmark"}
        scores["self_evolution"] = min(
            len(evo_tools & own_tools) / len(evo_tools) * 0.7 + 0.25, 0.92
        )

        # 14. 本地隐私 — 支持本地 LLM（独特优势）
        scores["local_privacy"] = 0.92

        # 15. 实时补全 — LSP 服务器提供基础代码补全
        try:
            from turing.lsp.server import TuringLSPServer  # noqa: F401
            scores["real_time_completion"] = 0.40
        except ImportError:
            scores["real_time_completion"] = 0.10

        # 16. 成本控制 — prompt caching + token budget + 多模型路由
        scores["cost_control"] = 0.78

        return scores

    # ===== 核心分析 =====

    def analyze(self) -> dict:
        """执行全面竞争力分析

        Returns:
            包含能力矩阵、差距排名、竞品对比、改进路线图的完整报告
        """
        turing_scores = self._assess_turing_capabilities()
        timestamp = time.time()

        # 1. 能力矩阵 — Turing vs 各竞品
        capability_matrix = self._build_capability_matrix(turing_scores)

        # 2. 差距分析 — 找出 Turing 最薄弱的维度
        gap_ranking = self._rank_gaps(turing_scores)

        # 3. 竞品逐一对比
        competitor_comparisons = self._compare_with_competitors(turing_scores)

        # 4. 优势识别 — Turing 领先的维度
        advantages = self._identify_advantages(turing_scores)

        # 5. 改进路线图
        roadmap = self._generate_roadmap(gap_ranking, turing_scores)

        # 6. 综合竞争力评分
        overall = self._compute_competitive_score(turing_scores)

        # 7. 趋势分析 — 与上次分析对比
        trend = self._compute_trend(turing_scores)

        report = {
            "version": "v1.0",
            "timestamp": timestamp,
            "turing_scores": turing_scores,
            "capability_matrix": capability_matrix,
            "gap_ranking": gap_ranking,
            "competitor_comparisons": competitor_comparisons,
            "advantages": advantages,
            "improvement_roadmap": roadmap,
            "overall_competitive_score": overall,
            "trend": trend,
        }

        # 持久化
        self._history.append({
            "timestamp": timestamp,
            "turing_scores": turing_scores,
            "overall_score": overall,
            "top_gaps": [g["dimension"] for g in gap_ranking[:3]],
            "top_advantages": [a["dimension"] for a in advantages[:3]],
        })
        self._save_history()

        # 保存完整报告
        report_path = Path(self._data_dir) / "evolution" / "competitive_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    def _build_capability_matrix(self, turing_scores: dict[str, float]) -> dict:
        """构建 Turing vs 竞品的能力矩阵"""
        matrix = {}
        for dim in CAPABILITY_DIMENSIONS:
            dim_info = CAPABILITY_DIMENSIONS[dim]
            row = {
                "name": dim_info["name"],
                "turing": round(turing_scores.get(dim, 0), 2),
            }
            for comp_id, comp in COMPETITOR_PROFILES.items():
                row[comp_id] = round(comp["strengths"].get(dim, 0), 2)

            # 计算 Turing 在该维度的排名
            all_scores = [(k, v) for k, v in row.items()
                          if k not in ("name", "turing") and isinstance(v, float)]
            all_scores.append(("turing", row["turing"]))
            all_scores.sort(key=lambda x: x[1], reverse=True)
            row["turing_rank"] = next(
                i + 1 for i, (k, _) in enumerate(all_scores) if k == "turing"
            )
            row["total_competitors"] = len(all_scores)
            matrix[dim] = row

        return matrix

    def _rank_gaps(self, turing_scores: dict[str, float]) -> list[dict]:
        """按差距大小排序各维度"""
        gaps = []
        for dim, turing_val in turing_scores.items():
            # 计算竞品最高分和平均分
            comp_scores = [
                comp["strengths"].get(dim, 0)
                for comp in COMPETITOR_PROFILES.values()
            ]
            if not comp_scores:
                continue

            best_score = max(comp_scores)
            avg_score = sum(comp_scores) / len(comp_scores)
            gap_to_best = best_score - turing_val
            gap_to_avg = avg_score - turing_val

            # 找到最强竞品
            best_competitor = max(
                COMPETITOR_PROFILES.items(),
                key=lambda x: x[1]["strengths"].get(dim, 0),
            )

            dim_info = CAPABILITY_DIMENSIONS.get(dim, {})
            gaps.append({
                "dimension": dim,
                "name": dim_info.get("name", dim),
                "turing_score": round(turing_val, 2),
                "best_competitor": best_competitor[0],
                "best_score": round(best_score, 2),
                "avg_score": round(avg_score, 2),
                "gap_to_best": round(gap_to_best, 2),
                "gap_to_avg": round(gap_to_avg, 2),
                "severity": (
                    "critical" if gap_to_best > 0.4
                    else "significant" if gap_to_best > 0.2
                    else "moderate" if gap_to_best > 0.1
                    else "minor" if gap_to_best > 0
                    else "leading"
                ),
            })

        gaps.sort(key=lambda x: x["gap_to_best"], reverse=True)
        return gaps

    def _compare_with_competitors(self, turing_scores: dict[str, float]) -> dict:
        """逐一与各竞品对比"""
        comparisons = {}
        for comp_id, comp in COMPETITOR_PROFILES.items():
            wins = []
            losses = []
            ties = []
            for dim in turing_scores:
                t = turing_scores[dim]
                c = comp["strengths"].get(dim, 0)
                diff = t - c
                entry = {
                    "dimension": dim,
                    "name": CAPABILITY_DIMENSIONS.get(dim, {}).get("name", dim),
                    "turing": round(t, 2),
                    "competitor": round(c, 2),
                    "diff": round(diff, 2),
                }
                if diff > 0.05:
                    wins.append(entry)
                elif diff < -0.05:
                    losses.append(entry)
                else:
                    ties.append(entry)

            # 排序
            wins.sort(key=lambda x: x["diff"], reverse=True)
            losses.sort(key=lambda x: x["diff"])

            comparisons[comp_id] = {
                "name": comp["name"],
                "category": comp["category"],
                "turing_wins": len(wins),
                "competitor_wins": len(losses),
                "ties": len(ties),
                "key_differentiators": comp["key_differentiators"],
                "turing_advantages": wins[:5],
                "turing_disadvantages": losses[:5],
            }

        return comparisons

    def _identify_advantages(self, turing_scores: dict[str, float]) -> list[dict]:
        """识别 Turing 的独特优势"""
        advantages = []
        for dim, turing_val in turing_scores.items():
            comp_scores = [
                comp["strengths"].get(dim, 0)
                for comp in COMPETITOR_PROFILES.values()
            ]
            avg = sum(comp_scores) / len(comp_scores) if comp_scores else 0
            lead = turing_val - avg

            if lead > 0.05:
                # 找到在该维度最弱的竞品
                weakest = min(
                    COMPETITOR_PROFILES.items(),
                    key=lambda x: x[1]["strengths"].get(dim, 0),
                )
                advantages.append({
                    "dimension": dim,
                    "name": CAPABILITY_DIMENSIONS.get(dim, {}).get("name", dim),
                    "turing_score": round(turing_val, 2),
                    "avg_competitor": round(avg, 2),
                    "lead": round(lead, 2),
                    "weakest_competitor": weakest[0],
                })

        advantages.sort(key=lambda x: x["lead"], reverse=True)
        return advantages

    def _generate_roadmap(self, gap_ranking: list[dict],
                          turing_scores: dict[str, float]) -> list[dict]:
        """生成优先级排序的改进路线图"""
        # 改进建议数据库
        improvement_actions: dict[str, dict] = {
            "real_time_completion": {
                "action": "开发 VS Code / JetBrains 插件，提供实时代码补全",
                "impact": "high",
                "effort": "very_high",
                "category": "UX",
            },
            "context_window": {
                "action": "优化上下文压缩算法，支持更大模型或 API 模式切换",
                "impact": "high",
                "effort": "medium",
                "category": "核心能力",
            },
            "code_understanding": {
                "action": "增强 AST 分析：类型推断、数据流分析、跨仓库符号解析",
                "impact": "high",
                "effort": "high",
                "category": "核心能力",
            },
            "autonomous_execution": {
                "action": "增强子 Agent 调度：并行执行、任务依赖图、超时控制",
                "impact": "high",
                "effort": "medium",
                "category": "核心能力",
            },
            "reasoning_depth": {
                "action": "引入 Tree-of-Thought 和 Monte Carlo 推理路径搜索",
                "impact": "medium",
                "effort": "high",
                "category": "核心能力",
            },
            "safety": {
                "action": "增强网络沙箱隔离，支持 Docker 网络策略",
                "impact": "medium",
                "effort": "medium",
                "category": "安全",
            },
            "project_awareness": {
                "action": "自动检测 monorepo 结构、依赖图、CI/CD 配置",
                "impact": "medium",
                "effort": "medium",
                "category": "工程化",
            },
            "multi_file_edit": {
                "action": "增强 batch_edit 支持事务性多文件编辑和回滚",
                "impact": "medium",
                "effort": "medium",
                "category": "核心能力",
            },
            "test_driven": {
                "action": "增强测试生成：覆盖率分析、property-based testing",
                "impact": "medium",
                "effort": "medium",
                "category": "质量保证",
            },
            "git_integration": {
                "action": "集成 PR 创建、代码 review、CI 状态检查",
                "impact": "medium",
                "effort": "medium",
                "category": "工程化",
            },
            "error_recovery": {
                "action": "增强错误分类粒度，引入 checkpoint-rollback 恢复机制",
                "impact": "medium",
                "effort": "low",
                "category": "可靠性",
            },
            "memory_persistence": {
                "action": "增强记忆检索效率：向量索引 + 时间衰减 + 重要性排序",
                "impact": "low",
                "effort": "medium",
                "category": "核心能力",
            },
            "self_evolution": {
                "action": "维持优势：持续增强竞争力分析和元认知系统",
                "impact": "low",
                "effort": "low",
                "category": "元能力",
            },
            "local_privacy": {
                "action": "维持优势：持续优化本地模型推理性能",
                "impact": "low",
                "effort": "low",
                "category": "隐私",
            },
            "cost_control": {
                "action": "增强成本监控可视化，支持按项目的预算配置",
                "impact": "low",
                "effort": "low",
                "category": "运营",
            },
        }

        roadmap = []
        for i, gap in enumerate(gap_ranking):
            dim = gap["dimension"]
            action_info = improvement_actions.get(dim, {
                "action": f"分析并改进 {dim} 能力",
                "impact": "medium",
                "effort": "medium",
                "category": "其他",
            })

            # 只给有实际差距的维度生成路线图
            if gap["severity"] in ("critical", "significant", "moderate"):
                roadmap.append({
                    "priority": len(roadmap) + 1,
                    "dimension": dim,
                    "name": gap["name"],
                    "current_score": gap["turing_score"],
                    "target_score": min(gap["turing_score"] + 0.2, gap["best_score"]),
                    "gap_severity": gap["severity"],
                    "action": action_info["action"],
                    "impact": action_info["impact"],
                    "effort": action_info["effort"],
                    "category": action_info["category"],
                })

        return roadmap

    def _compute_competitive_score(self, turing_scores: dict[str, float]) -> dict:
        """计算综合竞争力评分"""
        # 加权评分 — 代码理解和自主执行权重最高
        weights = {
            "code_understanding": 1.5,
            "autonomous_execution": 1.5,
            "reasoning_depth": 1.3,
            "context_window": 1.0,
            "tool_use": 1.2,
            "safety": 1.0,
            "project_awareness": 1.0,
            "multi_file_edit": 1.0,
            "test_driven": 1.1,
            "git_integration": 0.8,
            "error_recovery": 1.0,
            "memory_persistence": 0.9,
            "self_evolution": 0.8,
            "local_privacy": 0.5,
            "real_time_completion": 0.7,
            "cost_control": 0.5,
        }

        weighted_sum = sum(
            turing_scores.get(dim, 0) * w for dim, w in weights.items()
        )
        total_weight = sum(weights.values())
        turing_weighted = weighted_sum / total_weight

        # 竞品加权分
        comp_weighted = {}
        for comp_id, comp in COMPETITOR_PROFILES.items():
            comp_sum = sum(
                comp["strengths"].get(dim, 0) * w for dim, w in weights.items()
            )
            comp_weighted[comp_id] = round(comp_sum / total_weight, 3)

        # 排名
        all_scores = list(comp_weighted.items()) + [("turing", turing_weighted)]
        all_scores.sort(key=lambda x: x[1], reverse=True)
        turing_rank = next(
            i + 1 for i, (k, _) in enumerate(all_scores) if k == "turing"
        )

        return {
            "turing_score": round(turing_weighted, 3),
            "rank": turing_rank,
            "total": len(all_scores),
            "competitor_scores": comp_weighted,
            "ranking": [{"name": k, "score": round(v, 3)} for k, v in all_scores],
        }

    def _compute_trend(self, current_scores: dict[str, float]) -> dict:
        """与上次分析对比，计算趋势"""
        if not self._history:
            return {"status": "first_analysis", "message": "首次竞争力分析，无历史趋势"}

        last = self._history[-1]
        last_scores = last.get("turing_scores", {})
        last_overall = last.get("overall_score", {}).get("turing_score", 0)

        # 计算当前 overall
        current_overall = sum(current_scores.values()) / max(len(current_scores), 1)

        improved = []
        declined = []
        for dim in current_scores:
            old = last_scores.get(dim, 0)
            new = current_scores[dim]
            diff = new - old
            if diff > 0.05:
                improved.append({
                    "dimension": dim,
                    "old": round(old, 2),
                    "new": round(new, 2),
                    "delta": round(diff, 2),
                })
            elif diff < -0.05:
                declined.append({
                    "dimension": dim,
                    "old": round(old, 2),
                    "new": round(new, 2),
                    "delta": round(diff, 2),
                })

        return {
            "status": "has_history",
            "previous_analysis": last.get("timestamp"),
            "analyses_count": len(self._history),
            "overall_trend": (
                "improving" if current_overall > last_overall + 0.02
                else "declining" if current_overall < last_overall - 0.02
                else "stable"
            ),
            "improved_dimensions": improved,
            "declined_dimensions": declined,
        }

    # ===== 元认知联动接口 =====

    def get_competitive_awareness(self) -> dict:
        """为元认知系统提供竞争力意识数据

        返回精简的竞争力状态，用于注入元认知的认知调控。
        """
        scores = self._assess_turing_capabilities()

        # 找出最大差距（关键弱点）
        gap_ranking = self._rank_gaps(scores)
        critical_gaps = [g for g in gap_ranking if g["severity"] in ("critical", "significant")]

        # 找出领先优势
        advantages = self._identify_advantages(scores)

        overall = self._compute_competitive_score(scores)

        return {
            "competitive_rank": overall.get("rank", 0),
            "competitive_score": overall.get("turing_score", 0),
            "critical_gaps": [
                {"dim": g["dimension"], "name": g["name"],
                 "gap": g["gap_to_best"], "best_by": g["best_competitor"]}
                for g in critical_gaps[:3]
            ],
            "top_advantages": [
                {"dim": a["dimension"], "name": a["name"], "lead": a["lead"]}
                for a in advantages[:3]
            ],
            "total_competitors": len(COMPETITOR_PROFILES),
        }

    def get_task_relevant_gaps(self, task_type: str) -> list[dict]:
        """获取与特定任务类型相关的竞争力差距

        Args:
            task_type: bug_fix / feature / refactor / debug / explain 等

        Returns:
            该任务类型中 Turing 相对竞品的关键弱点
        """
        # 任务类型到关键维度的映射
        task_dim_map = {
            "bug_fix": ["code_understanding", "error_recovery", "test_driven",
                        "reasoning_depth"],
            "feature": ["code_understanding", "multi_file_edit", "test_driven",
                        "project_awareness", "autonomous_execution"],
            "refactor": ["multi_file_edit", "code_understanding",
                         "project_awareness", "test_driven"],
            "debug": ["code_understanding", "reasoning_depth", "error_recovery",
                       "tool_use"],
            "explain": ["code_understanding", "reasoning_depth", "context_window"],
            "general": ["autonomous_execution", "tool_use", "reasoning_depth",
                        "code_understanding"],
        }

        relevant_dims = task_dim_map.get(task_type, task_dim_map["general"])
        scores = self._assess_turing_capabilities()
        gap_ranking = self._rank_gaps(scores)

        return [
            g for g in gap_ranking
            if g["dimension"] in relevant_dims and g["gap_to_best"] > 0.05
        ]

    def get_evolution_insights(self) -> dict:
        """为策略进化提供竞争力驱动的改进建议

        返回应该优先强化的策略方向。
        """
        scores = self._assess_turing_capabilities()
        gap_ranking = self._rank_gaps(scores)

        # 将差距转化为策略改进方向
        strategy_hints = []
        for gap in gap_ranking[:5]:
            dim = gap["dimension"]
            if gap["severity"] in ("critical", "significant"):
                hint = self._gap_to_strategy_hint(dim, gap)
                if hint:
                    strategy_hints.append(hint)

        return {
            "strategy_improvement_hints": strategy_hints,
            "focus_areas": [g["dimension"] for g in gap_ranking[:3]
                           if g["gap_to_best"] > 0.1],
            "maintain_areas": [g["dimension"] for g in gap_ranking
                              if g["severity"] == "leading"],
        }

    def _gap_to_strategy_hint(self, dimension: str, gap: dict) -> dict | None:
        """将竞争力差距转化为策略改进提示"""
        hints = {
            "real_time_completion": {
                "strategy_type": "all",
                "lesson": "竞品通过 IDE 集成提供实时补全，Turing 应在非补全能力上建立更大优势",
                "action": "强化 CLI 交互体验和批量任务能力",
            },
            "context_window": {
                "strategy_type": "all",
                "lesson": "上下文窗口受限，需更积极地使用 RAG 和智能压缩来弥补",
                "action": "优先使用 rag_search 检索，避免加载大文件全文",
            },
            "code_understanding": {
                "strategy_type": "all",
                "lesson": "代码理解深度不足，应更多使用 AST 分析工具辅助理解",
                "action": "在 bug_fix 和 refactor 任务中优先调用 code_structure 和 call_graph",
            },
            "autonomous_execution": {
                "strategy_type": "feature",
                "lesson": "自主执行能力差距来自多步任务编排，应改进任务分解粒度",
                "action": "将大任务分解为 ≤3 步的子任务，每步验证后再继续",
            },
            "multi_file_edit": {
                "strategy_type": "refactor",
                "lesson": "多文件编辑能力需要先用 impact_analysis 评估范围再行动",
                "action": "重构前必须调用 impact_analysis，编辑后运行 run_tests",
            },
            "test_driven": {
                "strategy_type": "all",
                "lesson": "测试驱动能力需要更主动地生成和运行测试",
                "action": "每次代码修改后自动调用 run_tests，缺少测试时主动 generate_tests",
            },
        }

        hint_data = hints.get(dimension)
        if not hint_data:
            return None

        return {
            "dimension": dimension,
            "gap_severity": gap["severity"],
            "gap_to_best": gap["gap_to_best"],
            "best_competitor": gap["best_competitor"],
            **hint_data,
        }

    # ===== 持久化 =====

    def _load_history(self) -> list[dict]:
        if self._analysis_path.exists():
            try:
                with open(self._analysis_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save_history(self):
        # 保留最近 50 次分析
        self._history = self._history[-50:]
        with open(self._analysis_path, "w", encoding="utf-8") as f:
            json.dump(self._history, f, ensure_ascii=False, indent=2)
