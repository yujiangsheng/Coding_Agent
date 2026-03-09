"""四层记忆系统 (Four-Layer Memory System)

Turing 的记忆架构模仿人类认知分层，各层职责不同、存储方式各异：

- **L1 WorkingMemory** — 会话级工作记忆（内存 + JSON 落盘）
  短期上下文缓冲，TF-IDF 搜索（含中文 bigram 分词），时间衰减加权。

- **L2 LongTermMemory** — 跨会话向量记忆（ChromaDB / JSON 降级）
  历史经验与知识积累，余弦相似度语义搜索，访问次数加权。

- **L3 PersistentMemory** — 结构化持久知识（YAML/JSON 文件）
  项目知识库、策略模板、进化日志，Jaccard 相似度去重。

- **MemoryManager** — 统一管理接口
  跨层检索 → 优先级排序（L3 > L2 > L1）→ 去重 → 格式化。

记忆流转::

    用户请求 → 检索 L2+L3 → 注入 L1
        ↓
    任务执行（L1 持续更新）
        ↓ 遇到知识盲区
    检索 L4 (RAG/Web) → 结果写入 L1
        ↓
    任务完成 → 反思 → 写入 L2
        ↓ 发现稳定模式
    归纳为策略 → 写入 L3
"""
