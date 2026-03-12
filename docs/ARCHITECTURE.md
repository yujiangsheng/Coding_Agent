# 系统架构设计文档

> Turing v3.6 — 自进化编程智能体

## 1. 总体架构

Turing 采用分层架构设计，每层职责清晰、松耦合：

```
┌──────────────────────────────────────────────────────────────────────┐
│                       接入层 (Interface)                              │
│       main.py (CLI REPL)           web/server.py (Flask SSE)        │
├──────────────────────────────────────────────────────────────────────┤
│                       核心层 (Core)                                  │
│                    agent.py — TuringAgent                            │
│  10 阶段执行流水线 · CoT 推理 · ETF 验证 · 元认知 · 并行执行       │
│  持久化 Shell · Token-aware 上下文管理 · 自动项目索引 · LSP       │
├──────────┬───────────┬───────────┬─────────────────────────────────┤
│  工具引擎 │   记忆系统 │   RAG 引擎│   演化系统 + 元认知引擎          │
├──────────┼───────────┼───────────┼─────────────────────────────────┤
│  19 模块  │   4 层     │  ChromaDB │  15 维评分 · 策略进化 · 失败恢复 │
│  82 工具  │   TF-IDF   │  + JSON   │  自训练模拟器 · 6 维认知雷达     │
│  21 并行  │   跨层排序 │  查询扩展 │  经验合成 · 知识迁移 · 竞争力   │
└──────────┴───────────┴───────────┴─────────────────────────────────┘
         ↕                  ↕               ↕
     LLM Router          向量数据库      turing_data/
   (Multi-Provider)     (ChromaDB)      (JSON/YAML)
```

## 2. 核心组件

### 2.1 TuringAgent（`agent.py`）

Agent 主循环，是整个系统的调度中枢。v2.0 实现了完整的 10 阶段执行流水线，并新增多 Provider LLM 路由。

**执行流程（10 阶段）：**

```
用户输入
  │
  ├─[0] 记忆预加载 ── 从 L2(长期) + L3(持久) 检索相关经验
  │
  ├─[0.3] 按需代码上下文 ── RAG 检索相关代码片段
  │
  ├─[0.32] 智能依赖追踪 ── AST import 链自动分析，注入依赖模块结构摘要 (v3.6)
  │
  ├─[0.35] @-mention 解析 ── @file @folder 语法引用代码上下文
  │
  ├─[1] 策略注入 ── 关键词匹配任务类型 → 加载策略模板 + 推荐工具
  ├─[2] 工具推荐 ── 基于策略模板向 LLM 推荐最佳工具组合
  ├─[3] 元认知初始化 ── MetacognitiveEngine 启动 6 维认知雷达
  ├─[4] CoT 推理 ── 复杂度评估 → LLM 分层分解（简单任务跳过）
  │
  ├─[5. 主循环] ReAct Loop（最多 max_iterations=20 轮）
  │    ├── LLM 推理生成（支持流式/非流式）
  │    ├── 动态温度调节（planning=0.6 / execution=0.3 / debugging=0.45）
  │    ├── 工具调用分类 → 只读并行(20工具) / 副作用顺序
  │    ├── 循环检测（连续 3 次相同签名 → 中断）
  │    ├── 语义错误分析（连续失败 → 模式识别 → 智能修正）
  │    ├── ETF 提示注入（编辑操作后提醒验证）
  │    └── Token-aware 上下文溢出管理
  │
  ├─[6] 错误恢复 ── 失败恢复引擎（8 模式 × 3 级策略）
  ├─[7] 上下文管理 ── Token-aware 优先级打分 + 智能压缩
  ├─[8] 反思 ── LLM 深度反思 → 经验写入 L2 → 策略进化检查
  └─[9] 评分 ── 十五维能力评分更新 + 元认知报告
```

**关键设计决策：**

