"""自我演化系统 (Self-Evolution Engine v3.3)

Turing 的持续进化能力由 :class:`EvolutionTracker`、:class:`MetacognitiveEngine`
和 :class:`CompetitiveIntelligence` 三大引擎驱动：

**EvolutionTracker** — 十大子能力：

1. **经验积累** — 每次任务后记录反思（outcome、工具组合、经验教训）。
2. **策略进化** — 同类任务 ≥5 条经验后自动归纳策略模板。
3. **知识蒸馏** — 每 50 次任务触发合并去重、淘汰过时经验。
4. **AI 工具对比学习** — 分析 Claude Opus / Codex / Gemini / Copilot 策略并内化。
5. **经验合成** — 从引导策略合成模拟经验，加速策略从 bootstrapped 进化为 evolved。
6. **跨任务知识迁移** — bug_fix↔debug、feature↔refactor 技巧互通。
7. **自我诊断** — 策略成熟度、工具利用率、失败模式、进化速度、竞争力定位 5D 评估。
8. **失败恢复引擎** — 8 种失败模式分类、三级恢复策略、工具替代映射。
9. **工具探索顾问** — 基于任务特征推荐核心工具 + 探索工具，提升覆盖率。
10. **自训练模拟器** — 6 类型 × 3 难度生成含成功/失败的训练经验。

**MetacognitiveEngine** — 元认知九维能力：

11. **认知监控** — 实时评估推理质量、置信度、认知负荷。
12. **认知调控** — 根据监控信号动态调整策略、推理深度、工具选择。
13. **置信校准** — 校准预测置信度与实际成功率，防止系统性偏差。
14. **偏差检测** — 识别确认偏差、锚定偏差、决策振荡等认知陷阱。
15. **知识边界感** — 识别不确定性来源，知道何时需要更多信息。
16. **元认知反思** — 跨任务聚合元认知数据，生成能力画像和提升建议。
17. **认知自适应** — 自动调整置信度基线、负荷阈值、偏差灵敏度。
18. **认知效率** — 监控认知资源开销，优化推理效率。
19. **竞争力意识** — 将竞争对标洞察注入认知决策和策略建议。

**CompetitiveIntelligence** — 竞争力分析引擎（v3.3 新增）：

20. **持续自评** — 动态对标 7 大竞品（Claude Code / Cursor / Copilot / Devin / Aider / Codex / Windsurf）。
21. **能力矩阵** — 16 维度能力对比，排名和趋势分析。
22. **差距追踪** — 跟踪历次分析的差距变化趋势，验证改进效果。
23. **改进路线图** — 生成优先级排序的可实施改进项。
24. **元认知联动** — 竞争力洞察自动注入元认知决策和策略进化。

**评分系统** — 16 维度评分（10.5 分满分）。

数据存储::

    turing_data/
    ├── evolution/
    │   ├── reflections.json            # 所有任务反思
    │   ├── metacognition.json          # 元认知评估记录
    │   ├── calibration.json            # 置信校准历史
    │   ├── self_diagnosis.json         # 自我诊断报告
    │   ├── cognitive_adaptations.json  # 认知自适应参数
    │   ├── gap_analysis.json           # 差距分析报告
    │   ├── competitive_analysis.json   # 竞争力分析历史
    │   ├── competitive_report.json     # 最新竞争力报告
    │   └── recovery_playbook.json      # 失败恢复剧本
    │   └── recovery_playbook.json    # 失败恢复剧本
    └── persistent_memory/
        ├── strategies/          # 策略模板 (per task_type)
        ├── evolution_log.json   # 进化里程碑
        └── ai_tools_analysis/   # AI 工具学习笔记
"""
