"""Turing — 自进化编程智能体 (Self-Evolving Coding Agent) v6.0

基于本地大模型（Qwen3-Coder 30B）的编程 Agent，对标 Aider / Cursor / Claude Code / Devin，具备：

- **四层记忆系统** — L1 工作记忆 / L2 长期记忆 / L3 持久记忆 / L4 外部记忆（RAG）
- **80+ 内置工具** — 文件管理、持久化 Shell、Git 完整工作流、代码搜索、
  测试运行、多语言 AST 分析、基准评测、MCP 协议集成等
- **安全防护系统** — 危险操作确认 + Docker 沙箱隔离 + 审计日志（对标 Claude Code 权限系统）
- **多语言 AST 分析** — Python（内置 ast）+ JS/TS/Go/Rust/Java/C/C++/Ruby（tree-sitter）
- **精确 Token 管理** — tiktoken 精确计算 + 消息优先级打分 + 渐进式多层压缩
- **增量项目索引** — 基于文件哈希的增量 RAG 索引，避免重复索引未变更文件
- **子 Agent 支持** — spawn_sub_agent() 创建轻量级子 Agent 处理独立子任务
- **SWE-bench 评测** — 仓库级代码修改 + 回归测试评测框架
- **自我演化** — 任务反思 → 经验积累 → 策略进化 → 知识蒸馏 → AI 工具对比学习
  → 失败恢复引擎 → 自训练模拟器 → 15 维评分系统
- **元认知系统** — 6 维认知雷达、偏差检测、置信校准、认知自适应
- **v6.0 新能力**:
  · 安全防护系统 — SafetyGuard 危险操作确认 + SandboxExecutor Docker 沙箱（对标 Claude Code / Devin）
  · 多语言 AST — tree-sitter 支持 JS/TS/Go/Rust/Java/C/C++/Ruby 代码结构分析
  · 精确 Token 计算 — tiktoken 精确 token 计数替代字符估算
  · 增量 RAG 索引 — SHA-256 哈希检测文件变更，跳过未修改文件
  · 子 Agent 分派 — spawn_sub_agent() 独立上下文子任务执行
  · SWE-bench 评测 — 仓库级代码修改回归测试评测
  · 迭代上限提升 — max_iterations 20 → 50，支持更复杂任务
- **v3.2 新能力**:
  · 项目规约文件 — 自动加载 TURING.md / CLAUDE.md 编码约定
  · LLM 智能压缩 — compact 使用 LLM 生成高质量对话摘要
  · Prompt Caching — Anthropic cache_control 降低 system prompt 成本
  · Architect-Editor 双模型 — 规划用强模型，执行用快模型
  · 权限规则文件 — .turing-rules 项目级安全配置
  · ETF 三重验证 — 编辑后自动 lint + type-check + 测试
  · @-mention 引用 — @file @folder 语法引用代码上下文
  · 秘密检测 — API 密钥/密码泄露检测
  · 审计日志持久化 — JSONL 格式磁盘存储
  · 成本预算控制 — token_budget 限制单任务开销
  · 会话恢复 — --continue / --resume CLI 参数
  · 斜杠命令扩展 — /compact /cost /diff /undo /config 等
  · 内联 Diff 预览 — 编辑结果彩色高亮显示
- **v3.3 新能力**:
  · 竞争力分析引擎 — 自动对标 7 大竞品（Claude Code/Cursor/Copilot/Devin/Aider/Codex/Windsurf）
  · 16 维能力矩阵 — 动态评估各维度的竞争力排名和差距
  · 竞争力驱动进化 — 差距洞察自动注入元认知决策和策略演化
  · 改进路线图生成 — 优先级排序的可实施改进项
  · 趋势追踪 — 历次竞争力分析对比，验证改进效果
- **v3.4 新能力（竞争力驱动自动补全）**:
  · context_budget — 上下文 token 预算监控与优化建议
  · task_plan — 结构化任务分解（含依赖、风险、验证标准）
  · checkpoint_save/restore — 文件修改前快照，失败一键回滚
  · test_coverage — 专用覆盖率分析（pytest-cov / Istanbul）
  · security_scan — 静态安全扫描（bandit / 内置正则 8 种模式）
  · pr_summary — 基于 git diff 自动生成 PR 描述
  · detect_project 增强 — CI/CD 详情提取 + Monorepo 检测
  · 多路径推理提示 — 复杂任务自动考虑备选方案
  · 上下文预算管理提示 — token 使用超阈值自动压缩
- **v3.5 新能力（竞争力驱动第二轮补全）**:
  · context_compress — 智能上下文压缩（按内容类型选择压缩策略）
  · dependency_graph — 模块依赖图分析 + 循环依赖检测 + 拓扑分层
  · auto_fix — 自动 lint + 修复（ruff/eslint 集成）
  · verify_hypothesis — 结构化假设验证（含命令行实验）
  · LSP 补全服务器 — 基于 AST 的代码补全（python -m turing.lsp）
  · 增强型上下文压缩 — _summarize_tool_result 新增 AST/依赖图/PR 等内容类型
  · 竞争力评分更新 — 动态检测新工具提升各维度分数

架构::

    CLI / Web UI
        ↓
    TuringAgent (ReAct Loop + CoT + ETF + Safety + Sub-Agent)
        ├── SafetyGuard (Permission: ALLOW/CONFIRM/DENY + Audit)
        ├── SandboxExecutor (Docker isolation / host fallback)
        ├── ToolRegistry (80 tools, 19 modules)
        │     ├── 文件管理（diff 预览 + multi_edit + move/copy/delete/find）
        │     ├── 持久化 Shell（env/cwd 保持 + 后台进程 run/check/stop）
        │     ├── 搜索 + Repo Map / Git 完整工作流
        │     ├── 测试（覆盖率 + 失败详情）/ 质量（auto lint-fix）/ 重构
        │     ├── 多语言 AST 分析（Python ast + tree-sitter 多语言）
        │     ├── 项目 / 记忆 / RAG·Web（增量索引）
        │     └── 演化（含失败恢复 + 自训练）/ 元认知
        ├── LSPServer (基于 AST 的代码补全 over JSON-RPC/stdio)
        ├── MemoryManager (4 layers + TF-IDF + 跨层排序)
        ├── RAGEngine (query expansion + code-aware chunking + 增量索引)
        ├── EvolutionTracker (16 维评分 + 18 子能力)
        ├── MetacognitiveEngine (7 维认知雷达 + 偏差检测 + 竞争力意识)
        ├── CompetitiveIntelligence (7 竞品对标 + 16 维能力矩阵 + 自动路线图)
        ├── TokenAwareContextManager (tiktoken 精确计算 + 优先级打分 + 渐进压缩)
        ├── BenchmarkRunner (HumanEval + SWE-bench + 业界对比)
        └── ParallelExecutor (ThreadPoolExecutor, 只读工具并发)

Author: Jiangsheng Yu
License: MIT
"""

__version__ = "3.5.0"
__author__ = "Jiangsheng Yu"
