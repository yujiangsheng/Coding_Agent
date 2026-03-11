<div align="center">

# 🤖 Turing

**自进化编程智能体 · Self-Evolving Coding Agent**

*多模型 AI Coding Agent，具备四层记忆、61 内置工具、MCP 协议集成、多 Provider LLM 路由、基准评测、元认知、自我演化*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-green.svg)](https://python.org)
[![Model: Multi-Provider](https://img.shields.io/badge/Model-Ollama%20%7C%20OpenAI%20%7C%20Anthropic%20%7C%20DeepSeek-orange.svg)](https://ollama.com)
[![Version](https://img.shields.io/badge/Version-2.1.0-purple.svg)](CONTRIBUTING.md)
[![Tools](https://img.shields.io/badge/Tools-61-brightgreen.svg)](#-工具一览61-工具16-个模块)
[![Tests](https://img.shields.io/badge/Tests-19%20passed-success.svg)](tests/)

</div>

---

## ✨ 特性

### 核心能力

- **🧠 四层记忆系统** — 工作记忆 / 长期记忆 / 持久记忆 / 外部记忆（RAG），TF-IDF 中文检索，越用越懂你
- **🔧 61 内置工具** — 文件管理（含 diff 预览 + 原子化多文件编辑）、持久化 Shell 会话（env/cwd 跨调用保持 + 后台进程管理）、Git 完整工作流、代码搜索 + Repo Map + 智能上下文、测试运行（覆盖率 + 失败详情）、AST 代码分析、批量重构、基准评测、MCP 外部工具集成等
- **🔌 MCP 协议集成** — 通过 Model Context Protocol 连接外部工具服务器（stdio/SSE），自动发现并注册外部工具；可作为 MCP 服务端暴露自身工具给 Claude Code / Cursor / VS Code（对标 Claude Code 工具扩展）
- **🤖 多 Provider LLM 路由** — 支持 Ollama / OpenAI / Anthropic / DeepSeek，按任务复杂度自动路由到最优模型，失败时自动 fallback
- **📊 基准评测框架** — 内置 12 道 HumanEval 风格编程题，pass@k 评分 + 业界分数对比（Claude Opus / GPT-4o / Gemini），自修复评测
- **🔄 自我演化** — 任务反思 → 经验积累 → 策略进化 → 知识蒸馏 → AI 工具对比学习 → 失败恢复引擎 → 自训练模拟器 → 15 维评分系统
- **🧩 高级推理引擎** — 链式推理（CoT）分层任务分解、动态温度调节、编辑-测试-修复（ETF）自动验证循环
- **🔍 元认知系统** — 6 维认知雷达、偏差检测、置信校准、认知自适应
- **🧠 智能上下文收集** — import 链追踪 + 错误堆栈解析 + 符号引用查找，精准减少无效 token 占用
- **⚡ 并行工具执行** — 21 个只读工具自动并发运行（ThreadPoolExecutor），大幅提升多文件操作效率
- **🔒 安全守护** — 命令黑名单、路径黑名单、输出截断、非空目录删除保护
- **🏠 本地优先** — 默认基于 Ollama 本地部署，可选接入云端 LLM

### 对标顶尖工具的能力（v2.0）

| 能力 | Turing | Aider | Cursor | Claude Code | Codex |
|------|--------|-------|--------|-------------|-------|
| 多模型 LLM 路由 | ✅ | ✅ | ✅ | ❌ | ✅ |
| 基准评测框架 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 智能上下文收集 | ✅ | ❌ | ✅ | ✅ | ✅ |
| 持久化 Shell 会话 | ✅ | ❌ | ❌ | ✅ | ✅ |
| 后台进程管理 | ✅ | ❌ | ❌ | ❌ | ✅ |
| 原子化多文件编辑 | ✅ | ❌ | ✅ | ❌ | ✅ |
| Token-aware 上下文管理 | ✅ | ❌ | ✅ | ✅ | ✅ |
| 自动项目索引 | ✅ | ✅ | ✅ | ❌ | ✅ |
| Diff 预览 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Git 完整工作流 | ✅ | ✅ | ✅ | ✅ | ✅ |
| Repo Map | ✅ | ✅ | ❌ | ❌ | ❌ |
| Auto Lint-Fix | ✅ | ✅ | ✅ | ❌ | ❌ |
| 上下文压缩 (/compact) | ✅ | ❌ | ❌ | ✅ | ❌ |
| 一键撤销 (/undo) | ✅ | ✅ | ❌ | ❌ | ❌ |
| 自我演化记忆 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 元认知监控 | ✅ | ❌ | ❌ | ❌ | ❌ |
| 失败恢复引擎 | ✅ | ❌ | ❌ | ❌ | ❌ |
| MCP 协议集成 | ✅ | ❌ | ❌ | ✅ | ❌ |
| 本地优先 + 云端可选 | ✅ | ✅ | ❌ | ❌ | ❌ |

## 📋 架构概览

```
┌──────────────────────────────────────────────────────────────────────┐
│              CLI (main.py) / Web UI (web/server.py)                  │
│             交互式 REPL · 单次执行 · Flask SSE 服务                  │
├──────────────────────────────────────────────────────────────────────┤
│                     TuringAgent (agent.py)                           │
│  记忆预加载 → 策略注入 → 工具推荐 → 元认知初始化 → CoT推理          │
│  → LLM推理 → 工具执行(并行/顺序) → 错误恢复 → 上下文管理 → 反思     │
│  ┌──────────┐ ┌───────────┐ ┌────────────────┐ ┌─────────────────┐ │
│  │ CoT 推理 │ │ ETF 循环  │ │Token-aware     │ │ 并行工具执行    │ │
│  │ 任务分解 │ │ 编辑-测试 │ │上下文管理      │ │ ThreadPool      │ │
│  │ 动态温度 │ │ -修复     │ │优先级打分+压缩 │ │ 20只读工具并发  │ │
│  └──────────┘ └───────────┘ └────────────────┘ └─────────────────┘ │
│  ┌──────────────────┐ ┌────────────────┐ ┌──────────────────────┐  │
│  │ 持久化 Shell     │ │ 自动项目索引   │ │ Auto Lint-Fix +      │  │
│  │ env/cwd保持      │ │ 会话启动       │ │ Auto Commit          │  │
│  │ 后台进程管理     │ │ repo_map注入   │ │ Auto Undo/Rollback   │  │
│  └──────────────────┘ └────────────────┘ └──────────────────────┘  │
├───────────┬───────────┬───────────┬────────────────────────────────┤
│  Tools    │  Memory   │   RAG     │   Evolution + Metacognition    │
│  (61个    │  (4层)    │  Engine   │                                │
│  16模块)  │           │           │                                │
├───────────┼───────────┼───────────┼────────────────────────────────┤
│ file(9)   │ L1 working│ ChromaDB  │ 15维评分 · 策略进化            │
│ command(4)│ L2 long   │  / JSON   │ 失败恢复引擎(8模式×3级)       │
│ search(4) │ L3 persist│ 查询扩展  │ 自训练模拟器                   │
│ git(8)    │ L4 外部   │ 代码分块  │ 经验合成·知识迁移              │
│ test(2)   │           │           │ 6维认知雷达                    │
│ quality(3)│ TF-IDF    │           │ 偏差检测·置信校准              │
│ refactor  │ 跨层排序  │           │ 认知自适应                     │
│ project   │ Jaccard   │           │ 工具探索顾问                   │
│ ast(3)    │  去重     │           │ 恢复剧本构建                   │
│ memory(3) │           │           │                                │
│ rag/web   │           │           │                                │
│ evolve(10)│           │           │                                │
│ metacog(2)│           │           │                                │
│benchmark3 │           │           │                                │
│ mcp(3)    │           │           │                                │
└───────────┴───────────┴───────────┴────────────────────────────────┘
         ↕                  ↕               ↕
    LLM Router          向量数据库      turing_data/
  (Multi-Provider)     (ChromaDB)      (JSON/YAML)
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 安装 Ollama (macOS)
brew install ollama

# 拉取模型
ollama pull qwen3-coder:30b

# 确保 Ollama 服务运行中
ollama serve
```

### 2. 安装 Turing

```bash
git clone https://github.com/yujiangsheng/Coding_Agent.git
cd Coding_Agent

# 方式 A：pip 安装（推荐）
pip install -e .

# 方式 B：仅安装依赖
pip install -r requirements.txt
```

### 3. 启动

```bash
# 交互模式（CLI）
python main.py

# 指定模型
python main.py -m qwen3-coder:30b

# 单次执行
python main.py --one-shot "用 Python 实现一个 LRU Cache"

# Web UI 模式
python web/server.py                  # http://127.0.0.1:5000
python web/server.py -p 8080          # 自定义端口
```

## 💡 使用示例

### 交互式对话

```
 ___________            .__
 \__    ___/_ _______  _|__| ____    ____
   |    | |  |  \_  __ \|  |/    \  / ___\
   |    | |  |  /|  | \/|  |   |  \/ /_/  >
   |____| |____/ |__|   |__|___|  /\___  /
                                \//_____/
    自进化编程智能体 · Powered by Qwen3-Coder

输入编程任务开始对话。输入 /help 查看命令。输入 /exit 退出。

You > 帮我写一个快速排序算法

💭 检索到 2 条相关记忆
🔧 调用工具: write_file {"path": "quicksort.py", "content": "..."}
   ✓ {"status": "ok", "path": "quicksort.py"}
🔧 调用工具: run_command {"command": "python quicksort.py"}
   ✓ {"exit_code": 0, "output": "[1, 2, 3, 4, 5]"}

┌─ Turing ─────────────────────────────────────┐
│ 已创建 quicksort.py 并验证通过。             │
└──────────────────────────────────────────────┘

📝 经验记录: success (使用了 2 次工具调用)
```

### 常用命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助 |
| `/status` | 查看记忆和演化统计 |
| `/memory <关键词>` | 搜索所有记忆层 |
| `/strategies` | 列出已学会的策略模板 |
| `/evolution` | 查看进化日志 |
| `/index <路径>` | 索引项目到 RAG 知识库 |
| `/compact` | 压缩上下文（保留关键信息，释放 token 空间） |
| `/undo` | 撤销上一次文件修改（Git 级回滚） |
| `/diff` | 查看当前会话中所有文件变更的 diff 预览 |
| `/new` | 开始新会话 |
| `/exit` | 退出 |

> 更多示例请参考 [docs/EXAMPLES.md](docs/EXAMPLES.md)

## 🧠 四层记忆系统

| 层级 | 名称 | 存储方式 | 生命周期 | 用途 |
|------|------|----------|----------|------|
| L1 | 工作记忆 | 内存 + JSON | 会话级 | 当前任务上下文、计划、中间结果 |
| L2 | 长期记忆 | ChromaDB 向量库 | 跨会话 | 历史经验、编程知识、用户偏好 |
| L3 | 持久记忆 | YAML/JSON 文件 | 永久 | 项目架构、策略模板、进化日志 |
| L4 | 外部记忆 | RAG + 搜索引擎 | 实时 | 文档检索、Web 搜索、AI 工具参考 |

### 记忆检索引擎

- **TF-IDF 关键词检索** — 工作记忆与持久记忆采用 TF-IDF 评分，支持中文 bigram 分词
- **时间衰减加权** — `score *= 1.0 / (1.0 + age_hours × 0.01)`，近期记忆优先
- **跨层统一排序** — 持久记忆 ×1.2 > 长期记忆 ×1.0 > 工作记忆 ×0.8
- **Jaccard 去重** — 持久层写入时检查相似度 ≥0.85 的条目，避免重复存储

```
用户请求 → 检索 L2+L3 → 加载到 L1
    ↓
执行任务（L1 持续更新）
    ↓ 遇到知识盲区
检索 L4（RAG/Web） → 结果写入 L1
    ↓
任务完成 → 反思 → 写入 L2
    ↓ 发现稳定模式
归纳为规则 → 写入 L3
```

## 🔄 自我演化机制

1. **经验积累** — 每次任务后自动 LLM 深度反思，记录成功/失败经验、工具使用、耗时
2. **策略进化** — 同类任务 ≥5 条经验后，时间加权归纳策略模板（推荐工具、步骤、常见陷阱）
3. **知识蒸馏** — 每 50 次任务触发一次，合并冗余反思，淘汰低质量条目
4. **AI 工具学习** — 分析 Claude Opus / Codex / Gemini / Copilot 的策略并内化
5. **策略预播种** — 基于顶尖 AI 工具知识库，冷启动即加载专家级任务策略（6 大任务类型）
6. **十五维能力评分** — 代码质量 / 调试能力 / 架构设计 / 执行效率 / 安全意识 / 沟通清晰度 / 工具多样性 / 推理深度 / 记忆利用率 / 学习速率 / 验证覆盖率 / 错误恢复力 / 自主性 / 上下文管理 / 持续改进
7. **工具效率分析** — 追踪每个工具的成功关联率，识别高效工具组合
8. **决策质量追踪** — 评估工具选择质量和推理链深度
9. **失败恢复引擎** — 8 种失败模式 × 3 级恢复策略，自动构建恢复剧本
10. **自训练模拟器** — 生成合成任务并自我训练，持续提升弱项
11. **元认知监控** — 6 维认知雷达（计划质量 / 工具效率 / 错误恢复 / 创造性 / 专注度 / 综合），偏差检测与置信校准

## 🔧 工具一览（61 工具，16 个模块）

| 类别 | 工具 | 说明 |
|------|------|------|
| **文件操作 (9)** | `read_file` | 读取文件（支持行号范围） |
| | `write_file` | 创建/覆盖文件（自动创建目录） |
| | `edit_file` | 精确替换编辑（diff 预览 + 多匹配处理 + 近似提示） |
| | `generate_file` | AI 生成完整文件（保留已有内容确认） |
| | `multi_edit` | 原子化多文件编辑（事务性，失败自动回滚） |
| | `move_file` | 移动/重命名文件或目录 |
| | `copy_file` | 复制文件或目录 |
| | `delete_file` | 安全删除文件（非空目录保护） |
| | `find_files` | 按名称/模式/内容搜索文件（glob + regex） |
| **命令执行 (4)** | `run_command` | 持久化 Shell（env/cwd 跨调用保持 + 安全过滤） |
| | `run_background` | 启动后台进程（服务器、watch 等） |
| | `check_background` | 查看后台进程输出与状态 |
| | `stop_background` | 终止后台进程 |
| **代码搜索 (4)** | `search_code` | 文本/正则搜索（ripgrep/grep） |
| | `list_directory` | 列出目录内容（递归 + 文件大小） |
| | `repo_map` | 代码仓库结构地图（模块 + 函数 + 类） |
| | `smart_context` | 智能上下文收集（import 链 / 符号引用 / 错误堆栈解析） |
| **Git 操作 (8)** | `git_status` | 查看仓库状态 |
| | `git_diff` | 查看差异（工作区/暂存区/提交间） |
| | `git_log` | 查看提交历史（支持过滤） |
| | `git_blame` | 逐行归因 |
| | `git_add` | 暂存文件 |
| | `git_commit` | 提交变更 |
| | `git_branch` | 分支管理 |
| | `git_stash` | 暂存/恢复工作区 |
| **测试运行 (2)** | `run_tests` | 自动检测并运行测试（pytest/jest/go test + 覆盖率 + 失败详情） |
| | `generate_tests` | 为源文件生成测试脚手架 |
| **代码质量 (3)** | `lint_code` | 运行 Linter（Ruff/flake8/ESLint 等） |
| | `format_code` | 运行代码格式化（Black/Prettier 等） |
| | `type_check` | 运行类型检查（mypy/pyright/tsc） |
| **批量重构 (3)** | `batch_edit` | 跨文件批量搜索替换（支持正则） |
| | `rename_symbol` | 安全重命名符号 |
| | `impact_analysis` | 跨文件影响分析（修改前评估依赖影响） |
| **项目分析 (2)** | `detect_project` | 自动检测项目类型、语言、框架 |
| | `analyze_dependencies` | 解析依赖文件 |
| **AST 代码分析 (3)** | `code_structure` | 提取文件/目录的类、函数、导入结构 |
| | `call_graph` | 分析函数调用关系图和依赖链 |
| | `complexity_report` | 圈复杂度分析报告（识别高复杂度函数） |
| **记忆管理 (3)** | `memory_read` | 检索记忆（working/long_term/persistent） |
| | `memory_write` | 写入记忆 |
| | `memory_reflect` | 任务反思 |
| **外部搜索 (2)** | `rag_search` | RAG 本地文档检索（查询扩展 + 代码分块） |
| | `web_search` | DuckDuckGo 搜索 |
| **自我演化 (10)** | `learn_from_ai_tool` | 学习 AI 工具策略 |
| | `gap_analysis` | 能力差距分析 + 改进路线图 |
| | `evolve_strategies` | 批量策略进化 |
| | `distill_knowledge` | 知识蒸馏（合并冗余、淘汰低质量） |
| | `seed_strategies` | 策略预播种 |
| | `explore_tools` | 工具探索与推荐 |
| | `failure_recovery` | 失败恢复与剧本构建 |
| | `self_training` | 自训练模拟器 |
| | `build_playbook` | 恢复剧本构建 |
| | `cross_task_transfer` | 跨任务知识迁移 |
| **元认知 (2)** | `metacognition_checkpoint` | 认知检查点（6 维雷达扫描） |
| | `metacognition_report` | 元认知综合报告 |
| **基准评测 (3)** | `run_benchmark` | HumanEval 风格代码生成评测（pass@k） |
| | `eval_code` | 多维度代码质量评估（语法 + lint + 复杂度 + 安全） |
| | `benchmark_trend` | 历史评测分数趋势追踪 |
| **MCP 集成 (3)** | `mcp_list_servers` | 列出已配置的 MCP 服务器及连接状态 |
| | `mcp_list_tools` | 发现已连接 MCP 服务器的外部工具 |
| | `mcp_call_tool` | 调用外部 MCP 服务器工具（mcp::server::tool） |

## 🌐 Web UI

Turing 提供 VS Code 风格的 Web 界面，基于 Flask + Server-Sent Events：

```bash
python web/server.py                  # http://127.0.0.1:5000
python web/server.py -p 8080          # 自定义端口
python web/server.py --host 0.0.0.0   # 允许外部访问
```

**Web API 路由：**

| 方法 | 路由 | 说明 |
|------|------|------|
| POST | `/api/chat` | SSE 流式聊天 |
| GET | `/api/status` | 记忆与演化统计 |
| GET | `/api/memory/search?q=` | 跨层记忆搜索 |
| GET | `/api/strategies` | 策略模板列表 |
| GET | `/api/evolution` | 进化日志 |
| POST | `/api/new-session` | 新建会话 |
| POST | `/api/index-project` | 索引项目到 RAG |
| GET | `/api/files/list?path=` | 列出目录 |
| GET | `/api/files/read?path=` | 读取文件 |

## 🗂 数据目录结构

```
turing_data/
├── working_memory/          # L1: 工作记忆
│   └── session_*.json
├── long_term_memory/        # L2: 长期记忆
│   ├── chroma_db/           # ChromaDB（如已安装）
│   └── fallback_store.json  # 降级存储
├── persistent_memory/       # L3: 持久记忆
│   ├── projects/            # 项目知识库
│   ├── strategies/          # 策略模板
│   ├── index.json           # 持久记忆索引
│   └── evolution_log.json   # 进化日志
├── evolution/               # 演化数据
│   └── reflections.json     # 任务反思记录
└── external_memory/         # L4: 外部记忆
    ├── rag_db/              # RAG 索引数据
    ├── docs/                # 本地文档（放入后用 /index 索引）
    └── ai_tools_analysis/   # AI 工具学习笔记
```

## ⚙️ 配置

编辑 `config.yaml` 自定义行为：

```yaml
model:
  name: "qwen3-coder:30b"   # Ollama 模型名
  temperature: 0.3           # 代码生成温度（反思用 0.6）
  max_iterations: 20         # Agent 最大迭代轮次

memory:
  data_dir: "turing_data"    # 数据存储目录
  working:
    max_context_ratio: 0.3   # 工作记忆占上下文的最大比例
    keep_recent: 5           # 压缩时保留最近 N 条
  long_term:
    collection: "turing_long_term"
    decay_factor: 0.95       # 记忆衰减因子
  persistent:
    dir: "persistent_memory" # 持久记忆子目录

evolution:
  strategy_threshold: 5      # 触发策略进化的最小经验数
  distill_interval: 50       # 触发知识蒸馏的任务间隔

security:
  blocked_commands:           # 禁止执行的命令模式
    - "rm -rf /"
    - "DROP TABLE"
  blocked_paths:              # 禁止访问的路径
    - "/etc/shadow"
    - "/etc/passwd"

# MCP 协议集成（v2.1 新增）
# mcp:
#   servers:
#     filesystem:
#       transport: stdio
#       command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
#     github:
#       transport: sse
#       url: http://localhost:3000/sse
#       headers:
#         Authorization: "Bearer ghp_xxx"
```

## 📦 依赖

| 包 | 用途 | 是否必须 |
|----|------|----------|
| `ollama` | 本地大模型调用 | ✅ 必须 |
| `pyyaml` | 配置文件解析 | ✅ 必须 |
| `rich` | 终端 UI 渲染 | ✅ 必须 |
| `flask` | Web UI 后端 | ⚡ 推荐（Web 界面需要） |
| `chromadb` | 向量数据库（长期记忆 + RAG） | ⚡ 推荐（无则降级为 JSON） |
| `openai` | OpenAI / DeepSeek API 调用 | ⚡ 可选（云端模型需要） |
| `anthropic` | Anthropic Claude API 调用 | ⚡ 可选（Claude 模型需要） |
| `duckduckgo-search` | Web 搜索 | ⚡ 可选 |

## 🗺 演化路线图

| 版本 | 里程碑 | 状态 |
|------|--------|------|
| v0.1 | 基础能力：文件读写 + 命令执行 + 代码搜索 | ✅ 已完成 |
| v0.2 | 工作记忆：会话内上下文管理 | ✅ 已完成 |
| v0.3 | 长期记忆：跨会话经验积累 | ✅ 已完成 |
| v0.4 | **可靠性 + 智能化 + 规模化**：edit_file 多匹配处理、自动重试、TF-IDF 记忆检索（中文 bigram）、跨层排序、RAG 查询扩展、代码分块、Jaccard 去重、元推理框架、六维评分、循环检测、Git/测试/质量/重构/项目分析 26 工具 | ✅ 已完成 |
| v0.5 | **高级推理 + 策略预播种**：CoT 链式推理分层分解、智能工具路由、编辑-测试-修复（ETF）验证循环、动态温度调节、6 大任务类型策略预播种、语义错误分析与自动修正 | ✅ 已完成 |
| v0.6 | **深度代码分析 + 并行执行**：AST 代码结构提取、函数调用关系图、圈复杂度报告、跨文件影响分析、并行工具执行（ThreadPoolExecutor）、优先级滑动窗口上下文管理、对话摘要折叠、十一维能力评分（31 工具） | ✅ 已完成 |
| v0.7 | **对标顶尖 + Git 完整工作流**：与 Aider/Cursor/Claude Code 差距分析、Git 完整工作流（add/commit/branch/stash）、Diff 预览、Repo Map、Auto Lint-Fix、上下文压缩（/compact）、一键撤销（/undo）（41 工具） | ✅ 已完成 |
| v0.8 | **元认知系统**：MetacognitiveEngine（6 维认知雷达）、偏差检测、置信校准、认知自适应、经验合成器、跨任务知识迁移（46 工具） | ✅ 已完成 |
| v0.9 | **失败恢复 + 自我训练**：失败恢复引擎（8 模式 × 3 级恢复策略）、自训练模拟器、恢复剧本构建、工具探索顾问（48 工具） | ✅ 已完成 |
| v1.0 | **生产级完善**：持久化 Shell 会话（env/cwd 跨调用保持）、后台进程管理、文件管理（move/copy/delete/find）、原子化多文件编辑（multi_edit）、Token-aware 上下文管理、测试覆盖率 + 失败详情、自动项目索引（54 工具） | ✅ 已完成 |
| v2.0 | **多模型 + 基准评测**：多 Provider LLM 路由（Ollama/OpenAI/Anthropic/DeepSeek）、按复杂度自动路由 + fallback、HumanEval 基准评测框架（12 题 + pass@k + 自修复）、业界分数对比、智能上下文收集（import 链 + 错误堆栈 + 符号引用）、多维代码质量评估（58 工具） | ✅ 已完成 |
| v2.1 | **MCP 协议集成**：MCP 客户端（stdio/SSE 双传输 + 自动工具发现注册）、MCP 服务端（暴露 61 工具给外部 AI 客户端）、多服务器管理（命名空间隔离）、3 个 MCP 管理工具（对标 Claude Code 工具扩展）（61 工具） | ✅ 已完成 |
| v2.2 | 沙箱隔离（Docker 容器化代码执行） | 📋 计划中 |
| v2.3 | 多模态支持（图片/截图/UML 理解） | 📋 计划中 |
| v2.4 | IDE 插件（VS Code Extension） | 📋 计划中 |

## 📄 License

[MIT License](LICENSE) · Copyright (c) 2026 Jiangsheng Yu

## 👤 作者

**Jiangsheng Yu** — 设计、开发与维护
