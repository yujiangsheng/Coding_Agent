<div align="center">

# 🤖 Turing

**自进化编程智能体 · Self-Evolving Coding Agent**

*基于 Qwen3-Coder 本地大模型，具备四层记忆系统、26+ 内置工具和持续自我演化能力*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-green.svg)](https://python.org)
[![Model: Qwen3-Coder](https://img.shields.io/badge/Model-Qwen3--Coder%3A30B-orange.svg)](https://ollama.com)
[![Version](https://img.shields.io/badge/Version-0.4.0-purple.svg)](CONTRIBUTING.md)

</div>

---

## ✨ 特性

- **🧠 四层记忆系统** — 工作记忆 / 长期记忆 / 持久记忆 / 外部记忆（RAG），TF-IDF 中文检索，越用越懂你
- **🔄 自我演化** — 任务后自动反思，积累经验，策略进化，知识蒸馏，六维能力评分
- **🔧 26+ 内置工具** — 文件操作、命令执行、代码搜索、Git 操作、测试运行、代码质量检查、批量重构、项目分析、记忆管理、RAG 检索、Web 搜索、AI 工具学习
- **🧩 元推理框架** — 任务复杂度评估、策略匹配、循环检测、上下文溢出管理
- **📚 向顶尖 AI 学习** — 分析 Claude Opus / Codex / Gemini / Copilot 的策略并内化
- **🌐 双界面** — 交互式 CLI（Rich 渲染）+ VS Code 风格 Web UI（Flask SSE）
- **🔒 安全守护** — 命令黑名单、路径黑名单、输出截断，防止误操作
- **🏠 完全本地** — 基于 Ollama 本地部署，数据不出本机

## 📋 架构概览

```
┌─────────────────────────────────────────────────────────┐
│           CLI (main.py) / Web UI (web/server.py)        │
│          交互式 REPL · 单次执行 · Flask SSE 服务        │
├─────────────────────────────────────────────────────────┤
│                  TuringAgent (agent.py)                  │
│   记忆预加载 → 任务规划 → 工具调用循环 → 反思总结       │
│   ┌─────────┐  ┌──────────┐  ┌──────────┐              │
│   │元推理框架│  │循环检测  │  │上下文管理│              │
│   └─────────┘  └──────────┘  └──────────┘              │
├──────────┬───────────┬──────────┬───────────────────────┤
│  Tools   │  Memory   │   RAG    │   Evolution           │
│ (26+个)  │  (4层)    │  Engine  │   Tracker             │
├──────────┼───────────┼──────────┼───────────────────────┤
│ file     │ L1 working│ ChromaDB │ 经验积累              │
│ command  │ L2 long   │  / JSON  │ 策略进化              │
│ search   │ L3 persist│ fallback │ 知识蒸馏              │
│ memory   │ L4 外部   │          │ AI 工具学习           │
│ git      │           │ 查询扩展 │ 六维评分              │
│ test     │ TF-IDF    │ 代码分块 │ 工具效率分析          │
│ quality  │ 中文分词  │          │ 决策质量追踪          │
│ refactor │ 跨层排序  │          │                       │
│ project  │ Jaccard   │          │                       │
│ rag/web  │  去重     │          │                       │
│ evolve   │           │          │                       │
└──────────┴───────────┴──────────┴───────────────────────┘
         ↕                  ↕               ↕
    Ollama API          向量数据库      turing_data/
  (Qwen3-Coder)       (ChromaDB)      (JSON/YAML)
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
5. **六维能力评分** — 代码质量 / 调试能力 / 架构设计 / 执行效率 / 安全意识 / 沟通清晰度
6. **工具效率分析** — 追踪每个工具的成功关联率，识别高效工具组合

## 🔧 工具一览（26+ 工具）

| 类别 | 工具 | 说明 |
|------|------|------|
| **文件操作** | `read_file` | 读取文件（支持行号范围） |
| | `write_file` | 创建/覆盖文件（自动创建目录） |
| | `edit_file` | 精确替换编辑（多匹配处理 + 近似提示） |
| **命令执行** | `run_command` | 执行 Shell 命令（安全过滤 + 超时控制） |
| **代码搜索** | `search_code` | 文本/正则搜索（ripgrep/grep） |
| | `list_directory` | 列出目录内容（递归 + 文件大小） |
| **Git 操作** | `git_status` | 查看仓库状态 |
| | `git_diff` | 查看差异（工作区/暂存区/提交间） |
| | `git_log` | 查看提交历史（支持过滤） |
| | `git_blame` | 逐行归因 |
| **测试运行** | `run_tests` | 自动检测并运行测试（pytest/jest/go test 等） |
| | `generate_tests` | 为源文件生成测试脚手架 |
| **代码质量** | `lint_code` | 运行 Linter（Ruff/flake8/ESLint 等） |
| | `format_code` | 运行代码格式化（Black/Prettier 等） |
| | `type_check` | 运行类型检查（mypy/pyright/tsc） |
| **批量重构** | `batch_edit` | 跨文件批量搜索替换（支持正则） |
| | `rename_symbol` | 安全重命名符号 |
| **项目分析** | `detect_project` | 自动检测项目类型、语言、框架 |
| | `analyze_dependencies` | 解析依赖文件 |
| **记忆管理** | `memory_read` | 检索记忆（working/long_term/persistent） |
| | `memory_write` | 写入记忆 |
| | `memory_reflect` | 任务反思 |
| **外部搜索** | `rag_search` | RAG 本地文档检索（查询扩展 + 代码分块） |
| | `web_search` | DuckDuckGo 搜索 |
| **自我演化** | `learn_from_ai_tool` | 学习 AI 工具策略 |
| | `gap_analysis` | 能力差距分析 + 改进路线图 |

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
```

## 📦 依赖

| 包 | 用途 | 是否必须 |
|----|------|----------|
| `ollama` | 本地大模型调用 | ✅ 必须 |
| `pyyaml` | 配置文件解析 | ✅ 必须 |
| `rich` | 终端 UI 渲染 | ✅ 必须 |
| `flask` | Web UI 后端 | ⚡ 推荐（Web 界面需要） |
| `chromadb` | 向量数据库（长期记忆 + RAG） | ⚡ 推荐（无则降级为 JSON） |
| `duckduckgo-search` | Web 搜索 | ⚡ 可选 |

## 🗺 演化路线图

| 版本 | 里程碑 | 状态 |
|------|--------|------|
| v0.1 | 基础能力：文件读写 + 命令执行 + 代码搜索 | ✅ 已完成 |
| v0.2 | 工作记忆：会话内上下文管理 | ✅ 已完成 |
| v0.3 | 长期记忆：跨会话经验积累 | ✅ 已完成 |
| v0.4 | **可靠性 + 智能化 + 规模化**：edit_file 多匹配处理、自动重试、TF-IDF 记忆检索（中文 bigram）、跨层排序、RAG 查询扩展、代码分块、Jaccard 去重、元推理框架、六维评分、循环检测、Git/测试/质量/重构/项目分析工具 | ✅ 已完成 |
| v0.5 | 外部记忆：RAG + 搜索引擎 | ✅ 已完成 |
| v0.6 | 自我反思 + 策略进化 + 知识蒸馏 | ✅ 已完成 |
| v0.7 | AI 工具对比学习 | 🔜 进行中 |
| v0.8 | 基准评测（HumanEval / SWE-bench） | 📋 计划中 |
| v0.9 | 多项目协作 + 团队知识共享 | 📋 计划中 |
| v1.0 | 完整自进化循环 | 📋 计划中 |

## 📄 License

[MIT License](LICENSE) · Copyright (c) 2026 Jiangsheng Yu

## 👤 作者

**Jiangsheng Yu** — 设计、开发与维护
