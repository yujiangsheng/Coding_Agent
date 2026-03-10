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
│   ├── __init__.py            # 包定义（版本号 v0.6.0）
│   ├── agent.py               # Agent 主循环（ReAct + CoT 推理 + ETF 验证 + 并行执行）
│   ├── config.py              # YAML 配置管理（单例 + 深度合并）
│   ├── prompt.py              # System Prompt（16 能力 + 7 原则 + CoT 框架 + ETF 循环）
│   ├── tools/                 # 工具集（31+ 工具，13 个模块）
│   │   ├── __init__.py        # 工具系统概述
│   │   ├── registry.py        # @tool 装饰器 + Ollama Schema + 安全调度
│   │   ├── file_tools.py      # read_file / write_file / edit_file
│   │   ├── command_tools.py   # run_command（安全过滤 + 超时控制）
│   │   ├── search_tools.py    # search_code / list_directory
│   │   ├── memory_tools.py    # memory_read / memory_write / memory_reflect
│   │   ├── external_tools.py  # rag_search / web_search
│   │   ├── evolution_tools.py # learn_from_ai_tool / gap_analysis
│   │   ├── git_tools.py       # git_status / git_diff / git_log / git_blame
│   │   ├── project_tools.py   # detect_project / analyze_dependencies
│   │   ├── quality_tools.py   # lint_code / format_code / type_check
│   │   ├── refactor_tools.py  # batch_edit / rename_symbol / impact_analysis
│   │   ├── ast_tools.py       # code_structure / call_graph / complexity_report
│   │   └── test_tools.py      # run_tests / generate_tests
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
│       └── tracker.py         # 自我演化追踪器（反思/策略/蒸馏/学习/11维评分）
├── web/                       # Web UI（Flask SSE）
│   ├── server.py              # HTTP API + SSE 聊天服务（9 个 API 端点）
│   ├── templates/
│   │   └── index.html         # VS Code 风格前端
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── docs/
│   ├── EXAMPLES.md            # 详细使用示例（15+ 场景）
│   └── ARCHITECTURE.md        # 系统架构设计文档
├── generated_code/            # Agent 生成的代码输出目录
└── turing_data/               # 运行时数据（记忆/演化/RAG）
```

## 核心架构

### Agent 执行流程

```
用户输入
  ↓
[1] 记忆预加载 — 从 L2(长期) + L3(持久) 检索相关经验
  ↓
[2] 策略注入 — 匹配任务类型，加载对应策略模板（6 大类型预播种）
  ↓
[3] CoT 推理规划 — 链式推理分层分解，评估复杂度，制定执行计划
  ↓  ├── 简单任务：快速通道直接执行
  ↓  └── 复杂任务：LLM 结构化推理 → 问题分解 → 风险评估 → 方案选择
  ↓
[4] ReAct 循环 — LLM 推理 → 工具调用 → 观察结果（最多 20 轮）
  ↓  ├── 并行执行 — 只读工具自动并发（ThreadPoolExecutor, max=4）
  ↓  ├── 循环检测 — 连续 3 次相同调用自动中断
  ↓  ├── ETF 验证 — 编辑后自动注入测试/验证提示
  ↓  ├── 语义错误分析 — 连续失败时分析错误模式，智能修正参数
  ↓  ├── 动态温度 — planning(0.6) / execution(0.3) / debugging(0.45)
  ↓  └── 上下文溢出管理 — 优先级滑动窗口 + 摘要折叠 + 工具结果压缩
  ↓
[5] 输出结果
  ↓
[6] LLM 深度反思 — 分析过程质量、工具选择、推理深度、可复用模式
  ↓
[7] 策略进化检查 — 同类 ≥5 条经验时自动归纳策略（含工具路由建议）
  ↓
[8] 知识蒸馏检查 — 每 50 次任务合并冗余、淘汰低质量
  ↓
[9] 十一维评分更新 — 综合评估代码/调试/架构/效率/安全等维度
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

## License

贡献的代码将遵循 [MIT License](LICENSE)。
