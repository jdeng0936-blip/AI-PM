# T-1004 实施契约 —— `/api/v1/admin/departments` 服务 + 路由（5 端点 CRUD + members 反查）

> **指挥官签发时间戳**: `[2026-05-27 19:30:00]`
> **持牌任务**: T-1004（Phase 10 第三份代码任务,服务/路由层主线轮)
> **依赖前置**: T-1001（勘察） / T-1002（ProjectMember partial unique index） / T-1003（`Department` ORM + 7 seed） 全部 `[x]`
> **下游任务**: T-1005（`/api/v1/admin/reports?group_by=` 分组端点）/ T-1006（前端）/ T-1007（测试集中补）/ T-1008（文档收尾）

---

## 1. 任务背景

### 1.1 上游 T-1003 已落地的事实（Git 真相源）

- `backend/app/models/department.py` 已存在,`Department(BaseMixin, Base)` 含 `id UUID PK / name String(64) UNIQUE / manager_id UUID FK→users.id ON DELETE SET NULL nullable index`。
- alembic head = `b58bb129c24b`（T-1003 落地 commit `ad6643a`),`departments` 表已建好,7 seed 已写入(`技术部/生产部/采购部/财务部/商务部/销售部/仓储部`)。
- `app/models/__init__.py` 已 export `Department`,**禁止再次重排**。
- `User.department: String(64), nullable=False, default=""` **保留原样**（与 `departments.name` 字符串并存,FK 化迁移延后到 Phase 11+）。

### 1.2 本契约的目标

将 `Department` 数据层暴露为对外 REST 端点,提供 5 项 CRUD + 关联反查能力,挂在 `/api/v1/admin/departments` 前缀下,RBAC `require_role(UserRole.admin, UserRole.manager)`。完工后管理员可在 API 层直接增删改查部门,以及查看每个部门当前隶属的成员列表(从 `User.department: String(64)` 字段反查)。

### 1.3 端点清单（5 个,全部 admin/manager 鉴权）

| 方法 | 路径 | 响应模型 | 状态码 | 用途 |
|------|------|----------|--------|------|
| GET    | `/api/v1/admin/departments/`              | `list[DepartmentOut]`     | 200 | 列出全部部门(按 name asc) |
| POST   | `/api/v1/admin/departments/`              | `DepartmentOut`           | 201 | 新建部门(name + 可选 manager_id) |
| GET    | `/api/v1/admin/departments/{dept_id}/members` | `DepartmentWithMembers` | 200 | 查部门 + 反查成员列表 |
| PATCH  | `/api/v1/admin/departments/{dept_id}`     | `DepartmentOut`           | 200 | 部分更新 name / manager_id |
| DELETE | `/api/v1/admin/departments/{dept_id}`     | (无 body)                  | 204 | 硬删除部门 |

---

## 2. 任务范围

### 2.1 命中维度（必须改的 5 个文件）

1. **新建** `backend/app/schemas/department.py`（Pydantic V2 schemas:`DepartmentIn / DepartmentUpdate / DepartmentOut / DepartmentMember / DepartmentWithMembers`）。
2. **新建** `backend/app/services/department_service.py`（5 个 async 函数,**不 raise HTTPException**,只 raise `ValueError`/`IntegrityError`）。
3. **新建** `backend/app/routers/departments.py`（`APIRouter(prefix="/api/v1/admin/departments", tags=["Departments"])`,5 端点,RBAC `require_role(admin, manager)`,捕获 service 抛出的 `ValueError` 转 HTTPException）。
4. **改** `backend/app/main.py`（① import 块加 `departments,`(字母序在 `dashboard` 之后 `erp` 之前) ② 加 `app.include_router(departments.router)` 在 `app.include_router(kpi.router)` 之后）。
5. **改** `docs/dev_tasks.md`（Phase 10 看板 Task 4 描述字段扩为 5 端点;状态从 `[/] In Progress by Codex` 改为 `[x]`;**不动** 📣 锚点)。

### 2.2 不动维度（严禁触碰 —— 否则立即回滚）

