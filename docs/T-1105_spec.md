# 📜 T-1105 执行契约 — Phase 11 第五任(临时插队):立项时支持指派成员(项目成员一站式批量初始化)

> **起草时间戳**: `[2026-05-29 11:10:44]`(指挥官签字)
> **指挥官**: Claude (Opus 4.7 / 1M)
> **Worker**: Codex(待指挥官接手)
> **基线 commit**: `a532041` chore(progress): close T-1104 — Phase 11 第四任 User.department FK 双轨迁移第一阶段完工
> **alembic head**: `<由 T-1104 引入,Codex 接手时 alembic heads 二次核验>`(本任**零** migration,不动 alembic chain)
> **依赖前置**: T-1104 工程完工(commit `a532041`),指挥官二次验收记录暂未走完(本任并行起草,二次验收由指挥官在 T-1105 完工后统一回补)

---

## §1 任务背景与范围(WHY + WHAT)

### 1.1 起源

- **临时插队需求**(`[2026-05-29 用户指令]`):用户在 T-1104 起草后明确要求先规划"在新建项目(弹窗/表单)时,支持直接添加/指派项目成员"。
- 原 Phase 11 候选 backlog(`docs/implementation-plan.md:853`)规划:
  - ① **`User.department` → `Department.id` FK 迁移(双轨融合)** — T-1104 已完工(`64b45a9 → a532041`)
  - ② 物化视图增量按部门聚合预热(候选)
  - ③ 前端 Tabs `by_project` 视图加权重柱状图(候选)
  - ④ `Department.manager_id` 反查路径与 Phase 9 KPI `KpiScope=department` 打通(候选)
- **本任插队顺位**:T-1105 = 立项指派成员;原计划的 T-1105 "FK 第二阶段(切剩余 36+ 后端读路径)" **顺延为 T-1106 候选**;原 T-1106 "drop column" **顺延为 T-1107 候选**。
- **业务驱动力**:当前立项 Modal 只能录 `name / code / description / track / planned_launch_date / budget_total / is_temporary` 7 字段,**新项目立项后永远是"零成员"**,用户必须手动跳转到项目详情页 `/project/[id]` → activeTab='members' → 点击"添加成员"按钮 → 逐个填 `{user_id, track, role_in_project}` → 反复 N 次。一站式立项指派可消除这个"立项 → 跳详情 → 逐个加"的多步流转。

### 1.2 任务定位(扩展式,非破坏性)

| 维度 | 当前现状 | T-1105 后 |
|---|---|---|
| 立项 Modal 字段 | 7 字段(无成员) | 8 字段(末尾插入"项目成员"分块,允许 0..N 成员) |
| 后端 `ProjectCreate` schema | 7 字段 | **扩**:可选 `members: list[ProjectMemberInit] = None` |
| 后端 `POST /api/v1/projects/` | 创建 Project + 自动建 stages/backlog | 创建 Project + 自动建 stages/backlog + 一次性插入 N 个 ProjectMember(单事务原子性) |
| 后端 manager 端用户列表 | ❌ `GET /users` 是 admin-only(RBAC gap) | **新增** `GET /api/v1/users/picker`(精简字段 + RBAC = admin/manager,供立项 modal 消费) |
| 前端 `<MemberPicker>` 组件 | ❌ 无 | **新建**(可复用给项目详情页未来收紧 / 招聘 / 其他立项场景) |
| 现有 POST `/{id}/members` 单加路径 | 有 | **不动**(留作"立项后追加成员"的单点路径) |
| 现有项目详情页 `activeTab='members'` UI | 串调 `addProjectMember` | **不动**(留作"立项后追加"工作流) |
| ProjectMember.tenant_id 注入 | 现有(`creator.tenant_id`) | 严格沿用(`creator.tenant_id` + `creator.id`) |
| RBAC | `_mgr = require_role(manager, admin)` | 严格沿用(不动) |

### 1.3 双轨纯扩展策略(为何不强制必选成员)

**决策**:`ProjectCreate.members` 字段为 `Optional[list[ProjectMemberInit]] = None`,**允许 0 成员**(向后 100% 兼容)。

**理由**:
1. **向后兼容承诺** — 现有前端 `createProject(payload)` 调用方在 payload 不带 `members` 字段时,后端必须接受并走"零成员"路径,与现状 1:1 等价。
2. **业务连续性** — 临时工单项目 / 招标占位项目可能立项时就**确实**没成员(等指派人选未定),强制必选会破坏现有工作流。
3. **解耦立项 + 指派** — 立项 + 指派是两个独立产品决策点,后续单加路径(POST `/{id}/members`)继续保留,用户可两种姿势都用。
4. **测试基线零回归** — T-1101/1102/1103/1104 已经把 baseline 推到 193 passed,本任 ~12 新 case 严格扩展不破坏现有 case(包含临时工单项目 / batch_remove / get_members 等所有现有路径)。

### 1.4 不做范围(BLOCKER 红线)

- ❌ **不动** 现有 POST `/api/v1/projects/{id}/members` 单加路径(留作"立项后追加"工作流)
- ❌ **不动** DELETE `/api/v1/projects/{id}/members/batch` 批量移出路径(V2.5 Stage 2 既有)
- ❌ **不动** GET `/api/v1/projects/{id}/members` 列成员路径
- ❌ **不动** `frontend/src/app/project/[id]/page.tsx` 项目详情页成员管理 UI(`activeTab='members'` 块完全冻结)
- ❌ **不动** `backend/app/models/` 任意文件(本任零 model 改动,零 migration)
- ❌ **不动** `backend/alembic/` 任意文件(零 migration,head 仍是 T-1104 引入)
- ❌ **不动** `backend/app/services/` 任意文件(本任全在 router 层完成事务,不下沉 service)
- ❌ **不动** `backend/app/routers/users.py` 现有 8 端点(`GET / POST / PUT / DELETE / batch-disable / batch-enable / reset-password / status / resource-load`)— 仅**插入式**新增 GET `/picker` 端点
- ❌ **不动** `backend/conftest.py` / `backend/tests/_isolation.py` / `backend/tests/_db_url.py`(T-1102/1103 已闭环)
- ❌ **不动** `backend/.env*` / `README.md` / `DEPLOY.md`(T-1102 已闭环)
- ❌ **不动** `backend/pyproject.toml` / `backend/requirements.txt` / `backend/uv.lock`
- ❌ **不动** T-1104 已落地的 5 backend 文件(Migration / models/user.py / _department_resolver.py / department_service.py / test_phase11_dept_fk.py)
- ❌ **不动** 前端项目详情页 `/project/[id]/page.tsx`、`/admin/departments/page.tsx`、`/admin/kpi/page.tsx`、`/users/page.tsx`、`/dashboard/page.tsx`、`/sidebar.tsx` 任何文件
- ❌ **不** 自启 T-1106 / T-1107 / 其他 Phase 11 候选议题

---

## §2 严禁项(BLOCKER 红线 · 共 12 条)

