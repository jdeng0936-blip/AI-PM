# 📜 T-1106 执行契约 — Phase 11 第六任(候选):临时工单跟进追踪闭环(过程时间轴 + 结果强制 + 状态联动)

> **起草时间戳**: `[2026-05-29 11:37:28]`(指挥官签字)
> **指挥官**: Claude (Opus 4.7 / 1M)
> **Worker**: Codex(待 T-1105 完工 + 二次验收 PASS 之后,指挥官接手放牌)
> **基线 commit**: **由 T-1105 完工 `chore(progress)` commit hash 填实**(本 spec 起草时 T-1105 进行中:`a728081 chore(lock)` → `91e312b feat(projects)` → `<待 chore(progress)>`)
> **alembic head**: 由 T-1105 完工时填实(本任新增 1 migration 在 T-1105 之上,**不**跨 T-1105 改 alembic chain)
> **依赖前置(BLOCKER 红线)**: T-1105 完工(三 commit 完整) + 指挥官二次验收 PASS + 工作树干净;**严禁** 与 T-1105 并行执行(防文件踩踏)

---

## §1 任务背景与范围(WHY + WHAT)

### 1.1 起源

- **老板追加需求(`[2026-05-29 11:25 用户指令]`)**:改进"临时工单"的跟进与闭环追踪机制,3 项设计:
  1. **过程追踪**:轻量级"跟进记录"功能(类似动态时间轴),成员可随时添加文本进展
  2. **结果闭环**:临时工单流转为"已完成"时,**强制**填写"处理结果(`resolution_summary`)"
  3. **状态联动**:工单如果长达 X 天没有新增进展,健康度应受到影响
- **Phase 11 backlog 重排**(T-1105 临时插队 + T-1106 二次追加):
  - **T-1105**(进行中):立项指派成员 — Codex 已 `a728081 chore(lock)` + `91e312b feat(projects)` 推进 2 commit,等 `chore(progress)`
  - **T-1106(本任)**:临时工单跟进追踪 — 老板追加需求
  - **T-1107**(候选,顺延):原 T-1105 FK 第二阶段 — 切剩余 36+ 后端读路径用 Resolver + frontend schemas 扩 `department_id`
  - **T-1108**(候选,顺延):原 T-1106 drop column — `User.department VARCHAR(64)` + 删除 Resolver fallback
  - **T-1109+**(候选):Phase 11 候选议题 ②③④(物化视图增量 / KPI 钻取 / 前端 Tabs 加权重柱状图)
- **业务驱动力**:
  - **现状**:临时工单项目走 V2.3 轻量路径(`Project.is_temporary=True`,跳过 IPD 5 阶段 + 健康度固定 green/100,见 `backend/app/services/health_engine.py:182-188`),意味着**临时工单进入"无监管黑洞"** — 无健康度反馈、无过程跟进机制、无结果归集字段。
  - **痛点**:用户提了"日常 bug / 改价 / 临时维护"工单后,看不到处理进展(只能口头追问负责人);工单"已完成"状态打勾后无客观处理结果记录(不便审计);长时间停滞的工单不会反映到红黄绿矩阵(项目监控盲区)。
  - **T-1106 闭环价值**:轻量级时间轴 + 结果强制 + stale 健康度联动三件套,让临时工单从"轻量黑洞"升级为"轻量 + 可追溯 + 可监控"。

### 1.2 任务定位(三件套渐进闭环)

| 维度 | 当前现状 | T-1106 后 |
|---|---|---|
| 跟进记录数据模型 | ❌ 无 | **新建** `project_follow_ups` 表 + ORM(独立表,project_id FK + content text + created_by FK) |
| 跟进记录 API | ❌ 无 | **新建** POST `/api/v1/projects/{id}/followups` + GET `/api/v1/projects/{id}/followups`(2 端点) |
| 跟进记录前端 UI | ❌ 无 | **新建** `<FollowupTimeline>` 组件 + 项目详情页加 `activeTab='followups'` tab |
| `Project.resolution_summary` 字段 | ❌ 无 | **新增** `resolution_summary: Mapped[Optional[str]]`(仅临时工单使用)+ migration |
| 临时工单"已完成"流转 | 走 PATCH `/projects/{id}` `status='completed'`,无强制结果填写 | **强化** PATCH 守卫:`is_temporary=True + status='completed'` 时**必须**带 `resolution_summary`,缺则 400 |
| 健康度联动 | 临时工单固定 `green / score=100`(`health_engine.py:182-188`) | **改造** `refresh_project_health` 临时分支:按"最近一次 followup"判 stale(7 天 yellow / 14 天 red) |
| 健康度阈值 | 主干项目用 `SCORE_*_THRESHOLD + BLOCKER_*_DAYS` | **追加** 临时项目用 `STALE_YELLOW_DAYS = 7 / STALE_RED_DAYS = 14`(硬编码常量) |
| 定时刷新触发 | `scheduled_tasks.run_health_refresh_all` 每日重算所有活跃项目 | **复用,零修改**(stale 检测嵌入 `refresh_project_health` 后自动被现有 daily task 触发) |
| 主干项目 IPD 健康度 | 复杂多维聚合(`compute_stage_health`) | **零改动**,严格不污染 |
| 跟进记录覆盖范围 | — | **主干 + 临时项目共享**(任何项目都可记录跟进) |
| `resolution_summary` 适用范围 | — | **仅临时工单**(`is_temporary=True`,主干项目走 IPD gate 评审,有自己的结项逻辑) |
| stale 健康度联动适用范围 | — | **仅临时工单**(主干项目已有 health_engine 多维聚合,不扰动) |
| 跟进记录删除权限 | — | **不允许删**(append-only,审计友好,T-1109+ 可再开 admin 软删能力) |

### 1.3 与 T-1105 严格解耦策略

**前置约束(BLOCKER)**:T-1106 执行依赖 T-1105 完工 + 二次验收 PASS。Codex 接手前必须核对:
1. `git log --oneline -10` 看到 `T-1105 chore(progress)` commit
2. dev_tasks.md Task 5 = `[x] Done by Codex`
3. 工作树干净(零 modified / 仅既定 untracked)
4. 指挥官二次验收回执已落盘 / 或经 Supervisor 明示放行

**T-1105 锁定文件(本任 T-1106 严禁触碰非本任作用域以外的 T-1105 文件段)**:

| T-1105 锁定文件 | T-1106 是否触碰 | 触碰段说明 |
|---|---|---|
| `backend/app/schemas/project.py` | ⚠️ **触碰**(增量) | **严禁**改 T-1105 引入的 `ProjectMemberInit` / `ProjectCreate.members` 段;**只**追加 `ProjectFollowUpCreate` / `ProjectFollowUpOut` / `ProjectComplete` 新 schemas + 扩 `ProjectUpdate.resolution_summary` 字段 |
| `backend/app/routers/projects.py` | ⚠️ **触碰**(增量) | **严禁**改 T-1105 改的 `create_project` 函数内成员批插逻辑;**只**改 `update_project` 函数(加 `is_temporary + status='completed'` 强制 resolution_summary 守卫)+ 新增 POST `/{id}/followups` + GET `/{id}/followups` 2 端点 |
| `backend/app/routers/users.py` | ✅ **零触碰** | T-1105 引入的 `UserPickerItem` + `GET /picker` 端点本任完全不动 |
| `backend/tests/test_phase11_project_members.py` | ✅ **零触碰** | T-1105 新建测试文件本任完全不动 |
| `frontend/src/api/projects.ts` | ⚠️ **触碰**(末尾追加) | **严禁**改 T-1105 引入的 `ProjectMemberInit` / `CreateProjectPayload` / `createProject` type;**只**末尾追加 followup APIs(`createFollowup` / `listFollowups`)+ 改 `updateProject` 类型签名(可选,允许 untyped 'any' 继续) |
| `frontend/src/api/users.ts` | ✅ **零触碰** | T-1105 引入的 `UserPickerItem` + `getUserPicker` 本任完全不动 |
| `frontend/src/components/member-picker.tsx` | ✅ **零触碰** | T-1105 新建组件本任完全不动 |
| `frontend/src/app/projects/page.tsx` | ✅ **零触碰** | T-1105 改的立项 Modal 本任完全不动(本任 UI 改造在项目详情页 `[id]/page.tsx`) |

### 1.4 不做范围(BLOCKER 红线)

- ❌ **不动** 主干项目健康度计算(`compute_stage_health` / `_compute_health` 单一真理源,本任仅扩临时项目分支)
- ❌ **不动** `Project.health_score / health_status` 字段定义(model 字段不动,只新增 `resolution_summary` 字段)
- ❌ **不动** 现有 `routers/projects.py` 除 `update_project` 外的任何已存在路由函数(T-1105 已改的 `create_project` 在内,完全冻结)
- ❌ **不动** `backend/app/services/scheduled_tasks.py`(现有 `run_health_refresh_all` 已 cover 每日触发,本任 stale 检测嵌入 `refresh_project_health` 自动被触发,零定时任务新增)
- ❌ **不动** `backend/app/services/_department_resolver.py` / `department_service.py`(T-1104 落地,本任不重做)
- ❌ **不动** T-1105 完工 5 backend 文件(见 §1.3 表格)
- ❌ **不动** `backend/conftest.py` / `tests/_isolation.py` / `tests/_db_url.py` / `.env*` / `README.md` / `DEPLOY.md`(T-1102/1103 已闭环)
- ❌ **不动** `backend/pyproject.toml` / `backend/requirements.txt` / `backend/uv.lock`
- ❌ **不动** 前端 dashboard / admin / users / sidebar / login / change-password 任何页面
- ❌ **不动** 现有项目详情页 `[id]/page.tsx` 4 个现有 tab 渲染块(`overview / sprints / gates / members`)— 本任仅**追加** `followups` 第 5 tab + 完工对话框(主干项目 / 临时项目分支判断)
- ❌ **不** 加跟进记录的"标签 / 附件 / @mention / 编辑 / 删除"功能(留给 T-1109+ 单独提案)
- ❌ **不** 引入 `system_settings` 表存 stale 阈值(硬编码常量,T-1109+ 可单独提案配置化)
- ❌ **不** 自启 T-1107 / T-1108 / 其他 Phase 11 候选议题

---

## §2 严禁项(BLOCKER 红线 · 共 13 条)

