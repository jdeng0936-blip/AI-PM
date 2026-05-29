# T-1201 契约 — Phase 12 第一任:AI 助手多轮对话上下文 + 历史记录持久化

> **指挥官**:Claude(架构师 / Commander) `[2026-05-29 11:58:00]`
> **Worker**:Codex(待接手)
> **基线 commit**:`2243e27 chore(progress): close T-1106`(T-1106 工程完工 chore 落盘后)
> **隶属阶段**:Phase 12(本任为 Phase 12 启动任,先于所有 Phase 11 candidates T-1107/T-1108)
> **预计改动面**:**11 src/test/migration 文件**(后端 6 + 前端 3 + 测试 1 + migration 1),零 T-1104/T-1105/T-1106 文件踩踏
> **测试基线**:T-1106 完工 220 → T-1201 完工预期 `235 passed + 2 skipped`(+15 case)
> **质量闸门基线**:`ruff` PASS / `mypy` PASS / `pytest -q` PASS / `alembic upgrade-downgrade-upgrade` 来回幂等 / frontend `npm run lint && npm run typecheck` PASS
> **Auto Mode 决策签字数**:6(详见 §6)

---

## 1. 任务背景与业务需求

### 1.1 老板原话(`[2026-05-29 11:56:00]`)

> 老板追加新需求(请开启 **Phase 12**):AI 助手需要支持**多轮对话上下文**和**历史记录保存**。
>
> 请基于"**服务端持久化**"方案,在数据库新增 **ChatSession** 和 **ChatMessage** 表,改造 `/api/v1/chat/ask` 接口支持 `session_id` 追问,并增加历史列表查询接口。

### 1.2 当前痛点(从 `backend/app/routers/chat.py` 现状读盘)

`chat.py:166-268` 现状 `admin_ai_chat` 函数:
- **请求体**:`ChatRequest(question, allowed_tools)`,**完全无 session 概念**
- **messages 拼装**(L180-183):每次都从 `SYSTEM_PROMPT + user(question)` 起手,**前一轮对话完全丢失**
- **响应体**(L262-268):`ChatResponse(question, answer, tool_calls, rounds, model)`,**不持久化任何东西**
- **数据库**:`chat.py` 整个文件**未引用 ChatSession / ChatMessage / 任何 ORM 写入**;`db: AsyncSession` 仅传给 `registry.dispatch` 用于 tool 执行(L225)

业务后果:
- 总经理每次提问都是"冷启动",**无法说"刚才那个项目"**(代词指代失效)
- 历史问答**无任何持久化**,会话刷新或换机即丢失,**无法回溯**或**审计**
- 老板视角:把它当"一次性查询",而非"持续对话",大幅降低使用粘性

### 1.3 业务三件套(本任交付范围)

| 编号 | 需求 | 实现路径 | 覆盖范围 |
|---|---|---|---|
| ① | **多轮上下文** | 新增 `ChatSession` + `ChatMessage` 2 表;`ChatRequest.session_id: Optional[UUID]`;`admin_ai_chat` 在 SYSTEM_PROMPT 之后、当前 user question 之前注入历史 messages | 首次 ask 隐式创建 session;复用 session_id 自动加载上下文 |
| ② | **历史列表查询** | 新增 `GET /api/v1/chat/sessions`(分页 + 标题搜索)+ `GET /sessions/{id}`(含 messages) | RBAC = admin,跨 user 隔离,tenant_id 强过滤 |
| ③ | **会话生命周期管理** | 新增 `PATCH /sessions/{id}`(改 title) + `DELETE /sessions/{id}`(软删 set deleted_at) | Append-only message 永不删;session 软删后列表不出现 |

### 1.4 触碰段说明(防 T-1104/T-1105/T-1106 文件踩踏)

| 文件 | T-1104/1105/1106 触碰史 | T-1201 触碰段 | 风险防御 |
|---|---|---|---|
| `backend/app/models/__init__.py` | T-1104 添 `Department`(L12)/ T-1106 添 `ProjectFollowUp`(L42, L68) | **仅插入式追加** `ChatSession` + `ChatMessage` 2 项 import + 2 项 `__all__` | 严禁 重排现有项;严禁 修改 T-1104/1105/1106 添加的行 |
| `backend/app/routers/chat.py` | 未触碰 | **改 admin_ai_chat + 新增 5 端点**(本任 owner) | 不动 SYSTEM_PROMPT 字面量;不动 weekly-report 端点;不动 tools 端点 |
| `frontend/src/api/chat.ts` | 未触碰 | **改 askAI 签名(扩 sessionId)+ 新增 6 函数**(本任 owner) | 不动 triggerWeeklyReport 实现 |
| `frontend/src/app/chat/page.tsx` | 未触碰 | **改 ChatPage 组件**(本任 owner) | 不动子组件 UserBubble / AssistantBubble / ToolTraceList / ToolTraceItem / LoadingBubble / EmptyState 内部 markup |
| `backend/alembic/versions/` | T-1106 加 `20260530_1203_phase11_project_followups.py` | **新建** `20260530_HHMM_phase12_chat_history.py` | down_revision = `e6f7a8b9c0d1`(T-1106 head;Codex 接手时 `alembic heads` 二次核验) |

---

## 2. 严禁项(BLOCKER 红线 — 14 条)

1. ❌ **严禁** 基线 commit 错误。本任基线 = `2243e27 chore(progress): close T-1106`(T-1106 工程完工 chore 落盘 commit)。Codex 接手前必跑探针 `git log --oneline | grep "chore(progress): close T-1106"`,**必须命中**才能开工。
2. ❌ **严禁** 修改 T-1104 5 backend 文件(`backend/alembic/versions/20260529_1037_phase11_user_department_id_fk.py` / `backend/app/models/user.py` / `backend/app/services/_department_resolver.py` / `backend/app/services/department_service.py` / `backend/tests/test_phase11_dept_fk.py`)。FK 双轨迁移期 freeze。
3. ❌ **严禁** 修改 T-1105 8 src 文件(`backend/app/schemas/project.py` / `backend/app/routers/projects.py` / `backend/app/routers/users.py` / `backend/tests/test_phase11_project_members.py` / `frontend/src/api/projects.ts` / `frontend/src/api/users.ts` / `frontend/src/app/projects/page.tsx` / `frontend/src/components/member-picker.tsx`)。
4. ❌ **严禁** 修改 T-1106 11 src/test/migration 文件(`backend/app/models/project_followup.py` / `backend/app/models/project.py`(resolution_summary 字段)/ `backend/app/schemas/project.py`(ProjectFollowUp + ProjectComplete schemas)/ `backend/app/routers/projects.py`(update_project completed 守卫 + followups 2 端点)/ `backend/app/services/health_engine.py` / `backend/tests/test_phase11_followups.py` / `backend/alembic/versions/20260530_1203_phase11_project_followups.py` / `frontend/src/api/projects.ts`(ProjectFollowUp + createFollowup + listFollowups)/ `frontend/src/components/followup-timeline.tsx` / `frontend/src/app/project/[id]/page.tsx`)。
5. ❌ **严禁** 改 `backend/conftest.py` / `backend/tests/_isolation.py` / `backend/tests/_db_url.py`(T-1102/T-1103 已闭环)。
6. ❌ **严禁** 改 `backend/.env*` / `README.md` / `DEPLOY.md`(T-1102 已闭环,本任零配置漂移)。
7. ❌ **严禁** 改 `backend/app/services/llm_selector.py` / `backend/app/services/chat_tools/`(11 文件全冻结)。本任仅消费 `LLMSelector.get_model_for_task("admin_chat")` 已有口径。
8. ❌ **严禁** 改 `backend/app/services/chat_tools/weekly_report.py`(独立 tool,本任零关联)。
9. ❌ **严禁** 改 `backend/app/middleware/rbac.py` / `backend/app/middleware/`(本任仅消费 `require_role(UserRole.admin)` 已有接口)。
10. ❌ **严禁** 改 `backend/app/database.py` / `backend/app/main.py`(router 已 include,无需重新挂)。
11. ❌ **严禁** 改 `backend/pyproject.toml` / `backend/requirements.txt` / `backend/uv.lock` / `frontend/package.json` / `frontend/package-lock.json`(本任零依赖新增 — 复用 `sqlalchemy.dialects.postgresql.JSONB` 已有口)。
12. ❌ **严禁** `git push` / `git stash` / `git rebase` / `git commit --amend` / `--no-verify`。
13. ❌ **严禁** 自启 T-1107 / T-1108 / T-1202 / 其他 Phase 11 backlog 议题。本任**单点闭环**。
14. ❌ **严禁** 改 T-1106 工作区**遗留** 5 项(`frontend/src/app/{change-password,login}/page.tsx` 2 modified + `backend/check_project.py` + `backend/check_users.py` + `backend/reset_admin.py` 3 untracked)。**与 T-1201 无关**,留待用户决策。

---

## 3. 实施方案

### 3.1 数据层

#### 3.1.1 新建 `backend/app/models/chat_session.py`(~85 行)

**职责**:`ChatSession` ORM(BaseMixin + Base),append-only message 由 `ChatMessage` 独立模块承载。

**字面量(对齐 T-1106 `ProjectFollowUp` 体例)**:

```python
"""
app/models/chat_session.py — AI 对话会话(T-1201)

每个 admin 用户的一次对话线程。首次 /api/v1/chat/ask 调用隐式创建,
后续追问携带 session_id 自动加载历史上下文。

设计:
- 软删:deleted_at 标记;DELETE /sessions/{id} 设置该字段
- 计数字段 message_count / last_message_at:routers/chat.py 写入路径维护,
  避免每次列表查询都 JOIN aggregate ChatMessage 表
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class ChatSession(BaseMixin, Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index(
            "ix_chat_sessions_user_active",
            "user_id",
            "last_message_at",
        ),
        Index(
            "ix_chat_sessions_tenant_user_active",
            "tenant_id",
            "user_id",
            "deleted_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="会话归属用户(admin 角色)",
    )

    title: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="会话标题(首次 ask 截取 user.content 前 30 字符)",
    )

    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="本会话累计 message 数(所有 role,含 tool message);维护字段",
    )

    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最后一条 message 落盘时间;用于列表排序",
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="软删时间;非 NULL 表示已删除,列表查询自动过滤",
    )

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id} user={self.user_id} title={self.title!r}>"
```

