# 系统架构设计文档

> Turing v0.6.0 — 自进化编程智能体

## 1. 总体架构

Turing 采用分层架构设计，每层职责清晰、松耦合：

```
┌──────────────────────────────────────────────────────┐
│                   接入层 (Interface)                   │
│    main.py (CLI REPL)    web/server.py (Flask SSE)   │
├──────────────────────────────────────────────────────┤
│                   核心层 (Core)                        │
│                 agent.py — TuringAgent                │
│    ReAct Loop · CoT 推理 · ETF 验证 · 并行执行       │
├──────┬──────────┬──────────┬─────────────────────────┤
│ 工具 │   记忆   │   RAG    │        演化              │
│ 引擎 │   系统   │   引擎   │        系统              │
├──────┼──────────┼──────────┼─────────────────────────┤
│ 13个 │  4 层    │ ChromaDB │  反思/策略/蒸馏          │
│ 模块 │  TF-IDF  │  + JSON  │  AI学习/11维评分        │
│ 31+  │  跨层    │  查询    │  策略预播种              │
│ 工具 │  排序    │  扩展    │  工具效率分析            │
└──────┴──────────┴──────────┴─────────────────────────┘
         ↕              ↕              ↕
     Ollama API     向量数据库     turing_data/
   (Qwen3-Coder)   (ChromaDB)     (JSON/YAML)
```

## 2. 核心组件

### 2.1 TuringAgent（`agent.py`）

Agent 主循环，是整个系统的调度中枢。

**执行流程：**

```
用户输入
  │
  ├─[0] 记忆预加载 ── 从 L2+L3 检索 top_k=5 条相关记忆
  ├─[0.5] 策略注入 ── 关键词匹配任务类型 → 加载策略模板
  ├─[0.8] CoT 推理 ── 复杂度评估 → LLM 分层分解（简单任务跳过）
  │
  ├─[主循环] ReAct Loop（最多 max_iterations=20 轮）
  │    ├── LLM 推理生成（支持流式/非流式）
  │    ├── 动态温度调节（按 planning/execution/debugging 阶段）
  │    ├── 工具调用分类 → 只读并行 / 副作用顺序
  │    ├── 循环检测（连续 3 次相同签名 → 中断）
  │    ├── 语义错误分析（连续失败 → 模式识别 → 智能修正）
  │    ├── ETF 提示注入（编辑操作后提醒验证）
  │    └── 上下文溢出管理（优先级滑动窗口）
  │
  ├─[反思] LLM 深度反思 → 经验写入 L2
  ├─[进化] 策略进化检查 → 知识蒸馏检查
  └─[评分] 十一维能力评分更新
```

**关键设计决策：**

- **Generator 事件流**：`chat()` 返回 Generator，yield 类型化事件字典，支持 CLI/Web 统一消费
- **动态温度**：规划阶段 0.6（更发散）、执行阶段 0.3（更精确）、调试阶段 0.45（平衡）
- **自动修正**：文件路径错误时自动 `find` 搜索、`edit_file` 匹配失败时规范化空白

### 2.2 工具系统（`tools/`）

**注册机制：**

```python
@tool(name="...", description="...", parameters={...})
def my_tool(arg1: str) -> dict:
    return {"result": "..."}
```

- 基于装饰器的自动注册，import 即生效
- 统一返回 `dict` 类型（成功字段 + error 字段）
- 自动生成 Ollama function calling schema

**13 个工具模块：**

| 模块 | 工具数 | 说明 |
|------|--------|------|
| `file_tools.py` | 3 | 文件读写编辑（edit_file 支持多匹配 + 近似提示） |
| `command_tools.py` | 1 | Shell 命令执行（黑名单过滤 + 超时控制） |
| `search_tools.py` | 2 | 代码搜索 + 目录列表（ripgrep/grep 自适应） |
| `git_tools.py` | 4 | Git status/diff/log/blame |
| `test_tools.py` | 2 | 测试运行 + 测试生成（自动检测框架） |
| `quality_tools.py` | 3 | Lint + Format + TypeCheck（多工具自适应） |
| `refactor_tools.py` | 3 | 批量编辑 + 符号重命名 + 影响分析 |
| `project_tools.py` | 2 | 项目检测 + 依赖分析 |
| `ast_tools.py` | 3 | 代码结构 + 调用图 + 复杂度（Python AST） |
| `memory_tools.py` | 3 | 记忆读写 + 反思 |
| `external_tools.py` | 2 | RAG 检索 + Web 搜索 |
| `evolution_tools.py` | 2 | AI 工具学习 + 差距分析 |
| `registry.py` | — | 注册表 + Schema 生成 + 安全调度 |

**并行执行策略：**