| 决策 | 实现 | 原因 |
|------|------|------|
| Generator 事件流 | `chat()` 返回 Generator，yield 类型化事件字典 | CLI/Web 统一消费模型 |
| 动态温度 | planning=0.6 / execution=0.3 / debugging=0.45 | 不同阶段需要不同的发散/精确度 |
| 自动修正 | 路径错误→`find`搜索，edit_file→规范化空白 | 减少无效重试 |
| 持久化 Shell | `_ShellSession` 单例，env/cwd 跨调用保持 | 对标 Claude Code，支持复杂构建场景 |
| Token-aware | 基于 `model.context_length` 估算 token，分优先级压缩 | 比固定字符阈值更精准 |
| 自动项目索引 | 会话启动时自动 `detect_project` + `repo_map` | 冷启动即有项目上下文 |
| 多 Provider 路由 | `ModelRouter` 按复杂度路由 + 自动 fallback | 对标 Codex，支持 4 家 LLM Provider |

### 2.2 工具系统（`tools/`）

**注册机制：**

```python
from turing.tools.registry import tool

@tool(name="my_tool", description="工具描述", parameters={
    "arg1": {"type": "string", "description": "参数说明"}
})
def my_tool(arg1: str) -> dict:
    """工具实现，统一返回 dict。"""
    return {"result": "..."}
```

- 基于 `@tool` 装饰器自动注册（import 即生效）
- 统一返回 `dict` 类型（成功字段 + error 字段）
- 自动生成 Ollama function calling schema（`get_ollama_tool_schemas()`）
- `execute_tool()` 通过 `inspect.signature()` 自动过滤多余参数

**19 个工具模块（82 工具）：**

| 模块 | 工具数 | 说明 |
|------|--------|------|
| `file_tools.py` | 9 | 文件 CRUD + diff 预览 + 原子化多文件编辑 + 文件管理 |
| `command_tools.py` | 5 | 持久化 Shell（env/cwd 保持）+ 后台进程管理 + 自动修复 |
| `search_tools.py` | 6 | 代码搜索 + 目录列表 + Repo Map + 智能上下文收集 + 上下文预算/压缩 |
| `git_tools.py` | 8 | 完整 Git 工作流（status/diff/log/blame/add/commit/branch/stash） |
| `test_tools.py` | 2 | 测试运行（覆盖率 + 失败详情提取）+ 测试生成 |
| `quality_tools.py` | 3 | Lint + Format + TypeCheck（多工具自适应） |
| `refactor_tools.py` | 3 | 批量编辑 + 符号重命名 + 影响分析 |
| `project_tools.py` | 2 | 项目检测 + 依赖分析 |
| `ast_tools.py` | 4 | 代码结构 + 调用图 + 复杂度 + 依赖图（Python AST） |
| `memory_tools.py` | 3 | 记忆读写 + 反思 |
| `external_tools.py` | 3 | RAG 检索 + Web 搜索 + URL 内容获取 |
| `evolution_tools.py` | 12 | 策略进化 + 蒸馏 + AI学习 + 失败恢复 + 自训练 + 探索 + 竞争力分析 + 假设验证 |
| `benchmark_tools.py` | 3 | HumanEval 评测 + 代码质量评估 + 评测趋势 |
| `mcp_tools.py` | 3 | MCP 服务器管理 + 外部工具发现 + 外部工具调用 |
| `metacognition_tools.py` | 2 | 元认知反思 + checkpoint 管理 |
| `agent_tools.py` | 1 | 任务分解与计划 |
| `github_tools.py` | 5 | PR 摘要 + Issue 分析 + 安全扫描 + 代码审查 + 变更日志 |
| `registry.py` | — | 注册表 + Schema 生成 + 安全调度 |

**并行执行策略：**

25 个只读工具可通过 `ThreadPoolExecutor` 安全并行执行：
```python
_READONLY_TOOLS = {
    "read_file", "search_code", "list_directory", "repo_map",
    "memory_read", "rag_search", "web_search",
    "git_status", "git_diff", "git_log", "git_blame",
    "detect_project", "analyze_dependencies",
    "impact_analysis", "code_structure", "call_graph",
    "complexity_report", "gap_analysis", "find_files",
    "check_background", "smart_context",
    "mcp_list_servers", "mcp_list_tools",
    "context_budget", "dependency_graph",
    "competitive_benchmark", "verify_hypothesis",
}
```

