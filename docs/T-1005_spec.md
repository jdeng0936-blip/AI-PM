# T-1005 实施契约 —— `/api/v1/admin/reports?group_by=` 对外分组端点

> **指挥官签发时间戳**: `[2026-05-27 20:25:00]`
> **持牌任务**: T-1005(Phase 10 第四份代码任务,对外分组聚合主线轮)
> **依赖前置**: T-1001(勘察) / T-1002(ProjectMember partial unique) / T-1003(Department ORM) / T-1004(`/admin/departments` 5 端点) 全部 `[x]`
> **下游任务**: T-1006(前端 Dashboard Tabs 切换器) / T-1007(测试集中补) / T-1008(文档收尾)

---

## 1. 任务背景

### 1.1 上游事实(Git 真相源)

- T-1004 已落地 commit `d8737d9 → 9b431c4`,`/api/v1/admin/departments` 5 端点上线,RBAC `admin + manager`。
- `DailyReport(BaseMixin, Base)` 含 `deleted_at: DateTime(timezone=True) nullable index`(V2.4 Stage 2 软删除信号,L82-87),与 User 不同。
- `Project(BaseMixin, Base)` 同样含 `deleted_at` + `name: String(128)` + `is_temporary: bool`。
- `User.department: String(64), nullable=False, default=""` 仍是字符串字段(FK 化延后 Phase 11+)。

### 1.2 本契约的目标

落地 Phase 10 plan §10 L737-784 设计的**对外统一分组聚合端点**:`GET /api/v1/admin/reports?group_by=department|project&project_id=&start_date=&end_date=`,把现有分散在 `dashboard.py L300-323`(按 user/temp 聚合) 与 `trends.py L77-122`(按 department 聚合) 中的内部 SQL `GROUP BY` 统一对外暴露,供 T-1006 前端 Dashboard Tabs 切换器消费(全员 / 按部门 / 按项目 三 Tab)。

### 1.3 端点清单(1 个,admin/manager 鉴权)

| 方法 | 路径 | 响应模型 | 状态码 | RBAC |
|------|------|----------|--------|------|
| GET | `/api/v1/admin/reports?group_by=...&project_id=...&start_date=...&end_date=...` | `GroupedReportsResponse` | 200 | admin + manager |

错误码:
- 422:`group_by` 非 `department`/`project` 枚举值 / `start_date`/`end_date` 格式错 / `project_id` 非 UUID
- 400:`start_date > end_date` 语义冲突
- 200:其余路径,包括空结果(`groups: []`)

### 1.4 与现有端点的并存(不替换不冲突)

| 既有端点 | 用途 | T-1005 决策 |
|---------|------|------------|
| `GET /api/v1/trends/department-stats` | 按部门聚合,固定 7 日窗口,响应 `{"departments": [...]}` | **保留不动**,前端老页面继续用 |
| `GET /api/v1/dashboard/temp-ticket-summary` | 按 user/temp 聚合,临时项目用 | **保留不动** |
| `GET /api/v1/dashboard/weekly-stats` | 按 user/周 聚合 | **保留不动** |
| `GET /api/v1/admin/reports?group_by=...`(**新**) | 统一对外分组,前端 Tabs 消费 | T-1005 新增 |

---

## 2. 任务范围

### 2.1 命中维度(必须改的 5 个文件)

1. **新建** `backend/app/schemas/admin_reports.py`(Pydantic V2 schemas:`GroupBy` Literal 枚举 + `ReportGroupRow` + `GroupedReportsResponse`)。
2. **新建** `backend/app/services/admin_reports_service.py`(2 个 async 公开函数 `group_reports_by_department` / `group_reports_by_project`,**不 raise HTTPException**,统一 ValueError 错误信号)。
3. **新建** `backend/app/routers/admin_reports.py`(`APIRouter(prefix="/api/v1/admin/reports", tags=["Admin Reports"])`,1 个 GET 端点 + 参数校验 + ValueError → HTTPException 映射)。
4. **改** `backend/app/main.py`(插入式 2 行:① import 块 `admin_reports,` 字母序在 `analytics,` 之前;② `app.include_router(admin_reports.router)` 紧邻 `app.include_router(departments.router)` 之后)。
5. **改** `docs/dev_tasks.md`(Phase 10 看板 Task 5 描述扩为 1 端点统一分组 + 参数+错误码表;状态从 `[/] In Progress by Codex` 改为 `[x]`;**不动** 📣 锚点)。

### 2.2 不动维度(严禁触碰 —— 否则立即回滚)