| # | 严禁项 | 触发后果 |
|---|---|---|
| 1 | **基线 commit 错误**:Codex 接手时 base 不是 T-1105 完工 commit | BLOCKER 立即退回(防 T-1105 / T-1106 race) |
| 2 | 改 T-1105 引入的代码(`ProjectMemberInit` / `ProjectCreate.members` / `create_project` 成员批插逻辑 / `GET /users/picker` / `UserPickerItem` / `MemberPicker` / `getUserPicker` / `CreateProjectPayload` / 立项 Modal MemberPicker 块) | BLOCKER 立即退回 |
| 3 | 改 `backend/app/services/health_engine.py` 主干项目分支逻辑(`compute_stage_health` / `_compute_health` / `refresh_sprint_health` 三函数 + L36-45 主干阈值常量) — 只允许**插入式追加** stale 常量 + **改写** `refresh_project_health` 临时项目分支 | BLOCKER 立即退回 |
| 4 | 改 `backend/app/services/scheduled_tasks.py`(本任零定时任务新增) | BLOCKER 立即退回 |
| 5 | 改 `backend/app/routers/projects.py` 除 `update_project` 函数外的任何已存在路由函数(`add_project_member / batch_remove_members / list_project_members / archive_project / batch_soft_delete_projects / batch_restore_projects / get_deleted_projects / projects_overview / get_project / get_project_gantt` 等全部冻结) | BLOCKER 立即退回(只允许 update_project 改 + 新增 followups 2 端点) |
| 6 | Migration 新增表 `project_follow_ups` 缺索引(必须含 `ix_project_follow_ups_project_id` + `ix_project_follow_ups_created_at` 复合或独立 2 索引) | BLOCKER 立即退回 |
| 7 | Migration `downgrade()` 留空 / `NotImplementedError` / 不可回滚 | BLOCKER 立即退回(必须 drop_table + drop_column 反向 2 步完整) |
| 8 | 改 `backend/conftest.py` / `tests/_isolation.py` / `tests/_db_url.py` / `.env*` / `README.md` / `DEPLOY.md` / `pyproject.toml` / `requirements.txt` / `uv.lock` | BLOCKER 立即退回(T-1102/1103 闭环 + 工具链稳定) |
| 9 | 改 T-1104 5 backend 文件 / T-1105 8 文件中**任一与本任改动段重叠**的部分 | BLOCKER 立即退回 |
| 10 | 改前端 dashboard / admin / users / sidebar / login / change-password / `projects/page.tsx` 任何文件 — 只允许改 `frontend/src/app/project/[id]/page.tsx` 单 page + 新建 `components/followup-timeline.tsx` + 末尾追加 `api/projects.ts` followup APIs | BLOCKER 立即退回 |
| 11 | 自启 T-1107 / T-1108 / 其他 Phase 11 候选议题 | BLOCKER 立即退回 |
| 12 | `git push` / `git stash` / `amend` / `rebase` / `--no-verify` 跳过 hook | BLOCKER 立即退回 |
| 13 | 双 commit 任一缺 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 行(CLAUDE.md #7) | BLOCKER 立即退回 |

---

## §3 实施细则

### 3.1 数据层:新建 `project_follow_ups` 表 + `Project.resolution_summary` 字段

#### 3.1.1 新建 `backend/app/models/project_followup.py`(~75 行)

**字面量骨架**:

```python
"""
app/models/project_followup.py — 项目跟进记录表(T-1106 新增)

轻量级时间轴:成员可在任何项目(主干 + 临时)上追加文本进展,
用于:
  - 临时工单的进度追踪(T-1106 主战场)
  - 主干项目的非结构化补充信息(替代散落在企微 / 钉钉的对话)
  - 健康度联动:`is_temporary=True` 时,最近 followup 时间 > N 天 → 影响健康度

约束:
  - append-only(本任零删除 / 零编辑能力,留给 T-1109+ admin 软删)
  - content 字符串上限 1024(企微一条消息上限的 2x,够用)
  - created_by FK→users.id ON DELETE SET NULL(用户被删时保留 followup,审计友好)
  - project_id FK→projects.id ON DELETE CASCADE(项目删除时跟进一并清理)
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class ProjectFollowUp(BaseMixin, Base):
    __tablename__ = "project_follow_ups"
    __table_args__ = (
        Index("ix_project_follow_ups_project_created", "project_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供
    #       本任零删除能力,deleted_at 不需要(留给 T-1109+ 视需开)

    def __repr__(self) -> str:
        return f"<ProjectFollowUp project={self.project_id} at={self.created_at}>"
```

**说明**:
- **复合索引 `(project_id, created_at)`**:加速"按项目查最近 N 条 followup"(健康度 stale 检测 + 前端时间轴主查询);单字段 `ix_project_follow_ups_project_id` 由 `index=True` 自动建,与复合索引并存(SQLAlchemy 默认行为)
- **`Text` 不用 `String(1024)`**:Pydantic 层 max_length=1024 校验,DB 层不强约束(便于未来扩长度)
- **`created_by FK ON DELETE SET NULL`**:BaseMixin 提供;用户被硬删时保留 followup 但 created_by NULL(审计友好)
- **BaseMixin 自动提供** `created_at / updated_at / created_by / tenant_id`(本仓库现有所有表沿用)

#### 3.1.2 改 `backend/app/models/project.py`(+5 行,在 L82-91 `deleted_at` 字段之**前**插入)

**字面量**(L82 `# ── V2.4 Stage 2 软删标识 ──` 注释行**之前**插入):

```python
    # ── T-1106 临时工单处理结果归集 ─────────────────────────────────
    # 仅 is_temporary=True 流转到 status='completed' 时强制要求填写
    # 主干项目走 IPD G4 关卡评审,resolution_summary 永远 NULL
    resolution_summary: Mapped[Optional[str]] = mapped_column(
        String(2048),
        nullable=True,
        comment="临时工单处理结果(T-1106):仅 is_temporary=True 完工时强制填写;主干项目永久 NULL",
    )

```

**说明**:
- **`String(2048)`**:resolution_summary 通常 100-500 字够用,2048 给充裕余量(对比 `description: String(512)` 翻 4 倍)
- **`nullable=True`**:主干项目 / 未完工临时项目均允许 NULL,只在"临时工单流转 completed"时 router 层强制守卫(§3.3.2)
- **导入**:L12 `from typing import Optional` 已就位,L14 `from sqlalchemy import ... String ...` 已就位,**严禁**改 import 块

#### 3.1.3 改 `backend/app/models/__init__.py`(+2 行)

**字面量**(L43 `from app.models.project_stage import ProjectStage` **之前**插入):

```python
from app.models.project_followup import ProjectFollowUp
```

**字面量**(L67 `"ProjectStage",` **之前**插入到 `__all__`):

```python
    "ProjectFollowUp",
```

**说明**:**严禁**重排 `__all__` 其他 string,**严禁**重排 import 顺序 — 在 IPD 项目管理模型块内插入式追加。

#### 3.1.4 新建 Alembic Migration(`backend/alembic/versions/20260530_HHMM_phase11_project_followups.py` ~120 行)

**关键字面量**:

```python
"""Phase 11 T-1106: project_follow_ups table + Project.resolution_summary column.

Revision ID: <Codex 自选 12 位 hex>
Revises: <由 T-1105 完工时 alembic heads 实际值填实;如 T-1105 零 migration,则仍是 T-1104 引入的 head>
Create Date: 2026-05-30 HH:MM:SS

T-1106 三件套:
  - 新建 project_follow_ups 表(轻量时间轴,append-only)
  - 新增 Project.resolution_summary VARCHAR(2048) 字段
  - 复合索引 (project_id, created_at) 加速 stale 检测 + 前端时间轴查询
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "<Codex 自选 12 位 hex>"
down_revision = "<T-1105 完工 head 字面量 / 或 T-1104 head>"  # Codex 接手时 alembic heads 二次核验
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: 建 project_follow_ups 表(BaseMixin 字段:created_at / updated_at / created_by / tenant_id)
    op.create_table(
        "project_follow_ups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        # BaseMixin 字段
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_project_follow_ups_project_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_project_follow_ups_created_by", ondelete="SET NULL"
        ),
    )
    # Step 2: 索引(单字段 + 复合)
    op.create_index("ix_project_follow_ups_project_id", "project_follow_ups", ["project_id"])
    op.create_index("ix_project_follow_ups_project_created", "project_follow_ups", ["project_id", "created_at"])

    # Step 3: 给 projects 表加 resolution_summary 列
    op.add_column(
        "projects",
        sa.Column("resolution_summary", sa.String(2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "resolution_summary")
    op.drop_index("ix_project_follow_ups_project_created", table_name="project_follow_ups")
    op.drop_index("ix_project_follow_ups_project_id", table_name="project_follow_ups")
    op.drop_table("project_follow_ups")
```

**说明**:
- **`down_revision`**:Codex 接手时**必须** `alembic heads` 二次核验取实际值(T-1105 零 migration 时仍是 T-1104 head;但若 T-1105 完工后有意外 migration 漂移,以实际为准)
- **server_default `now()` / `"default"`**:对齐现有所有 BaseMixin migrations 体例(参考 `20260527_*` Phase 10 migrations)
- **drop 顺序**:列 → 复合索引 → 单字段索引 → 表(逆 upgrade 顺序)

### 3.2 Schema 层扩展(改 `backend/app/schemas/project.py` ~+35 行)

#### 3.2.1 imports 块(**不动**)

`from typing import Optional` / `import uuid` / `from datetime import date, datetime` / `from pydantic import BaseModel, Field` 全部已就位(本任不需补 import)。

⚠️ **严禁**改 T-1105 引入的 `ProjectMemberInit` 类。

#### 3.2.2 扩 `ProjectUpdate` 类(原 L29-38 段,在 `status: Optional[str]` 之后**追加** `resolution_summary`)

**字面量**(在 `status: Optional[str] = Field(None, description="active / paused / completed / cancelled")` 之后追加):

```python
    # T-1106 临时工单处理结果(仅 is_temporary=True 完工时强制,主干项目永远 NULL)
    resolution_summary: Optional[str] = Field(
        None,
        max_length=2048,
        description="临时工单处理结果归集(T-1106):仅 is_temporary=True 流转 status='completed' 时强制",
    )
```

#### 3.2.3 新增 `ProjectComplete` 类(在 `ProjectUpdate` 之后,`Milestone` 之前插入)

**字面量**:

```python
# ── T-1106 临时工单完工(强制结果填写) ─────────────────────────
class ProjectComplete(BaseModel):
    """临时工单流转 'completed' 时的强制结果填写 payload(供 router 守卫使用)。

    本 schema 不直接绑定到端点,仅作 router 内字段语义锚点。
    实际端点(PATCH /projects/{id})继续用 ProjectUpdate,守卫逻辑在 router 层。
    """

    resolution_summary: str = Field(..., min_length=1, max_length=2048)
```

**说明**:本 schema 仅作"显式语义锚点",router 守卫读 ProjectUpdate.resolution_summary 字段;不强制端点切换避免破坏现有调用方。

#### 3.2.4 新增 `ProjectFollowUpCreate` / `ProjectFollowUpOut` 类(在 `ProjectMemberAdd` 之后插入)

**字面量**:

```python
# ── T-1106 项目跟进记录(轻量时间轴) ──────────────────────────
class ProjectFollowUpCreate(BaseModel):
    """成员追加跟进记录的 payload(POST /projects/{id}/followups)。"""

    content: str = Field(..., min_length=1, max_length=1024, description="跟进文本内容,1-1024 字")


class ProjectFollowUpOut(BaseModel):
    """跟进记录返回(GET /projects/{id}/followups list item)。"""

    id: str
    project_id: str
    content: str
    created_by: Optional[str]
    created_by_name: Optional[str]  # JOIN users.name 反查(便于前端展示头像/姓名)
    created_at: datetime

    model_config = {"from_attributes": True}
```

**说明**:
- **`created_by_name`**:JOIN `User.name` 反查,避免前端二次请求(对齐 `list_project_members` L854-865 体例)
- **`from_attributes = True`**:Pydantic V2 兼容 SQLAlchemy ORM 实例直接 unpack

### 3.3 Router 层扩展(改 `backend/app/routers/projects.py` ~+90 行)

#### 3.3.1 imports 块(L30-36)**插入式**追加新 schemas + 新 model

**字面量**(在 `from app.schemas.project import (` 块内,**插入** 3 项;在 `from app.models.project_member import ProjectMember` 之后**插入** ProjectFollowUp model import):

```python
from app.models.project_followup import ProjectFollowUp  # T-1106 新增
# ... 现有 imports ...
from app.schemas.project import (
    GanttStage,
    ProjectComplete,         # T-1106 新增(显式语义锚点,守卫读 ProjectUpdate)
    ProjectCreate,
    ProjectFollowUpCreate,   # T-1106 新增
    ProjectFollowUpOut,      # T-1106 新增
    ProjectMemberAdd,
    ProjectMemberInit,
    ProjectUpdate,
    StageUpdate,
)
```

⚠️ **严禁**重排现有 import 顺序(T-1105 已新增 ProjectMemberInit 字母序略偏离,保留;本任继续插入式追加保持自洽)。

#### 3.3.2 改 `update_project` 函数(L619-662,加 `is_temporary + completed` 守卫)

**找到** L619 `@router.patch("/{project_id}")` 开始的 `update_project` 函数体,**插入式**追加"临时工单 completed 守卫"逻辑(在更新前校验 + 在 status 字段写入前后)。

**字面量参考**(Codex 接手时按现有函数体语义对齐;具体行号视 T-1105 完工后 routers/projects.py 实际状态):

```python
@router.patch("/{project_id}")
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == _user.tenant_id,
                Project.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "项目不存在")

    # T-1106 守卫:临时工单流转 'completed' 必须带 resolution_summary
    target_status = data.status if data.status is not None else None
    if (
        project.is_temporary
        and target_status == "completed"
        and not (data.resolution_summary or project.resolution_summary)
    ):
        raise HTTPException(
            400,
            "临时工单完工必须填写处理结果(resolution_summary),长度 1-2048 字符",
        )

    # 现有字段更新逻辑(保留所有现状,字面量 Codex 按 T-1105 完工后实际接续) ...
    # 新增:resolution_summary 字段写入
    if data.resolution_summary is not None:
        project.resolution_summary = data.resolution_summary

    await db.commit()
    # T-1106:若刚流转为 completed 或新增了 resolution_summary,触发健康度重算
    # (临时工单 stale 检测可能因刚完工而切换 green;主干项目 refresh_project_health 已有逻辑)
    if target_status == "completed" or data.resolution_summary is not None:
        await refresh_project_health(db, project_id)

    return {"message": "项目已更新", "project_id": str(project.id)}
```

**说明**:
- **守卫触发条件**:`is_temporary=True + 即将切换到 status='completed' + payload 和 DB 都无 resolution_summary` → 400 拦截
- **允许已 completed 项目补填**:若项目已是 completed 且 DB 已有 resolution_summary,本次 PATCH 不带 resolution_summary 也不报错(不重复校验)
- **健康度刷新**:完工后 `refresh_project_health` 调用,让 stale 检测立即生效(从 stale red → 完工 green)
- ⚠️ **不动** T-1105 已改的 `create_project` 函数;不动其他 router 函数

#### 3.3.3 新增 POST `/{project_id}/followups` 端点(在 `add_project_member` L734 函数**之前**插入)

**字面量**:

```python
# ── T-1106 项目跟进记录:追加 + 列表 ──────────────────────────────
@router.post("/{project_id}/followups", status_code=201)
async def create_followup(
    project_id: uuid.UUID,
    data: ProjectFollowUpCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """追加项目跟进记录(主干 + 临时项目共享路径)。

    RBAC:任何在该项目可见范围内的活跃用户均可追加(对齐 employee 也能看自己项目的语义)。
    严格 tenant 隔离 + 项目可见性校验(_get_visible_project)。
    """
    project = await _get_visible_project(db, project_id, current_user)
    followup = ProjectFollowUp(
        project_id=project.id,
        content=data.content,
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
    )
    db.add(followup)
    await db.commit()
    await db.refresh(followup)
    # T-1106:临时项目追加 followup 后触发健康度重算(让 stale 检测立即生效)
    if project.is_temporary:
        await refresh_project_health(db, project_id)
    return {
        "id": str(followup.id),
        "project_id": str(followup.project_id),
        "content": followup.content,
        "created_at": followup.created_at.isoformat(),
    }


@router.get("/{project_id}/followups")
async def list_followups(
    project_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200, description="返回条数上限,默认 50,最大 200"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出项目跟进记录(倒序,最新在前)。

    RBAC:任何在该项目可见范围内的活跃用户均可读。
    """
    await _get_visible_project(db, project_id, current_user)
    # JOIN users 反查 created_by_name
    from app.models.user import User as UserModel  # 局部 import 避免循环
    rows = await db.execute(
        select(ProjectFollowUp, UserModel.name)
        .outerjoin(UserModel, ProjectFollowUp.created_by == UserModel.id)
        .where(
            ProjectFollowUp.project_id == project_id,
            ProjectFollowUp.tenant_id == current_user.tenant_id,
        )
        .order_by(ProjectFollowUp.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": str(r.ProjectFollowUp.id),
            "project_id": str(r.ProjectFollowUp.project_id),
            "content": r.ProjectFollowUp.content,
            "created_by": str(r.ProjectFollowUp.created_by) if r.ProjectFollowUp.created_by else None,
            "created_by_name": r.name,
            "created_at": r.ProjectFollowUp.created_at.isoformat(),
        }
        for r in rows.all()
    ]
```

**说明**:
- **RBAC**:`get_current_user`(任何活跃用户)+ `_get_visible_project`(项目可见性 = 跨 tenant 隔离 + employee 限制只看自己参与的项目);**不**用 `_mgr`,因为跟进记录是协作工具,employee 也应能用
- **`outerjoin` 而非 `join`**:`created_by` 可能 NULL(用户被硬删后 SET NULL),outer join 保证仍返回 followup
- **`limit`**:默认 50,最大 200,防大列表性能问题
- **倒序**:`order_by(created_at.desc())` 最新在前,前端时间轴语义
- **临时项目 followup 触发健康度刷新**:对齐"成员追加 followup → 项目立即 unstale → 健康度变绿"业务期待

### 3.4 健康度联动(改 `backend/app/services/health_engine.py` ~+45 行)

#### 3.4.1 阈值常量追加(L36-45 之后**追加** stale 常量)

**字面量**(L45 `W_NO_BLOCKER = 0.20` 之后追加):

```python

# ── T-1106 临时工单 stale 健康度阈值 ───────────────────────────────
# 临时工单最近一次 followup 距今天数 → 健康度联动
STALE_YELLOW_DAYS = 7   # ≥7 天无 followup → yellow
STALE_RED_DAYS = 14     # ≥14 天无 followup → red
# (在阈值之间的天数走 yellow;< STALE_YELLOW_DAYS 保持 green)
```

#### 3.4.2 改 `refresh_project_health` 临时项目分支(L182-188 重写)

**字面量替换**(L182-188 原"固定 green / score=100"逻辑):

```python
    # V2.3 + T-1106 临时工单项目:
    # 不走 IPD 阶段健康度,改走"最近 followup 距今天数"stale 检测
    if project.is_temporary:
        from app.models.project_followup import ProjectFollowUp  # 局部 import 避免循环

        last_followup_q = await db.execute(
            select(func.max(ProjectFollowUp.created_at)).where(
                ProjectFollowUp.project_id == project_id,
                ProjectFollowUp.tenant_id == project.tenant_id,
            )
        )
        last_followup_at = last_followup_q.scalar()

        # 已完工的临时工单永远 green / 100(对齐"已结案就不再扰动监管"语义)
        if project.status and getattr(project.status, "value", project.status) == "completed":
            project.health_status = ProjectHealthStatus.green
            project.health_score = 100
        elif last_followup_at is None:
            # 临时工单立项后从未追加过 followup → 用 created_at 作 baseline
            baseline = project.created_at
            days_stale = (datetime.now(timezone.utc) - baseline).days if baseline else 0
            project.health_status, project.health_score = _compute_temp_stale_health(days_stale)
        else:
            days_stale = (datetime.now(timezone.utc) - last_followup_at).days
            project.health_status, project.health_score = _compute_temp_stale_health(days_stale)

        await db.commit()
        return
```

**说明**:
- **已完工临时工单永远 green/100**:对齐"工单结案,不再扰动监管"业务语义
- **从未追加 followup 的临时工单**:用 `Project.created_at` 作 stale baseline(否则永远 stale red,不合理 — 应当从立项时计时)
- **`datetime.now(timezone.utc)`**:对齐 BaseMixin `created_at` 的 `DateTime(timezone=True)`(避免 naive/aware 比较抛错)
- **`from datetime import datetime, timezone` 已存在 import**(L24 `from datetime import date, timedelta`)— ⚠️ Codex 接手时确认 imports;若需补 `datetime, timezone` 则插入式追加

#### 3.4.3 新增 `_compute_temp_stale_health` 私有函数(在 `_compute_health` 之**后**插入)

**字面量**:

```python

def _compute_temp_stale_health(days_stale: int) -> tuple[ProjectHealthStatus, int]:
    """T-1106:基于"最近 followup 距今天数"计算临时工单健康度与分数。

    阶梯:
      < 7 天   → green / 100
      [7, 14)  → yellow / 60(简单线性递减,给前端视觉差异)
      ≥ 14 天  → red / 30
    """
    if days_stale >= STALE_RED_DAYS:
        return ProjectHealthStatus.red, 30
    if days_stale >= STALE_YELLOW_DAYS:
        return ProjectHealthStatus.yellow, 60
    return ProjectHealthStatus.green, 100
```

**说明**:
- **score 直接给固定值**(100 / 60 / 30):简化,避免线性插值的实现成本;前端"健康分"显示有区分度
- **私有函数**:下划线前缀对齐 `_compute_health` 体例

#### 3.4.4 import 补全(L21-34)

需补 import:`from datetime import datetime, timedelta, timezone`(替换 L24 现有 `from datetime import date, timedelta`)

**字面量**(L24 替换):

```python
from datetime import date, datetime, timedelta, timezone
```

### 3.5 前端 API 扩展(改 `frontend/src/api/projects.ts` 末尾追加 ~+15 行)

#### 3.5.1 文件末尾**插入式**追加 followup APIs

**字面量**(在 `getDeletedProjects` 之后追加):

```typescript

// T-1106 项目跟进记录(轻量时间轴)
export interface ProjectFollowUp {
  id: string
  project_id: string
  content: string
  created_by: string | null
  created_by_name: string | null
  created_at: string  // ISO timestamp
}

export const createFollowup = (projectId: string, content: string) =>
  request.post<unknown, { id: string; project_id: string; content: string; created_at: string }>(
    `/projects/${projectId}/followups`,
    { content },
  )

export const listFollowups = (projectId: string, limit = 50) =>
  request.get<unknown, ProjectFollowUp[]>(`/projects/${projectId}/followups`, { params: { limit } })
```

⚠️ **严禁**改 T-1105 引入的 `ProjectMemberInit` / `CreateProjectPayload` / `createProject` 类型签名。

### 3.6 前端组件新建(`frontend/src/components/followup-timeline.tsx` ~180 行)

#### 3.6.1 组件设计目标

- 时间轴展示(最新在顶)
- 顶部"追加跟进"输入框 + 提交按钮(textarea,字符计数 0/1024)
- 每条 followup 卡片显示:`created_by_name`(头像首字符)+ `created_at`(相对时间)+ `content`
- 加载状态 + 空状态 + 错误 toast
- 可控属性:`projectId: string` + `onAdded?: () => void`(回调用于触发外部 refresh,如健康度刷新)

#### 3.6.2 字面量骨架(Codex 落盘时按本骨架展开,允许 ±15% 行数偏移)

```typescript
/**
 * components/followup-timeline.tsx — 项目跟进时间轴(T-1106)
 *
 * 数据源:GET /api/v1/projects/{id}/followups + POST /api/v1/projects/{id}/followups
 *
 * 复用候选:
 *   - frontend/src/app/project/[id]/page.tsx activeTab='followups'(本任 T-1106 接入)
 *   - T-1109+ 主干项目卡片 / KPI 钻取详情 / OKR 跟踪记录
 */
'use client'

import { useState, useEffect, useCallback } from 'react'
import { createFollowup, listFollowups, type ProjectFollowUp } from '@/api/projects'
import { toast } from 'sonner'
import { Send, MessageCircle, RefreshCw } from 'lucide-react'

interface FollowupTimelineProps {
  projectId: string
  onAdded?: () => void  // 追加成功后回调(如外层刷新 project)
}

function formatRelative(iso: string): string {
  const now = new Date()
  const then = new Date(iso)
  const diff = (now.getTime() - then.getTime()) / 1000  // seconds
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
  return then.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

export default function FollowupTimeline({ projectId, onAdded }: FollowupTimelineProps) {
  const [items, setItems] = useState<ProjectFollowUp[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [content, setContent] = useState('')

  const fetchAll = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const data = await listFollowups(projectId, 50)
      setItems((data as unknown as ProjectFollowUp[]) || [])
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '加载跟进记录失败')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => { fetchAll() }, [fetchAll])

  async function handleSubmit() {
    const trimmed = content.trim()
    if (!trimmed) {
      toast.error('请输入跟进内容')
      return
    }
    if (trimmed.length > 1024) {
      toast.error('内容超过 1024 字符上限')
      return
    }
    setSubmitting(true)
    try {
      await createFollowup(projectId, trimmed)
      setContent('')
      toast.success('跟进已记录')
      await fetchAll()
      onAdded?.()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '追加失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-4">
      {/* 顶部输入区 */}
      <div className="stat-card">
        <div className="section-title flex items-center gap-2">
          <MessageCircle size={14} />
          追加跟进
        </div>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={3}
          maxLength={1024}
          placeholder="记录最新进展、协作动态、阶段性发现..."
          className="w-full px-3 py-2 rounded-lg text-sm outline-none resize-none mt-2"
          style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
        />
        <div className="flex items-center justify-between mt-2">
          <span className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
            {content.length}/1024
          </span>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || !content.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white disabled:opacity-50"
            style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
          >
            <Send size={12} />
            {submitting ? '提交中...' : '追加'}
          </button>
        </div>
      </div>

      {/* 时间轴 */}
      <div className="stat-card">
        <div className="flex items-center justify-between mb-3">
          <div className="section-title">📜 跟进时间轴({items.length})</div>
          <button
            type="button"
            onClick={fetchAll}
            disabled={loading}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>
        {loading && items.length === 0 && (
          <div className="text-center text-xs py-8" style={{ color: 'var(--color-text-secondary)' }}>加载中...</div>
        )}
        {!loading && items.length === 0 && (
          <div className="text-center py-8" style={{ color: 'var(--color-text-secondary)' }}>
            <MessageCircle size={32} className="mx-auto opacity-30 mb-2" />
            <p className="text-xs">暂无跟进记录,从上方追加第一条进展</p>
          </div>
        )}
        <div className="space-y-3">
          {items.map((it) => (
            <div key={it.id} className="flex gap-3 pb-3" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs shrink-0"
                style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
              >
                {it.created_by_name?.charAt(0) || '?'}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
                    {it.created_by_name || '(已删除用户)'}
                  </span>
                  <span style={{ color: 'var(--color-text-secondary)' }}>
                    {formatRelative(it.created_at)}
                  </span>
                </div>
                <p className="text-sm mt-1 whitespace-pre-wrap" style={{ color: 'var(--color-text-primary)' }}>
                  {it.content}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

### 3.7 前端项目详情页改造(改 `frontend/src/app/project/[id]/page.tsx`)

#### 3.7.1 imports 块(L1-16)**插入式**追加

**字面量**(在 L16 `import ListActionBar from '@/components/list-action-bar'` 之后追加):

```typescript
import FollowupTimeline from '@/components/followup-timeline'
```

#### 3.7.2 `activeTab` Union 扩展(L39)

**字面量替换**(L39):

```typescript
  const [activeTab, setActiveTab] = useState<'overview' | 'sprints' | 'gates' | 'members' | 'followups'>('overview')
```

#### 3.7.3 `tabs` 数组(L129-134)**追加** `followups` 项

**字面量替换**(L129-134):

```typescript
  const tabs = [
    { key: 'overview', label: '概览' },
    { key: 'sprints', label: 'Sprint' },
    { key: 'gates', label: '门禁' },
    { key: 'members', label: '成员' },
    { key: 'followups', label: '跟进' },  // T-1106 新增
  ]
```

#### 3.7.4 新增 `followups` tab 渲染块(在 `members` tab 渲染块之**后**插入)

**字面量**(在 `members` tab 渲染块结束 `)}` 之后,在编辑阶段 Modal 之前插入):

```jsx
      {/* T-1106 跟进时间轴 */}
      {activeTab === 'followups' && (
        <div className="animate-in">
          <FollowupTimeline projectId={id} onAdded={fetchAll} />
        </div>
      )}
