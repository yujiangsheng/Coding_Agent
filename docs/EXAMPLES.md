# 使用示例

> Turing v3.5.0 — 80 工具 · 19 模块 · 15 维评分 · 竞争力分析 · LSP 服务

## 目录

1. [基本对话 — 写代码](#1-基本对话--写代码)
2. [修复 Bug](#2-修复-bug)
3. [索引项目并利用 RAG 回答问题](#3-索引项目并利用-rag-回答问题)
4. [记忆系统演示](#4-记忆系统演示)
5. [向 AI 工具学习](#5-向-ai-工具学习)
6. [单次执行模式](#6-单次执行模式)
7. [自定义配置](#7-自定义配置)
8. [Git 操作](#8-git-操作)
9. [测试与代码质量](#9-测试与代码质量)
10. [批量重构](#10-批量重构)
11. [项目分析](#11-项目分析)
12. [Web UI 使用](#12-web-ui-使用)
13. [AST 深度代码分析](#13-ast-深度代码分析)
14. [跨文件影响分析](#14-跨文件影响分析)
15. [策略预播种与能力评分](#15-策略预播种与能力评分)
16. [持久化 Shell 与后台进程 (v1.0)](#16-持久化-shell-与后台进程-v10)
17. [文件管理 (v1.0)](#17-文件管理-v10)
18. [原子化多文件编辑 (v1.0)](#18-原子化多文件编辑-v10)
19. [上下文压缩与撤销 (v1.0)](#19-上下文压缩与撤销-v10)
20. [Diff 预览与 Repo Map (v1.0)](#20-diff-预览与-repo-map-v10)
21. [依赖图分析 (v3.5)](#21-依赖图分析-v35)
22. [自动修复 Lint 错误 (v3.5)](#22-自动修复-lint-错误-v35)
23. [假设验证调试 (v3.5)](#23-假设验证调试-v35)
24. [上下文压缩与预算管理 (v3.5)](#24-上下文压缩与预算管理-v35)
25. [竞争力基准评测 (v3.4)](#25-竞争力基准评测-v34)
26. [任务规划与 PR 摘要 (v3.4)](#26-任务规划与-pr-摘要-v34)
27. [安全扫描 (v3.4)](#27-安全扫描-v34)
28. [Checkpoint 工作流 (v3.3)](#28-checkpoint-工作流-v33)

---

## 1. 基本对话 — 写代码

```
You > 用 Python 写一个二分查找函数

💭 检索到 0 条相关记忆
🔧 调用工具: write_file {"path": "binary_search.py", "content": "..."}
   ✓ {"status": "ok", ...}
🔧 调用工具: run_command {"command": "python binary_search.py"}
   ✓ {"exit_code": 0, "output": "Found at index 3"}

┌─ Turing ─────────────────────────────────────┐
│ 已创建 binary_search.py，包含递归和迭代两种  │
│ 实现，并通过测试验证。                        │
└──────────────────────────────────────────────┘
```

## 2. 修复 Bug

```
You > main.py 第 42 行报 IndexError，帮我修复

💭 检索到 1 条相关记忆: [long_term] 之前遇到过类似的列表越界问题
🔧 调用工具: read_file {"path": "main.py", "start_line": 35, "end_line": 50}
   ✓ {"content": "...", "total_lines": 120}
🔧 调用工具: edit_file {"path": "main.py", "old_str": "items[idx]", "new_str": "items[idx] if idx < len(items) else None"}
   ✓ {"status": "ok"}
🔧 调用工具: run_command {"command": "python -m pytest test_main.py"}
   ✓ {"exit_code": 0, "output": "5 passed"}

┌─ Turing ─────────────────────────────────────┐
│ 已修复：添加了边界检查，所有测试通过。        │
└──────────────────────────────────────────────┘

📝 经验记录: success (使用了 3 次工具调用)
```

## 3. 索引项目并利用 RAG 回答问题

```
You > /index ./my_project

正在索引 ./my_project ...
索引完成: {'status': 'ok', 'files_indexed': 47}

You > my_project 的认证是怎么实现的？

💭 检索到 3 条相关记忆
🔧 调用工具: rag_search {"query": "authentication implementation", "source": "codebase"}
   ✓ {"results": [...], "count": 5}
🔧 调用工具: read_file {"path": "my_project/auth/jwt_handler.py"}
   ✓ {"content": "..."}

┌─ Turing ─────────────────────────────────────┐
│ 认证使用 JWT 方案：                           │
│ 1. auth/jwt_handler.py 负责 token 签发和验证  │
│ 2. middleware/auth.py 在每个请求前校验 token   │
│ 3. 密钥存储在环境变量 JWT_SECRET 中           │
└──────────────────────────────────────────────┘
```

## 4. 记忆系统演示

```
You > /memory 快速排序

[long_term] (task_reflection, success): {"summary": "实现快速排序", ...}
[persistent] (strategy): 排序算法选择策略...

You > /strategies

  📋 bug_fix (成功率: 85%)
  📋 feature (成功率: 92%)

You > /status

┌─ Turing 状态 ────────────┬──────────┐
│ 指标                     │ 值       │
├──────────────────────────┼──────────┤
│ 工作记忆条目             │ 5        │
│ 长期记忆条目             │ 23       │
│ 持久策略数               │ 2        │
│ 累计任务数               │ 42       │
│ 成功率                   │ 38/42    │
└──────────────────────────┴──────────┘
```

## 5. 向 AI 工具学习

```
You > 分析 Claude Opus 在 bug 修复方面的策略

🔧 调用工具: learn_from_ai_tool {"tool_name": "claude_opus", "task_type": "bug_fix"}
   ✓ {"tool": "claude_opus", "strengths": ["深度推理链", ...], ...}

┌─ Turing ─────────────────────────────────────┐
│ 已学习 Claude Opus 在 bug_fix 任务的策略：    │
│ • 对复杂问题先进行多步推理分解                │
│ • 修改代码前先完整阅读相关上下文              │
│ • 主动识别安全漏洞并修复                      │
│ 这些策略已存入持久记忆。                      │
└──────────────────────────────────────────────┘
```

## 6. 单次执行模式

```bash
# 直接生成代码，不进入交互
python main.py --one-shot "写一个 Flask REST API，实现用户 CRUD"

# 指定不同模型
python main.py -m qwen3-coder:14b --one-shot "解释 Python 的 GIL"
```

## 7. 自定义配置

```yaml
# config.yaml
model:
  name: "qwen3-coder:14b"    # 换成更小的模型
  temperature: 0.1            # 更保守的生成

memory:
  data_dir: "/data/turing"    # 自定义数据目录

evolution:
  strategy_threshold: 3       # 更快触发策略进化
  distill_interval: 20        # 更频繁的知识蒸馏
```

## 8. Git 操作

```
You > 查看这个项目最近的修改

🔧 调用工具: git_status {"path": "."}
   ✓ {"branch": "main", "modified": ["src/api.py", "src/utils.py"], ...}
🔧 调用工具: git_diff {"path": ".", "file": "src/api.py"}
   ✓ {"diff": "- old_code\n+ new_code", ...}
🔧 调用工具: git_log {"path": ".", "count": 5, "oneline": true}
   ✓ {"commits": [...]}

┌─ Turing ─────────────────────────────────────┐
│ 最近修改了 2 个文件：                         │
│ • src/api.py — 新增了用户认证中间件           │
│ • src/utils.py — 修复了日期格式化 bug         │
│ 最近 5 次提交都集中在认证模块的开发。         │
└──────────────────────────────────────────────┘

You > 看看 api.py 第 30-50 行是谁写的

🔧 调用工具: git_blame {"file": "src/api.py", "start_line": 30, "end_line": 50}
   ✓ {"lines": [{"line": 30, "author": "alice", "commit": "a1b2c3d", ...}, ...]}

┌─ Turing ─────────────────────────────────────┐
│ 第 30-45 行由 alice 在 2 天前提交（a1b2c3d）  │
│ 第 46-50 行由 bob 在上周提交（e5f6g7h）       │
└──────────────────────────────────────────────┘
```

## 9. 测试与代码质量

```
You > 运行这个项目的测试并检查代码质量

🔧 调用工具: detect_project {"path": "."}
   ✓ {"type": "python", "framework": "flask", "test_framework": "pytest", ...}
🔧 调用工具: run_tests {"path": ".", "verbose": true}
   ✓ {"exit_code": 0, "output": "15 passed, 2 failed", "success": false}
🔧 调用工具: lint_code {"path": "."}
   ✓ {"tool": "ruff", "issues": 3, "output": "..."}
🔧 调用工具: type_check {"path": "."}
   ✓ {"tool": "mypy", "errors": 1, "output": "..."}

┌─ Turing ─────────────────────────────────────┐
│ 项目分析结果：                                 │
│ • 测试：15 通过 / 2 失败（test_auth.py:42）    │
│ • Lint：3 个小问题（未使用的导入等）            │
│ • 类型：1 个类型错误（api.py:55）               │
│ 我来修复失败的测试...                          │
└──────────────────────────────────────────────┘

You > 帮我自动格式化代码

🔧 调用工具: format_code {"path": ".", "check_only": false}
   ✓ {"tool": "ruff format", "files_changed": 5, "output": "..."}

┌─ Turing ─────────────────────────────────────┐
│ 已格式化 5 个文件，代码风格统一。             │
└──────────────────────────────────────────────┘

You > 帮我生成 utils.py 的测试

🔧 调用工具: generate_tests {"source_file": "src/utils.py", "output_file": "tests/test_utils.py"}
   ✓ {"status": "ok", "path": "tests/test_utils.py", "test_count": 8}
🔧 调用工具: run_tests {"test_file": "tests/test_utils.py"}
   ✓ {"exit_code": 0, "output": "8 passed"}

┌─ Turing ─────────────────────────────────────┐
│ 已生成 tests/test_utils.py，包含 8 个测试，   │
│ 全部通过。覆盖了所有公开函数。                │
└──────────────────────────────────────────────┘
```

## 10. 批量重构

```
You > 把项目中所有的 print() 替换成 logger.info()

🔧 调用工具: batch_edit {"pattern": "print(", "replacement": "logger.info(", "file_pattern": "*.py", "dry_run": true}
   ✓ {"matches": 23, "files": ["src/api.py", "src/utils.py", ...], "preview": [...]}

┌─ Turing ─────────────────────────────────────┐
│ 扫描到 23 处 print() 调用，分布在 8 个文件。  │
│ 先看看 dry_run 预览，确认后再执行？           │
└──────────────────────────────────────────────┘

You > 确认执行

🔧 调用工具: batch_edit {"pattern": "print(", "replacement": "logger.info(", "file_pattern": "*.py", "dry_run": false}
   ✓ {"replaced": 23, "files_modified": 8}

┌─ Turing ─────────────────────────────────────┐
│ 已完成批量替换：23 处修改，8 个文件。          │
└──────────────────────────────────────────────┘

You > 把所有的 getUserName 重命名为 get_user_name

🔧 调用工具: rename_symbol {"old_name": "getUserName", "new_name": "get_user_name", "path": ".", "dry_run": true}
   ✓ {"matches": 12, "files": ["src/user.py", "src/api.py", ...]}
🔧 调用工具: rename_symbol {"old_name": "getUserName", "new_name": "get_user_name", "path": "."}
   ✓ {"renamed": 12, "files_modified": 4}

┌─ Turing ─────────────────────────────────────┐
│ 已将 getUserName 重命名为 get_user_name，      │
│ 修改了 4 个文件中的 12 处引用。                │
└──────────────────────────────────────────────┘
```

## 11. 项目分析

```
You > 分析这个项目的结构和依赖

🔧 调用工具: detect_project {"path": "."}
   ✓ {"type": "python", "framework": "flask", "build": "pip+setuptools", ...}
🔧 调用工具: analyze_dependencies {"path": "."}
   ✓ {"file": "requirements.txt", "dependencies": [...], "count": 15}

┌─ Turing ─────────────────────────────────────┐
│ 项目概况：                                     │
│ • 类型：Python Flask Web 应用                  │
│ • 构建：pip + setuptools                       │
│ • 依赖：15 个（Flask, SQLAlchemy, ...）         │
│ • 测试框架：pytest                             │
│ • Linter：ruff                                 │
└──────────────────────────────────────────────┘
```

## 12. Web UI 使用

Turing 提供 VS Code 风格的 Web 界面：

```bash
# 启动 Web 服务
python web/server.py

# 自定义端口
python web/server.py -p 8080

# 允许局域网访问
python web/server.py --host 0.0.0.0
```

访问 `http://127.0.0.1:5000` 即可使用：

- **聊天界面** — 支持流式输出，实时显示思考过程和工具调用
- **文件浏览器** — 浏览项目目录，查看文件内容
- **记忆面板** — 搜索记忆、查看策略、浏览进化日志
- **状态监控** — 实时查看记忆统计和演化进度

### Web API 调用示例

```bash
# SSE 流式聊天
curl -X POST http://127.0.0.1:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "写一个 hello world"}'

# 查看状态
curl http://127.0.0.1:5000/api/status

# 搜索记忆
curl "http://127.0.0.1:5000/api/memory/search?q=排序算法"

# 索引项目
curl -X POST http://127.0.0.1:5000/api/index-project \
  -H "Content-Type: application/json" \
  -d '{"path": "./my_project"}'
```

---

## 13. AST 深度代码分析

Turing 内置 AST（抽象语法树）分析工具，无需逐行阅读即可快速了解代码结构。

### 代码结构提取

```
You > 分析 turing/agent.py 的代码结构

🔧 调用工具: code_structure {"path": "turing/agent.py"}
   ✓ {"classes": ["TuringAgent"], "functions": [...], "imports": [...]}

┌─ Turing ─────────────────────────────────────┐
│ turing/agent.py 结构分析：                     │
│ • 1 个类: TuringAgent (750+ 行)               │
│ • 19 个方法: chat, start_session, ...          │
│ • 12 个导入模块                                │
│ • 核心方法: chat() 是 Generator 事件流模式     │
└──────────────────────────────────────────────┘
```

### 函数调用关系图

```
You > 分析 turing/ 目录的函数调用关系

🔧 调用工具: call_graph {"path": "turing/", "depth": 2}
   ✓ {"nodes": [...], "edges": [...], "entry_points": [...]}

┌─ Turing ─────────────────────────────────────┐
│ 调用关系图：                                   │
│ chat() → _assess_and_plan()                   │
│       → _load_relevant_strategy()             │
│       → _classify_tool_calls()                │
│       → _execute_parallel() / _execute_with_retry() │
│       → _post_task_reflect()                  │
│            → _llm_reflect()                   │
│            → evolution.add_reflection()       │
│            → evolution.check_strategy_evolution() │
└──────────────────────────────────────────────┘
```

### 圈复杂度报告

```
You > 检查项目中哪些函数复杂度过高

🔧 调用工具: complexity_report {"path": "turing/", "threshold": 10}
   ✓ {"high_complexity": [...], "summary": {...}}

┌─ Turing ─────────────────────────────────────┐
│ 高复杂度函数（阈值 > 10）：                    │
│ • agent.py: chat() — 复杂度 18（主循环）       │
│ • agent.py: _check_context_overflow() — 14    │
│ • tracker.py: _score_dimensions() — 12        │
│ 建议考虑拆分 chat() 中的工具执行分支。         │
└──────────────────────────────────────────────┘
```

## 14. 跨文件影响分析

修改代码前，Turing 可以自动分析跨文件依赖影响。

```
You > 我想重命名 MemoryManager 类，先帮我分析影响范围

🔧 调用工具: impact_analysis {"symbol": "MemoryManager", "path": "."}
   ✓ {"references": [...], "files_affected": 3, "risk_level": "medium"}

┌─ Turing ─────────────────────────────────────┐
│ MemoryManager 影响分析：                       │
│ • 定义位置: turing/memory/manager.py:15        │
│ • 引用文件 (3):                                │
│   - turing/agent.py:28 (import)               │
│   - turing/memory/__init__.py:8 (re-export)   │
│   - web/server.py:44 (间接通过 agent)          │
│ • 风险等级: 中等                               │
│ • 建议: 安全重命名后运行 run_tests 验证        │
└──────────────────────────────────────────────┘

You > 确认重命名为 UnifiedMemoryManager

🔧 调用工具: rename_symbol {"old_name": "MemoryManager", "new_name": "UnifiedMemoryManager", "path": "."}
   ✓ {"renamed": 5, "files_modified": 3}
🔧 调用工具: run_tests {"path": "."}
   ✓ {"exit_code": 0, "output": "all tests passed"}

┌─ Turing ─────────────────────────────────────┐
│ 已完成安全重命名，3 个文件 5 处引用已更新，    │
│ 所有测试通过。                                 │
└──────────────────────────────────────────────┘
```

## 15. 策略预播种与能力评分

Turing 具备策略预播种和多维能力评分机制，即使是首次使用也能获得专家级指导。

### 查看已播种的策略

```
You > /strategies

  📋 bug_fix (基于 Claude/Codex 最佳实践)
     推荐工具: read_file → search_code → edit_file → run_tests
     核心经验: 先完整理解上下文再修改、最小改动原则

  📋 feature (基于 10+ 条经验进化)
     推荐工具: detect_project → write_file → run_tests → lint_code
     历史成功率: 92%

  📋 refactor (基于 Codex/Gemini 策略)
     推荐工具: code_structure → impact_analysis → batch_edit → run_tests

  📋 debug (基于 Claude Opus 深度推理)
     推荐工具: read_file → run_command → search_code → edit_file

  📋 explain (基于 Gemini 知识检索)
     推荐工具: code_structure → call_graph → rag_search

  📋 test (基于 Copilot 测试生成)
     推荐工具: detect_project → generate_tests → run_tests → lint_code
```

### 能力差距分析

```
You > 分析当前能力差距

🔧 调用工具: gap_analysis {}
   ✓ {"dimensions": [...], "total_score": 8.3, "gaps": [...]}

┌─ Turing 能力评分 (8.3/10) ────────────────────┐
│ 维度               │ 得分  │ 说明             │
├────────────────────┼───────┼──────────────────┤
│ 代码质量           │ 8.5   │ ██████████░░     │
│ 调试能力           │ 8.0   │ █████████░░░     │
│ 架构设计           │ 7.5   │ ████████░░░░     │
│ 执行效率           │ 8.5   │ ██████████░░     │
│ 安全意识           │ 9.0   │ ███████████░     │
│ 沟通清晰度         │ 8.0   │ █████████░░░     │
│ 工具多样性         │ 9.0   │ ███████████░     │
│ 推理深度           │ 8.0   │ █████████░░░     │
│ 记忆利用率         │ 8.0   │ █████████░░░     │
│ 学习速率           │ 8.5   │ ██████████░░     │
│ 验证覆盖率         │ 8.5   │ ██████████░░     │
│ 错误恢复力         │ 8.0   │ █████████░░░     │
│ 自主性             │ 8.5   │ ██████████░░     │
│ 上下文管理         │ 9.0   │ ███████████░     │
│ 持续改进           │ 8.0   │ █████████░░░     │
└────────────────────┴───────┴──────────────────┘
```

## 16. 持久化 Shell 与后台进程 (v1.0)

v1.0.0 引入持久化 Shell 会话，环境变量和工作目录跨调用保持。

### 环境变量保持

```
You > 帮我设置环境变量然后验证

🔧 调用工具: run_command {"command": "export API_KEY=sk-123456 && export DEBUG=true"}
   ✓ {"exit_code": 0}
🔧 调用工具: run_command {"command": "echo $API_KEY && echo $DEBUG"}
   ✓ {"exit_code": 0, "output": "sk-123456\ntrue"}

┌─ Turing ─────────────────────────────────────┐
│ 环境变量已设置并保持：                         │
│ • API_KEY=sk-123456                           │
│ • DEBUG=true                                   │
│ 在后续命令中可直接使用这些变量。               │
└──────────────────────────────────────────────┘
```

### 工作目录保持

```
You > 进入项目目录

🔧 调用工具: run_command {"command": "cd /Users/me/project && pwd"}
   ✓ {"exit_code": 0, "output": "/Users/me/project"}
🔧 调用工具: run_command {"command": "ls src/"}
   ✓ {"exit_code": 0, "output": "main.py  utils.py  config.py"}

┌─ Turing ─────────────────────────────────────┐
│ 已切换到 /Users/me/project，后续命令都在      │
│ 该目录下执行。                                 │
└──────────────────────────────────────────────┘
```

### 后台进程管理

```
You > 启动开发服务器

🔧 调用工具: run_background {"command": "python -m flask run --port 5001", "label": "dev-server"}
   ✓ {"pid": 12345, "label": "dev-server", "status": "running"}

┌─ Turing ─────────────────────────────────────┐
│ 开发服务器已在后台启动 (PID: 12345)            │
│ 访问 http://127.0.0.1:5001                    │
└──────────────────────────────────────────────┘

You > 查看服务器日志

🔧 调用工具: check_background {"label": "dev-server"}
   ✓ {"pid": 12345, "status": "running", "output": "* Running on http://127.0.0.1:5001"}

You > 停止服务器

🔧 调用工具: stop_background {"label": "dev-server"}
   ✓ {"stopped": true, "pid": 12345}
```

## 17. 文件管理 (v1.0)

v1.0.0 新增完整的文件管理工具。

### 文件搜索

```
You > 找到所有包含 "TODO" 的 Python 文件

🔧 调用工具: find_files {"pattern": "*.py", "content_pattern": "TODO", "path": "."}
   ✓ {"matches": [{"path": "src/api.py", "lines": [42, 67]}, ...], "count": 5}

┌─ Turing ─────────────────────────────────────┐
│ 找到 5 个文件包含 TODO：                       │
│ • src/api.py (行 42, 67)                       │
│ • src/utils.py (行 15)                         │
│ • tests/test_api.py (行 8)                     │
│ • ...                                          │
└──────────────────────────────────────────────┘
```

### 文件操作

```
You > 把 src/old_module.py 移到 src/legacy/ 目录下

🔧 调用工具: move_file {"source": "src/old_module.py", "destination": "src/legacy/old_module.py"}
   ✓ {"status": "ok", "source": "src/old_module.py", "destination": "src/legacy/old_module.py"}

You > 复制 config.yaml 做一个备份

🔧 调用工具: copy_file {"source": "config.yaml", "destination": "config.yaml.bak"}
   ✓ {"status": "ok"}

You > 删除临时文件

🔧 调用工具: delete_file {"path": "tmp/debug.log"}
   ✓ {"status": "ok", "deleted": "tmp/debug.log"}
```

## 18. 原子化多文件编辑 (v1.0)

`multi_edit` 支持事务性编辑多个文件，任意一步失败自动回滚。

```
You > 把所有文件中的 v0.9.0 更新为 v1.0.0

🔧 调用工具: multi_edit {"edits": [
    {"path": "pyproject.toml", "old_str": "version = \"0.9.0\"", "new_str": "version = \"1.0.0\""},
    {"path": "turing/__init__.py", "old_str": "__version__ = \"0.9.0\"", "new_str": "__version__ = \"1.0.0\""},
    {"path": "README.md", "old_str": "v0.9.0", "new_str": "v1.0.0"}
  ]}
   ✓ {"status": "ok", "edits_applied": 3, "files_modified": 3}

┌─ Turing ─────────────────────────────────────┐
│ 3 个文件已原子化更新为 v1.0.0。                │
│ 如果任一编辑失败，所有变更都会自动回滚。       │
└──────────────────────────────────────────────┘
```

## 19. 上下文压缩与撤销 (v1.0)

### /compact — 压缩上下文

```
You > /compact

┌─ Turing ─────────────────────────────────────┐
│ 上下文已压缩：                                 │
│ • 压缩前: 28,672 tokens                       │
│ • 压缩后: 12,480 tokens                       │
│ • 保留: 系统提示 + 最近 4 轮对话 + 关键结果    │
│ • 移除: 早期历史 + 大输出 + 冗余消息           │
└──────────────────────────────────────────────┘
```

### /undo — 撤销文件修改

```
You > /undo

🔧 调用工具: git_diff {"staged": false}
   ✓ 显示最近修改的 diff

┌─ Turing ─────────────────────────────────────┐
│ 已撤销上一次文件修改：                         │
│ • 恢复: src/api.py (3 行变更已回滚)            │
└──────────────────────────────────────────────┘
```

### /diff — 查看当前变更

```
You > /diff

┌─ Diff 预览 ──────────────────────────────────┐
│ src/api.py:                                    │
│   - old_function()                             │
│   + new_function()                             │
│ src/utils.py:                                  │
│   + import logging                             │
│   + logger = logging.getLogger(__name__)        │
└──────────────────────────────────────────────┘
```

## 20. Diff 预览与 Repo Map (v1.0)

### Repo Map — 代码仓库结构

```
You > 生成项目的 Repo Map

🔧 调用工具: repo_map {"path": "."}
   ✓ {"map": "..."}

┌─ Repo Map ───────────────────────────────────┐
│ turing/                                        │
│ ├── agent.py                                   │
│ │   └── class TuringAgent                      │
│ │       ├── chat() → Generator                 │
│ │       ├── start_session()                    │
│ │       └── ... (19 methods)                   │
│ ├── config.py                                  │
│ │   └── class Config                           │
│ │       ├── get(key_path)                      │
│ │       └── _deep_merge()                      │
│ ├── memory/                                    │
│ │   ├── manager.py                             │
│ │   │   └── class MemoryManager                │
│ │   ├── working.py                             │
│ │   │   └── class WorkingMemory                │
│ │   └── ...                                    │
│ └── tools/ (19 modules, 80 tools)              │
└──────────────────────────────────────────────┘
```

### 测试覆盖率 (v1.0)

```
You > 运行测试并生成覆盖率报告

🔧 调用工具: run_tests {"path": ".", "coverage": true}
   ✓ {"exit_code": 0, "output": "21 passed",
      "coverage": {"total": 78, "files": {"agent.py": 82, "config.py": 95, ...}},
      "failures": []}

┌─ Turing ─────────────────────────────────────┐
│ 测试结果：21 通过 / 0 失败                     │
│ 整体覆盖率：78%                                │
│ • agent.py: 82%                                │
│ • config.py: 95%                               │
│ • tools/registry.py: 100%                      │
└──────────────────────────────────────────────┘
```

## 21. 依赖图分析 (v3.5)

```
You > 分析项目的模块依赖关系

🔧 调用工具: dependency_graph {"path": "turing", "format": "text"}
   ✓ {"graph": {"nodes": 19, "edges": 42, "cycles": []}, ...}

┌─ Turing ─────────────────────────────────────┐
│ 模块依赖图分析完成：                            │
│ • 19 个模块，42 条依赖关系                      │
│ • 未检测到循环依赖 ✓                            │
│ • 核心模块: agent.py (入度最高, 12 个依赖)      │
│ • 叶模块: ast_tools.py (无出度依赖)             │
└──────────────────────────────────────────────┘
```

## 22. 自动修复 Lint 错误 (v3.5)

```
You > 自动修复项目中的 lint 错误

🔧 调用工具: auto_fix {"path": ".", "fix_types": ["lint", "import"]}
   ✓ {"fixed": 8, "files_modified": 3, "details": [...]}

┌─ Turing ─────────────────────────────────────┐
│ 自动修复完成：                                  │
│ • 修复 8 个问题，涉及 3 个文件                  │
│ • F401 未使用导入: 4 处                         │
│ • E302 空行不足: 2 处                           │
│ • W291 行尾空格: 2 处                           │
└──────────────────────────────────────────────┘
```

## 23. 假设验证调试 (v3.5)

```
You > 我怀疑 config.py 的 _deep_merge 方法在处理空字典时有 bug

🔧 调用工具: verify_hypothesis {
     "hypothesis": "_deep_merge 在 base 为空 dict 时跳过 override 值",
     "evidence_commands": [
       "grep -n '_deep_merge' turing/config.py",
       "python -c \"from turing.config import Config; print(Config._deep_merge({}, {'a': 1}))\""
     ]
   }
   ✓ {"verdict": "refuted", "confidence": 0.95,
      "evidence": "空字典正确合并，返回 {'a': 1}",
      "suggestion": "检查是否是 None 值而非空字典导致的问题"}

┌─ Turing ─────────────────────────────────────┐
│ 假设验证结果：❌ 已否定（置信度 95%）             │
│ • _deep_merge({}, {'a': 1}) 正确返回 {'a': 1}  │
│ • 建议：检查传入的是否为 None 而非空 dict        │
└──────────────────────────────────────────────┘
```

## 24. 上下文压缩与预算管理 (v3.5)

```
You > 当前上下文预算还剩多少？

🔧 调用工具: context_budget {}
   ✓ {"total_tokens": 128000, "used_tokens": 45200,
      "remaining_tokens": 82800, "usage_percent": 35.3}

You > 压缩当前上下文，保留最关键的信息

🔧 调用工具: context_compress {"strategy": "relevance", "target_ratio": 0.5}
   ✓ {"before_tokens": 45200, "after_tokens": 22100,
      "removed_items": 12, "kept_items": 18}

┌─ Turing ─────────────────────────────────────┐
│ 上下文压缩完成：                                │
│ • 压缩前: 45,200 tokens (35.3%)                │
│ • 压缩后: 22,100 tokens (17.3%)                │
│ • 移除 12 项低相关性内容，保留 18 项核心上下文   │
└──────────────────────────────────────────────┘
```

## 25. 竞争力基准评测 (v3.4)

```
You > 评估 Turing 和其他 AI Agent 的差距

🔧 调用工具: competitive_benchmark {}
   ✓ {"rank": 1, "total": 8, "score": 0.864,
      "competitors": [...], "gaps": [...]}

┌─ Turing ─────────────────────────────────────┐
│ 竞争力评测结果：                                │
│ 🏆 排名: 1/8（得分 0.864）                     │
│                                                │
│ 对标分析（前 3）：                               │
│ 1. Turing     0.864  ██████████████████░░       │
│ 2. Cursor     0.850  █████████████████░░░       │
│ 3. Copilot    0.840  █████████████████░░░       │
│                                                │
│ 关键差距：                                      │
│ • real_time_completion: 0.40 vs 竞品 0.95       │
│ • 建议：集成 LSP 实时补全提升该维度              │
└──────────────────────────────────────────────┘
```

## 26. 任务规划与 PR 摘要 (v3.4)

### 任务规划

```
You > 我需要给项目添加 WebSocket 支持

🔧 调用工具: task_plan {"task": "添加 WebSocket 实时通信支持"}
   ✓ {"steps": [...], "estimated_complexity": "medium"}

┌─ Turing ─────────────────────────────────────┐
│ 任务计划（4 步）：                               │
│ 1. 安装 flask-socketio 依赖                     │
│ 2. 修改 web/server.py 添加 SocketIO 事件处理    │
│ 3. 更新 web/static/js/app.js 前端 WS 连接       │
│ 4. 添加连接/断开/消息测试用例                    │
└──────────────────────────────────────────────┘
```

### PR 摘要

```
You > 为当前分支生成 PR 摘要

🔧 调用工具: pr_summary {"base": "main"}
   ✓ {"title": "...", "summary": "...", "changes": [...]}

┌─ PR Summary ─────────────────────────────────┐
│ feat: 添加竞争力分析引擎与 LSP 服务             │
│                                                │
│ ## 变更概述                                     │
│ 新增 4 个工具，实现竞争力自评与代码补全          │
│                                                │
│ ## 文件变更 (12 files)                          │
│ + turing/evolution/competitive.py (新增)        │
│ + turing/lsp/__init__.py (新增)                 │
│ ~ turing/tools/evolution_tools.py (修改)        │
│ ~ turing/tools/search_tools.py (修改)           │
│ ...                                             │
└──────────────────────────────────────────────┘
```

## 27. 安全扫描 (v3.4)

```
You > 扫描项目中的安全隐患

🔧 调用工具: security_scan {"path": "."}
   ✓ {"issues": [...], "severity_counts": {"high": 0, "medium": 1, "low": 2}}

┌─ Turing ─────────────────────────────────────┐
│ 安全扫描结果：                                  │
│ • 高危: 0 ✓                                    │
│ • 中危: 1 — web/server.py:25 未设置 CORS 限制   │
│ • 低危: 2 — 硬编码默认端口、DEBUG 模式未关闭     │
│ 建议：添加 CORS 白名单，生产环境关闭 DEBUG       │
└──────────────────────────────────────────────┘
```

## 28. Checkpoint 工作流 (v3.3)

```
You > 保存当前工作状态

🔧 调用工具: checkpoint_save {"label": "feature-websocket-v1"}
   ✓ {"checkpoint_id": "chk_20250701_143022", "label": "feature-websocket-v1"}

You > 查看已保存的检查点

🔧 调用工具: checkpoint_list {}
   ✓ {"checkpoints": [
        {"id": "chk_20250701_143022", "label": "feature-websocket-v1", "time": "14:30:22"},
        {"id": "chk_20250701_120015", "label": "pre-refactor", "time": "12:00:15"}
      ]}

You > 恢复到之前的检查点

🔧 调用工具: checkpoint_restore {"checkpoint_id": "chk_20250701_120015"}
   ✓ {"restored": true, "label": "pre-refactor"}

┌─ Turing ─────────────────────────────────────┐
│ 已恢复到检查点: pre-refactor (12:00:15)         │
│ • 工作记忆已回滚 ✓                              │
│ • 元认知状态已恢复 ✓                            │
└──────────────────────────────────────────────┘
```

---

*文档版本: v3.5.0 · 最后更新: 2025-07*