只读工具集合（17 个）可安全并行执行：
```
read_file, search_code, list_directory, memory_read,
rag_search, web_search, git_status, git_diff, git_log,
git_blame, detect_project, analyze_dependencies,
impact_analysis, code_structure, call_graph,
complexity_report, gap_analysis
```

### 2.3 记忆系统（`memory/`）

四层分级存储，搜索时跨层统一排序：

```
L1 工作记忆 (working.py)
├── 存储：内存 + JSON 文件
├── 生命周期：会话级
├── 检索：TF-IDF（中文 bigram 分词 + 时间衰减）
└── 用途：当前任务上下文、计划、中间结果

L2 长期记忆 (long_term.py)
├── 存储：ChromaDB 向量库（无则降级 JSON）
├── 生命周期：跨会话永久
├── 检索：语义向量搜索 / TF-IDF 降级
└── 用途：历史经验、编程知识、用户偏好

L3 持久记忆 (persistent.py)
├── 存储：YAML/JSON 文件
├── 生命周期：永久
├── 检索：TF-IDF + Jaccard 去重（阈值 0.85）
├── 用途：项目架构、策略模板、进化日志
└── 特性：写入时自动去重防止知识膨胀

L4 外部记忆 (RAG + Web)
├── 存储：ChromaDB 索引 / 搜索引擎
├── 生命周期：实时
├── 检索：查询扩展 + 代码感知分块
└── 用途：文档检索、Web 搜索、AI 工具参考
```

**跨层统一检索算法：**

```
1. 计算 TF-IDF 相关度分数
   score = Σ(tf(word) × idf(word))
   tf(word) = count(word_in_doc)
   idf(word) = log(1 + N / (1 + df(word)))

2. 应用时间衰减
   score *= 1.0 / (1.0 + age_hours × 0.01)

3. 应用层级权重
   persistent ×1.2 > long_term ×1.0 > working ×0.8

4. 跨层排序 + Jaccard 去重（similarity ≥ 0.85 → 合并）
```

**上下文管理（滑动窗口）：**

当总上下文超过 80K 字符时，按优先级分四层压缩：
1. 大工具结果 → 保留关键行（error/success/status）
2. 早期 system 提示 → 只保留最近 2 条
3. 早期对话 → 折叠为摘要
4. 极端情况 → 只保留最近 14 条消息

### 2.4 RAG 引擎（`rag/engine.py`）

- **查询扩展**：自动展开同义词和相关关键词
- **代码感知分块**：按函数/类边界分块（而非固定长度），保持语义完整性
- **双存储后端**：优先 ChromaDB 向量库，无则降级为 JSON TF-IDF
- **索引 API**：`/index <路径>` 可索引本地项目到 RAG 知识库

### 2.5 演化系统（`evolution/tracker.py`）

自我演化是 Turing 的核心差异化能力：

```
任务完成
  ↓
[LLM 深度反思]
  ├── 工具选择质量评估 (good/adequate/poor)
  ├── 推理链深度自评 (deep/medium/shallow)
  ├── 可复用模式提取
  └── 经验教训提炼
  ↓
[经验积累] → 写入 reflections.json
  ↓
[策略进化检查] ── 同类 ≥5 条 → 时间加权归纳
  ├── 推荐工具列表
  ├── 推荐步骤序列
  ├── 核心经验（最近 5 条）
  ├── 常见陷阱
  ├── 工具路由建议
  └── 验证工具推荐
  ↓
[知识蒸馏] ── 每 50 次任务 → 合并冗余、淘汰低质量
  ↓
[十一维评分] → 综合能力画像
  ├── ① 代码质量      ② 调试能力     ③ 架构设计
  ├── ④ 执行效率      ⑤ 安全意识     ⑥ 沟通清晰度
  ├── ⑦ 工具多样性    ⑧ 推理深度     ⑨ 记忆利用率
  └── ⑩ 学习速率      ⑪ 验证覆盖率
```

**策略预播种（6 大任务类型）：**

冷启动时基于 Claude Opus / Codex / Gemini / Copilot 最佳实践预载策略：
1. `bug_fix` — 先理解再修复，最小改动，必须验证
2. `feature` — 项目检测 → 编码 → 测试 → 质量检查
3. `refactor` — 结构分析 → 影响评估 → 批量修改 → 回归测试
4. `debug` — 深度推理，分析堆栈，逐步排查
5. `explain` — 结构提取 → 调用图 → 知识检索
6. `test` — 框架检测 → 生成测试 → 运行验证

## 3. 数据流

### 3.1 请求处理流