```

#### 3.7.5 临时工单完工对话框(在 Header 区附近 / 或独立 modal)— **可选简化**

**最小可用方案**(避免破坏现有 UI 结构):

- 不新增独立完工对话框
- 项目详情页"概览" tab 内,若 `project?.is_temporary && project?.status !== 'completed'`,在某显眼位置展示"标记完工"按钮 → 点击弹出小 modal 收集 `resolution_summary` → 调 PATCH `/projects/{id}` `{status: 'completed', resolution_summary: ...}` → 成功后 `fetchAll()`
- **Codex 落盘时**:在 "概览" tab 现有内容**末尾**追加这一区块(不修改现有 Row 1 / Row 2 / 阶段流转图),保持现有渲染 100% 不动
- **临时工单已 completed 时**:展示 `resolution_summary` 内容(只读)
- **主干项目**:此区块完全不渲染(`if (!project?.is_temporary) return null` 守卫)

**字面量参考**(简化 ~50 行,Codex 按详情页现有体例落地):

```jsx
{/* T-1106 临时工单完工 / 结果回显(仅 is_temporary 项目)*/}
{project?.is_temporary && activeTab === 'overview' && (
  <div className="stat-card animate-in" style={{ animationDelay: '0.3s' }}>
    <div className="section-title">🎫 工单结果</div>
    {project.status === 'completed' && project.resolution_summary ? (
      <div className="text-sm mt-2 whitespace-pre-wrap" style={{ color: 'var(--color-text-primary)' }}>
        {project.resolution_summary}
      </div>
    ) : project.status === 'completed' ? (
      <div className="text-xs mt-2" style={{ color: 'var(--color-text-secondary)' }}>已完工但无处理结果记录</div>
    ) : (
      <button
        type="button"
        onClick={() => setShowCompleteModal(true)}
        className="mt-2 px-3 py-1.5 rounded text-xs text-white"
        style={{ background: '#22c55e' }}
      >
        ✅ 标记完工 + 填写处理结果
      </button>
    )}
  </div>
)}

