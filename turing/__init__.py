"""Turing — 自进化编程智能体 (Self-Evolving Coding Agent)

基于本地大模型（Qwen3-Coder 30B）的编程 Agent，具备：

- **四层记忆系统** — L1 工作记忆 / L2 长期记忆 / L3 持久记忆 / L4 外部记忆（RAG）
- **26+ 内置工具** — 文件读写、命令执行、代码搜索、Git 操作、测试运行、代码质量检查、
  批量重构、项目分析、记忆管理、RAG 检索、Web 搜索、AI 工具学习
- **自我演化** — 任务反思 → 经验积累 → 策略进化 → 知识蒸馏 → AI 工具对比学习
- **元推理框架** — 任务复杂度评估、策略匹配、循环检测、上下文溢出管理
- **TF-IDF 记忆检索** — 中文分词 + bigram 支持，跨层排序与去重

架构::

    CLI / Web UI
        ↓
    TuringAgent (ReAct Loop)
        ├── ToolRegistry (26 tools)
        ├── MemoryManager (4 layers)
        ├── RAGEngine (query expansion + code-aware chunking)
        └── EvolutionTracker (reflection → strategy → distillation)

Author: Jiangsheng Yu
License: MIT
"""

__version__ = "0.4.0"
__author__ = "Jiangsheng Yu"