| # | 严禁项 | 触发后果 |
|---|---|---|
| 1 | 改 `backend/app/models/` 任意文件 / 新建 alembic migration | BLOCKER 立即退回(本任零 schema 改) |
| 2 | 改 `backend/app/services/` 任意文件 | BLOCKER 立即退回(本任 router 层完成事务) |
| 3 | 改 `backend/app/routers/users.py` 现有 8 端点的任何行(`get|post|put|delete|patch + 路由 path + RBAC + 函数体`)— 只允许**末尾插入式**新增 `GET /picker` 端点 | BLOCKER 立即退回 |
| 4 | 改 `backend/app/routers/projects.py` 除 `create_project` 单函数外的任何代码 | BLOCKER 立即退回 |
| 5 | 改 `backend/conftest.py` / `tests/_isolation.py` / `tests/_db_url.py` / `.env*` / `README.md` / `DEPLOY.md` | BLOCKER 立即退回(T-1102/1103 闭环) |
| 6 | 改 `backend/pyproject.toml` / `requirements.txt` / `uv.lock` | BLOCKER 立即退回 |
| 7 | 改前端项目详情页 `frontend/src/app/project/[id]/page.tsx` / `dashboard/page.tsx` / `admin/*/page.tsx` / `users/page.tsx` / `sidebar.tsx` | BLOCKER 立即退回(零回归承诺) |
| 8 | 改 `frontend/src/app/projects/page.tsx` 现有"编辑项目 Modal / 归档确认 Modal / 卡片列表 / 批量操作栏"等任何非"新建项目 Modal"区块 | BLOCKER 立即退回 |
| 9 | 改 T-1104 5 backend 文件(Migration / models/user.py / _department_resolver.py / services/department_service.py / tests/test_phase11_dept_fk.py) | BLOCKER 立即退回 |
| 10 | 自启 T-1106 / T-1107 / 其他 Phase 11 候选议题(② 物化视图 / ③ KPI 钻取 / ④ 前端看板) | BLOCKER 立即退回 |
| 11 | `git push` / `git stash` / `amend` / `rebase` / `--no-verify` 跳过 hook | BLOCKER 立即退回 |
| 12 | 双 commit 任一缺 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 行(CLAUDE.md #7) | BLOCKER 立即退回 |

---

## §3 实施细则

### 3.1 后端 Schema 扩展(改 `backend/app/schemas/project.py` ~+22 行)

#### 3.1.1 新增 `ProjectMemberInit` 类(在 `ProjectMemberAdd` 类**之上 / 之间**插入)

**字面量**(在文件中找到 `class ProjectMemberAdd(BaseModel):` 段 L84,**之上**插入):

```python
# ── 项目成员初始化(立项时一站式批量插入,T-1105 新增) ──────────
class ProjectMemberInit(BaseModel):
    """立项时一次性指派的项目成员。不带 project_id(由 URL 上下文注入),
    其余字段与 ProjectMemberAdd 对齐 1:1。"""

    user_id: uuid.UUID
    track: str = Field(..., description="hardware / software / both")
    role_in_project: Optional[str] = Field(None, max_length=64)
```

**说明**:
- `track` 用 `str` 不用 `MemberTrack` enum(对齐 `ProjectMemberAdd` L87 现有写法 `track: str = Field(..., description="hardware / software / both")`)
- `user_id: uuid.UUID` 严格 UUID 类型(对齐 `ProjectMemberAdd` L86 `user_id: uuid.UUID`)
- `role_in_project: Optional[str] = Field(None, max_length=64)` 对齐 `ProjectMemberAdd` L88 + `ProjectMember.role_in_project: Mapped[Optional[str]] = mapped_column(String(64))` model 字面量

#### 3.1.2 扩展 `ProjectCreate` 类(L16-25 末尾**追加** `members` 字段)

**字面量**(在 `is_temporary: bool = Field(...)` 之后插入,**不动**前 7 行字段):

```python
    # T-1105 立项时一站式指派成员(可选,默认 None 等价于"零成员"现状)
    members: Optional[list[ProjectMemberInit]] = Field(
        None,
        max_length=50,
        description="立项时一次性指派的项目成员(0..50);None / [] 时走零成员路径,与现状 100% 兼容",
    )
```

**说明**:
- `max_length=50` 与 V2.5 `BatchRemoveMembersBody.member_ids` 的 `max_length=200` 不一致,**故意**:立项一次性指派通常 ≤ 20 人,50 给充裕余量;200 是批量移出场景的回收性能预留。
- 默认 `None` 而非 `[]`(语义区分:"未指定" vs "明确空列表",二者后端逻辑 100% 等价但更利于前端调用方语义清晰)。

#### 3.1.3 import 块**不动**(`Field` 已 import,`uuid` 已 import,`Optional` 已 import)

`backend/app/schemas/project.py` L1-12 import 块完整(`from typing import Optional` / `import uuid` / `from pydantic import BaseModel, Field` 已就位),**严禁**重排 / 删除。

### 3.2 后端 Router 扩展之一(改 `backend/app/routers/projects.py` 单函数 `create_project`)

#### 3.2.1 imports 块(`backend/app/routers/projects.py` L30-36)**插入式**追加 `ProjectMemberInit`

**字面量**(L30-36 现有 5 行 import 块,在 `ProjectMemberAdd,` 之后插入 `ProjectMemberInit,`):

```python
from app.schemas.project import (
    GanttStage,
    ProjectCreate,
    ProjectMemberAdd,
    ProjectMemberInit,  # T-1105 新增
    ProjectUpdate,
    StageUpdate,
)
```

**说明**:**严禁**重排现有 5 项 import(字母序略有偏离的现状保留即可)。

#### 3.2.2 `create_project` 函数(L250-423)末尾**插入式**追加成员批量插入逻辑

**插入点 1**:在 L418 `await db.commit()` **之前**插入成员批量插入逻辑(临时项目分支 L329-350 在 L343 已 `await db.commit()` + `return`,**先于**本插入点 return,所以本插入点只影响主干项目路径)。

**逻辑梳理**:
- 临时项目分支(L329-350)有自己的 `await db.commit() + return`,本任 T-1105 **不在临时项目分支内插入成员逻辑**,**而是把成员插入逻辑提前到** L323 `db.flush()` 之后 + 临时项目分支 + 主干分支**共享**前置,从而临时项目 + 主干项目都能享受立项指派
- **修正策略**(更严谨):在 L324 `await db.flush()  # 获取 project.id` **之后**、L326 临时项目分支 if **之前**插入"统一成员批量插入逻辑",作用域覆盖临时 + 主干两条分支

**字面量**(在 L324 `await db.flush()  # 获取 project.id` 之后,L326 `# ── V2.3 临时工单项目` 之前插入):

```python
    # T-1105 立项时一站式指派成员(主干 + 临时项目共享路径)
    # data.members 为 None / [] 时跳过,沿用零成员路径(向后兼容)
    if data.members:
        # 1. payload 内 user_id dedup 校验(同一 user_id 出现 2 次 → 400)
        seen_user_ids: set[uuid.UUID] = set()
        for m in data.members:
            if m.user_id in seen_user_ids:
                raise HTTPException(400, f"成员列表中重复的 user_id: {m.user_id}")
            seen_user_ids.add(m.user_id)
        # 2. 一次性校验 user_id 全部存在且同 tenant_id(零部分插入)
        existing_user_ids_q = await db.execute(
            select(User.id).where(
                User.id.in_(list(seen_user_ids)),
                User.tenant_id == creator.tenant_id,
            )
        )
        existing_user_ids = {row[0] for row in existing_user_ids_q.all()}
        missing_user_ids = seen_user_ids - existing_user_ids
        if missing_user_ids:
            raise HTTPException(
                400,
                f"以下 user_id 不存在或不属于当前 tenant: {sorted(str(u) for u in missing_user_ids)}",
            )
        # 3. 批量插入 ProjectMember(单事务,失败整体 rollback)
        for m in data.members:
            db.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=m.user_id,
                    track=m.track,
                    role_in_project=m.role_in_project,
                    tenant_id=creator.tenant_id,
                    created_by=creator.id,
                )
            )
        await db.flush()  # 让 partial UNIQUE (T-1002) 触发 IntegrityError 落到 router 异常处理
```

**说明**:
- **dedup**:payload 内 user_id 重复 → 400(对齐现有 POST `/{id}/members` L770 "已在成员列表" 409 不同语义 — 本任是 client payload 错误 = 400;现有单加路径是 DB 已存在状态 = 409)
- **批量存在性校验**:单 SQL `User.id.in_(list)` 一次性核对,避免 N+1
- **tenant 隔离**:`User.tenant_id == creator.tenant_id` 严格(对齐 L755 现有单加路径 tenant 过滤)
- **不**插入前再次检查 partial UNIQUE(由 DB 层 T-1002 `ix_project_members_project_user_active` 兜底,新建项目场景天然不会冲突)
- **`db.flush()`**:把 ProjectMember rows 推到 DB 触发 partial UNIQUE 检查,如有 IntegrityError 由 FastAPI 默认异常处理转 500(本任新建项目场景不应触发 — 同 project_id 内 user_id 已 dedup)

#### 3.2.3 临时项目分支返回体扩展(L344-350)

**字面量**(L344-350 临时项目分支 `return {...}` 字典,**追加** `members_added` 字段):

```python
        return {
            "message": "临时工单项目创建成功(轻量模式,无 IPD 阶段)",
            "project_id": str(project.id),
            "code": project.code,
            "is_temporary": True,
            "backlog_sprint_id": str(backlog_sprint.id),
            "members_added": len(data.members) if data.members else 0,  # T-1105 新增
        }
```

#### 3.2.4 主干项目分支返回体扩展(L419-423)

**字面量**(L419-423 主干项目 `return {...}` 字典,**追加** `members_added` 字段):

```python
    await db.commit()
    return {
        "message": "项目创建成功，已自动初始化5个 IPD 阶段及里程碑",
        "project_id": str(project.id),
        "code": project.code,
        "members_added": len(data.members) if data.members else 0,  # T-1105 新增
    }
```

**说明**:返回体扩展是 backward compatible(前端 ignore 多余字段),便于前端 toast 提示"项目 P2026-005 立项成功,已指派 3 名成员"。

### 3.3 后端 Router 扩展之二(改 `backend/app/routers/users.py` 末尾**插入式**追加 GET `/picker` 端点)

#### 3.3.1 imports 块(`backend/app/routers/users.py` L13-28)**不动**

`backend/app/routers/users.py` L20 已 import `from app.models.user import User, UserRole`,本任不需补 import。

#### 3.3.2 末尾**插入式**追加 `GET /picker` 端点(在文件最后一个 `@router.<METHOD>` 端点之后追加)

**插入点**:`backend/app/routers/users.py` 最后一个 `@router.get("/resource-load")` 端点函数体之后,在文件**末尾**追加。

**字面量**:

```python
# T-1105 立项指派成员用户选择器(轻量 + manager 可访问)
class UserPickerItem(BaseModel):
    """精简字段 — 用于立项 Modal / 项目成员追加场景的下拉选择器。"""

    id: str
    name: str
    department: str = ""
    role: str
    is_active: bool


@router.get("/picker", response_model=list[UserPickerItem])
async def list_users_for_picker(
    search: str = Query("", description="按姓名 / 部门 / 企微ID 模糊搜索"),
    include_inactive: bool = Query(False, description="是否包含已停用用户(默认 False)"),
    db: AsyncSession = Depends(get_db),
    _mgr: User = Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """
    立项指派成员 / 项目成员追加场景用户选择器。

    设计:
    - 与 `GET /users` 现有 admin-only 端点解耦:本端点 RBAC = admin + manager,
      避免 manager 立项时无法列用户的 RBAC gap
    - 字段精简到 id / name / department / role / is_active,降低数据传输量
    - 同 tenant_id 隔离(沿用 require_role 注入的 _mgr.tenant_id)
    - 默认过滤 is_active=True(立项不应指派已停用员工);可选 include_inactive=True
    - 不分页(一站式立项指派场景通常 ≤ 几百用户,前端可本地过滤)
    """
    stmt = select(User).where(User.tenant_id == _mgr.tenant_id)
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))
    if search:
        like_pat = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.name.ilike(like_pat),
                User.department.ilike(like_pat),
                User.wechat_userid.ilike(like_pat),
            )
        )
    stmt = stmt.order_by(User.name)
    rows = await db.execute(stmt)
    return [
        UserPickerItem(
            id=str(u.id),
            name=u.name,
            department=u.department or "",
            role=u.role.value,
            is_active=u.is_active,
        )
        for u in rows.scalars().all()
    ]
```

**说明**:
- **路由前缀**:`router = APIRouter(prefix="/api/v1/users", tags=["用户管理"])`(L30 已声明)→ 最终路径 = `GET /api/v1/users/picker`
- **RBAC**:`require_role(UserRole.admin, UserRole.manager)`(对齐 `_mgr` projects.py L43 体例,**严禁** employee 访问)
- **不分页**:用户表通常 < 1000 行,一次性返回 + 前端本地搜索;真要分页留给 T-1108+ 再说
- **`UserPickerItem` Pydantic 类**:在端点函数之**上**定义(对齐 projects.py L97 `class ProjectBatchDeleteBody(BaseModel):` 体例),内联 schema 不下沉到 `app/schemas/user.py`(避免大改 user schemas)
- **`from sqlalchemy import or_`**:L15 已 import,无需补
- **`BaseModel`**:L14 已 `from pydantic import BaseModel, Field` 已 import

### 3.4 前端 API 类型扩展之一(改 `frontend/src/api/projects.ts` ~+15 行)

#### 3.4.1 文件顶部**插入式**新增 ProjectMemberInit 类型 + createProject 重新声明

**字面量**(在 L30 `export const createProject = (data: any) => request.post('/projects/', data)` **之上**插入类型 + 替换 createProject 单行声明):

```typescript
// T-1105 立项时一站式指派成员(可选,默认空 → 走"零成员"路径)
export interface ProjectMemberInit {
  user_id: string  // UUID
  track: 'hardware' | 'software' | 'both'
  role_in_project?: string
}

export interface CreateProjectPayload {
  name: string
  code?: string
  description?: string
  track?: string
  planned_launch_date?: string  // ISO date
  budget_total?: number
  budget_alert_threshold?: number
  is_temporary?: boolean
  members?: ProjectMemberInit[]  // T-1105 新增
}

export const createProject = (data: CreateProjectPayload) => request.post('/projects/', data)
```

**说明**:
- 把 `createProject = (data: any)` 升级为 `createProject = (data: CreateProjectPayload)` 类型安全(对齐 V2.5 `batchRemoveProjectMembers` 端点 L24-29 已开始 `request.delete<unknown, {...}>` 类型化的趋势)
- **不动**其他 14 个 export 函数 / import 块 / `request` from `'@/api/request'`

### 3.5 前端 API 类型扩展之二(改 `frontend/src/api/users.ts` ~+8 行)

#### 3.5.1 文件末尾**插入式**新增 getUserPicker 函数

**字面量**(在 L70 `export const batchEnableUsers = ...` 之后追加):

```typescript

// T-1105 立项指派成员用户选择器(轻量 + manager 可访问)
export interface UserPickerItem {
  id: string
  name: string
  department: string
  role: string
  is_active: boolean
}

export const getUserPicker = (params: { search?: string; include_inactive?: boolean } = {}) =>
  request.get<unknown, UserPickerItem[]>('/users/picker', { params })
```

**说明**:
- **响应类型**:`UserPickerItem[]` 字面量与后端 `response_model=list[UserPickerItem]` 1:1 对齐
- **不动**现有 11 个 export 函数 / `UserStatus` 类型 / import 块

### 3.6 前端组件新建(`frontend/src/components/member-picker.tsx` ~200 行)

#### 3.6.1 组件设计目标

- 多选用户列表 + 每行配 track select + role_in_project 文本输入 + 移除按钮
- 顶部搜索框(本地过滤 + ilike 后端 fallback)
- 已选列表区块(顶部 chips 风格,易于增删)
- 未选区块(下拉 / inline 表格,可滚动)
- 可控属性:`value: ProjectMemberInit[]` + `onChange: (next: ProjectMemberInit[]) => void`
- 风格对齐 `admin/departments/page.tsx` Modal 设计语言(已成熟体例,T-1006 闭环)

#### 3.6.2 字面量骨架(Codex 落盘时按本骨架展开,允许 ±15% 行数偏移)

```typescript
/**
 * components/member-picker.tsx — 项目成员选择器(T-1105 立项指派成员场景)
 *
 * 可控组件:value: ProjectMemberInit[] + onChange 回调
 * 数据源:GET /api/v1/users/picker(manager + admin 可访问)
 *
 * 复用候选:
 *   - frontend/src/app/projects/page.tsx 立项 Modal(本任 T-1105 接入)
 *   - frontend/src/app/project/[id]/page.tsx activeTab='members' 单加(留作 T-1106+ 收紧候选)
 */
'use client'

import { useState, useEffect, useMemo } from 'react'
import { getUserPicker, type UserPickerItem } from '@/api/users'
import type { ProjectMemberInit } from '@/api/projects'
import { Search, X, Plus, UserPlus } from 'lucide-react'

interface MemberPickerProps {
  value: ProjectMemberInit[]
  onChange: (next: ProjectMemberInit[]) => void
  maxMembers?: number  // 默认 50,对齐后端 schema max_length
}

const TRACK_OPTIONS: Array<{ value: 'hardware' | 'software' | 'both'; label: string }> = [
  { value: 'both', label: '双轨' },
  { value: 'hardware', label: '硬件轨' },
  { value: 'software', label: '软件轨' },
]

export default function MemberPicker({ value, onChange, maxMembers = 50 }: MemberPickerProps) {
  const [users, setUsers] = useState<UserPickerItem[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [showPicker, setShowPicker] = useState(false)

  // 拉用户列表(挂载时一次性)
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getUserPicker()
      .then((data) => { if (!cancelled) setUsers(data as unknown as UserPickerItem[]) })
      .catch(() => { if (!cancelled) setUsers([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  // 已选 user_ids set(O(1) 查重)
  const selectedUserIds = useMemo(() => new Set(value.map((m) => m.user_id)), [value])

  // 未选 + 过滤
  const available = useMemo(() => {
    const q = search.toLowerCase()
    return users
      .filter((u) => !selectedUserIds.has(u.id))
      .filter((u) => !q || u.name.toLowerCase().includes(q) || (u.department || '').toLowerCase().includes(q))
  }, [users, selectedUserIds, search])

  function handleAdd(user: UserPickerItem) {
    if (value.length >= maxMembers) return
    onChange([...value, { user_id: user.id, track: 'both', role_in_project: '' }])
  }

  function handleRemove(userId: string) {
    onChange(value.filter((m) => m.user_id !== userId))
  }

  function handleUpdate(userId: string, patch: Partial<ProjectMemberInit>) {
    onChange(value.map((m) => (m.user_id === userId ? { ...m, ...patch } : m)))
  }

  // 已选列表展示用 — 把 user_id 反查到 name/department
  const selectedRows = useMemo(() => {
    const map = new Map(users.map((u) => [u.id, u]))
    return value.map((m) => ({ ...m, user: map.get(m.user_id) }))
  }, [value, users])

  return (
    <div className="space-y-3">
      {/* 标签 + 计数 */}
      <div className="flex items-center justify-between">
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          项目成员({value.length}/{maxMembers})
        </label>
        <button
          type="button"
          onClick={() => setShowPicker((v) => !v)}
          className="flex items-center gap-1 text-xs px-2 py-1 rounded"
          style={{ background: 'rgba(59,130,246,0.18)', color: '#93c5fd' }}
          disabled={value.length >= maxMembers}
          title={value.length >= maxMembers ? `已达上限 ${maxMembers} 人` : '点击添加成员'}
        >
          <UserPlus size={12} />
          {showPicker ? '收起' : '添加成员'}
        </button>
      </div>

      {/* 已选列表 */}
      {selectedRows.length > 0 && (
        <div className="space-y-2 max-h-48 overflow-y-auto rounded-lg p-2" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}>
          {selectedRows.map((row) => (
            <div key={row.user_id} className="flex items-center gap-2 text-xs">
              <span className="font-medium" style={{ color: 'var(--color-text-primary)', minWidth: 80 }}>
                {row.user?.name || '(未知用户)'}
              </span>
              <span className="text-[10px]" style={{ color: 'var(--color-text-secondary)', minWidth: 60 }}>
                {row.user?.department || '—'}
              </span>
              <select
                value={row.track}
                onChange={(e) => handleUpdate(row.user_id, { track: e.target.value as 'hardware' | 'software' | 'both' })}
                className="px-2 py-1 rounded text-xs"
                style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
              >
                {TRACK_OPTIONS.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <input
                type="text"
                value={row.role_in_project || ''}
                onChange={(e) => handleUpdate(row.user_id, { role_in_project: e.target.value })}
                placeholder="角色(可选,如 PM)"
                maxLength={64}
                className="flex-1 px-2 py-1 rounded text-xs"
                style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
              />
              <button
                type="button"
                onClick={() => handleRemove(row.user_id)}
                className="p-1 rounded hover:bg-red-500/15"
                title="移除"
              >
                <X size={12} color="#ef4444" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 候选列表(下拉)*/}
      {showPicker && (
        <div className="rounded-lg p-2 space-y-2" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}>
          <div className="relative">
            <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-secondary)' }} />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索姓名 / 部门..."
              className="w-full pl-7 pr-2 py-1.5 rounded text-xs"
              style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
            />
          </div>
          <div className="max-h-48 overflow-y-auto">
            {loading && (
              <div className="text-center text-xs py-3" style={{ color: 'var(--color-text-secondary)' }}>加载中...</div>
            )}
            {!loading && available.length === 0 && (
              <div className="text-center text-xs py-3" style={{ color: 'var(--color-text-secondary)' }}>
                {users.length === 0 ? '无可选用户' : '无搜索结果'}
              </div>
            )}
            {!loading && available.map((u) => (
              <button
                key={u.id}
                type="button"
                onClick={() => handleAdd(u)}
                disabled={value.length >= maxMembers}
                className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-xs text-left hover:bg-white/5 disabled:opacity-50"
              >
                <Plus size={11} color="#22c55e" />
                <span className="font-medium" style={{ color: 'var(--color-text-primary)', minWidth: 80 }}>{u.name}</span>
                <span className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
                  {u.department || '—'} · {u.role}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

**说明**:
- **复用候选**:留作 T-1106+ 项目详情页 `activeTab='members'` 单加路径 UI 收紧候选;本任 T-1105 仅接入立项 Modal
- **可控属性**:`value + onChange` 标准 React 受控组件模式
- **track 默认 'both'**:对齐 1.4 节"既不偏硬件也不偏软件"产品语义;Codex 落盘时可视 UX 测试决定换 'software' 默认(spec 字面量优先级 < UX 自洽)
- **`maxLength={64}`**:对齐 backend `ProjectMember.role_in_project: String(64)` model 字面量

### 3.7 前端 Modal 改造(改 `frontend/src/app/projects/page.tsx` ~+70 行)

#### 3.7.1 imports 块 L7-31 **插入式**追加 MemberPicker

**字面量**(在 L26 `import { toast } from 'sonner'` 之后插入):

```typescript
import MemberPicker from '@/components/member-picker'
import type { ProjectMemberInit } from '@/api/projects'
```

**说明**:**不动**现有 lucide-react icons import / `MAIN_TRACK_OPTIONS` 等其他 import 行。

#### 3.7.2 `projectForm` state 扩展(L111-119)

**字面量**(L111-119 现有 7 字段,**追加** `members` 字段):

```typescript
  const [projectForm, setProjectForm] = useState({
    name: '',
    code: '',
    description: '',
    track: 'dual',
    planned_launch_date: '',
    budget_total: 100000,
    is_temporary: false, // V2.3 临时工单项目
    members: [] as ProjectMemberInit[],  // T-1105 新增
  })
```

#### 3.7.3 `handleCreateProject` payload 构建(L166-200)— 把 members 注入 payload

**字面量**(L174-183 现有 payload 构建段,扩展支持 members):

```typescript
    setSubmitting(true)
    try {
      // 临时工单项目只传精简字段,避免后端强校验 budget/launch_date
      const payload: any = projectForm.is_temporary
        ? {
            name: projectForm.name,
            code: projectForm.code || undefined,
            description: projectForm.description || undefined,
            planned_launch_date: projectForm.planned_launch_date || undefined,
            is_temporary: true,
            track: projectForm.track, // 临时项目也允许选择轨道 (如日常支撑)
            // T-1105:临时项目也支持立项指派成员
            ...(projectForm.members.length > 0 ? { members: projectForm.members } : {}),
          }
        : {
            // T-1105:主干项目 payload 展开,显式列出字段以便注入 members
            name: projectForm.name,
            code: projectForm.code || undefined,
            description: projectForm.description || undefined,
            track: projectForm.track,
            planned_launch_date: projectForm.planned_launch_date || undefined,
            budget_total: projectForm.budget_total,
            is_temporary: false,
            ...(projectForm.members.length > 0 ? { members: projectForm.members } : {}),
          }
      const created = await createProject(payload) as any
      // T-1105:toast 提示带成员指派数
      const membersHint = projectForm.members.length > 0 ? ` · 已指派 ${projectForm.members.length} 名成员` : ''
      toast.success(
        projectForm.is_temporary
          ? `🎫 临时工单项目 ${created?.code || projectForm.name} 创建成功${membersHint}`
          : `项目 ${created?.code || projectForm.code || projectForm.name} 立项成功${membersHint}`,
      )
      setShowCreate(false)
      setProjectForm({ name: '', code: '', description: '', track: 'dual', planned_launch_date: '', budget_total: 100000, is_temporary: false, members: [] })
      // 创建临时项目后,自动开启 includeTemporary 让用户能立即看到
      if (projectForm.is_temporary) setIncludeTemporary(true)
      fetchProjects()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '立项失败')
    } finally {
      setSubmitting(false)
    }
