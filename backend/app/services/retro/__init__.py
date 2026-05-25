"""
app/services/retro/ — AI 自动复盘服务

四种复盘类型(scope):
- okr_cycle: OKR 周期结束时的目标达成复盘
- project:   项目完成时的全周期复盘
- monthly:   月度管理复盘(跨项目)
- incident:  连续高危风险的事故复盘

工作流:
  1. collectors.py 按 scope 聚合相关业务数据(纯查询,不调 LLM)
  2. prompts.py 按 scope 渲染 system + user prompt
  3. generator.py 调 LLM(retrospective 模型),输出结构化复盘 Markdown
  4. persistor.py 把复盘沉淀为 KnowledgeItem(category=retrospective)
                  并按需触发通知(管理层 / 项目负责人)

设计原则:
- 复盘是知识资产,落入 knowledge_items,可被未来的 OKR 制定 / 项目立项时检索
- 失败任何一步都不影响调用方主流程(generator 提供 safe 版本)
"""

from app.services.retro.generator import (
    RetroGenerationResult,
    generate_retrospective,
    generate_retrospective_safe,
)

__all__ = [
    "generate_retrospective",
    "generate_retrospective_safe",
    "RetroGenerationResult",
]