{/* T-1106 完工 Modal */}
{showCompleteModal && (
  <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => !completing && setShowCompleteModal(false)}>
    <div className="w-full max-w-md rounded-2xl p-6" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }} onClick={(e) => e.stopPropagation()}>
      <h2 className="text-base font-semibold mb-3" style={{ color: 'var(--color-text-primary)' }}>完工归档</h2>
      <p className="text-xs mb-3" style={{ color: 'var(--color-text-secondary)' }}>填写处理结果(1-2048 字),完工后状态切为"已完成"</p>
      <textarea
        value={resolutionDraft}
        onChange={(e) => setResolutionDraft(e.target.value)}
        rows={5}
        maxLength={2048}
        placeholder="例:已联系供应商更换零件,验收通过;后续按原计划安排..."
        className="w-full px-3 py-2 rounded-lg text-sm outline-none resize-none"
        style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
      />
      <div className="text-[10px] mt-1" style={{ color: 'var(--color-text-secondary)' }}>{resolutionDraft.length}/2048</div>
      <div className="flex justify-end gap-3 mt-4">
        <button onClick={() => setShowCompleteModal(false)} disabled={completing} className="px-4 py-2 rounded-lg text-sm disabled:opacity-60" style={{ color: 'var(--color-text-secondary)', border: '1px solid var(--color-border-subtle)' }}>取消</button>
        <button onClick={handleComplete} disabled={completing || !resolutionDraft.trim()} className="px-4 py-2 rounded-lg text-sm text-white disabled:opacity-60" style={{ background: '#22c55e' }}>{completing ? '提交中...' : '确认完工'}</button>
      </div>
    </div>
  </div>
)}
```

**配套 state + handler**(Codex 按详情页现有 state 体例追加):

```typescript
const [showCompleteModal, setShowCompleteModal] = useState(false)
const [resolutionDraft, setResolutionDraft] = useState('')
const [completing, setCompleting] = useState(false)

