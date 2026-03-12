"""演化学习工具

提供 learn_from_ai_tool / gap_analysis / synthesize_experiences /
cross_task_transfer / self_diagnose / cognitive_adapt 工具，
驱动 Turing 的持续自我演化。

全局 EvolutionTracker 实例在 Agent 启动时通过 ``set_evolution_tracker()`` 注入。
"""

from __future__ import annotations

from turing.tools.registry import tool

_evolution_tracker = None


def set_evolution_tracker(tracker):
    """注入全局 EvolutionTracker 实例（Agent 启动时调用）。"""
    global _evolution_tracker
    _evolution_tracker = tracker


@tool(
    name="learn_from_ai_tool",
    description="分析顶尖 AI 编程工具的策略，提取可学习的模式和技巧。",
    parameters={
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "AI 工具名称",
                "enum": ["claude_opus", "codex", "gemini", "copilot"],
            },
            "task_type": {
                "type": "string",
                "description": "任务类型（如 bug_fix, feature, refactor）",
            },
            "reference_output": {
                "type": "string",
                "description": "该工具的参考输出（可选）",
            },
        },
        "required": ["tool_name", "task_type"],
    },
)
def learn_from_ai_tool(tool_name: str, task_type: str, reference_output: str = None) -> dict:
    """分析顶尖 AI 工具的策略并提取可学习的模式。"""
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.learn_from(tool_name, task_type, reference_output)