```

**说明**:
- **payload spread 替换隐式 `: projectForm`**:原代码 non-temp 分支是 `: projectForm`(隐式 spread),现在显式列字段以保证 `members` 字段精确注入(并保证 `members: []` 时不带 `members` key,与现状 100% 兼容 — `...(projectForm.members.length > 0 ? { members: projectForm.members } : {})`)
- **reset state**:`setProjectForm({...., members: []})` 重置后保持空数组(避免下次开 Modal 残留)
- **toast hint**:成员指派数显式提示,提升用户感知

#### 3.7.4 Modal JSX 末尾**插入式**追加 MemberPicker 块(L848-864 预算字段之后)

**字面量**(在 L862-863 `</>` + `)}` 临时工单条件结束之后,L865 `<div className="flex justify-end gap-3 mt-6">` 按钮区域**之前**插入):

```jsx
              {/* T-1105 立项指派成员选择器(可选,主干 + 临时项目共享) */}
              <MemberPicker
                value={projectForm.members}
                onChange={(next) => setProjectForm({ ...projectForm, members: next })}
              />
```

**说明**:
- **位置**:在所有现有字段(临时工单复选框 / 项目名称 / 项目编号 / 项目描述 / 轨道 / 计划交付 / 预算总额)**之后**、确认按钮**之前**,语义对齐"先描述项目再指派人员"用户心智
- **临时 + 主干共享**:与 §3.2.2 后端逻辑一致,临时项目也可指派成员

#### 3.7.5 **不动**清单(零回归承诺)

- 🚫 **不动** 编辑项目 Modal(L887-972)— `editForm` state + 编辑流程完全不动
- 🚫 **不动** 归档确认 Modal(L975-1017)
- 🚫 **不动** 卡片列表(L577-749)、统计条(L435-477)、搜索框(L480-491)、FilterBar(L495-504)、includeArchived/includeTemporary 切换(L506-539)、批量操作栏(L542-574)
- 🚫 **不动** `useListFilters` / `useMultiSelect` / `handleBatchSoftDelete` / `handleBatchArchive` / `openEditModal` / `handleSaveEdit` / `handleToggleStatus` / `handleRestore` / `handleArchive` 任何函数

### 3.8 测试新建(`backend/tests/test_phase11_project_members.py` ~280 行 ~12 case)

#### 3.8.1 fixtures 消费(对齐 T-1104 体例)

- `db_session`(conftest.py autouse,rollback per case)
- `client`(conftest.py autouse,dependency_overrides)
- `_isolation_external_settings`(autouse fixture,T-1103 已落地)

#### 3.8.2 私有 helpers 命名前缀 `_phase11_picker_*`(对齐 T-1104 `_phase11_*` + T-1007 `_phase10_*` 体例)

```python
async def _cleanup_phase11_picker_test_data(db_session: AsyncSession) -> None:
    """清理 wechat_userid like "phase11_picker_%" + projects.code like "phase11_picker_%" 残留"""
    ...