**关键设计点**:
- **复合索引 `ix_chat_sessions_user_active(user_id, last_message_at)`**:列表查询 `WHERE user_id = ? ORDER BY last_message_at DESC` 的覆盖索引。
- **复合索引 `ix_chat_sessions_tenant_user_active(tenant_id, user_id, deleted_at)`**:RBAC + 跨 tenant + 软删过滤覆盖索引。
- `message_count` + `last_message_at` 为**维护字段**:写入路径(`/ask`)同步 INC + 更新,**严禁** 触发器,严禁 DB-level cascade UPDATE。
- `title` `String(120)` 留缓冲(30 字符 + 未来 LLM 摘要可能扩);comment 锁定首版策略为"前 30 字符"。
- **不加** `relationship("ChatMessage", ...)`:消费侧均显式 `select(ChatMessage).where(session_id=...)`,避免 lazy-load N+1 与 cascade delete 元数据复杂度;cascade 由 DB 层 ON DELETE CASCADE 保证。

#### 3.1.2 新建 `backend/app/models/chat_message.py`(~95 行)

```python
"""
app/models/chat_message.py — AI 对话消息(T-1201)

Append-only message 表。每次 /api/v1/chat/ask 调用会落盘 1 条 user message +
N 条 assistant/tool message(取决于 LLM tool calling 轮数)。

设计:
- role: 严格对齐 OpenAI Chat Completion API 四角(user / assistant / tool / system)
- tool_calls: JSONB nullable;仅 role=assistant 且包含 tool 调用时填充,
  存储 LLM 原始返回的 tool_calls 数组(含 id / function.name / function.arguments)
- tool_call_id: nullable;仅 role=tool 时填充,关联到上一条 assistant tool_calls 的某个 id
- token_count: 预留字段,T-1201 不实现统计(LLM SDK 未返回 usage),保留 nullable
- 复合索引 (session_id, created_at):会话详情按时间序加载
"""

from __future__ import annotations

import enum
import uuid
from typing import Any, Optional

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"
    system = "system"


class ChatMessage(BaseMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index(
            "ix_chat_messages_session_created",
            "session_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="所属会话;session 删除时 CASCADE 删 messages",
    )

    role: Mapped[ChatRole] = mapped_column(
        Enum(ChatRole, name="chat_role", native_enum=True),
        nullable=False,
        comment="消息角色(OpenAI 四角)",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="消息正文;role=assistant 且仅有 tool_calls 时可空字符串",
    )

    tool_calls: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="LLM 返回的 tool_calls 数组(仅 role=assistant 且本轮调用 tool 时填充)",
    )

    tool_call_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="tool 执行结果回填时关联的 tool_call.id(仅 role=tool 时填充)",
    )

    token_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="本条 message 估算 token 数(T-1201 预留,不实现统计)",
    )

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<ChatMessage session={self.session_id} role={self.role.value}>"
```

**关键设计点**:
- **`ChatRole` 枚举**:严格 OpenAI 四角 + `native_enum=True` 走 PG native ENUM 类型(`chat_role`),与既有 `OKRStatus / TaskStatus / SprintStatus` 体例一致。
- **`content` Text + default=""**:assistant 仅返回 tool_calls 时 content 可能为空字符串(LLM SDK 行为),保留**非 NULL** + 空字符串语义。
- **`tool_calls` JSONB**:存原始 LLM 返回结构(数组,每元素含 `id / type / function {name, arguments}`);回放时直接喂回 LLM 不需要二次解析。
- **复合索引 `(session_id, created_at)`**:GET `/sessions/{id}` 详情按时间序加载的覆盖索引。
- **零 `relationship("ChatSession", ...)`**:同 §3.1.1,避免 N+1。

#### 3.1.3 改 `backend/app/models/__init__.py`(+4 行,严格插入式)

**改动锚点(从 T-1106 后状态读盘 L40-44)**:

```python
# --- IPD 项目管理模型 ---
from app.models.project import Project
from app.models.project_followup import ProjectFollowUp
from app.models.project_member import ProjectMember
from app.models.project_stage import ProjectStage
```

**在 `from app.models.project_stage import ProjectStage` 之后追加**(防止与 T-1106 `ProjectFollowUp` 行冲突,**不**改 T-1106 添加的那行):

```python
# --- IPD 项目管理模型 ---
from app.models.project import Project
from app.models.project_followup import ProjectFollowUp
from app.models.project_member import ProjectMember
from app.models.project_stage import ProjectStage

# --- AI 对话历史模型 (Phase 12 T-1201) ---
from app.models.chat_message import ChatMessage, ChatRole
from app.models.chat_session import ChatSession
```

**`__all__` 列表追加(在 `KpiPeriod` 之后,列表尾部)**:

```python
    "KpiTarget",
    "KpiScope",
    "KpiMetric",
    "KpiPeriod",
    "ChatSession",
    "ChatMessage",
    "ChatRole",
]
```

**字面量约束**:
- **不动** 现有 import 行顺序,**不动** 现有 `__all__` 项顺序。
- **不**为 `ChatSession / ChatMessage` 额外建分组段落注释**除上述 1 行**(`# --- AI 对话历史模型 (Phase 12 T-1201) ---`),与 T-1106 体例一致。

#### 3.1.4 新建 Migration `backend/alembic/versions/20260530_HHMM_phase12_chat_history.py`(~145 行)

**`HHMM`** Codex 接手时按系统时间填(例如 `20260530_1430_phase12_chat_history.py`)。

**revision 链定锚**:
- `revision = "f7a8b9c0d1e2"`(本任 head — 12 字符 hex,沿用 T-1104/T-1106 风格)
- `down_revision = "e6f7a8b9c0d1"`(T-1106 head;Codex 接手时探针 `alembic heads` 二次核验,**严禁** 在 `e6f7a8b9c0d1` 未上盘前接手)

**upgrade 字面量**:

```python
"""Phase 12 T-1201: AI 对话历史持久化(ChatSession + ChatMessage + chat_role ENUM)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-30 HH:MM:00

T-1201 多轮对话 + 历史保存:
  - 新建 chat_role PG ENUM 类型(user/assistant/tool/system)
  - 新建 chat_sessions 表 + 3 索引(user_id / 复合 user_active / 复合 tenant_user_active)
  - 新建 chat_messages 表 + 2 索引(session_id / 复合 session_created)
  - 双表 FK ON DELETE CASCADE,session 删除自动清 message
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── 1. chat_role ENUM(条件分支防重复) ────────────────────
    existing_enums = {row[0] for row in bind.execute(sa.text(
        "SELECT typname FROM pg_type WHERE typtype='e'"
    )).fetchall()}
    chat_role_enum = postgresql.ENUM(
        "user", "assistant", "tool", "system",
        name="chat_role",
        create_type=False,
    )
    if "chat_role" not in existing_enums:
        chat_role_enum.create(bind, checkfirst=False)

    # ── 2. chat_sessions 表 ────────────────────────────────────
    if "chat_sessions" not in inspector.get_table_names():
        op.create_table(
            "chat_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=False),
            sa.Column("message_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=64), server_default=sa.text("'default'"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_chat_sessions_user_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_chat_sessions_created_by", ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    session_indexes = set()
    if "chat_sessions" in inspector.get_table_names():
        session_indexes = {idx["name"] for idx in inspector.get_indexes("chat_sessions")}
    if "ix_chat_sessions_user_id" not in session_indexes:
        op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    if "ix_chat_sessions_tenant_id" not in session_indexes:
        op.create_index("ix_chat_sessions_tenant_id", "chat_sessions", ["tenant_id"])
    if "ix_chat_sessions_user_active" not in session_indexes:
        op.create_index("ix_chat_sessions_user_active", "chat_sessions", ["user_id", "last_message_at"])
    if "ix_chat_sessions_tenant_user_active" not in session_indexes:
        op.create_index(
            "ix_chat_sessions_tenant_user_active",
            "chat_sessions",
            ["tenant_id", "user_id", "deleted_at"],
        )

    # ── 3. chat_messages 表 ───────────────────────────────────
    if "chat_messages" not in inspector.get_table_names():
        op.create_table(
            "chat_messages",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "role",
                postgresql.ENUM(name="chat_role", create_type=False),
                nullable=False,
            ),
            sa.Column("content", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("tool_calls", postgresql.JSONB(), nullable=True),
            sa.Column("tool_call_id", sa.String(length=128), nullable=True),
            sa.Column("token_count", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=64), server_default=sa.text("'default'"), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], name="fk_chat_messages_session_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_chat_messages_created_by", ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    message_indexes = set()
    if "chat_messages" in inspector.get_table_names():
        message_indexes = {idx["name"] for idx in inspector.get_indexes("chat_messages")}
    if "ix_chat_messages_session_id" not in message_indexes:
        op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    if "ix_chat_messages_tenant_id" not in message_indexes:
        op.create_index("ix_chat_messages_tenant_id", "chat_messages", ["tenant_id"])
    if "ix_chat_messages_session_created" not in message_indexes:
        op.create_index(
            "ix_chat_messages_session_created",
            "chat_messages",
            ["session_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "chat_messages" in inspector.get_table_names():
        existing = {idx["name"] for idx in inspector.get_indexes("chat_messages")}
        for name in (
            "ix_chat_messages_session_created",
            "ix_chat_messages_tenant_id",
            "ix_chat_messages_session_id",
        ):
            if name in existing:
                op.drop_index(name, table_name="chat_messages")
        op.drop_table("chat_messages")

    if "chat_sessions" in inspector.get_table_names():
        existing = {idx["name"] for idx in inspector.get_indexes("chat_sessions")}
        for name in (
            "ix_chat_sessions_tenant_user_active",
            "ix_chat_sessions_user_active",
            "ix_chat_sessions_tenant_id",
            "ix_chat_sessions_user_id",
        ):
            if name in existing:
                op.drop_index(name, table_name="chat_sessions")
        op.drop_table("chat_sessions")

    existing_enums = {row[0] for row in bind.execute(sa.text(
        "SELECT typname FROM pg_type WHERE typtype='e'"
    )).fetchall()}
    if "chat_role" in existing_enums:
        sa.Enum(name="chat_role").drop(bind, checkfirst=False)
```