| 维度 | 状态 | 原因 |
|------|------|------|
| `backend/app/models/department.py` | **冻结** | T-1003 已落地,本任务零 ORM 改动 |
| `backend/app/models/user.py` | **冻结** | `User.department: String(64)` 保留;FK 化延后 Phase 11+ |
| `backend/app/models/__init__.py` | **冻结** | T-1003 已正确 export `Department` |
| 其他 model | **冻结** | `User / Project / ProjectMember / KpiTarget / *` 全冻 |
| 任何 alembic migration | **冻结** | 本任务零 DB schema 改动,**禁止新增 migration** |
| `backend/tests/` | **冻结** | 测试统一推到 T-1007 集中补,本任务不写测试 |
| `frontend/src/` | **冻结** | 前端 Dashboard Tabs + admin/departments 页推到 T-1006 |
| `backend/scripts/seed_data.py` | **冻结** | 与 alembic seed 已解耦,不动 |
| `backend/uv.lock` | **冻结(untracked)** | 继续保持 untracked 状态 |
| `docs/implementation-plan.md` | **冻结** | §10 收尾段推到 T-1008 |
| `docs/recap.md` | **冻结** | Phase 10 整体 recap 推到 T-1008 |

---

## 3. 原子执行步骤

> **执行顺序不可乱**：3.1 → 3.2 → 3.3 → 3.4(单一 commit 提交) → 3.5(单独 commit 收口) 。

### 3.1 新建 `backend/app/schemas/department.py`

#### 文件骨架（完全按下面体例,不可增删字段)

```python
"""
app/schemas/department.py — Phase 10 部门 Pydantic V2 Schemas

对应 ORM Model（app/models/department.py）字段约束:
  - name: String(64) UNIQUE NOT NULL
  - manager_id: UUID FK→users.id ON DELETE SET NULL nullable
  - BaseMixin 4 字段:created_at / updated_at / created_by / tenant_id

成员反查口径:
  - 从 User.department: String(64) 字符串字段按 name 等值匹配反查
  - 仅返回 is_active=True 的活跃用户(本仓库 User 软删除信号 = is_active=False,**无** deleted_at 字段;
    User 模型不继承 BaseMixin,见 backend/app/models/user.py L4-7 注释)
  - 字段裁剪到 id / name / role / department,不暴露密码/手机号等敏感字段
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole


class DepartmentIn(BaseModel):
    """POST /admin/departments/ 请求体。"""

    name: str = Field(..., min_length=1, max_length=64, description="部门名称")
    manager_id: Optional[uuid.UUID] = Field(None, description="部门负责人 user.id;可选")


class DepartmentUpdate(BaseModel):
    """PATCH /admin/departments/{id} 请求体,字段全 optional。"""

    name: Optional[str] = Field(None, min_length=1, max_length=64, description="部门名称")
    manager_id: Optional[uuid.UUID] = Field(None, description="部门负责人 user.id")


class DepartmentOut(BaseModel):
    """通用响应模型。"""

    id: uuid.UUID
    name: str
    manager_id: Optional[uuid.UUID]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    created_by: Optional[uuid.UUID]
    tenant_id: str

    model_config = ConfigDict(from_attributes=True)


class DepartmentMember(BaseModel):
    """成员反查时的精简用户视图。"""

    id: uuid.UUID
    name: str
    role: UserRole
    department: str

    model_config = ConfigDict(from_attributes=True)


class DepartmentWithMembers(DepartmentOut):
    """GET /admin/departments/{id}/members 响应。"""

    members: list[DepartmentMember]
```

#### 严禁项

- **严禁**加 `validator` / `model_validator` —— 本任务字段约束简单,Pydantic 内置即可。
- **严禁**加 `Computed` / `@property` 字段。
- **严禁**导入 `Department` ORM(只导 `UserRole`,避免循环 import 风险)。

---

### 3.2 新建 `backend/app/services/department_service.py`

#### 文件骨架