def _phase11_picker_headers(token: str) -> dict[str, str]:
    """构造 Authorization header"""
    ...

async def _phase11_picker_make_user(
    db_session: AsyncSession,
    *,
    wechat_userid: str,
    name: str = "测试用户",
    role: UserRole = UserRole.employee,
    department: str = "",
    is_active: bool = True,
) -> User:
    """构造 User(must_change_password=False 对齐 T-1101 体例)"""
    ...
```

#### 3.8.3 ~12 case 命名锁定字面量

**Schema 层(3 case)**:
1. `test_project_create_accepts_members_field` — payload 含 `members: [{user_id, track, role_in_project}]` Pydantic 校验通过
2. `test_project_create_accepts_none_members` — payload 不带 `members` / `members=None` 均接受(向后兼容)
3. `test_project_member_init_max_length_50_enforced` — payload `members: [51 项]` Pydantic 422

**Router 层 — 主干项目(4 case)**:
4. `test_create_project_with_3_members_success` — 主干项目 POST `/` + members 3 项 → DB 内 1 Project + 5 ProjectStages + 3 ProjectMember,返回体 `members_added: 3`
5. `test_create_project_with_empty_members_zero_member_path` — payload `members: []` → 走零成员路径(DB 内 1 Project + 0 ProjectMember,等价于现状)
6. `test_create_project_with_duplicate_user_ids_400` — payload `members: [{u1,...},{u1,...}]` → 400 "成员列表中重复的 user_id"
7. `test_create_project_with_missing_user_id_400_rollback` — payload `members: [{nonexistent_uuid,...}]` → 400 "以下 user_id 不存在",**且 DB 内 0 Project + 0 ProjectMember**(整事务 rollback)

**Router 层 — 临时项目(1 case)**:
8. `test_create_temporary_project_with_2_members_success` — 临时项目 + members 2 项 → DB 内 1 Project(is_temporary=True)+ 1 Sprint(sprint_number=0 Backlog)+ 2 ProjectMember,返回体 `members_added: 2 + is_temporary: True`

**Router 层 — Picker 端点(3 case)**:
9. `test_user_picker_admin_lists_users` — admin GET `/api/v1/users/picker` → 200 + `list[UserPickerItem]`,默认过滤 `is_active=True`
10. `test_user_picker_manager_lists_users` — manager GET `/api/v1/users/picker` → 200(对齐"立项指派 manager 也可调"产品意图)
11. `test_user_picker_employee_403` — employee GET `/api/v1/users/picker` → 403

**Router 层 — 跨 tenant 隔离(1 case)**:
12. `test_create_project_members_cross_tenant_user_id_blocked` — payload `members: [{user_in_other_tenant_id,...}]` → 400 "以下 user_id 不存在"(tenant_id 过滤生效)

#### 3.8.4 测试纪律(对齐 T-1007 / T-1104 体例)

- 每 case 入口**强制** `await _cleanup_phase11_picker_test_data(db_session)`
- 作用域:`wechat_userid like "phase11_picker_%"` + `projects.code like "phase11_picker_%"`
- **零** mock / monkeypatch / skip / print / logger.* / sleep
- 命名前缀 `_phase11_picker_*` 严格(对齐 `_phase11_*` T-1104 + `_phase10_*` T-1007 体例)

### 3.9 fail-safe self-check grep 闸门(Codex 提交前自跑,共 7 项)

```bash
cd backend
# 1. 零 models / 零 migration 改动
git diff a532041..HEAD -- app/models/ alembic/ | wc -l  # 必须 = 0

