"""
chat_tools/weekly_report.py — AI 自动生成管理周报

设计:
- 一个 Tool: generate_weekly_report — LLM 在对话中调用,或定时任务直接调用
- 数据来源:聚合本周日报 + 风险预警 + 项目健康度
- 由内置的 LLM 二次调用生成 Markdown 周报(不依赖外层对话 LLM,工具自闭环)

调用关系:
  /chat/ask "帮我写本周周报" → LLM 决定调 generate_weekly_report
  scheduler 周一 09:00 → 直接调 generate_weekly_report → 走通知服务推送
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

import httpx
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.daily_report import DailyReport
from app.models.project import Project, ProjectStatus
from app.models.risk_alert import RiskAlert
from app.models.user import User
from app.services.chat_tools import tool
from app.services.llm_selector import LLMSelector

logger = logging.getLogger("aipm.weekly_report")


# ────────────────────────────────────────────────────────────────
# 数据聚合(供 Tool 和定时任务复用)
# ────────────────────────────────────────────────────────────────


async def collect_weekly_data(
    db: AsyncSession,
    *,
    end_date: Optional[date] = None,
) -> dict[str, Any]:
    """收集"上一个完整周(周一→周日)"的数据。end_date 默认昨天。"""
    if end_date is None:
        end_date = date.today() - timedelta(days=1)

    # 找到 end_date 所在那一周的周一和周日
    monday = end_date - timedelta(days=end_date.weekday())
    sunday = monday + timedelta(days=6)

    # 1) 日报汇总
    report_stmt = (
        select(
            User.name,
            User.department,
            DailyReport.report_date,
            DailyReport.ai_score,
            DailyReport.pass_check,
            DailyReport.parsed_content,
        )
        .join(User, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= monday,
                DailyReport.report_date <= sunday,
            )
        )
        .order_by(DailyReport.report_date.desc(), DailyReport.ai_score.desc())
    )
    reports = (await db.execute(report_stmt)).all()

    # 2) 部门聚合
    dept_stmt = (
        select(
            User.department,
            func.avg(DailyReport.ai_score).label("avg_score"),
            func.count(DailyReport.id).label("submitted"),
        )
        .join(User, DailyReport.user_id == User.id)
        .where(and_(DailyReport.report_date >= monday, DailyReport.report_date <= sunday))
        .group_by(User.department)
        .order_by(desc("avg_score"))
    )
    departments = [
        {
            "department": r.department or "(未分组)",
            "avg_score": round(float(r.avg_score), 1) if r.avg_score else 0,
            "submitted": int(r.submitted),
        }
        for r in (await db.execute(dept_stmt)).all()
    ]

    # 3) 风险预警(本周新增 + 仍未解决)
    risk_stmt = (
        select(
            User.name,
            User.department,
            RiskAlert.description,
            RiskAlert.alert_type,
            RiskAlert.days_unresolved,
            RiskAlert.status,
            RiskAlert.created_at,
        )
        .join(User, RiskAlert.user_id == User.id)
        .where(RiskAlert.created_at >= monday)
        .order_by(desc(RiskAlert.days_unresolved))
        .limit(30)
    )
    risks = [
        {
            "user": r.name,
            "department": r.department,
            "description": r.description[:200],
            "type": r.alert_type,
            "days_unresolved": int(r.days_unresolved),
            "status": r.status,
        }
        for r in (await db.execute(risk_stmt)).all()
    ]

    # 4) 项目健康度
    proj_stmt = select(Project).where(Project.status == ProjectStatus.active).order_by(Project.health_score)
    projects = [
        {
            "code": p.code,
            "name": p.name,
            "stage": p.current_stage,
            "health_status": p.health_status.value if p.health_status else None,
            "health_score": p.health_score,
        }
        for p in (await db.execute(proj_stmt)).scalars().all()
    ]

    # 5) Top/Bottom 人员
    user_perf_stmt = (
        select(
            User.name,
            User.department,
            func.avg(DailyReport.ai_score).label("avg_score"),
            func.count(DailyReport.id).label("submitted"),
        )
        .join(DailyReport, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= monday,
                DailyReport.report_date <= sunday,
                DailyReport.deleted_at.is_(None),  # V2.4 Stage 3 C1
            )
        )
        .group_by(User.id, User.name, User.department)
        .order_by(desc("avg_score"))
    )
    user_perf = [
        {
            "name": r.name,
            "department": r.department,
            "avg_score": round(float(r.avg_score), 1) if r.avg_score else 0,
            "submitted": int(r.submitted),
        }
        for r in (await db.execute(user_perf_stmt)).all()
    ]

    return {
        "week_range": {"start": monday.isoformat(), "end": sunday.isoformat()},
        "report_count": len(reports),
        "departments": departments,
        "risks": risks,
        "projects": projects,
        "top_performers": user_perf[:5],
        "bottom_performers": list(reversed(user_perf))[:3] if len(user_perf) >= 3 else [],
    }


# ────────────────────────────────────────────────────────────────
# 内置 LLM 调用(独立于对话主循环,工具自闭环)
# ────────────────────────────────────────────────────────────────


WEEKLY_PROMPT = """你是徽远成科技的 AI 战略秘书,负责为总经理撰写本周管理周报。

