"""检索增强生成引擎 (Retrieval-Augmented Generation Engine)

四层记忆系统中 L4 外部记忆的核心组件，提供：

- **智能分块** — 代码文件按函数/类边界切割，文档按段落切割，
  避免截断语义单元（默认 500 字符分块）。

- **查询扩展** — 对用户查询生成 2-3 个语义等价变体（含编程术语同义词），
  多查询结果合并去重后返回 top_k。

- **多数据源** — 支持 docs（本地文档）、codebase（代码库）、
  experience_db（历史经验）三种数据源，独立索引。

- **存储后端** — 优先使用 ChromaDB 向量数据库进行语义搜索，
  未安装时自动降级为 JSON 关键词匹配。

Usage::

    from turing.rag.engine import RAGEngine
    engine = RAGEngine(data_dir="turing_data")
    engine.index_directory("./my_project", source="codebase")
    results = engine.search("authentication flow", source="codebase")
"""
