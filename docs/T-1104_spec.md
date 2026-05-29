# 📜 T-1104 执行契约 — Phase 11 第四任:`User.department` FK 双轨迁移(议题 ① 外键迁移 · 第一阶段)

> **起草时间戳**: `[2026-05-29 起草]`(由指挥官在 chore(spec) commit 落盘时填实)
> **指挥官**: Claude (Opus 4.7 / 1M)
> **Worker**: Codex(待指挥官接手)
> **基线 commit**: `2baaaed` docs(tasks): T-1103 二次验收通过(Phase 11 第三任收口)
> **alembic head**: `9a1b2c3d4e5f`(由 `b5e77c3 fix: harden security and deployment readiness` 引入,T-1102 + T-1103 未碰 alembic chain)
> **依赖前置**: T-1101 / T-1102 / T-1103 全闭环并 push origin/main(`origin/main...HEAD` 差异 0/0)

---

## §1 任务背景与范围(WHY + WHAT)

### 1.1 起源

- Phase 10 T-1003(`ad6643a`)落地 `departments` 独立表 + 7 seed(技术部 / 生产部 / 采购部 / 财务部 / 商务部 / 销售部 / 仓储部),`departments.manager_id` FK→`users.id` ON DELETE SET NULL 已正确建立。
- T-1003 spec 签字"**`User.department: VARCHAR(64)` 字段保留,FK 迁移延后到 Phase 11+**"(参见 `backend/app/models/department.py:7-8` 注释 + `docs/implementation-plan.md:826`)。
- Phase 10 T-1008(`5e5ce2b`)收尾文档(`docs/implementation-plan.md:853`)把 4 项 Phase 11 候选议题落盘:
  - **① `User.department` → `Department.id` FK 迁移(双轨融合)** ← 本任(T-1104)
  - ② 物化视图增量按部门聚合预热
  - ③ 前端 Tabs `by_project` 视图加权重柱状图 + 趋势线
  - ④ `Department.manager_id` 反查路径与 Phase 9 KPI `KpiScope=department` 打通
- Phase 11 已闭环 T-1101(测试基线 26 failures `1c67bd4` + `19ac08e`) + T-1102(测试隔离 + 配置漂移 `ddc41ba` + `9f6ab11`) + T-1103(隔离全局化 + 议题 C 残留 11 处 `e343db3` + `045533d` + `2baaaed`),工作树 clean,等待启动 T-1104。
- 指挥官 `[2026-05-29 早安战报启动]` 4 个候选议题中选定 ① 外键迁移,4 个起草前决策点全部按推荐选项拍板(详见 §10 内部矛盾签字)。

### 1.2 任务定位 — 议题 ① 外键迁移 · 第一阶段(3 任务渐进路径之一)

| 子任务 | 内容 | 状态 |
|---|---|---|
| **T-1104(本任)** | Migration + Model + backfill + Resolver helper + `department_service.get_department_with_members` 接入(双轨 OR 反查) | 起草中 |
| **T-1105(后续)** | 切剩余 36+ 处后端 routers/services 读路径用 Resolver helper + frontend schemas 扩 `department_id` output 字段(`schemas/user.py` / `schemas/report.py` / `schemas/department.py:61`)+ 写路径(`routers/users.py:188`)接入 `resolve_department_id_by_name` | 候选 backlog |
| **T-1106(后续)** | drop column `User.department VARCHAR(64)` + 删除 Resolver fallback 路径(`resolve_user_department_name` 简化为单一 FK 读) | 候选 backlog |

### 1.3 双轨纯增量策略(为何不一刀切)

**决策**:`User.department: VARCHAR(64)` 字段**保留不动**,新增 `User.department_id: UUID FK→departments.id ON DELETE SET NULL nullable=True index=True`。

**理由(对齐指挥官拍板理由)**:
1. **零回归承诺** — Phase 11 三任(T-1101/1102/1103)千辛万苦把测试基线从 `26 failures` 回滚到 `178 passed`,T-1104 一刀切改 36+ 处读路径会引爆测试基线,违反 Phase 11 全期"零回归"承诺。
2. **可回退** — Alembic downgrade -1 只 drop 新增列,VARCHAR 字段保留 = 数据零丢失,production 部署后任何异常可秒回。
3. **改造面分摊** — 36+ 处读路径 + 7 处写路径 + 6+ 个 frontend api 模块 + 3+ schema 类型,一任 commit 量 ≥ 20,Codex 难以一次性闭环;拆 3 任每任 ~150-200 行代码,符合 Codex 单任专注节奏。
4. **业务连续性** — production `User.department` 字符串字段还有 `routers/users.py:188` 等 7 个写路径在跑,双轨期前端可继续消费 `department: str`(T-1105 前完全不动)。

### 1.4 不做范围(BLOCKER 红线,留给 T-1105 / T-1106)

- ❌ **不动** `backend/app/routers/` 任意文件(20 处后端 routers 读路径全留给 T-1105)
- ❌ **不动** `backend/app/services/` 除 `department_service.py` + 新建 `_department_resolver.py` 外的任意文件(16 处 services 读路径 — `scheduled_tasks.py / admin_reports_service.py / capacity_engine.py / chat_tools/weekly_report.py / chat_tools/people.py` — 全留给 T-1105)
- ❌ **不动** `backend/app/schemas/` 任意文件(暴露给前端的 `department: str` 字段 — `user.py:44/56/70 / report.py:78 / department.py:61` — 全留给 T-1105 扩 `department_id`)
- ❌ **不动** `frontend/src/api/` 任意文件(6 个 api 模块 — `dashboard.ts / analytics.ts / admin.ts / users.ts / chat.ts / trends.ts` — 全留给 T-1105 扩类型)
- ❌ **不动** `backend/app/routers/users.py:188` 写路径(`user.department = req.department` — `routers/users.py:140/157/188/205/92` + `routers/auth.py:110/132` + `routers/reports.py:161` 共 7 处写入点全留给 T-1105 接入 `resolve_department_id_by_name`)
- ❌ **不动** Phase 9 KPI scope 路径(候选议题 ③ KPI 钻取留给 Phase 12+ T-1107+)
- ❌ **不动** Phase 10 dashboard tabs 可视化(候选议题 ④ 前端看板留给 Phase 12+)
- ❌ **不动** `backend/.env` / `backend/.env.example` / `DEPLOY.md` / `README.md`(T-1102 已闭环议题不重做)
- ❌ **不动** `backend/conftest.py` / `backend/tests/_isolation.py` / `backend/tests/_db_url.py`(T-1102/1103 已闭环议题不重做)
- ❌ **不动** `backend/pyproject.toml` / `backend/requirements.txt` / `backend/uv.lock`
- ❌ **不** drop column `User.department`(留给 T-1106)
- ❌ **不** 加 `relationship("Department", ...)` 到 `User` model(留给 T-1105 视实际 N+1 需要决定,避免 eager-load 性能误触)