```python
"""
app/services/department_service.py — Phase 10 部门服务层

职责:
  - CRUD: list / create / update / delete (4 个写读函数)
  - 反查: get_with_members(从 User.department 字符串字段反查成员)

错误模型:
  - 不 raise HTTPException(职责留给 router 层)
  - 用 ValueError + str 区分错误类型,router 按字面量映射 4xx 状态码:
    - "not_found"        → 404
    - "name_conflict"    → 409
    - "manager_not_found" → 400
  - 数据库 IntegrityError 在 service 内捕获并转 ValueError("name_conflict")

约束:
  - 全异步 AsyncSession
  - TENANT_ID = "default"(对齐 kpi_service)
  - 返回 Schema Out 实例(不暴露 ORM)
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.user import User
from app.schemas.department import (
    DepartmentIn,
    DepartmentMember,
    DepartmentOut,
    DepartmentUpdate,
    DepartmentWithMembers,
)

TENANT_ID = "default"


async def _get_department_or_raise(db: AsyncSession, dept_id: uuid.UUID) -> Department:
    stmt = select(Department).where(
        Department.id == dept_id,
        Department.tenant_id == TENANT_ID,
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if result is None:
        raise ValueError("not_found")
    return result


async def _verify_manager_exists(db: AsyncSession, manager_id: uuid.UUID) -> None:
    """校验 manager_id 对应 user 存在且活跃(is_active=True)。

    本仓库 User 不使用 deleted_at,软删除 = is_active=False(见 backend/app/routers/users.py:223)。
    """
    stmt = select(User.id).where(
        User.id == manager_id,
        User.is_active.is_(True),
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise ValueError("manager_not_found")


async def list_departments(db: AsyncSession) -> list[DepartmentOut]:
    stmt = (
        select(Department)
        .where(Department.tenant_id == TENANT_ID)
        .order_by(Department.name.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [DepartmentOut.model_validate(row) for row in rows]


async def create_department(
    db: AsyncSession,
    payload: DepartmentIn,
    actor: User,
) -> DepartmentOut:
    if payload.manager_id is not None:
        await _verify_manager_exists(db, payload.manager_id)

    dept = Department(
        name=payload.name.strip(),
        manager_id=payload.manager_id,
        created_by=actor.id,
        tenant_id=TENANT_ID,
    )
    db.add(dept)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("name_conflict") from None
    await db.commit()
    await db.refresh(dept)
    return DepartmentOut.model_validate(dept)


async def update_department(
    db: AsyncSession,
    dept_id: uuid.UUID,
    payload: DepartmentUpdate,
    actor: User,
) -> DepartmentOut:
    dept = await _get_department_or_raise(db, dept_id)

    update_data = payload.model_dump(exclude_unset=True)
    if "manager_id" in update_data and update_data["manager_id"] is not None:
        await _verify_manager_exists(db, update_data["manager_id"])

    if "name" in update_data and update_data["name"] is not None:
        dept.name = update_data["name"].strip()
    if "manager_id" in update_data:
        dept.manager_id = update_data["manager_id"]

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("name_conflict") from None
    await db.commit()
    await db.refresh(dept)
    return DepartmentOut.model_validate(dept)


async def delete_department(db: AsyncSession, dept_id: uuid.UUID) -> None:
    dept = await _get_department_or_raise(db, dept_id)
    await db.delete(dept)
    await db.commit()


async def get_department_with_members(
    db: AsyncSession, dept_id: uuid.UUID
) -> DepartmentWithMembers:
    dept = await _get_department_or_raise(db, dept_id)

    member_stmt = (
        select(User)
        .where(
            User.department == dept.name,
            User.is_active.is_(True),
            User.tenant_id == TENANT_ID,
        )
        .order_by(User.name.asc())
    )
    member_rows = (await db.execute(member_stmt)).scalars().all()
    members = [DepartmentMember.model_validate(u) for u in member_rows]

    base = DepartmentOut.model_validate(dept).model_dump()
    return DepartmentWithMembers(**base, members=members)
```

#### 严禁项

- **严禁** 在 service 层 raise `HTTPException`（违反本仓库 `kpi_service` 体例）。
- **严禁** 在 service 层做 `print` / `logger.info` 等副作用。
- **严禁** 引入 `app.routers.*` 任何模块。
- **严禁** 调用 `app/services/deletion_history.py` 或写入 `deletion_history` 表(Department 不在软删除框架内,T-1004 范围)。
- **严禁** 自行追加 `manager_id` FK 校验之外的复杂业务校验。

#### User 活跃字段说明(已勘察实证,无需 Codex 再做探针)

- 本仓库 `User` 模型**不**继承 BaseMixin,**没有** `deleted_at` 字段(见 `backend/app/models/user.py` L4-7 注释 + L82-92 通用字段段落)。
- 软删除信号: `is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)`(L59)。
- 现有体例: `User.is_active.is_(True)` 已在多处使用(`services/chat_tools/people.py:117` / `services/chat_tools/reports.py:315` / `services/export/reports_excel.py:117` / `routers/users.py:72,237,256`)。本契约 §3.2 服务层完全对齐此体例。
- 用户软删除路径 = `routers/users.py:223`(`user.is_active = False`),硬删除路径无(只走停用)。

