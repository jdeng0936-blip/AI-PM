"""
app/services/retro/generator.py — 复盘生成主入口

整合 collectors → prompts → LLM → 沉淀为 KnowledgeItem。

调用方:
- routers/retro.py 的手工触发端点
- scheduled_tasks 的季度自动触发
- chat_tools.retro 的对话触发
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date as _date
from typing import Any, Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.knowledge import KnowledgeCategory, KnowledgeItem, RetroScope
from app.services.llm_selector import LLMSelector
from app.services.retro import collectors, prompts

logger = logging.getLogger("aipm.retro")


@dataclass
class RetroGenerationResult:
    scope: str
    title: str
    markdown: str
    knowledge_item_id: Optional[str]
    raw_data: dict[str, Any]


# ────────────────────────────────────────────────────────────────
# 主入口
# ────────────────────────────────────────────────────────────────


async def generate_retrospective(
    db: AsyncSession,
    *,
    scope: str,
    target_id: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    project_id: Optional[str] = None,
    incident_id: Optional[str] = None,
    persist: bool = True,
    actor_id: Optional[UUID] = None,
) -> RetroGenerationResult:
    """
    生成复盘报告。根据 scope 分派:
    - scope='okr_cycle' + target_id(cycle UUID)
    - scope='project' + project_id(project UUID)
    - scope='monthly' + year/month
    - scope='incident' + incident_id(risk_alert UUID)
    """
    scope = scope.lower().strip()

    # 1) 聚合数据
    data, default_title, source_id, related_project_id = await _collect(
        db, scope=scope, target_id=target_id,
        year=year, month=month,
        project_id=project_id, incident_id=incident_id,
    )
    if "error" in data:
        raise ValueError(data["error"])

    # 2) 选 prompt
    user_prompt = _render_prompt(scope, data)

    # 3) 调 LLM
    markdown = await _call_llm(user_prompt)

    # 4) 沉淀
    knowledge_id: Optional[str] = None
    if persist:
        item = KnowledgeItem(
            title=default_title,
            category=KnowledgeCategory.RETROSPECTIVE,
            content=markdown,
            tags=_scope_tag(scope),
            source_type="ai_retrospective",
            source_id=source_id,
            project_id=UUID(related_project_id) if related_project_id else None,
            created_by=actor_id,
        )
        db.add(item)
        await db.flush()
        knowledge_id = str(item.id)
        # 注:由调用方决定 commit;季度任务/对话场景在外层提交

    return RetroGenerationResult(
        scope=scope,
        title=default_title,
        markdown=markdown,
        knowledge_item_id=knowledge_id,
        raw_data=data,
    )


async def generate_retrospective_safe(
    db: AsyncSession, **kwargs: Any,
) -> Optional[RetroGenerationResult]:
    """异常安全版本(给定时任务/Tool 调用用),失败返回 None"""
    try:
        return await generate_retrospective(db, **kwargs)
    except Exception:
        logger.exception("retro generation failed")
        return None


# ────────────────────────────────────────────────────────────────
# 内部
# ────────────────────────────────────────────────────────────────


async def _collect(
    db: AsyncSession, *,
    scope: str,
    target_id: Optional[str],
    year: Optional[int], month: Optional[int],
    project_id: Optional[str], incident_id: Optional[str],
) -> tuple[dict, str, Optional[str], Optional[str]]:
    """返回 (data, default_title, source_id, related_project_id)"""
    if scope == RetroScope.OKR_CYCLE:
        if not target_id:
            return {"error": "scope=okr_cycle 需要 target_id(cycle uuid)"}, "", None, None
        data = await collectors.collect_okr_cycle(db, UUID(target_id))
        if "error" in data:
            return data, "", None, None
        title = f"OKR 周期复盘 · {data['cycle']['name']}"
        return data, title, target_id, None

    if scope == RetroScope.PROJECT:
        pid = project_id or target_id
        if not pid:
            return {"error": "scope=project 需要 project_id"}, "", None, None
        data = await collectors.collect_project(db, UUID(pid))
        if "error" in data:
            return data, "", None, None
        title = f"项目复盘 · {data['project']['name']}"
        return data, title, pid, pid

    if scope == RetroScope.MONTHLY:
        if not (year and month):
            today = _date.today()
            year = year or today.year
            month = month or today.month
        data = await collectors.collect_monthly(db, year, month)
        title = f"月度复盘 · {year}-{month:02d}"
        return data, title, f"{year}-{month:02d}", None

    if scope == RetroScope.INCIDENT:
        rid = incident_id or target_id
        if not rid:
            return {"error": "scope=incident 需要 incident_id(risk_alert uuid)"}, "", None, None
        data = await collectors.collect_incident(db, UUID(rid))
        if "error" in data:
            return data, "", None, None
        owner_name = (data.get("incident", {}).get("owner") or {}).get("name") or "未知"
        title = f"事故复盘 · {owner_name} · {data['incident']['type']}"
        return data, title, rid, None

    return {"error": f"unsupported scope: {scope}"}, "", None, None


def _render_prompt(scope: str, data: dict[str, Any]) -> str:
    if scope == RetroScope.OKR_CYCLE:
        return prompts.render_okr_cycle_prompt(data)
    if scope == RetroScope.PROJECT:
        return prompts.render_project_prompt(data)
    if scope == RetroScope.MONTHLY:
        return prompts.render_monthly_prompt(data)
    if scope == RetroScope.INCIDENT:
        return prompts.render_incident_prompt(data)
    raise ValueError(f"no prompt for scope: {scope}")


def _scope_tag(scope: str) -> str:
    return f"retro,{scope}"


async def _call_llm(user_prompt: str) -> str:
    model_config = LLMSelector.get_model_for_task("retrospective")
    payload = {
        "model": model_config["name"],
        "messages": [
            {"role": "system", "content": prompts.SYSTEM_BASE},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": model_config.get("temperature", 0.55),
        "max_tokens": model_config.get("max_tokens", 5500),
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{settings.new_api_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.new_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"] or ""