```
用户输入 "修复 auth.py 的 bug"
  │
  ├── MemoryManager.retrieve("修复 auth bug", ["long_term", "persistent"])
  │   └── 返回: [历史 bug_fix 经验, auth 模块知识]
  │
  ├── _load_relevant_strategy("修复 auth.py 的 bug")
  │   └── 关键词匹配 "修复/bug" → 加载 bug_fix 策略模板
  │
  ├── _assess_and_plan("修复 auth.py 的 bug")
  │   └── 中等复杂度 → 快速计划
  │
  ├── Ollama.chat() → 模型决定调用 read_file
  │   ├── _classify_tool_calls → [read_file] → 只读，可并行
  │   └── execute_tool("read_file", {"path": "auth.py"})
  │
  ├── Ollama.chat() → 模型决定调用 edit_file
  │   ├── _classify_tool_calls → [edit_file] → 有副作用，顺序执行
  │   ├── execute_tool("edit_file", {...})
  │   └── ETF 提示注入: "代码已修改，请运行测试验证"
  │
  ├── Ollama.chat() → 模型调用 run_tests
  │   └── execute_tool("run_tests", {"path": "."})
  │
  ├── 任务完成 → _post_task_reflect()
  │   ├── _llm_reflect() → LLM 深度反思
  │   ├── evolution.add_reflection() → 记录经验
  │   └── evolution.check_strategy_evolution() → bug_fix 经验 +1
  │
  └── yield {"type": "done"}
```

### 3.2 记忆生命周期

```
任务开始
  ├── L2/L3 → 检索 → 注入 L1（工作记忆）
  │
任务执行中
  ├── 关键中间结果 → 写入 L1
  ├── 遇到知识盲区 → L4 (RAG/Web) → 结果写入 L1
  │
任务完成
  ├── 反思结果 → 写入 L2（长期记忆）
  ├── 发现稳定模式 → 归纳为策略 → 写入 L3（持久记忆）
  │
定期维护
  ├── 工作记忆 → 会话结束时清理
  ├── 长期记忆 → 知识蒸馏（合并冗余）
  └── 持久记忆 → Jaccard 去重（阈值 0.85）
```

## 4. 安全设计

### 4.1 命令执行安全

- **黑名单过滤**：`rm -rf /`, `DROP TABLE` 等危险命令被拦截
- **超时控制**：命令执行默认 30 秒超时
- **输出截断**：超长输出自动截断，防止上下文爆炸

### 4.2 路径访问控制

- **路径黑名单**：`/etc/shadow`, `/etc/passwd` 等敏感路径禁止访问
- **Web API**：文件浏览接口进行路径安全检查

### 4.3 输入校验

- **工具参数验证**：通过 JSON Schema 验证参数类型和必填项
- **外部输入隔离**：工具结果通过 `json.dumps` 序列化后传递

## 5. 配置参考

完整配置项说明请参考 `config.yaml`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `model.name` | `qwen3-coder:30b` | Ollama 模型名称 |
| `model.temperature` | `0.3` | 基础生成温度 |
| `model.reflect_temperature` | `0.6` | 反思时使用的温度 |
| `model.max_iterations` | `20` | ReAct 循环最大轮次 |
| `model.stream_output` | `true` | 是否启用流式输出 |
| `memory.data_dir` | `turing_data` | 数据持久化目录 |
| `memory.working.max_context_ratio` | `0.3` | 工作记忆占上下文比例 |
| `memory.working.keep_recent` | `5` | 压缩时保留最近 N 条 |
| `memory.long_term.collection` | `turing_long_term` | ChromaDB collection 名 |
| `memory.long_term.decay_factor` | `0.95` | 记忆时间衰减因子 |
| `memory.persistent.dir` | `persistent_memory` | 持久记忆子目录 |
| `evolution.strategy_threshold` | `5` | 触发策略进化的最小经验数 |
| `evolution.distill_interval` | `50` | 触发知识蒸馏的任务间隔 |
| `security.blocked_commands` | `[rm -rf /, ...]` | 禁止执行的命令模式 |
| `security.blocked_paths` | `[/etc/shadow, ...]` | 禁止访问的路径 |

## 6. 扩展指南

### 添加新工具

1. 在 `turing/tools/` 下创建模块文件
2. 使用 `@tool` 装饰器定义工具
3. 在 `agent.py` 中添加 `import turing.tools.xxx  # noqa: F401`
4. 如果是只读工具，添加到 `_READONLY_TOOLS` 集合

### 添加新记忆层

1. 在 `turing/memory/` 下实现存储类
2. 实现 `write()`, `search()`, `get_stats()` 等接口
3. 在 `MemoryManager` 中集成

### 添加新演化维度

1. 在 `EvolutionTracker._score_dimensions()` 中添加评分逻辑
2. 在 `SYSTEM_PROMPT` 中描述新维度的能力要求
3. 更新 `gap_analysis` 工具的差距分析逻辑

---

*文档版本: v0.6.0 · 最后更新: 2025-07*