---

### 3.3 新建 `backend/app/routers/departments.py`

#### 文件骨架

```python
"""
app/routers/departments.py — Phase 10 部门 REST API

端点(全部 admin + manager RBAC):
  - GET    /api/v1/admin/departments/                —— 列出全部部门
  - POST   /api/v1/admin/departments/                —— 新建部门
  - GET    /api/v1/admin/departments/{id}/members    —— 查部门 + 反查成员
  - PATCH  /api/v1/admin/departments/{id}            —— 部分更新
  - DELETE /api/v1/admin/departments/{id}            —— 硬删除

错误码映射(service raise ValueError(str)):
  - "not_found"         → 404 "部门不存在"
  - "name_conflict"     → 409 "部门名称已存在"
  - "manager_not_found" → 400 "manager_id 对应的用户不存在或已删除"
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.user import User, UserRole
from app.schemas.department import (
    DepartmentIn,
    DepartmentOut,
    DepartmentUpdate,
    DepartmentWithMembers,
)
from app.services.department_service import (
    create_department,
    delete_department,
    get_department_with_members,
    list_departments,
    update_department,
)

router = APIRouter(prefix="/api/v1/admin/departments", tags=["Departments"])
_mgr_or_admin = require_role(UserRole.admin, UserRole.manager)


def _map_value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "not_found":
        return HTTPException(status_code=404, detail="部门不存在")
    if code == "name_conflict":
        return HTTPException(status_code=409, detail="部门名称已存在")
    if code == "manager_not_found":
        return HTTPException(status_code=400, detail="manager_id 对应的用户不存在或已删除")
    return HTTPException(status_code=500, detail="未知错误")


@router.get("/", response_model=list[DepartmentOut])
async def list_all(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> list[DepartmentOut]:
    return await list_departments(db)


@router.post("/", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
async def create(
    payload: DepartmentIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(_mgr_or_admin),
) -> DepartmentOut:
    try:
        return await create_department(db, payload, actor)
    except ValueError as e:
        raise _map_value_error(e) from None


@router.get("/{dept_id}/members", response_model=DepartmentWithMembers)
async def get_members(
    dept_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> DepartmentWithMembers:
    try:
        return await get_department_with_members(db, dept_id)
    except ValueError as e:
        raise _map_value_error(e) from None


@router.patch("/{dept_id}", response_model=DepartmentOut)
async def update(
    dept_id: uuid.UUID,
    payload: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(_mgr_or_admin),
) -> DepartmentOut:
    try:
        return await update_department(db, dept_id, payload, actor)
    except ValueError as e:
        raise _map_value_error(e) from None


@router.delete("/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    dept_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> Response:
    try:
        await delete_department(db, dept_id)
    except ValueError as e:
        raise _map_value_error(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

#### 严禁项

- **严禁** 在 router 层做 ORM 查询(全部走 service)。
- **严禁** 在 router 层 raise 业务校验 `HTTPException`(只允许通过 `_map_value_error` 转译,鉴权 403 由 `require_role` 自动处理)。
- **严禁** 改 RBAC 范围 —— 必须 `admin + manager`,**禁止** 加 `employee`。
- **严禁** 在端点处理函数里 print / logger.info。
- **严禁** 自行加 PATCH 之外的 PUT 端点(本契约 5 端点,不增不减)。

---

### 3.4 改 `backend/app/main.py`（**插入式 2 行**)

#### Diff 预期

```diff
 from app.routers import (
     analytics,
     auth,
     dashboard,
+    departments,
     erp,
     export,
     gates,
     kpi,
     me_deletions,
     reports,
     sprints,
     users,
     wechat,
 )
```

以及在 `app.include_router(kpi.router)` 之后**紧邻插入**:

```diff
 app.include_router(kpi.router)
+app.include_router(departments.router)

 app.include_router(wechat.router)