**v2.0 新增工具亮点：**

| 工具 | 特性 |
|------|------|
| `smart_context` | 智能上下文收集（import 链追踪 / 符号引用 / 错误堆栈解析） |
| `mcp_list_servers` | MCP 服务器状态查看（连接状态 + 工具数） |
| `mcp_list_tools` | MCP 外部工具发现（列出已连接服务器的全部工具） |
| `mcp_call_tool` | MCP 外部工具调用（通过 mcp::server::tool 名称路由） |
| `run_benchmark` | HumanEval 风格基准评测，pass@k 指标 + 业界分数横向对比 |
| `eval_code` | 多维代码质量评估（语法 + lint + 圈复杂度 + 安全模式） |
| `benchmark_trend` | 历史评测分数趋势追踪，量化能力进化 |

**v3.4/v3.5 新增工具亮点：**

| 工具 | 特性 |
|------|------|
| `competitive_benchmark` | 多维竞争力自评，对标 8 大主流 Agent，输出排名 + 差距分析 |
| `verify_hypothesis` | 假设验证引擎，结构化假设→证据→结论工作流 |
| `context_compress` | 上下文压缩，超出 token 预算时自动精简无关信息 |
| `context_budget` | 上下文预算管理，跟踪剩余 token + 成本预估 |
| `dependency_graph` | 模块依赖图分析，可视化 import 关系 + 循环检测 |
| `auto_fix` | 自动修复 lint 错误和常见代码问题 |
| `task_plan` | 任务分解与计划，将复杂需求拆解为可执行步骤 |
| `security_scan` | 安全漏洞扫描，检测常见安全问题 |
| `pr_summary` | PR 变更摘要自动生成 |

**v3.6 新增工具亮点：**

| 工具 | 特性 |
|------|------|
| `fetch_url` | URL 内容获取（robots.txt 检查 + User-Agent + 超时保护 + HTML→纯文本） |

**v3.6 新增能力：**

| 能力 | 说明 |
|------|------|
| VS Code 扩展 | 原生 VS Code Extension，通过 MCP 协议连接 Turing（侧边栏聊天 + 代码解释） |
| 智能依赖追踪 | AST import 链自动分析，为 LLM 注入依赖模块的类/函数结构摘要 |
| Prompt Caching | Anthropic `cache_control` 标记，减少 System Prompt 重复传输成本 |
| 多模态输入 | `encode_image()` 支持图片 base64 编码，3 家 Provider 均支持 vision |

**v1.0.0 新增工具亮点：**

| 工具 | 特性 |
|------|------|
| `multi_edit` | 原子化多文件编辑，任意一步失败自动回滚全部变更 |
| `run_command` | 持久化 Shell 会话，env/cwd 跨调用保持（`_ShellSession` 单例） |
| `run_background` | 启动后台进程（服务器、watch 等），返回 PID |
| `check_background` / `stop_background` | 查看/终止后台进程 |
| `move_file` / `copy_file` / `delete_file` | 完整文件管理，非空目录删除保护 |
| `find_files` | 混合搜索（glob 模式 + 正则内容匹配） |
| `generate_file` | AI 生成完整文件，已有文件需确认 |
| `run_tests` | 新增覆盖率报告（`--cov`）+ 正则提取失败详情 |

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

**Token-aware 上下文管理（v1.0.0 新增）：**

取代旧版 80K 字符固定阈值，基于 `model.context_length` 配置动态估算 token 数：

```
当前 token 估算 = len(messages_json) / 4
上下文上限 = config.get("model.context_length", 32768) × 0.85

溢出时按优先级打分压缩：
 优先级分 = base_score × recency_weight × type_weight
 ├── system/plan 消息:   base=10 (最高保护)
 ├── 最近 4 轮对话:      base=8
 ├── 含工具结果的助理:    base=6
 ├── 普通对话:           base=4
 └── 早期历史:           base=2 (最先压缩)

压缩策略：按优先级从低到高移除，直到 token 恢复安全线
```

### 2.4 LLM 路由层（`llm/`）

