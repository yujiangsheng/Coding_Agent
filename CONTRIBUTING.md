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
├── main.py                    # CLI 入口（REPL + 单次执行）
├── config.yaml                # 默认配置
├── pyproject.toml             # 项目元数据 & 构建配置
├── requirements.txt           # 依赖清单
├── coding_agent_prompt.md     # Agent Prompt 设计文档
├── turing/
│   ├── __init__.py            # 包定义（版本号 v0.4.0）
│   ├── agent.py               # Agent 主循环（ReAct loop + 元推理）
│   ├── config.py              # YAML 配置管理（单例 + 深度合并）
│   ├── prompt.py              # System Prompt（元推理框架 + 8 步工作流）
│   ├── tools/                 # 工具集（26+ 工具，12 个模块）
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
│   │   ├── refactor_tools.py  # batch_edit / rename_symbol
│   │   └── test_tools.py      # run_tests / generate_tests
│   ├── memory/                # 四层记忆系统
│   │   ├── __init__.py        # 记忆架构概述
│   │   ├── working.py         # L1 工作记忆（TF-IDF + 中文 bigram + 时间衰减）
│   │   ├── long_term.py       # L2 长期记忆（ChromaDB / JSON 降级）
│   │   ├── persistent.py      # L3 持久记忆（YAML/JSON + Jaccard 去重）
│   │   └── manager.py         # 统一管理器（跨层排序 + 去重）
│   ├── rag/
│   │   ├── __init__.py        # RAG 引擎概述
│   │   └── engine.py          # RAG 检索引擎（查询扩展 + 代码分块）
│   └── evolution/
│       ├── __init__.py        # 演化系统概述
│       └── tracker.py         # 自我演化追踪器（反思/策略/蒸馏/学习）
├── web/                       # Web UI（Flask SSE）
│   ├── server.py              # HTTP API + SSE 聊天服务
│   ├── templates/
│   │   └── index.html         # VS Code 风格前端
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── docs/
│   └── EXAMPLES.md            # 详细使用示例
└── tests/                     # 测试（待完善）
```

## 核心架构

### Agent 执行流程

```
用户输入
  ↓
[1] 记忆预加载 — 从 L2(长期) + L3(持久) 检索相关经验
  ↓
[2] 策略注入 — 匹配任务类型，加载对应策略模板
  ↓
[3] 任务规划 — 评估复杂度，制定执行计划
  ↓
[4] ReAct 循环 — LLM 推理 → 工具调用 → 观察结果（最多 20 轮）
  ↓  ├── 循环检测（防止无限循环）
  ↓  ├── 上下文溢出管理（自动压缩）
  ↓  └── 工具重试（失败自动重试一次）
  ↓
[5] 输出结果
  ↓
[6] LLM 深度反思 — 分析过程质量，提取经验
  ↓
[7] 策略进化检查 — 同类 ≥5 条经验时自动归纳策略
  ↓
[8] 知识蒸馏检查 — 每 50 次任务触发一次
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