```

#### 严禁项

- **严禁** 重排 import 块的其他元素(只允许在 `dashboard` 与 `erp` 之间插入)。
- **严禁** 改 `app.include_router(...)` 其他调用的相对顺序。
- **严禁** 改 Sentry 初始化逻辑、`lifespan` 函数。
- **严禁** 改任何中间件挂载顺序。

---

### 3.5 改 `docs/dev_tasks.md`（**两处编辑**)

#### 编辑 A: Phase 10 看板 Task 4 描述微调 + 状态打钩

- 找到行 128(`- [ ] **Task 4 (T-1004): ...**`),把状态从 `[/] In Progress by Codex(...)` 改为 `[x]`。
- **附加** 第 4-5 个 bullet 描述 PATCH 与 DELETE 端点,以及成员反查的口径:
  - 子描述追加:`PATCH /api/v1/admin/departments/{id}(部分更新 name / manager_id)` + `DELETE /api/v1/admin/departments/{id}(硬删除,返回 204)`。
  - 子描述追加成员反查口径:`GET /{id}/members 从 User.department: String(64) 等值反查 + User.is_active.is_(True) 过滤(本仓库无 deleted_at 字段)`。

#### 编辑 B: 📣 锚点保留不动

- **不动** 📣 恢复执行指令锚点(指挥官会在 `chore(spec): T-1004 契约` commit 中统一替换为 T-1004 发牌内容,Worker 在 chore(progress) 收口时**不要碰**)。

#### 严禁项

- **严禁** 改 Phase 9 章节或其他 Task 的描述。
- **严禁** 改 Phase 10 Task 5/6/7/8 的描述(它们由后续契约定稿)。
- **严禁** 改 📣 锚点(指挥官专属位置)。

---

### 3.6 起始状态(由指挥官打锁,Worker 不再处理)

- 指挥官在 `chore(spec): T-1004 契约` commit 中已经一并完成:
  - Task 4 状态从 `[ ]` 改为 `[/] In Progress by Codex(指挥官 chore(spec) commit 已加锁,2026-05-27 19:30)`
  - 📣 锚点替换为 T-1004 发牌内容(持牌任务 = T-1004,head = `b58bb129c24b`)
- Worker 接力时,**不要重复 `chore(lock)`**,直接进入 §3.1 → §3.5 实施阶段。

---

## 4. 防越界红线表

| # | 红线 | 触发后果 |
|---|------|----------|
| 01 | 改 `backend/app/models/department.py` | 立即回滚 + 通报 |
| 02 | 改 `backend/app/models/user.py`(`User.department` 字段) | 立即回滚 + 通报 |
| 03 | 改 `backend/app/models/__init__.py` | 立即回滚 + 通报 |
| 04 | 新增任何 alembic migration | 立即回滚 + 通报 |
| 05 | 改 `backend/scripts/seed_data.py` | 立即回滚 + 通报 |
| 06 | 在 `backend/tests/` 新增 / 修改 测试文件 | 立即回滚 + 通报(T-1007 集中补) |
| 07 | 改 `frontend/src/` 任何文件 | 立即回滚 + 通报(T-1006) |
| 08 | 给 service / router 加 `print` 或 `logger` 副作用 | 立即回滚 |
| 09 | service 层 raise `HTTPException`(违反 kpi_service 体例) | 立即回滚 |
| 10 | router 层做 ORM 查询(应全走 service) | 立即回滚 |
| 11 | 自行扩端点(PUT / OPTIONS / HEAD 等)或减端点 | 立即回滚 |
| 12 | RBAC 范围加 `employee` 或去掉 `manager` | 立即回滚 |
| 13 | 重排 `main.py` import 块其他元素 | 立即回滚 |
| 14 | 重排 `__all__` 或 `from app.routers import (...)` 其他元素 | 立即回滚 |
| 15 | `git add backend/uv.lock` 或其他 4 个 untracked 文件 | 立即回滚 |
| 16 | `git push` 自动推送 | 立即停手 |
| 17 | 自行启动 T-1005 / T-1006 / T-1007 / T-1008 | 立即停手 |
| 18 | 改 📣 锚点("当前持牌任务: T-1004" 必须保留) | 立即回滚 |
| 19 | 在 service 写 `await db.delete()` 之外的级联 SQL | 立即回滚 |
| 20 | 在 router 端点函数加业务级 `print` 或自定义中间件 | 立即回滚 |

---

## 5. 数据风险评估

### 5.1 风险点清单

| # | 风险 | 概率 | 影响 | 应对 |
|---|------|------|------|------|
| 1 | DELETE 部门后,`User.department: String(64)` 字段出现孤儿名引用 | 中 | 中 | **接受**:Phase 10 不前置校验;Phase 11+ FK 化时统一清洗。本契约 §5.2 已说明。 |
| 2 | POST/PATCH 时 `manager_id` 校验 race condition(校验后 manager 立即被删) | 极低 | 低 | **接受**:被删的 manager 在下一次 GET 时仍能正常显示(`ON DELETE SET NULL` 不会让 department 整张消失) |
| 3 | name UNIQUE 冲突在并发 POST 下漏判 | 低 | 低 | **接受**:`IntegrityError` catch 已兜底,Codex 不需做应用层 lock |
| 4 | DELETE 7 seed 部门 | 中 | 低 | **接受**:admin 可自由删除任意部门;若 T-1006 前端需要锁定 seed,留给前端层面 disable 按钮(本契约不阻止) |
| 5 | `get_with_members` 在大规模部门下成员反查慢 | 极低 | 低 | **接受**:目前 7 个 seed + User 表规模小,无需分页;后续扩 paging 留 Phase 11+ |

### 5.2 孤儿名引用的明确处理路径(签字)

- T-1004 完工后,若 admin 删除"技术部":
  - `departments` 表中"技术部" row 消失。
  - `users.department` 中所有 `="技术部"` 的字符串 **保留不变**(因为 `User.department` 不是 FK,无级联)。
  - 调用方在 GET `/users/?department=技术部` 仍能查到这些用户。
  - GET `/admin/departments/` 不再显示"技术部",但 GET `/admin/departments/{已删除 id}/members` 返回 404。
- **Phase 11+** 引入 `User.department_id: UUID FK→departments.id` 时,需要先做数据清洗 migration(把孤儿字符串映射到 NULL 或重建对应 department);本契约**显式不承担**此责任。

---

## 6. 测试基线（Worker 提交前必跑,全绿才能 commit)

```bash
cd backend
# ① 语法 + 类型
.venv/bin/ruff check .
.venv/bin/mypy app/schemas/department.py app/services/department_service.py app/routers/departments.py app/main.py

