"""元认知引擎 — Turing 自我意识与认知调控核心

元认知 (Metacognition) 是"对思考的思考"，让 Turing 具备：

1. **认知监控 (Monitoring)** — 实时评估推理质量、置信度、认知负荷
2. **认知调控 (Regulation)** — 根据监控信号动态调整策略、深度、工具选择
3. **认知知识 (Knowledge)** — 对自身能力边界的认知，知道何时该深入、何时该求助
4. **置信校准 (Calibration)** — 判断输出可信度，防止过度自信或过度犹豫
5. **认知偏差检测 (Bias Detection)** — 识别确认偏差、锚定偏差、可得性偏差

元认知评分维度（6维雷达）：
    - 监控精度 (monitoring_accuracy)：能否正确识别推理中的薄弱环节
    - 调控有效性 (regulation_effectiveness)：策略调整是否改善了结果
    - 置信校准度 (confidence_calibration)：预测置信度 vs 实际成功率
    - 认知灵活性 (cognitive_flexibility)：遇到困难时能否切换方案
    - 知识边界感 (boundary_awareness)：是否知道自己知道/不知道什么
    - 反思深度 (reflection_depth)：反思是否真正提炼出可迁移的知识
"""

from __future__ import annotations

import json
import time
from collections import Counter, deque
from pathlib import Path
from typing import Any


class MetacognitiveState:
    """单次任务的元认知状态快照"""

    __slots__ = (
        "confidence", "cognitive_load", "reasoning_depth",
        "strategy_switches", "uncertainty_points", "bias_alerts",
        "phase", "start_time", "checkpoints",
    )

    def __init__(self):
        self.confidence: float = 0.5          # 当前任务置信度 [0, 1]
        self.cognitive_load: float = 0.0      # 认知负荷 [0, 1]
        self.reasoning_depth: str = "medium"  # shallow / medium / deep
        self.strategy_switches: int = 0       # 策略切换次数
        self.uncertainty_points: list[str] = []  # 不确定性节点
        self.bias_alerts: list[str] = []      # 偏差警报
        self.phase: str = "init"              # 当前认知阶段
        self.start_time: float = time.time()
        self.checkpoints: list[dict] = []     # 认知检查点

    def snapshot(self) -> dict:
        """返回当前元认知状态的快照字典。"""
        return {
            "confidence": round(self.confidence, 3),
            "cognitive_load": round(self.cognitive_load, 3),
            "reasoning_depth": self.reasoning_depth,
            "strategy_switches": self.strategy_switches,
            "uncertainty_points": self.uncertainty_points[-5:],
            "bias_alerts": self.bias_alerts[-5:],
            "phase": self.phase,
            "elapsed": round(time.time() - self.start_time, 1),
            "checkpoints": len(self.checkpoints),
        }