**字面量约束**:
- `revision = "f7a8b9c0d1e2"` / `down_revision = "e6f7a8b9c0d1"` 字面量精准对齐(对齐 T-1104 `d4f7a8b9c1e2` + T-1106 `e6f7a8b9c0d1` 风格,12 字符 hex)
- ENUM 名 `chat_role` 与 ORM `Enum(name="chat_role")` 1:1
- 双表 FK 命名 `fk_chat_sessions_user_id / fk_chat_sessions_created_by / fk_chat_messages_session_id / fk_chat_messages_created_by`(对齐 T-1104 `fk_users_department_id_departments` 体例:`fk_<table>_<col>[_<refTable>]`)
- 全表 condition-branch 防重复(对齐 T-1106 migration L29-71 体例),`alembic upgrade-downgrade-upgrade` 可来回幂等
- `users.id` 删除时 `chat_sessions.user_id CASCADE` 会级联清光该用户所有会话(数据合规友好)

### 3.2 Schema 层

#### 3.2.1 新建 `backend/app/schemas/chat_session.py`(~110 行)

```python
"""Pydantic V2 schemas for T-1201 chat session/message API"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.chat_message import ChatRole


class ChatSessionListItem(BaseModel):
    """GET /chat/sessions 列表项(不含 messages)"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionListItem]
    total: int


class ChatMessageOut(BaseModel):
    """单条消息序列化"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: ChatRole
    content: str
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    created_at: datetime


class ChatSessionDetail(BaseModel):
    """GET /chat/sessions/{id} 详情(含完整 messages)"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime
    messages: list[ChatMessageOut]


class ChatSessionUpdate(BaseModel):
    """PATCH /chat/sessions/{id} 改 title"""
    title: str = Field(..., min_length=1, max_length=120)
```

**字面量约束**:
- 全 Pydantic V2(`ConfigDict(from_attributes=True)`,对齐项目体例 `schemas/project.py:L8`)
- `ChatRole` 通过 `from app.models.chat_message import ChatRole` 复用,避免重复定义
- `ChatSessionDetail.messages` 用 `list[ChatMessageOut]`(对齐 V2 体例)
- **零** `ChatSessionCreate` schema:首次会话隐式由 `/ask` 创建,**不**对外暴露 POST `/sessions`

#### 3.2.2 改 `backend/app/routers/chat.py` ChatRequest(+1 行字段)

L68-71 现状:

```python
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    # 可选:限定本次对话只暴露这些 tool(测试/隔离用)
    allowed_tools: Optional[list[str]] = None
```

**改造为**(在 `allowed_tools` 之后追加):

```python
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    # 可选:限定本次对话只暴露这些 tool(测试/隔离用)
    allowed_tools: Optional[list[str]] = None
    # T-1201: 可选;携带则加载该会话历史并追加本轮,缺省则隐式创建新会话
    session_id: Optional[uuid.UUID] = None
```

**新增 ChatResponse 字段**(L81-86 现状之后追加):

```python
class ChatResponse(BaseModel):
    question: str
    answer: str
    tool_calls: list[ToolCallTrace] = []
    rounds: int
    model: str
    session_id: uuid.UUID  # T-1201: 始终返回(隐式/显式 session 统一口径)
```

**imports 块需追加**(L20):`import uuid`(对齐 router 体例使用 `uuid.UUID` 类型)。

### 3.3 Router 改造

#### 3.3.1 改 `backend/app/routers/chat.py` `admin_ai_chat`(~+95 行)

**核心改造点**(L166-268):

1. **入口**(`admin_ai_chat` 函数顶部,L173 question 解包之后):
   - 解析 `req.session_id`
   - **若 session_id 为 None**:创建新 `ChatSession`(`user_id=_user.id, tenant_id=_user.tenant_id, title=question[:30]`)→ `db.add(session); await db.flush()` → 拿到 `session.id`
   - **若 session_id 非 None**:`select(ChatSession).where(id=session_id, user_id=_user.id, tenant_id=_user.tenant_id, deleted_at.is_(None))`,**未命中** → `HTTPException(404, "会话不存在或无权访问")`
   - **加载历史**:`select(ChatMessage).where(session_id=session.id).order_by(created_at).limit(MAX_HISTORY_MESSAGES)`(常量 `MAX_HISTORY_MESSAGES = 20`)
   - **token 预算**:遍历历史 message,累计 content + tool_calls 字符长度;超出 `MAX_HISTORY_CHARS = 20000` 则从最老的丢弃(`while history and total > MAX_HISTORY_CHARS: history.pop(0); recompute`),保留 `SYSTEM_PROMPT` 不动

2. **messages 拼装**(L180-183 改造):
   - `messages = [{"role": "system", "content": SYSTEM_PROMPT}]`
   - 追加 history messages(按 created_at 升序),映射规则:
     - `role=user / assistant / tool / system` → 1:1 透传
     - `tool_calls` 字段(JSONB)若非 NULL → 注入到 assistant message 的 `tool_calls` 字段
     - `tool_call_id` 字段若非 NULL → 注入到 tool message 的 `tool_call_id` 字段
   - 追加本轮 user message:`{"role": "user", "content": question}`

3. **落盘当轮 user message**(`db.flush()` 拿到 session.id 之后立刻):
   - `user_msg = ChatMessage(session_id=session.id, role=ChatRole.user, content=question, tenant_id=_user.tenant_id, created_by=_user.id)` → `db.add(user_msg)`
   - **不 commit**:整个 ask 在单事务中,失败回滚

4. **LLM tool calling 循环内**(L187-243 现有逻辑保留 + 改造):
   - 每轮 `assistant_msg` 拿到后:
     - 若有 `tool_calls`:落盘 `ChatMessage(session_id, role=ChatRole.assistant, content=assistant_msg.get("content") or "", tool_calls=tool_calls)`
     - 若无 `tool_calls`(最终回答):**不在循环内落盘**(等 break 后统一落盘 assistant final)
   - 每条 tool 执行结果:落盘 `ChatMessage(session_id, role=ChatRole.tool, content=json.dumps(result, ...), tool_call_id=tc_id)`

5. **最终 assistant 落盘**(`return ChatResponse(...)` 之前):
   - `final_msg = ChatMessage(session_id=session.id, role=ChatRole.assistant, content=final_answer.strip(), tenant_id=_user.tenant_id, created_by=_user.id)` → `db.add(final_msg)`
   - **session 维护字段更新**:`session.message_count = await scalar(select(func.count(ChatMessage.id)).where(session_id=session.id))`(精确计数,避免漂移)+ `session.last_message_at = func.now()`(server-side now 一致)
   - **触发 commit**:由 FastAPI dependency `get_db` 的事务自动 commit;**严禁** 手动 `await db.commit()`(对齐既有 router 体例 `routers/projects.py:create_project` 未手动 commit)

6. **响应体扩 session_id**:`return ChatResponse(question, answer, tool_calls, rounds, model, session_id=session.id)`

**新增常量(放在 `MAX_TOOL_ROUNDS = 5` 之后,L40-41 附近)**:

```python
MAX_TOOL_ROUNDS = 5
MAX_HISTORY_MESSAGES = 20  # T-1201: 加载历史 message 上限
MAX_HISTORY_CHARS = 20000  # T-1201: 历史 content + tool_calls 字符总长上限
```

**字面量约束**:
- 多轮上下文加载严格"先按 ASC 取 N 条 → token 预算超额则从最老的 pop"
- `session.title` 仅在**新建**时设置一次,**严禁** 后续追问改写 title(用户主动通过 PATCH 改)
- **错误回滚**:LLM 调用失败(L194-196 `HTTPException(502)`)时整个事务回滚 → user message + 部分 tool message 不落盘 → session 也不留(因为 session 是本次 flush 后才有 id;commit 未触发即丢)。**例外**:旧 session 复用情况下 LLM 失败,session 本身已存在 → 仅本次 user message 不落盘
- **零 commit 模式**:全程依赖 fastapi `get_db` dependency 的隐式事务管理(`async with` block)

#### 3.3.2 新增 4 端点(在 `admin_ai_chat` 之后追加)

```python
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
    total = (await db.execute(total_stmt)).scalar_one()
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
    msg_rows = (await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.asc())
    )).scalars().all()
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
    await db.flush()
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
    return None


# ────────────────────────────────────────────────────────────────
# 内部 helper
# ────────────────────────────────────────────────────────────────


async def _load_owned_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user,
) -> "ChatSession":
    """加载会话并校验 RBAC(归属当前 admin + 同 tenant + 未软删);失败 404"""
    session = (await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
            ChatSession.tenant_id == user.tenant_id,
            ChatSession.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if session is None:
        raise HTTPException(404, "会话不存在或无权访问")
    return session
```