| 维度 | 状态 | 原因 |
|------|------|------|
| `backend/app/models/` 全部 | **冻结** | T-1005 零 ORM 改动 |
| `backend/alembic/versions/` | **冻结** | 本任务零 DB schema 改动,**禁止新增 migration** |
| `backend/app/routers/dashboard.py / trends.py / reports.py` | **冻结** | 现有端点保留不动,§1.4 已签字并存 |
| `backend/app/routers/departments.py / kpi.py / *` | **冻结** | T-1004 已上线,不复用不修改 |
| `backend/tests/` | **冻结** | 测试集中推到 T-1007 |
| `frontend/src/` | **冻结** | Dashboard Tabs 推到 T-1006 |
| `backend/scripts/seed_data.py` | **冻结** | 与本契约无关 |
| `backend/uv.lock` / `.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md` | **冻结(untracked)** | 继续保持 untracked |
| `docs/implementation-plan.md` / `docs/recap.md` | **冻结** | Phase 10 收尾段推到 T-1008 |
| Phase 7 物化视图(`mv_daily_user_stats` / `mv_weekly_dept_stats`) | **不复用** | 本端点是即时按 query 窗口聚合,不依赖 MV;若复用 MV 反而引入刷新时滞 |

---

## 3. 原子执行步骤

> **执行顺序不可乱**:3.1 → 3.2 → 3.3 → 3.4(单一 commit 提交) → 3.5(单独 commit 收口)。

### 3.1 新建 `backend/app/schemas/admin_reports.py`

#### 文件骨架

```python
"""
app/schemas/admin_reports.py — Phase 10 对外分组聚合 Pydantic V2 Schemas

服务于 GET /api/v1/admin/reports?group_by=department|project,统一前端 Tabs 切换器。

聚合指标对齐 trends.py /department-stats (L92-101) 的 4 项:
  - report_count: 该窗口内日报数(过滤 deleted_at IS NULL)
  - avg_score: AVG(ai_score),COALESCE 0
  - pass_count: COUNT() FILTER (pass_check = True)
  - pass_rate: pass_count / max(report_count, 1) * 100,保留 1 位小数

key 语义:
  - group_by=department: key = User.department: str(部门名称,空串表示未挂部门)
  - group_by=project: key = str(Project.id) UUID 字符串(便于前端 routing)
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


GroupBy = Literal["department", "project"]


class ReportGroupRow(BaseModel):
    """单个分组行。"""

    key: str = Field(..., description="分组键:部门名或 project_id 字符串")
    report_count: int = Field(..., ge=0, description="该窗口内日报数")
    avg_score: float = Field(..., ge=0, description="AI 评分均值,COALESCE 0")
    pass_count: int = Field(..., ge=0, description="质检通过日报数")
    pass_rate: float = Field(..., ge=0, le=100, description="通过率百分比 0-100,保留 1 位小数")

    model_config = ConfigDict(from_attributes=True)


class GroupedReportsResponse(BaseModel):
    """GET /api/v1/admin/reports 响应。"""

    group_by: GroupBy
    start_date: date
    end_date: date
    project_id: Optional[uuid.UUID]
    groups: list[ReportGroupRow]

    model_config = ConfigDict(from_attributes=True)
```

#### 严禁项

- **严禁** 加 `validator` / `model_validator`(参数语义校验由 router 层做)。
- **严禁** 加 `@property` / `Computed` / 反序列化方法。
- **严禁** 导入 ORM(`DailyReport / Project / User` 等)。
- **严禁** 用 `Decimal` 或自定义数值类型(全部 `int` / `float`,前端易解析)。

---

### 3.2 新建 `backend/app/services/admin_reports_service.py`

#### 文件骨架

