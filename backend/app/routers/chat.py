"""
app/routers/chat.py — 总经理 AI 对话查询

支持自然语言提问，AI 通过 SQL 聚合 + LLM 推理回答。
示例问题:
  - "本周谁延期最多？"
  - "采购部进度怎么样？"
  - "帮我生成本周的管理周报"
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.daily_report import DailyReport
from app.models.risk_alert import RiskAlert
from app.models.project import Project
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/chat", tags=["Admin AI Chat"])

_admin_only = require_role(UserRole.admin)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500, description="自然语言问题")


class ChatResponse(BaseModel):
    question: str
    answer: str
    data_context: dict = {}


@router.post("/ask", response_model=ChatResponse)
async def admin_ai_chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_admin_only),
):
    """
    总经理自然语言对话查询。
    Step 1: 根据问题关键词预检索相关数据
    Step 2: 将数据 + 问题发给 LLM 做推理回答
    """
    question = req.question.strip()
    context_data = {}

    # ── Step 1: 根据关键词预检索数据 ─────────────────────────────
    end = date.today()
    start = end - timedelta(days=7)

    # 近 7 天全员日报摘要
    reports_stmt = (
        select(User.name, User.department, DailyReport.report_date,
               DailyReport.ai_score, DailyReport.pass_check)
        .join(User, DailyReport.user_id == User.id)
        .where(DailyReport.report_date >= start)
        .order_by(DailyReport.report_date.desc())
        .limit(100)
    )
    reports = (await db.execute(reports_stmt)).all()
    context_data["recent_reports"] = [
        f"{r.name}({r.department}) {r.report_date} 评分{r.ai_score} {'✅' if r.pass_check else '❌'}"
        for r in reports
    ]

    # 未解决风险
    risks_stmt = (
        select(RiskAlert.description, RiskAlert.days_unresolved, User.name)
        .join(User, RiskAlert.user_id == User.id)
        .where(RiskAlert.status == "unresolved")
        .order_by(RiskAlert.days_unresolved.desc())
        .limit(20)
    )
    risks = (await db.execute(risks_stmt)).all()
    context_data["unresolved_risks"] = [
        f"{r.name}: {r.description} (已{r.days_unresolved}天)"
        for r in risks
    ]

    # 项目概况
    projects_stmt = select(
        Project.name, Project.health_status, Project.health_score
    ).limit(20)
    projects = (await db.execute(projects_stmt)).all()
    context_data["projects"] = [
        f"{p.name} 健康{p.health_status} 评分{p.health_score}"
        for p in projects
    ]

    # ── Step 2: 调 LLM 推理 ──────────────────────────────────────
    data_summary = (
        f"【近7天日报】\n" + "\n".join(context_data["recent_reports"][:30]) + "\n\n"
        f"【未解决风险】\n" + "\n".join(context_data["unresolved_risks"][:10]) + "\n\n"
        f"【项目概况】\n" + "\n".join(context_data["projects"][:10])
    )

    try:
        import httpx
        from app.config import settings
        from app.services.llm_selector import LLMSelector

        model_config = LLMSelector.get_model_for_task("admin_chat")
        payload = {
            "model": model_config["name"],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是徽远成科技的AI管理助手。根据以下业务数据回答总经理的提问。"
                        "回答要简洁、专业、有数据支撑。使用中文回答。"
                        "如果数据不足以回答，请坦诚说明。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"业务数据：\n{data_summary}\n\n总经理提问：{question}",
                },
            ],
            "temperature": model_config.get("temperature", 0.3),
            "max_tokens": model_config.get("max_tokens", 800),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.new_api_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.new_api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"]

    except Exception as e:
        answer = f"AI 回答生成失败：{str(e)[:200]}\n\n已检索到 {len(reports)} 条日报、{len(risks)} 条风险。"

    return ChatResponse(
        question=question,
        answer=answer,
        data_context={
            "reports_count": len(reports),
            "risks_count": len(risks),
            "projects_count": len(projects),
        },
    )
