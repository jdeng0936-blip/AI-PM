"""T-1201 tests: AI chat sessions and persisted message history."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from importlib import import_module
from typing import Any, AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.middleware.rbac import create_access_token
from app.models import ChatMessage, ChatRole, ChatSession
from app.models.user import User, UserRole
from app.routers import chat as chat_router
from app.routers.chat import MAX_HISTORY_CHARS, MAX_HISTORY_MESSAGES
from tests._db_url import derive_test_database_url

pytestmark = pytest.mark.asyncio

TENANT_ID = "default"
OTHER_TENANT_ID = "phase12_chat_other"
PHASE12_PREFIX = "phase12_chat"
FAKE_ANSWER = "[fake answer] 已收到提问。"
TEST_DATABASE_URL = derive_test_database_url(settings.database_url)


async def _cleanup_phase12_chat_test_data(db_session: AsyncSession) -> None:
    phase12_user_ids = select(User.id).where(User.wechat_userid.like(f"{PHASE12_PREFIX}_%"))
    phase12_session_ids = select(ChatSession.id).where(ChatSession.title.like(f"{PHASE12_PREFIX}_%"))

    await db_session.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(phase12_session_ids)))
    await db_session.execute(delete(ChatSession).where(ChatSession.id.in_(phase12_session_ids)))
    await db_session.execute(delete(User).where(User.id.in_(phase12_user_ids)))
    await db_session.flush()


def _phase12_chat_login_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


async def _phase12_chat_make_admin(
    db_session: AsyncSession,
    *,
    wechat_userid: str,
    tenant_id: str = TENANT_ID,
) -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=wechat_userid,
        name=wechat_userid,
        department="经营管理",
        job_title="管理员",
        role=UserRole.admin,
        is_active=True,
        tenant_id=tenant_id,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


async def _phase12_chat_create_session(
    db_session: AsyncSession,
    *,
    admin: User,
    title: str = "phase12_chat_session",
    message_count: int = 0,
    last_message_at: datetime | None = None,
    tenant_id: str | None = None,
) -> ChatSession:
    session = ChatSession(
        id=uuid.uuid4(),
        user_id=admin.id,
        title=title,
        message_count=message_count,
        last_message_at=last_message_at,
        tenant_id=tenant_id or admin.tenant_id,
        created_by=admin.id,
    )
    db_session.add(session)
    await db_session.flush()
    await db_session.refresh(session)
    return session


async def _phase12_chat_attach_message(
    db_session: AsyncSession,
    *,
    session: ChatSession,
    role: ChatRole,
    content: str,
    created_by: uuid.UUID | None = None,
    created_at: datetime | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    tool_call_id: str | None = None,
) -> ChatMessage:
    message = ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        tenant_id=session.tenant_id,
        created_by=created_by,
    )
    if created_at is not None:
        message.created_at = created_at
    db_session.add(message)
    await db_session.flush()
    await db_session.refresh(message)
    return message


def _phase12_chat_fake_llm(calls: list[list[dict[str, Any]]]):
    async def _fake_call_llm(
        *,
        model_config: dict[str, Any],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        timeout: float = 90.0,
    ) -> dict[str, Any]:
        calls.append([dict(message) for message in messages])
        return {
            "role": "assistant",
            "content": FAKE_ANSWER,
            "tool_calls": None,
        }

    return _fake_call_llm


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        await _cleanup_phase12_chat_test_data(session)
        await session.commit()
        try:
            yield session
        finally:
            await session.rollback()
            await _cleanup_phase12_chat_test_data(session)
            await session.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app = import_module("app.main").app
    test_app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=cast(Any, test_app))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    test_app.dependency_overrides.clear()


async def test_chat_session_create_and_message_count_default_zero(db_session: AsyncSession) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_a")

    session = await _phase12_chat_create_session(db_session, admin=admin, title="phase12_chat_default")

    assert session.message_count == 0
    assert session.last_message_at is None
    assert session.deleted_at is None
    assert session.user_id == admin.id


async def test_chat_message_role_enum_persisted(db_session: AsyncSession) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_b")
    session = await _phase12_chat_create_session(db_session, admin=admin, title="phase12_chat_roles")

    for role in (ChatRole.user, ChatRole.assistant, ChatRole.tool, ChatRole.system):
        await _phase12_chat_attach_message(db_session, session=session, role=role, content=f"{role.value} content")
    await db_session.commit()

    roles = (
        (
            await db_session.execute(
                select(ChatMessage.role).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert set(roles) == {ChatRole.user, ChatRole.assistant, ChatRole.tool, ChatRole.system}


async def test_chat_message_cascade_on_session_delete(db_session: AsyncSession) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_c")
    session = await _phase12_chat_create_session(db_session, admin=admin, title="phase12_chat_cascade")
    await _phase12_chat_attach_message(db_session, session=session, role=ChatRole.user, content="hello")
    await db_session.commit()

    await db_session.execute(delete(ChatSession).where(ChatSession.id == session.id))
    await db_session.commit()

    count = await db_session.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == session.id)
    )
    assert int(count or 0) == 0


async def test_ask_implicitly_creates_session(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_d")
    await db_session.commit()
    calls: list[list[dict[str, Any]]] = []
    monkeypatch.setattr(chat_router, "_call_llm", _phase12_chat_fake_llm(calls))

    response = await client.post(
        "/api/v1/chat/ask",
        headers=_phase12_chat_login_headers(admin),
        json={"question": "phase12_chat 首次提问"},
    )

    assert response.status_code == 200
    body = response.json()
    assert uuid.UUID(body["session_id"])
    assert body["answer"] == FAKE_ANSWER
    session = await db_session.get(ChatSession, uuid.UUID(body["session_id"]))
    assert session is not None
    assert session.title == "phase12_chat 首次提问"
    assert session.message_count == 2
    message_count = await db_session.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == session.id)
    )
    assert int(message_count or 0) == 2


async def test_ask_reuses_session_id_and_loads_history(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_e")
    await db_session.commit()
    calls: list[list[dict[str, Any]]] = []
    monkeypatch.setattr(chat_router, "_call_llm", _phase12_chat_fake_llm(calls))

    first = await client.post(
        "/api/v1/chat/ask",
        headers=_phase12_chat_login_headers(admin),
        json={"question": "phase12_chat 第一轮"},
    )
    session_id = first.json()["session_id"]
    second = await client.post(
        "/api/v1/chat/ask",
        headers=_phase12_chat_login_headers(admin),
        json={"question": "phase12_chat 第二轮", "session_id": session_id},
    )

    assert second.status_code == 200
    assert second.json()["session_id"] == session_id
    sessions_count = await db_session.scalar(select(func.count()).select_from(ChatSession))
    messages_count = await db_session.scalar(
        select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == uuid.UUID(session_id))
    )
    assert int(sessions_count or 0) == 1
    assert int(messages_count or 0) >= 4
    second_payload = calls[-1]
    contents = [m.get("content") for m in second_payload]
    assert "phase12_chat 第一轮" in contents
    assert FAKE_ANSWER in contents
    assert "phase12_chat 第二轮" in contents


async def test_ask_invalid_session_id_returns_404(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_f")
    await db_session.commit()

    response = await client.post(
        "/api/v1/chat/ask",
        headers=_phase12_chat_login_headers(admin),
        json={"question": "phase12_chat invalid", "session_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "会话不存在或无权访问"


async def test_list_sessions_returns_admin_own_only(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin_a = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_g_a")
    admin_b = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_g_b")
    await _phase12_chat_create_session(db_session, admin=admin_a, title="phase12_chat_a_1")
    await _phase12_chat_create_session(db_session, admin=admin_a, title="phase12_chat_a_2")
    await _phase12_chat_create_session(db_session, admin=admin_b, title="phase12_chat_b_1")
    await db_session.commit()

    response = await client.get("/api/v1/chat/sessions", headers=_phase12_chat_login_headers(admin_a))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["title"] for item in body["items"]} == {"phase12_chat_a_1", "phase12_chat_a_2"}


async def test_get_session_detail_returns_messages_in_order(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_h")
    session = await _phase12_chat_create_session(db_session, admin=admin, title="phase12_chat_detail")
    older = datetime.now(timezone.utc) - timedelta(minutes=2)
    newer = datetime.now(timezone.utc) - timedelta(minutes=1)
    await _phase12_chat_attach_message(
        db_session, session=session, role=ChatRole.user, content="first", created_at=older
    )
    await _phase12_chat_attach_message(
        db_session,
        session=session,
        role=ChatRole.assistant,
        content="second",
        created_at=newer,
        tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
    )
    session.message_count = 2
    await db_session.commit()

    response = await client.get(f"/api/v1/chat/sessions/{session.id}", headers=_phase12_chat_login_headers(admin))

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [m["content"] for m in messages] == ["first", "second"]
    assert messages[1]["role"] == "assistant"
    assert messages[1]["tool_calls"][0]["id"] == "call_1"


async def test_rename_session_updates_title(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_i")
    session = await _phase12_chat_create_session(
        db_session,
        admin=admin,
        title="phase12_chat_old_title",
        message_count=3,
    )
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/chat/sessions/{session.id}",
        headers=_phase12_chat_login_headers(admin),
        json={"title": "phase12_chat_new_title"},
    )
    await db_session.refresh(session)

    assert response.status_code == 200
    assert response.json()["title"] == "phase12_chat_new_title"
    assert session.title == "phase12_chat_new_title"
    assert session.message_count == 3


async def test_delete_session_soft_deletes_and_hidden_from_list(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_j")
    session = await _phase12_chat_create_session(db_session, admin=admin, title="phase12_chat_delete")
    await db_session.commit()

    delete_response = await client.delete(
        f"/api/v1/chat/sessions/{session.id}",
        headers=_phase12_chat_login_headers(admin),
    )
    await db_session.refresh(session)
    list_response = await client.get("/api/v1/chat/sessions", headers=_phase12_chat_login_headers(admin))
    detail_response = await client.get(
        f"/api/v1/chat/sessions/{session.id}",
        headers=_phase12_chat_login_headers(admin),
    )

    assert delete_response.status_code == 204
    assert session.deleted_at is not None
    assert list_response.json()["total"] == 0
    assert detail_response.status_code == 404


async def test_list_sessions_search_filters_by_title_ilike(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_k")
    await _phase12_chat_create_session(db_session, admin=admin, title="phase12_chat_采购周报")
    await _phase12_chat_create_session(db_session, admin=admin, title="phase12_chat_项目进度")
    await db_session.commit()

    response = await client.get(
        "/api/v1/chat/sessions?search=采购",
        headers=_phase12_chat_login_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "phase12_chat_采购周报"


async def test_list_sessions_paginated(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_l")
    base_time = datetime.now(timezone.utc)
    for index in range(25):
        await _phase12_chat_create_session(
            db_session,
            admin=admin,
            title=f"phase12_chat_page_{index:02d}",
            last_message_at=base_time - timedelta(minutes=index),
        )
    await db_session.commit()

    response = await client.get(
        "/api/v1/chat/sessions?page=2&page_size=10",
        headers=_phase12_chat_login_headers(admin),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 25
    assert len(body["items"]) == 10


async def test_ask_with_other_user_session_id_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin_a = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_m_a")
    admin_b = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_m_b")
    session = await _phase12_chat_create_session(db_session, admin=admin_a, title="phase12_chat_owner")
    await db_session.commit()

    response = await client.post(
        "/api/v1/chat/ask",
        headers=_phase12_chat_login_headers(admin_b),
        json={"question": "phase12_chat cross user", "session_id": str(session.id)},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "会话不存在或无权访问"


async def test_session_tenant_isolation(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin_a = await _phase12_chat_make_admin(
        db_session,
        wechat_userid="phase12_chat_admin_n_a",
        tenant_id=TENANT_ID,
    )
    admin_b = await _phase12_chat_make_admin(
        db_session,
        wechat_userid="phase12_chat_admin_n_b",
        tenant_id=OTHER_TENANT_ID,
    )
    session = await _phase12_chat_create_session(db_session, admin=admin_a, title="phase12_chat_tenant")
    await db_session.commit()

    list_response = await client.get("/api/v1/chat/sessions", headers=_phase12_chat_login_headers(admin_b))
    detail_response = await client.get(
        f"/api/v1/chat/sessions/{session.id}",
        headers=_phase12_chat_login_headers(admin_b),
    )

    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0
    assert detail_response.status_code == 404


async def test_history_truncated_when_exceeding_max_chars(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _cleanup_phase12_chat_test_data(db_session)
    admin = await _phase12_chat_make_admin(db_session, wechat_userid="phase12_chat_admin_o")
    session = await _phase12_chat_create_session(db_session, admin=admin, title="phase12_chat_long_history")
    base_time = datetime.now(timezone.utc) - timedelta(hours=1)
    for index in range(30):
        await _phase12_chat_attach_message(
            db_session,
            session=session,
            role=ChatRole.user,
            content=f"phase12_chat_long_{index}_" + ("甲" * 1200),
            created_at=base_time + timedelta(seconds=index),
        )
    await db_session.commit()
    calls: list[list[dict[str, Any]]] = []
    monkeypatch.setattr(chat_router, "_call_llm", _phase12_chat_fake_llm(calls))

    response = await client.post(
        "/api/v1/chat/ask",
        headers=_phase12_chat_login_headers(admin),
        json={"question": "phase12_chat 继续", "session_id": str(session.id)},
    )

    assert response.status_code == 200
    sent_messages = calls[-1]
    history_messages = sent_messages[1:-1]
    history_chars = sum(len(str(message.get("content") or "")) for message in history_messages)
    assert len(history_messages) <= MAX_HISTORY_MESSAGES
    assert history_chars <= MAX_HISTORY_CHARS
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[-1]["content"] == "phase12_chat 继续"