```python
"""
app/services/admin_reports_service.py — Phase 10 对外分组聚合服务层

职责:
  - group_reports_by_department(): 按 User.department 聚合
  - group_reports_by_project(): 按 Project.id 聚合(自动 join Project,过滤已软删项目)

错误模型:
  - 不 raise HTTPException(职责留给 router 层)
  - 仅 raise ValueError + str:
    - "date_range_invalid" → 400(start_date > end_date)
  - 数据库错误不在本服务捕获(让 SQLAlchemy 异常透传到全局 handler)

约束:
  - 全异步 AsyncSession
  - TENANT_ID = "default"(对齐 kpi_service / department_service 体例)
  - 返回 Schema GroupedReportsResponse 实例(不暴露 ORM)
  - SQL 体例对齐 trends.py L77-122 的 4 项聚合 + dashboard.py L300-323 的 join 链
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.models.project import Project
from app.models.user import User
from app.schemas.admin_reports import GroupedReportsResponse, ReportGroupRow

TENANT_ID = "default"


def _validate_date_range(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise ValueError("date_range_invalid")


def _row_to_group(key: str, report_count: int, avg_score: float, pass_count: int) -> ReportGroupRow:
    pass_rate = round(pass_count / max(report_count, 1) * 100, 1)
    return ReportGroupRow(
        key=key,
        report_count=int(report_count),
        avg_score=round(float(avg_score), 1),
        pass_count=int(pass_count),
        pass_rate=pass_rate,
    )


async def group_reports_by_department(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    project_id: Optional[uuid.UUID],
) -> GroupedReportsResponse:
    _validate_date_range(start_date, end_date)

    conditions = [
        DailyReport.report_date >= start_date,
        DailyReport.report_date <= end_date,
        DailyReport.deleted_at.is_(None),
        DailyReport.tenant_id == TENANT_ID,
    ]
    if project_id is not None:
        conditions.append(DailyReport.project_id == project_id)

    stmt = (
        select(
            User.department.label("key"),
            func.count(DailyReport.id).label("report_count"),
            func.coalesce(func.avg(DailyReport.ai_score), 0).label("avg_score"),
            func.count().filter(DailyReport.pass_check.is_(True)).label("pass_count"),
        )
        .join(User, DailyReport.user_id == User.id)
        .where(and_(*conditions))
        .group_by(User.department)
        .order_by(func.coalesce(func.avg(DailyReport.ai_score), 0).desc())
    )
    rows = (await db.execute(stmt)).all()
    groups = [
        _row_to_group(r.key or "", r.report_count, r.avg_score, r.pass_count)
        for r in rows
    ]

    return GroupedReportsResponse(
        group_by="department",
        start_date=start_date,
        end_date=end_date,
        project_id=project_id,
        groups=groups,
    )


async def group_reports_by_project(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    project_id: Optional[uuid.UUID],
) -> GroupedReportsResponse:
    _validate_date_range(start_date, end_date)

    conditions = [
        DailyReport.report_date >= start_date,
        DailyReport.report_date <= end_date,
        DailyReport.deleted_at.is_(None),
        DailyReport.tenant_id == TENANT_ID,
        Project.deleted_at.is_(None),
    ]
    if project_id is not None:
        conditions.append(Project.id == project_id)

    stmt = (
        select(
            Project.id.label("key"),
            func.count(DailyReport.id).label("report_count"),
            func.coalesce(func.avg(DailyReport.ai_score), 0).label("avg_score"),
            func.count().filter(DailyReport.pass_check.is_(True)).label("pass_count"),
        )
        .join(Project, DailyReport.project_id == Project.id)
        .where(and_(*conditions))
        .group_by(Project.id)
        .order_by(func.coalesce(func.avg(DailyReport.ai_score), 0).desc())
    )
    rows = (await db.execute(stmt)).all()
    groups = [
        _row_to_group(str(r.key), r.report_count, r.avg_score, r.pass_count)
        for r in rows
    ]

    return GroupedReportsResponse(
        group_by="project",
        start_date=start_date,
        end_date=end_date,
        project_id=project_id,
        groups=groups,
    )
```

#### 关键决策签字

- **过滤口径**:
  - `DailyReport.deleted_at.is_(None)` —— DailyReport 软删除信号(模型 L82-87,V2.4 Stage 2)
  - `Project.deleted_at.is_(None)` —— Project 软删除信号(仅 `group_by=project` 时叠加,department 路径不强制 project 是否软删,因为 department 聚合不依赖 project 维度)
  - `tenant_id == TENANT_ID` —— 多租户隔离
  - **不**过滤 `User.is_active`(User 状态不影响其历史日报的聚合权重)
- **未挂部门用户**:`User.department == ""` 会作为 `key=""` 单独成组(由前端决定如何显示"未分配部门");**不**做过滤剔除。
- **未挂项目日报**:`group_by=project` 时,`DailyReport.project_id IS NULL` 的日报会被 `INNER JOIN Project` 自动剔除(plan §10 设计如此)。
- **聚合排序**:统一按 `avg_score DESC`(对齐 trends.py L100)。
- **AVG 类型**:`func.avg(DailyReport.ai_score)` 返回 `Decimal`,在 `_row_to_group` 内 `round(float(...), 1)` 转 `float`。
- **`func.count().filter(...)`**:对齐 trends.py L94 现有体例(SQLAlchemy 1.4+ 标准 FILTER 子句)。

#### 严禁项

- **严禁** 在 service 层 raise `HTTPException`。
- **严禁** 在 service 层做 `print` / `logger.info`。
- **严禁** 引入 `app.routers.*`。
- **严禁** 复用 `mv_daily_user_stats` / `mv_weekly_dept_stats` 物化视图(本端点是即时按 query 窗口聚合,MV 反而引入刷新时滞)。
- **严禁** 加分页 / `limit` / `offset`(目前部门数 7 + 项目数 ≤ 数十,无需分页;扩展留 Phase 11+)。
- **严禁** 在 service 内捕获 SQLAlchemy 异常(让框架统一处理)。
- **严禁** 给 `_row_to_group` 加除四项之外的额外字段。

---

### 3.3 新建 `backend/app/routers/admin_reports.py`

#### 文件骨架

