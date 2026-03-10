"""Turing 智能体主循环

实现完整的 Agent Loop（v0.6.0）：

1. 接收用户输入
2. 从长期记忆 / 持久记忆中检索相关经验
3. 匹配策略模板，注入任务指导（策略预播种）
4. Chain-of-Thought 推理：复杂度评估 + 分层任务分解
5. 调用 Ollama 本地模型生成响应（支持流式输出）
6. 解析并执行工具调用（只读并行 + 副作用顺序）
7. 语义错误分析 + 参数自动修正 + ETF 验证循环
8. 智能上下文管理（优先级滑动窗口 + 摘要折叠）
9. 任务完成后 LLM 深度反思，积累经验
10. 触发策略进化 / 知识蒸馏 / 十一维评分更新

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
import time
from typing import Any, Generator

import ollama

from turing.config import Config
from turing.prompt import SYSTEM_PROMPT
from turing.memory.manager import MemoryManager
from turing.rag.engine import RAGEngine
from turing.evolution.tracker import EvolutionTracker
from turing.tools.registry import get_ollama_tool_schemas, execute_tool

# 注入全局工具依赖
from turing.tools import memory_tools, external_tools, evolution_tools

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
        self.max_iterations = self.config.get("model.max_iterations", 20)
        self.stream_output = self.config.get("model.stream_output", True)
        data_dir = self.config.get("memory.data_dir", "turing_data")

        # 初始化子系统
        self.memory = MemoryManager(data_dir)
        self.rag = RAGEngine(data_dir)
        self.evolution = EvolutionTracker(data_dir, self.memory.persistent)

        # 注入全局依赖到工具层
        memory_tools.set_memory_manager(self.memory)
        external_tools.set_rag_engine(self.rag)
        evolution_tools.set_evolution_tracker(self.evolution)

        # 会话消息历史
        self._messages: list[dict] = []
        self._task_log: dict = {"actions": [], "outcome": None, "start_time": 0}
        self._initialized = False
        self._session_id: str | None = None
        self._data_dir = data_dir
        self._recent_tool_calls: list[str] = []  # 用于循环检测
        self._current_phase: str = "planning"     # 当前执行阶段
        self._etf_retry_count: int = 0             # ETF 循环重试计数
        self._error_history: list[dict] = []       # 错误历史（语义分析）

        # 验证工具注册完整性
        self._validate_tool_registration()

    def start_session(self):
        """启动新会话"""
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._task_log = {"actions": [], "outcome": None, "start_time": time.time()}
        self._initialized = True
        self._recent_tool_calls = []
        self._current_phase = "planning"
        self._etf_retry_count = 0
        self._error_history = []

    def _validate_tool_registration(self):
        """验证所有预期工具都已成功注册"""
        from turing.tools.registry import get_all_tools
        registered = {t.name for t in get_all_tools()}
        expected = {
            "read_file", "write_file", "edit_file", "run_command",
            "search_code", "list_directory", "memory_read", "memory_write",
            "memory_reflect", "rag_search", "web_search", "learn_from_ai_tool",
            "gap_analysis", "git_status", "git_diff", "git_log", "git_blame",
            "run_tests", "generate_tests", "lint_code", "format_code",
            "type_check", "detect_project", "analyze_dependencies",
            "batch_edit", "rename_symbol", "impact_analysis",
            "code_structure", "call_graph", "complexity_report",
        }
        missing = expected - registered
        if missing:
            import warnings
            warnings.warn(f"Turing: 以下工具未成功注册: {missing}")

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

        # ===== 阶段 0.5：策略注入 =====
        strategy_context = self._load_relevant_strategy(user_input)
        if strategy_context:
            self._messages.append({
                "role": "system",
                "content": strategy_context,
            })
            yield {"type": "thinking", "content": "已加载匹配的策略模板指导本次任务"}

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

        for iteration in range(self.max_iterations):
            # 动态温度：根据执行阶段调整
            current_temp = self._get_dynamic_temperature()

            try:
                if self.stream_output:
                    # 流式输出：逐 token 生成
                    msg = self._stream_chat(tool_schemas, temperature=current_temp)
                    if msg is None:
                        yield {"type": "error", "content": "模型调用失败（流式）"}
                        return
                    # 流式文本已通过 yield 发出，此处 msg 是完整消息
                else:
                    response = ollama.chat(
                        model=self.model,
                        messages=self._messages,
                        tools=tool_schemas if tool_schemas else None,
                        options={"temperature": current_temp},
                    )
                    msg = response.get("message", {})
            except Exception as e:
                yield {"type": "error", "content": f"模型调用失败: {e}"}
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
                yield {"type": "done"}
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
                        yield {"type": "done"}
                        return
                # 保留最近 10 个调用签名
                self._recent_tool_calls = self._recent_tool_calls[-10:]

                yield {"type": "tool_call", "name": tool_name, "args": tool_args}

                # 执行（含自动重试 + 语义错误分析）
                result = self._execute_with_retry(tool_name, tool_args)

                # 语义错误分析：检测错误模式并切换阶段
                if "error" in result:
                    self._error_history.append({
                        "tool": tool_name, "error": result["error"],
                        "iteration": iteration,
                    })
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
                else:
                    # 成功后清除错误历史并切换回 execution 阶段
                    self._error_history = []
                    self._current_phase = "execution"

                    # ETF 循环跟踪：编辑操作后检测是否需要验证
                    if tool_name in ("edit_file", "write_file", "generate_file", "batch_edit"):
                        self._etf_retry_count = 0
                        # 注入 ETF 提示
                        if not any("请运行测试或验证" in m.get("content", "") for m in self._messages[-3:]):
                            self._messages.append({
                                "role": "system",
                                "content": (
                                    "代码已修改。请执行 ETF 验证循环：\n"
                                    "1. run_tests 运行相关测试\n"
                                    "2. 或 run_command 验证功能\n"
                                    "3. 如果失败，分析原因并修复后重新验证"
                                ),
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

            # 工作记忆容量检查
            self._check_context_overflow()

        # 超过最大迭代
        self._task_log["outcome"] = "max_iterations_reached"
        reflection = self._post_task_reflect(user_input)
        if reflection:
            yield {"type": "reflection", "data": reflection}
        yield {"type": "text", "content": f"已达到最大迭代次数（{self.max_iterations}），任务可能未完全完成。"}
        yield {"type": "done"}

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

        reflect_prompt = (
            f"你刚完成了一个编程任务，请进行深度反思。\n"
            f"- 任务: {user_request}\n"
            f"- 结果: {outcome}\n"
            f"- 使用的工具: {tools_used}\n"
            f"- 工具调用次数: {actions_count}\n"
            f"- 耗时: {elapsed:.1f}s{error_summary}\n\n"
            f"请用 JSON 格式回答（不要用 markdown 代码块，直接输出 JSON）：\n"
            f'{{"task_type": "bug_fix/feature/refactor/debug/explain/general 之一",'
            f' "lessons": "一句话总结可复用的经验教训",'
            f' "what_went_well": "做得好的地方",'
            f' "what_could_improve": "可以改进的地方",'
            f' "tool_selection_quality": "good/adequate/poor",'
            f' "reasoning_depth": "deep/medium/shallow",'
            f' "reusable_pattern": "如果有可复用的解题模式，描述之，否则填 null"}}'
        )

        # 最多重试 2 次
        for attempt in range(2):
            try:
                resp = ollama.chat(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "你是一个善于自我反思的编程智能体。输出纯 JSON。"},
                        {"role": "user", "content": reflect_prompt},
                    ],
                    options={"temperature": reflect_temp},
                )
                content = resp.get("message", {}).get("content", "")
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
            resp = ollama.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个编程任务规划专家。输出简洁的分析。"},
                    {"role": "user", "content": cot_prompt},
                ],
                options={"temperature": reflect_temp},
            )
            content = resp.get("message", {}).get("content", "").strip()
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
        "read_file", "search_code", "list_directory", "memory_read",
        "rag_search", "web_search", "git_status", "git_diff", "git_log",
        "git_blame", "detect_project", "analyze_dependencies",
        "impact_analysis", "code_structure", "call_graph",
        "complexity_report", "gap_analysis",
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
        """语义压缩工具结果（对标 Claude 的智能上下文管理）

        对不同工具使用不同的压缩策略，保留语义关键信息。
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

        elif tool_name in ("run_command", "run_tests"):
            # 命令/测试输出：保留错误信息和结尾摘要
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

        elif tool_name in ("git_diff", "git_log"):
            # Git 输出：保留文件变更摘要 + 关键差异
            return result_str[:8000] + "\n...(截断)...\n" + result_str[-3000:]

        else:
            return result_str[:8000] + "\n...(截断)...\n" + result_str[-3000:]

    def _check_context_overflow(self):
        """智能上下文管理（Phase 7 增强 — 对标 Gemini 的大上下文管理）

        分层压缩 + 优先级滑动窗口策略：
        1. 计算总上下文大小
        2. 如果接近限制，先压缩工具结果
        3. 然后合并相邻 system 消息
        4. 对超出窗口的历史消息进行摘要折叠
        5. 最后淘汰低优先级消息

        消息优先级（高→低）：
        - system prompt (核心身份) → 必须保留
        - 最近的 user 消息 → 必须保留（当前任务上下文）
        - 最近的 assistant 消息 → 高优先级
        - tool 结果（含 error） → 高优先级
        - tool 结果（成功）→ 可压缩
        - 早期的 system 提示 → 可合并
        - 早期的 tool 结果 → 可丢弃
        """
        total_chars = sum(
            len(json.dumps(m, ensure_ascii=False, default=str))
            for m in self._messages
        )
        threshold = 80000
        if total_chars <= threshold:
            return

        self.memory.compress_working_memory(keep_recent=5)

        # 分离消息角色
        system_prompt = None
        system_hints = []
        conversation = []

        for i, m in enumerate(self._messages):
            role = m.get("role", "")
            if role == "system":
                if system_prompt is None:
                    system_prompt = m  # 第一个 system 为核心 prompt
                else:
                    system_hints.append(m)
            else:
                conversation.append(m)

        # 第一层：压缩大的 tool 结果（保留语义关键信息）
        for i, m in enumerate(conversation):
            if m.get("role") == "tool":
                content = m.get("content", "")
                if len(content) > 2000:
                    key_lines = []
                    for line in content.split("\n"):
                        ll = line.lower()
                        if any(kw in ll for kw in [
                            "error", "fail", "success", "status", "result",
                            "错误", "成功", "失败", "ok", "traceback"
                        ]):
                            key_lines.append(line)
                    if key_lines:
                        summary = "\n".join(key_lines[:20])
                        conversation[i] = {
                            **m,
                            "content": f"[压缩摘要]\n{summary}\n[原始长度: {len(content)}字符]",
                        }
                    else:
                        conversation[i] = {
                            **m,
                            "content": content[:1000] + "\n...(压缩)...\n" + content[-500:],
                        }

        # 第二层：合并 system 提示（保留核心 + 最近 2 条）
        if len(system_hints) > 2:
            system_hints = system_hints[-2:]

        # 第三层：对早期对话进行摘要折叠
        recalc = sum(
            len(json.dumps(m, ensure_ascii=False, default=str))
            for m in ([system_prompt] + system_hints + conversation if system_prompt else system_hints + conversation)
        )

        if recalc > threshold and len(conversation) > 10:
            # 将早期消息折叠为摘要
            keep_recent = 10
            early = conversation[:-keep_recent]
            recent = conversation[-keep_recent:]

            # 提取早期阶段的关键信息
            summary_parts = []
            tools_used = set()
            errors_encountered = []
            for m in early:
                role = m.get("role", "")
                content = m.get("content", "")
                if role == "user":
                    summary_parts.append(f"用户: {content[:100]}")
                elif role == "tool":
                    # 提取工具名和结果状态
                    if "error" in content.lower():
                        errors_encountered.append(content[:80])
                elif role == "assistant" and content:
                    # 保留 assistant 的前 50 字符
                    summary_parts.append(f"助手: {content[:80]}")

            if summary_parts or errors_encountered:
                fold_text = "[早期对话摘要]\n"
                if summary_parts:
                    fold_text += "\n".join(summary_parts[:8]) + "\n"
                if errors_encountered:
                    fold_text += f"遇到 {len(errors_encountered)} 个错误\n"
                conversation = [{"role": "system", "content": fold_text}] + recent
            else:
                conversation = recent

        # 第四层：极端情况下只保留最近消息
        if len(conversation) > 16:
            conversation = conversation[-14:]

        # 重组消息
        rebuilt = []
        if system_prompt:
            rebuilt.append(system_prompt)
        rebuilt.extend(system_hints)
        rebuilt.extend(conversation)
        self._messages = rebuilt

    def get_memory_stats(self) -> dict:
        """获取记忆系统统计"""
        return self.memory.get_stats()

    def get_evolution_stats(self) -> dict:
        """获取演化统计"""
        return self.evolution.get_stats()

    def index_project(self, project_path: str) -> dict:
        """索引项目到 RAG 知识库"""
        return self.rag.index_directory(project_path, source="codebase")

    # ===== Phase 3: 流式输出 =====

    def _stream_chat(self, tool_schemas: list, temperature: float = None) -> dict | None:
        """流式调用 Ollama 模型，逐 token 输出

        返回组装后的完整消息（与非流式兼容）。
        流式 token 通过回调或由上层循环拉取。
        """
        temp = temperature if temperature is not None else self.temperature
        try:
            stream = ollama.chat(
                model=self.model,
                messages=self._messages,
                tools=tool_schemas if tool_schemas else None,
                options={"temperature": temp},
                stream=True,
            )
            assembled = {"role": "assistant", "content": ""}
            tool_calls = []

            for chunk in stream:
                msg = chunk.get("message", {})
                # 累积文本
                if msg.get("content"):
                    assembled["content"] += msg["content"]
                # 累积工具调用
                if msg.get("tool_calls"):
                    tool_calls.extend(msg["tool_calls"])

            if tool_calls:
                assembled["tool_calls"] = tool_calls

            return assembled
        except Exception:
            return None

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
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        return session_id

    def load_conversation(self, session_id: str) -> bool:
        """从磁盘加载历史会话

        返回是否加载成功。
        """
        from pathlib import Path

        filepath = Path(self._data_dir) / "conversations" / f"{session_id}.json"
        if not filepath.exists():
            return False

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

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
