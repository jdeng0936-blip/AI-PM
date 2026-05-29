"""
app/routers/chat.py — 总经理 AI 对话查询(Function Calling 多轮编排)

工作流:
  Step 0: 用户提问 → 拼装 system + user 消息
  Step 1: LLM 决策:回答 or 调用 Tool
  Step 2: 若 Tool 调用,执行 → 把结果以 tool message 喂回 LLM → 回到 Step 1
  Step 3: LLM 给出最终自然语言回答 + 引用源

设计要点:
- 最多 5 轮 Tool 调用,防止 LLM 无限循环
- 所有 Tool 失败都返回 {"error": ...} 而不是抛异常,LLM 自主决策
- 记录每次调用 trace(tool_name + args + result_summary),前端可展开"思考过程"
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.rbac import require_role
from app.models.chat_message import ChatMessage, ChatRole
from app.models.chat_session import ChatSession
from app.models.user import User, UserRole
from app.schemas.chat_session import (
    ChatMessageOut,
    ChatSessionDetail,
    ChatSessionListItem,
    ChatSessionListResponse,
    ChatSessionUpdate,
)
from app.services.chat_tools import registry
from app.services.llm_selector import LLMSelector

router = APIRouter(prefix="/api/v1/chat", tags=["Admin AI Chat"])

logger = logging.getLogger("aipm.chat")

_admin_only = require_role(UserRole.admin)

MAX_TOOL_ROUNDS = 5
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARS = 20000


SYSTEM_PROMPT = """你是徽远成科技的 AI 战情助手,服务总经理(admin 角色)。

【你的能力】
- 你拥有一组业务数据查询 Tool,可以查询日报、风险预警、项目状态、人员表现等
- 你必须通过 Tool 获取数据,严禁凭印象编造数字/姓名/项目名

【回答规则】
1. 优先用最匹配的 Tool 取数据,需要多维度信息时可连续调用多个 Tool
2. 拿到数据后用简洁的中文回答总经理,关键数字用粗体或列表呈现
3. 答案末尾用一行『📊 数据来源: 调用了 X 次 Tool,基于 Y 条记录』标注引用
4. 数据不足时坦诚说明,不要假装知道
5. 时间相关问题默认窗口是「近 7 天」,除非用户明确指定