```python
"""
app/routers/admin_reports.py — Phase 10 对外分组聚合 REST API

单端点:
  - GET /api/v1/admin/reports?group_by=department|project&project_id=&start_date=&end_date=

默认窗口:end_date 缺省 today();start_date 缺省 today() - 30 天。

错误码映射(service raise ValueError(str)):
  - "date_range_invalid" → 400 "start_date 不能晚于 end_date"
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.user import User, UserRole
from app.schemas.admin_reports import GroupBy, GroupedReportsResponse
from app.services.admin_reports_service import (
    group_reports_by_department,
    group_reports_by_project,
)

router = APIRouter(prefix="/api/v1/admin/reports", tags=["Admin Reports"])
_mgr_or_admin = require_role(UserRole.admin, UserRole.manager)


def _map_value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "date_range_invalid":
        return HTTPException(status_code=400, detail="start_date 不能晚于 end_date")
    return HTTPException(status_code=500, detail="未知错误")


@router.get("/", response_model=GroupedReportsResponse)
async def grouped_reports(
    group_by: GroupBy = Query(..., description="department 或 project"),
    project_id: Optional[uuid.UUID] = Query(None, description="可选项目过滤"),
    start_date: Optional[date] = Query(None, description="窗口起始日(含),默认 today-30"),
    end_date: Optional[date] = Query(None, description="窗口结束日(含),默认 today"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> GroupedReportsResponse:
    end_d = end_date or date.today()
    start_d = start_date or (end_d - timedelta(days=30))

    try:
        if group_by == "department":
            return await group_reports_by_department(db, start_d, end_d, project_id)
        return await group_reports_by_project(db, start_d, end_d, project_id)
    except ValueError as e:
        raise _map_value_error(e) from None
```

#### 关键决策签字

- **end_date 默认 today()**;**start_date 默认 today() - 30 天**(对齐 dashboard.py L296-297 体例)。
- **Pydantic Literal 自动 422**:`group_by` 非法值由 FastAPI/Pydantic 直接转 422,**无需** router 层判断。
- **`Optional[uuid.UUID]` 自动 422**:`project_id` 格式错也由 FastAPI 转 422。
- **redirect_slashes 默认 True**:`GET /api/v1/admin/reports` 与 `/admin/reports/` 都可达,无需特殊配置。
- **错误信号** 仅 1 个(`date_range_invalid`),其余路径返回 200 + 空 groups。

#### 严禁项

- **严禁** router 层做 ORM 查询(全走 service)。
- **严禁** RBAC 加 `employee` 或去掉 `manager`。
- **严禁** 自行扩端点(只 1 个 GET)。
- **严禁** 自行加 POST / PATCH / DELETE / OPTIONS。
- **严禁** print / logger.info。
- **严禁** 改 `_map_value_error` 兜底之外的状态码语义。

---

### 3.4 改 `backend/app/main.py`(**插入式 2 行**)

#### Diff 预期

```diff
 from app.routers import (
+    admin_reports,
     analytics,
     auth,
     dashboard,
     departments,
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

以及在 `app.include_router(departments.router)` 之后**紧邻插入**:

```diff
 app.include_router(kpi.router)
 app.include_router(departments.router)
+app.include_router(admin_reports.router)
 # ── 基础功能 ─────────────────────────────────────
 app.include_router(wechat.router)