# 2. 零 services 改动(T-1105 全在 router 层)
git diff a532041..HEAD -- app/services/ | wc -l  # 必须 = 0

# 3. 零 schemas/user.py 改动(只允许 schemas/project.py 改)
git diff a532041..HEAD -- app/schemas/user.py | wc -l  # 必须 = 0

# 4. 零 conftest / _isolation / _db_url / .env / README / DEPLOY
git diff a532041..HEAD -- conftest.py tests/_isolation.py tests/_db_url.py .env.example pyproject.toml requirements.txt | wc -l  # 必须 = 0

# 5. 零 T-1104 文件改动
git diff a532041..HEAD -- alembic/versions/20260529_*.py app/models/user.py app/services/_department_resolver.py app/services/department_service.py tests/test_phase11_dept_fk.py | wc -l  # 必须 = 0

# 6. 零前端无关页面改动
cd ../frontend
git diff a532041..HEAD -- src/app/project/ src/app/dashboard/ src/app/admin/ src/app/users/ src/components/sidebar.tsx src/components/dashboard/ src/components/charts/ | wc -l  # 必须 = 0

# 7. project router 只改 create_project 单函数(不动 add_project_member / batch_remove_members / list_project_members 等)
cd ../backend
git diff a532041..HEAD -- app/routers/projects.py | grep -E "^[-+] " | grep -vE "create_project|ProjectMemberInit|members|seen_user_ids|existing_user_ids|missing_user_ids|members_added" | wc -l  # 期望少量(imports + 注释行)
```

---

## §4 文件改动清单(8 文件 = 5 改 + 3 新建 + docs)

### 4.1 backend(5 文件)

| # | 文件 | 类型 | 改动估算 |
|---|---|---|---|
| 1 | `backend/app/schemas/project.py` | 改 | +22 行(新增 `ProjectMemberInit` + 扩 `ProjectCreate.members`) |
| 2 | `backend/app/routers/projects.py` | 改 | ~+70 行(imports +1 + `create_project` 内成员插入逻辑 + 临时 / 主干分支返回体扩 `members_added`) |
| 3 | `backend/app/routers/users.py` | 改 | ~+50 行(末尾追加 `UserPickerItem` + `GET /picker` 端点) |
| 4 | `backend/tests/test_phase11_project_members.py` | 新建 | ~280 行 ~12 case |

### 4.2 frontend(3 文件)

| # | 文件 | 类型 | 改动估算 |
|---|---|---|---|
| 5 | `frontend/src/api/projects.ts` | 改 | ~+15 行(新增 `ProjectMemberInit` + `CreateProjectPayload` interface + 替换 `createProject` 单行声明) |
| 6 | `frontend/src/api/users.ts` | 改 | ~+8 行(新增 `UserPickerItem` interface + `getUserPicker` 函数) |
| 7 | `frontend/src/components/member-picker.tsx` | 新建 | ~200 行(可控组件) |
| 8 | `frontend/src/app/projects/page.tsx` | 改 | ~+70 行(imports +2 + projectForm state 扩 + handleCreateProject 重构 payload + Modal JSX 插入 MemberPicker 块) |

### 4.3 docs(1 文件,chore commit 内)

| # | 文件 | 类型 | 改动估算 |
|---|---|---|---|
| 9 | `docs/dev_tasks.md` | 改 | +~30 / -2(Task 5 条目 `[/]` → `[x]` + 📣 锚点替换为 T-1105 完工字面量) |

### 4.4 严禁夹带清单(9 项)

零夹带闸门 — `git diff a532041..HEAD` 必须**完全没有**触碰以下文件 / 路径:

1. `backend/app/models/` 任意文件
2. `backend/alembic/` 任意文件
3. `backend/app/services/` 任意文件
4. `backend/app/schemas/` 除 `project.py` 外的任意文件
5. `backend/app/routers/` 除 `projects.py` + `users.py` 外的任意文件
6. `backend/conftest.py` / `backend/tests/_isolation.py` / `backend/tests/_db_url.py`
7. `backend/.env*` / `README.md` / `DEPLOY.md`
8. `backend/pyproject.toml` / `backend/requirements.txt` / `backend/uv.lock`
9. `frontend/src/app/` 除 `projects/page.tsx` 外的任意文件 + `frontend/src/components/` 除新建 `member-picker.tsx` 外的任意文件

---

## §5 测试要求

### 5.1 ~12 case 命名 100% 字面量锁定(参 §3.8.3)

12 个 `async def test_*` 函数命名严格对齐 §3.8.3 字面量。Codex 改名 = BLOCKER 驳回。

### 5.2 helper 命名锁定

- `_cleanup_phase11_picker_test_data` 入口必跑
- `_phase11_picker_make_user` / `_phase11_picker_make_project` / `_phase11_picker_headers` 等 helper 前缀 `_phase11_picker_*` 严格

### 5.3 测试基线零回归承诺

- T-1104 完工基线 `193 passed, 2 skipped`
- T-1105 完工预期 `205 passed, 2 skipped`(+12 case)
- 全量 `pytest -q` 必须达成 205 / 2 / 0 failed,任一 case 回归 = BLOCKER 驳回

### 5.4 测试纪律

- **零** mock(包括 `unittest.mock` / `pytest-mock`)
- **零** monkeypatch(包括 `monkeypatch.setattr` / `monkeypatch.setenv`)
- **零** `@pytest.mark.skip` / `@pytest.mark.skipif`
- **零** `print(...)` / `logger.*` 调用
- **零** `time.sleep` / `asyncio.sleep`
- **零** 直接读 `os.environ` / `os.getenv`(autouse `_isolation_external_settings` 已 clean)

### 5.5 grep 闸门(Codex 提交前自跑)

```bash
cd backend
grep -E "mock|monkeypatch|skip|print\(|logger\.|asyncio\.sleep|time\.sleep|os\.(environ|getenv)" tests/test_phase11_project_members.py | wc -l  # 必须 = 0
grep -c "^async def test_" tests/test_phase11_project_members.py  # 必须 = 12
grep -c "_phase11_picker_" tests/test_phase11_project_members.py  # 必须 ≥ 12(每 case 至少 cleanup 1 次)
```

---

## §6 质量闸门(Codex 提交前必跑)

```bash
# 后端
cd backend
.venv/bin/ruff check app/schemas/project.py app/routers/projects.py app/routers/users.py tests/test_phase11_project_members.py
.venv/bin/mypy app/schemas/project.py app/routers/projects.py app/routers/users.py
.venv/bin/pytest tests/test_phase11_project_members.py -v  # 期望 12 passed
.venv/bin/pytest -q  # 期望 205 passed, 2 skipped(从 T-1104 完工基线 193 + 12)

