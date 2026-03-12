# 贡献指南

感谢你对 Turing 的关注！欢迎参与贡献。

## 开发环境

```bash
# 克隆仓库
git clone https://github.com/yujiangsheng/Coding_Agent.git
cd Coding_Agent

# 安装开发依赖
pip install -e ".[full,dev]"

# 运行测试
pytest
```

## 项目结构

```
.
├── main.py                    # CLI 入口（REPL + 单次执行 + 斜杠命令）
├── config.yaml                # 默认配置（模型/记忆/演化/安全）
├── pyproject.toml             # 项目元数据 & 构建配置
├── requirements.txt           # 运行时依赖清单
├── coding_agent_prompt.md     # Agent Prompt 设计文档
├── turing/
│   ├── __init__.py            # 包定义（版本号 v3.6.0）
│   ├── agent.py               # Agent 主循环（10 阶段流水线 + 元认知 + Token-aware）
│   ├── config.py              # YAML 配置管理（单例 + 深度合并）
│   ├── prompt.py              # System Prompt（28 能力声明 + 21 专题段落 + CoT + ETF）
│   ├── tools/                 # 工具集（82 工具，19 个模块）
│   │   ├── __init__.py        # 工具系统概述
│   │   ├── registry.py        # @tool 装饰器 + Ollama Schema + 安全调度
│   │   ├── file_tools.py      # 文件操作 (9): read/write/edit/generate/multi_edit/move/copy/delete/find
│   │   ├── command_tools.py   # 命令执行 (5): 持久化 Shell + 后台进程管理 + 自动修复
│   │   ├── search_tools.py    # 代码搜索 (6): search_code / list_directory / repo_map / smart_context / context_budget / context_compress
│   │   ├── memory_tools.py    # 记忆管理 (3): read / write / reflect
│   │   ├── external_tools.py  # 外部搜索 (3): rag_search / web_search / fetch_url
│   │   ├── evolution_tools.py # 自我演化 (12): 策略进化 + 蒸馏 + 失败恢复 + 自训练 + 竞争力分析 + 假设验证
│   │   ├── git_tools.py       # Git 操作 (8): status/diff/log/blame/add/commit/branch/stash
│   │   ├── project_tools.py   # 项目分析 (2): detect_project / analyze_dependencies
│   │   ├── quality_tools.py   # 代码质量 (3): lint_code / format_code / type_check
│   │   ├── refactor_tools.py  # 批量重构 (3): batch_edit / rename_symbol / impact_analysis
│   │   ├── ast_tools.py       # AST 分析 (4): code_structure / call_graph / complexity_report / dependency_graph
│   │   ├── test_tools.py      # 测试 (2): run_tests(覆盖率+失败详情) / generate_tests
│   │   ├── benchmark_tools.py # 基准评测 (3): run_benchmark / eval_code / benchmark_trend
│   │   ├── mcp_tools.py       # MCP 协议 (3): mcp_list_servers / mcp_list_tools / mcp_call_tool
│   │   ├── metacognition_tools.py # 元认知 (2): metacognitive_reflect / checkpoint
│   │   ├── agent_tools.py     # 任务规划 (1): task_plan
│   │   └── github_tools.py    # GitHub (5): pr_summary / issue_analyze / security_scan / code_review / changelog
│   ├── memory/                # 四层记忆系统
│   │   ├── __init__.py        # 记忆架构概述
│   │   ├── working.py         # L1 工作记忆（TF-IDF + 中文 bigram + 时间衰减）
│   │   ├── long_term.py       # L2 长期记忆（ChromaDB / JSON 降级）
│   │   ├── persistent.py      # L3 持久记忆（YAML/JSON + Jaccard 去重）
│   │   └── manager.py         # 统一管理器（跨层排序 + 去重 + 上下文压缩）
│   ├── rag/
│   │   ├── __init__.py        # RAG 引擎概述
│   │   └── engine.py          # RAG 检索引擎（查询扩展 + 代码分块）
│   └── evolution/
│       ├── __init__.py        # 演化系统概述
│       ├── tracker.py         # 自我演化（15维评分 + 策略进化 + 失败恢复 + 自训练）
│       ├── metacognition.py   # 元认知引擎（6维认知雷达 + 偏差检测）
│       └── competitive.py     # 竞争力分析引擎（8 大竞品对标 + 差距分析）
│   ├── lsp/                   # LSP 代码补全服务
│   │   ├── __init__.py        # LSP 服务概述
│   │   └── server.py          # Language Server Protocol 实现
├── web/                       # Web UI（Flask SSE）
│   ├── server.py              # HTTP API + SSE 聊天服务（9 个 API 端点）
│   ├── templates/index.html   # VS Code 风格前端
│   └── static/                # CSS + JS 静态资源
├── vscode-extension/          # VS Code 原生扩展 (v3.6)
│   ├── src/extension.ts       # 扩展入口 + 命令注册
│   ├── src/mcpClient.ts       # MCP stdio 客户端 (JSON-RPC 2.0)
│   ├── src/chatView.ts        # 聊天面板 Webview Provider
│   └── package.json           # 扩展清单
├── tests/                     # 测试套件（21 项全通过）
├── docs/
│   ├── EXAMPLES.md            # 详细使用示例（20+ 场景）
│   └── ARCHITECTURE.md        # 系统架构设计文档
├── generated_code/            # Agent 生成的代码输出目录
└── turing_data/               # 运行时数据（记忆/演化/RAG）
```

