# T-1007 实施契约 — Phase 10 后端测试集中补

> **指挥官签发**：`[2026-05-27 20:55:00]`
> **签发 commit**：随本 `chore(spec): T-1007 契约` 一并落盘
> **承接者**：Codex Worker
> **前序依赖**：T-1003 / T-1004 / T-1005（已全部 `[x]`，HEAD = `7879399` 即 T-1005 验收 commit）

---

## 1. 任务背景

### 1.1 上下文
Phase 10 业务主线后端三轮 (T-1003 Department ORM + 7 seed / T-1004 `/admin/departments` 5 端点 + members 反查 / T-1005 `/admin/reports?group_by=` 1 端点 + 4 聚合指标) 已全部落地并验收通过,但**零专属测试覆盖**。本契约执行 dev_tasks.md Task 7 签字的「测试集中补」轮：在 `backend/tests/` 新建 1 个测试文件 `test_phase10_dept_group.py`,以三层覆盖 (Model / Service / Router) 验证 T-1003/04/05 的端到端行为,确保 Phase 11 启动前所有后端契约都有自动化护栏。

### 1.2 当前 Git 真相源
- **HEAD**：`7879399 docs(tasks): T-1005 验收通过`
- **本地领先 origin/main**：20 commit (本契约 `chore(spec)` 落盘后 21)
- **alembic head**：`b58bb129c24b`（T-1007 零 schema 改动）
- **既定 untracked 4 文件**：`.cursorrules / CLAUDE.md / CONVENTIONS.md / backend/uv.lock`(永不 git add)

### 1.3 目标产出
新建 1 个测试文件,**~19 个 test case**,覆盖：
- **Model 层**:`ProjectMember` partial UNIQUE 行为 + `Department.name` UNIQUE 行为
- **Service 层**:`department_service.get_department_with_members` 反查 + `admin_reports_service` 双路径聚合 + `_validate_date_range`
- **Router 层**:T-1004 `/admin/departments` 5 端点 RBAC + 错误码 + T-1005 `/admin/reports` RBAC + 错误码 + Literal 参数校验

跑通后 `pytest tests/` 总数从 `160 passed, 2 skipped` 增至 **`~179 passed, 2 skipped` 零回归**。

### 1.4 选 T-1007 而非 T-1006 的理由（指挥官签字）
- 测试先行能稳住三个后端轮次的契约,T-1006 前端开发期回归压力小
- T-1006 涉及 Tabs 样式 / Modal 字段细节 / 路由导航等多个前端 UI 决策点,需 PM Ask 后才能起草高质量契约
- T-1007 是纯契约性工作 (case 命名 / fixture 复用 / RBAC 体例),指挥官可一次性签字到位

---

## 2. 任务范围

### 2.1 命中文件清单（恰好 1 + 1 = 2 文件）
| # | 文件 | 操作 | 行数预估 |
|---|------|------|---------|
| 1 | `backend/tests/test_phase10_dept_group.py` | 新建 | ~380 行 |
| 2 | `docs/dev_tasks.md` | 改（Task 7 → `[x]`） | +1 -1 |