# alembic 零改动闸门
.venv/bin/alembic check  # 跳过依据 T-1101/1102/1103 既定 Supervisor 特批(local DB drift 误报)

# 前端
cd ../frontend
npm run lint  # 期望 0 error
npm run typecheck  # 期望 0 error
```

**全绿后才能打 feat / chore 双 commit**。

---

## §7 commit 纪律

### 7.1 双 commit 原子收口

#### 7.1.1 第一 commit:feat(全部 7 src/test 文件 + ~3 frontend 文件)

```
feat(projects): T-1105 立项时一站式指派成员 — ProjectCreate.members 扩展 + GET /users/picker + MemberPicker 组件

T-1105 临时插队:Phase 11 第五任(原 T-1105 FK 第二阶段顺延为 T-1106 候选)

业务点:
- 立项 Modal 末尾新增"项目成员"分块,支持 0..50 成员一站式指派
- 主干项目 + 临时工单项目共享立项指派路径(临时项目轻量化不冲突)
- payload 内 user_id dedup + 跨 tenant 严格隔离 + 整事务原子性(单失败全 rollback)

后端扩展:
- schemas/project.py: 新增 ProjectMemberInit 类 + ProjectCreate 加 members 字段(默认 None 向后兼容)
- routers/projects.py: create_project 函数末尾插入式批量插入逻辑(payload dedup + 一次性存在性校验 + 单事务批插)
- routers/users.py: 末尾插入式新增 GET /api/v1/users/picker 端点(RBAC = admin+manager,弥补 manager 端用户列表 RBAC gap)
- tests/test_phase11_project_members.py: 新建 ~12 case(Schema 3 + 主干 4 + 临时 1 + Picker 3 + tenant 1)

前端接入:
- api/projects.ts: 新增 ProjectMemberInit + CreateProjectPayload type
- api/users.ts: 新增 UserPickerItem + getUserPicker 函数
- components/member-picker.tsx: 新建可控组件(value + onChange,支持搜索 + 已选 + 候选两区)
- app/projects/page.tsx: 立项 Modal 末尾插入 MemberPicker;handleCreateProject payload 显式 spread 注入 members(0 成员时不带 members key 向后兼容)

零回归承诺:
- T-1104 5 backend 文件零改动
- 现有 POST /{id}/members + DELETE /{id}/members/batch + GET /{id}/members 三端点零改动
- 项目详情页 activeTab='members' UI 零改动
- 现有 ProjectMember partial UNIQUE(T-1002)兜底新建项目场景 user_id dedup
- 测试基线 T-1104 193 → T-1105 205 严格(+12)

[alembic check 跳过依据 T-1101/1102/1103 既定 Supervisor 特批 — local DB drift 误报]

Worker timestamp: [2026-05-29 HH:MM:SS]
```

**文件清单**(7 文件):
1. `backend/app/schemas/project.py`
2. `backend/app/routers/projects.py`
3. `backend/app/routers/users.py`
4. `backend/tests/test_phase11_project_members.py`
5. `frontend/src/api/projects.ts`
6. `frontend/src/api/users.ts`
7. `frontend/src/components/member-picker.tsx`
8. `frontend/src/app/projects/page.tsx`

#### 7.1.2 第二 commit:chore(progress)(1 文件)

```
chore(progress): close T-1105 — 立项时一站式指派成员(临时插队,Phase 11 第五任)

完工概要:
- 立项 Modal 支持 0..50 成员一站式指派,临时 + 主干项目共享路径
- 后端原子事务承诺(payload dedup + 跨 tenant 隔离 + 单失败全 rollback)
- Manager 端 RBAC gap 修复(GET /users/picker 弥补 admin-only /users 现状)
- MemberPicker 组件就位,留作 T-1106+ 项目详情页单加路径 UI 收紧候选

文件改动:
- docs/dev_tasks.md: Task 5 [/] → [x] + 📣 锚点替换为 T-1105 完工字面量(等待指挥官二次验收)

严禁项遵守证据:
- 0 models (backend/app/models/)
- 0 migration (backend/alembic/)
- 0 services (backend/app/services/)
- 0 schemas/user.py
- 0 routers 除 projects.py + users.py 外
- 0 conftest / _isolation / _db_url
- 0 .env* / README / DEPLOY
- 0 pyproject / requirements / uv.lock
- 0 T-1104 5 文件改动
- 0 项目详情页 / dashboard / admin / users / sidebar 改动
- 0 git push / stash / amend / rebase
- 0 T-1106 / T-1107 自启

[alembic check 跳过依据 T-1101/1102/1103 既定 Supervisor 特批 — local DB drift 误报]