v2.0 新增多 Provider LLM 路由，支持按任务复杂度自动选择最优模型：

```
ModelRouter
├── _select_provider(task_complexity)
│   ├── simple (< 0.3) → 快速轻量模型 (Ollama / GPT-4o-mini)
│   ├── medium (0.3-0.7) → 主力模型 (GPT-4o / Claude Sonnet)
│   └── complex (> 0.7) → 最强模型 (Claude Opus / o3)
│
├── chat() / stream_chat()
│   └── 主模型调用 → 失败 → fallback 到下一个 Provider
│
├── 4 个 Provider 实现
│   ├── OllamaProvider   — 本地模型，ollama.chat() 接口
│   ├── OpenAIProvider    — GPT-4o / o3，流式 tool_call 累积
│   ├── AnthropicProvider — Claude Opus/Sonnet，消息角色交替处理
│   └── DeepSeekProvider  — DeepSeek-V3，扩展 OpenAI 接口
│
└── 初始化模式
    ├── 配置文件 llm.providers 块（最精确）
    ├── 环境变量自动检测（零配置）
    └── 纯 Ollama 降级（默认）
```

### 2.5 基准评测框架（`benchmark/`）

v2.0 新增 HumanEval 风格基准评测，量化代码生成能力：

```
BenchmarkRunner
├── run_humaneval(num_tasks, k)
│   ├── 从 BenchmarkDataset 加载评测题（12 道内置）
│   ├── _run_single_humaneval(task)
│   │   ├── LLM 生成代码 → _extract_code() 清理
│   │   ├── CodeEvaluator.check_execution() 执行测试
│   │   └── 失败 → _self_repair() → 再次检测
│   ├── BenchmarkScorer.pass_at_k() 计算得分
│   └── _compare_with_benchmarks() 对标业界
│
├── CodeEvaluator
│   ├── check_execution() — 沙箱化测试执行
│   └── check_quality() — 语法 + lint + 复杂度 + 安全
│
├── 12 道内置评测题
│   ├── Easy: two_sum, LCP, valid_parentheses, flatten_nested
│   ├── Medium: LRU_cache, group_anagrams, LIS, course_schedule, merge_k_sorted
│   └── Hard: median_sorted_arrays, tree_serialization, calculator
│
└── 业界对比基准
    ├── Claude Opus 4: 92.5%
    ├── GPT-4o: 90.5%
    ├── Claude Sonnet 4: 89.5%
    ├── DeepSeek-V3: 88%
    └── Qwen3-Coder-30B: 72%
```

### 2.6 MCP 协议层（`mcp/`）

v2.1 新增 MCP (Model Context Protocol) 集成，实现双向工具生态扩展：

```
MCPManager (manager.py)
├── load_from_config(mcp_config)
│   └── 解析 config.yaml 的 mcp.servers 块
│
├── connect_all()
│   ├── _connect_server(name, cfg)
│   │   ├── stdio → StdioTransport(command, env)
│   │   └── sse → SSETransport(url, headers)
│   └── _discover_and_register(name, client, cfg)
│       ├── client.list_tools() → MCP 工具发现
│       ├── mcp_tool_to_turing_schema() → 转换为 Turing ToolDef
│       ├── make_caller() → 创建桥接闭包函数
│       └── _REGISTRY[f"mcp::{server}::{tool}"] → 动态注册
│
├── disconnect_server(name)
│   └── _unregister_tools(name) → 从 _REGISTRY 移除
│
└── get_status() / get_mcp_tool_names() / is_mcp_tool()

MCPClient (client.py)
├── 传输层
│   ├── StdioTransport — 子进程 stdin/stdout + select 非阻塞读
│   └── SSETransport — HTTP POST + SSE 后台监听线程
├── JSON-RPC 2.0 协议
│   ├── _handshake() → initialize + notifications/initialized
│   ├── list_tools() → tools/list
│   ├── call_tool(name, args) → tools/call
│   └── list_resources() / read_resource(uri)
└── 工具转换
    ├── _mcp_result_to_dict() → MCP 结果 → Turing dict 格式
    └── mcp_tool_to_turing_schema() → MCP inputSchema → Turing 参数 schema

MCPServer (server.py)
├── stdio JSON-RPC 2.0 服务
├── 支持方法：initialize / tools/list / tools/call / resources/list / resources/read / ping
├── 自动过滤 mcp:: 前缀工具（避免递归暴露）
├── 暴露资源：turing://strategies / turing://evolution / turing://gap_analysis
└── 入口：python -m turing.mcp.server
```

