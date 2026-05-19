"""
app/services/retro/prompts.py — 复盘 Prompt 工程

每种 scope 一份精心设计的 Prompt:
- 强调结构化输出(便于沉淀为知识资产)
- 强制要求归因 + 经验提炼 + 下一步建议
- 要求引用具体数据(防止 LLM 编造)
"""
from __future__ import annotations

import json
from typing import Any


SYSTEM_BASE = (
    "你是徽远成科技的 AI 复盘官,擅长基于客观数据进行根因分析与经验提炼。"
    "你写出的复盘报告会沉淀到知识库,未来在制定 OKR / 立项 / 决策时被检索复用,"
    "所以质量必须高:\n"
    "1. 所有结论必须有数据支撑,不要凭空判断\n"
    "2. 复盘三件套:What(发生了什么) → Why(根因) → How(下次怎么做)\n"
    "3. 经验提炼要可迁移,不只描述事件\n"
    "4. 中文输出,Markdown 格式,正文用 ## / ### / **粗体** / 列表\n"
    "5. 客观、平衡 — 既看到成绩也指出问题,不一边倒\n"
)


OKR_CYCLE_TEMPLATE = """请基于以下 OKR 周期数据撰写《周期复盘报告》。

【素材 JSON】
{data}

【报告结构(请严格按照此结构输出)】
## 周期概览
1-2 段文字,说明本周期目标完成度、KR 达成分布、整体趋势。

## 目标级达成分析
针对每个 Objective:
- ✅/⚠️/❌ 标记达成情况
- 哪些 KR 是亮点(原因)
- 哪些 KR 是短板(根因分析,引用进度日志来源)

## 根因总结(必填,3-5 条)
跨越具体目标,提炼本周期最值得记住的 **失败/成功原因**。
每条形如「问题描述 → 根因 → 影响范围」。

## 经验提炼(必填,3-5 条)
可迁移到未来周期的方法论或反模式。形如「下次类似场景,应该…避免…」。

## 下个周期建议
- 沿用什么(已被验证有效)
- 改进什么(本周期暴露的问题)
- 试验什么(新的赌注)
"""


PROJECT_TEMPLATE = """请基于以下项目数据撰写《项目复盘报告》。

【素材 JSON】
{data}

【报告结构】
## 项目摘要
项目名 / 周期 / 健康度终态 / 预算执行率。

## 关键里程碑回顾
列出关键节点 + 完成情况(若数据缺失请如实说明)。

## 团队表现
亮点成员 + 待提升成员(基于评分数据)。

## 风险与应对
本项目出现的主要风险事件 + 当时的处理方式 + 事后看是否合适。

## 根因总结(必填,3-5 条)
本项目最值得记住的成败原因。

## 经验提炼(必填,3-5 条)
对未来同类项目可迁移的方法论或反模式。

## 后续行动
- 立刻要做的(如收尾工作)
- 中长期改进项
"""


MONTHLY_TEMPLATE = """请基于以下月度数据撰写《月度管理复盘》。

【素材 JSON】
{data}

【报告结构】
## 月度概览
提交率、平均评分、风险数量、新增项目数。

## 部门表现对比
按平均分排名 + 各部门主要贡献 / 主要问题。

## 风险态势
本月主要风险类型 + 解决率 + 滞留风险。

## 关键人员
表现突出者 + 需要关注者(用数据支撑)。

## 经验提炼(必填,3 条)
本月管理动作中最值得迁移到下月的实践。

## 下月聚焦
管理层下月应优先处理的 3 件事。
"""


INCIDENT_TEMPLATE = """请基于以下事故数据撰写《事故复盘报告》。

【素材 JSON】
{data}

注意:这是「卡点已超过预期时长」类事件的复盘,目的是积累避坑经验。

【报告结构】
## 事件经过
按时间线还原:卡点出现 → 当事人响应 → 解决/未解决。

## 根因分析(必填)
用 5 Whys 或类似方法挖掘真因,不要停留在表象。

## 损失评估
延误天数、影响范围(项目/团队)、二次风险。

## 当时应该怎么做(必填)
针对每一步如果重来,正确动作是什么。

## 经验提炼(必填,3 条)
形成可检索的避坑清单条目,标题尽量像「【XX 类问题】XX 时该 XX」。

## 预防机制建议
组织/流程/系统层面如何避免再发。
"""


def render_okr_cycle_prompt(data: dict[str, Any]) -> str:
    return OKR_CYCLE_TEMPLATE.format(data=_dump(data))


def render_project_prompt(data: dict[str, Any]) -> str:
    return PROJECT_TEMPLATE.format(data=_dump(data))


def render_monthly_prompt(data: dict[str, Any]) -> str:
    return MONTHLY_TEMPLATE.format(data=_dump(data))


def render_incident_prompt(data: dict[str, Any]) -> str:
    return INCIDENT_TEMPLATE.format(data=_dump(data))


def _dump(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