### 2.2 严禁触碰的 11 维度（零夹带边界）
- **ORM Model**：`backend/app/models/` 全部文件保留不动
- **Migration**：`backend/alembic/` 零新文件,head 保持 `b58bb129c24b`
- **Service / Router**：T-1003/04/05 落地的 `department_service.py / admin_reports_service.py / departments.py / admin_reports.py` 零改动
- **既有路由**：`dashboard.py / trends.py / reports.py / kpi.py / analytics.py / export.py` 零改动
- **main.py**：零行改动
- **seed_data.py**：保留不动
- **既有测试文件**：`test_kpi_phase9.py / test_export_phase8.py / test_analytics.py / test_e2e_ipd.py / test_okr.py` 等 19 个文件零改动
- **conftest.py**：保留不动,只**消费**其 `db_session / client` fixture
- **frontend/**：零改动（前端测试留给 T-1006）
- **docs/**：除 dev_tasks.md Task 7 状态翻转外,其他文档零改动
- **Phase 7 物化视图**：本测试**不**触发 `mv_daily_user_stats / mv_weekly_dept_stats` 刷新,**不**写 `CREATE MATERIALIZED VIEW` 语句

---

## 3. 原子执行步骤

### 3.1 新建 `backend/tests/test_phase10_dept_group.py` 骨架契约

**头部 imports（必含,不可缺）**：
```python
"""
tests/test_phase10_dept_group.py — Phase 10 部门 + 项目分组聚合后端测试

覆盖范围:
  - Model 层: ProjectMember partial UNIQUE (project_id, user_id) WHERE left_at IS NULL
             + Department.name UNIQUE
  - Service 层: department_service.get_department_with_members (反查 + 空)
              + admin_reports_service.group_reports_by_department / by_project
              + _validate_date_range
  - Router 层: /api/v1/admin/departments 5 端点 (200 / 403 / 400 / 409 / 404)
             + /api/v1/admin/reports 1 端点 (200 / 403 / 422 / 400 / project_id 过滤)
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.rbac import create_access_token
from app.models.daily_report import DailyReport
from app.models.department import Department
from app.models.project import Project
from app.models.project_member import MemberTrack, ProjectMember
from app.models.user import User, UserRole
from app.services.admin_reports_service import (
    _validate_date_range,
    group_reports_by_department,
    group_reports_by_project,
)
from app.services.department_service import get_department_with_members
```

**私有 helpers（共 6 个,统一前缀 `_`）**：
```python
TENANT_ID = "default"


async def _cleanup_phase10_test_data(db: AsyncSession) -> None:
    """测试前清理本测试创建的 wechat_userid='phase10_*' 用户及连锁 ORM 行。"""
    await db.execute(delete(DailyReport).where(DailyReport.tenant_id == TENANT_ID))
    await db.execute(delete(ProjectMember))
    await db.execute(delete(Project).where(Project.tenant_id == TENANT_ID))
    await db.execute(delete(Department).where(Department.tenant_id == TENANT_ID))
    await db.execute(delete(User).where(User.wechat_userid.like("phase10_%")))
    await db.commit()


async def _make_user(
    db: AsyncSession,
    role: UserRole,
    name: str = "Phase10 用户",
    department: str = "技术部",
    is_active: bool = True,
) -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=f"phase10_{uuid.uuid4().hex[:12]}",
        name=name,
        department=department,
        job_title="工程师",
        role=role,
        is_active=is_active,
        tenant_id=TENANT_ID,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


async def _make_department(db: AsyncSession, name: str, manager_id: uuid.UUID | None = None) -> Department:
    dept = Department(id=uuid.uuid4(), name=name, manager_id=manager_id, tenant_id=TENANT_ID)
    db.add(dept)
    await db.commit()
    await db.refresh(dept)
    return dept


async def _make_project(db: AsyncSession, name: str = "Phase10 项目") -> Project:
    project = Project(id=uuid.uuid4(), name=name, tenant_id=TENANT_ID)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def _make_daily_report(
    db: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None,
    report_date: date,
    ai_score: float,
    pass_check: bool,
) -> DailyReport:
    report = DailyReport(
        id=uuid.uuid4(),
        user_id=user_id,
        project_id=project_id,
        report_date=report_date,
        ai_score=ai_score,
        pass_check=pass_check,
        tenant_id=TENANT_ID,
        content="phase10 test content",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report
```

### 3.2 Model 层测试（3 cases）

| Case 名 | 验证点 | 关键断言 |
|---------|-------|---------|
| `test_project_member_unique_active_blocks_duplicate` | 同 `(project_id, user_id)` 都 `left_at IS NULL` 第二次插入抛 IntegrityError | `pytest.raises(IntegrityError)` |
| `test_project_member_unique_active_allows_after_left` | 第一条 `left_at=<some date>` 第二条 `left_at IS NULL` 允许并存 | 两条都成功插入,`select count` = 2 |
| `test_department_unique_name_blocks_duplicate` | 两个同名 Department 第二次插入抛 IntegrityError | `pytest.raises(IntegrityError)` |

骨架（典型一例）：
```python
@pytest.mark.asyncio
async def test_project_member_unique_active_blocks_duplicate(db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    user = await _make_user(db_session, UserRole.employee, name="PM-User")
    project = await _make_project(db_session)
    db_session.add(ProjectMember(
        project_id=project.id, user_id=user.id, track=MemberTrack.software, tenant_id=TENANT_ID,
    ))
    await db_session.commit()
    db_session.add(ProjectMember(
        project_id=project.id, user_id=user.id, track=MemberTrack.hardware, tenant_id=TENANT_ID,
    ))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
```

### 3.3 Service 层测试（5 cases）

| Case 名 | 验证点 |
|---------|-------|
| `test_dept_service_get_with_members_returns_active_users` | 创建 dept "技术部" + 3 活跃用户(department="技术部") + 1 inactive 用户(is_active=False) → service 反查返回 3 个 active |
| `test_dept_service_get_with_members_empty_returns_empty_list` | 创建 dept 但无用户挂载 → `members == []` |
| `test_admin_reports_group_by_department_aggregates_correctly` | 创建 2 部门 × 各 2 用户 × 各 3 报告 → 验证 `report_count / avg_score / pass_count / pass_rate` 数值正确,window 内 |
| `test_admin_reports_group_by_project_inner_join_excludes_null_project` | 创建 1 报告无 project_id + 1 报告有 project_id → group_by=project 仅返回 1 行(剔除 NULL) |
| `test_validate_date_range_raises_when_start_after_end` | `_validate_date_range(today, today - timedelta(1))` → `ValueError("date_range_invalid")` |

骨架（聚合典型一例）：
```python
@pytest.mark.asyncio
async def test_admin_reports_group_by_department_aggregates_correctly(db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    u_tech = await _make_user(db_session, UserRole.employee, department="技术部")
    u_sales = await _make_user(db_session, UserRole.employee, department="销售部")
    today = date.today()
    await _make_daily_report(db_session, u_tech.id, None, today, ai_score=80.0, pass_check=True)
    await _make_daily_report(db_session, u_tech.id, None, today, ai_score=60.0, pass_check=False)
    await _make_daily_report(db_session, u_sales.id, None, today, ai_score=90.0, pass_check=True)

    result = await group_reports_by_department(db_session, today - timedelta(days=7), today, project_id=None)
    by_key = {row.key: row for row in result.groups}
    assert by_key["技术部"].report_count == 2
    assert by_key["技术部"].pass_count == 1
    assert by_key["技术部"].avg_score == 70.0
    assert by_key["技术部"].pass_rate == 50.0
    assert by_key["销售部"].report_count == 1
    assert by_key["销售部"].pass_rate == 100.0
```

### 3.4 Router 层 T-1004 测试（5 cases）

| Case 名 | 端点 | 期望 status |
|---------|------|------------|
| `test_router_dept_list_admin_returns_200` | `GET /api/v1/admin/departments/` | 200 |
| `test_router_dept_list_manager_returns_200` | `GET /api/v1/admin/departments/` | 200 |
| `test_router_dept_list_employee_returns_403` | `GET /api/v1/admin/departments/` | 403 |
| `test_router_dept_create_name_conflict_returns_409` | `POST` 同名两次 | 第二次 409 |
| `test_router_dept_create_invalid_manager_id_returns_400` | `POST` 带不存在 user.id | 400 |

骨架（typical 一例）：
```python
@pytest.mark.asyncio
async def test_router_dept_list_employee_returns_403(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase10_test_data(db_session)
    employee = await _make_user(db_session, UserRole.employee, name="DEPT_EMP")
    resp = await client.get("/api/v1/admin/departments/", headers=_headers(employee))
    assert resp.status_code == 403
```

### 3.5 Router 层 T-1005 测试（5 cases）

| Case 名 | 端点 | 期望 status |
|---------|------|------------|
| `test_router_admin_reports_admin_dept_returns_200` | `GET /api/v1/admin/reports/?group_by=department` | 200 + `group_by == "department"` |
| `test_router_admin_reports_manager_project_returns_200` | `GET /api/v1/admin/reports/?group_by=project` | 200 + `group_by == "project"` |
| `test_router_admin_reports_employee_returns_403` | `GET /api/v1/admin/reports/?group_by=department` | 403 |
| `test_router_admin_reports_invalid_group_by_returns_422` | `GET /api/v1/admin/reports/?group_by=invalid` | 422 |
| `test_router_admin_reports_date_range_invalid_returns_400` | `GET ?group_by=department&start_date=today&end_date=yesterday` | 400 + detail `start_date 不能晚于 end_date` |

骨架（typical 一例）：
```python
@pytest.mark.asyncio
async def test_router_admin_reports_date_range_invalid_returns_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase10_test_data(db_session)
    admin = await _make_user(db_session, UserRole.admin, name="REPORTS_ADM")
    today = date.today()
    resp = await client.get(
        f"/api/v1/admin/reports/?group_by=department&start_date={today.isoformat()}"
        f"&end_date={(today - timedelta(days=1)).isoformat()}",
        headers=_headers(admin),
    )
    assert resp.status_code == 400
    assert "start_date 不能晚于 end_date" in resp.json()["detail"]
```

### 3.6 改 `docs/dev_tasks.md`
Phase 10 看板 Task 7 状态 `[ ] → [x]`（与最后一个 commit 一起 add）。**不动** 📣 锚点(留给指挥官在起草 T-1006 / T-1008 时统一替换)。

---

## 4. 防越界红线表（违反立即回滚）

| # | 项 | 详 |
|---|---|---|
| 1 | 不改 ORM | `backend/app/models/` 任何文件零行 |
| 2 | 不写 migration | `backend/alembic/versions/` 零新文件 |
| 3 | 不动 service / router | T-1003/04/05 的 4 个新建文件 + main.py 零改动 |
| 4 | 不动既有测试 | `test_kpi_phase9.py` 等 19 个文件零改动,**绝对不导入**它们的 helpers |
| 5 | 不动 conftest.py | 只**消费**其 `db_session / client` fixture,**不**新建 conftest 或自定义 engine |
| 6 | 不写 MV / CREATE TABLE | 本测试**不**执行任何 DDL,只读已有 Base.metadata 创建的表 |
| 7 | 不假定 seed 数据 | 每个 test case 开头**强制** `await _cleanup_phase10_test_data(db_session)`,杜绝跨 case 状态泄漏 |
| 8 | 不引入 `print` / `logger.info` | 测试静默,失败靠 assert |
| 9 | 不跳过 cleanup | 即便 partial UNIQUE 测试断言 IntegrityError,**仍要** `await db_session.rollback()` |
| 10 | 不用 `tenant_id != "default"` | 全程锁 `TENANT_ID = "default"`,避免命中 RBAC 多租户边界 |
| 11 | 不 mock | 全部真库 + 真 ORM + 真 service + 真 router(回滚 session 保隔离) |
| 12 | 不 hard-code UUID | 全部用 `uuid.uuid4()` 生成 |
| 13 | 不 sleep | 时间敏感的窗口边界用 `date.today() / timedelta`,严禁 `asyncio.sleep` |
| 14 | 不引入新依赖 | 仅用 `pytest / pytest_asyncio / httpx / sqlalchemy` 已有库 |
| 15 | 不写跳过逻辑 | 严禁 `pytest.mark.skip` / `pytest.skip()`,所有 case 必须执行 |
| 16 | 不改 📣 锚点 | dev_tasks.md L185-end 保留 T-1007 持牌 |
| 17 | 不 `git add` 既定 untracked | `.cursorrules / CLAUDE.md / CONVENTIONS.md / backend/uv.lock` 永远 untracked |
| 18 | 不自启下游 | T-1006 / T-1008 由指挥官另行起草,Worker **不**主动捎带 |
| 19 | 不 `git push` | 全程本地 commit |
| 20 | 不写 frontend | `frontend/src/` 零改动 |

---

## 5. 数据风险评估

| 风险 | 等级 | 缓释 |
|------|-----|------|
| 测试库脏数据残留 | 低 | conftest `setup_test_db` autouse + 每个 case 入口 `_cleanup_phase10_test_data` |
| ProjectMember partial UNIQUE 在测试库不生效 | 低 | 测试库 PG,`create_all` 通过 SQLAlchemy 自动建索引;若 CI 失败需 PM 介入(非 Worker 责任) |
| DailyReport.content 必填 | 低 | helper `_make_daily_report` 固定塞 `"phase10 test content"` |
| 跨 case session 残留 | 极低 | `db_session` fixture 自动 rollback |
| RBAC token 失效 | 极低 | `create_access_token` 已在 `test_kpi_phase9.py` 验证有效;本测试照搬 |
| Project 软删除影响 | 低 | helper 默认创建 `deleted_at IS NULL` 的项目,本测试不触碰软删除路径 |
| Phase 7 MV 是否需要 | 无 | 本测试**不**用 MV,group_reports_by_* 是即时 query |

---

## 6. 测试基线（Worker 提交前必跑,全绿才能 commit）

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/mypy tests/test_phase10_dept_group.py
.venv/bin/pytest tests/test_phase10_dept_group.py -v           # 19 cases 全 passed
.venv/bin/pytest tests/ -q                                      # 总数 ~179 passed, 2 skipped 零回归
.venv/bin/alembic upgrade head && .venv/bin/alembic check       # head 仍 b58bb129c24b
cd ../frontend && npm run lint && npm run typecheck             # 前端无改动,应保持干净
```

**签字不修事项**：
- `app/services/scheduled_tasks.py:609 + app/routers/analytics.py:107-109` 4 个存量 mypy error 与 T-1004/T-1005 同源,**不在本契约范围**,**不修**。
- 本契约只对 `tests/test_phase10_dept_group.py` 跑 mypy,不**强制要求**全 backend mypy 零 error。

---

## 7. 完工提交序列（原子 2 commit,顺序不可乱）

### Commit 1（test feat）
```
feat(tests): add test_phase10_dept_group.py — Phase 10 后端 3 层 19 case 测试

Phase 10 / T-1007 — 集中补 T-1003/04/05 三个后端轮次的测试覆盖,
落地 dev_tasks.md Task 7 签字的 Model + Service + Router 三层契约。

文件改动: backend/tests/test_phase10_dept_group.py(新建)。

测试覆盖:
  - Model 层 (3 case): ProjectMember partial UNIQUE + Department.name UNIQUE
  - Service 层 (5 case): get_department_with_members + group_reports_by_* + _validate_date_range
  - Router 层 (10 case): /admin/departments 5 端点 + /admin/reports 1 端点 RBAC + 错误码

不动 ORM / migration / 现有 service / router / 既有测试文件 / conftest.py / frontend / seed_data.py。

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

### Commit 2（chore close）
```
chore(progress): close T-1007 — Phase 10 后端 3 层 19 case 测试上线

dev_tasks.md Phase 10 章节 Task 7 状态改为 [x]。pytest 全量从 160 → ~179 passed 零回归,
3 层覆盖 Model + Service + Router,后端 Phase 10 契约护栏完工。
📣 恢复执行指令锚点保留 T-1007,留给指挥官起草 T-1006 / T-1008 时统一替换。

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

---

## 8. 验收清单（指挥官二次验收时按此核对）

- [ ] 1. `git log --oneline -3` 显示链路 `<chore close> → <feat tests> → <chore(spec) T-1007>`,顺序正确
- [ ] 2. Commit 1 (feat tests) 改动恰好 1 文件 `backend/tests/test_phase10_dept_group.py`,零夹带
- [ ] 3. Commit 2 (chore close) 仅改 `docs/dev_tasks.md`,Task 7 = `[x]`
- [ ] 4. 新测试文件含 ~19 个 `async def test_*` 函数(允许 ±2 偏差)
- [ ] 5. 每个 test case 入口含 `await _cleanup_phase10_test_data(db_session)`,保证状态隔离
- [ ] 6. 私有 helpers 6 个 (`_cleanup / _make_user / _headers / _make_department / _make_project / _make_daily_report`),全部 `_` 前缀
- [ ] 7. 无 `pytest.mark.skip` / `pytest.skip()` / `print(...)` / `logger.*`
- [ ] 8. 无 `import` 引用其他 test_*.py 文件(零横向耦合)
- [ ] 9. 无 mock(`unittest.mock` / `pytest_mock` 零导入)
- [ ] 10. ruff All passed
- [ ] 11. mypy `tests/test_phase10_dept_group.py` 0 error
- [ ] 12. `pytest tests/test_phase10_dept_group.py -v` 全 passed
- [ ] 13. `pytest tests/ -q` 总数从 `160 passed, 2 skipped` 增至 `~177-181 passed, 2 skipped` 零回归(允许测试数±2 偏差)
- [ ] 14. alembic check `No new upgrade operations detected.`,head 仍 `b58bb129c24b`
- [ ] 15. `git diff origin/main -- backend/alembic/ backend/app/models/ backend/app/services/ backend/app/routers/ backend/app/main.py backend/app/schemas/ frontend/src/ backend/scripts/` 全空(本任务零既有文件改动)
- [ ] 16. `git diff origin/main -- backend/tests/conftest.py` 为空(conftest.py 不动)
- [ ] 17. 两个 commit 的 message 都含 `Worker timestamp: [...]` 行
- [ ] 18. 📣 锚点中"当前持牌任务: T-1007"保留(留给指挥官在 T-1006 / T-1008 spec 中统一替换)
- [ ] 19. 4 既定 untracked 保留 (`.cursorrules / CLAUDE.md / CONVENTIONS.md / backend/uv.lock`)

---

## 9. 与其他任务的关系

- **上游**: T-1003 / T-1004 / T-1005 已全部 `[x]`,本契约**消费**其 ORM / Service / Router,**禁止**修改任何已落地代码。
- **平行**: 无。Codex 不会同时被分派 T-1006 / T-1008。
- **下游**:
  - **T-1006** 前端 Dashboard Tabs 切换器(全员/按部门/按项目)+ admin/departments 管理页 —— 后端已有自动化护栏保障稳定性,前端开发期可以放心 mock /真调
  - **T-1008** 文档收尾(implementation-plan.md §10 + recap.md)—— 引用 T-1007 测试通过数作为 Phase 10 完工证据。
- **跳过**: 不消费、不影响:Phase 9 KPI / Phase 7 物化视图(已签字不复用)/ Phase 8 Export / Phase 6 OKR / Phase 5 Sprint / Phase 4 Gate / Phase 3 Capacity / Phase 2 Auth。

---

## 📣 附录:给 Worker 的物理交接单(指挥官在 chore(spec) commit 同步落盘)

> **更新时间戳**: `[2026-05-27 20:55:00]`
> **当前持牌任务**: **T-1007**(指挥官已通过本 `chore(spec)` commit 一并加锁,Task 7 = `[/]`)
> **任务全称**: Phase 10 后端测试集中补 — `test_phase10_dept_group.py` 三层 19 case 全覆盖

**执行入口**：阅读 `docs/T-1007_spec.md`,不要重复 `chore(lock)`(已由指挥官打过),直接进入实施阶段。**前置勘察已由指挥官完成,无需 Codex 再验**:① `conftest.py` 已提供 `db_session(auto-rollback) + client(dependency_overrides get_db)` 双 fixture,**直接消费**;② `test_kpi_phase9.py` L147-164 的 `_make_user / _headers` 体例已锁定,本契约**照搬不变形**(只改字段值);③ `ProjectMember.__table_args__` 是 partial UNIQUE `(project_id, user_id) WHERE left_at IS NULL`(`models/project_member.py` L34-42),测试时**必须**在 PG 测试库执行,SQLite 不支持 partial index;④ `Department.name` 是 `unique=True`(`models/department.py` L34),无 partial 条件;⑤ `DailyReport.content` 字段 NOT NULL,helper 必须塞默认值;⑥ Phase 7 MV `mv_daily_user_stats / mv_weekly_dept_stats` **不**复用,本测试零 DDL。

**核心动作（2 步,严格按 §3 顺序）**

1. **新建** `backend/tests/test_phase10_dept_group.py` —— 头部 docstring + imports(`pytest / pytest_asyncio / httpx.AsyncClient / SQLAlchemy / delete / IntegrityError / app.models.* / app.services.* / app.middleware.rbac.create_access_token`)。`TENANT_ID = "default"` 常量。6 个 `_*` 私有 helpers(`_cleanup_phase10_test_data / _make_user(role, name, department, is_active) / _headers(user) -> dict / _make_department(name, manager_id) / _make_project(name) / _make_daily_report(user_id, project_id, report_date, ai_score, pass_check)`)。然后 19 个 `@pytest.mark.asyncio async def test_*` 函数,**按 §3.2/3.3/3.4/3.5 顺序分块**(Model 3 + Service 5 + Router T-1004 5 + Router T-1005 5 = 18,允许 ±1 case)。每个 case 入口**强制** `await _cleanup_phase10_test_data(db_session)`。
2. **改** `docs/dev_tasks.md` —— Phase 10 看板 Task 7 从 `[/] In Progress by Codex` 改为 `[x]`(放最后一个 commit 一起 add)。**不动** 📣 锚点(留给指挥官在起草 T-1006 / T-1008 时统一替换)。

**测试 case 锁定表（按文件顺序）**

| # | 块 | Case 名 | 期望 |
|---|---|---------|------|
| 1 | Model | `test_project_member_unique_active_blocks_duplicate` | IntegrityError |
| 2 | Model | `test_project_member_unique_active_allows_after_left` | 两条都成功 |
| 3 | Model | `test_department_unique_name_blocks_duplicate` | IntegrityError |
| 4 | Service | `test_dept_service_get_with_members_returns_active_users` | 仅返回 is_active=True |
| 5 | Service | `test_dept_service_get_with_members_empty_returns_empty_list` | `members == []` |
| 6 | Service | `test_admin_reports_group_by_department_aggregates_correctly` | 4 项指标数值精确 |
| 7 | Service | `test_admin_reports_group_by_project_inner_join_excludes_null_project` | 仅 1 行,NULL project_id 行被排除 |
| 8 | Service | `test_validate_date_range_raises_when_start_after_end` | `ValueError("date_range_invalid")` |
| 9 | Router T-1004 | `test_router_dept_list_admin_returns_200` | 200 |
| 10 | Router T-1004 | `test_router_dept_list_manager_returns_200` | 200 |
| 11 | Router T-1004 | `test_router_dept_list_employee_returns_403` | 403 |
| 12 | Router T-1004 | `test_router_dept_create_name_conflict_returns_409` | 409 |
| 13 | Router T-1004 | `test_router_dept_create_invalid_manager_id_returns_400` | 400 |
| 14 | Router T-1005 | `test_router_admin_reports_admin_dept_returns_200` | 200 + `group_by == "department"` |
| 15 | Router T-1005 | `test_router_admin_reports_manager_project_returns_200` | 200 + `group_by == "project"` |
| 16 | Router T-1005 | `test_router_admin_reports_employee_returns_403` | 403 |
| 17 | Router T-1005 | `test_router_admin_reports_invalid_group_by_returns_422` | 422 |
| 18 | Router T-1005 | `test_router_admin_reports_date_range_invalid_returns_400` | 400 + detail 字面量包含 `"start_date 不能晚于 end_date"` |

**严禁项（违反立即回滚）**：见 §4 红线表 20 项。**特别强调**：① 不动 conftest.py / 既有 test_*.py ② 不引入 mock ③ 不引入 `pytest.skip` ④ 不在 helper 之外硬编码 `tenant_id` 值 ⑤ 不写 print/logger ⑥ 不假定 seed 用户存在,**每个 case 自带 fixture 构造**。

**闸门（全绿才提交）** — 见 §6,完工后跑：
```bash
cd backend
.venv/bin/ruff check .
.venv/bin/mypy tests/test_phase10_dept_group.py
.venv/bin/pytest tests/test_phase10_dept_group.py -v
.venv/bin/pytest tests/ -q                                  # ~179 passed, 2 skipped 零回归
.venv/bin/alembic upgrade head && .venv/bin/alembic check   # head 仍 b58bb129c24b
cd ../frontend && npm run lint && npm run typecheck         # 前端零改动应干净
```

**完工提交序列（原子 2 commit,顺序不可乱）**：见 §7,顺序 = feat → chore close,两个 message 必须包含 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 末行。

**时间戳纪律**：所有 commit message 末尾 / 终端汇报 / 写入 `dev_tasks.md` 段落必须带 `[YYYY-MM-DD HH:MM:SS]`。

**完工后**：停手汇报「T-1007 完工,等待二次验收 + T-1006 / T-1008 起草」,**不要**自启下游 task。