# ② 全量回归（不允许任何回归,新增端点不写测试故计数应保持)
.venv/bin/pytest tests/ -q

# ③ alembic 没改动,跑 head 校验确保 import 链路不破坏
.venv/bin/alembic upgrade head && .venv/bin/alembic check

# ④ 前端无破坏验证
cd ../frontend
npm run lint
npm run typecheck
```

#### 验收条件

- ruff:无 violation。
- mypy:目标 4 文件 0 error;若现有其他文件 mypy 已存量报错,**不修复**(不在本契约范围)。
- pytest:`162 passed`(或与 T-1003 完工时基线一致,**零回归**);**不允许 fail / error**。
- alembic check:`No new upgrade operations detected.`
- npm run lint / typecheck:全绿。

#### 测试不要新增

- 本契约**不写** `test_phase10_dept_*.py` 测试文件。Router 行为(404 / 409 / 400 / 200 / 201 / 204 / RBAC)统一推到 **T-1007** 集中编写。
- 若 Codex 觉得"必须自查一下",**仅允许**手动 `curl` / `httpie` 临时调用(不写入仓库),并在汇报中带 curl 输出。

---

## 7. 完工提交序列（原子 2 commit,顺序不可乱）

#### Commit 1: feat(department) — 5 个文件改动一次性进入

```
feat(department): add Department service + router + 5 endpoints (CRUD + members)

Phase 10 / T-1004 — 暴露 Department 数据层为 REST 端点。

文件改动:
- 新建 backend/app/schemas/department.py(5 个 Pydantic V2 schemas)
- 新建 backend/app/services/department_service.py(5 个 async 函数,ValueError 错误信号)
- 新建 backend/app/routers/departments.py(5 端点 + RBAC + ValueError → HTTPException 映射)
- 改 backend/app/main.py(import + include_router 插入式 2 行)

端点(全部 admin + manager RBAC):
- GET    /api/v1/admin/departments/                —— 列表
- POST   /api/v1/admin/departments/                —— 新建(201)
- GET    /api/v1/admin/departments/{id}/members    —— 查部门 + 反查成员
- PATCH  /api/v1/admin/departments/{id}            —— 部分更新
- DELETE /api/v1/admin/departments/{id}            —— 硬删除(204)

错误码映射:
- not_found        → 404
- name_conflict    → 409
- manager_not_found → 400

不动:
- ORM / migration / __init__.py(T-1003 已完结)
- User.department: String(64)(FK 化延后 Phase 11+)
- 任何测试 / 前端 / seed_data.py(留给 T-1005~T-1008)

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