## 核心架构

### Agent 执行流程

```
用户输入
  ↓
[0] 记忆预加载 — 从 L2(长期) + L3(持久) 检索相关经验
  ↓
[1] 策略注入 — 匹配任务类型，加载对应策略模板（6 大类型预播种）
  ↓
[2] 工具推荐 — 基于策略模板推荐最佳工具组合
  ↓
[3] 元认知初始化 — MetacognitiveEngine 6 维认知雷达启动
  ↓
[4] CoT 推理规划 — 链式推理分层分解，评估复杂度
  ↓  ├── 简单任务：快速通道直接执行
  ↓  └── 复杂任务：LLM 结构化推理 → 问题分解 → 风险评估
  ↓
[5] ReAct 循环 — LLM 推理 → 工具调用 → 观察结果（最多 20 轮）
  ↓  ├── 并行执行 — 25 个只读工具自动并发（ThreadPoolExecutor, max=4）
  ↓  ├── 持久化 Shell — env/cwd 跨调用保持 + 后台进程管理
  ↓  ├── 循环检测 — 连续 3 次相同调用自动中断
  ↓  ├── ETF 验证 — 编辑后自动注入测试/验证提示
  ↓  ├── 语义错误分析 — 连续失败时分析错误模式，智能修正参数
  ↓  ├── 动态温度 — planning(0.6) / execution(0.3) / debugging(0.45)
  ↓  └── Token-aware 上下文管理 — 优先级打分 + 智能压缩
  ↓
[6] 错误恢复 — 失败恢复引擎（8 模式 × 3 级策略）
  ↓
[7] 上下文管理 — Token-aware 优先级打分 + 智能压缩
  ↓
[8] LLM 深度反思 + 策略进化检查 + 知识蒸馏检查
  ↓
[9] 十五维能力评分更新 + 元认知报告
```

### 记忆检索算法

- **TF-IDF 评分**：`score = tf × idf = count(word) × log(1 + N / (1 + df))`
- **时间衰减**：`score *= 1.0 / (1.0 + age_hours × 0.01)`
- **跨层权重**：persistent ×1.2 > long_term ×1.0 > working ×0.8
- **Jaccard 去重**：`similarity = |A ∩ B| / |A ∪ B|`，阈值 0.85

## 添加新工具

使用 `@tool` 装饰器即可自动注册：

```python
# turing/tools/my_tools.py
from turing.tools.registry import tool

@tool(
    name="my_tool",
    description="工具描述",
    parameters={
        "type": "object",
        "properties": {
            "arg1": {"type": "string", "description": "参数说明"},
        },
        "required": ["arg1"],
    },
)
def my_tool(arg1: str) -> dict:
    # 返回值必须是 dict，包含结果或错误
    return {"result": "..."}
```

然后在 `turing/agent.py` 中添加一行导入：

```python
import turing.tools.my_tools  # noqa: F401
```

**工具开发要点：**
- 返回值必须是 `dict` 类型
- 成功时返回有意义的结果字段
- 失败时返回 `{"error": "错误描述"}`
- 耗时操作要设置合理超时
- 涉及文件/命令操作时遵守安全配置

## 代码规范

- 兼容 Python 3.9+（在需要 `X | Y` 语法的文件中加 `from __future__ import annotations`）
- 使用 `ruff` 检查代码风格：`ruff check .`
- 所有 docstring 使用中文
- 变量和函数名使用英文 snake_case
- 类名使用英文 PascalCase

## VS Code 扩展开发

```bash
cd vscode-extension
npm install
npm run compile
```

- 按 F5 启动扩展调试宿主（Extension Development Host）
- MCP 通信逻辑在 `src/mcpClient.ts`，通过 stdio 启动 `python -m turing.mcp.server`
- 聊天面板 Webview 在 `src/chatView.ts`，使用 HTML/CSS/JS 渲染
- 如需添加新命令，在 `package.json` 的 `contributes.commands` 中注册，然后在 `src/extension.ts` 中实现

## License

贡献的代码将遵循 [MIT License](LICENSE)。
