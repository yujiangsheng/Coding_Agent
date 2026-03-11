"""Turing — 自进化编程智能体 (Self-Evolving Coding Agent) v5.0

基于本地大模型（Qwen3-Coder 30B）的编程 Agent，对标 Aider / Cursor / Claude Code / Devin，具备：

- **四层记忆系统** — L1 工作记忆 / L2 长期记忆 / L3 持久记忆 / L4 外部记忆（RAG）
- **61 内置工具** — 文件管理、持久化 Shell、Git 完整工作流、代码搜索、
  测试运行、AST 分析、基准评测、MCP 协议集成等
- **自我演化** — 任务反思 → 经验积累 → 策略进化 → 知识蒸馏 → AI 工具对比学习
  → 失败恢复引擎 → 自训练模拟器 → 15 维评分系统
- **元认知系统** — 6 维认知雷达、偏差检测、置信校准、认知自适应
- **v5.0 新能力**:
  · 持久化 Shell 会话 — env/cwd 跨命令保持 + 后台进程管理（对标 Claude Code / Devin）
  · 完整文件管理 — move/copy/delete/find_files + multi_edit 原子化多文件编辑（对标 Cursor）
  · Token-aware 上下文管理 — 基于 token 估算 + 消息优先级打分 + 渐进式压缩（对标 Claude Code）
  · 测试覆盖率 & 失败详情 — pytest --cov + 自动提取断言错误和堆栈（对标 Cursor）
  · 自动项目索引 — 会话启动自动 repo_map 注入项目全貌（对标 Cursor / Windsurf）

架构::

    CLI / Web UI
        ↓
    TuringAgent (ReAct Loop + CoT + ETF + Auto Lint-Fix + Auto Commit + Auto Index)
        ├── ToolRegistry (54 tools, 13 modules)
        │     ├── 文件管理（diff 预览 + multi_edit + move/copy/delete/find）
        │     ├── 持久化 Shell（env/cwd 保持 + 后台进程 run/check/stop）
        │     ├── 搜索 + Repo Map / Git 完整工作流
        │     ├── 测试（覆盖率 + 失败详情）/ 质量（auto lint-fix）/ 重构
        │     ├── 项目 / AST 代码分析 / 记忆 / RAG·Web
        │     └── 演化（含失败恢复 + 自训练）/ 元认知
        ├── MemoryManager (4 layers + TF-IDF + 跨层排序)
        ├── RAGEngine (query expansion + code-aware chunking)
        ├── EvolutionTracker (15 维评分 + 18 子能力)
        ├── MetacognitiveEngine (6 维认知雷达 + 偏差检测)
        ├── TokenAwareContextManager (token 估算 + 优先级打分 + 渐进压缩)
        └── ParallelExecutor (ThreadPoolExecutor, 只读工具并发)

Author: Jiangsheng Yu
License: MIT
"""

__version__ = "2.1.0"
__author__ = "Jiangsheng Yu"