**设计决策：**

| 决策 | 实现 | 原因 |
|------|------|------|
| 同步 MCP 客户端 | 自建 sync 客户端（非 async SDK） | Turing 工具系统全同步，避免引入 asyncio |
| 命名空间隔离 | `mcp::server::tool` 格式 | 多服务器工具名冲突避免 |
| 动态注册 | 直接操作 `_REGISTRY` dict | 运行时连接/断开服务器 |
| 递归防护 | server.py 过滤 `mcp_` 前缀工具 | 避免 MCP 服务暴露 MCP 管理工具 |

### 2.7 RAG 引擎（`rag/engine.py`）

- **查询扩展**：自动展开同义词和相关关键词
- **代码感知分块**：按函数/类边界分块（而非固定长度），保持语义完整性
- **双存储后端**：优先 ChromaDB 向量库，无则降级为 JSON TF-IDF
- **索引 API**：`/index <路径>` 可索引本地项目到 RAG 知识库

### 2.8 演化系统（`evolution/tracker.py`）

自我演化是 Turing 的核心差异化能力。v2.0 新增了基准评测框架量化进化进度。

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
[失败恢复引擎] ── 8 种失败模式 × 3 级恢复策略
  ├── 模式：syntax_error / runtime_error / test_failure / timeout
  ├── 模式：resource_error / dependency_error / logic_error / unknown
  ├── 级别：immediate (快速修复) / deep (根因分析) / alternative (换方案)
  └── 自动构建恢复剧本（Playbook）
  ↓
[自训练模拟器] ── 合成任务训练弱项维度
  ↓
[十五维评分] → 综合能力画像
  ├── ① 代码质量      ② 调试能力       ③ 架构设计
  ├── ④ 执行效率      ⑤ 安全意识       ⑥ 沟通清晰度
  ├── ⑦ 工具多样性    ⑧ 推理深度       ⑨ 记忆利用率
  ├── ⑩ 学习速率      ⑪ 验证覆盖率     ⑫ 错误恢复力
  └── ⑬ 自主性        ⑭ 上下文管理     ⑮ 持续改进
```

### 2.9 元认知引擎（`evolution/metacognition.py`）

v0.8 新增的元认知系统，提供 6 维认知自我监控：

```
MetacognitiveEngine
├── 6 维认知雷达
│   ├── planning_quality     — 计划质量（结构化/完整性）
│   ├── tool_efficiency      — 工具效率（成功率/选择质量）
│   ├── error_recovery       — 错误恢复（恢复速度/策略有效性）
│   ├── creativity           — 创造性（方案多样性/创新度）
│   ├── focus                — 专注度（任务相关性/偏离检测）
│   └── overall              — 综合评分
│
├── 认知检查点 (checkpoint)
│   └── 在执行关键节点扫描 6 维雷达，检测认知偏差
│
├── 偏差检测 (bias detection)
│   ├── 确认偏差 — 是否只寻找支持假设的证据
│   ├── 锚定偏差 — 是否被初始信息过度影响
│   └── 可用性偏差 — 是否偏向最近使用的工具/方法
│
└── 置信校准 (confidence calibration)
    └── 评估自身判断的准确度，避免过度自信或不足