```

#### 严禁项

- **严禁** 重排 import 块的其他元素(只允许在 `analytics,` 之前插入 `admin_reports,`)。
- **严禁** 改 include_router 其他调用顺序。
- **严禁** 改 Sentry 初始化 / lifespan / 中间件挂载。

---

### 3.5 改 `docs/dev_tasks.md`(**两处编辑**)

#### 编辑 A: Task 5 描述扩展 + 状态打钩

- 把行 136-138 的 `[ ] **Task 5 (T-1005): ...**` 改为 `[x]`,描述扩展为 1 端点统一分组 + 参数+错误码表 + 与现有 `dashboard.py L300-323 / trends.py L77-122` 端点的并存关系。

#### 编辑 B: 📣 锚点保留不动

- **不动** 📣 恢复执行指令锚点(指挥官会在 `chore(spec): T-1005 契约` commit 中统一替换;Worker 在 chore(progress) 收口时**不要碰**)。

#### 严禁项

- **严禁** 改 Phase 9 章节或其他 Task 的描述。
- **严禁** 改 Phase 10 Task 6/7/8 的描述(它们由后续契约定稿)。
- **严禁** 改 📣 锚点(指挥官专属位置)。

---

### 3.6 起始状态(由指挥官打锁,Worker 不再处理)

- 指挥官在 `chore(spec): T-1005 契约` commit 中已经一并完成:
  - Task 5 状态从 `[ ]` 改为 `[/] In Progress by Codex(指挥官 chore(spec) commit 已加锁,2026-05-27 20:25)`
  - 📣 锚点替换为 T-1005 发牌内容(持牌任务 = T-1005,head = `b58bb129c24b`)
- Worker 接力时,**不要重复 `chore(lock)`**,直接进入 §3.1 → §3.5 实施阶段。

---

## 4. 防越界红线表

| # | 红线 | 触发后果 |
|---|------|----------|
| 01 | 改 `backend/app/models/` 任何文件 | 立即回滚 |
| 02 | 新增任何 alembic migration | 立即回滚 |
| 03 | 改 `routers/dashboard.py / trends.py / reports.py` 任意一行 | 立即回滚 |
| 04 | 改 `routers/departments.py / kpi.py` | 立即回滚 |
| 05 | 改 `backend/scripts/seed_data.py` | 立即回滚 |
| 06 | 在 `backend/tests/` 新增/修改 测试文件 | 立即回滚(T-1007) |
| 07 | 改 `frontend/src/` 任何文件 | 立即回滚(T-1006) |
| 08 | service 层 raise `HTTPException` | 立即回滚 |
| 09 | router 层做 ORM 查询(应全走 service) | 立即回滚 |
| 10 | 给 service / router 加 `print` / `logger.info` 副作用 | 立即回滚 |
| 11 | 自行扩端点(POST/PATCH/DELETE/OPTIONS)或减端点(必须严格 1 个 GET) | 立即回滚 |
| 12 | RBAC 范围加 `employee` 或去 `manager` | 立即回滚 |
| 13 | 复用 `mv_daily_user_stats` / `mv_weekly_dept_stats` 物化视图 | 立即回滚 |
| 14 | 在 service 加分页 / `limit` / `offset` 参数 | 立即回滚 |
| 15 | 重排 `main.py` import 块或 `include_router` 顺序 | 立即回滚 |
| 16 | `git add backend/uv.lock` 或其他 4 个既定 untracked | 立即回滚 |
| 17 | 自动 `git push` | 立即停手 |
| 18 | 自行启动 T-1006 / T-1007 / T-1008 | 立即停手 |
| 19 | 改 📣 锚点("当前持牌任务: T-1005" 必须保留) | 立即回滚 |
| 20 | 给 `_row_to_group` 加除 4 项之外的额外字段(`min_score` / `max_score` 等) | 立即回滚 |
| 21 | 改 `_validate_date_range` 的 `>` 比较为 `>=`(允许同一天聚合,语义保留) | 立即回滚 |
| 22 | 在过滤条件加 `User.is_active` 限制(User 状态不影响历史日报聚合,加了反而漏数据) | 立即回滚 |
| 23 | 在 `group_by=project` 路径用 `outerjoin Project`(必须 `inner join`,过滤未挂项目日报) | 立即回滚 |

---

## 5. 数据风险评估

### 5.1 风险点清单

| # | 风险 | 概率 | 影响 | 应对 |
|---|------|------|------|------|
| 1 | `User.department == ""` 用户被聚合为 `key=""` 空字符串组 | 中 | 低 | **接受**:前端 T-1006 决定如何显示"未分配部门",service 层不剔除 |
| 2 | `Project.is_temporary=True` 的临时项目在 `group_by=project` 路径出现 | 高 | 中 | **接受**:临时项目也是合法项目,纳入聚合;若 T-1006 需要剔除,前端自行 filter |
| 3 | 大窗口(`end_date - start_date > 365 天`)聚合慢 | 极低 | 低 | **接受**:目前数据规模小;扩展留 Phase 11+ |
| 4 | `DailyReport.deleted_at` 软删日报被错误纳入 | 极低 | 中 | **已过滤**:`DailyReport.deleted_at.is_(None)` 强制条件 |
| 5 | `group_by=department + project_id=X` 同时使用 | 中 | 低 | **接受**:语义为"仅该项目的日报按部门分组",前端可能用于"查某项目各部门贡献度";不阻断 |
| 6 | `group_by=project + project_id=X` 同时使用 | 中 | 低 | **接受**:返回单 group 或空 group,前端可用于钻取场景;不阻断 |
| 7 | `avg_score` 在无数据时为 0 而非 `null` | 中 | 极低 | **接受**:COALESCE 0 对齐 trends.py L93 体例,前端区分"0 分" vs "无数据" 看 `report_count` |

### 5.2 与 Phase 7 物化视图的关系签字

- T-1005 **不消费** `mv_daily_user_stats` / `mv_weekly_dept_stats`:
  - 原因 1:MV 刷新有时滞,即时 query 更准
  - 原因 2:MV 的聚合维度固定(day / week × user / dept),不支持任意 `start_date / end_date` 窗口
  - 原因 3:本端点是 admin 工具,QPS 极低,直接走 OLTP 表完全可承受
- Phase 11+ 若需性能优化,可考虑加 `mv_admin_reports_grouped` 单独 MV(本契约不预留)。

---

## 6. 测试基线(Worker 提交前必跑,全绿才能 commit)

```bash
cd backend
# ① 语法 + 类型
.venv/bin/ruff check .
.venv/bin/mypy app/schemas/admin_reports.py app/services/admin_reports_service.py app/routers/admin_reports.py app/main.py

# ② 全量回归(零回归,新增端点不写测试,基线应保持 160 passed + 2 skipped)
.venv/bin/pytest tests/ -q

# ③ alembic check(零 migration 改动)
.venv/bin/alembic upgrade head && .venv/bin/alembic check

