"""Turing — 自进化编程智能体 (Self-Evolving Coding Agent)

基于本地大模型（Qwen3-Coder 30B）的编程 Agent，具备：

- **四层记忆系统** — L1 工作记忆 / L2 长期记忆 / L3 持久记忆 / L4 外部记忆（RAG）
- **31+ 内置工具** — 文件读写、命令执行、代码搜索、Git 操作、测试运行、代码质量检查、
  批量重构、项目分析、记忆管理、RAG 检索、Web 搜索、AI 工具学习、AST 深度代码分析
- **自我演化** — 任务反思 → 经验积累 → 策略进化 → 知识蒸馏 → AI 工具对比学习
- **高级推理** — 链式推理（CoT）分层任务分解、动态温度调节、编辑-测试-修复循环
- **智能工具路由** — 任务类型感知的工具推荐、策略预播种、并行执行只读工具
- **语义错误分析** — 连续错误模式检测、参数自动修正、智能上下文压缩
- **TF-IDF 记忆检索** — 中文分词 + bigram 支持，跨层排序与去重

架构::

    CLI / Web UI
        ↓
    TuringAgent (ReAct Loop + CoT 推理 + ETF 验证循环)
        ├── ToolRegistry (31 tools, 13 modules)
        │     ├── 文件 / 命令 / 搜索 / Git / 测试 / 质量 / 重构 / 项目
        │     └── 记忆 / RAG·Web / 演化 / AST 代码分析
        ├── MemoryManager (4 layers + TF-IDF + 跨层排序)
        ├── RAGEngine (query expansion + code-aware chunking)
        ├── EvolutionTracker (反思 → 策略 → 蒸馏 → AI 学习 → 11 维评分)
        └── ParallelExecutor (ThreadPoolExecutor, 只读工具并发)

Author: Jiangsheng Yu
License: MIT
"""

__version__ = "0.6.0"
__author__ = "Jiangsheng Yu"
