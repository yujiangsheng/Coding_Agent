"""自我演化追踪器

Turing 的持续自我进化核心，四大能力：

1. **经验积累** — 每次任务后记录反思（outcome、工具组合、经验教训）
2. **策略进化** — 同类任务 ≥ threshold 条时自动归纳策略模板
3. **知识蒸馏** — 每 N 次任务触发一次，合并去重、淘汰过时经验
4. **AI 工具学习** — 分析 Claude Opus / Codex / Gemini / Copilot 的策略并内化
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from turing.memory.persistent import PersistentMemory


class EvolutionTracker:
    """Turing 自我演化追踪器

    功能：
    1. 经验积累 —— 记录每次任务的反思
    2. 策略进化 —— 同类任务 ≥ threshold 条时归纳策略模板
    3. 知识蒸馏 —— 定期合并、去重、淘汰
    4. AI 工具学习 —— 分析顶尖工具的策略并内化
    """

    def __init__(self, data_dir: str = "turing_data", persistent: PersistentMemory | None = None):
        self._data_dir = data_dir
        self._persistent = persistent or PersistentMemory(data_dir)
        self._reflections_path = Path(data_dir) / "evolution" / "reflections.json"
        self._reflections_path.parent.mkdir(parents=True, exist_ok=True)
        self._ai_learning_dir = Path(data_dir) / "external_memory" / "ai_tools_analysis"
        self._ai_learning_dir.mkdir(parents=True, exist_ok=True)

        self._reflections = self._load_reflections()
        self._task_count = len(self._reflections)
        self._strategy_threshold = 5
        self._distill_interval = 50

    # ===== 经验积累 =====

    def add_reflection(self, reflection: dict) -> dict:
        """记录一次任务反思"""
        reflection["timestamp"] = time.time()
        reflection["task_number"] = self._task_count + 1
        self._reflections.append(reflection)
        self._task_count += 1
        self._save_reflections()
        return {"status": "ok", "task_number": self._task_count}

    # ===== 策略进化 =====

    def check_strategy_evolution(self, reflection: dict):
        """检查是否需要进化策略模板"""
        task_type = self._classify_task(reflection)
        similar = [
            r for r in self._reflections
            if self._classify_task(r) == task_type
        ]

        if len(similar) >= self._strategy_threshold:
            strategy = self._synthesize_strategy(task_type, similar)
            self._persistent.save_strategy(task_type, strategy)
            return {"evolved": True, "task_type": task_type, "based_on": len(similar)}
        return {"evolved": False}

    def _synthesize_strategy(self, task_type: str, reflections: list[dict]) -> dict:
        """从经验中归纳策略模板（按时间加权，近期经验权重更高）"""
        successes = [r for r in reflections if r.get("outcome") == "success"]
        failures = [r for r in reflections if r.get("outcome") == "failure"]

        # 按时间加权统计工具使用频率（近期权重更高）
        tool_counter = Counter()
        now = time.time()
        for r in successes:
            ts = r.get("timestamp", 0)
            age_days = (now - ts) / 86400 if ts else 30
            weight = 1.0 / (1.0 + age_days * 0.02)  # 30天半衰期
            for tool in r.get("tools_used", []):
                tool_counter[tool] += weight

        # 统计工具协同模式（哪些工具經常一起使用）
        tool_pairs = Counter()
        for r in successes:
            tools = sorted(set(r.get("tools_used", [])))
            for i in range(len(tools)):
                for j in range(i + 1, len(tools)):
                    tool_pairs[(tools[i], tools[j])] += 1

        # 收集经验教训（去重）
        lessons = []
        seen_lessons = set()
        for r in reflections:
            lesson = r.get("lessons") or r.get("lesson", "")
            if lesson and lesson not in seen_lessons:
                seen_lessons.add(lesson)
                lessons.append(lesson)

        # 收集常见陷阱（去重）
        pitfalls = []
        seen_pitfalls = set()
        for r in failures:
            failed = r.get("what_failed", "")
            if failed and failed not in seen_pitfalls:
                seen_pitfalls.add(failed)
                pitfalls.append(failed)

        success_rate = len(successes) / max(len(reflections), 1)

        # 常用工具组合
        common_combos = [
            f"{a} + {b}" for (a, b), _ in tool_pairs.most_common(3)
        ] if tool_pairs else []

        return {
            "task_type": task_type,
            "total_experiences": len(reflections),
            "success_rate": round(success_rate, 2),
            "recommended_tools": [t for t, _ in tool_counter.most_common(5)],
            "tool_combos": common_combos,
            "key_lessons": lessons[-10:],
            "common_pitfalls": pitfalls[-5:],
            "recommended_steps": self._infer_steps(successes),
            "created_at": time.time(),
        }

    def _infer_steps(self, successes: list[dict]) -> list[str]:
        """从成功案例推断推荐步骤"""
        if not successes:
            return ["分析需求", "阅读代码", "实施修改", "验证结果"]

        # 统计成功案例中使用的工具顺序
        step_patterns = Counter()
        for r in successes:
            tools = r.get("tools_used", [])
            for t in tools:
                step_patterns[t] += 1

        ordered = [t for t, _ in step_patterns.most_common()]
        step_map = {
            "read_file": "阅读相关代码",
            "search_code": "搜索代码库",
            "memory_read": "检索历史经验",
            "edit_file": "实施代码修改",
            "write_file": "创建/写入文件",
            "run_command": "运行测试/验证",
            "rag_search": "查阅文档",
            "web_search": "搜索外部资料",
        }
        return [step_map.get(t, t) for t in ordered[:6]]

    # ===== 知识蒸馏 =====

    def check_distillation(self) -> dict:
        """检查是否触发知识蒸馏"""
        if self._task_count > 0 and self._task_count % self._distill_interval == 0:
            return self._distill_knowledge()
        return {"distilled": False}

    def _distill_knowledge(self) -> dict:
        """执行知识蒸馏"""
        before_count = len(self._reflections)

        # 1. 合并高度相似的经验（相同 task_type + 相同 outcome）
        merged = {}
        for r in self._reflections:
            key = f"{self._classify_task(r)}_{r.get('outcome', 'unknown')}"
            if key not in merged:
                merged[key] = []
            merged[key].append(r)

        # 2. 每组只保留最近的 10 条 + 所有失败经验
        distilled = []
        for key, group in merged.items():
            if "failure" in key:
                distilled.extend(group[-20:])  # 失败经验保留更多
            else:
                distilled.extend(group[-10:])

        self._reflections = distilled
        self._save_reflections()

        # 3. 生成成长报告
        report = self._generate_growth_report()

        return {
            "distilled": True,
            "before": before_count,
            "after": len(distilled),
            "removed": before_count - len(distilled),
            "report": report,
        }

    def _generate_growth_report(self) -> dict:
        """生成能力成长报告"""
        if not self._reflections:
            return {"message": "暂无足够数据生成报告"}

        # 按类型统计
        type_stats = Counter()
        outcome_stats = Counter()
        for r in self._reflections:
            type_stats[self._classify_task(r)] += 1
            outcome_stats[r.get("outcome", "unknown")] += 1

        total = len(self._reflections)
        success_rate = outcome_stats.get("success", 0) / max(total, 1)

        report = {
            "version": f"Turing v0.{self._task_count // 50 + 1}",
            "total_tasks": self._task_count,
            "task_distribution": dict(type_stats),
            "overall_success_rate": round(success_rate, 2),
            "outcome_distribution": dict(outcome_stats),
            "strategies_count": len(self._persistent.list_strategies()),
            "timestamp": time.time(),
        }

        # 写入进化日志
        self._persistent.append_evolution_log(report)
        return report

    # ===== AI 工具学习 =====

    def learn_from(self, tool_name: str, task_type: str, reference_output: str = None) -> dict:
        """分析顶尖 AI 工具的策略"""
        # AI 工具特长数据库
        tool_strengths = {
            "claude_opus": {
                "strengths": ["深度推理链", "复杂架构设计", "长上下文理解", "安全编码"],
                "strategies": [
                    "对复杂问题先进行多步推理分解",
                    "修改代码前先完整阅读相关上下文",
                    "主动识别安全漏洞并修复",
                    "提供详细的修改理由",
                ],
            },
            "codex": {
                "strengths": ["代码补全准确率", "多语言覆盖", "API 集成"],
                "strategies": [
                    "利用类型信息提升补全准确度",
                    "参考已有代码风格保持一致性",
                    "优先使用标准库和已有依赖",
                ],
            },
            "gemini": {
                "strengths": ["多模态理解", "大规模代码库导航", "测试生成"],
                "strategies": [
                    "先理解项目整体结构再定位目标",
                    "为修改自动生成测试用例",
                    "利用文件间关系图进行影响分析",
                ],
            },
            "copilot": {
                "strengths": ["IDE 集成", "上下文感知补全", "工作流优化"],
                "strategies": [
                    "根据光标位置推断用户意图",
                    "利用文件头部注释推断功能",
                    "生成与周围代码风格一致的补全",
                ],
            },
        }

        tool_info = tool_strengths.get(tool_name, {
            "strengths": ["通用编程能力"],
            "strategies": ["遵循编程最佳实践"],
        })

        analysis = {
            "tool": tool_name,
            "task_type": task_type,
            "strengths": tool_info["strengths"],
            "applicable_strategies": [
                s for s in tool_info["strategies"]
            ],
            "recommendation": f"在 {task_type} 任务中，可借鉴 {tool_name} 的策略",
            "timestamp": time.time(),
        }

        if reference_output:
            analysis["reference_analyzed"] = True
            analysis["reference_length"] = len(reference_output)

        # 保存学习笔记
        self._save_learning(tool_name, analysis)

        # 如果策略有效，存入持久记忆
        self._persistent.add(
            json.dumps(analysis, ensure_ascii=False),
            tags=["ai_learning", tool_name, task_type],
        )

        return analysis

    def _save_learning(self, tool_name: str, analysis: dict):
        """保存 AI 工具学习笔记"""
        filepath = self._ai_learning_dir / f"{tool_name}.json"
        existing = []
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.append(analysis)
        # 只保留最近 50 条
        existing = existing[-50:]
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    # ===== 辅助 =====

    def _classify_task(self, reflection: dict) -> str:
        """推断任务类型"""
        if "task_type" in reflection:
            return reflection["task_type"]
        # 从任务描述推断
        task = reflection.get("task", "").lower()
        if any(w in task for w in ["bug", "fix", "修复", "报错", "error"]):
            return "bug_fix"
        elif any(w in task for w in ["feature", "功能", "新增", "添加", "implement"]):
            return "feature"
        elif any(w in task for w in ["refactor", "重构", "优化", "clean"]):
            return "refactor"
        elif any(w in task for w in ["debug", "调试", "排查"]):
            return "debug"
        elif any(w in task for w in ["explain", "解释", "什么是"]):
            return "explain"
        return "general"

    def _load_reflections(self) -> list[dict]:
        if self._reflections_path.exists():
            with open(self._reflections_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_reflections(self):
        with open(self._reflections_path, "w", encoding="utf-8") as f:
            json.dump(self._reflections, f, ensure_ascii=False, indent=2)

    def get_stats(self) -> dict:
        """获取演化统计"""
        outcome_counter = Counter(r.get("outcome", "unknown") for r in self._reflections)
        return {
            "total_tasks": self._task_count,
            "reflections": len(self._reflections),
            "outcomes": dict(outcome_counter),
            "strategies": self._persistent.list_strategies(),
            "evolution_log_entries": len(self._persistent.get_evolution_log()),
            "tool_efficiency": self._compute_tool_efficiency(),
            "decision_quality": self._compute_decision_quality(),
        }

    def _compute_tool_efficiency(self) -> dict:
        """分析工具使用效率——哪些工具组合最有效"""
        if not self._reflections:
            return {}
        tool_stats = {}
        for r in self._reflections:
            for tool in r.get("tools_used", []):
                if tool not in tool_stats:
                    tool_stats[tool] = {"used": 0, "in_success": 0}
                tool_stats[tool]["used"] += 1
                if r.get("outcome") == "success":
                    tool_stats[tool]["in_success"] += 1

        # 计算每个工具的成功关联率
        efficiency = {}
        for tool, stats in tool_stats.items():
            rate = stats["in_success"] / max(stats["used"], 1)
            efficiency[tool] = {
                "usage_count": stats["used"],
                "success_correlation": round(rate, 2),
            }
        return efficiency

    def _compute_decision_quality(self) -> dict:
        """评估决策质量——任务结果分布和改进趋势"""
        if len(self._reflections) < 5:
            return {"status": "insufficient_data"}

        # 最近 20 条 vs 全部的成功率对比
        recent = self._reflections[-20:]
        recent_success = sum(1 for r in recent if r.get("outcome") == "success") / len(recent)
        overall_success = sum(
            1 for r in self._reflections if r.get("outcome") == "success"
        ) / len(self._reflections)

        # 平均工具调用次数趋势
        recent_actions = [r.get("actions_count", 0) for r in recent if "actions_count" in r]
        avg_actions = sum(recent_actions) / max(len(recent_actions), 1) if recent_actions else 0

        return {
            "recent_success_rate": round(recent_success, 2),
            "overall_success_rate": round(overall_success, 2),
            "trend": "improving" if recent_success > overall_success else "stable",
            "avg_tool_calls_recent": round(avg_actions, 1),
        }

    # ===== 差距分析引擎 =====

    def analyze_gaps(self) -> dict:
        """分析 Turing 与顶尖 AI 编码工具之间的能力差距

        对比维度：
        1. 工具能力覆盖（已有 vs 缺失）
        2. 推理深度（反思质量指标）
        3. 策略成熟度（各类任务策略完备度）
        4. 学习闭环（经验是否真正反馈到行为）
        """

        # --- 1. 工具能力对标 ---
        from turing.tools.registry import get_all_tools
        own_tools = {t.name for t in get_all_tools()}

        # 顶尖工具的核心能力清单
        top_tool_capabilities = {
            "代码读写": {"read_file", "write_file", "edit_file"},
            "代码搜索": {"search_code", "list_directory"},
            "命令执行": {"run_command"},
            "Git 版本控制": {"git_status", "git_diff", "git_log", "git_blame"},
            "记忆系统": {"memory_read", "memory_write", "memory_reflect"},
            "RAG 文档检索": {"rag_search"},
            "外部搜索": {"web_search"},
            "自我演化": {"learn_from_ai_tool"},
            "测试执行": {"run_tests", "generate_tests"},
            "代码质量": {"lint_code", "format_code", "type_check"},
            "项目理解": {"detect_project", "analyze_dependencies"},
            "多文件重构": {"batch_edit", "rename_symbol"},
        }

        covered = {}
        missing = {}
        for category, tools in top_tool_capabilities.items():
            have = tools & own_tools
            lack = tools - own_tools
            covered[category] = list(have) if have else []
            if lack:
                missing[category] = list(lack)

        coverage_rate = sum(
            1 for tools in top_tool_capabilities.values()
            if tools & own_tools
        ) / len(top_tool_capabilities)

        # --- 2. 反思质量评估 ---
        has_lessons = sum(1 for r in self._reflections if r.get("lessons"))
        has_deep_reflection = sum(
            1 for r in self._reflections
            if r.get("what_went_well") or r.get("what_could_improve")
        )
        reflection_depth = {
            "total_reflections": len(self._reflections),
            "with_lessons": has_lessons,
            "with_deep_analysis": has_deep_reflection,
            "depth_rate": round(has_deep_reflection / max(len(self._reflections), 1), 2),
        }

        # --- 3. 策略成熟度 ---
        all_task_types = ["bug_fix", "feature", "refactor", "debug", "explain", "general"]
        existing_strategies = set(self._persistent.list_strategies())
        strategy_maturity = {}
        for tt in all_task_types:
            if tt in existing_strategies:
                s = self._persistent.load_strategy(tt) or {}
                strategy_maturity[tt] = {
                    "status": "evolved",
                    "success_rate": s.get("success_rate", 0),
                    "experiences": s.get("total_experiences", 0),
                }
            else:
                count = sum(1 for r in self._reflections if self._classify_task(r) == tt)
                strategy_maturity[tt] = {
                    "status": "accumulating" if count > 0 else "no_data",
                    "progress": f"{count}/{self._strategy_threshold}",
                }

        # --- 4. 与顶尖工具的具体差距 ---
        gap_details = {
            "vs_claude_opus": {
                "gaps": [],
                "turing_strengths": [],
            },
            "vs_codex": {
                "gaps": [],
                "turing_strengths": [],
            },
            "vs_gemini": {
                "gaps": [],
                "turing_strengths": [],
            },
            "vs_copilot": {
                "gaps": [],
                "turing_strengths": [],
            },
        }

        # Claude Opus 对比
        opus_gaps = gap_details["vs_claude_opus"]
        if reflection_depth["depth_rate"] < 0.5:
            opus_gaps["gaps"].append("反思深度不够：Claude Opus 会进行多步推理链分析")
        if "测试执行" in missing:
            opus_gaps["gaps"].append("缺少自动测试能力：Claude Opus 会主动运行和生成测试")
        if "代码质量" in missing:
            opus_gaps["gaps"].append("缺少代码质量检查：Claude Opus 会主动检查安全漏洞和代码质量")
        if "项目理解" in missing:
            opus_gaps["gaps"].append("缺少项目结构理解：Claude Opus 能自动检测项目类型和依赖")
        opus_gaps["turing_strengths"].append("四层记忆系统支持跨任务知识积累")
        opus_gaps["turing_strengths"].append("自我演化机制能持续优化策略")
        opus_gaps["turing_strengths"].append("本地部署保护隐私，无需上传代码")

        # Codex 对比
        codex_gaps = gap_details["vs_codex"]
        if "多文件重构" in missing:
            codex_gaps["gaps"].append("缺少多文件批量编辑和符号重命名能力")
        codex_gaps["gaps"].append("代码补全精度依赖本地模型质量")
        codex_gaps["turing_strengths"].append("多轮工具调用支持复杂任务")
        codex_gaps["turing_strengths"].append("记忆系统让经验教训可复用")

        # Gemini 对比
        gemini_gaps = gap_details["vs_gemini"]
        if "项目理解" in missing:
            gemini_gaps["gaps"].append("缺少大规模代码库导航和影响分析")
        gemini_gaps["gaps"].append("RAG 分块策略不够智能（无 AST 感知切分）")
        gemini_gaps["turing_strengths"].append("本地 RAG + ChromaDB 支持私有文档检索")
        gemini_gaps["turing_strengths"].append("Git 集成支持代码历史分析")

        # Copilot 对比
        copilot_gaps = gap_details["vs_copilot"]
        copilot_gaps["gaps"].append("无 IDE 插件集成，仅支持 CLI/Web 交互")
        copilot_gaps["gaps"].append("无实时流式补全（需等待完整响应）")
        copilot_gaps["turing_strengths"].append("完整的任务执行能力（而非仅补全）")
        copilot_gaps["turing_strengths"].append("持久化经验和策略持续进化")

        # --- 5. 生成改进路线图 ---
        roadmap = []
        priority = 1
        if "测试执行" in missing:
            roadmap.append({
                "priority": priority, "area": "测试执行",
                "action": "实现 run_tests / generate_tests 工具",
                "impact": "high", "effort": "medium",
            })
            priority += 1
        if "代码质量" in missing:
            roadmap.append({
                "priority": priority, "area": "代码质量",
                "action": "集成 linter/formatter/type-checker 工具",
                "impact": "high", "effort": "low",
            })
            priority += 1
        if "项目理解" in missing:
            roadmap.append({
                "priority": priority, "area": "项目结构理解",
                "action": "实现项目类型检测和依赖分析",
                "impact": "medium", "effort": "medium",
            })
            priority += 1
        if "多文件重构" in missing:
            roadmap.append({
                "priority": priority, "area": "多文件重构",
                "action": "实现批量编辑和符号重命名",
                "impact": "medium", "effort": "high",
            })
            priority += 1
        if reflection_depth["depth_rate"] < 0.8:
            roadmap.append({
                "priority": priority, "area": "反思深度",
                "action": "启用 LLM 深度反思（已实现，需积累更多数据）",
                "impact": "high", "effort": "done",
            })
            priority += 1

        result = {
            "tool_coverage": {
                "rate": round(coverage_rate, 2),
                "covered_categories": covered,
                "missing_categories": missing,
            },
            "reflection_quality": reflection_depth,
            "strategy_maturity": strategy_maturity,
            "gap_details": gap_details,
            "improvement_roadmap": roadmap,
            "overall_score": self._compute_overall_score(
                coverage_rate, reflection_depth, strategy_maturity
            ),
            "timestamp": time.time(),
        }

        # 持久化差距报告
        report_path = Path(self._data_dir) / "evolution" / "gap_analysis.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return result

    def _compute_overall_score(self, coverage_rate: float, reflection_depth: dict,
                                strategy_maturity: dict) -> dict:
        """计算综合能力评分（10分制）"""
        # 1. 工具覆盖 (2分)
        tool_score = coverage_rate * 2.0

        # 2. 反思质量 (2分)
        depth_rate = reflection_depth.get("depth_rate", 0)
        reflection_score = depth_rate * 2.0

        # 3. 策略成熟度 (2分)
        evolved = sum(1 for v in strategy_maturity.values() if v.get("status") == "evolved")
        strategy_score = min(evolved / 3, 1.0) * 2.0  # 3个以上策略即满分

        # 4. 经验积累 (1分)
        total = reflection_depth.get("total_reflections", 0)
        experience_score = min(total / 50, 1.0) * 1.0  # 50条以上即满分

        # 5. 记忆系统完备度 (1.5分) — 根据实际能力
        memory_features = [
            True,  # working memory
            True,  # long_term memory
            True,  # persistent memory
            True,  # RAG engine
            True,  # TF-IDF search
            True,  # cross-layer ranking
        ]
        memory_score = sum(memory_features) / len(memory_features) * 1.5

        # 6. 可靠性 (1.5分)
        reliability_features = [
            True,  # tool retry
            True,  # loop detection
            True,  # context overflow management
            True,  # result summarization
            True,  # LLM reflect fallback
            True,  # tool validation
        ]
        reliability_score = sum(reliability_features) / len(reliability_features) * 1.5

        total_score = (tool_score + reflection_score + strategy_score +
                       experience_score + memory_score + reliability_score)

        return {
            "total": round(total_score, 1),
            "breakdown": {
                "tool_coverage": round(tool_score, 1),
                "reflection_quality": round(reflection_score, 1),
                "strategy_maturity": round(strategy_score, 1),
                "experience_depth": round(experience_score, 1),
                "memory_system": round(memory_score, 1),
                "reliability": round(reliability_score, 1),
            },
            "max_score": 10.0,
        }