Worker timestamp: [2026-05-29 HH:MM:SS]
```

**文件清单**(1 文件):
1. `docs/dev_tasks.md`

### 7.2 commit 通用要求

- 双 commit 必带 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]`(CLAUDE.md #7)
- **严禁** `git push`(等指挥官接手二次验收)
- **严禁** `git stash`(跨 Agent 不可见,违反 CLAUDE.md #5)
- **严禁** amend / rebase 历史 commit(违反 CLAUDE.md #4)
- **严禁** `--no-verify` 跳过 pre-commit hook
- chore commit body 必含完工概要 + 文件清单 + 严禁项遵守证据(对齐 T-1103 + T-1104 风格)

---

## §8 验收清单(指挥官二次验收用,共 28 项)

### 8.1 改动面闸门(8 项)

1. ☐ commit 链路干净:从 `a532041` 出发,仅 3 commit(`chore(lock)` → `feat(projects)` → `chore(progress)`)
2. ☐ feat commit 严格 8 文件(对齐 §7.1.1 文件清单 1-8)
3. ☐ chore commit 严格 1 文件(`docs/dev_tasks.md`)
4. ☐ **零夹带闸门** §4.4 9 项 grep 全 0:`git diff a532041..HEAD -- <严禁路径>` 完全空
5. ☐ §3.9 fail-safe self-check 7 项 grep 全通过(`backend/app/models/` / `services/` / `schemas/user.py` / conftest / T-1104 文件 / 无关前端页面 / `projects.py` 单函数作用域均为 0 diff)
6. ☐ Worker timestamp 双 commit 均带(grep `Worker timestamp` 各 1 hit)
7. ☐ chore commit body 含完工概要 + 文件清单 + 严禁项遵守证据(11 项遵守证据全到位,对齐 T-1103 / T-1104 chore 风格)
8. ☐ 4 既定 untracked 保留未污染(`backend/.env` / `backend/uv.lock` / 历史既定 2 项)

### 8.2 Schema + Router 闸门(7 项)

9. ☐ `ProjectMemberInit` 类字面量对齐 §3.1.1(`user_id: uuid.UUID` + `track: str` + `role_in_project: Optional[str] = Field(None, max_length=64)`)
10. ☐ `ProjectCreate.members: Optional[list[ProjectMemberInit]] = Field(None, max_length=50, ...)` 字面量对齐 §3.1.2
11. ☐ `create_project` 函数内成员批量插入逻辑插入点在 `db.flush()` 之后、临时项目 if 分支之前(对齐 §3.2.2)
12. ☐ payload dedup 字面量 `"成员列表中重复的 user_id: {m.user_id}"` 400(对齐 §3.2.2)
13. ☐ 存在性校验字面量 `"以下 user_id 不存在或不属于当前 tenant: ..."` 400(对齐 §3.2.2)
14. ☐ 临时 + 主干分支返回体均扩 `members_added: int`(对齐 §3.2.3 / §3.2.4)
15. ☐ `GET /api/v1/users/picker` 端点 RBAC = `require_role(UserRole.admin, UserRole.manager)`,响应体 `list[UserPickerItem]`(对齐 §3.3.2)

### 8.3 前端闸门(6 项)

16. ☐ `frontend/src/api/projects.ts` `ProjectMemberInit + CreateProjectPayload + createProject(data: CreateProjectPayload)` 三件套对齐 §3.4.1
17. ☐ `frontend/src/api/users.ts` `UserPickerItem + getUserPicker` 对齐 §3.5.1
18. ☐ `frontend/src/components/member-picker.tsx` 新建,可控组件(value + onChange),包含搜索框 + 已选 + 候选三区(对齐 §3.6.2 骨架,允许 ±15% 行数偏移)
19. ☐ `frontend/src/app/projects/page.tsx` imports +2(`MemberPicker` + `ProjectMemberInit type`)
20. ☐ `projectForm` state 加 `members: [] as ProjectMemberInit[]`(对齐 §3.7.2)
21. ☐ Modal JSX 在预算字段之后、按钮区域之前插入 `<MemberPicker value={...} onChange={...} />`(对齐 §3.7.4 位置 + 字面量)

### 8.4 测试闸门(5 项)

22. ☐ 12 case 命名 100% 对齐 §3.8.3 字面量(`grep -c "^async def test_" tests/test_phase11_project_members.py` = 12)
23. ☐ 4 类 case 分布:Schema 3 + 主干 4 + 临时 1 + Picker 3 + tenant 1 = 12
24. ☐ `_phase11_picker_*` helper 命名前缀严格(对齐 §3.8.2)
25. ☐ `pytest tests/test_phase11_project_members.py -v` 12/12 PASS
26. ☐ `pytest -q` 全量 `205 passed, 2 skipped`(从 T-1104 完工基线 193 + 12)

### 8.5 文档 + 协议闸门(2 项)

27. ☐ `dev_tasks.md` Task 5 标识 `[x] Done by Codex [YYYY-MM-DD HH:MM:SS]`
28. ☐ `dev_tasks.md` 末尾 📣 锚点替换为 T-1105 完工字面量(等待指挥官二次验收的口径)+ Phase 11 候选 backlog 状态更新(T-1106 候选 = 原 T-1105 FK 第二阶段顺延 / T-1107 候选 = 原 T-1106 drop column 顺延)

---

## §9 风险与回滚

### 9.1 风险点 5 项

| # | 风险 | 触发条件 | 应对 |
|---|---|---|---|
| 1 | **payload 含已停用用户 ID** | 立项 Modal 没过滤 `is_active=False` 用户 | 后端 `GET /users/picker` 默认 `is_active=True` + 前端 `<MemberPicker>` 默认请求不带 `include_inactive`,双层防御 |
| 2 | **partial UNIQUE 触发 IntegrityError** | 立项场景同 project_id 内 user_id 应当已 dedup 不触发,但若 DB race 导致 | dedup 后单事务批插已最大化降低概率;真触发 → 500 由 FastAPI 兜底(立项失败 + 整 rollback) |
| 3 | **大批量(40+ 成员)立项 performance** | 单 POST `/projects/` 批插 50 ProjectMember | 实际 ORM batch insert + `db.flush()` 单 SQL 多 VALUES,百级以内 < 100ms;真到性能瓶颈留给 T-1108+ |
| 4 | **跨 tenant user_id 注入攻击** | 恶意 actor 在 payload 注入其他 tenant 的 user_id | §3.2.2 存在性校验 `User.tenant_id == creator.tenant_id` 严格防御,400 拒绝 + 整 rollback |
| 5 | **前端 MemberPicker 渲染大量用户(1000+)卡顿** | 未分页 + 未虚拟列表 | 当前用户量级远未到瓶颈;真触发 → MemberPicker 加 react-window 虚拟列表(留给 T-1108+) |

### 9.2 回滚动作(production hot rollback)

```bash
# 一键 revert(production 环境无 schema 改动,纯应用层)
git revert <T-1105 feat commit>
git revert <T-1105 chore commit>
# 结果:
# - ProjectCreate.members 字段移除(向后兼容,旧前端调用不带 members 仍 work)
# - GET /users/picker 端点移除(若有前端调用方残留会 404 但不影响其他流程)
# - 已立项的 Project + ProjectMember 数据**完整保留**(DB 层零改动)
# - 影响时间窗口:< 1 分钟(纯代码 revert + reload uvicorn)
```

### 9.3 回滚后跟进

- 已立项的 Project + ProjectMember 数据完整保留(本任零 schema 改动,纯应用层扩展)
- 若回滚后前端发现"立项 Modal 找不到成员区块"是预期行为(回滚到 T-1104 完工 baseline)
- 指挥官二次验收 BLOCKER 时,可直接 `git revert <feat commit>` + `git revert <chore commit>`(双 commit 倒序 revert),无需 force-push

---

## §10 内部矛盾签字(指挥官 [2026-05-29 11:10:44])

本 spec 起草前已由指挥官在 Auto Mode 下做出 6 项关键架构决策,显式签字以利用户审阅 spec 时一次性拍板:

| # | 决策点 | 指挥官选择 | 理由 |
|---|---|---|---|
| 1 | **API 改动策略** | A. 扩 `ProjectCreate.members` + 后端原子批插 | 单事务一致性最优;前端 single round-trip 简单;消除前端串调 N 次 POST `/{id}/members` 的部分失败漂移风险 |
| 2 | **成员必填性** | 否,允许 0 成员(`members: Optional` 默认 `None`) | 向后 100% 兼容现有前端调用;解耦立项 + 指派两个产品决策点;留作"先立项后追加"现有工作流 |
| 3 | **临时工单是否允许指派成员** | 是,临时 + 主干共享立项指派路径 | 对齐"立项即指派"统一语义;临时项目轻量化只是跳过 IPD 阶段,不限制成员;避免割裂用户心智 |
| 4 | **manager 端用户列表 RBAC gap** | 新建 `GET /api/v1/users/picker` 端点(RBAC = admin + manager,精简字段)| 不破坏现有 admin-only `GET /users` contract;为立项 / 项目成员追加等多场景共用;字段精简降低数据传输 |
| 5 | **track 默认值** | `'both'`(双轨)| 既不偏硬件也不偏软件,中性兜底;UX 测试后 Codex 可视需要换 'software'(spec 字面量优先级 < 落盘前 UX 自洽) |
| 6 | **现有 POST `/{id}/members` 单加路径处置** | **完全冻结**,留作"立项后追加" | 严格作用域纪律(对齐 T-1004 / T-1005 / T-1006 不改既有端点);避免破坏 V2.5 `batch_remove_members` 等下游依赖 |

### 10.1 spec 自洽校验

- 无内部矛盾(§3.1 字面量 + §3.2 字面量 + §3.3 字面量 + §3.4-3.7 前端字面量 + §3.8 case 命名 + §7 commit body 描述全数自洽)
- §3.6.2 MemberPicker 组件骨架行数 ~200 行 vs §4.2 估算 ~200 行(±15% 允许),Codex 落盘时按 UX 自洽
- §3.2.2 成员批插逻辑位于 L324 `db.flush()` 之后 + 临时项目 if 分支之前 → 临时 + 主干共享 → §3.2.3 + §3.2.4 双分支返回体均扩 `members_added`(对齐)
- §3.3.2 `GET /users/picker` 端点字面量 + RBAC `require_role(admin, manager)` + §3.5.1 前端 `getUserPicker` 函数 + §3.6.2 MemberPicker `getUserPicker()` 调用三处呼应

### 10.2 spec 起草盲点防御

- T-1102 spec 起草曾遗漏全仓 `.replace(...)` 11 处残留,T-1103 补救后形成"全仓 grep 闸门"经验。本任 T-1105 已对应预防:
  - §3.9 fail-safe self-check 7 项 grep 闸门由 Codex 在 commit 前自跑
  - §4.4 严禁夹带清单 9 项作为 spec 字面量,验收 §8.1 第 4-5 项作为指挥官二次验收闸门
- §3.2.2 成员批插逻辑**严格作用域**:仅在 `create_project` 单函数内插入,**不**改 `add_project_member` / `batch_remove_members` / `list_project_members` / `update_project` / `archive_project` / `batch_soft_delete_projects` / `batch_restore_projects` / `get_deleted_projects` / `projects_overview` 等其他 11 个 router 函数(对齐 T-1003 / T-1004 / T-1005 三轨道严格作用域纪律)
- §3.3.2 新增 `/users/picker` 端点**严格末尾追加**,不动 `list_users` / `create_user` / `update_user` / `delete_user` / `batch_disable_users` / `batch_enable_users` / `reset_password` / `update_user_status` / `get_resource_load` 等 9 个现有端点
- §3.7.5 前端 Modal 改造**严格作用域**:仅在新建项目 Modal 内插入 MemberPicker,**不**改 编辑 Modal / 归档 Modal / 卡片列表 / 统计条 / 搜索 / FilterBar / 切换 toggle / 批量操作栏

### 10.3 T-1104 二次验收并行说明

- T-1104 工程已完工(commit `a532041`),但**指挥官二次验收回执尚未走完**(对话上下文中 28 项验收清单未逐项核对)
- T-1105 起草建立在"T-1104 工程完工 + 二次验收 follow-up"的混合基线之上
- 指挥官在 T-1105 起草 commit 落盘后,可选择:
  - A. 立即回补 T-1104 二次验收回执(在 dev_tasks.md Task 4 行**保留 Codex 完工回执** + **追加指挥官二次验收回执**),然后启动 T-1105 Codex 接手
  - B. T-1105 完工后,T-1104 + T-1105 两任二次验收一次性统一回补(批量验收)
- 本 spec 不强制选择;Codex 接手 T-1105 不依赖 T-1104 二次验收 PASS(基线 commit `a532041` 即可)

---

## 📣 附录:给 Worker(Codex)的物理交接单

> **指挥官时间戳**:`[2026-05-29 11:10:44]`
> **当前持牌任务**:T-1105(Phase 11 第五任 — 临时插队:立项时一站式指派成员)
> **依赖前置**:T-1104 工程完工(基线 `a532041`),指挥官二次验收 follow-up

### 恢复执行指令(Codex 接手时必跑)

1. **静默 Git 探针**(CLAUDE.md #1):
   ```bash
   git status --short --branch
   git log -5 --oneline
   git diff
   git diff --cached
   git rev-list --left-right --count origin/main...HEAD  # 期望 0 5(本地领先 5 commit:T-1104 4 + T-1105 spec 1)
   ```
2. **读盘**:
   - `docs/T-1105_spec.md` 全文(本文件,~700 行 10 章 + 📣 附录)
   - `docs/dev_tasks.md` 末尾 📣 锚点段(T-1105 持牌字面量)
   - `backend/app/schemas/project.py:84` (`ProjectMemberAdd` 类参考 + 在它之上插入 `ProjectMemberInit`)
   - `backend/app/routers/projects.py:248-423` (`create_project` 函数全文,找 L324 `db.flush()` 插入点)
   - `backend/app/routers/users.py:1-71` 末尾追加 `GET /picker` 端点(文件末尾)
   - `frontend/src/api/projects.ts:30` (`createProject` 单行声明替换为 `(data: CreateProjectPayload)`)
   - `frontend/src/api/users.ts:70` 末尾追加 `getUserPicker`
   - `frontend/src/app/projects/page.tsx:111-119` (`projectForm` state 扩 `members`)+ `L166-200` (handleCreateProject payload 重构)+ `L795-863` (Modal 字段块末尾插入 MemberPicker)
3. **二次确认 alembic head**(尽管本任零 migration):
   ```bash
   cd backend && .venv/bin/alembic heads
   ```
   - 本任**零** migration,不动 alembic chain;head 应当是 T-1104 引入的字面量(`a532041` 内 `20260529_1037_phase11_user_department_id_fk.py`)
4. **改 `docs/dev_tasks.md` Task 5 → `[/]`** + 单 commit `chore(lock): T-1105 开工`(CLAUDE.md #3 加锁)
   ```
   chore(lock): T-1105 开工 — Phase 11 第五任 立项时一站式指派成员(临时插队)

   Worker timestamp: [2026-05-29 HH:MM:SS]
   ```
5. **按 §3 实施细则 8 文件改动**:
   - 3 改 backend(`schemas/project.py` + `routers/projects.py` + `routers/users.py`)
   - 1 新建 test(`tests/test_phase11_project_members.py` ~280 行 ~12 case)
   - 2 改 frontend(`api/projects.ts` + `api/users.ts`)
   - 1 新建 frontend(`components/member-picker.tsx` ~200 行)
   - 1 改 frontend(`app/projects/page.tsx` 立项 Modal)
6. **§6 质量闸门 6+ 项全跑**:
   - ruff(4 backend 文件)
   - mypy(3 backend src 文件)
   - pytest 子集(12/12 PASS)+ 全量(205 passed + 2 skipped)
   - frontend lint + typecheck(零 error)
   - alembic check 跳过(Supervisor 既定特批)
   - §3.9 fail-safe self-check 7 项 grep 全 0
7. **§7 commit 纪律 2 commit 原子收口**:
   - Commit 1:`feat(projects): T-1105 ...` 8 文件,Worker timestamp 必带,body 含业务点 + 后端扩展 + 前端接入 + 零回归承诺
   - Commit 2:`chore(progress): close T-1105 ...` 1 文件(`docs/dev_tasks.md` Task 5 → `[x]` + 📣 锚点替换),Worker timestamp 必带 + body 含完工概要 + 文件清单 + 11 项严禁项遵守证据
8. **完工后停手汇报**:`「T-1105 完工,等待指挥官二次验收 + T-1104 二次验收回补 + T-1106 候选起草」`

### 严禁项再确认(BLOCKER 红线)

- 🚫 **严禁** `git push`(等指挥官接手二次验收)
- 🚫 **严禁** 自启 T-1106 / T-1107 / 其他 Phase 11 候选议题(原 FK 第二阶段 / drop column / 物化视图 / KPI 钻取 / 前端看板)
- 🚫 **严禁** 改 `backend/app/models/` / `backend/alembic/` / `backend/app/services/` / `backend/app/schemas/user.py` / `backend/app/routers/` 除 `projects.py + users.py` 外的任何文件
- 🚫 **严禁** 改 `backend/app/routers/projects.py` 除 `create_project` 单函数外的任何 router 函数(`add_project_member` / `batch_remove_members` / `list_project_members` / `update_project` / `archive_project` / `batch_soft_delete_projects` / `batch_restore_projects` / `get_deleted_projects` / `projects_overview` 等 9 函数全部冻结)
- 🚫 **严禁** 改 `backend/app/routers/users.py` 除末尾**插入式**追加 `UserPickerItem` 类 + `GET /picker` 端点外的任何代码(`list_users` / `create_user` / `update_user` / `delete_user` / `batch_disable_users` / `batch_enable_users` / `reset_password` / `update_user_status` / `get_resource_load` 等 9 现有端点全部冻结)
- 🚫 **严禁** 改 `backend/conftest.py` / `tests/_isolation.py` / `tests/_db_url.py` / `.env*` / `README.md` / `DEPLOY.md` / `pyproject.toml` / `requirements.txt` / `uv.lock`(T-1102/1103 已闭环 + 工具链稳定)
- 🚫 **严禁** 改 T-1104 5 backend 文件(Migration `20260529_1037_*.py` / models/user.py / _department_resolver.py / department_service.py / test_phase11_dept_fk.py)
- 🚫 **严禁** 改 前端项目详情页 `frontend/src/app/project/[id]/page.tsx` 任何代码(`activeTab='members'` UI 完全冻结)
- 🚫 **严禁** 改 `frontend/src/app/dashboard/page.tsx` / `admin/*/page.tsx` / `users/page.tsx` / `components/sidebar.tsx` / `components/dashboard/` / `components/charts/` 任何文件
- 🚫 **严禁** 改 `frontend/src/app/projects/page.tsx` 现有"编辑项目 Modal / 归档确认 Modal / 卡片列表 / 批量操作栏 / FilterBar / 统计条 / 搜索框 / includeXxx 切换"等任何非"新建项目 Modal"区块
- 🚫 **严禁** `git stash` / amend / rebase / `--no-verify` 跳过 hook
- 🚫 **严禁** 测试 mock / monkeypatch / skip / print / logger.* / sleep / 直接读 os.environ
- 🚫 **严禁** 改 `📣 附录` 位置 / 删除指挥官签字痕迹

### 回滚动作(production hot rollback)

```bash
# 一键 revert(本任零 schema 改动,纯应用层)
git revert <T-1105 feat commit>
git revert <T-1105 chore commit>
# 已立项的 Project + ProjectMember 数据完整保留;ProjectCreate.members 字段移除;GET /users/picker 端点移除
```

### 二次验收前预案

- 若指挥官二次验收驳回 BLOCKER → 按 §10.2 spec 起草盲点防御惯例,Codex 单一原子 `fix(...)` commit 修复 + 保留二次验收记录
- 若指挥官接受非 BLOCKER 小减分 → 在 chore commit body 注明减分理由,T-1106 起草时统一收紧
- 若指挥官同时要求回补 T-1104 二次验收回执 → 在 chore commit 内同时更新 dev_tasks.md Task 4 行(追加指挥官二次验收段)+ Task 5 行

---

**🏁 spec 落盘完成。等待 Codex 接手执行。**