---

## §2 严禁项(BLOCKER 红线 · 共 12 条)

| # | 严禁项 | 触发后果 |
|---|---|---|
| 1 | 任何 `backend/app/routers/` 改动 | BLOCKER 立即退回(本任不动 router 层) |
| 2 | 任何 `backend/app/services/` 改动,除白名单(`department_service.py` 内 `get_department_with_members` 单一函数 + 新建 `_department_resolver.py`) | BLOCKER 立即退回 |
| 3 | 任何 `backend/app/schemas/` 改动 | BLOCKER 立即退回(schemas 留给 T-1105) |
| 4 | 任何 `frontend/` 改动 | BLOCKER 立即退回 |
| 5 | 任何 `backend/conftest.py` / `backend/tests/_isolation.py` / `backend/tests/_db_url.py` 改动 | BLOCKER 立即退回(T-1102/1103 已闭环) |
| 6 | 任何 `backend/.env` / `backend/.env.example` / `README.md` / `DEPLOY.md` 改动 | BLOCKER 立即退回 |
| 7 | 任何 `backend/pyproject.toml` / `backend/requirements.txt` / `backend/uv.lock` 改动 | BLOCKER 立即退回 |
| 8 | Migration `downgrade()` 留空或抛 `NotImplementedError` | BLOCKER 立即退回(必须可回滚) |
| 9 | Migration backfill 失败时 silent 跳过 | BLOCKER 立即退回(必须输出 dry-run 报告) |
| 10 | 自启 T-1105 / T-1106 / 其他 Phase 11 候选议题 | BLOCKER 立即退回 |
| 11 | `git push` / `git stash` / `amend` / `rebase` | BLOCKER 立即退回 |
| 12 | 双 commit 任一缺 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 行(CLAUDE.md #7) | BLOCKER 立即退回 |

---

## §3 实施细则

### 3.1 Alembic Migration(新建,~80 行)

**文件名**:`backend/alembic/versions/20260529_HHMM_phase11_user_department_id_fk.py`
- `HHMM` 由 Codex 落盘时刻填入(对齐 Phase 10/11 既有 migration 命名惯例,见 `backend/alembic/versions/20260527_*` / `20260528_*`)
- revision id:Codex 自选 12 位 hex(对齐 Phase 10 `b58bb129c24b` / T-1102 `9a1b2c3d4e5f` 体例)
- `down_revision = "9a1b2c3d4e5f"`(当前 head 字面量)
- **接手探针**:Codex 接手时**必须**先 `cd backend && .venv/bin/alembic heads` 二次核验 head 仍是 `9a1b2c3d4e5f`,如已偏移以实际为准更新 `down_revision`(spec 字面量优先级 < alembic 实际 head)

#### 3.1.1 `upgrade()` 字面量

```python
"""Phase 11 T-1104: users.department_id FK to departments (dual-track).

Revision ID: <Codex 自选 12 位 hex>
Revises: 9a1b2c3d4e5f
Create Date: 2026-05-29 HH:MM:SS

T-1104 双轨纯增量:
  - 新增 users.department_id UUID FK→departments.id ON DELETE SET NULL nullable=True
  - 保留 users.department VARCHAR(64) 字段不动(T-1106 才 drop)
  - 一次性 backfill:UPDATE users SET department_id = d.id FROM departments d WHERE users.department = d.name AND users.department != ''
  - 严格 LEFT JOIN — unmapped 留 NULL,输出 dry-run 报告(N unmapped 部门名 + M 受影响 user)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "<Codex 自选 12 位 hex>"
down_revision = "9a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: 加 department_id 列(nullable=True,默认 NULL)
    op.add_column(
        "users",
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Step 2: 建 FK 约束(ON DELETE SET NULL,对齐 Department.manager_id 同语义)
    op.create_foreign_key(
        "fk_users_department_id_departments",
        "users",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Step 3: 建 index(对齐 Department.manager_id 同样有 index)
    op.create_index("ix_users_department_id", "users", ["department_id"])

    # Step 4: Backfill — 严格 LEFT JOIN,未命中保留 NULL
    bind = op.get_bind()
    result = bind.execute(sa.text(
        "UPDATE users SET department_id = d.id "
        "FROM departments d "
        "WHERE users.department = d.name AND users.department != ''"
    ))
    backfilled_count = result.rowcount

    # Step 5: Dry-run report — 输出 unmapped 部门名 + 受影响 user 数
    unmapped_rows = bind.execute(sa.text(
        "SELECT users.department AS dept_name, COUNT(*) AS user_count "
        "FROM users "
        "LEFT JOIN departments d ON users.department = d.name "
        "WHERE users.department != '' AND d.id IS NULL "
        "GROUP BY users.department "
        "ORDER BY user_count DESC"
    )).fetchall()

    print(f"[T-1104 backfill] {backfilled_count} users mapped to department_id")
    if unmapped_rows:
        print(f"[T-1104 backfill] {len(unmapped_rows)} unmapped department names:")
        for row in unmapped_rows:
            print(f"  - {row.dept_name!r}: {row.user_count} users")
    else:
        print("[T-1104 backfill] all non-empty department strings successfully mapped")


def downgrade() -> None:
    op.drop_index("ix_users_department_id", table_name="users")
    op.drop_constraint("fk_users_department_id_departments", "users", type_="foreignkey")
    op.drop_column("users", "department_id")
```

#### 3.1.2 字面量锁定表

| 项 | 字面量 |
|---|---|
| 列名 | `department_id` |
| 列类型 | `postgresql.UUID(as_uuid=True)` nullable=True |
| FK 约束名 | `fk_users_department_id_departments` |
| FK 引用 | `departments.id` ON DELETE `SET NULL` |
| Index 名 | `ix_users_department_id` |
| Backfill SQL | `UPDATE users SET department_id = d.id FROM departments d WHERE users.department = d.name AND users.department != ''` |
| Dry-run stdout 前缀 | `[T-1104 backfill]` |
| down_revision | `9a1b2c3d4e5f`(以 alembic heads 实际为准) |

### 3.2 ORM Model(改 `backend/app/models/user.py`,~5-8 行插入式)

**改动定位**:在 L53 `department: Mapped[str] = mapped_column(...)` 之后,插入新字段定义。

**插入字段字面量**:

```python
department_id: Mapped[Optional[uuid.UUID]] = mapped_column(
    ForeignKey("departments.id", ondelete="SET NULL"),
    index=True,
    nullable=True,
    comment="部门外键(T-1104 引入,与 department:VARCHAR(64) 双轨;T-1106 drop column 后成为单一真理源)",
)
```

**import 块增补**(若文件头未导入):
- `from typing import Optional`(若未导入)
- `from sqlalchemy import ForeignKey`(若未导入,通常 Phase 10 T-1003 后 User 模型不一定有,Codex 接手时 grep 确认)
- `import uuid`(若未导入)
- 现有 `Mapped, mapped_column` 等已存在,无需追加

**严禁项**:
- ❌ **不**动 L53 `department: Mapped[str]` 字段定义(`String(64), nullable=False, default=""` 字面量 0 改动)
- ❌ **不**改 `__repr__`(若存在)
- ❌ **不**改 `__init__` 自定义构造
- ❌ **不**加 `relationship("Department", ...)` 或 `back_populates`(留给 T-1105 评估)
- ❌ **不**改 Mapper 配置 / `__table_args__` / Index 集合

### 3.3 Resolver helper(新建 `backend/app/services/_department_resolver.py`,~65 行)

**文件名**:`backend/app/services/_department_resolver.py`(前缀 `_` 表示模块内部,对齐 Phase 9 `_kpi_internal.py`(如有)惯例 — 实际命名可由 Codex 在 grep 现有惯例后微调)

**文件全文字面量**:

```python
"""
T-1104 部门解析双轨读 helper —— department_id FK 优先 + fallback 到 department VARCHAR。

3 任务渐进路径(T-1104 → T-1105 → T-1106):
  - T-1104(本任): 引入 department_id 列 + backfill + 此 helper 在 department_service 内首次接入
  - T-1105: 切剩余 36+ 处后端 routers/services 读路径用此 helper,frontend schema 扩 department_id output 字段
  - T-1106: drop column User.department + 删此 fallback 路径(此 helper 简化为直读 department_id)

调用方应使用 await resolve_user_department_name(db, user) 而非直接 user.department,确保 T-1106 字段下线时调用面已统一切换。
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.user import User


async def resolve_user_department_name(
    db: AsyncSession,
    user: User,
) -> str:
    """返回 user 的部门名:department_id 优先 → fallback 到 department VARCHAR。

    - 若 user.department_id 非 NULL → JOIN departments 取 name 返回
    - 若 user.department_id 为 NULL → 返回 user.department(字符串字段,空串语义不变)
    - 若 department_id 非 NULL 但 Department 已被删(ON DELETE SET NULL 触发前的瞬态)
      → ORM 上 user.department_id 已被自动置 NULL,走 fallback 分支

    返回值约定:
        - 命中 FK:Department.name
        - 走 fallback:user.department(可能为空串 "")
        - 都不可用:空串 ""
    """
    if user.department_id is not None:
        result = await db.execute(
            select(Department.name).where(Department.id == user.department_id)
        )
        name = result.scalar_one_or_none()
        if name is not None:
            return name
    return user.department or ""


async def resolve_department_id_by_name(
    db: AsyncSession,
    name: str,
) -> Optional[uuid.UUID]:
    """工具函数:根据 name 反查 department_id(T-1105 用于 routers/users.py:188 写入路径)。

    - 输入空串 / None → 直接返回 None
    - 输入合法 name 但 departments 表无此 seed → 返回 None(由调用方决定 backfill / 报错 / 留 NULL)

    本任(T-1104)暂不接入写路径,只暴露给 T-1105 使用。
    """
    if not name:
        return None
    result = await db.execute(
        select(Department.id).where(Department.name == name)
    )
    return result.scalar_one_or_none()
```

### 3.4 接入点(改 `backend/app/services/department_service.py`,~6 行替换)

**严格仅改一个函数 `get_department_with_members`**,改动定位在现有 `User.department == dept.name` 等值反查的 stmt 构造段(参见 `backend/app/services/department_service.py:135`)。

#### 3.4.1 改前(基线)

```python
stmt = (
    select(User)
    .where(
        User.department == dept.name,
        User.is_active.is_(True),
        User.tenant_id == tenant_id,
    )
    .order_by(User.name)
)
```

#### 3.4.2 改后(双轨 OR 反查)

```python
stmt = (
    select(User)
    .where(
        sa.or_(
            User.department_id == dept.id,
            sa.and_(User.department_id.is_(None), User.department == dept.name),
        ),
        User.is_active.is_(True),
        User.tenant_id == tenant_id,
    )
    .order_by(User.name)
)
```

#### 3.4.3 口径锁定

- 双轨 OR 逻辑严格:`department_id == dept.id` **OR** `(department_id IS NULL AND department == dept.name)`
- 优先 FK 反查(覆盖 T-1104 backfill 成功的用户)
- FK 未填充的老数据(backfill unmapped 残留 + 后续手工建用户未填 FK)走字符串 fallback
- **不**改其他 `User.department` 引用点(其他 36+ 处统统留给 T-1105)
- **不**改 `_map_value_error` / `list_departments` / `create_department` / `update_department` / `delete_department` / `_check_manager_id_exists`(如有)等任何业务逻辑函数
- **不**动 import 块除非必须(若现有 `from sqlalchemy import ...` 已含 `or_, and_`,无需改;否则补 `from sqlalchemy import and_, or_`)

#### 3.4.4 import 探针

Codex 接手时先 `grep -n "from sqlalchemy" backend/app/services/department_service.py`,确认 `and_` / `or_` 是否已导入。若已导入,直接 `sa.or_` 写法不可用(因为 import 形式不同),则改用 `or_(...)` / `and_(...)` 裸函数;若未导入,优先按 `sa.or_` / `sa.and_` 形式(前提:文件头有 `import sqlalchemy as sa`)。

**字面量优先级**:实际改后代码必须语义对齐 §3.4.2,具体 `sa.` 前缀还是裸函数由 Codex 按文件现有 import 风格自洽。

### 3.5 范围严格闸门 — fail-safe self-check

Codex 完工 commit 前必须自跑以下 grep 闸门,任一非 0 即 BLOCKER 立即退回:

```bash
# 1. 零 router 夹带
git diff <baseline>..HEAD -- backend/app/routers/ | wc -l  # 期望 0

# 2. 零 schema 夹带
git diff <baseline>..HEAD -- backend/app/schemas/ | wc -l  # 期望 0

# 3. 零 frontend 夹带
git diff <baseline>..HEAD -- frontend/ | wc -l  # 期望 0

# 4. 零 services 夹带(除 department_service.py + 新建 _department_resolver.py)
git diff <baseline>..HEAD -- backend/app/services/ | grep -E '^\+\+\+ b/backend/app/services/' | grep -v -E '(department_service\.py|_department_resolver\.py)' | wc -l  # 期望 0

# 5. 零 conftest / isolation / _db_url 夹带
git diff <baseline>..HEAD -- backend/conftest.py backend/tests/_isolation.py backend/tests/_db_url.py | wc -l  # 期望 0

# 6. 零 env / readme / deploy 夹带
git diff <baseline>..HEAD -- backend/.env backend/.env.example README.md DEPLOY.md | wc -l  # 期望 0

# 7. 零 pyproject / requirements 夹带
git diff <baseline>..HEAD -- backend/pyproject.toml backend/requirements.txt backend/uv.lock | wc -l  # 期望 0
```

`<baseline>` = `2baaaed`(T-1103 docs 二次验收 commit)。

---

## §4 文件改动清单

### 4.1 新建(3 文件)

| # | 路径 | 预估行数 | 类型 |
|---|---|---|---|
| 1 | `backend/alembic/versions/20260529_HHMM_phase11_user_department_id_fk.py` | ~80 行 | Alembic migration |
| 2 | `backend/app/services/_department_resolver.py` | ~65 行 | Service helper |
| 3 | `backend/tests/test_phase11_dept_fk.py` | ~280 行 / ~15 case | 测试 |

### 4.2 改动(2 文件)

| # | 路径 | 预估变更 | 类型 |
|---|---|---|---|
| 4 | `backend/app/models/user.py` | +5~8 / -0(插入式) | ORM Model |
| 5 | `backend/app/services/department_service.py` | +5 / -3(单函数 stmt 替换) | Service 接入 |

### 4.3 Docs(1 文件,改)

| # | 路径 | 预估变更 | 类型 |
|---|---|---|---|
| 6 | `docs/dev_tasks.md` | Task 4 → `[x]` + 📣 锚点替换(+~15 / -~5) | 看板 |

### 4.4 不归 Codex 范围(指挥官二次验收时改)

- `docs/recap.md` — Phase 11 候选状态更新(T-1104 完工记录)
- `docs/implementation-plan.md` — 视需要追加 Phase 11 实施段(留给 T-1106 收口时统一写)

### 4.5 严禁夹带(任一改动 = BLOCKER)

- `backend/app/routers/*.py` 任意文件
- `backend/app/schemas/*.py` 任意文件
- `backend/app/services/*.py` 除 `department_service.py`(单函数) + 新建 `_department_resolver.py` 外的任意文件
- `frontend/**`
- `backend/conftest.py` / `backend/tests/_isolation.py` / `backend/tests/_db_url.py`
- `backend/.env*` / `README.md` / `DEPLOY.md`
- `backend/pyproject.toml` / `backend/requirements.txt` / `backend/uv.lock`
- `backend/alembic/env.py` / `backend/alembic.ini`(env 配置不动)

---

## §5 测试要求

### 5.1 新建 `backend/tests/test_phase11_dept_fk.py`(~280 行 / ~15 case)

#### Model 层(3 case)

```
test_user_department_id_nullable
  - 创建 User(department_id=None) → 持久化成功,department_id 字段为 NULL
test_user_department_id_set_to_department
  - 创建 Department + User(department_id=dept.id) → 持久化成功,fresh load 后 department_id 等于 dept.id
test_user_department_id_fk_set_null_on_department_delete
  - 创建 Department + User(department_id=dept.id) → 删 Department → fresh load user → department_id 自动 NULL(ON DELETE SET NULL 验证)
```

#### Backfill 层(3 case,直接 SQL UPDATE 验证 migration 逻辑)

```
test_backfill_maps_existing_department_string
  - User(department="技术部", department_id=None) + Department("技术部")
  - 跑 backfill SQL → user fresh load,department_id == 技术部.id
test_backfill_skips_unmapped_department_string
  - User(department="开发部", department_id=None) 但 departments 表无 "开发部"
  - 跑 backfill SQL → user fresh load,department_id 仍 NULL,department 字符串保留
test_backfill_skips_empty_department_string
  - User(department="", department_id=None)
  - 跑 backfill SQL → user fresh load,department_id 仍 NULL(WHERE 子句过滤 != "")
```

#### Resolver 层(4 case)

```
test_resolve_returns_department_name_via_fk
  - User(department_id=dept.id, department="旧名漂移") + Department(name="技术部", id=dept.id)
  - resolve_user_department_name(db, user) == "技术部"(FK 优先,字符串字段被忽略)
test_resolve_fallback_to_string_when_id_null
  - User(department_id=None, department="销售部")
  - resolve_user_department_name(db, user) == "销售部"(走 fallback)
test_resolve_fallback_to_empty_when_both_null
  - User(department_id=None, department="")
  - resolve_user_department_name(db, user) == ""
test_resolve_department_id_by_name_returns_uuid
  - Department(name="技术部")
  - resolve_department_id_by_name(db, "技术部") == 技术部.id
  - resolve_department_id_by_name(db, "不存在") is None
  - resolve_department_id_by_name(db, "") is None
```

#### Service 层接入测试(5 case)

```
test_get_department_with_members_returns_fk_users
  - Department("技术部") + User(department_id=技术部.id, department="技术部", is_active=True)
  - get_department_with_members(技术部.id) → members 包含此 user
test_get_department_with_members_returns_fallback_users
  - Department("技术部") + User(department_id=None, department="技术部", is_active=True)
  - get_department_with_members(技术部.id) → members 仍包含此 user(双轨 OR 命中 fallback 分支)
test_get_department_with_members_excludes_inactive
  - Department + 1 个 is_active=True + 1 个 is_active=False 用户(都对齐 dept)
  - members 仅含 active 用户
test_get_department_with_members_excludes_other_tenant
  - Department(tenant_id="default") + User(department_id=dept.id, tenant_id="other")
  - members 不含 other 租户用户
test_get_department_with_members_returns_empty_when_no_match
  - Department 无任何 user 对齐(双轨都不命中)
  - members 返回空列表 []
```

### 5.2 测试纪律(严格遵循 T-1003/1007/1103 体例)

- ✅ 消费 `db_session` + `client` + `_isolation_external_settings` 已有 autouse fixture(由 T-1102/1103 提供)
- ✅ 私有 helpers 命名前缀 `_phase11_*`(`_cleanup_phase11_test_data / _phase11_make_user / _phase11_make_department / _phase11_headers`)
- ✅ 每 case 入口必跑 `await _cleanup_phase11_test_data(db_session)`
- ✅ `_cleanup_phase11_test_data` 作用域至 `wechat_userid like "phase11_%"` + `departments.name like "phase11_%"`(避免污染 Phase 10 7 seed)
- ✅ 测试库 URL 通过 `derive_test_database_url(settings.database_url)`(T-1102 helper)+ `from tests._db_url import derive_test_database_url`
- ❌ 不 mock / 不 monkeypatch ORM 层 / 不 stub Database 连接
- ❌ 不 skip / 不 print / 不 logger 输出
- ❌ 不动 `conftest.py`
- ❌ 不动 `_isolation.py` / `_db_url.py`
- ❌ 不新建 fixture(除 case 内部 helper 函数)

### 5.3 测试基线

| 阶段 | passed | skipped | failed |
|---|---|---|---|
| T-1103 完工基线(`2baaaed`) | **178** | 2 | 0 |
| T-1104 完工预期 | **193**(178 + 15) | 2 | 0 |

**零回归**:旧 178 个 case 全部继续 PASS(双轨期不破坏现有读路径,`department_service.get_department_with_members` 的旧 case 应同时命中 fallback 分支)。

---

## §6 质量闸门(Codex commit 前必跑)

```bash
# 1. 后端 lint(目标 4 文件,严格作用域)
cd backend && .venv/bin/ruff check \
    app/models/user.py \
    app/services/_department_resolver.py \
    app/services/department_service.py \
    tests/test_phase11_dept_fk.py

# 2. 后端类型检查(目标 3 src 文件)
cd backend && .venv/bin/mypy \
    app/models/user.py \
    app/services/_department_resolver.py \
    app/services/department_service.py

# 3. Alembic 闸门(upgrade-downgrade-upgrade 来回 PASS)
cd backend && .venv/bin/alembic upgrade head
cd backend && .venv/bin/alembic check
cd backend && .venv/bin/alembic downgrade -1
cd backend && .venv/bin/alembic upgrade head

# 4. 单元测试(新文件全 PASS)
cd backend && .venv/bin/pytest tests/test_phase11_dept_fk.py -v

# 5. 全量回归(193 passed, 2 skipped)
cd backend && .venv/bin/pytest -q

# 6. 前端 lint + typecheck(零改动应清白)
cd frontend && npm run lint && npm run typecheck
```

#### 6.1 已知特批跳过项(Supervisor 签字)

- `alembic check` 在 Codex 环境可能因 local DB drift 误报(`T-1101` / `T-1102` / `T-1103` 已多次特批跳过,见 dev_tasks.md L226 / L242 / L249)。如本任 `alembic check` 在 Codex 环境继续误报,凭既定特批跳过,但需在 `chore(progress)` commit body 中注明"alembic check 跳过依据 T-1101/1102/1103 特批"。
- 前端 lint/typecheck 若 frontend/ 完全 0 改动,跑出全绿是预期;若出现非 0 报错则 BLOCKER(说明范围严格闸门 §3.5 失守)。

---

## §7 commit 纪律(严格 2 commit 原子收口)

### 7.1 Commit 1 — feat(models)

```
feat(models): T-1104 User.department_id FK 双轨迁移 第一阶段 — Migration + ORM + Resolver helper + department_service 接入

议题 ① 外键迁移 · 第一阶段(3 任务渐进 T-1104 → T-1105 → T-1106 之首):

- backend/alembic/versions/20260529_HHMM_phase11_user_department_id_fk.py:
  - 新增 users.department_id UUID FK→departments.id ON DELETE SET NULL nullable=True
  - 建 fk_users_department_id_departments 约束 + ix_users_department_id 索引
  - 一次性 backfill:UPDATE users SET department_id = d.id FROM departments d
    WHERE users.department = d.name AND users.department != ''
  - 严格 LEFT JOIN — unmapped 留 NULL,stdout 输出 dry-run 报告
    (backfilled N + unmapped 部门名+ user 数明细)
  - downgrade() 反向 drop_index → drop_constraint → drop_column 3 步可回滚
- backend/app/models/user.py:
  - 插入式 +5~8 行,新增 department_id: Mapped[Optional[uuid.UUID]]
    + ForeignKey("departments.id", ondelete="SET NULL") + index=True
  - department: VARCHAR(64) 字段保留不动(T-1106 才 drop)
- backend/app/services/_department_resolver.py:
  - 新建 ~65 行,resolve_user_department_name + resolve_department_id_by_name 双 helper
  - FK 优先 → fallback 到 VARCHAR 字符串,T-1106 简化为单一 FK 路径
- backend/app/services/department_service.py:
  - 仅 get_department_with_members 内 stmt 改双轨 OR(~5 行替换)
  - or_(department_id == dept.id, and_(department_id IS NULL, department == dept.name))
  - 其他函数零改动(list/create/update/delete + _map_value_error 全冻结)
- backend/tests/test_phase11_dept_fk.py:
  - 新建 ~280 行 ~15 case,覆盖 Model 3 + Backfill 3 + Resolver 4 + Service 5
  - 消费 db_session + _isolation_external_settings autouse fixture
  - _cleanup_phase11_test_data 入口必跑,作用域 wechat_userid+departments name like 'phase11_%'

闸门全绿:ruff/mypy 4+3 文件 / alembic upgrade-downgrade-upgrade 来回 PASS /
pytest 子集 15/15 PASS + 全量 193 passed + 2 skipped 零回归 /
frontend lint+typecheck 干净。

零夹带:0 router / 0 schema / 0 frontend / 0 conftest / 0 _isolation /
0 _db_url / 0 .env* / 0 README / 0 DEPLOY / 0 pyproject / 0 requirements。

后续 T-1105 接入剩余 36+ 处后端读路径 + frontend schema 扩 + 写路径,
T-1106 drop column 收口。

Worker timestamp: [2026-05-29 HH:MM:SS]
```

**文件清单**(5 文件):
1. `backend/alembic/versions/20260529_HHMM_phase11_user_department_id_fk.py`(新建)
2. `backend/app/models/user.py`(改)
3. `backend/app/services/_department_resolver.py`(新建)
4. `backend/app/services/department_service.py`(改)
5. `backend/tests/test_phase11_dept_fk.py`(新建)

### 7.2 Commit 2 — chore(progress)

```
chore(progress): close T-1104 — Phase 11 第四任 User.department FK 双轨迁移第一阶段完工

完工概要:
- 议题 ① 外键迁移 · 第一阶段闭环(双轨纯增量策略,零回归)
- 5 backend 文件改动:2 新建 + 2 改 + 1 新建 test(严格作用域,零夹带)
- Migration up/down 来回可回滚验证(VARCHAR 字段保留 = 数据零丢失)
- 双轨 OR 反查口径锁定:FK 优先 → fallback 到 VARCHAR
- Resolver helper 已就位,等待 T-1105 接入剩余 36+ 处后端读路径
- 测试基线零回归:T-1103 178 passed → T-1104 193 passed + 2 skipped

文件改动:
- docs/dev_tasks.md: Task 4 [/] → [x] + 📣 锚点替换为 T-1104 完工

严禁项遵守证据:
- 0 router (backend/app/routers/)
- 0 schema (backend/app/schemas/)
- 0 frontend (frontend/)
- 0 conftest / _isolation / _db_url
- 0 .env* / README / DEPLOY
- 0 pyproject / requirements / uv.lock
- 0 git push / stash / amend / rebase
- 0 T-1105 自启

[alembic check 跳过依据 T-1101/1102/1103 既定 Supervisor 特批 — local DB drift 误报]

Worker timestamp: [2026-05-29 HH:MM:SS]
```

**文件清单**(1 文件):
1. `docs/dev_tasks.md`

### 7.3 commit 通用要求

- 双 commit 必带 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]`(CLAUDE.md #7)
- **严禁** `git push`(等指挥官接手二次验收)
- **严禁** `git stash`(跨 Agent 不可见,违反 CLAUDE.md #5)
- **严禁** amend / rebase 历史 commit(违反 CLAUDE.md #4)
- **严禁** `--no-verify` 跳过 pre-commit hook

---

## §8 验收清单(指挥官二次验收用,共 28 项)

### 8.1 改动面闸门(7 项)

1. ☐ commit 链路干净:从 `2baaaed` 出发,仅 2 commit(`feat(models)` → `chore(progress)`)
2. ☐ feat commit 严格 5 文件:`alembic/versions/20260529_*.py` 新建 + `app/models/user.py` 改 + `app/services/_department_resolver.py` 新建 + `app/services/department_service.py` 改 + `tests/test_phase11_dept_fk.py` 新建
3. ☐ chore commit 严格 1 文件:`docs/dev_tasks.md`
4. ☐ **零夹带闸门** §3.5 grep 7 项全 0:`git diff 2baaaed..HEAD -- backend/app/routers/ backend/app/schemas/ frontend/ backend/conftest.py backend/tests/_isolation.py backend/tests/_db_url.py backend/.env.example README.md DEPLOY.md backend/pyproject.toml backend/requirements.txt` 完全空
5. ☐ 4 既定 untracked 保留未污染(`backend/.env` / `backend/uv.lock` / 历史既定 2 项)
6. ☐ Worker timestamp 双 commit 均带(grep `Worker timestamp` 各 1 hit)
7. ☐ chore commit body 含完工概要 + 文件清单 + 严禁项遵守证据(对齐 T-1103 chore 风格,审计可读性收紧)

### 8.2 Migration 闸门(5 项)

8. ☐ Migration 文件命名对齐 `20260529_HHMM_phase11_user_department_id_fk.py`(HHMM 反映 Codex 实际落盘时刻)
9. ☐ `down_revision = "9a1b2c3d4e5f"`(或对齐 Codex 接手时 alembic heads 实际值)
10. ☐ upgrade() 字面量对齐 §3.1:列名 `department_id` / 列类型 `postgresql.UUID(as_uuid=True)` / FK 名 `fk_users_department_id_departments` / index 名 `ix_users_department_id` / ON DELETE `SET NULL`
11. ☐ downgrade() 反向 3 步完整:drop_index → drop_constraint → drop_column
12. ☐ `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` 来回 PASS,backfill stdout 命中 `[T-1104 backfill]` 字面量

### 8.3 Model + Service 闸门(6 项)

13. ☐ `User.department: Mapped[str]` 字段 L53 原行 **0 删除**(`git diff 2baaaed..HEAD -- backend/app/models/user.py | grep "^-[^-]" | grep "department:" | wc -l` = 0)
14. ☐ `User.department_id` 字段命名 + `ForeignKey("departments.id", ondelete="SET NULL")` + `index=True` + `nullable=True` 字面量对齐 §3.2
15. ☐ `_department_resolver.py` 2 公开函数命名:`resolve_user_department_name` / `resolve_department_id_by_name`,零 HTTPException / 零 print / 零 logger
16. ☐ `department_service.get_department_with_members` stmt 改为双轨 OR(`sa.or_` 或 `or_` 视 import 风格自洽,语义对齐 §3.4.2)
17. ☐ `department_service.py` 其他函数**零改动**:`list_departments` / `create_department` / `update_department` / `delete_department` / `_map_value_error` 全部不动
18. ☐ `app/models/__init__.py` 与现有 `Department` import 体例对齐(若 `_department_resolver` 不在 `__init__.py` 暴露体例内,跳过此项)

### 8.4 测试闸门(8 项)

19. ☐ 测试 ~15 case 命名 100% 对齐 §5.1 字面量(grep `^async def test_` 命中数 = 15)
20. ☐ 4 类 case 分布:Model 3 + Backfill 3 + Resolver 4 + Service 5
21. ☐ 测试零 mock / 零 monkeypatch / 零 skip / 零 print / 零 logger(grep `mock|monkeypatch|skip|print|logger\.` 严禁字 0 hit)
22. ☐ `_cleanup_phase11_test_data` helper 入口存在,作用域至 `wechat_userid like "phase11_%"` + `departments.name like "phase11_%"`
23. ☐ `_phase11_make_user / _phase11_make_department` 等 helper 命名前缀 `_phase11_*`(对齐 T-1007 `_phase10_*` 体例)
24. ☐ `pytest tests/test_phase11_dept_fk.py -v` 全 PASS(15/15)
25. ☐ `pytest -q` 全量 `193 passed, 2 skipped`(从 T-1103 完工基线 178 + 新增 15)
26. ☐ `ruff check` + `mypy` 目标 4+3 文件全绿

### 8.5 文档 + 协议闸门(2 项)

27. ☐ dev_tasks.md Task 4 标识 `[x] Done by Codex [YYYY-MM-DD HH:MM:SS]`
28. ☐ dev_tasks.md 末尾 📣 锚点替换为 T-1104 完工字面量(待指挥官二次验收的口径)+ Phase 11 候选 backlog 状态更新(T-1105 候选 + T-1106 候选)

---

## §9 风险与回滚

### 9.1 风险点 5 项

| # | 风险 | 触发条件 | 应对 |
|---|---|---|---|
| 1 | **Backfill 与现有数据软冲突** | `users.department` 有 `"技术部 "`(尾空格)/ 大小写差异 / 半角全角混排 | Migration 输出 dry-run 报告(N unmapped 部门名)给指挥官人工审阅,不引入自动数据清洗。Codex 不改 backfill SQL 添加 TRIM/LOWER |
| 2 | **departments 7 seed 与现有数据严重不重叠** | production 数据库 `users.department` 多数是"开发组"/"产品组"等非 seed 部门 | Backfill 大面积 unmapped,字符串 fallback 仍可用,**业务零损失**,留给后续手工扩 seed 或 T-1105 决策 |
| 3 | **Migration 跨环境 backfill 时机** | Production 部署 → upgrade head → 一次性 backfill | Backfill 用 SQL UPDATE 在 migration 事务内,失败自动 rollback(Alembic auto-transaction);Codex 不需要写 try/except |
| 4 | **双轨读 OR 性能影响** | `get_department_with_members` 改 OR 后扫表代价从 1 谓词变 2 谓词 | 当前 dept 反查在小表(单 dept 通常 < 100 users + tenant_id 隔离),P95 影响可忽略。真正性能优化(T-1106 drop column 后只读 department_id)留给后续 |
| 5 | **测试基线回归** | 双轨 OR 改动若 SQL 语义错误,可能破坏现有 Phase 10 T-1007 测试 | 测试要求 §5.3 强制 `pytest -q` 全量 193 passed,Phase 10 T-1004/1005/1007 等现有 case 必须全部继续 PASS |

### 9.2 回滚动作(production hot rollback)

```bash
# 一键回滚(production 环境)
cd backend && .venv/bin/alembic downgrade -1
# 结果:
# - users.department_id 列 + FK + index 删除
# - users.department VARCHAR(64) 字段数据完整保留
# - 任何依赖 user.department 字符串字段的现有路径继续 work(36+ 处后端读 + 7 处写 + frontend api)
# - 影响时间窗口:< 1 秒(单 ALTER TABLE DROP COLUMN + DROP CONSTRAINT)
```

### 9.3 回滚后跟进

- Codex commit 不会破坏 main 分支(本任不 push),回滚仅针对已 upgrade 的本地 / staging / production 数据库
- 指挥官二次验收 BLOCKER 时,可直接 `git revert <feat commit>` + `git revert <chore commit>`(双 commit 倒序 revert),无需 force-push

---

## §10 内部矛盾签字(指挥官 [2026-05-29])

本 spec 起草前已与指挥官 `[2026-05-29 早安战报启动]` 4 个关键决策点交叉拍板:

| # | 决策点 | 指挥官选择 | 理由 |
|---|---|---|---|
| 1 | **迁移路径** | 方案 A 双轨纯增量(推荐) | 零回归 + 可回退 + 改造面分摊 + 业务连续性 |
| 2 | **缺失部门处理** | i 严格保留 NULL(推荐) | 数据透明 + 财务顺序锁定 + 零变量 + 不破坏 7 seed |
| 3 | **FK ON DELETE 行为** | SET NULL(推荐) | 对齐 `Department.manager_id` 同语义 + 不阶联删用户 |
| 4 | **工程粒度** | 拆 3 任务渐进(推荐) | 每任 ~150-200 行可控 + Codex 单任专注节奏 + 测试基线可逐任校验 |

#### 10.1 spec 自洽校验

- 无内部矛盾(spec §3.1 字面量 + §3.2 字面量 + §3.4 字面量 + §5.1 case 命名 + §7 commit body 描述全数自洽)
- §3.4.4 import 探针给出"sa. 前缀 vs 裸函数"二选一的口径选择权 — **字面量优先级 < 文件现有 import 风格**,Codex 按文件自洽即可(对齐 T-1103 spec §3.6.2 vs §10 #8 自洽差异由 Codex 字面量优先处置惯例)

#### 10.2 spec 起草盲点防御

- T-1102 spec 起草曾遗漏全仓 `.replace(...)` 11 处残留,T-1103 补救后形成"全仓 grep 闸门"经验。本任 T-1104 已对应预防:
  - §3.5 fail-safe self-check 7 项 grep 闸门(零 router / 零 schema / 零 frontend / 零 services 越界 / 零 conftest / 零 env / 零 pyproject)由 Codex 在 commit 前自跑
  - §4.5 严禁夹带清单 9 项作为 spec 字面量,验收 §8.1 第 4 项作为指挥官二次验收闸门
- §3.4 `department_service.py` 仅改 `get_department_with_members` 单函数,**不**误改 `list_departments / create / update / delete / _map_value_error`(对齐 T-1003 / T-1004 / T-1005 三轨道严格作用域纪律)

---

## 📣 附录:给 Worker(Codex)的物理交接单

> **指挥官时间戳**:`[2026-05-29 起草]`(由指挥官在 chore(spec) commit 落盘时填实)
> **当前持牌任务**:T-1104(Phase 11 第四任 — `User.department` FK 双轨迁移 · 第一阶段)
> **依赖前置**:T-1101 / T-1102 / T-1103 全闭环并 push origin/main(基线 `2baaaed`)

### 恢复执行指令(Codex 接手时必跑)

1. **静默 Git 探针**(CLAUDE.md #1):
   ```bash
   git status --short --branch
   git log -5 --oneline
   git diff
   git diff --cached
   git rev-list --left-right --count origin/main...HEAD  # 期望 0 0
   ```
2. **读盘**:
   - `docs/T-1104_spec.md` 全文(本文件,~600 行 10 章 + 📣 附录)
   - `docs/dev_tasks.md` 末尾 📣 锚点段(L253+,T-1104 持牌字面量)
   - `backend/app/models/user.py:53`(`User.department` 字段定义)
   - `backend/app/models/department.py`(全文 ~50 行,Department 表 + manager_id FK 体例参考)
   - `backend/app/services/department_service.py` 全文(找到 `get_department_with_members` 函数 + L135 `User.department == dept.name` 等值反查段)
   - `backend/alembic/versions/20260528_1000_security_readiness_constraints.py`(确认 head revision id 仍是 `9a1b2c3d4e5f`)
3. **二次确认 alembic head**:
   ```bash
   cd backend && .venv/bin/alembic heads
   ```
   - 如非 `9a1b2c3d4e5f` 以实际为准更新 spec §3.1 `down_revision` 字面量(spec 字面量优先级 < alembic 实际 head)
   - 实际值出现在你的迁移文件 `down_revision = "..."` 时务必对齐
4. **改 `docs/dev_tasks.md` Task 4 → `[/]`** + 单 commit `chore(lock): T-1104 开工`(CLAUDE.md #3 加锁)
   ```
   chore(lock): T-1104 开工 — Phase 11 第四任 User.department FK 双轨迁移第一阶段

   Worker timestamp: [2026-05-29 HH:MM:SS]
   ```
5. **按 §3 实施细则 5 文件改动**:
   - 2 新建 backend(alembic version + `_department_resolver.py`)
   - 2 改 backend(`models/user.py` 插入式 + `services/department_service.py` 单函数 stmt 替换)
   - 1 新建 test(`tests/test_phase11_dept_fk.py` ~280 行 ~15 case)
6. **§6 质量闸门 6 项全跑**:
   - ruff(4 文件)
   - mypy(3 src 文件)
   - alembic upgrade-downgrade-upgrade 来回 PASS(stdout 命中 `[T-1104 backfill]`)
   - pytest 子集(15/15 PASS)+ 全量(193 passed + 2 skipped)
   - frontend lint+typecheck(零改动应清白)
7. **§7 commit 纪律 2 commit 原子收口**:
   - Commit 1:`feat(models): T-1104 ...` 5 文件,Worker timestamp 必带
   - Commit 2:`chore(progress): close T-1104 ...` 1 文件(`docs/dev_tasks.md` Task 4 → `[x]` + 📣 锚点替换),Worker timestamp 必带 + body 含完工概要 + 文件清单 + 严禁项遵守证据
8. **完工后停手汇报**:`「T-1104 完工,等待指挥官二次验收 + T-1105 候选起草」`

### 严禁项再确认(BLOCKER 红线)

- 🚫 **严禁** `git push`(等指挥官接手二次验收)
- 🚫 **严禁** 自启 T-1105 / T-1106 / 其他 Phase 11 候选议题(② 物化视图 / ③ KPI 钻取 / ④ 前端看板)
- 🚫 **严禁** 改 `backend/app/routers/` / `backend/app/schemas/` / `frontend/` / `backend/conftest.py` / `backend/tests/_isolation.py` / `backend/tests/_db_url.py` / `backend/.env*` / `README.md` / `DEPLOY.md` / `backend/pyproject.toml` / `backend/requirements.txt` / `backend/uv.lock`(任一改动 = BLOCKER 立即退回,二次验收时驳回)
- 🚫 **严禁** 改 `backend/app/services/department_service.py` 除 `get_department_with_members` 单函数外的任何函数(`list_departments / create / update / delete / _map_value_error` 全部冻结)
- 🚫 **严禁** Migration backfill 内 silent 跳过 unmapped(必须输出 `[T-1104 backfill]` 字面量 stdout 报告)
- 🚫 **严禁** Migration `downgrade()` 留空或抛 `NotImplementedError`
- 🚫 **严禁** `git stash` / amend / rebase / `--no-verify` 跳过 hook
- 🚫 **严禁** 测试 mock / monkeypatch / skip / print / logger
- 🚫 **严禁** 改 `📣 附录` 位置 / 删除指挥官签字痕迹

### 回滚动作(production hot rollback)

```bash
cd backend && .venv/bin/alembic downgrade -1
# users.department_id 列 + FK + index 删除,users.department VARCHAR(64) 数据完整保留
```

### 二次验收前预案

- 若指挥官二次验收驳回 BLOCKER → 按 §10.2 spec 起草盲点防御惯例,Codex 单一原子 `fix(...)` commit 修复 + 保留二次验收记录
- 若指挥官接受非 BLOCKER 小减分 → 在 chore commit body 注明减分理由,T-1105 起草时统一收紧

---

**🏁 spec 落盘完成。等待 Codex 接手执行。**