@tool(
    name="gap_analysis",
    description="分析 Turing 与 Claude Opus / Codex / Gemini / Copilot 等顶尖 AI 编码工具的能力差距，生成详细的差距报告和改进路线图。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def gap_analysis() -> dict:
    """分析与顶尖 AI 编码工具的能力差距，生成改进路线图。"""
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.analyze_gaps()


@tool(
    name="synthesize_experiences",
    description="经验合成器 — 从引导策略和AI学习数据库合成高质量模拟经验，加速策略进化。解决经验深度不足和策略未进化的瓶颈问题。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def synthesize_experiences() -> dict:
    """从引导策略和 AI 学习数据库合成高质量模拟经验。"""
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.synthesize_experiences()


@tool(
    name="cross_task_transfer",
    description="跨任务知识迁移 — 从高经验类型向低经验类型迁移可复用知识。例如 bug_fix 经验可迁移到 debug，feature 经验可迁移到 refactor。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def cross_task_transfer() -> dict:
    """从高经验任务类型向低经验类型迁移可复用知识。"""
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.cross_task_transfer()


@tool(
    name="self_diagnose",
    description="自我诊断协议 — 系统性识别最薄弱的能力维度，分析策略成熟度、工具利用率、失败模式和进化速度，生成优先级排序的提升计划。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def self_diagnose() -> dict:
    """系统性识别最薄弱能力维度并生成优先级提升计划。"""
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.self_diagnose()


@tool(
    name="cognitive_adapt",
    description="认知自适应 — 基于累积的元认知数据自动调整认知参数（置信度基线、负荷阈值、偏差检测灵敏度、推理深度策略、检查点频率）。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def cognitive_adapt() -> dict:
    """基于元认知数据自动调整认知参数（置信度、负荷阈值等）。"""
    from turing.evolution.metacognition import MetacognitiveEngine
    data_dir = "turing_data"
    if _evolution_tracker is not None:
        data_dir = getattr(_evolution_tracker, "_data_dir", "turing_data")
    engine = MetacognitiveEngine(data_dir)
    return engine.adapt()


@tool(
    name="recovery_advice",
    description="失败恢复建议 — 基于历史失败模式和恢复剧本，为当前错误提供分类诊断、恢复策略和工具替代方案。",
    parameters={
        "type": "object",
        "properties": {
            "error_msg": {
                "type": "string",
                "description": "错误信息",
            },
            "tool_name": {
                "type": "string",
                "description": "出错的工具名称（可选）",
            },
        },
        "required": ["error_msg"],
    },
)
def recovery_advice(error_msg: str, tool_name: str = "") -> dict:
    """基于历史失败模式为当前错误提供恢复策略。"""
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.get_recovery_advice(error_msg, tool_name)


@tool(
    name="recommend_tools",
    description="工具探索顾问 — 基于任务描述和历史数据推荐最佳工具组合，并识别应该探索但从未使用的工具。",
    parameters={
        "type": "object",
        "properties": {
            "task_description": {
                "type": "string",
                "description": "任务描述",
            },
            "task_type": {
                "type": "string",
                "description": "任务类型",
                "enum": ["bug_fix", "feature", "refactor", "debug", "explain", "general"],
            },
        },
        "required": ["task_description"],
    },
)
def recommend_tools(task_description: str, task_type: str = "general") -> dict:
    """基于任务描述和历史数据推荐最佳工具组合。"""
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.recommend_tools(task_description, task_type)


@tool(
    name="run_self_training",
    description="自训练模拟器 — 模拟多种类型、多种难度的任务执行，快速积累经验画像，构建失败恢复剧本，加速策略进化。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def run_self_training() -> dict:
    """模拟多种任务执行以快速积累经验并加速策略进化。"""
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.run_self_training()


@tool(
    name="build_recovery_playbook",
    description="构建/更新失败恢复剧本 — 从所有历史失败中提炼恢复策略、工具替代方案和预防措施。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def build_recovery_playbook() -> dict:
    """从历史失败中提炼恢复策略并构建/更新恢复剧本。"""
    if _evolution_tracker is None:
        return {"error": "演化系统未初始化"}
    return _evolution_tracker.build_recovery_playbook()


@tool(
    name="competitive_benchmark",
    description="竞争力对标分析 — 全面对比 Turing 与 Claude Code / Cursor / Copilot / Devin / Aider / Codex CLI / Windsurf 在 16 个能力维度上的表现，"
                "生成能力矩阵、差距排名、优势识别和改进路线图。结果自动注入元认知和策略进化系统。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def competitive_benchmark() -> dict:
    """执行全面竞争力对标分析。"""
    from turing.evolution.competitive import CompetitiveIntelligence
    data_dir = "turing_data"
    if _evolution_tracker is not None:
        data_dir = getattr(_evolution_tracker, "_data_dir", "turing_data")
    ci = CompetitiveIntelligence(data_dir)
    return ci.analyze()


# ────────────────── 假设验证工具 ──────────────────


@tool(
    name="verify_hypothesis",
    description="结构化假设验证 — 当面对复杂问题时，先提出假设再系统性验证。"
                "支持自动执行验证命令、对比预期与实际结果、记录验证链。",
    parameters={
        "type": "object",
        "properties": {
            "hypothesis": {
                "type": "string",
                "description": "待验证的假设（如 '数据库连接池耗尽导致超时'）",
            },
            "verification_cmd": {
                "type": "string",
                "description": "验证命令（如 'grep timeout logs/*.log'）",
            },
            "expected_result": {
                "type": "string",
                "description": "预期结果描述（如 '应该能找到 timeout 日志'）",
            },
            "evidence": {
                "type": "string",
                "description": "支持或反驳假设的已有证据（可选）",
            },
        },
        "required": ["hypothesis"],
    },
)
def verify_hypothesis(
    hypothesis: str,
    verification_cmd: str = "",
    expected_result: str = "",
    evidence: str = "",
) -> dict:
    """结构化假设验证。"""
    import subprocess
    import time

    result = {
        "hypothesis": hypothesis,
        "timestamp": time.time(),
        "verification_steps": [],
    }

    # 如果有验证命令，执行它
    if verification_cmd:
        # 安全检查：拒绝危险命令
        dangerous = ["rm ", "rm -", "sudo", "mkfs", "dd if=", "> /dev"]
        if any(d in verification_cmd.lower() for d in dangerous):
            return {"error": "验证命令包含危险操作，已拒绝执行"}

        try:
            proc = subprocess.run(
                verification_cmd, shell=False if " " not in verification_cmd
                else True,  # noqa: S603
                capture_output=True, text=True, timeout=30,
                cwd="."
            )
            cmd_output = proc.stdout[-2000:] if len(proc.stdout) > 2000 else proc.stdout
            cmd_error = proc.stderr[-500:] if proc.stderr else ""

            step = {
                "action": "execute_cmd",
                "command": verification_cmd,
                "exit_code": proc.returncode,
                "output": cmd_output,
            }
            if cmd_error:
                step["stderr"] = cmd_error
            result["verification_steps"].append(step)

            # 简单判断：命令成功执行且有输出 → 可能支持假设
            if proc.returncode == 0 and proc.stdout.strip():
                result["cmd_supports_hypothesis"] = True
            else:
                result["cmd_supports_hypothesis"] = False

        except subprocess.TimeoutExpired:
            result["verification_steps"].append({
                "action": "execute_cmd",
                "command": verification_cmd,
                "error": "命令超时",
            })
        except Exception as e:
            result["verification_steps"].append({
                "action": "execute_cmd",
                "command": verification_cmd,
                "error": str(e),
            })

    # 证据分析
    if evidence:
        result["evidence"] = evidence
        result["verification_steps"].append({
            "action": "evidence_review",
            "evidence": evidence[:500],
        })

    if expected_result:
        result["expected_result"] = expected_result

    # 生成验证建议
    suggestions = []
    if not verification_cmd:
        suggestions.append("建议提供验证命令以自动验证假设")
    if not evidence:
        suggestions.append("建议收集更多证据（日志、堆栈、配置等）")
    suggestions.append("如果假设被否定，考虑提出新的假设并重复验证")
    suggestions.append("记录验证过程到记忆系统（memory_write），避免重复排查")
    result["next_steps"] = suggestions

    return result
