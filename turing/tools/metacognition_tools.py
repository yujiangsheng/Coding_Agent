"""元认知工具 — 暴露元认知能力给 Agent 主循环

提供以下工具：
- metacognitive_profile: 获取元认知能力画像（6维雷达 + 趋势分析）
- metacognitive_advice: 获取基于元认知画像的自我提升建议

全局 MetacognitiveEngine 实例在 Agent 启动时通过 set_metacognitive_engine() 注入。
"""

from __future__ import annotations

from turing.tools.registry import tool

_metacognitive_engine = None


def set_metacognitive_engine(engine):
    global _metacognitive_engine
    _metacognitive_engine = engine


@tool(
    name="metacognitive_profile",
    description="获取 Turing 的元认知能力画像，包含 6 维评分（监控精度、调控有效性、置信校准度、认知灵活性、知识边界感、反思深度）、常见偏差统计和效率趋势。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def metacognitive_profile() -> dict:
    if _metacognitive_engine is None:
        return {"error": "元认知系统未初始化"}
    return _metacognitive_engine.get_metacognitive_profile()


@tool(
    name="metacognitive_advice",
    description="基于元认知画像生成自我提升建议，识别薄弱环节并提供针对性改进行动。",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)
def metacognitive_advice() -> dict:
    if _metacognitive_engine is None:
        return {"error": "元认知系统未初始化"}
    recommendations = _metacognitive_engine.get_evolution_recommendations()
    return {"recommendations": recommendations}