**新增 imports 块**(L16-32 现状之后追加):

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models.chat_message import ChatMessage, ChatRole
from app.models.chat_session import ChatSession
from app.schemas.chat_session import (
    ChatMessageOut,
    ChatSessionDetail,
    ChatSessionListItem,
    ChatSessionListResponse,
    ChatSessionUpdate,
)
```

**RBAC**:全 5 端点统一 `_admin_only`(对齐 chat.py 既有体例 L38);**严禁** 引入 manager 角色访问(本任仅 admin 范围)。

### 3.4 前端 API 层

#### 3.4.1 改 `frontend/src/api/chat.ts`(+~50 行)

**改 `ChatResponse`**(L10-16 现状):

```typescript
export interface ChatResponse {
  question: string
  answer: string
  tool_calls: ToolCallTrace[]
  rounds: number
  model: string
  session_id: string         // T-1201: 始终返回
}
```

**改 `askAI`**(L39-41 现状):

```typescript
export async function askAI(
  question: string,
  sessionId?: string,
  allowedTools?: string[],
): Promise<ChatResponse> {
  const payload: Record<string, unknown> = { question }
  if (sessionId) payload.session_id = sessionId
  if (allowedTools && allowedTools.length > 0) payload.allowed_tools = allowedTools
  return request.post<unknown, ChatResponse>('/chat/ask', payload)
}
```

**末尾追加 6 件**:

```typescript
// ──────────────────────────────────────
// T-1201: 会话历史
// ──────────────────────────────────────

export interface ChatSessionListItem {
  id: string
  title: string
  message_count: number
  last_message_at: string | null
  created_at: string
}

export interface ChatSessionListResponse {
  items: ChatSessionListItem[]
  total: number
}

export type ChatRole = 'user' | 'assistant' | 'tool' | 'system'

export interface ChatMessageOut {
  id: string
  role: ChatRole
  content: string
  tool_calls?: Array<Record<string, unknown>> | null
  tool_call_id?: string | null
  created_at: string
}

export interface ChatSessionDetail {
  id: string
  title: string
  message_count: number
  last_message_at: string | null
  created_at: string
  messages: ChatMessageOut[]
}

export async function listChatSessions(params: {
  page?: number
  page_size?: number
  search?: string
} = {}): Promise<ChatSessionListResponse> {
  return request.get<unknown, ChatSessionListResponse>('/chat/sessions', { params })
}

export async function getChatSession(sessionId: string): Promise<ChatSessionDetail> {
  return request.get<unknown, ChatSessionDetail>(`/chat/sessions/${sessionId}`)
}