文件清单:
1. `backend/app/schemas/department.py`(新建)
2. `backend/app/services/department_service.py`(新建)
3. `backend/app/routers/departments.py`(新建)
4. `backend/app/main.py`(改 import + include_router,只 +2 行)

#### Commit 2: chore(progress) — 仅更新 dev_tasks.md

```
chore(progress): close T-1004 — /api/v1/admin/departments 5 端点 + 成员反查上线

dev_tasks.md Phase 10 章节 Task 4 状态改为 [x],并扩描述至 5 端点(GET list / POST create / GET {id}/members / PATCH {id} / DELETE {id})。📣 恢复执行指令锚点保留 T-1004,留给指挥官起草 T-1005 时统一替换。

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

文件清单:
1. `docs/dev_tasks.md`(改 Task 4 状态 + 描述,**不动** 📣 锚点)

#### 严禁项

- **严禁** 把 Commit 1 与 Commit 2 合并。
- **严禁** 在 Commit 1 中夹带 `docs/dev_tasks.md`(职责拆开)。
- **严禁** 在 Commit 2 中夹带任何 src 文件。
- **严禁** 写 `Co-Authored-By:` 之外的额外作者署名。
- **严禁** 在 commit message 中省略 `Worker timestamp: [...]` 行。

---

## 8. 验收清单（指挥官二次验收时按此核对)

- [ ] 1. `git log --oneline -3` 显示链路 `<chore> → <feat> → 4deb8a5/T-1003 spec...`,顺序正确
- [ ] 2. Commit 1 (feat) 改动恰好 4 个文件(`schemas/department.py` + `services/department_service.py` + `routers/departments.py` + `main.py`),零夹带
- [ ] 3. Commit 2 (chore) 仅改 `docs/dev_tasks.md`,Task 4 = `[x]`,描述含 5 端点
- [ ] 4. `backend/app/main.py` import 块仅在 `dashboard` 与 `erp` 之间插入 `departments,`,其他元素零移动
- [ ] 5. `app.include_router(departments.router)` 紧邻在 `app.include_router(kpi.router)` 之后
- [ ] 6. Schema 文件含 5 个 class(`DepartmentIn / DepartmentUpdate / DepartmentOut / DepartmentMember / DepartmentWithMembers`),字段约束对齐 §3.1
- [ ] 7. Service 文件含 5 个公开 async 函数 + 2 个 `_*` 私有助手;**不**含 `HTTPException` 引用
- [ ] 8. Router 文件含 5 个端点;`_map_value_error` 仅映射 3 个 code + 兜底 500
- [ ] 9. RBAC 全部 `admin + manager`,**未**降级到 `employee`
- [ ] 10. 全部测试基线绿(ruff / mypy / pytest / alembic check / 前端 lint+typecheck)
- [ ] 11. `git status` 干净(仅 4 个既定 untracked 保留:`.cursorrules / CLAUDE.md / CONVENTIONS.md / backend/uv.lock`)
- [ ] 12. `git diff origin/main -- backend/alembic/` 为空(本任务零 migration)
- [ ] 13. `git diff origin/main -- backend/tests/ frontend/src/` 为空(本任务零测试 + 零前端)
- [ ] 14. `git diff origin/main -- backend/app/models/` 为空(本任务零 ORM)
- [ ] 15. 两个 commit 的 message 都含 `Worker timestamp: [...]` 行
- [ ] 16. 📣 锚点中"当前持牌任务: T-1004"保留(留给指挥官在 T-1005 spec 中统一替换)

---

## 9. 与其他任务的关系

- **上游**: T-1003(`Department` ORM + 7 seed)已落地。本契约消费 `Department` 模型,**禁止再改 ORM**。
- **平行**: 无。本契约期间 Codex 不会被分派 T-1005/06/07/08。
- **下游**: 完工后指挥官将立即起草:
  - **T-1005** `/api/v1/admin/reports?group_by=department|project` 分组端点(消费部门数据做聚合)。
  - 或视实际情况优先起 **T-1007** 集中补 Phase 10 测试套件(包括本契约的 5 端点测试)。
- **跳过**: 不消费、不影响:Phase 9 KPI / Phase 7 物化视图 / Phase 8 Export / Phase 6 OKR / Phase 5 Sprint / Phase 4 Gate / Phase 3 Capacity / Phase 2 Auth / Phase 1 Base。

---

## 📣 附录:给 Worker 的物理交接单(指挥官在 chore(spec) commit 同步落盘)

> **时间戳**: `[2026-05-27 19:30:00]`
> **当前持牌任务**: T-1004
> **执行入口**: 阅读本契约 §3.1 → §3.5,严格按原子顺序执行,**不要重复 `chore(lock)`**(指挥官在 chore(spec) commit 已加锁)。

### 核心动作(严格按 §3 顺序)

1. **新建** `backend/app/schemas/department.py` —— 5 个 Pydantic V2 schemas,完全按 §3.1 骨架,字段约束不可扩缩。
2. **新建** `backend/app/services/department_service.py` —— 5 个公开 async 函数(`list / create / update / delete / get_with_members`)+ 2 个 `_` 私有助手,**不 raise HTTPException**,ValueError 错误信号体例,完全按 §3.2 骨架。
3. **新建** `backend/app/routers/departments.py` —— `APIRouter(prefix="/api/v1/admin/departments")` + 5 端点,完全按 §3.3 骨架,RBAC `require_role(admin, manager)`,`_map_value_error` 映射 3 code → 4xx。
4. **改** `backend/app/main.py` —— 插入式 2 行:① import 块 `departments,` 在 `dashboard` 与 `erp` 之间;② `app.include_router(departments.router)` 紧邻 `kpi` 之后。**严禁**重排其他元素。
5. **改** `docs/dev_tasks.md` —— Task 4 状态 `[/] → [x]`,描述扩为 5 端点(放最后一个 commit 一起 add)。**不动** 📣 锚点。

### 严禁项(违反则立即回滚)

- **严禁** 改 ORM(`department.py / user.py / __init__.py` 全冻)。
- **严禁** 新增 alembic migration。
- **严禁** 写测试(留给 T-1007 集中补)。
- **严禁** 改前端任何文件(留给 T-1006)。
- **严禁** 改 `User.department: String(64)` 字段定义。
- **严禁** 在 service 层 raise `HTTPException`(违反 kpi_service 体例)。
- **严禁** 在 router 层做 ORM 查询。
- **严禁** 加端点(只允许 5 个)或减端点。
- **严禁** RBAC 范围加 `employee` 或去 `manager`。
- **严禁** 自动 `git push`。
- **严禁** 自行启动 T-1005 / T-1006 / T-1007 / T-1008。
- **严禁** 改 📣 锚点("当前持牌任务: T-1004" 保留)。
- **严禁** `git add backend/uv.lock` 或其他 4 个既定 untracked 文件。
- **严禁** 在 commit message 漏写 `Worker timestamp: [...]`。

### Error code 映射(全契约一致,落盘到代码注释)

| Service raise (ValueError str) | Router HTTPException | detail 字符串 |
|--------------------------------|-----------------------|---------------|
| `"not_found"`         | 404 | `"部门不存在"` |
| `"name_conflict"`     | 409 | `"部门名称已存在"` |
| `"manager_not_found"` | 400 | `"manager_id 对应的用户不存在或已删除"` |

### 测试基线(全绿才提交)

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/mypy app/schemas/department.py app/services/department_service.py app/routers/departments.py app/main.py
.venv/bin/pytest tests/ -q                                    # 必须零回归(与 T-1003 完工基线一致)
.venv/bin/alembic upgrade head && .venv/bin/alembic check
cd ../frontend && npm run lint && npm run typecheck
```

### 完工提交序列(原子 2 commit,顺序不可乱)

1. `feat(department): add Department service + router + 5 endpoints (CRUD + members)` —— 4 个新/改文件:`schemas/department.py` + `services/department_service.py` + `routers/departments.py` + `main.py`(插入式 2 行)
2. `chore(progress): close T-1004 — /api/v1/admin/departments 5 端点 + 成员反查上线` —— 仅 `docs/dev_tasks.md`,Task 4 → `[x]`

### 时间戳纪律

所有 commit message 末尾、终端汇报、写入 `dev_tasks.md` 段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。

### 完工后

立即停手汇报「T-1004 完工,等待指挥官二次验收 + 起草 T-1005 (`/api/v1/admin/reports?group_by=` 分组端点) 实施契约 / 或起草 T-1007 (测试集中补)」。**不要** 自行启动任何下游 task。

---

> **指挥官签字落盘**: `[2026-05-27 19:30:00]`
> **关联 commit**: `chore(spec): T-1004 契约` —— `dev_tasks.md` Task 4 加锁 + 📣 锚点替换 由同 commit 一并完成。
