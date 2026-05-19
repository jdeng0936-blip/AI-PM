"""
app/routers/retro.py — AI 复盘库 API

提供给前端复盘库页面 + admin 手工触发复盘生成。

端点:
- POST /retro/generate           手工生成新复盘(admin)
- GET  /retro/items              列出已沉淀的复盘(全员可见)
- GET  /retro/items/{id}         单条详情(全员可见)
- DELETE /retro/items/{id}       删除(admin)
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user, require_role
from app.models.knowledge import KnowledgeCategory, KnowledgeItem, RetroScope
from app.models.user import User, UserRole
from app.services.retro import generate_retrospective

router = APIRouter(prefix="/api/v1/retro", tags=["复盘库"])

_admin_only = require_role(UserRole.admin)
_writers = require_role(UserRole.admin, UserRole.manager)


# ────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    scope: str = Field(..., description="okr_cycle / project / monthly / incident")
    target_id: Optional[str] = None
    project_id: Optional[str] = None
    incident_id: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None
    persist: bool = True


class GenerateResponse(BaseModel):
    scope: str
    title: str
    markdown: str
    knowledge_item_id: Optional[str]


class RetroItemOut(BaseModel):
    id: str
    title: str
    category: str
    scope: Optional[str]
    tags: Optional[str]
    source_type: str
    source_id: Optional[str]
    project_id: Optional[str]
    created_by: Optional[str]
    created_at: Optional[str]


class RetroItemDetail(RetroItemOut):
    content: str


class RetroListResponse(BaseModel):
    total: int
    items: list[RetroItemOut]


# ────────────────────────────────────────────────────────────────
# 端点
# ────────────────────────────────────────────────────────────────


@router.post("/generate", response_model=GenerateResponse)
async def trigger_generate(
    req: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_writers),
):
    """手工触发一次复盘生成"""
    try:
        result = await generate_retrospective(
            db,
            scope=req.scope,
            target_id=req.target_id,
            project_id=req.project_id,
            incident_id=req.incident_id,
            year=req.year,
            month=req.month,
            persist=req.persist,
            actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"复盘生成失败:{exc}")

    if req.persist:
        await db.commit()

    return GenerateResponse(
        scope=result.scope,
        title=result.title,
        markdown=result.markdown,
        knowledge_item_id=result.knowledge_item_id,
    )


def _scope_from_tags(tags: Optional[str]) -> Optional[str]:
    if not tags:
        return None
    parts = [t.strip() for t in tags.split(",")]
    for s in (RetroScope.OKR_CYCLE, RetroScope.PROJECT, RetroScope.MONTHLY, RetroScope.INCIDENT):
        if s in parts:
            return s
    return None


@router.get("/items", response_model=RetroListResponse)
async def list_items(
    scope: Optional[str] = Query(None, description="过滤 scope"),
    project_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    stmt = select(KnowledgeItem).where(
        KnowledgeItem.category == KnowledgeCategory.RETROSPECTIVE
    )
    if scope:
        stmt = stmt.where(KnowledgeItem.tags.ilike(f"%{scope}%"))
    if project_id:
        stmt = stmt.where(KnowledgeItem.project_id == uuid.UUID(project_id))

    # 简单 count(避免大量数据时性能问题留后续优化)
    total = len((await db.execute(stmt.with_only_columns(KnowledgeItem.id))).scalars().all())

    stmt = (
        stmt.order_by(desc(KnowledgeItem.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return RetroListResponse(
        total=total,
        items=[
            RetroItemOut(
                id=str(r.id),
                title=r.title,
                category=r.category,
                scope=_scope_from_tags(r.tags),
                tags=r.tags,
                source_type=r.source_type,
                source_id=r.source_id,
                project_id=str(r.project_id) if r.project_id else None,
                created_by=str(r.created_by) if r.created_by else None,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in rows
        ],
    )


@router.get("/items/{item_id}", response_model=RetroItemDetail)
async def get_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    item = await db.get(KnowledgeItem, uuid.UUID(item_id))
    if not item or item.category != KnowledgeCategory.RETROSPECTIVE:
        raise HTTPException(404, "复盘报告不存在")
    # 浏览量 +1
    item.view_count = (item.view_count or 0) + 1
    await db.commit()
    return RetroItemDetail(
        id=str(item.id),
        title=item.title,
        category=item.category,
        scope=_scope_from_tags(item.tags),
        tags=item.tags,
        source_type=item.source_type,
        source_id=item.source_id,
        project_id=str(item.project_id) if item.project_id else None,
        created_by=str(item.created_by) if item.created_by else None,
        created_at=item.created_at.isoformat() if item.created_at else None,
        content=item.content,
    )


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_admin_only),
):
    item = await db.get(KnowledgeItem, uuid.UUID(item_id))
    if not item or item.category != KnowledgeCategory.RETROSPECTIVE:
        raise HTTPException(404, "复盘报告不存在")
    await db.delete(item)
    await db.commit()