【素材】
以下是本周(周一至周日)的业务数据 JSON,请基于这些事实撰写周报。

{data_json}

【输出要求】
用 Markdown 格式输出,包含以下 6 个章节(可按需调整顺序):
1. ## 本周总览  — 1-2 段文字概述本周整体情况(提交率/平均分/关键风险)
2. ## 部门表现  — 按部门排名,标注最优 + 需关注
3. ## ⚠️ 风险预警  — 关键卡点 Top 3,每条说明影响 + 建议动作
4. ## 项目健康度  — 三色分布 + 重点项目状态
5. ## 个人亮点 / 关注  — Top 2-3 个表现优秀者 + 需关注者
6. ## 下周建议  — 给管理层的 3 条具体建议(基于本周数据)

【风格】
- 简洁专业,数据先行
- 关键数字加粗
- 避免空话套话
- 中文输出
"""


async def render_weekly_report_markdown(data: dict[str, Any]) -> str:
    """调 LLM 渲染周报 Markdown"""
    import json

    model_config = LLMSelector.get_model_for_task("deep_analysis")
    payload = {
        "model": model_config["name"],
        "messages": [
            {
                "role": "user",
                "content": WEEKLY_PROMPT.format(data_json=json.dumps(data, ensure_ascii=False, indent=2)),
            }
        ],
        "temperature": model_config.get("temperature", 0.5),
        "max_tokens": model_config.get("max_tokens", 4096),
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.new_api_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.new_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        logger.exception("weekly_report LLM call failed")
        return f"⚠️ 周报 AI 渲染失败: {exc}\n\n原始数据已收集:见 data_context"


# ────────────────────────────────────────────────────────────────
# Tool:对话中调用 / 定时任务直接调用都走这里
# ────────────────────────────────────────────────────────────────


@tool(
    description="生成本周或上一个完整周的 AI 管理周报(返回 Markdown + 原始数据)",
)
async def generate_weekly_report(
    db: AsyncSession,
    scope: str = "last_week",
) -> dict[str, Any]:
    """
    Args:
        scope: 周报范围,可选 last_week(默认,上一个完整周) | this_week(本周至今)
    """
    today = date.today()
    if scope == "this_week":
        end_date = today
    else:
        # last_week:取上周日作为 end_date
        end_date = today - timedelta(days=today.weekday() + 1)

    data = await collect_weekly_data(db, end_date=end_date)
    markdown = await render_weekly_report_markdown(data)

    return {
        "week_range": data["week_range"],
        "markdown": markdown,
        "stats": {
            "report_count": data["report_count"],
            "department_count": len(data["departments"]),
            "risk_count": len(data["risks"]),
            "project_count": len(data["projects"]),
        },
    }