# ④ 前端无破坏验证
cd ../frontend
npm run lint
npm run typecheck
```

#### 验收条件

- ruff:`All checks passed!`
- mypy:目标 4 文件 0 error;**已知存量** error(`analytics.py:107-109` / `scheduled_tasks.py:609`)**不修复**,T-1005 范围外。
- pytest:`160 passed, 2 skipped`(与 T-1004 完工基线一致,**零回归**)。
- alembic check:`No new upgrade operations detected.`(head 仍 `b58bb129c24b`)。
- npm run lint / typecheck:全绿。

#### 测试不要新增

- 本契约**不写** `test_phase10_admin_reports_*.py` 测试。端点行为(200 路径 / 422 / 400 / RBAC 403)统一推到 **T-1007** 集中编写。
- 若 Codex 觉得"必须自查",仅允许手动 `curl` / `httpie` 临时调用,不写入仓库。

---

## 7. 完工提交序列(原子 2 commit,顺序不可乱)

#### Commit 1: feat(admin_reports) — 4 个文件改动一次性进入

```
feat(admin_reports): add /api/v1/admin/reports?group_by= 对外分组聚合端点

Phase 10 / T-1005 — 落地 plan §10 L737-784 设计的对外统一分组端点,供 T-1006 前端 Dashboard Tabs 切换器消费。

文件改动:
- 新建 backend/app/schemas/admin_reports.py (GroupBy + ReportGroupRow + GroupedReportsResponse 3 个 Pydantic V2 schemas)
- 新建 backend/app/services/admin_reports_service.py (2 个 async 公开函数 + 2 个私有助手,ValueError 错误信号)
- 新建 backend/app/routers/admin_reports.py (1 个 GET 端点 + RBAC + ValueError → HTTPException 映射)
- 改 backend/app/main.py (import + include_router 插入式 2 行)

端点(admin + manager RBAC):
- GET /api/v1/admin/reports?group_by=department|project&project_id=&start_date=&end_date= → GroupedReportsResponse

聚合指标对齐 trends.py /department-stats(4 项):report_count / avg_score / pass_count / pass_rate

不动:
- ORM / migration / 现有 dashboard.py / trends.py / reports.py / departments.py
- 测试 / 前端 / seed_data.py
- Phase 7 物化视图(本端点即时按 query 窗口聚合,不复用 MV)

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

文件清单:
1. `backend/app/schemas/admin_reports.py`(新建)
2. `backend/app/services/admin_reports_service.py`(新建)
3. `backend/app/routers/admin_reports.py`(新建)
4. `backend/app/main.py`(改 import + include_router,只 +2 行)

#### Commit 2: chore(progress) — 仅更新 dev_tasks.md