```

**策略预播种（6 大任务类型）：**

冷启动时基于 Claude Opus / Codex / Gemini / Copilot 最佳实践预载策略：
1. `bug_fix` — 先理解再修复，最小改动，必须验证
2. `feature` — 项目检测 → 编码 → 测试 → 质量检查
3. `refactor` — 结构分析 → 影响评估 → 批量修改 → 回归测试
4. `debug` — 深度推理，分析堆栈，逐步排查
5. `explain` — 结构提取 → 调用图 → 知识检索
6. `general` — 通用策略，适应性推理

### 2.10 VS Code Extension（`vscode-extension/`）

v3.6 新增 VS Code 原生扩展，通过 MCP 协议连接 Turing 智能体：

```
vscode-extension/
├── src/
│   ├── extension.ts     # 扩展入口：激活、命令注册、Webview 初始化
│   ├── mcpClient.ts     # MCP 客户端：stdio 子进程 + JSON-RPC 2.0 协议
│   └── chatView.ts      # 聊天面板：Webview HTML/CSS/JS + 消息通信
├── resources/turing-icon.svg
├── package.json         # VS Code 扩展清单：命令、视图、配置
└── tsconfig.json        # TypeScript 编译配置
```

**架构流程：**

```
VS Code UI (Webview Chat Panel)
    │
    ├── 用户输入 → extension.ts → mcpClient.ts
    │   │
    │   └── JSON-RPC → python -m turing.mcp.server
    │       │
    │       ├── initialize → tools/list → tools/call
    │       └── 82 个 Turing 工具可通过 MCP 调用
    │
    └── 工具结果 → chatView.ts → Webview 渲染
```

| 功能 | 实现 |
|------|------|
| 侧边栏聊天 | `TuringChatViewProvider` Webview，支持流式输出 |
| 代码解释 | 右键菜单 `turing.explainSelection`，获取选中代码发送到聊天 |
| MCP 初始化 | `TuringMCPClient.connect()` 启动子进程 + 握手 + 工具发现 |
| 超时保护 | 每个 MCP 请求 30s 超时，防止无限等待 |

## 3. 数据流

### 3.1 请求处理流

```
用户输入 "修复 auth.py 的 bug"
  │
  ├── [0] MemoryManager.retrieve(query, ["long_term", "persistent"])
  │   └── 返回: [历史 bug_fix 经验, auth 模块知识]
  │
  ├── [1] _load_relevant_strategy(query)
  │   └── 关键词匹配 "修复/bug" → 加载 bug_fix 策略模板 + 推荐工具
  │
  ├── [3] MetacognitiveEngine.start_task()
  │   └── 初始化 6 维认知雷达基线
  │
  ├── [4] _assess_and_plan(query)
  │   └── 中等复杂度 → 快速计划
  │
  ├── [5.1] LLM Router.chat() → read_file (只读并行)
  ├── [5.2] LLM Router.chat() → edit_file (副作用顺序) + ETF 提示注入
  ├── [5.3] LLM Router.chat() → run_tests (覆盖率 + 失败详情)
  │
  ├── [7] _manage_context_overflow() → Token-aware 压缩
  ├── [8] _post_task_reflect() → 深度反思 + 策略进化
  ├── [9] evolution.score_task() → 十五维评分更新
  │
  └── yield {"type": "done"}
```

### 3.2 记忆生命周期

```
任务开始
  ├── L2/L3 → 检索 → 注入 L1（工作记忆）
  ├── 自动项目索引 → detect_project + repo_map → 注入上下文
  │
任务执行中
  ├── 关键中间结果 → 写入 L1
  ├── 遇到知识盲区 → L4 (RAG/Web) → 结果写入 L1
  ├── 持久化 Shell 状态 → env/cwd 自动保持
  │
任务完成
  ├── 反思结果 → 写入 L2（长期记忆）
  ├── 发现稳定模式 → 归纳为策略 → 写入 L3（持久记忆）
  ├── 失败模式 → 恢复引擎记录 → 构建恢复剧本
  │
定期维护
  ├── 工作记忆 → 会话结束时清理
  ├── 长期记忆 → 知识蒸馏（合并冗余，每 50 次任务）
  └── 持久记忆 → Jaccard 去重（阈值 0.85）
