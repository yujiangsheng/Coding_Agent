# 使用示例

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