```
chore(progress): close T-1005 — /api/v1/admin/reports 对外分组聚合端点上线

dev_tasks.md Phase 10 章节 Task 5 状态改为 [x],并扩描述至 1 端点统一分组(group_by=department|project)+ 4 项聚合指标 + 与现有 dashboard.py L300-323 / trends.py L77-122 并存关系签字。📣 恢复执行指令锚点保留 T-1005,留给指挥官起草 T-1006 时统一替换。

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

文件清单:
1. `docs/dev_tasks.md`(改 Task 5 状态 + 描述,**不动** 📣 锚点)

#### 严禁项

- **严禁** 把 Commit 1 与 Commit 2 合并。
- **严禁** 在 Commit 1 中夹带 `docs/dev_tasks.md`。
- **严禁** 在 Commit 2 中夹带任何 src 文件。
- **严禁** 在 commit message 中省略 `Worker timestamp: [...]` 行。

---

## 8. 验收清单(指挥官二次验收时按此核对)

- [ ] 1. `git log --oneline -3` 显示链路 `<chore> → <feat> → 76fd5b4(T-1004 验收)/c2a75f6...`,顺序正确
- [ ] 2. Commit 1 (feat) 改动恰好 4 个文件(`schemas/admin_reports.py` + `services/admin_reports_service.py` + `routers/admin_reports.py` + `main.py`),零夹带
- [ ] 3. Commit 2 (chore) 仅改 `docs/dev_tasks.md`,Task 5 = `[x]`,描述含 1 端点 + 4 项聚合指标
- [ ] 4. `backend/app/main.py` import 块仅在 `analytics,` 之前插入 `admin_reports,`(字母序),其他元素零移动
- [ ] 5. `app.include_router(admin_reports.router)` 紧邻在 `app.include_router(departments.router)` 之后
- [ ] 6. Schema 文件含 3 个公开类型(`GroupBy` Literal + `ReportGroupRow` + `GroupedReportsResponse`),字段约束对齐 §3.1
- [ ] 7. Service 文件含 2 个公开 async 函数 + 2 个 `_*` 私有助手;**不**含 `HTTPException` 引用
- [ ] 8. Router 文件含 1 个 GET 端点;`_map_value_error` 仅映射 1 个 code(`date_range_invalid`) + 兜底 500
- [ ] 9. RBAC `admin + manager`,**未**降级到 `employee`
- [ ] 10. 过滤口径对齐:`DailyReport.deleted_at.is_(None)` + `DailyReport.tenant_id == TENANT_ID` + `Project.deleted_at.is_(None)`(仅 project 路径) + **不** 过滤 `User.is_active`
- [ ] 11. 全部测试基线绿(ruff / mypy 4 文件 / pytest 零回归 / alembic check / 前端 lint+typecheck)
- [ ] 12. `git status` 干净(仅 4 个既定 untracked 保留)
- [ ] 13. `git diff origin/main -- backend/alembic/` 为空(本任务零 migration)
- [ ] 14. `git diff origin/main -- backend/tests/ frontend/src/` 为空
- [ ] 15. `git diff origin/main -- backend/app/models/ backend/app/routers/dashboard.py backend/app/routers/trends.py backend/app/routers/reports.py backend/app/routers/departments.py` 为空(本任务零既有文件修改)
- [ ] 16. 两个 commit 的 message 都含 `Worker timestamp: [...]` 行
- [ ] 17. 📣 锚点中"当前持牌任务: T-1005"保留(留给指挥官在 T-1006 spec 中统一替换)

---

## 9. 与其他任务的关系

- **上游**: T-1003(Department ORM)+ T-1004(`/admin/departments` 5 端点)已落地,本契约**消费** `Project / DailyReport / User` 现有 ORM,**禁止**修改任何 ORM。
- **平行**: 无。Codex 不会同时被分派 T-1006 / T-1007 / T-1008。
- **下游**:
  - **T-1006** 前端 Dashboard Tabs 切换器(全员/按部门/按项目)+ admin/departments 管理页 —— 消费本契约新增的 `/api/v1/admin/reports?group_by=` 端点,以及 T-1004 的 `/api/v1/admin/departments` 5 端点。
  - **T-1007** 后端测试集中补 `test_phase10_dept_group.py` —— 覆盖 T-1003/04/05 三个数据/服务/路由层 task 的端到端行为(包括本契约的 GET 端点 200/422/400/RBAC 路径)。
- **跳过**: 不消费、不影响:Phase 9 KPI / Phase 7 物化视图(已签字不复用)/ Phase 8 Export / Phase 6 OKR / Phase 5 Sprint / Phase 4 Gate / Phase 3 Capacity / Phase 2 Auth。

---

## 📣 附录:给 Worker 的物理交接单(指挥官在 chore(spec) commit 同步落盘)

> **时间戳**: `[2026-05-27 20:25:00]`
> **当前持牌任务**: T-1005
> **执行入口**: 阅读本契约 §3.1 → §3.5,严格按原子顺序执行,**不要重复 `chore(lock)`**(指挥官在 chore(spec) commit 已加锁)。

### 核心动作(严格按 §3 顺序)

1. **新建** `backend/app/schemas/admin_reports.py` —— `GroupBy = Literal["department", "project"]` + `ReportGroupRow` + `GroupedReportsResponse`,完全按 §3.1 骨架,字段约束不可扩缩。
2. **新建** `backend/app/services/admin_reports_service.py` —— `_validate_date_range`(`start_date > end_date` → `raise ValueError("date_range_invalid")`)+ `_row_to_group`(4 项指标 + `pass_rate = round(pass_count / max(report_count, 1) * 100, 1)`)+ `group_reports_by_department`(`join User` + `group_by(User.department)`)+ `group_reports_by_project`(`join Project` + `group_by(Project.id)`)。**强制条件**:`DailyReport.deleted_at.is_(None) + DailyReport.tenant_id == TENANT_ID`;`group_by=project` 额外叠加 `Project.deleted_at.is_(None)`;**不**过滤 `User.is_active`。
3. **新建** `backend/app/routers/admin_reports.py` —— `APIRouter(prefix="/api/v1/admin/reports", tags=["Admin Reports"])` + `_mgr_or_admin = require_role(UserRole.admin, UserRole.manager)` + `_map_value_error(exc)`(`date_range_invalid → 400 "start_date 不能晚于 end_date"`,兜底 500)。1 个 GET 端点,`group_by: GroupBy = Query(...)` 必传,`project_id / start_date / end_date` Optional。`end_date or date.today()`;`start_date or (end_d - timedelta(days=30))`。try/except ValueError + `raise _map_value_error(e) from None`。
4. **改** `backend/app/main.py` —— 插入式 2 行:① import 块 `admin_reports,` 字母序在 `analytics,` 之前;② `app.include_router(admin_reports.router)` 紧邻 `app.include_router(departments.router)` 之后。**严禁** 重排其他元素。
5. **改** `docs/dev_tasks.md` —— Task 5 状态 `[/] → [x]`,描述扩为 1 端点 + 4 项聚合指标 + 现有端点并存关系。**不动** 📣 锚点。

### 严禁项(违反则立即回滚)

- **严禁** 改 `backend/app/models/` 任何文件。
- **严禁** 新增任何 alembic migration。
- **严禁** 改 `routers/dashboard.py / trends.py / reports.py / departments.py / kpi.py` 任意一行。
- **严禁** 写测试(留给 T-1007 集中补)。
- **严禁** 改 `frontend/src/` 任何文件(留给 T-1006)。
- **严禁** service 层 raise `HTTPException`。
- **严禁** router 层做 ORM 查询。
- **严禁** 复用 Phase 7 物化视图 `mv_daily_user_stats` / `mv_weekly_dept_stats`。
- **严禁** 加分页 / `limit` / `offset` 参数。
- **严禁** 自行扩端点(只允许 1 个 GET)或减端点。
- **严禁** RBAC 范围加 `employee` 或去掉 `manager`。
- **严禁** 在过滤条件加 `User.is_active`(User 状态不影响历史日报聚合)。
- **严禁** 在 `group_by=project` 路径用 `outerjoin Project`(必须 `inner join`)。
- **严禁** 改 `_validate_date_range` 的 `>` 为 `>=`(允许同日聚合,语义保留)。
- **严禁** 给 `_row_to_group` 加除 4 项之外的额外字段。
- **严禁** 重排 `main.py` import / `include_router` 顺序。
- **严禁** 自动 `git push`。
- **严禁** 自行启动 T-1006 / T-1007 / T-1008。
- **严禁** 改 📣 锚点("当前持牌任务: T-1005" 必须保留)。

### 端点 + 错误码 + RBAC 锁定表

| 方法 | 路径 | 响应模型 | 状态码 | RBAC |
|------|------|----------|--------|------|
| GET | `/api/v1/admin/reports/` | `GroupedReportsResponse` | 200 | admin + manager |

| 错误信号 | service ValueError 字面量 | router HTTPException | detail |
|---------|--------------------------|----------------------|--------|
| 日期范围反 | `"date_range_invalid"` | 400 | `"start_date 不能晚于 end_date"` |
| group_by 非法 | (由 Pydantic Literal 自动) | 422 | (FastAPI 默认 detail) |
| project_id 非 UUID | (由 Pydantic 自动) | 422 | (FastAPI 默认 detail) |
| RBAC 不足 | (由 require_role 自动) | 403 | (RBAC 中间件默认 detail) |

### 聚合指标 4 项锁定(对齐 trends.py L92-101)

| 指标 | SQL | 类型 |
|------|-----|------|
| `report_count` | `func.count(DailyReport.id)` | int |
| `avg_score` | `func.coalesce(func.avg(DailyReport.ai_score), 0)` round 1 位 | float |
| `pass_count` | `func.count().filter(DailyReport.pass_check.is_(True))` | int |
| `pass_rate` | `round(pass_count / max(report_count, 1) * 100, 1)` | float 0-100 |

### 过滤条件锁定

- 强制(两条路径都用):
  - `DailyReport.report_date >= start_date AND <= end_date`
  - `DailyReport.deleted_at.is_(None)`
  - `DailyReport.tenant_id == TENANT_ID`("default")
- `group_by=department` 额外:
  - 可选 `DailyReport.project_id == project_id`(传 project_id 时叠加)
- `group_by=project` 额外:
  - `Project.deleted_at.is_(None)`(必加)
  - 可选 `Project.id == project_id`(传 project_id 时叠加)
- **不**过滤 `User.is_active` —— User 状态不影响其历史日报权重。

### 测试基线(全绿才提交)

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/mypy app/schemas/admin_reports.py app/services/admin_reports_service.py app/routers/admin_reports.py app/main.py
.venv/bin/pytest tests/ -q                                    # 必须零回归(160 passed + 2 skipped,与 T-1004 完工一致)
.venv/bin/alembic upgrade head && .venv/bin/alembic check     # head 仍 b58bb129c24b
cd ../frontend && npm run lint && npm run typecheck
```

### 完工提交序列(原子 2 commit,顺序不可乱)

1. `feat(admin_reports): add /api/v1/admin/reports?group_by= 对外分组聚合端点` —— 4 文件:schemas + service + router + main.py(插入式 2 行)
2. `chore(progress): close T-1005 — /api/v1/admin/reports 对外分组聚合端点上线` —— 仅 `docs/dev_tasks.md`,Task 5 → `[x]`

### 时间戳纪律

所有 commit message 末尾、终端汇报、写入 `dev_tasks.md` 的段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。

### 完工后

立即停手汇报「T-1005 完工,等待指挥官二次验收 + 起草 T-1006 (前端 Dashboard Tabs 切换器) 或 T-1007 (测试集中补) 实施契约」。**不要** 自行启动任何下游 task。

---

> **指挥官签字落盘**: `[2026-05-27 20:25:00]`
> **关联 commit**: `chore(spec): T-1005 契约` —— `dev_tasks.md` Task 5 加锁 + 📣 锚点替换 由同 commit 一并完成。