async function handleComplete() {
  const trimmed = resolutionDraft.trim()
  if (!trimmed) return
  setCompleting(true)
  try {
    await updateProject(id, { status: 'completed', resolution_summary: trimmed } as any)
    toast.success('工单已完工归档')
    setShowCompleteModal(false)
    setResolutionDraft('')
    fetchAll()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || '完工失败')
  } finally {
    setCompleting(false)
  }
}
```

**说明**:
- **`updateProject` 类型签名**:T-1105 已存在(`updateProject = (id, data) => request.patch...`),T-1106 加 `as any` 兜底 `resolution_summary` 字段;若 T-1105 改了类型签名(spec §3.4.1 未明确改 updateProject signature),Codex 选 untyped 'any' 兼容
- ⚠️ **不动** 详情页现有 4 个 tab 渲染块(`overview / sprints / gates / members`)的现有内部 markup,只在 `overview` tab 末尾追加临时工单完工区块 + 末尾新增 `followups` tab 渲染块

### 3.8 测试新建(`backend/tests/test_phase11_followups.py` ~350 行 ~15 case)

#### 3.8.1 fixtures 消费(对齐 T-1104 / T-1105 体例)

- `db_session`(conftest.py autouse,rollback per case)
- `client`(conftest.py autouse,dependency_overrides)
- `_isolation_external_settings`(autouse fixture,T-1103 已落地)

#### 3.8.2 私有 helpers 命名前缀 `_phase11_followup_*`

```python
async def _cleanup_phase11_followup_test_data(db_session: AsyncSession) -> None:
    """清理 wechat_userid like "phase11_followup_%" + projects.code like "phase11_followup_%" 残留"""
    ...

def _phase11_followup_headers(token: str) -> dict[str, str]: ...

async def _phase11_followup_make_user(...) -> User: ...

async def _phase11_followup_make_project(
    db_session: AsyncSession,
    *,
    code: str,
    name: str = "测试工单",
    is_temporary: bool = True,
    creator: User,
) -> Project: ...
```

#### 3.8.3 ~15 case 命名锁定字面量

**Model 层(3 case)**:
1. `test_project_followup_basic_create_persists` — ORM 直接创建 → DB 反查命中
2. `test_project_followup_cascade_delete_with_project` — Project ON DELETE CASCADE 删除时 followup 一并清理
3. `test_project_resolution_summary_field_persists` — Project.resolution_summary 字段读写

**Router 层 — Followup APIs(5 case)**:
4. `test_post_followup_returns_201_with_basic_payload` — POST + content → 201 + 返回体含 id/project_id/content/created_at
5. `test_post_followup_employee_can_create_for_own_project` — employee 在自己参与的项目上可追加(RBAC 验证)
6. `test_post_followup_employee_cannot_create_for_other_project` — employee 在非自己参与的项目 → 404(_get_visible_project 拦截)
7. `test_get_followups_orders_by_created_desc` — GET 返回按 created_at 降序,最新在前
8. `test_get_followups_respects_limit_param` — `?limit=3` 只返回 3 条

**Router 层 — 临时工单完工守卫(3 case)**:
9. `test_patch_temporary_project_completed_without_resolution_400` — 临时项目 PATCH `{status:'completed'}` 缺 resolution_summary → 400
10. `test_patch_temporary_project_completed_with_resolution_success` — 临时项目 PATCH `{status:'completed', resolution_summary:'xxx'}` → 200 + DB 更新
11. `test_patch_main_project_completed_without_resolution_success` — 主干项目 PATCH `{status:'completed'}` 不要求 resolution_summary → 200

**Health Engine — Stale 联动(4 case)**:
12. `test_temporary_project_no_followup_uses_created_at_baseline` — 临时项目从未 followup,用 created_at 计 stale;< 7 天 → green
13. `test_temporary_project_stale_7_to_14_days_yellow` — 临时项目最近 followup > 7 < 14 天前 → yellow / score=60
14. `test_temporary_project_stale_over_14_days_red` — 临时项目最近 followup > 14 天前 → red / score=30
15. `test_temporary_project_completed_always_green` — 已 completed 临时项目无论 stale → green / 100

#### 3.8.4 测试纪律(对齐 T-1007 / T-1104 / T-1105 体例)

- 每 case 入口**强制** `await _cleanup_phase11_followup_test_data(db_session)`
- 作用域:`wechat_userid like "phase11_followup_%"` + `projects.code like "phase11_followup_%"`
- **零** mock / monkeypatch / skip / print / logger.* / sleep
- **临时项目 stale 测试用 fixture 操作时间**:用 `func.now() - interval '8 days'` 或 ORM `created_at = datetime.now(timezone.utc) - timedelta(days=8)` 直接构造,**严禁** `monkeypatch.setattr(date, 'today', ...)`(autouse `_isolation_external_settings` 不破坏 date 模块)

### 3.9 fail-safe self-check grep 闸门(Codex 提交前自跑,共 8 项)

```bash
cd backend
BASELINE_T1105=<T-1105 完工 chore(progress) commit hash>

# 1. 零 T-1105 文件踩踏
git diff $BASELINE_T1105..HEAD -- \
  app/routers/users.py \
  tests/test_phase11_project_members.py \
  | wc -l  # 必须 = 0

cd ../frontend
git diff $BASELINE_T1105..HEAD -- \
  src/api/users.ts \
  src/components/member-picker.tsx \
  src/app/projects/page.tsx \
  | wc -l  # 必须 = 0

# 2. project.py + projects.py + api/projects.ts 改动只在新增段(grep 关键字字面量)
cd ../backend
git diff $BASELINE_T1105..HEAD -- app/schemas/project.py | grep "^[+]" | grep -vE "ProjectFollowUp|ProjectComplete|resolution_summary" | grep -vE "^\+\+\+|^$|^\+#|^\+ *$" | wc -l  # 期望少量(import or 注释)
git diff $BASELINE_T1105..HEAD -- app/routers/projects.py | grep -vE "^[-+] " | wc -l  # 仅看 metadata 行,不影响验证

# 3. 零 T-1104 文件踩踏
git diff $BASELINE_T1105..HEAD -- \
  app/models/user.py \
  app/services/_department_resolver.py \
  app/services/department_service.py \
  tests/test_phase11_dept_fk.py \
  | wc -l  # 必须 = 0(本任零 T-1104 改动)

# 4. 零 conftest / _isolation / _db_url / env / README / DEPLOY / requirements
git diff $BASELINE_T1105..HEAD -- \
  conftest.py tests/_isolation.py tests/_db_url.py \
  .env.example pyproject.toml requirements.txt \
  | wc -l  # 必须 = 0

# 5. 零 services 非 health_engine 改动
git diff $BASELINE_T1105..HEAD -- app/services/ | grep "^\+\+\+" | grep -vE "health_engine\.py$" | wc -l  # 必须 = 0

# 6. 零 scheduled_tasks 改动
git diff $BASELINE_T1105..HEAD -- app/services/scheduled_tasks.py | wc -l  # 必须 = 0

# 7. 零无关前端页面改动
cd ../frontend
git diff $BASELINE_T1105..HEAD -- \
  src/app/dashboard/ src/app/admin/ src/app/users/ \
  src/app/login/ src/app/change-password/ \
  src/components/sidebar.tsx src/components/dashboard/ src/components/charts/ \
  | wc -l  # 必须 = 0