```

### 3.3 持久化 Shell 会话

```
_ShellSession 单例
  │
  ├── run_command("cd /project && export API_KEY=xxx")
  │   └── 状态保存: cwd=/project, env={API_KEY: xxx}
  │
  ├── run_command("echo $API_KEY && pwd")
  │   └── 继承状态: 输出 "xxx\n/project"
  │
  ├── run_background("python server.py", label="dev-server")
  │   └── 返回 PID, 加入 _bg_processes 追踪表
  │
  ├── check_background("dev-server")
  │   └── 返回进程状态 + 最新输出
  │
  └── stop_background("dev-server")
      └── 发送 SIGTERM, 清理追踪表
```

## 4. 安全设计

### 4.1 命令执行安全

- **黑名单过滤**：`rm -rf /`, `DROP TABLE` 等危险命令被拦截
- **超时控制**：命令执行默认 30 秒超时
- **输出截断**：超长输出自动截断（`_truncate_output`），防止上下文爆炸
- **后台进程隔离**：后台进程通过 PID 管理，支持检查和终止

### 4.2 文件操作安全

- **路径黑名单**：`/etc/shadow`, `/etc/passwd` 等敏感路径禁止访问
- **非空目录保护**：`delete_file` 默认不删除非空目录，需显式确认
- **原子化编辑**：`multi_edit` 失败时自动回滚全部变更，保证一致性
- **diff 预览**：`edit_file` 操作返回 unified diff，方便审查

### 4.3 Web API 安全

- **路径安全检查**：文件浏览接口校验路径范围
- **输入校验**：工具参数通过 JSON Schema 验证类型和必填项
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
| `model.context_length` | `32768` | 模型上下文窗口大小（token） |
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
| `mcp.servers` | `{}` | MCP 服务器配置（server_name → transport/command/url） |

## 6. 项目结构

```
Coding_Agent/
├── main.py                         # CLI 入口（交互式 REPL / 单次执行）
├── config.yaml                     # 全局配置
├── pyproject.toml                  # 构建配置
├── requirements.txt                # 依赖列表
├── turing/                         # 核心包
│   ├── __init__.py                 # 版本号 + 架构说明
│   ├── agent.py                    # TuringAgent（10 阶段主循环）
│   ├── config.py                   # Config 单例（YAML 加载 + 点路径访问）
│   ├── prompt.py                   # SYSTEM_PROMPT（28 项能力声明 + 21 专题段落）
│   ├── llm/                        # 多 Provider LLM 路由层
│   │   ├── __init__.py              # 包入口 + 导出
│   │   ├── provider.py              # LLMProvider ABC + 4 实现
│   │   └── router.py                # ModelRouter（复杂度路由 + fallback）
│   ├── mcp/                        # MCP 协议集成层
│   │   ├── __init__.py              # 包入口（导出 MCPClient, MCPManager）
│   │   ├── client.py                # MCP 客户端（stdio/SSE 双传输 + JSON-RPC 2.0）
│   │   ├── manager.py               # 多服务器连接管理 + 工具动态注册
│   │   └── server.py                # MCP 服务端（暴露 Turing 工具给外部客户端）
│   ├── benchmark/                  # 基准评测框架
│   │   ├── __init__.py              # 包入口
│   │   ├── evaluator.py             # CodeEvaluator + BenchmarkScorer
│   │   ├── datasets.py              # HumanEvalTask + 12 内置评测题
│   │   └── runner.py                # BenchmarkRunner（评测调度 + 自修复）
│   ├── memory/                     # 四层记忆系统
│   │   ├── manager.py              # MemoryManager（跨层检索 + 统一排序）
│   │   ├── working.py              # L1 工作记忆（TF-IDF + 会话级）
│   │   ├── long_term.py            # L2 长期记忆（ChromaDB / JSON 降级）
│   │   └── persistent.py           # L3 持久记忆（YAML + Jaccard 去重）
│   ├── rag/
│   │   └── engine.py               # RAG 引擎（查询扩展 + 代码分块）
│   ├── evolution/
│   │   ├── tracker.py              # EvolutionTracker（15 维 + 策略 + 失败恢复 + 自训练）
│   │   ├── metacognition.py        # MetacognitiveEngine（6维认知雷达）
│   │   └── competitive.py          # CompetitiveIntelligence（16维×7竞品对标）
│   ├── lsp/                        # LSP 代码补全服务器
│   │   ├── __init__.py              # 包入口
│   │   ├── server.py                # LSP 服务器（JSON-RPC/stdio + AST 补全）
│   │   └── __main__.py              # python -m turing.lsp 入口
│   └── tools/                      # 82 个工具
│       ├── registry.py             # 工具注册表 + Schema 生成 + 安全调度
│       ├── file_tools.py           # 文件操作 (9)
│       ├── command_tools.py        # 命令执行 (5): Shell + 后台进程 + auto_fix
│       ├── search_tools.py         # 代码搜索 + 智能上下文 + 上下文压缩 (6)
│       ├── git_tools.py            # Git 操作 (8)
│       ├── test_tools.py           # 测试 (2)
│       ├── quality_tools.py        # 质量 (3)
│       ├── refactor_tools.py       # 重构 (3)
│       ├── project_tools.py        # 项目 (2)
│       ├── ast_tools.py            # AST (4): 代码结构 + 调用图 + 复杂度 + 依赖图
│       ├── memory_tools.py         # 记忆 (3)
│       ├── external_tools.py       # 外部 (3): RAG + Web 搜索 + URL 获取
│       ├── evolution_tools.py      # 演化 (12): 含竞争力分析 + 假设验证
│       ├── metacognition_tools.py  # 元认知 (2)
│       ├── benchmark_tools.py      # 基准评测 (3)
│       ├── mcp_tools.py            # MCP 集成 (3)
│       ├── agent_tools.py          # 子 Agent (1)
│       └── github_tools.py         # GitHub API (5)
├── web/                            # Web UI
│   ├── server.py                   # Flask + SSE 后端
│   ├── templates/index.html        # VS Code 风格前端
│   └── static/                     # CSS + JS 静态资源
├── vscode-extension/               # VS Code 原生扩展 (v3.6)
│   ├── src/extension.ts            # 扩展入口 + 命令注册
│   ├── src/mcpClient.ts            # MCP stdio 客户端 (JSON-RPC 2.0)
│   ├── src/chatView.ts             # 聊天面板 Webview Provider
│   └── package.json                # 扩展清单
├── tests/                          # 测试套件（21 项全通过）
├── docs/                           # 文档
│   ├── ARCHITECTURE.md             # 本文件
│   └── EXAMPLES.md                 # 使用示例集
├── turing_data/                    # 运行时数据（自动生成）
└── generated_code/                 # Agent 生成的代码示例
```

## 7. 扩展指南

### 添加新工具

1. 在 `turing/tools/` 下创建或修改模块文件
2. 使用 `@tool` 装饰器定义工具（name, description, parameters）
3. 在 `agent.py` 中添加 `import turing.tools.xxx  # noqa: F401`
4. 如果是只读工具，添加到 `_READONLY_TOOLS` 集合
5. 如果是 v1.0+ 关键工具，添加到 `expected` 集合进行启动检查

### 添加新记忆层

1. 在 `turing/memory/` 下实现存储类
2. 实现 `write()`, `search()`, `get_stats()` 等接口
3. 在 `MemoryManager` 中集成，设置层级权重

### 添加新演化维度

1. 在 `EvolutionTracker._score_dimensions()` 中添加评分逻辑（当前 15 维）
2. 在 `SYSTEM_PROMPT` 中描述新维度的能力要求
3. 更新 `gap_analysis` 工具的差距分析逻辑

### 添加新元认知维度

1. 在 `MetacognitiveEngine` 中添加维度定义
2. 实现对应的评估逻辑和偏差检测规则
3. 集成到 checkpoint 扫描流程

### 开发 VS Code Extension

1. 进入 `vscode-extension/` 目录
2. 安装依赖：`npm install`
3. 编译 TypeScript：`npm run compile`
4. 在 VS Code 中按 F5 启动扩展调试宿主
5. MCP 通信通过 `TuringMCPClient` 类管理，见 `src/mcpClient.ts`

---

*文档版本: v3.6.0 · 最后更新: 2025-07*