【风格】
- 简洁专业,像给 CEO 汇报
- 避免冗长,关键结论先行,细节按需补充
- 中文回答
"""


# ────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    # 可选:限定本次对话只暴露这些 tool(测试/隔离用)
    allowed_tools: Optional[list[str]] = None
    # T-1201: 可选;携带则加载该会话历史并追加本轮,缺省则隐式创建新会话
    session_id: Optional[uuid.UUID] = None


class ToolCallTrace(BaseModel):
    tool: str
    arguments: dict[str, Any]
    result_preview: str
    error: Optional[str] = None


class ChatResponse(BaseModel):
    question: str
    answer: str
    tool_calls: list[ToolCallTrace] = []
    rounds: int
    model: str
    session_id: uuid.UUID


# ────────────────────────────────────────────────────────────────
# LLM 调用
# ────────────────────────────────────────────────────────────────


async def _call_llm(
    *,
    model_config: dict[str, Any],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    timeout: float = 90.0,
) -> dict[str, Any]:
    """单次调用 LLM,返回完整 response.message 对象(含可能的 tool_calls)"""
    payload = {
        "model": model_config["name"],
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": model_config.get("temperature", 0.3),
        "max_tokens": model_config.get("max_tokens", 2048),
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
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
    return data["choices"][0]["message"]


def _result_preview(result: dict[str, Any], max_len: int = 280) -> str:
    """把 tool 结果压缩为单行预览,供前端展示"""
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        text = str(result)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def _message_to_openai(row: ChatMessage) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": row.role.value,
        "content": row.content or "",
    }
    if row.tool_calls is not None:
        message["tool_calls"] = row.tool_calls
    if row.tool_call_id:
        message["tool_call_id"] = row.tool_call_id
    return message


def _message_size(message: dict[str, Any]) -> int:
    size = len(str(message.get("content") or ""))
    tool_calls = message.get("tool_calls")
    if tool_calls is not None:
        size += len(json.dumps(tool_calls, ensure_ascii=False, default=str))
    return size


def _trim_history(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trimmed = list(messages)
    total = sum(_message_size(m) for m in trimmed)
    while trimmed and total > MAX_HISTORY_CHARS:
        trimmed.pop(0)
        total = sum(_message_size(m) for m in trimmed)
    return trimmed


# ────────────────────────────────────────────────────────────────
# Endpoint
# ────────────────────────────────────────────────────────────────


@router.get("/tools")
async def list_tools(_user=Depends(_admin_only)) -> dict:
    """暴露当前所有可用 Tool 列表(管理员调试用)"""
    return {
        "count": len(registry.all()),
        "tools": [{"name": t.name, "description": t.description} for t in registry.all()],
    }


class WeeklyReportRequest(BaseModel):
    scope: str = Field(default="last_week", description="last_week | this_week")


@router.post("/weekly-report")
async def trigger_weekly_report(
    req: WeeklyReportRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_admin_only),
):
    """手工触发周报生成(管理员从前端按钮调用,不走 LLM tool calling)"""
    from app.services.chat_tools.weekly_report import generate_weekly_report

    result = await generate_weekly_report(db, scope=req.scope, tenant_id=_user.tenant_id)
    return result


@router.post("/ask", response_model=ChatResponse)
async def admin_ai_chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_admin_only),
):
    """总经理自然语言对话查询(基于 Function Calling)"""
    question = req.question.strip()
    model_config = LLMSelector.get_model_for_task("admin_chat")

    tools = registry.openai_schemas(only=req.allowed_tools)
    if not tools:
        raise HTTPException(503, "未注册任何对话 Tool")

    if req.session_id is None:
        session = ChatSession(
            user_id=_user.id,
            title=question[:30],
            tenant_id=_user.tenant_id,
            created_by=_user.id,
        )
        db.add(session)
        await db.flush()
    else:
        session = await _load_owned_session(db, req.session_id, _user)

    history_rows = (
        (
            await db.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session.id,
                    ChatMessage.tenant_id == _user.tenant_id,
                )
                .order_by(ChatMessage.created_at.asc())
                .limit(MAX_HISTORY_MESSAGES)
            )
        )
        .scalars()
        .all()
    )
    history_messages = _trim_history([_message_to_openai(row) for row in history_rows])

    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history_messages)
    messages.append({"role": "user", "content": question})

    db.add(
        ChatMessage(
            session_id=session.id,
            role=ChatRole.user,
            content=question,
            tenant_id=_user.tenant_id,
            created_by=_user.id,
        )
    )
    traces: list[ToolCallTrace] = []
    final_answer: str = ""

    for round_idx in range(MAX_TOOL_ROUNDS):
        try:
            assistant_msg = await _call_llm(
                model_config=model_config,
                messages=messages,
                tools=tools,
            )
        except httpx.HTTPError as exc:
            logger.exception("LLM call failed at round %d", round_idx)
            raise HTTPException(502, f"LLM 调用失败: {exc}")

        tool_calls = assistant_msg.get("tool_calls") or []

        # LLM 给出了最终答案 → 收尾
        if not tool_calls:
            final_answer = assistant_msg.get("content") or ""
            break

        # 把 assistant 消息(含 tool_calls)塞回历史
        messages.append(
            {
                "role": "assistant",
                "content": assistant_msg.get("content") or "",
                "tool_calls": tool_calls,
            }
        )
        db.add(
            ChatMessage(
                session_id=session.id,
                role=ChatRole.assistant,
                content=assistant_msg.get("content") or "",
                tool_calls=tool_calls,
                tenant_id=_user.tenant_id,
                created_by=_user.id,
            )
        )

        # 逐个执行 tool_calls
        for tc in tool_calls:
            tc_id = tc.get("id") or ""
            fn = tc.get("function") or {}
            tool_name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError:
                args = {}

            result = await registry.dispatch(tool_name, db, args, context={"tenant_id": _user.tenant_id})
            traces.append(
                ToolCallTrace(
                    tool=tool_name,
                    arguments=args,
                    result_preview=_result_preview(result),
                    error=result.get("error") if isinstance(result, dict) else None,
                )
            )

            # 喂回 tool message
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": tool_name,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
            db.add(
                ChatMessage(
                    session_id=session.id,
                    role=ChatRole.tool,
                    content=json.dumps(result, ensure_ascii=False, default=str),
                    tool_call_id=tc_id,
                    tenant_id=_user.tenant_id,
                    created_by=_user.id,
                )
            )
    else:
        # 5 轮内未收敛 → 强制让 LLM 总结
        messages.append(
            {
                "role": "user",
                "content": "已达到工具调用上限,请基于现有信息直接给出最终回答,不要再调用工具。",
            }
        )
        try:
            final_msg = await _call_llm(
                model_config=model_config,
                messages=messages,
                tools=[],
            )
            final_answer = final_msg.get("content") or "无法在限定轮数内得到答案。"
        except Exception:
            final_answer = "AI 在限定轮数内未能完成查询。"

    final_answer = final_answer.strip()
    db.add(
        ChatMessage(
            session_id=session.id,
            role=ChatRole.assistant,
            content=final_answer,
            tenant_id=_user.tenant_id,
            created_by=_user.id,
        )
    )
    await db.flush()
    session.message_count = int(
        await db.scalar(select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session.id)) or 0
    )
    session.last_message_at = datetime.now(timezone.utc)
    await db.commit()

    return ChatResponse(
        question=question,
        answer=final_answer,
        tool_calls=traces,
        rounds=len(traces) and (round_idx + 1) or 1,
        model=model_config["name"],
        session_id=session.id,
    )


# ────────────────────────────────────────────────────────────────
# T-1201: 会话历史管理
# ────────────────────────────────────────────────────────────────


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_admin_only),
):
    """列表本 admin 的对话历史(分页 + 可选标题搜索)"""
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(400, "page >=1 / page_size 1~100")

    stmt = (
        select(ChatSession)
        .where(
            ChatSession.user_id == _user.id,
            ChatSession.tenant_id == _user.tenant_id,
            ChatSession.deleted_at.is_(None),
        )
        .order_by(ChatSession.last_message_at.desc().nulls_last(), ChatSession.created_at.desc())
    )
    if search:
        stmt = stmt.where(ChatSession.title.ilike(f"%{search.strip()}%"))

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await db.execute(total_stmt)).scalar_one() or 0)
    rows = (await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return ChatSessionListResponse(items=[ChatSessionListItem.model_validate(r) for r in rows], total=total)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_session_detail(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_admin_only),
):
    """会话详情(含完整 message 列表,按 created_at ASC)"""
    session = await _load_owned_session(db, session_id, _user)
    msg_rows = (
        (
            await db.execute(
                select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return ChatSessionDetail(
        id=session.id,
        title=session.title,
        message_count=session.message_count,
        last_message_at=session.last_message_at,
        created_at=session.created_at,
        messages=[ChatMessageOut.model_validate(m) for m in msg_rows],
    )


@router.patch("/sessions/{session_id}", response_model=ChatSessionListItem)
async def update_session(
    session_id: uuid.UUID,
    payload: ChatSessionUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_admin_only),
):
    """改 session.title(用户给历史会话重命名)"""
    session = await _load_owned_session(db, session_id, _user)
    session.title = payload.title.strip()
    await db.commit()
    await db.refresh(session)
    return ChatSessionListItem.model_validate(session)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_admin_only),
):
    """软删 session(设置 deleted_at);message 物理保留备查"""
    session = await _load_owned_session(db, session_id, _user)
    if session.deleted_at is None:
        session.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return None


# ────────────────────────────────────────────────────────────────
# 内部 helper
# ────────────────────────────────────────────────────────────────


async def _load_owned_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user: User,
) -> ChatSession:
    """加载会话并校验 RBAC(归属当前 admin + 同 tenant + 未软删);失败 404"""
    session = (
        await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == user.id,
                ChatSession.tenant_id == user.tenant_id,
                ChatSession.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(404, "会话不存在或无权访问")
    return session