# 8. health_engine.py 改动只在 stale 常量 + temp 分支 + _compute_temp_stale_health(grep 字面量)
cd ../backend
git diff $BASELINE_T1105..HEAD -- app/services/health_engine.py | grep "^[+]" | grep -vE "STALE_|_compute_temp_stale_health|project_followup|is_temporary|^\+\+\+|^\+#|^\+ *$" | wc -l  # 期望少量(import 补全行)
```

---

## §4 文件改动清单(12 文件 = 8 改 + 3 新建 + docs)

### 4.1 backend(8 文件)

| # | 文件 | 类型 | 改动估算 |
|---|---|---|---|
| 1 | `backend/app/models/project_followup.py` | 新建 | ~75 行 |
| 2 | `backend/app/models/project.py` | 改 | +9 行(`resolution_summary` 字段,在 `deleted_at` 之前插入) |
| 3 | `backend/app/models/__init__.py` | 改 | +2 行(import + `__all__`) |
| 4 | `backend/alembic/versions/20260530_HHMM_phase11_project_followups.py` | 新建 | ~120 行 |
| 5 | `backend/app/schemas/project.py` | 改 | +~40 行(扩 `ProjectUpdate.resolution_summary` + 新增 `ProjectComplete` + `ProjectFollowUpCreate` + `ProjectFollowUpOut`)|
| 6 | `backend/app/routers/projects.py` | 改 | +~95 行(imports +5 + `update_project` 守卫 +~20 + 新增 `create_followup` + `list_followups` 2 端点 ~60) |
| 7 | `backend/app/services/health_engine.py` | 改 | +~50 行(2 行 import 补全 + 5 行 STALE 常量 + 临时分支重写 ~25 + `_compute_temp_stale_health` ~10) |
| 8 | `backend/tests/test_phase11_followups.py` | 新建 | ~350 行 ~15 case |

### 4.2 frontend(3 文件)

| # | 文件 | 类型 | 改动估算 |
|---|---|---|---|
| 9 | `frontend/src/api/projects.ts` | 改 | +~18 行(末尾追加 `ProjectFollowUp` interface + `createFollowup` + `listFollowups`) |
| 10 | `frontend/src/components/followup-timeline.tsx` | 新建 | ~180 行 |
| 11 | `frontend/src/app/project/[id]/page.tsx` | 改 | +~70 行(imports +1 + `activeTab` Union 扩 + tabs 数组扩 + followups 渲染块 + 临时完工 Modal + state 3 + handleComplete) |

### 4.3 docs(1 文件,chore commit 内)

| # | 文件 | 类型 | 改动估算 |
|---|---|---|---|
| 12 | `docs/dev_tasks.md` | 改 | +~35 / -2(Task 6 条目 `[/]` → `[x]` + 📣 锚点替换为 T-1106 完工字面量) |

### 4.4 严禁夹带清单(10 项)

零夹带闸门 — `git diff $BASELINE_T1105..HEAD` 必须**完全没有**触碰以下文件 / 路径:

1. T-1105 锁定文件中**本任不改动**的:`routers/users.py` / `tests/test_phase11_project_members.py` / `api/users.ts` / `components/member-picker.tsx` / `app/projects/page.tsx`
2. T-1104 5 backend 文件(Migration `20260529_1037_*.py` / `models/user.py` / `_department_resolver.py` / `department_service.py` / `tests/test_phase11_dept_fk.py`)
3. `backend/app/services/` 除 `health_engine.py` 外的任意文件(scheduled_tasks / capacity_engine / etc 全冻结)
4. `backend/app/routers/` 除 `projects.py` 外的任意文件
5. `backend/app/schemas/` 除 `project.py` 外的任意文件
6. `backend/app/models/` 除新增 `project_followup.py` + 改 `project.py` + 改 `__init__.py` 外的任意文件
7. `backend/conftest.py` / `tests/_isolation.py` / `tests/_db_url.py` / `.env*` / `README.md` / `DEPLOY.md`
8. `backend/pyproject.toml` / `backend/requirements.txt` / `backend/uv.lock`
9. `frontend/src/app/` 除新增 `project/[id]/page.tsx` 外的任意文件 + `frontend/src/components/` 除新建 `followup-timeline.tsx` 外的任意文件 + `frontend/src/api/` 除 `projects.ts` 外的任意文件
10. T-1105 进行中可能落下的 debug 文件(`backend/check_project.py` / `backend/check_users.py` / `backend/reset_admin.py` 等不归本任处置)

---

## §5 测试要求

### 5.1 ~15 case 命名 100% 字面量锁定(参 §3.8.3)

15 个 `async def test_*` 函数命名严格对齐 §3.8.3 字面量。Codex 改名 = BLOCKER 驳回。

### 5.2 helper 命名锁定

- `_cleanup_phase11_followup_test_data` 入口必跑
- `_phase11_followup_make_user` / `_phase11_followup_make_project` / `_phase11_followup_headers` 等 helper 前缀 `_phase11_followup_*` 严格

### 5.3 测试基线零回归承诺

- T-1105 完工预期 `205 passed, 2 skipped`
- T-1106 完工预期 `220 passed, 2 skipped`(+15 case)
- 全量 `pytest -q` 必须达成 220 / 2 / 0 failed,任一 case 回归 = BLOCKER 驳回

### 5.4 测试纪律

- **零** mock(包括 `unittest.mock` / `pytest-mock`)
- **零** monkeypatch(包括 `monkeypatch.setattr` / `monkeypatch.setenv`)
- **零** `@pytest.mark.skip` / `@pytest.mark.skipif`
- **零** `print(...)` / `logger.*` 调用
- **零** `time.sleep` / `asyncio.sleep`
- **零** 直接读 `os.environ` / `os.getenv`(autouse `_isolation_external_settings` 已 clean)
- Stale 时间偏移用 ORM `created_at = datetime.now(timezone.utc) - timedelta(days=N)` 直接构造,**严禁** `monkeypatch.setattr(date, 'today', ...)`

### 5.5 grep 闸门(Codex 提交前自跑)

```bash
cd backend
grep -E "mock|monkeypatch|skip|print\(|logger\.|asyncio\.sleep|time\.sleep|os\.(environ|getenv)" tests/test_phase11_followups.py | wc -l  # 必须 = 0
grep -c "^async def test_" tests/test_phase11_followups.py  # 必须 = 15
grep -c "_phase11_followup_" tests/test_phase11_followups.py  # 必须 ≥ 15
```

---

## §6 质量闸门(Codex 提交前必跑)

```bash
# 后端
cd backend
.venv/bin/ruff check app/models/project_followup.py app/models/project.py app/models/__init__.py app/schemas/project.py app/routers/projects.py app/services/health_engine.py tests/test_phase11_followups.py alembic/versions/20260530_*.py
.venv/bin/mypy app/models/project_followup.py app/models/project.py app/schemas/project.py app/routers/projects.py app/services/health_engine.py
.venv/bin/alembic upgrade head  # 期望:新 migration 应用成功
.venv/bin/alembic downgrade -1  # 期望:project_follow_ups + resolution_summary 反向 drop
.venv/bin/alembic upgrade head  # 期望:再次 upgrade,确认幂等
.venv/bin/pytest tests/test_phase11_followups.py -v  # 期望 15 passed
.venv/bin/pytest -q  # 期望 220 passed, 2 skipped(从 T-1105 完工基线 205 + 15)

# alembic check 跳过依据 T-1101/1102/1103 既定 Supervisor 特批(local DB drift 误报)

# 前端
cd ../frontend
npm run lint  # 期望 0 error
npm run typecheck  # 期望 0 error
```

**全绿后才能打 feat / chore 双 commit**。

---

## §7 commit 纪律

### 7.1 双 commit 原子收口

#### 7.1.1 第一 commit:feat(11 src/test/migration 文件)

```
feat(projects): T-1106 临时工单跟进追踪闭环 — followup 时间轴 + resolution_summary 强制 + stale 健康度联动

T-1106 Phase 11 第六任(老板追加需求):
- 过程追踪: 轻量级跟进时间轴(POST/GET /api/v1/projects/{id}/followups + ProjectFollowUp 表)
- 结果闭环: 临时工单 PATCH status='completed' 强制带 resolution_summary(400 拦截)
- 状态联动: 临时工单 stale 检测嵌入 refresh_project_health(7 天 yellow / 14 天 red)

依赖前置: T-1105 完工(基线 commit <T-1105 chore(progress) hash>)+ 指挥官二次验收 PASS

数据层:
- models/project_followup.py: 新建 ProjectFollowUp 表(append-only 时间轴)
- models/project.py: +5 字段 resolution_summary: Optional[String(2048)]
- models/__init__.py: +2 行暴露 ProjectFollowUp
- alembic/versions/20260530_*: 建表 + 加列 + 复合索引 + downgrade

后端 API:
- schemas/project.py: 扩 ProjectUpdate.resolution_summary + 新增 ProjectComplete + ProjectFollowUpCreate + ProjectFollowUpOut
- routers/projects.py: update_project 加临时工单完工守卫 + 新增 POST/GET /{id}/followups 2 端点
- services/health_engine.py: 追加 STALE_*_DAYS 常量 + refresh_project_health 临时分支重写(stale 检测)+ _compute_temp_stale_health 私有函数

前端接入:
- api/projects.ts: 末尾追加 ProjectFollowUp interface + createFollowup + listFollowups
- components/followup-timeline.tsx: 新建可控组件(textarea 输入 + 时间轴 + 相对时间)
- app/project/[id]/page.tsx: 加 activeTab='followups' tab + 临时工单完工 Modal + resolution_summary 回显

零回归承诺:
- T-1104 5 backend 文件零改动
- T-1105 8 文件中本任不改动的 5 文件零踩踏(routers/users.py + tests/test_phase11_project_members.py + api/users.ts + components/member-picker.tsx + app/projects/page.tsx)
- 主干项目健康度计算(compute_stage_health / _compute_health / refresh_sprint_health)零改动
- backend/.env* / conftest / _isolation / _db_url / scheduled_tasks / README / DEPLOY 零改动
- 现有 4 tab 渲染块(overview/sprints/gates/members)零改动
- 测试基线 T-1105 205 → T-1106 220 严格(+15 case)

[alembic check 跳过依据 T-1101/1102/1103 既定 Supervisor 特批 — local DB drift 误报]

Worker timestamp: [2026-05-30 HH:MM:SS]
```

**文件清单**(11 文件):
1. `backend/app/models/project_followup.py`
2. `backend/app/models/project.py`
3. `backend/app/models/__init__.py`
4. `backend/alembic/versions/20260530_*_phase11_project_followups.py`
5. `backend/app/schemas/project.py`
6. `backend/app/routers/projects.py`
7. `backend/app/services/health_engine.py`
8. `backend/tests/test_phase11_followups.py`
9. `frontend/src/api/projects.ts`
10. `frontend/src/components/followup-timeline.tsx`
11. `frontend/src/app/project/[id]/page.tsx`

#### 7.1.2 第二 commit:chore(progress)(1 文件)

```
chore(progress): close T-1106 — 临时工单跟进追踪闭环(过程时间轴 + 结果强制 + 状态联动)

完工概要:
- 过程: 轻量时间轴 ProjectFollowUp + 主干/临时项目共享 + RBAC = current_user(employee 可写自己项目)
- 结果: 临时工单完工强制 resolution_summary(1-2048 字符) + PATCH 守卫
- 联动: 临时项目 stale 健康度规则(< 7 天 green / 7-14 yellow / ≥ 14 red);已完工临时项目永远 green/100
- 测试: 15 case 严格(Model 3 + Followup APIs 5 + 完工守卫 3 + Stale 4)

文件改动:
- docs/dev_tasks.md: Task 6 [/] → [x] + 📣 锚点替换为 T-1106 完工字面量

严禁项遵守证据:
- 0 T-1105 5 文件踩踏(routers/users.py + tests/test_phase11_project_members.py + api/users.ts + components/member-picker.tsx + app/projects/page.tsx)
- 0 T-1104 5 文件踩踏
- 0 services 除 health_engine.py 外
- 0 routers 除 projects.py 外
- 0 schemas 除 project.py 外
- 0 主干项目健康度逻辑(compute_stage_health / _compute_health / refresh_sprint_health)
- 0 scheduled_tasks
- 0 conftest / _isolation / _db_url / .env* / README / DEPLOY / pyproject / requirements / uv.lock
- 0 前端 dashboard / admin / users / sidebar / login / change-password / projects/page.tsx
- 0 git push / stash / amend / rebase
- 0 测试 mock / monkeypatch / skip / print / logger / sleep
- 0 T-1107 / T-1108 自启

[alembic check 跳过依据 T-1101/1102/1103 既定 Supervisor 特批 — local DB drift 误报]

