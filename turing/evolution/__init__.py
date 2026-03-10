"""自我演化系统 (Self-Evolution Engine)

Turing 的持续进化能力由 :class:`EvolutionTracker` 驱动，包含四大子能力：

1. **经验积累** — 每次任务后记录反思（成功/失败/工具使用/耗时），
   按 task_type 分类归档（bug_fix / feature / refactor / debug / explain / general）。

2. **策略进化** — 同类任务 ≥5 条经验后，自动从成功案例中归纳策略模板，
   提取推荐步骤与最佳实践，加权综合（时间衰减 × 成功率）。

3. **知识蒸馏** — 每 50 次任务触发一次，合并冗余反思，淘汰低质量条目，
   生成能力成长报告（十一维评分：代码质量/调试/架构/效率/安全/沟通/工具多样性/推理深度/记忆利用率/学习速率/验证覆盖率）。

4. **AI 工具对比学习** — 分析 Claude Opus / Codex / Gemini / Copilot 的策略，
   提取差异化优势并内化为自身策略，识别能力差距并生成改进路线图。

数据存储::

    turing_data/
    ├── evolution/
    │   └── reflections.json     # 所有任务反思
    └── persistent_memory/
        ├── strategies/          # 策略模板 (per task_type)
        ├── evolution_log.json   # 进化里程碑
        └── ai_tools_analysis/   # AI 工具学习笔记
"""