class MetacognitiveEngine:
    """Turing 元认知引擎

    在每个任务执行周期中进行实时认知监控和调控，
    跨任务积累元认知知识以持续提升自我意识水平。
    """

    def __init__(self, data_dir: str = "turing_data"):
        self._data_dir = data_dir
        self._meta_path = Path(data_dir) / "evolution" / "metacognition.json"
        self._meta_path.parent.mkdir(parents=True, exist_ok=True)

        # 跨任务的元认知记录
        self._meta_records: list[dict] = self._load_records()

        # 当前任务的元认知状态
        self._current: MetacognitiveState | None = None

        # 置信校准历史 (predicted_confidence, actual_success)
        self._calibration_history: list[tuple[float, bool]] = []
        self._load_calibration()

        # 认知模式库：记录哪些认知模式在何种任务中有效
        self._cognitive_patterns: dict[str, list[dict]] = {}

    # ===== 任务生命周期 =====

    def begin_task(self, task_description: str, task_type: str = "general") -> dict:
        """开始一个新任务的元认知监控"""
        self._current = MetacognitiveState()

        # 基于历史评估初始置信度
        initial_confidence = self._estimate_initial_confidence(task_type)
        self._current.confidence = initial_confidence

        # 评估认知负荷
        complexity = self._estimate_complexity(task_description)
        self._current.cognitive_load = complexity
        self._current.phase = "understanding"

        # 推荐推理深度
        if complexity > 0.7:
            self._current.reasoning_depth = "deep"
        elif complexity < 0.3:
            self._current.reasoning_depth = "shallow"
        else:
            self._current.reasoning_depth = "medium"

        return {
            "initial_confidence": round(initial_confidence, 3),
            "estimated_complexity": round(complexity, 3),
            "recommended_depth": self._current.reasoning_depth,
            "cognitive_advisory": self._generate_advisory(task_type, complexity),
        }

    def checkpoint(self, event_type: str, details: dict) -> dict | None:
        """在关键决策点进行元认知检查

        event_type: tool_selection | strategy_switch | error_encountered |
                    mid_task_review | output_generation
        """
        if self._current is None:
            return None

        signals = {}

        if event_type == "tool_selection":
            signals = self._monitor_tool_selection(details)
        elif event_type == "strategy_switch":
            self._current.strategy_switches += 1
            signals = self._monitor_strategy_switch(details)
        elif event_type == "error_encountered":
            signals = self._monitor_error(details)
        elif event_type == "mid_task_review":
            signals = self._mid_task_review(details)
        elif event_type == "output_generation":
            signals = self._monitor_output(details)

        # 记录检查点
        checkpoint = {
            "event": event_type,
            "time": time.time() - self._current.start_time,
            "confidence": self._current.confidence,
            "signals": signals,
        }
        self._current.checkpoints.append(checkpoint)

        # 生成调控建议
        regulation = self._regulate(signals)
        if regulation:
            checkpoint["regulation"] = regulation

        return regulation

    def end_task(self, outcome: str, reflection: dict | None = None) -> dict:
        """结束任务，生成元认知评估报告"""
        if self._current is None:
            return {"error": "no_active_task"}

        # 校准置信度
        success = outcome == "success"
        self._calibration_history.append((self._current.confidence, success))

        # 生成元认知评估
        meta_assessment = {
            "task_outcome": outcome,
            "final_state": self._current.snapshot(),
            "metacognitive_quality": self._assess_metacognitive_quality(),
            "calibration_error": self._compute_calibration_error(),
            "cognitive_efficiency": self._compute_cognitive_efficiency(),
            "lessons_meta": self._extract_meta_lessons(outcome, reflection),
            "timestamp": time.time(),
        }

        self._meta_records.append(meta_assessment)
        self._save_records()
        self._save_calibration()

        # 清理当前状态
        self._current = None

        return meta_assessment

    # ===== 认知监控 =====

    def _monitor_tool_selection(self, details: dict) -> dict:
        """监控工具选择的合理性"""
        tool_name = details.get("tool", "")
        task_phase = self._current.phase if self._current else "unknown"
        signals = {"type": "tool_selection", "tool": tool_name}

        # 检查工具是否适合当前阶段
        phase_tools = {
            "understanding": {"read_file", "search_code", "list_directory",
                              "detect_project", "analyze_dependencies",
                              "code_structure", "call_graph", "memory_read"},
            "planning": {"memory_read", "rag_search", "web_search",
                         "complexity_report", "impact_analysis"},
            "execution": {"edit_file", "write_file", "run_command",
                          "batch_edit", "rename_symbol", "generate_file"},
            "verification": {"run_tests", "lint_code", "type_check",
                             "run_command", "format_code"},
            "debugging": {"read_file", "search_code", "git_diff",
                          "git_blame", "run_tests", "edit_file"},
        }

        appropriate_tools = phase_tools.get(task_phase, set())
        if tool_name in appropriate_tools:
            signals["phase_alignment"] = "aligned"
            self._current.confidence = min(self._current.confidence + 0.02, 1.0)
        elif tool_name:
            signals["phase_alignment"] = "misaligned"
            signals["advisory"] = (
                f"工具 {tool_name} 通常不在 {task_phase} 阶段使用，"
                "请确认是否有特殊原因"
            )
            self._current.uncertainty_points.append(
                f"工具阶段偏离: {tool_name} @ {task_phase}"
            )

        return signals

    def _monitor_strategy_switch(self, details: dict) -> dict:
        """监控策略切换的合理性"""
        reason = details.get("reason", "")
        signals = {"type": "strategy_switch", "reason": reason}

        if self._current.strategy_switches > 3:
            signals["warning"] = "策略切换过于频繁，可能存在决策振荡"
            self._current.bias_alerts.append("决策振荡: 频繁切换策略")
            self._current.confidence *= 0.85
        elif self._current.strategy_switches == 1:
            # 第一次切换通常是合理的适应
            signals["assessment"] = "首次策略调整，认知灵活性表现"
            self._current.confidence = min(self._current.confidence + 0.05, 1.0)

        return signals

    def _monitor_error(self, details: dict) -> dict:
        """监控错误响应模式"""
        error_msg = details.get("error", "")
        tool_name = details.get("tool", "")
        retry_count = details.get("retry_count", 0)
        signals = {"type": "error", "tool": tool_name}

        # 置信度衰减
        self._current.confidence *= 0.9

        # 检测确认偏差（重复尝试相同方案）
        if retry_count >= 2:
            signals["bias_alert"] = "确认偏差: 多次重试相同失败方案"
            self._current.bias_alerts.append(
                f"确认偏差: 对 {tool_name} 重试 {retry_count} 次"
            )
            signals["regulation"] = "应停止重试，分析根因或切换方案"

        # 检测锚定偏差（始终使用同一工具）
        if self._current.checkpoints:
            recent_tools = [
                cp.get("signals", {}).get("tool", "")
                for cp in self._current.checkpoints[-5:]
                if cp.get("event") == "tool_selection"
            ]
            if len(recent_tools) >= 3 and len(set(recent_tools)) == 1:
                signals["bias_alert"] = f"锚定偏差: 过度依赖 {recent_tools[0]}"
                self._current.bias_alerts.append(
                    f"锚定偏差: 持续使用 {recent_tools[0]}"
                )

        return signals

    def _mid_task_review(self, details: dict) -> dict:
        """中期任务审查"""
        iteration = details.get("iteration", 0)
        progress = details.get("progress", "")
        signals = {"type": "mid_review", "iteration": iteration}

        if self._current is None:
            return signals

        elapsed = time.time() - self._current.start_time

        # 时间/迭代比评估
        if iteration > 0 and elapsed / iteration > 30:
            signals["efficiency_warning"] = "每次迭代耗时较长，考虑简化方案"
            self._current.cognitive_load = min(self._current.cognitive_load + 0.1, 1.0)

        # 检查是否陷入局部循环
        if iteration > 8 and self._current.confidence < 0.3:
            signals["escalation"] = "置信度持续低迷，建议重新评估任务可行性"
            self._current.phase = "re-planning"

        # 更新阶段
        if iteration <= 2:
            self._current.phase = "understanding"
        elif iteration <= 5:
            self._current.phase = "execution"
        else:
            self._current.phase = "verification"

        return signals

    def _monitor_output(self, details: dict) -> dict:
        """监控输出生成质量"""
        output_length = details.get("length", 0)
        has_code = details.get("has_code", False)
        signals = {"type": "output_check"}

        # 过短输出可能表示理解不足
        if output_length < 20 and has_code:
            signals["concern"] = "输出过短，可能遗漏关键细节"
            self._current.confidence *= 0.95

        return signals

    # ===== 认知调控 =====

    def _regulate(self, signals: dict) -> dict | None:
        """基于监控信号生成调控指令"""
        if self._current is None:
            return None

        regulations = []

        # 置信度过低 → 建议增加验证
        if self._current.confidence < 0.3:
            regulations.append({
                "action": "increase_verification",
                "reason": f"置信度偏低 ({self._current.confidence:.2f})",
                "suggestion": "增加验证步骤，使用 run_tests 或 run_command 确认",
            })

        # 认知负荷过高 → 建议分解任务
        if self._current.cognitive_load > 0.8:
            regulations.append({
                "action": "decompose_task",
                "reason": f"认知负荷过高 ({self._current.cognitive_load:.2f})",
                "suggestion": "将当前任务拆分为更小的子任务逐步完成",
            })

        # 检测到偏差 → 注入纠偏提示
        if self._current.bias_alerts:
            latest_bias = self._current.bias_alerts[-1]
            regulations.append({
                "action": "debias",
                "reason": latest_bias,
                "suggestion": "暂停当前方案，从头审视问题，考虑完全不同的解法",
            })

        # 推理深度不匹配 → 调整
        if (self._current.cognitive_load > 0.6 and
                self._current.reasoning_depth == "shallow"):
            self._current.reasoning_depth = "deep"
            regulations.append({
                "action": "deepen_reasoning",
                "reason": "任务复杂度超出浅层推理能力",
                "suggestion": "切换到深度推理模式，进行 Chain-of-Thought 分析",
            })

        if not regulations:
            return None

        return {
            "regulations": regulations,
            "current_confidence": round(self._current.confidence, 3),
            "current_load": round(self._current.cognitive_load, 3),
        }

    # ===== 元认知评估 =====

    def _assess_metacognitive_quality(self) -> dict:
        """评估本次任务的元认知质量（6维）"""
        if self._current is None:
            return {}

        state = self._current

        # 1. 监控精度：是否在关键点进行了检查
        checkpoints_count = len(state.checkpoints)
        monitoring = min(checkpoints_count / 5, 1.0)  # 5 个检查点为满分

        # 2. 调控有效性：策略切换是否带来改善
        regulation_effective = 1.0
        if state.strategy_switches > 3:
            regulation_effective = 0.5  # 过度切换扣分
        elif state.strategy_switches == 0 and state.confidence < 0.4:
            regulation_effective = 0.3  # 该切换没切换

        # 3. 置信校准：当前任务的置信度波动合理性
        confidence_stability = 1.0
        if state.checkpoints:
            confs = [cp["confidence"] for cp in state.checkpoints]
            if len(confs) > 1:
                variance = sum((c - sum(confs)/len(confs))**2 for c in confs) / len(confs)
                confidence_stability = max(0, 1.0 - variance * 4)

        # 4. 认知灵活性：面对困难是否调整过方案
        flexibility = 0.5  # 基线
        if state.strategy_switches > 0:
            flexibility = min(0.5 + state.strategy_switches * 0.2, 1.0)
        if state.bias_alerts:
            flexibility -= 0.1 * len(state.bias_alerts)
        flexibility = max(0, min(flexibility, 1.0))

        # 5. 知识边界感：有没有识别出不确定点
        boundary = min(len(state.uncertainty_points) * 0.25, 1.0)

        # 6. 反思深度：检查点中有多少包含实质性信号
        substantive = sum(
            1 for cp in state.checkpoints
            if len(cp.get("signals", {})) > 2
        )
        depth = min(substantive / max(checkpoints_count, 1), 1.0)

        return {
            "monitoring_accuracy": round(monitoring, 2),
            "regulation_effectiveness": round(regulation_effective, 2),
            "confidence_calibration": round(confidence_stability, 2),
            "cognitive_flexibility": round(flexibility, 2),
            "boundary_awareness": round(boundary, 2),
            "reflection_depth": round(depth, 2),
            "composite_score": round(
                (monitoring + regulation_effective + confidence_stability +
                 flexibility + boundary + depth) / 6, 2
            ),
        }

    def _compute_calibration_error(self) -> dict:
        """计算置信校准误差 — 预测置信度 vs 实际成功率"""
        if len(self._calibration_history) < 3:
            return {"status": "insufficient_data", "samples": len(self._calibration_history)}

        # 按置信度区间分桶
        buckets = {"low": [], "medium": [], "high": []}
        for conf, success in self._calibration_history:
            if conf < 0.4:
                buckets["low"].append(success)
            elif conf < 0.7:
                buckets["medium"].append(success)
            else:
                buckets["high"].append(success)

        calibration = {}
        total_error = 0
        count = 0
        for bucket_name, outcomes in buckets.items():
            if outcomes:
                actual_rate = sum(outcomes) / len(outcomes)
                expected = {"low": 0.3, "medium": 0.6, "high": 0.85}[bucket_name]
                error = abs(actual_rate - expected)
                calibration[bucket_name] = {
                    "predicted_range": bucket_name,
                    "actual_success_rate": round(actual_rate, 2),
                    "expected_rate": expected,
                    "calibration_error": round(error, 2),
                    "samples": len(outcomes),
                }
                total_error += error
                count += 1

        return {
            "buckets": calibration,
            "mean_calibration_error": round(total_error / max(count, 1), 3),
            "total_samples": len(self._calibration_history),
        }

    def _compute_cognitive_efficiency(self) -> dict:
        """计算认知效率 — 用最少的认知资源达成目标"""
        if self._current is None:
            return {}

        elapsed = time.time() - self._current.start_time
        checks = len(self._current.checkpoints)
        switches = self._current.strategy_switches
        errors = len([
            cp for cp in self._current.checkpoints
            if cp.get("event") == "error_encountered"
        ])

        # 效率 = 1 / (1 + 归一化开销)
        overhead = (switches * 0.3    # 策略切换开销
                    + errors * 0.2    # 错误开销
                    + max(0, checks - 10) * 0.05)  # 过多检查点开销
        efficiency = 1.0 / (1.0 + overhead)

        return {
            "efficiency_score": round(efficiency, 2),
            "elapsed_seconds": round(elapsed, 1),
            "total_checkpoints": checks,
            "strategy_switches": switches,
            "errors_encountered": errors,
        }

    def _extract_meta_lessons(self, outcome: str, reflection: dict | None) -> list[str]:
        """提取元认知层面的经验教训"""
        lessons = []
        if self._current is None:
            return lessons

        # 从偏差警报中学习
        if self._current.bias_alerts:
            lessons.append(
                f"认知偏差检测: 本次任务中出现 {len(self._current.bias_alerts)} 个偏差警报，"
                f"包括 {'、'.join(set(self._current.bias_alerts[:3]))}"
            )

        # 从置信度轨迹中学习
        if self._current.checkpoints:
            confs = [cp["confidence"] for cp in self._current.checkpoints]
            if confs:
                if outcome == "success" and confs[-1] < 0.4:
                    lessons.append("过度保守: 任务成功但置信度偏低，可适当提升自信")
                elif outcome == "failure" and confs[-1] > 0.7:
                    lessons.append("过度自信: 任务失败但置信度偏高，需加强验证步骤")

        # 从认知负荷中学习
        if self._current.cognitive_load > 0.7 and outcome == "failure":
            lessons.append("高负荷失败: 任务复杂度超出处理能力，下次应更早拆解任务")

        # 从策略切换中学习
        if self._current.strategy_switches > 3:
            lessons.append("策略振荡: 频繁切换策略导致效率低下，应更早确定方案")
        elif self._current.strategy_switches == 0 and outcome == "failure":
            lessons.append("认知僵化: 未尝试调整策略，遇困难时应考虑替代方案")

        return lessons

    # ===== 跨任务元认知分析 =====

    def get_metacognitive_profile(self) -> dict:
        """生成元认知能力画像 — 跨任务聚合分析"""
        if not self._meta_records:
            return {"status": "no_data", "message": "需要积累更多任务数据"}

        # 各维度历史平均
        dimensions = [
            "monitoring_accuracy", "regulation_effectiveness",
            "confidence_calibration", "cognitive_flexibility",
            "boundary_awareness", "reflection_depth",
        ]
        profile = {}
        for dim in dimensions:
            values = [
                r.get("metacognitive_quality", {}).get(dim, 0)
                for r in self._meta_records
                if dim in r.get("metacognitive_quality", {})
            ]
            if values:
                profile[dim] = {
                    "mean": round(sum(values) / len(values), 2),
                    "trend": self._compute_trend(values),
                    "samples": len(values),
                }

        # 常见偏差统计
        all_biases = []
        for r in self._meta_records:
            state = r.get("final_state", {})
            all_biases.extend(state.get("bias_alerts", []))
        bias_counter = Counter(all_biases)

        # 效率趋势
        efficiencies = [
            r.get("cognitive_efficiency", {}).get("efficiency_score", 0)
            for r in self._meta_records
            if "cognitive_efficiency" in r
        ]

        # 校准误差趋势
        calibration = self._compute_calibration_error()

        return {
            "dimension_profile": profile,
            "common_biases": dict(bias_counter.most_common(5)),
            "efficiency_trend": self._compute_trend(efficiencies) if efficiencies else "n/a",
            "calibration": calibration,
            "total_tasks_analyzed": len(self._meta_records),
            "composite_score": round(
                sum(p.get("mean", 0) for p in profile.values()) / max(len(profile), 1), 2
            ) if profile else 0,
        }

    def get_evolution_recommendations(self) -> list[dict]:
        """基于元认知画像生成自我提升建议"""
        profile = self.get_metacognitive_profile()
        if profile.get("status") == "no_data":
            return [{"area": "general", "advice": "开始积累任务经验，建立元认知基线"}]

        recommendations = []
        dims = profile.get("dimension_profile", {})

        if dims.get("monitoring_accuracy", {}).get("mean", 1) < 0.6:
            recommendations.append({
                "area": "monitoring",
                "priority": "high",
                "advice": "增加关键决策点的元认知检查频率",
                "action": "在工具选择、策略切换、错误恢复时自动触发 checkpoint",
            })

        if dims.get("confidence_calibration", {}).get("mean", 1) < 0.6:
            recommendations.append({
                "area": "calibration",
                "priority": "high",
                "advice": "置信度预测与实际结果偏差较大",
                "action": "校正初始置信度估计，增加不确定性表达",
            })

        if dims.get("cognitive_flexibility", {}).get("mean", 1) < 0.5:
            recommendations.append({
                "area": "flexibility",
                "priority": "medium",
                "advice": "遇到困难时策略切换不足",
                "action": "当连续 2 次失败时自动触发策略重评估",
            })

        if dims.get("boundary_awareness", {}).get("mean", 1) < 0.4:
            recommendations.append({
                "area": "boundary",
                "priority": "medium",
                "advice": "对自身能力边界认知不足",
                "action": "记录失败模式，建立能力边界知识库",
            })

        calibration = profile.get("calibration", {})
        if calibration.get("mean_calibration_error", 0) > 0.3:
            recommendations.append({
                "area": "overconfidence",
                "priority": "high",
                "advice": "存在系统性过度自信倾向",
                "action": "在置信度 > 0.7 时强制增加一次验证步骤",
            })

        if not recommendations:
            recommendations.append({
                "area": "maintenance",
                "priority": "low",
                "advice": "元认知系统运行良好，继续积累数据",
            })

        return recommendations

    # ===== 辅助 =====

    def _estimate_initial_confidence(self, task_type: str) -> float:
        """基于历史同类任务表现估计初始置信度"""
        if not self._meta_records:
            return 0.5  # 无数据时中性置信度

        # 同类任务的历史成功率
        relevant = [
            r for r in self._meta_records
            if r.get("task_outcome") in ("success", "failure")
        ]
        if not relevant:
            return 0.5

        success_count = sum(1 for r in relevant if r["task_outcome"] == "success")
        base = success_count / len(relevant)

        # 用贝叶斯平滑避免极端值
        alpha, beta = 2, 2  # 先验：均匀分布
        smoothed = (success_count + alpha) / (len(relevant) + alpha + beta)

        return round(smoothed, 3)

    def _estimate_complexity(self, description: str) -> float:
        """估计任务复杂度 [0, 1]"""
        score = 0.3  # 基线

        # 长度信号
        if len(description) > 200:
            score += 0.15
        elif len(description) > 100:
            score += 0.08

        # 复杂度关键词
        complex_words = [
            "重构", "refactor", "架构", "architecture", "迁移", "migrate",
            "批量", "batch", "多个文件", "系统", "system", "设计", "design",
            "性能优化", "并发", "concurrent", "分布式", "distributed",
        ]
        matches = sum(1 for w in complex_words if w in description.lower())
        score += min(matches * 0.1, 0.3)

        # 多步骤信号
        step_words = ["然后", "接着", "最后", "首先", "第一步", "步骤"]
        step_matches = sum(1 for w in step_words if w in description)
        score += min(step_matches * 0.08, 0.2)

        return min(score, 1.0)

    def _compute_trend(self, values: list[float]) -> str:
        """计算趋势方向"""
        if len(values) < 3:
            return "insufficient_data"
        mid = len(values) // 2
        first_half = sum(values[:mid]) / mid
        second_half = sum(values[mid:]) / (len(values) - mid)
        diff = second_half - first_half
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "declining"
        return "stable"

    def _generate_advisory(self, task_type: str, complexity: float) -> str:
        """生成针对当前任务的元认知建议"""
        parts = []

        if complexity > 0.7:
            parts.append("高复杂度任务：建议先进行 CoT 深度分解，不要急于行动")
        elif complexity < 0.3:
            parts.append("低复杂度任务：可快速执行，注意不要过度工程化")

        # 从历史偏差中提取提醒
        if self._meta_records:
            recent = self._meta_records[-5:]
            recent_biases = []
            for r in recent:
                recent_biases.extend(
                    r.get("final_state", {}).get("bias_alerts", [])
                )
            if recent_biases:
                common_bias = Counter(recent_biases).most_common(1)
                if common_bias:
                    parts.append(f"历史偏差提醒: 注意避免 {common_bias[0][0]}")

        if not parts:
            parts.append("正常执行，注意在关键决策点进行自我检查")

        return "；".join(parts)

    # ===== 持久化 =====

    def _load_records(self) -> list[dict]:
        """从磁盘加载元认知历史记录。"""
        if self._meta_path.exists():
            with open(self._meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_records(self):
        """持久化元认知记录到磁盘（保留最近 200 条）。"""
        # 只保留最近 200 条
        self._meta_records = self._meta_records[-200:]
        with open(self._meta_path, "w", encoding="utf-8") as f:
            json.dump(self._meta_records, f, ensure_ascii=False, indent=2)

    def _load_calibration(self):
        """从磁盘加载置信校准历史。"""
        cal_path = Path(self._data_dir) / "evolution" / "calibration.json"
        if cal_path.exists():
            with open(cal_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._calibration_history = [
                    (item["confidence"], item["success"])
                    for item in data
                ]

    def _save_calibration(self):
        """持久化置信校准数据到磁盘（保留最近 500 条）。"""
        cal_path = Path(self._data_dir) / "evolution" / "calibration.json"
        data = [
            {"confidence": c, "success": s}
            for c, s in self._calibration_history[-500:]
        ]
        with open(cal_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ===== Phase 12: 认知适应层 (Cognitive Adaptation Layer) =====

    def adapt(self) -> dict:
        """认知自适应 — 基于累积的元认知数据自动调整认知参数

        调整目标：
        1. 初始置信度基线（避免系统性高估/低估）
        2. 认知负荷阈值（适应不同难度的任务分布）
        3. 偏差检测灵敏度（减少误报/漏报）
        4. 推理深度策略（优化深浅推理的切换阈值）
        5. 检查点频率（平衡监控开销与信息量）
        """
        if len(self._meta_records) < 3:
            return {"status": "insufficient_data", "message": "需要至少 3 条元认知记录"}

        adaptations = {}
        adaptation_path = Path(self._data_dir) / "evolution" / "cognitive_adaptations.json"

        # 加载已有适应参数
        current_params = {}
        if adaptation_path.exists():
            with open(adaptation_path, "r", encoding="utf-8") as f:
                current_params = json.load(f)

        # 1. 置信度校正因子
        calibration = self._compute_calibration_error()
        if calibration.get("mean_calibration_error", 0) > 0.15:
            # 分析方向：是过度自信还是不够自信
            high_bucket = calibration.get("buckets", {}).get("high", {})
            low_bucket = calibration.get("buckets", {}).get("low", {})

            if high_bucket.get("actual_success_rate", 0.85) < 0.7:
                # 高置信度区实际成功率低 → 过度自信
                factor = 0.85  # 压低初始置信度
                adaptations["confidence_correction"] = {
                    "direction": "deflate",
                    "factor": factor,
                    "reason": "高置信预测准确率不足，系统性过度自信",
                }
            elif low_bucket.get("actual_success_rate", 0.3) > 0.5:
                # 低置信度区实际成功率高 → 过度保守
                factor = 1.15
                adaptations["confidence_correction"] = {
                    "direction": "inflate",
                    "factor": factor,
                    "reason": "低置信预测对应较高成功率，系统性过度保守",
                }

        # 2. 认知负荷阈值自适应
        load_outcomes = []
        for r in self._meta_records:
            load = r.get("final_state", {}).get("cognitive_load", 0.5)
            success = r.get("task_outcome") == "success"
            load_outcomes.append((load, success))

        if len(load_outcomes) >= 5:
            high_load_tasks = [(l, s) for l, s in load_outcomes if l > 0.6]
            low_load_tasks = [(l, s) for l, s in load_outcomes if l <= 0.6]

            high_success = (
                sum(s for _, s in high_load_tasks) / max(len(high_load_tasks), 1)
            )
            low_success = (
                sum(s for _, s in low_load_tasks) / max(len(low_load_tasks), 1)
            )

            if high_success > 0.7:
                # 高负荷也能成功 → 提高阈值（更能承受复杂任务）
                adaptations["load_threshold"] = {
                    "new_threshold": 0.85,
                    "reason": "在高认知负荷下仍保持高成功率，提升负荷容忍度",
                }
            elif high_success < 0.4:
                # 高负荷表现差 → 降低阈值（更早拆解任务）
                adaptations["load_threshold"] = {
                    "new_threshold": 0.6,
                    "reason": "高认知负荷导致失败率偏高，应更早拆解任务",
                }

        # 3. 偏差检测灵敏度自适应
        total_biases = sum(
            len(r.get("final_state", {}).get("bias_alerts", []))
            for r in self._meta_records
        )
        avg_bias_per_task = total_biases / len(self._meta_records)

        if avg_bias_per_task > 3:
            # 偏差警报过多 → 可能误报，降低灵敏度
            adaptations["bias_sensitivity"] = {
                "adjustment": "decrease",
                "reason": f"平均每任务 {avg_bias_per_task:.1f} 个偏差警报，可能存在误报",
                "new_retry_threshold": 3,  # 从 2 提高到 3 次重试才报确认偏差
            }
        elif avg_bias_per_task < 0.3 and total_biases > 0:
            # 偏差警报很少但不为零 → 可以适当提高灵敏度
            adaptations["bias_sensitivity"] = {
                "adjustment": "increase",
                "reason": "偏差检测率低，提高灵敏度以捕获更多潜在偏差",
                "new_retry_threshold": 1,
            }

        # 4. 推理深度策略自适应
        depth_outcomes = {}
        for r in self._meta_records:
            depth = r.get("final_state", {}).get("reasoning_depth", "medium")
            success = r.get("task_outcome") == "success"
            depth_outcomes.setdefault(depth, []).append(success)

        depth_success = {}
        for depth, outcomes in depth_outcomes.items():
            if outcomes:
                depth_success[depth] = sum(outcomes) / len(outcomes)

        if depth_success.get("shallow", 1.0) < 0.5:
            adaptations["depth_strategy"] = {
                "adjustment": "raise_shallow_threshold",
                "new_threshold": 0.2,  # 只有极简单的任务才用 shallow
                "reason": "浅层推理成功率偏低，提高切换到深度推理的倾向",
            }
        elif depth_success.get("deep", 0) > 0.9 and depth_success.get("medium", 0) > 0.8:
            adaptations["depth_strategy"] = {
                "adjustment": "balanced",
                "reason": "深度和中度推理均表现良好，维持当前策略",
            }

        # 5. 检查点频率自适应
        efficiencies = [
            r.get("cognitive_efficiency", {}).get("efficiency_score", 0.5)
            for r in self._meta_records
        ]
        avg_efficiency = sum(efficiencies) / max(len(efficiencies), 1)
        avg_checkpoints = sum(
            r.get("final_state", {}).get("checkpoints", 0)
            for r in self._meta_records
        ) / len(self._meta_records)

        if avg_efficiency < 0.5 and avg_checkpoints > 8:
            adaptations["checkpoint_frequency"] = {
                "adjustment": "reduce",
                "reason": "检查点过多拖慢效率，减少非关键检查",
                "suggested_interval": 5,  # 每 5 轮检查一次
            }
        elif avg_efficiency > 0.8 and avg_checkpoints < 3:
            adaptations["checkpoint_frequency"] = {
                "adjustment": "increase",
                "reason": "监控频率偏低，增加检查以提升监控精度",
                "suggested_interval": 2,
            }

        # 持久化适应参数
        current_params["adaptations"] = adaptations
        current_params["last_adapted"] = time.time()
        current_params["records_analyzed"] = len(self._meta_records)

        with open(adaptation_path, "w", encoding="utf-8") as f:
            json.dump(current_params, f, ensure_ascii=False, indent=2)

        return {
            "adaptations": adaptations,
            "total_adjustments": len(adaptations),
            "records_analyzed": len(self._meta_records),
            "message": f"基于 {len(self._meta_records)} 条记录完成 {len(adaptations)} 项认知自适应调整",
        }

    def get_adaptation_params(self) -> dict:
        """获取当前认知适应参数"""
        adaptation_path = Path(self._data_dir) / "evolution" / "cognitive_adaptations.json"
        if adaptation_path.exists():
            with open(adaptation_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"status": "no_adaptations", "message": "尚未进行认知自适应"}
