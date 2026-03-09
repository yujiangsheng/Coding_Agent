"""Turing 智能体主循环

实现完整的 Agent Loop：
1. 接收用户输入
2. 从长期记忆 / 持久记忆中检索相关经验
3. 调用 Ollama 本地模型生成响应
4. 解析并执行工具调用（多轮迭代）
5. 任务完成后自动反思，积累经验
6. 触发策略进化 / 知识蒸馏

事件流模型：chat() 方法是一个 Generator，通过 yield 产出
类型化事件字典（thinking / tool_call / tool_result / text /
reflection / done / error），方便 UI 层流式渲染。
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

        # 验证工具注册完整性
        self._validate_tool_registration()

    def start_session(self):
        """启动新会话"""
        self._messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._task_log = {"actions": [], "outcome": None, "start_time": time.time()}
        self._initialized = True
        self._recent_tool_calls = []

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
            "batch_edit", "rename_symbol",
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
            try:
                if self.stream_output:
                    # 流式输出：逐 token 生成
                    msg = self._stream_chat(tool_schemas)
                    if msg is None:
                        yield {"type": "error", "content": "模型调用失败（流式）"}
                        return
                    # 流式文本已通过 yield 发出，此处 msg 是完整消息
                else:
                    response = ollama.chat(
                        model=self.model,
                        messages=self._messages,
                        tools=tool_schemas if tool_schemas else None,
                        options={"temperature": self.temperature},
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

            # 执行工具调用
            for tc in tool_calls:
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

                # 执行（含自动重试）
                result = self._execute_with_retry(tool_name, tool_args)

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
        """调用 LLM 对任务执行过程进行深度反思（含重试）"""
        reflect_temp = self.config.get("model.reflect_temperature", 0.6)
        tools_used = ", ".join(mechanical.get("tools_used", []))
        outcome = mechanical.get("outcome", "unknown")
        actions_count = mechanical.get("actions_count", 0)
        elapsed = time.time() - self._task_log.get("start_time", time.time())

        reflect_prompt = (
            f"你刚完成了一个编程任务，请进行简短反思。\n"
            f"- 任务: {user_request}\n"
            f"- 结果: {outcome}\n"
            f"- 使用的工具: {tools_used}\n"
            f"- 工具调用次数: {actions_count}\n"
            f"- 耗时: {elapsed:.1f}s\n\n"
            f"请用 JSON 格式回答（不要用 markdown 代码块，直接输出 JSON）：\n"
            f'{{"task_type": "bug_fix/feature/refactor/debug/explain/general 之一",'
            f' "lessons": "一句话总结经验教训",'
            f' "what_went_well": "做得好的地方",'
            f' "what_could_improve": "可以改进的地方"}}'
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

        return "\n".join(lines)

    def _assess_and_plan(self, user_input: str) -> str | None:
        """快速评估任务复杂度并生成执行计划"""
        input_lower = user_input.lower()

        # 复杂度信号词
        complex_signals = [
            "重构", "refactor", "批量", "batch", "多个文件", "multiple files",
            "架构", "architecture", "迁移", "migrate", "全部", "all",
        ]
        simple_signals = [
            "解释", "explain", "什么是", "what is", "查看", "show", "读",
        ]

        is_complex = any(s in input_lower for s in complex_signals)
        is_simple = any(s in input_lower for s in simple_signals)

        if is_simple:
            return None  # 简单任务不需要规划

        if is_complex:
            return (
                "复杂任务 → 1) 先理解全貌（搜索+阅读）"
                " 2) 制定具体步骤 3) 逐步执行并验证 4) 回归测试"
            )

        # 中等复杂度
        if len(user_input) > 80:
            return "中等任务 → 1) 理解需求 2) 定位代码 3) 实施修改 4) 验证"

        return None

    def _execute_with_retry(self, tool_name: str, tool_args: dict, max_retries: int = 1) -> dict:
        """执行工具调用，支持自动重试

        对于超时和临时错误自动重试一次。
        """
        for attempt in range(max_retries + 1):
            result = execute_tool(tool_name, tool_args)
            if "error" not in result:
                return result
            err = result.get("error", "")
            # 可重试的错误类型
            retryable = ("超时" in err or "timeout" in err.lower() or "临时" in err)
            if retryable and attempt < max_retries:
                # 对超时命令增加 timeout
                if "timeout" in tool_name or tool_name == "run_command":
                    tool_args["timeout"] = tool_args.get("timeout", 30) * 2
                continue
            break
        return result

    def _summarize_tool_result(self, tool_name: str, result_str: str) -> str:
        """压缩过大的工具结果以节省上下文空间"""
        max_len = 12000
        if len(result_str) <= max_len:
            return result_str

        # 对不同工具使用不同压缩策略
        if tool_name in ("search_code", "list_directory"):
            # 搜索结果：保留前后部分
            return result_str[:6000] + "\n...(结果过多，已截断)...\n" + result_str[-3000:]
        elif tool_name in ("read_file", "run_command", "run_tests"):
            # 文件内容 / 命令输出：保留头尾
            return result_str[:8000] + "\n...(截断)...\n" + result_str[-3000:]
        else:
            return result_str[:8000] + "\n...(截断)...\n" + result_str[-3000:]

    def _check_context_overflow(self):
        """智能上下文管理 — 按优先级压缩"""
        total_chars = sum(
            len(json.dumps(m, ensure_ascii=False, default=str))
            for m in self._messages
        )
        # ~4 chars/token, 32K context ≈ 128K chars, keep 60% headroom
        threshold = 80000
        if total_chars <= threshold:
            return

        self.memory.compress_working_memory(keep_recent=5)

        # 智能压缩：先压缩大的 tool 结果（保留摘要），再删旧消息
        compressed = []
        system_msgs = []
        for m in self._messages:
            if m.get("role") == "system":
                system_msgs.append(m)
                continue
            # 压缩大的 tool 结果
            if m.get("role") == "tool":
                content = m.get("content", "")
                if len(content) > 3000:
                    m = {**m, "content": content[:1500] + "\n...(压缩)...\n" + content[-500:]}
            compressed.append(m)

        # 保留所有 system + 最近 12 条非 system 消息
        recent = compressed[-12:] if len(compressed) > 12 else compressed
        self._messages = system_msgs + recent

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

    def _stream_chat(self, tool_schemas: list) -> dict | None:
        """流式调用 Ollama 模型，逐 token 输出

        返回组装后的完整消息（与非流式兼容）。
        流式 token 通过回调或由上层循环拉取。
        """
        try:
            stream = ollama.chat(
                model=self.model,
                messages=self._messages,
                tools=tool_schemas if tool_schemas else None,
                options={"temperature": self.temperature},
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