export async function updateChatSession(
  sessionId: string,
  title: string,
): Promise<ChatSessionListItem> {
  return request.patch<unknown, ChatSessionListItem>(`/chat/sessions/${sessionId}`, { title })
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  return request.delete<unknown, void>(`/chat/sessions/${sessionId}`)
}
```

**字面量约束**:
- `askAI` 签名扩**3 参数**(`question`, `sessionId?`, `allowedTools?`),保持现有 page.tsx `askAI(q)` 调用向后兼容(`sessionId` undefined 时 backend 隐式新建)
- 6 件新增**全在文件末尾**,**严禁** 在 `triggerWeeklyReport` 之间插入

### 3.5 前端 UI 层

#### 3.5.1 改 `frontend/src/app/chat/page.tsx`(~+180 行,改造为左右双栏)

**职责**:左侧加 session 历史侧栏(列表 + 新建按钮 + 改名/删除菜单);右侧保留现有对话区(EmptyState / Bubbles / 输入区);切换 session 时加载完整 message history 反序列化为 `Message[]`。

**改造点清单**:

1. **顶部 imports 块**(L13-18):
   ```typescript
   import {
     askAI,
     triggerWeeklyReport,
     listChatSessions,
     getChatSession,
     updateChatSession,
     deleteChatSession,
     type ChatResponse,
     type ChatSessionListItem,
     type ChatMessageOut,
     type ToolCallTrace,
   } from '@/api/chat'
   ```

2. **新增 lucide-react icons**:`Plus, MessageSquare, MoreHorizontal, Trash2, Pencil`(沿用现有 lucide-react 体例,L20-31 追加,**严禁** 引入新 UI 库)

3. **`ChatPage` 组件新增 state**:
   ```typescript
   const [sessions, setSessions] = useState<ChatSessionListItem[]>([])
   const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
   const [sessionsLoading, setSessionsLoading] = useState(false)
   const [renamingId, setRenamingId] = useState<string | null>(null)
   const [renameDraft, setRenameDraft] = useState('')
   ```

4. **`useEffect` 启动加载会话列表**(L75-77 现状 effect 之后追加):
   ```typescript
   useEffect(() => {
     void refreshSessions()
   }, [])
   ```

5. **新增 helper**(`handleSend` 之前):
   ```typescript
   async function refreshSessions() {
     setSessionsLoading(true)
     try {
       const r = await listChatSessions({ page: 1, page_size: 50 })
       setSessions(r.items)
     } catch {
       toast.error('加载历史会话失败')
     } finally {
       setSessionsLoading(false)
     }
   }

   async function handleSwitchSession(sessionId: string) {
     if (sessionId === activeSessionId) return
     try {
       const detail = await getChatSession(sessionId)
       const restored: Message[] = []
       for (const m of detail.messages) {
         if (m.role === 'user') {
           restored.push({
             role: 'user',
             content: m.content,
             timestamp: formatTime(m.created_at),
           })
         } else if (m.role === 'assistant' && m.content) {
           // tool-call-only 的 assistant 不渲染(只是中间过程),只渲染含最终文本的
           restored.push({
             role: 'ai',
             question: '',
             answer: m.content,
             fullAnswer: m.content,
             toolCalls: [],  // 历史不还原 tool trace(原始 chart 已无 result_preview)
             visibleToolCount: 0,
             rounds: 0,
             model: '',
             done: true,
             timestamp: formatTime(m.created_at),
           })
         }
       }
       setMessages(restored)
       setActiveSessionId(sessionId)
     } catch {
       toast.error('加载会话内容失败')
     }
   }

   function handleNewSession() {
     setMessages([])
     setActiveSessionId(null)
   }

   async function handleDeleteSession(sessionId: string) {
     if (!confirm('确定删除该会话?消息记录将无法找回。')) return
     try {
       await deleteChatSession(sessionId)
       if (activeSessionId === sessionId) handleNewSession()
       await refreshSessions()
       toast.success('已删除')
     } catch {
       toast.error('删除失败')
     }
   }

   async function handleRename(sessionId: string) {
     if (!renameDraft.trim()) {
       setRenamingId(null)
       return
     }
     try {
       await updateChatSession(sessionId, renameDraft.trim())
       setRenamingId(null)
       setRenameDraft('')
       await refreshSessions()
     } catch {
       toast.error('重命名失败')
     }
   }

   function formatTime(iso: string): string {
     return new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
   }
   ```

6. **`handleSend` 改造**(L158-175 现状):
   ```typescript
   async function handleSend(question?: string) {
     const q = (question || input).trim()
     if (!q || loading) return

     const ts = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
     setMessages((prev) => [...prev, { role: 'user', content: q, timestamp: ts }])
     setInput('')
     setLoading(true)

     try {
       const data = await askAI(q, activeSessionId ?? undefined)
       animateAssistantReply(data)
       // T-1201: 首轮隐式创建后,后续追问复用同一 session_id
       if (!activeSessionId) {
         setActiveSessionId(data.session_id)
         await refreshSessions()
       } else {
         // 老 session 更新计数 / 排序
         await refreshSessions()
       }
     } catch (err: any) {
       toast.error(err?.response?.data?.detail || 'AI 回答失败,请稍后重试')
     } finally {
       setLoading(false)
     }
   }
   ```

7. **JSX 改造**(L208-277 整段):
   - 把现有 `<div className="page-container flex flex-col" style={{ height: ... }}>` 改造为 `<div className="page-container flex" style={{ height: ... }}>`
   - 内部分两栏:**左侧** `<aside className="w-64 ...">`(sessions 侧栏)+ **右侧** `<main className="flex-1 flex flex-col">`(原对话区)
   - 左侧子结构:
     - 顶部 `<button onClick={handleNewSession}>` 「+ 新建对话」
     - 滚动列表 `sessions.map((s) => <SessionItem ... />)`
     - 每项点击 `handleSwitchSession(s.id)`
     - hover 时显示 ⋯ 菜单(重命名 / 删除)
     - 重命名:行内 input 替换 title
   - 右侧:**完全保留** 原 EmptyState / Bubbles / 输入区 markup 不改

8. **新增子组件 `SessionItem`**(在 `EmptyState` 之前):
   ```typescript
   function SessionItem({
     session,
     active,
     renaming,
     renameDraft,
     onSwitch,
     onStartRename,
     onChangeRename,
     onFinishRename,
     onDelete,
   }: {
     session: ChatSessionListItem
     active: boolean
     renaming: boolean
     renameDraft: string
     onSwitch: () => void
     onStartRename: () => void
     onChangeRename: (v: string) => void
     onFinishRename: () => void
     onDelete: () => void
   }) {
     // ~50 行 JSX:行容器(active 高亮)+ MessageSquare icon + 标题 / 重命名 input + 右侧 ⋯ 菜单
     // 严格不引入 dropdown 库 — 用最简 hover-reveal 两按钮(Pencil + Trash2)
     ...
   }
   ```

**改造严禁项**:
- ❌ 严禁 改 `UserBubble / AssistantBubble / ToolTraceList / ToolTraceItem / LoadingBubble / EmptyState` 6 个子组件内部 markup
- ❌ 严禁 改 `animateAssistantReply` 函数内部 typewriter 时序(打字机 / tool trace reveal 逻辑保留)
- ❌ 严禁 改 `QUICK_QUESTIONS` 数组、`TYPEWRITER_INTERVAL` / `TOOL_REVEAL_INTERVAL` 常量
- ❌ 严禁 删除 `handleGenerateWeeklyReport`(周报按钮保留可用,新会话也可触发)
- ❌ 严禁 引入新 UI 库(`@radix-ui/react-dropdown-menu` / `shadcn` 等)
- ❌ 严禁 给侧栏加排序 / 多选 / 拖拽功能(留 backlog)

### 3.6 测试

#### 3.6.1 新建 `backend/tests/test_phase12_chat_sessions.py`(~370 行,~15 case)

**测试结构(严格沿用 T-1106 / T-1105 体例)**:

```python
"""T-1201 测试:AI 对话历史(ChatSession + ChatMessage)

Coverage:
  - Model 3 case:CRUD / role enum / cascade delete
  - 主干 6 case:首次 ask 隐式建 session / 复用 session_id 追问 / 上下文加载 / 列表查询 / 详情查询 / 多轮 LLM round trip 落盘
  - RBAC + 隔离 3 case:跨 user 404 / 跨 tenant 404 / 软删后查不到
  - 会话管理 3 case:rename / 软删 / search by title
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient

from app.config import settings
from app.database import Base
from app.models import (
    ChatMessage,
    ChatRole,
    ChatSession,
    User,
    UserRole,
)
from sqlalchemy import select, delete

# 测试隔离 + 作用域 helper
from tests._db_url import derive_test_database_url


_PHASE12_PREFIX = "phase12_chat"
```

**case 命名清单(严格 15 个)**:

| # | 函数名 | 类别 | 验证点 |
|---|---|---|---|
| 1 | `test_chat_session_create_and_message_count_default_zero` | Model | 建 session message_count=0 / last_message_at=NULL / deleted_at=NULL |
| 2 | `test_chat_message_role_enum_persisted` | Model | 4 role 均能落盘读出;ENUM 类型对齐 |
| 3 | `test_chat_message_cascade_on_session_delete` | Model | 物理 DELETE session 时 message CASCADE 清光(非软删测试) |
| 4 | `test_ask_implicitly_creates_session` | 主干 | 首次 POST /ask 无 session_id;响应含 session_id;DB 新建 session + 2 message(user + assistant) |
| 5 | `test_ask_reuses_session_id_and_loads_history` | 主干 | 第 1 次 ask 建 session;第 2 次 ask 带 session_id;DB session 只 1 条;message ≥ 4;LLM call 拼装的 messages 包含历史 user + assistant(mocked 验证) |
| 6 | `test_ask_invalid_session_id_returns_404` | 主干 | 携带不存在的 session_id → 404 "会话不存在或无权访问" |
| 7 | `test_list_sessions_returns_admin_own_only` | 主干 + RBAC | admin A 建 2 session / admin B 建 1 session;A 调 GET /sessions → 仅返回 2 条 |
| 8 | `test_get_session_detail_returns_messages_in_order` | 主干 | 详情 messages 按 created_at ASC;含 role + content + tool_calls fields |
| 9 | `test_rename_session_updates_title` | 会话管理 | PATCH /sessions/{id} → title 改;message_count 不变 |
| 10 | `test_delete_session_soft_deletes_and_hidden_from_list` | 会话管理 | DELETE /sessions/{id} → deleted_at 非 NULL;列表不再含;详情仍 404 |
| 11 | `test_list_sessions_search_filters_by_title_ilike` | 会话管理 | 建标题 "采购周报" / "项目进度",search="采购" → 仅 1 条 |
| 12 | `test_list_sessions_paginated` | 会话管理 | 建 25 条;page=2 page_size=10 → 返回 10 条;total=25 |
| 13 | `test_ask_with_other_user_session_id_returns_404` | RBAC | admin A 建 session;admin B 携带 A 的 session_id → 404 |
| 14 | `test_session_tenant_isolation` | RBAC | tenant=t1 建 session;tenant=t2 admin 列表 → 0 条;详情 404 |
| 15 | `test_history_truncated_when_exceeding_max_chars` | 主干 | 注入 30 条 message + 极长 content;ask 时 messages 拼装最多 MAX_HISTORY_MESSAGES + 字符总长 ≤ MAX_HISTORY_CHARS + 5000 上限(给 system + question 留 token) |

**测试基础设施(严格沿用)**:
- consume `db_session + client` fixture(conftest.py 已有)
- consume `_isolation_external_settings` autouse fixture(T-1102 / T-1103 已有)
- 每 case 入口跑 `_cleanup_phase12_chat_test_data(db_session)` helper:`DELETE FROM chat_messages WHERE session_id IN (SELECT id FROM chat_sessions WHERE title LIKE 'phase12_chat_%')` + `DELETE FROM chat_sessions WHERE title LIKE 'phase12_chat_%'` + `DELETE FROM users WHERE wechat_userid LIKE 'phase12_chat_%'`
- 私有 helpers `_phase12_chat_*` 前缀:`_phase12_chat_make_admin` / `_phase12_chat_login_headers` / `_phase12_chat_create_session` / `_phase12_chat_attach_message`
- 作用域闸门:**全部** test data 命名以 `phase12_chat_` 起手,**严禁** 污染其他测试
- LLM mock:`monkeypatch.setattr("app.routers.chat._call_llm", _fake_call_llm)`(mock 该模块级 async helper,**仅 _call_llm,不 mock ORM**)

**LLM mock 编排(case 4-5-8-15 共用)**:

```python
async def _fake_call_llm(*, model_config, messages, tools, timeout=90.0):
    """模拟 LLM 不调用 tool,直接返回最终答案。
    case 5 验证 history 加载:assert 任一历史 user 在 messages 中。
    """
    return {
        "role": "assistant",
        "content": "[mocked answer] 已收到提问。",
        "tool_calls": None,
    }
```

**严禁项**:
- 零 mock ORM(仅 mock `_call_llm` LLM HTTP 调用)
- 零 monkeypatch DB session
- 零 print / logger / skip / xfail
- 零 真实 LLM 网络调用(`new_api_base_url` 不会被命中)

#### 3.6.2 测试基线对齐

| 阶段 | 全套 pytest 期望 |
|---|---|
| T-1106 完工(基线) | `220 passed + 2 skipped` |
| T-1201 完工(预期) | `235 passed + 2 skipped`(+15 case) |

**回归承诺**:**零** existing test 减分。

### 3.7 main.py / router 挂载

**零改动**:`backend/app/main.py:159` 已 `from app.routers import chat`,L162 已 `app.include_router(chat.router)`。本任**仅扩 chat router 内部端点**,挂载层完全不动。

### 3.8 LLMSelector / chat_tools 接口

**零改动**:本任仅消费 `LLMSelector.get_model_for_task("admin_chat")`(`chat.py:174` 已有调用)+ `registry.openai_schemas / registry.dispatch`(`chat.py:176, 225` 已有调用)。**严禁** 改 `llm_selector.py` 或 `chat_tools/` 任何文件。

### 3.9 fail-safe self-check(Codex 接手前必跑 8 项 grep 闸门)

在 chore(lock) 之后、首次 Edit 之前,Codex 必跑以下 8 条探针,**任何一条失败立即 stop and ask**:

```bash
# 1. 基线锁定
git log --oneline -5 | head -1 | grep -F "chore(progress): close T-1106"

# 2. T-1106 migration 已存在
test -f backend/alembic/versions/20260530_1203_phase11_project_followups.py

# 3. T-1104 5 文件零改动确认
git diff 2243e27..HEAD -- \
  backend/alembic/versions/20260529_1037_phase11_user_department_id_fk.py \
  backend/app/models/user.py \
  backend/app/services/_department_resolver.py \
  backend/app/services/department_service.py \
  backend/tests/test_phase11_dept_fk.py | wc -l   # 期望 0

# 4. T-1105 8 文件零改动确认
git diff 2243e27..HEAD -- \
  backend/tests/test_phase11_project_members.py \
  frontend/src/api/users.ts \
  frontend/src/app/projects/page.tsx \
  frontend/src/components/member-picker.tsx | wc -l   # 期望 0(picker test/users.ts/projects page/member-picker)

# 5. T-1106 10 文件零改动确认
git diff 2243e27..HEAD -- \
  backend/app/models/project_followup.py \
  backend/app/services/health_engine.py \
  backend/tests/test_phase11_followups.py \
  backend/alembic/versions/20260530_1203_phase11_project_followups.py \
  frontend/src/components/followup-timeline.tsx \
  frontend/src/app/project/\[id\]/page.tsx | wc -l   # 期望 0

# 6. conftest / _isolation / _db_url / .env / README / DEPLOY 零改动
git diff 2243e27..HEAD -- \
  backend/conftest.py \
  backend/tests/_isolation.py \
  backend/tests/_db_url.py \
  backend/.env.example \
  README.md DEPLOY.md | wc -l   # 期望 0

# 7. 工作区遗留 5 项未污染(modified 仍是 2 项 + untracked 仍是 3 项)
git status --short | grep -E '^( M|\?\?)' | wc -l   # 期望 5

# 8. alembic heads 单头确认
cd backend && alembic heads | wc -l   # 期望 1(预期内容含 e6f7a8b9c0d1)
```

---

## 4. 测试基线 + 闸门

| 闸门 | 命令 | 期望 |
|---|---|---|
| ruff(后端) | `cd backend && ruff check app/routers/chat.py app/models/chat_session.py app/models/chat_message.py app/schemas/chat_session.py alembic/versions/20260530_*_phase12_chat_history.py tests/test_phase12_chat_sessions.py` | All passed |
| mypy(后端) | `cd backend && mypy app/routers/chat.py app/models/chat_session.py app/models/chat_message.py app/schemas/chat_session.py` | 0 error |
| Alembic upgrade-downgrade-upgrade | `cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head` | 无 error / 重复 upgrade 幂等 |
| 新测试 | `cd backend && pytest tests/test_phase12_chat_sessions.py -v` | `15 passed` |
| 全量 pytest | `cd backend && pytest -q` | `235 passed + 2 skipped` |
| frontend lint | `cd frontend && npm run lint` | 0 error |
| frontend typecheck | `cd frontend && npm run typecheck` | 0 error |
| `alembic check` | (沿用 T-1101/T-1102/T-1103 Supervisor 特批跳过 local DB drift 误报) | — |

**新测试 + 全量回归基线零回归**:T-1106 完工 `220 passed + 2 skipped` → T-1201 完工 `235 passed + 2 skipped`(+15 case 全 PASS)。

---

## 5. 改动面文件清单(11 文件 + 4 边界冻结)

### 5.1 11 文件改动面

| # | 文件 | 类型 | 行数预算 | 改动方式 |
|---|---|---|---|---|
| 1 | `backend/app/models/chat_session.py` | 新建 | ~85 | Write |
| 2 | `backend/app/models/chat_message.py` | 新建 | ~95 | Write |
| 3 | `backend/app/models/__init__.py` | 改 | +4 | Edit(2 import + 3 __all__) |
| 4 | `backend/alembic/versions/20260530_HHMM_phase12_chat_history.py` | 新建 | ~145 | Write |
| 5 | `backend/app/schemas/chat_session.py` | 新建 | ~110 | Write |
| 6 | `backend/app/routers/chat.py` | 改 | +~150 | Edit(import block + ChatRequest/Response 字段 + admin_ai_chat 改造 + 5 新端点 + 1 helper) |
| 7 | `backend/tests/test_phase12_chat_sessions.py` | 新建 | ~370 | Write |
| 8 | `frontend/src/api/chat.ts` | 改 | +~70 | Edit(ChatResponse + askAI 签名 + 4 interface + 4 函数) |
| 9 | `frontend/src/app/chat/page.tsx` | 改 | +~180 | Edit(imports + state + helpers + handleSend 改造 + JSX 左右分栏 + SessionItem 子组件) |

(**注**:严格 9 个,§3.5 罗列的 imports + state + helper + JSX 改造 + SessionItem 都在 `chat/page.tsx` 同一个文件中,**不另立子组件文件**;旧版"11 文件"的预算口径中 SessionItem 拆文件被收口为内联子组件以减少改动面)

### 5.2 4 边界冻结面(grep 闸门必须返回 0)

```bash
# 边界 ①:T-1104/T-1105/T-1106 全部锁定文件
git diff 2243e27..HEAD -- \
  backend/alembic/versions/20260529_1037_phase11_user_department_id_fk.py \
  backend/app/models/user.py \
  backend/app/services/_department_resolver.py \
  backend/app/services/department_service.py \
  backend/tests/test_phase11_dept_fk.py \
  backend/app/schemas/project.py \
  backend/app/routers/projects.py \
  backend/app/routers/users.py \
  backend/tests/test_phase11_project_members.py \
  frontend/src/api/projects.ts \
  frontend/src/api/users.ts \
  frontend/src/app/projects/page.tsx \
  frontend/src/components/member-picker.tsx \
  backend/app/models/project_followup.py \
  backend/app/models/project.py \
  backend/app/services/health_engine.py \
  backend/tests/test_phase11_followups.py \
  backend/alembic/versions/20260530_1203_phase11_project_followups.py \
  frontend/src/components/followup-timeline.tsx \
  frontend/src/app/project/\[id\]/page.tsx | wc -l   # 期望 0

# 边界 ②:配置/测试基础设施全冻结
git diff 2243e27..HEAD -- \
  backend/conftest.py \
  backend/tests/_isolation.py \
  backend/tests/_db_url.py \
  backend/.env.example \
  README.md DEPLOY.md \
  backend/pyproject.toml backend/requirements.txt backend/uv.lock \
  frontend/package.json frontend/package-lock.json | wc -l   # 期望 0

# 边界 ③:LLM / chat_tools / 周报 全冻结
git diff 2243e27..HEAD -- \
  backend/app/services/llm_selector.py \
  backend/app/services/chat_tools/ | wc -l   # 期望 0

# 边界 ④:其他无关页 / 中间件 / main / database
git diff 2243e27..HEAD -- \
  backend/app/main.py \
  backend/app/database.py \
  backend/app/middleware/ \
  frontend/src/app/dashboard \
  frontend/src/app/admin \
  frontend/src/app/users \
  frontend/src/app/project \
  frontend/src/app/login \
  frontend/src/app/change-password \
  frontend/src/components/sidebar.tsx | wc -l   # 期望 0(注:T-1106 工作区 modified 的 login + change-password 不归本任管,本探针在 stash 后跑或视为 spec-time baseline)
```

**注**:由于工作区有 2 项 modified(login / change-password)与 T-1201 无关,Codex 接手时**不**纳入 staged,**不**额外覆盖。

---

## 6. 6 决策签字(指挥官 Auto Mode `[2026-05-29 11:58:30]`)

| # | 决策 | 选项 | 签字 | 理由 |
|---|---|---|---|---|
| 1 | 数据层结构 | (A) 2 表 ChatSession + ChatMessage 独立 module / (B) 单表 ChatMessage 由 session_id self-ref / (C) 混合 JSONB messages 数组 | **A** | append-only message 独立扩展(token 统计 / 检索 / 审计)空间大;sessions 列表查询零 JOIN |
| 2 | session 创建策略 | (A) 隐式由首次 /ask 创建 / (B) 显式 POST /sessions / (C) 双口可选 | **A** | 用户心智简单 — 直接提问即可;无空 session 垃圾数据;POST 端口可留 backlog T-1202 |
| 3 | role enum 严格度 | (A) 严格 OpenAI 四角 / (B) 加 ChatRole.error 容错 | **A** | 严格对齐 OpenAI Chat Completion API 复用 LLM 端契约,error 走 tool message 含 error 字段更标准 |
| 4 | 历史加载上限 | (A) `MAX_HISTORY_MESSAGES=20 + MAX_HISTORY_CHARS=20000` 双闸 / (B) 仅消息数 / (C) 仅字符 / (D) 仅 token | **A** | 双闸防 LLM context overflow;字符闸门粗略对齐 token 预算(中文约 1.5 char/token);token 闸门留 backlog |
| 5 | title 生成 | (A) 截首条 user.content 前 30 字符 / (B) LLM 摘要 / (C) 用户首次手填 | **A** | T-1201 简化 first-cut;LLM 摘要留 backlog T-1202(消耗额外 token);手填增加首次交互摩擦 |
| 6 | 删除策略 | (A) Session 软删 + Message append-only / (B) 双表硬删 / (C) Session 硬删 cascade Message | **A** | 软删保留审计回溯能力;后续可加 admin 端"已删除"列表 + 恢复;Message append-only 与 T-1106 ProjectFollowUp 体例一致 |

---

## 7. Commit 计划(3 commit 闭环)

### 7.1 chore(lock) — T-1201 开工 lock

```
chore(lock): T-1201 开工 — Phase 12 第一任 AI 多轮对话 + 历史持久化

Worker timestamp: [2026-05-30 HH:MM:SS]
```

**改动**:仅 `docs/dev_tasks.md` Task 7 状态 `[ ]` → `[/] In Progress by Codex`,1 行变更。

### 7.2 feat — 工程主提交

```
feat(chat): T-1201 AI 多轮对话上下文 + 历史持久化

后端:
- 新建 ChatSession + ChatMessage 模型(BaseMixin + JSONB tool_calls + chat_role ENUM)
- 新建 alembic 迁移 phase12_chat_history(double-table + 5 indexes + ENUM)
- 新建 schemas/chat_session(ChatSessionListItem/Response/Detail/Update + ChatMessageOut)
- 改 routers/chat.py:
  * ChatRequest 扩 session_id; ChatResponse 扩 session_id
  * admin_ai_chat 首次隐式建 session;复用时加载 ≤20 message 历史(MAX_HISTORY_CHARS=20000 闸门)
  * 每轮 LLM 调用 + tool 执行结果均落盘 ChatMessage
  * 新增 GET/PATCH/DELETE /chat/sessions 端点(分页 + ilike 搜索 + 软删)

前端:
- 改 api/chat.ts:askAI 扩 sessionId 参数 + 4 件 sessions API + ChatSessionListItem / Detail
- 改 app/chat/page.tsx:左右分栏(侧栏 sessions 列表 + 新建/重命名/删除 + 切换加载 history)

测试:
- 新建 tests/test_phase12_chat_sessions.py 15 case(Model 3 + 主干 6 + RBAC 3 + 会话管理 3)

零回归:
- T-1104/T-1105/T-1106 全部锁定文件零改动
- conftest/_isolation/_db_url/.env/README/DEPLOY/llm_selector/chat_tools 零改动
- 测试基线 220 → 235 passed + 2 skipped

Worker timestamp: [2026-05-30 HH:MM:SS]
```

### 7.3 chore(progress) — 完工 chore + 看板状态更新

```
chore(progress): close T-1201 — Phase 12 第一任 AI 对话历史持久化完工

工程完工实绩:
- 9 文件改动面严格(2 新建 model + 1 改 __init__ + 1 新建 migration + 1 新建 schema + 1 改 router + 1 新建 test + 1 改 api + 1 改 page)
- 15 case 全 PASS / 全量 235 passed + 2 skipped / ruff + mypy + frontend lint/typecheck 全绿
- alembic upgrade-downgrade-upgrade 来回幂等(ENUM + 双表 + 5 index)

严禁项遵守证据:0 T-1104 / 0 T-1105 / 0 T-1106 / 0 conftest / 0 _isolation / 0 _db_url / 0 .env / 0 README / 0 DEPLOY / 0 llm_selector / 0 chat_tools / 0 push / 0 amend / 0 rebase / 0 --no-verify / 0 自启 T-1202

Worker timestamp: [2026-05-30 HH:MM:SS]
```

**改动**:仅 `docs/dev_tasks.md` Task 7 状态 `[/] In Progress` → `[x] Done by Codex [HH:MM:SS]` + 完工实绩段落填充。

---

## 8. 验收清单(指挥官二次验收 28 项)

### 8.1 改动面闸门(8 项)

- ㉑ 从 `2243e27` 出发严格 3 commit 链路干净(`chore(lock)` → `feat(chat)` → `chore(progress)`)
- ㉒ feat commit 严格 9 文件(对齐 §5.1 文件清单)
- ㉓ chore(lock) + chore(progress) 各严格 1 文件 `docs/dev_tasks.md`
- ㉔ §5.2 边界 ① 4 块 grep 闸门**完全空**
- ㉕ §3.9 self-check 8 项探针 Codex 接手前**全 PASS**
- ㉖ Worker timestamp 三 commit 均带 `[YYYY-MM-DD HH:MM:SS]`
- ㉗ chore commit body 含完工概要 + 文件清单 + 严禁项遵守证据(对齐 T-1106 chore 风格)
- ㉘ 工作区遗留 5 项保留未污染(2 modified + 3 untracked 与 T-1201 无关)

### 8.2 Migration 闸门(5 项)

- ㉙ 命名 `20260530_HHMM_phase12_chat_history.py`(HHMM=Codex 接手填)
- ㉚ `revision = "f7a8b9c0d1e2"` + `down_revision = "e6f7a8b9c0d1"`(T-1106 head 字面量精准对齐)
- ㉛ upgrade() 字面量全对齐 §3.1.4:`chat_role` ENUM + chat_sessions 表 + chat_messages 表 + 5 索引 + 4 FK 命名
- ㉜ downgrade() 反向完整:`drop chat_messages + 3 indexes → drop chat_sessions + 4 indexes → drop chat_role ENUM`
- ㉝ `alembic upgrade head → downgrade -1 → upgrade head` 来回幂等(condition branch 防重)

### 8.3 Model + Schema + Router 闸门(8 项)

- ㉞ `ChatSession` 字面量对齐 §3.1.1:`title String(120) + message_count Integer default=0 + last_message_at + deleted_at + 2 复合 index`
- ㉟ `ChatMessage` 字面量对齐 §3.1.2:`role Enum native_enum=True + content Text default="" + tool_calls JSONB + tool_call_id String(128) + token_count Integer nullable + 复合 index`
- ㊱ `__init__.py` 严格插入式 +4 行(2 import + 3 __all__),零现有顺序重排
- ㊲ `schemas/chat_session.py` 5 schemas 字面量对齐 §3.2.1 + Pydantic V2 + `from_attributes=True`
- ㊳ `ChatRequest.session_id: Optional[uuid.UUID] = None` 字段精准追加;`ChatResponse.session_id: uuid.UUID` 字段精准追加
- ㊴ `admin_ai_chat` 改造点 6 类齐全:入口建/校验 session + 历史加载双闸 + user msg 落盘 + tool round 落盘 + 最终 assistant 落盘 + session 维护字段
- ㊵ 4 新增端点 RBAC = `_admin_only` + 跨 user/tenant 隔离 + 软删过滤 + 分页 + ilike search 字面量全对齐 §3.3.2
- ㊶ `_load_owned_session` helper 字面量对齐 §3.3.2 `(user_id == user.id, tenant_id == user.tenant_id, deleted_at.is_(None))`

### 8.4 前端闸门(3 项)

- ㊷ `api/chat.ts` 字面量对齐 §3.4.1:`ChatResponse.session_id` 扩 + `askAI(question, sessionId?, allowedTools?)` 签名 + 4 interface + 4 函数全在文件末尾
- ㊸ `app/chat/page.tsx` 改造点 7 类齐全:imports + 5 state + 5 helper + handleSend 改造 + JSX 左右分栏 + SessionItem 内联子组件 + 6 现有子组件零改动
- ㊹ 严禁项遵守:零引入新 UI 库 / 零改 animateAssistantReply / 零改 QUICK_QUESTIONS / 零删 handleGenerateWeeklyReport

### 8.5 测试闸门(3 项)

- ㊺ `test_phase12_chat_sessions.py` 15 case 命名 100% 对齐 §3.6.1 字面量(`grep -c "^async def test_" = 15`)
- ㊻ 4 类 case 分布严格:Model 3 + 主干 6 + RBAC 3 + 会话管理 3 = 15
- ㊼ 测试零 mock ORM / 零 monkeypatch DB / 零 print / 零 logger / 零 skip / 零真实 LLM 网络(grep 严禁字 0 hit);仅 mock `_call_llm` LLM helper

### 8.6 综合质量闸门(1 项)

- ㊽ `pytest -q` 全量 `235 passed + 2 skipped` + `ruff` + `mypy` + `alembic` + frontend `npm run lint && npm run typecheck` 全绿

**合计 28 项**(8 + 5 + 8 + 3 + 3 + 1 = 28)。

---

## 9. 风险与 follow-up

### 9.1 风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 历史加载双闸门 20 msg + 20000 chars 触发 LLM context truncate 不够智能 | 中 | 中(老对话掉 context) | T-1202 backlog:接入精确 tokenizer(`tiktoken`)或 LLM summarize 旧消息 |
| JSONB tool_calls 反序列化失败(LLM SDK 改返回 schema) | 低 | 高(detail 端点 500) | 落盘前 `json.dumps + json.loads round-trip` 校验;读盘时 try/except 容错 |
| ENUM `chat_role` 新增值时需 migration | 低 | 中 | T-1201 不引入第五种 role;T-1202 若加 `summary` role 需新 migration `ALTER TYPE chat_role ADD VALUE 'summary'` |
| 高并发同会话同时 ask 导致 message_count 漂移 | 低 | 低 | T-1201 维护字段用 `SELECT count(*)` 精确写,而非 `INC`,牺牲一点 perf 换正确性 |
| user 表 CASCADE 删除时 chat 数据连带清除 | 中 | 中(合规) | 注释明示;后续如要做"用户离职但对话留存"backlog 改 ON DELETE SET NULL + user_id nullable |

### 9.2 backlog(明确不归本任)

- **T-1202 候选**:LLM-based title 摘要(替代前 30 字符截取)+ tiktoken 精确 token 预算 + summary role 压缩老消息
- **T-1203 候选**:对话出口(支持 Markdown / JSON 导出)+ 全局搜索(跨 sessions content ilike)+ 分享只读 link(临时 token)
- **T-1204 候选**:对话评分 / 反馈(踩 / 赞)+ admin 分析看板(高频问题 / 热门 tool)
- **T-1107 / T-1108**(原 Phase 11 backlog):FK 第二阶段切剩余读路径 + drop column 老路径

### 9.3 与 Phase 11 backlog 关系

T-1201 = **Phase 12 启动任**(纯新增 + 后端独立模块 + 前端纯增量页改造),与 Phase 11 backlog(T-1107/T-1108 FK 双轨完工)**正交无依赖**;两条线可并行规划,但 T-1107/T-1108 仍按指挥官放牌节奏推进,本任**不**绑定它们。

---

## 10. 关键决策记录

### 10.1 为什么不暴露 `POST /chat/sessions`(显式建空 session)

- 用户心智:聊天产品(ChatGPT / Claude / 通义)统一都是"直接发问即建会话",空 session 是无意义垃圾数据
- 工程简化:少一个端点 + 少一类 schema + 减少状态机分支
- 后续可补:如真有 backlog 需求(批量预创建 / 测试隔离),T-1202 加 `POST /chat/sessions` 单独端点

### 10.2 为什么 `MAX_HISTORY_MESSAGES = 20` + `MAX_HISTORY_CHARS = 20000`

- 实测数据假设:平均一次问答 user + assistant + 0~3 tool message ≈ 4 message;20 msg ≈ 5 个完整问答(含 tool 调用)轮次
- 字符闸门:中文约 1.5 char/token,20000 chars ≈ 13000 tokens,加上 SYSTEM_PROMPT(~500 tokens)+ 当前 question(~100 tokens)+ tool schema(~1500 tokens)+ 输出预算(2048 tokens),总计 ~17000 tokens,留 buffer 给主流模型 32k 上下文
- 双闸:消息数闸门防"碎片化短消息撑爆"; 字符闸门防"个别长 tool result 占满 context"

### 10.3 为什么 ChatRole 用 `native_enum=True` + PG ENUM 类型

- 与 `OKRStatus / TaskStatus / SprintStatus` 项目体例一致(`models/okr.py` / `models/sprint*.py` 已有 PG ENUM)
- 类型安全:DB 层强制 4 角,防止脏 string 落盘
- 索引友好:ENUM 在 PG 中是 4-byte int,比 string 更快

### 10.4 为什么 `tool_calls` 用 JSONB 而非关联子表

- JSONB 在 PG 中支持高效索引(GIN)+ JSON path 查询
- LLM 返回 tool_calls 结构是数组,自然 JSON 表达
- 子表化收益不显著:tool_calls 几乎不用作查询过滤条件(仅展示)
- 后续真要做 tool 调用聚合分析(如"本月最常用 tool")可加物化视图,不需要拆子表

### 10.5 为什么 sessions 列表用 `(user_id, last_message_at, deleted_at)` 复合索引

- 主查询 pattern:`WHERE user_id = ? AND tenant_id = ? AND deleted_at IS NULL ORDER BY last_message_at DESC`
- 索引覆盖:`(user_id, last_message_at)` 主走 user;`(tenant_id, user_id, deleted_at)` 兼顾跨 tenant + 软删过滤
- 不合一索引:tenant_id 选择性低(单租户),把它放主索引头会浪费 B+ tree 节点

### 10.6 为什么 T-1106 工作区遗留(login / change-password / debug 脚本)留给用户决策

- 遵守 CLAUDE.md 第 4 条:严禁盲目回滚 / 删除未知改动
- 已使用 `git blame` 等溯源动作判断这些为 `ericdv111` 远端 fix 残留或本机调试,与 T-1201 业务无关
- 不纳入本任 commit 既避免污染 chore(spec) 边界,也避免主观覆盖用户实际工作

---

## 📣 附录:给 Worker(Codex)的物理交接单

> **更新时间戳**:`[2026-05-29 11:58:30]`(指挥官 Claude 起草完工)
>
> **接手前置守卫**(Codex 必跑 8 项探针,见 §3.9):
> 1. `git log --oneline -5 | head -1 | grep -F "chore(progress): close T-1106"` 必须命中
> 2. `test -f backend/alembic/versions/20260530_1203_phase11_project_followups.py` 必须存在
> 3. T-1104 5 文件零改动(§3.9 第 3 条 grep wc = 0)
> 4. T-1105 4 关键文件零改动(§3.9 第 4 条 grep wc = 0)
> 5. T-1106 6 关键文件零改动(§3.9 第 5 条 grep wc = 0)
> 6. `conftest / _isolation / _db_url / .env / README / DEPLOY` 零改动
> 7. 工作区遗留仍是 5 项(`git status --short | wc -l = 5`)
> 8. `cd backend && alembic heads | wc -l = 1`(预期 `e6f7a8b9c0d1`)
>
> **8 步执行指令**(严格顺序):
>
> **Step 1 — chore(lock) 落盘**:
> ```bash
> # 编辑 docs/dev_tasks.md:Task 7 (T-1201) [ ] → [/] In Progress by Codex
> git add docs/dev_tasks.md
> git commit -m "$(cat <<'EOF'
> chore(lock): T-1201 开工 — Phase 12 第一任 AI 多轮对话 + 历史持久化
>
> Worker timestamp: [YYYY-MM-DD HH:MM:SS]
>
> Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
> EOF
> )"
> ```
>
> **Step 2 — 数据层落盘**:严格按 §3.1.1 / §3.1.2 字面量 Write 2 个新 model 文件;严格按 §3.1.3 字面量 Edit `models/__init__.py`(+4 行 插入式);严格按 §3.1.4 字面量 Write 新 migration 文件(`HHMM` 填当前系统时间)。
>
> **Step 3 — Schema 落盘**:严格按 §3.2.1 字面量 Write `schemas/chat_session.py`(5 schemas Pydantic V2);严格按 §3.2.2 字面量 Edit `routers/chat.py` ChatRequest + ChatResponse(+2 字段)。
>
> **Step 4 — Router 改造**:严格按 §3.3.1 字面量改造 `admin_ai_chat`(6 改造点齐全);严格按 §3.3.2 字面量追加 4 端点 + 1 helper;严格按 §3.3.2 末尾追加 imports 块。
>
> **Step 5 — 前端**:严格按 §3.4.1 字面量 Edit `api/chat.ts`(改 ChatResponse + askAI 签名 + 末尾追加 4 interface + 4 函数);严格按 §3.5.1 字面量 Edit `app/chat/page.tsx`(imports + state + 5 helper + handleSend + JSX 左右分栏 + SessionItem 内联);**严禁** 改 6 个现有子组件内部 markup。
>
> **Step 6 — 测试落盘**:严格按 §3.6.1 字面量 Write `test_phase12_chat_sessions.py`(15 case,4 类分布严格);LLM mock 仅替换 `_call_llm` 模块级 helper;每 case 入口跑 `_cleanup_phase12_chat_test_data` helper;作用域 `phase12_chat_` 前缀严格。
>
> **Step 7 — 质量闸门 8 条**(全绿才能 commit feat):
> ```bash
> cd backend
> ruff check app/routers/chat.py app/models/chat_session.py app/models/chat_message.py app/schemas/chat_session.py alembic/versions/20260530_*_phase12_chat_history.py tests/test_phase12_chat_sessions.py
> mypy app/routers/chat.py app/models/chat_session.py app/models/chat_message.py app/schemas/chat_session.py
> alembic upgrade head && alembic downgrade -1 && alembic upgrade head
> pytest tests/test_phase12_chat_sessions.py -v   # 期望 15 passed
> pytest -q   # 期望 235 passed + 2 skipped
> cd ../frontend
> npm run lint
> npm run typecheck
> ```
>
> **Step 8 — feat + chore(progress) 落盘**:
> ```bash
> # feat 严格 9 文件 staged(对齐 §5.1)
> git add backend/app/models/chat_session.py \
>         backend/app/models/chat_message.py \
>         backend/app/models/__init__.py \
>         backend/alembic/versions/20260530_*_phase12_chat_history.py \
>         backend/app/schemas/chat_session.py \
>         backend/app/routers/chat.py \
>         backend/tests/test_phase12_chat_sessions.py \
>         frontend/src/api/chat.ts \
>         frontend/src/app/chat/page.tsx
> git commit -m "$(cat <<'EOF'
> feat(chat): T-1201 AI 多轮对话上下文 + 历史持久化
>
> 后端:
> - 新建 ChatSession + ChatMessage 模型(BaseMixin + JSONB tool_calls + chat_role ENUM)
> - 新建 alembic 迁移 phase12_chat_history(double-table + 5 indexes + ENUM)
> - 新建 schemas/chat_session(ChatSessionListItem/Response/Detail/Update + ChatMessageOut)
> - 改 routers/chat.py:
>   * ChatRequest 扩 session_id; ChatResponse 扩 session_id
>   * admin_ai_chat 首次隐式建 session;复用时加载 ≤20 message 历史(MAX_HISTORY_CHARS=20000 闸门)
>   * 每轮 LLM 调用 + tool 执行结果均落盘 ChatMessage
>   * 新增 GET/PATCH/DELETE /chat/sessions 端点(分页 + ilike 搜索 + 软删)
>
> 前端:
> - 改 api/chat.ts:askAI 扩 sessionId 参数 + 4 件 sessions API + ChatSessionListItem / Detail
> - 改 app/chat/page.tsx:左右分栏(侧栏 sessions 列表 + 新建/重命名/删除 + 切换加载 history)
>
> 测试:
> - 新建 tests/test_phase12_chat_sessions.py 15 case(Model 3 + 主干 6 + RBAC 3 + 会话管理 3)
>
> 零回归:
> - T-1104/T-1105/T-1106 全部锁定文件零改动
> - conftest/_isolation/_db_url/.env/README/DEPLOY/llm_selector/chat_tools 零改动
> - 测试基线 220 → 235 passed + 2 skipped
>
> Worker timestamp: [YYYY-MM-DD HH:MM:SS]
>
> Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
> EOF
> )"
>
> # chore(progress) 严格 1 文件
> # 编辑 docs/dev_tasks.md:Task 7 (T-1201) [/] → [x] Done by Codex [HH:MM:SS] + 完工实绩段落填充
> git add docs/dev_tasks.md
> git commit -m "$(cat <<'EOF'
> chore(progress): close T-1201 — Phase 12 第一任 AI 对话历史持久化完工
>
> 工程完工实绩:
> - 9 文件改动面严格(2 新建 model + 1 改 __init__ + 1 新建 migration + 1 新建 schema + 1 改 router + 1 新建 test + 1 改 api + 1 改 page)
> - 15 case 全 PASS / 全量 235 passed + 2 skipped / ruff + mypy + frontend lint/typecheck 全绿
> - alembic upgrade-downgrade-upgrade 来回幂等(ENUM + 双表 + 5 index)
>
> 严禁项遵守证据:0 T-1104 / 0 T-1105 / 0 T-1106 / 0 conftest / 0 _isolation / 0 _db_url / 0 .env / 0 README / 0 DEPLOY / 0 llm_selector / 0 chat_tools / 0 push / 0 amend / 0 rebase / 0 --no-verify / 0 自启 T-1202
>
> Worker timestamp: [YYYY-MM-DD HH:MM:SS]
>
> Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
> EOF
> )"
> ```
>
> **严禁项再确认(BLOCKER 红线 — 14 条已在 §2 罗列,Codex 接手前必须二次自查)**:
>
> 1. 🚫 严禁 `git push` / `git stash` / `git rebase` / `git commit --amend` / `--no-verify`(等指挥官二次验收 + 用户决定推送时机)
> 2. 🚫 严禁 自启 T-1107 / T-1108 / T-1202 / T-1203 / 其他 Phase 11/12 backlog
> 3. 🚫 严禁 改 T-1104 / T-1105 / T-1106 任何锁定文件(§2 第 2~4 条)
> 4. 🚫 严禁 改 `conftest / _isolation / _db_url / .env* / README / DEPLOY / llm_selector / chat_tools / 周报 / 中间件 / main / database`
> 5. 🚫 严禁 改 `pyproject / requirements / uv.lock / package.json / package-lock.json`(零依赖新增)
> 6. 🚫 严禁 改 6 个现有 chat 子组件内部 markup(UserBubble / AssistantBubble / ToolTraceList / ToolTraceItem / LoadingBubble / EmptyState)
> 7. 🚫 严禁 引入新 UI 库(radix-ui / shadcn 等)+ 严禁 改 lucide-react 体例之外的 icon library
> 8. 🚫 严禁 触碰工作区遗留 5 项(login / change-password / 3 debug 脚本)
> 9. 🚫 严禁 mock ORM 或 monkeypatch DB session(仅允许 mock `_call_llm` 模块级 helper)
>
> **状态切换信号**:`docs/dev_tasks.md` Task 7 标识从 `[/] In Progress by Codex` 切到 `[x] Done by Codex [YYYY-MM-DD HH:MM:SS]`,且 chore(progress) commit 落盘成功 — 指挥官以此为信号启动二次验收(28 项清单见 §8)。

---

**📌 spec 元数据**:
- 行数:~1080 行
- 章节数:10 章 + 📣 物理交接单
- 字面量字段精准锁定:Migration revision/down_revision/FK/index 命名 + Model 字段类型 + Schema Pydantic V2 + Router endpoint path/method/RBAC + 前端 interface/函数签名
- 验收清单条目:28(§8)
- 严禁项条目:14 BLOCKER 红线(§2)
- 决策签字:6(§6)
- 改动面文件:9(§5.1)
- 闸门探针:8 self-check(§3.9)+ 4 边界 grep(§5.2)+ 8 质量闸门(§4)