Worker timestamp: [2026-05-30 HH:MM:SS]
```

**文件清单**(1 文件):
1. `docs/dev_tasks.md`

### 7.2 commit 通用要求

- 双 commit 必带 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]`(CLAUDE.md #7)
- **严禁** `git push`(等指挥官接手二次验收)
- **严禁** `git stash`(跨 Agent 不可见,违反 CLAUDE.md #5)
- **严禁** amend / rebase 历史 commit(违反 CLAUDE.md #4)
- **严禁** `--no-verify` 跳过 pre-commit hook
- chore commit body 必含完工概要 + 文件清单 + 严禁项遵守证据(对齐 T-1103 + T-1104 + T-1105 风格)

---

## §8 验收清单(指挥官二次验收用,共 28 项)

### 8.1 改动面闸门(8 项)

1. ☐ 基线 commit 是 T-1105 完工 `chore(progress)` hash(`git log --oneline` 看到 T-1105 收口)
2. ☐ commit 链路干净:从 T-1105 完工出发,仅 3 commit(`chore(lock)` → `feat(projects)` → `chore(progress)`)
3. ☐ feat commit 严格 11 文件(对齐 §7.1.1 文件清单 1-11)
4. ☐ chore commit 严格 1 文件(`docs/dev_tasks.md`)
5. ☐ §4.4 零夹带闸门 10 项 grep 全 0
6. ☐ §3.9 fail-safe self-check 8 项 grep 全通过
7. ☐ Worker timestamp 双 commit 均带(grep `Worker timestamp` 各 1 hit)
8. ☐ chore commit body 含完工概要 + 文件清单 + 11 项严禁项遵守证据

### 8.2 数据层 + Schema 闸门(7 项)

9. ☐ `ProjectFollowUp` model 字面量对齐 §3.1.1(`content: Text nullable=False` + `project_id: UUID FK CASCADE` + `created_by: UUID FK SET NULL` 通过 BaseMixin + 复合索引 `(project_id, created_at)`)
10. ☐ `Project.resolution_summary: String(2048) nullable=True` 字面量对齐 §3.1.2(插入位置在 `deleted_at` 之前)
11. ☐ Migration upgrade 建表 + 加列 + 2 索引;downgrade 反向 4 步完整(drop_column → drop_index ×2 → drop_table)
12. ☐ `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` 来回幂等
13. ☐ `ProjectUpdate.resolution_summary: Optional[str] = Field(None, max_length=2048, ...)` 字面量对齐
14. ☐ 新增 `ProjectComplete` / `ProjectFollowUpCreate` / `ProjectFollowUpOut` 3 schemas 字段对齐 §3.2.3 / §3.2.4
15. ☐ `app/models/__init__.py` 新增 `ProjectFollowUp` import + `__all__` 插入式(零重排其他)

### 8.3 Router + Health Engine 闸门(7 项)

16. ☐ `update_project` 守卫字面量:`is_temporary + target_status='completed' + not resolution_summary` → 400 "临时工单完工必须填写处理结果..."
17. ☐ `update_project` 末尾追加健康度刷新(`refresh_project_health` 在 commit 后调用,触发条件 = status 切到 completed 或 resolution_summary 有写入)
18. ☐ POST `/{project_id}/followups` 端点字面量对齐 §3.3.3:`status_code=201` + RBAC `get_current_user` + `_get_visible_project` 守卫 + 临时项目追加后触发健康度刷新
19. ☐ GET `/{project_id}/followups` 端点字面量对齐 §3.3.3:`limit: int = Query(50, ge=1, le=200)` + 倒序 + outerjoin users 反查 `created_by_name`
20. ☐ `health_engine.py` 阈值常量追加:`STALE_YELLOW_DAYS = 7` + `STALE_RED_DAYS = 14`(L45 之后插入式)
21. ☐ `refresh_project_health` 临时分支重写对齐 §3.4.2:已 completed → green/100;无 followup → 用 created_at baseline;有 followup → 用 last_followup_at;走 `_compute_temp_stale_health` 阶梯
22. ☐ `_compute_temp_stale_health` 函数实现 3 阶梯(green/100 < 7 / yellow/60 [7,14) / red/30 ≥ 14)

### 8.4 前端闸门(3 项)

23. ☐ `frontend/src/api/projects.ts` 末尾追加 `ProjectFollowUp` interface + `createFollowup` + `listFollowups`(零改 T-1105 引入的 ProjectMemberInit/CreateProjectPayload/createProject)
24. ☐ `frontend/src/components/followup-timeline.tsx` 新建,可控组件含 textarea 输入区(maxLength=1024 + 字符计数)+ 时间轴(相对时间格式化)+ 空状态 + 加载状态
25. ☐ `frontend/src/app/project/[id]/page.tsx` 改造:`activeTab` Union 扩 'followups' + tabs 数组 +1 项 + followups 渲染块 + 临时工单完工 Modal + state 3(showCompleteModal/resolutionDraft/completing)+ handleComplete + resolution_summary 回显;零动现有 4 tab 渲染块内部 markup

### 8.5 测试 + 协议闸门(3 项)

26. ☐ 15 case 命名 100% 对齐 §3.8.3 字面量(`grep -c "^async def test_" tests/test_phase11_followups.py` = 15)
27. ☐ `pytest -q` 全量 `220 passed, 2 skipped`(从 T-1105 完工基线 205 + 15)
28. ☐ dev_tasks.md Task 6 标识 `[x] Done by Codex [YYYY-MM-DD HH:MM:SS]` + 📣 锚点替换为 T-1106 完工字面量

---

## §9 风险与回滚

### 9.1 风险点 6 项

| # | 风险 | 触发条件 | 应对 |
|---|---|---|---|
| 1 | **跨任竞争**:T-1106 起草在 T-1105 完工前;Codex 误以 T-1104 完工 commit 为基线启动 | Codex 接手 T-1106 时 git log 看不到 T-1105 chore(progress) | §1.3 + §2 #1 严禁项明示;Codex 接手探针强制核对 |
| 2 | **stale 阈值过严**:7 天 yellow / 14 天 red 在真实业务可能过严(某些工单本就跨月) | 用户反馈 yellow 太频繁 | 阈值常量集中 §3.4.1;T-1109+ 可单独提案 system_settings 配置化 |
| 3 | **`created_at` aware/naive 比较**:`datetime.now(timezone.utc) - last_followup_at` 若 last_followup_at 是 naive 会抛 TypeError | DB 反查 created_at 没正确反序列化为 aware datetime | BaseMixin `DateTime(timezone=True)` 保证 aware;§3.4.2 显式 `timezone.utc` |
| 4 | **临时工单已 completed 也走 stale**:已完工的工单也被算 stale red 不合理 | 没识别 completed 状态 | §3.4.2 优先级:已 completed → green/100 直接返回,不进 stale 分支 |
| 5 | **employee 滥用 followup**:任何 employee 都可往自己参与的项目追加 followup,可能被滥用为垃圾内容渠道 | 没限制频率 | §3.3.3 用 `_get_visible_project` 严格项目可见性;T-1109+ 可加 rate limit(本任不引入) |
| 6 | **健康度刷新性能**:每次 followup 追加都触发 `refresh_project_health` | 1 个临时项目 1 天 100 条 followup → 100 次刷新 | 临时项目 refresh 是 O(1) `func.max(created_at)` 单 SQL + 单 UPDATE,可忽略 |

### 9.2 回滚动作(production hot rollback)

```bash
# 一键回滚(数据完整保留)
cd backend && .venv/bin/alembic downgrade -1
# 结果:
# - project_follow_ups 表删除(所有跟进记录数据丢失;若已有重要 followup,先手工 dump)
# - projects.resolution_summary 列删除(完工归集数据丢失)
# - 主干项目逻辑零回滚影响

git revert <T-1106 feat commit>
git revert <T-1106 chore commit>
# 应用层代码回退:
# - update_project 守卫移除(临时工单可重新无 resolution_summary 完工)
# - health_engine.py 临时项目分支回到"固定 green/100"
# - 前端跟进 tab 移除 + 完工 Modal 移除
# - T-1104 / T-1105 落地代码不受影响
```

### 9.3 回滚后跟进

- 跟进记录 / resolution_summary 数据若有业务价值,production 回滚前必须先 `pg_dump --table=project_follow_ups --table=projects --column=resolution_summary` 备份
- 临时工单已完工的 `resolution_summary` 在 column drop 后无法恢复 — 慎重决策
- 指挥官二次验收 BLOCKER 时,可直接 `git revert <feat commit>` + `git revert <chore commit>`(双 commit 倒序 revert)

---

## §10 内部矛盾签字(指挥官 [2026-05-29 11:37:28])

本 spec 起草前已由指挥官在 Auto Mode 下做出 6 项关键架构决策,显式签字以利用户审阅 spec 时一次性拍板:

| # | 决策点 | 指挥官选择 | 理由 |
|---|---|---|---|
| 1 | **跟进记录数据模型** | A. 新建 `project_follow_ups` 独立表(BaseMixin + FK + 复合索引) | 可扩展(未来加 tags/attachments)+ 查询友好(JOIN users / WHERE project_id)+ 不污染 Project 表 |
| 2 | **三项功能覆盖范围** | 跟进记录:主干 + 临时共享 / resolution_summary:仅临时 / stale 健康度:仅临时 | 主干项目走 IPD gate 评审,有自己的结项 + 健康度;临时项目轻量化需要补齐三件套 |
| 3 | **状态联动实现方式** | 改写 `refresh_project_health` 临时分支(原 fixed green → stale rule)+ 复用现有 `run_health_refresh_all` 每日 task | 单点改造 + 零定时任务新增;主干项目分支零污染 |
| 4 | **stale 阈值配置化** | 硬编码常量(`STALE_YELLOW_DAYS = 7 / STALE_RED_DAYS = 14`) | 简化首版;T-1109+ 可单独提案 system_settings 表;现状测试基线零回归承诺优先 |
| 5 | **resolution_summary 强制时机** | PATCH `/projects/{id}` `is_temporary + status='completed'` 守卫(单点拦截) | 沿用现有 update_project 路径,避免新增 `POST /complete` 端点的契约扩散;前端可清晰映射到"标记完工"按钮 |
| 6 | **跟进记录删除权限** | 不允许删(append-only) | 审计友好 + 时间轴语义 + 首版简化;T-1109+ 视需开 admin 软删 |

### 10.1 spec 自洽校验

- 无内部矛盾(§3.1 字面量 + §3.2 字面量 + §3.3 字面量 + §3.4 字面量 + §3.5-3.7 前端字面量 + §3.8 case 命名 + §7 commit body 描述全数自洽)
- §3.4.2 临时项目分支 status 比较用 `getattr(project.status, "value", project.status) == "completed"` 兼容 SQLAlchemy enum vs str 双形态(对齐 `projects.py:468` `str(getattr(k, "value", k))` 体例)
- §3.4.3 `_compute_temp_stale_health` 阶梯 < 7 / [7,14) / ≥ 14 与 §3.4.1 常量定义 1:1 对齐
- §3.3.2 update_project 守卫 + §3.3.3 followups 端点共同覆盖 3 需求(过程 + 结果 + 联动)
- §8 28 项验收 8.1-8.5 分类与 §3 实施细则 6 节 1:1 映射

### 10.2 spec 起草盲点防御

- T-1102 spec 起草曾遗漏全仓 `.replace(...)` 11 处残留,T-1103 补救后形成"全仓 grep 闸门"经验。本任 T-1106 已对应预防:
  - §3.9 fail-safe self-check 8 项 grep 闸门由 Codex 在 commit 前自跑
  - §4.4 严禁夹带清单 10 项作为 spec 字面量,验收 §8.1 第 5-6 项作为指挥官二次验收闸门
- T-1106 严禁项 13 条 vs T-1105 12 条 + T-1104 12 条:新增 #1 "基线 commit 错误"针对 race 防御
- **关键防御 — T-1105 文件踩踏闸门**:§3.9 #1 grep 闸门 + §4.4 #1 严禁夹带清单 双层防御,Codex 接手任何 T-1105 文件改动 = BLOCKER 立即驳回(本任仅触碰 T-1105 文件中**本任增量段不重叠**的 3 文件 — schemas/project.py + routers/projects.py + api/projects.ts)
- §3.4.2 import `datetime, timezone` 补全:Codex 接手时 explicit check L24 现有 `from datetime import date, timedelta`,改为 `from datetime import date, datetime, timedelta, timezone`(spec §3.4.4)
- §3.7.5 `updateProject` 类型签名兼容:本任不改 T-1105 引入的 createProject 类型,但 updateProject 加 resolution_summary 字段需要类型签名扩;Codex 选 `as any` 兜底避免破坏 T-1105 编译契约

### 10.3 T-1105 完工依赖说明

- **本任 T-1106 spec 起草**(本 chore(spec) commit)= **独立**,不依赖 T-1105 完工
- **本任 T-1106 执行**(feat + chore(progress) 双 commit)= **严格依赖** T-1105 完工 + 二次验收 PASS
- Codex 接手 T-1106 时必跑探针:
  1. `git log --oneline -10` 看到 `chore(progress): close T-1105` commit
  2. `cat docs/dev_tasks.md | grep "Task 5"` 看到 `[x] Done by Codex`
  3. `git status` 工作树干净(零 modified;既定 untracked 不构成阻断)
  4. 指挥官二次验收回执已在 dev_tasks.md L? 写入 / 或经 Supervisor 明示放行
- **race 防御预案**:若 Codex 误以 T-1104 完工 commit 为基线接手 T-1106 → §2 #1 严禁项触发 BLOCKER 立即退回 + Worker 撤销 chore(lock) 等 T-1105 完工

---

## 📣 附录:给 Worker(Codex)的物理交接单

> **指挥官时间戳**:`[2026-05-29 11:37:28]`
> **当前持牌任务**:T-1106 候选 spec(临时工单跟进追踪闭环 — 老板追加需求)
> **依赖前置(BLOCKER)**:T-1105 完工 + 指挥官二次验收 PASS;本任执行**严格排在 T-1105 之后**

### 恢复执行指令(Codex 接手时必跑)

1. **静默 Git 探针**(CLAUDE.md #1):
   ```bash
   git status --short --branch
   git log -10 --oneline
   git diff
   git diff --cached
   git rev-list --left-right --count origin/main...HEAD
   ```
2. **依赖前置核对**(BLOCKER 守卫):
   ```bash
   # 必看到 T-1105 chore(progress) 在 log
   git log --oneline | grep "chore(progress): close T-1105" | wc -l  # 必须 ≥ 1

   # 必看到 dev_tasks.md Task 5 = [x]
   grep "T-1105.*Done by Codex" docs/dev_tasks.md | wc -l  # 必须 ≥ 1
   ```
3. **读盘**:
   - `docs/T-1106_spec.md` 全文(本文件,~XXX 行 10 章 + 📣 附录)
   - `docs/dev_tasks.md` 末尾 📣 锚点段(T-1106 持牌字面量)
   - `backend/app/models/project.py:82` (`deleted_at` 字段位置,resolution_summary 插入点)
   - `backend/app/models/__init__.py:43 + 67` (`ProjectStage` import 位置 + `__all__` 位置)
   - `backend/app/schemas/project.py` 完整文件(确认 T-1105 已落地的 ProjectMemberInit / ProjectCreate.members 段在哪;本任增量在末尾追加)
   - `backend/app/routers/projects.py` 完整文件(确认 T-1105 已改的 imports / create_project 段;本任改 update_project + 新增 followups 2 端点)
   - `backend/app/services/health_engine.py:36-45 + 182-188` (阈值常量块 + 临时项目分支)
   - `frontend/src/api/projects.ts` 末尾(确认 T-1105 末尾 export 的 createProject + types;本任末尾追加 followup APIs)
   - `frontend/src/app/project/[id]/page.tsx:1-50 + 129-134 + 390-460` (imports + tabs 数组 + members tab 渲染块体例)
4. **二次确认 alembic head**:
   ```bash
   cd backend && .venv/bin/alembic heads
   ```
   - 用实际 head 值更新本任新 migration 的 `down_revision` 字面量
5. **改 `docs/dev_tasks.md` Task 6 → `[/]`** + 单 commit `chore(lock): T-1106 开工`(CLAUDE.md #3 加锁)
   ```
   chore(lock): T-1106 开工 — Phase 11 第六任 临时工单跟进追踪闭环(老板追加需求)

   Worker timestamp: [2026-05-30 HH:MM:SS]
   ```
6. **按 §3 实施细则 11 文件改动**:
   - 3 新建 backend(`models/project_followup.py` + alembic migration + `tests/test_phase11_followups.py`)
   - 4 改 backend(`models/project.py` + `models/__init__.py` + `schemas/project.py` + `routers/projects.py` + `services/health_engine.py`)
   - 1 改 frontend(`api/projects.ts` 末尾追加)
   - 1 新建 frontend(`components/followup-timeline.tsx`)
   - 1 改 frontend(`app/project/[id]/page.tsx`)
   - 总计 11 src/test/migration 文件(对齐 §7.1.1 文件清单)
7. **§6 质量闸门 8+ 项全跑**:
   - ruff(8 backend 文件)
   - mypy(5 backend src 文件)
   - Alembic upgrade-downgrade-upgrade 来回幂等(`alembic check` 跳过依据 Supervisor 既定特批)
   - pytest 子集(15/15 PASS)+ 全量(220 passed + 2 skipped)
   - frontend lint + typecheck(零 error)
   - §3.9 fail-safe self-check 8 项 grep 全 0
   - §4.4 零夹带闸门 10 项 grep 全 0
8. **§7 commit 纪律 2 commit 原子收口**:
   - Commit 1:`feat(projects): T-1106 ...` 11 文件,Worker timestamp 必带,body 含 3 需求闭环 + 数据层 + 后端 API + 前端接入 + 零回归承诺
   - Commit 2:`chore(progress): close T-1106 ...` 1 文件(`docs/dev_tasks.md` Task 6 → `[x]` + 📣 锚点替换),Worker timestamp 必带 + body 含完工概要 + 文件清单 + 11 项严禁项遵守证据
9. **完工后停手汇报**:`「T-1106 完工,等待指挥官二次验收 + T-1107/T-1108 候选起草」`

### 严禁项再确认(BLOCKER 红线 13 项)

- 🚫 **严禁** 基线 commit 错误(Codex 接手前必看到 T-1105 chore(progress) 在 log + dev_tasks.md Task 5 = [x])
- 🚫 **严禁** 改 T-1105 引入的代码(`ProjectMemberInit` / `ProjectCreate.members` 字段 / `create_project` 成员批插逻辑 / `GET /users/picker` / `UserPickerItem` / `MemberPicker` / `getUserPicker` / `CreateProjectPayload` / 立项 Modal MemberPicker 块)
- 🚫 **严禁** 改 `health_engine.py` 主干项目分支(`compute_stage_health` / `_compute_health` / `refresh_sprint_health` 三函数 + L36-45 主干阈值常量)
- 🚫 **严禁** 改 `scheduled_tasks.py`(本任零定时任务新增)
- 🚫 **严禁** 改 `routers/projects.py` 除 `update_project` 函数外的任何已存在路由函数(`create_project` 在内,完全冻结)
- 🚫 **严禁** Migration 缺索引 / `downgrade()` 留空 / `NotImplementedError`
- 🚫 **严禁** 改 `backend/conftest.py` / `tests/_isolation.py` / `tests/_db_url.py` / `.env*` / `README.md` / `DEPLOY.md` / `pyproject.toml` / `requirements.txt` / `uv.lock`
- 🚫 **严禁** 改 T-1104 5 backend 文件 / T-1105 8 文件中本任不改动的 5 文件
- 🚫 **严禁** 改前端 dashboard / admin / users / sidebar / login / change-password / `projects/page.tsx`(本任前端改 detail page 单 page + 新建 timeline component + 末尾追加 api/projects.ts)
- 🚫 **严禁** 自启 T-1107 / T-1108 / 其他 Phase 11 候选议题(原 FK 第二阶段 / drop column / 物化视图 / KPI 钻取 / 前端看板)
- 🚫 **严禁** `git push` / `git stash` / amend / rebase / `--no-verify`
- 🚫 **严禁** 测试 mock / monkeypatch / skip / print / logger / sleep / 直接读 os.environ
- 🚫 **严禁** 改 `📣 附录` 位置 / 删除指挥官签字痕迹

### 回滚动作(production hot rollback)

```bash
cd backend && .venv/bin/alembic downgrade -1
# project_follow_ups 表 + projects.resolution_summary 列删除
# 警告:已有 followup + resolution_summary 数据丢失,production 回滚前必须 pg_dump 备份

git revert <T-1106 feat commit>
git revert <T-1106 chore commit>
# 应用层代码回退,T-1104 / T-1105 不受影响
```

### 二次验收前预案

- 若指挥官二次验收驳回 BLOCKER → 按 §10.2 spec 起草盲点防御惯例,Codex 单一原子 `fix(...)` commit 修复 + 保留二次验收记录
- 若指挥官接受非 BLOCKER 小减分 → 在 chore commit body 注明减分理由,T-1107 起草时统一收紧
- 若 T-1105 完工出现意外延期或被驳回 → T-1106 spec 保持落盘但 `[ ]` pending,Codex 不接手直到 T-1105 PASS

---

**🏁 spec 落盘完成。等待 T-1105 完工 + 二次验收 PASS 后,指挥官放牌 Codex 接手 T-1106 执行。**
