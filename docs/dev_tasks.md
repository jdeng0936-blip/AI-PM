# Phase 9: KPI 目标设定 (KPI Targets & Achievement Dashboard)

## 当前状态与上下文

- Phase 8 数据导出已合并落地,8 条原子 commit 链路完整(`c23ed01 → 8083ce6`),`/api/v1/export/{reports,scores,project-summary}` 三个接口 + 前端三类下载卡片均已上线,138+ 测试通过。
- 业务流转入 **Phase 9 — KPI 目标设定**。
- 设计源:`docs/implementation-plan.md §9`。最小核心闭环:
  1. 后端可持久化 KPI 目标(全局 / 部门 / 岗位三种 scope × 4 类 metric)。
  2. 后端可计算「目标 vs 实际」达成率快照。
  3. 总经理 / 部门负责人可在前端管理目标并查看达成率仪表盘。
- **关键工程偏差(相对 plan §9)**:
  - `users.id` 在本项目是 `UUID`,plan 里写的 `created_by INT` 需校正为 `UUID FK`。
  - 所有核心业务表必须继承 `app.models.base_mixin.BaseMixin`(自动注入 `created_at / updated_at / created_by / tenant_id`),plan 里的精简 SQL 不能照搬。
  - 路由前缀沿用现有规约 `/api/v1/admin/kpi`(plan 写 `/api/admin/kpi`,统一加 `/v1/`)。
- 当前领先 `origin/main` 16 个 commit,工作树干净(仅 `backend/uv.lock` 未跟踪,继续保持不动)。

## 任务看板

### 数据层 (Models & Migrations)
- [x] **Task 1 (T-901): `kpi_targets` 表与 SQLAlchemy Model**
  - 新建 `backend/app/models/kpi_target.py`(`KpiTarget` 类 + `KpiScope` / `KpiMetric` / `KpiPeriod` 三个 Enum)。
  - 新建 Alembic migration `backend/alembic/versions/20260527_<HHMM>_phase9_add_kpi_targets.py`:`upgrade()` 建表 + 复合索引 + UNIQUE 约束 + 4 条 seed;`downgrade()` 反向回滚。
  - 在 `app/models/__init__.py` 暴露 `KpiTarget` 及三个 Enum,加入 `__all__`。
  - **完整执行契约见 `docs/T-901_spec.md`**(必读)。
  - **验收回执(指挥官 2026-05-27)**: ruff / mypy / `alembic downgrade -1 + upgrade head + check` 全绿,seed 4 行准确,索引 + FK 完整。**但**负向测试发现 UNIQUE 在 `scope_value IS NULL` 时失效(PostgreSQL 默认 NULL DISTINCT 语义)—— 契约 §3.2 设计疏漏,指挥官承担,见 T-901-FIX。

- [x] **Task 1.5 (T-901-FIX): UNIQUE 升级为 `NULLS NOT DISTINCT`**
  - 新增 follow-up migration `backend/alembic/versions/20260527_<HHMM>_phase9_fix_kpi_targets_unique_nulls.py`,drop + recreate UNIQUE 约束并加 `postgresql_nulls_not_distinct=True`。
  - 同步修改 `app/models/kpi_target.py` 的 `UniqueConstraint` 参数,保持 ORM 与 DB schema 一致。
  - **完整执行契约见 `docs/T-901-FIX_spec.md`**(必读)。
  - 验收通过条件:负向测试「重复 `(global, NULL, submit_rate, monthly)` 必须抛 `IntegrityError`」。

### 服务层 (services/)
- [x] **Task 2 (T-902): Pydantic Schemas + KPI 服务层**
  - 新建 `backend/app/schemas/kpi.py`:`KpiTargetIn` / `KpiTargetOut` / `KpiAchievementRow` / `KpiAchievementResponse`。
  - 新建 `backend/app/services/kpi_service.py`:
    - `list_kpi_targets(db) -> list[KpiTargetOut]`
    - `upsert_kpi_target(db, payload, actor) -> KpiTargetOut` —— UNIQUE 冲突走 ON CONFLICT DO UPDATE。
    - `calculate_kpi_achievement(db, period) -> list[KpiAchievementRow]` —— 复用 Phase 7 的 MV(`mv_daily_user_stats / mv_weekly_dept_stats`)+ 现有 `analytics_service` 中的部门聚合做 actual 值,缺数据时 `actual=None / gap=None` 而不是 0。

### 路由层 (routers/)
- [x] **Task 3 (T-903): `/api/v1/admin/kpi` 三端点**
  - 新增 `backend/app/routers/kpi.py`(`prefix="/api/v1/admin/kpi"`,`tags=["KPI"]`),并在 `app.main.py` 注册。
  - `GET /` — 列出所有目标,`require_role(UserRole.admin, UserRole.manager)`。
  - `POST /` — 创建/更新目标,同样 RBAC。请求体经 Pydantic 校验 scope/metric/period 枚举。
  - `GET /achievement?period=monthly` — 计算达成率快照,`period` 默认 `monthly`,支持 `weekly|monthly|quarterly`。

### 测试 (tests/)
- [x] **Task 4 (T-904): 后端测试**
  - 新增 `backend/tests/test_kpi_phase9.py`(沿用 `test_deletion_cleanup.py` 的本地 `db_session` fixture 模式)。
  - 必须覆盖:
    - Model 层:UNIQUE `(scope, scope_value, metric, period)` 冲突抛 `IntegrityError`;Enum 值非法插入失败。
    - Service 层:`upsert_kpi_target` 重复 key 走 update;`calculate_kpi_achievement` 在无实际数据时返回 `actual=None`。
    - Router 层:200 路径 + RBAC(普通员工 403)+ 参数校验(`?period=daily` 422)。
  - 跑通后所有 quality gates 必须全绿。

### 前端 (frontend/src/app/)
- [x] **Task 5 (T-905): KPI 管理页 `/admin/kpi`**
  - 新建 `frontend/src/app/admin/kpi/page.tsx`,表格 + 新建/编辑 Modal,字段含 scope / scope_value / metric / target_value / period。
  - 调用 `/api/v1/admin/kpi` GET/POST,使用现有 `apiFetch` 帮助函数。
  - RBAC:页面入口在 admin / manager 可见;员工身份直接 redirect。

- [x] **Task 6 (T-906): 达成率仪表盘组件**
  - 在 `/dashboard` 加一个「KPI 达成率」面板(admin / manager 可见),调 `/api/v1/admin/kpi/achievement`。
  - 用现有 `CompareBarChart`(Phase 7 已封装)展示「目标 vs 实际」,达成的绿色,未达成的红色;`actual=null` 标灰并写「暂无数据」。

### 文档与收尾
- [x] **Task 7 (T-907): 文档收尾 + 后端测试补全**
  - 更新 `docs/recap.md` 追加 Phase 9 章节(「当前阶段」改为 Phase 9 + 6 条 bullet + 7 条历史移交记录)。
  - 在 `docs/implementation-plan.md §9` 末尾**追加**「实际落地路径(Phase 9)」段:
    - `id` 字段类型偏差(SERIAL → Integer autoincrement,plan 原意保留)。
    - `created_by` 类型校正(INT → UUID FK)。
    - 路由前缀(`/api/admin/kpi` → `/api/v1/admin/kpi`)。
    - 引入 `tenant_id / created_at` 字段(继承 BaseMixin)。
    - UNIQUE NULLS NOT DISTINCT(T-901-FIX 补,plan 漏列)。
    - metric 枚举校正(`sprint_completion` → `objective_completion`)。
  - 在 `backend/tests/test_kpi_phase9.py` 末尾追加 3 个测试(achievement 真路径计算 / router POST 创建 / manager RBAC),`pytest -v` 应 12 passed。
  - **完整执行契约见 `docs/T-907_spec.md`**(必读)。

### 漂移修复 (Drift Fixes)
- [x] **Task 8 (T-908): 修 metric 枚举漂移**
  - 出处:T-907 验收时勘察发现 —— 后端 ORM/migration `sprint_completion` 与前端 T-905/T-906 已 ship 的 `objective_completion` 命名不一致,导致前端 POST OKR 完成率会被后端 422,后端 seed `sprint_completion` 行在 dashboard 显示时指标名空白。
  - 修复:新增 alembic migration `ALTER TYPE kpi_metric RENAME VALUE 'sprint_completion' TO 'objective_completion'`(PG native enum 原子重命名,seed 自动同步),同步 ORM `KpiMetric` Enum 与 Pydantic schema docstring。
  - 不动前端 / 不动历史 migration / 不动测试代码 / 不动 service 逻辑。
  - **完整执行契约见 `docs/T-908_spec.md`**(必读)。

---

# Phase 10: 部门与项目分组(勘察先行轮)

## 当前状态与上下文

- Phase 9(KPI 目标设定)已 100% 闭环并推送至 `origin/main`(`0b2a150`),全部 54 commit 已合并。
- Phase 10 启动时发现**真实歧义**:`implementation-plan.md` §10 原文(L737-784)描述「`departments` 独立表 + `/api/admin/reports?group_by=` 端点 + 前端 Tabs 切换器」,但**附录 A L1077** 又标 §10 ✅(关键文件 `models/{project,project_member,project_stage}.py`、`routers/projects.py`)。
- 指挥官初步勘察证实**部分实现 + 部分空白**:
  - ✅ 已实现:`Project` / `ProjectMember` / `ProjectStage` 三个 ORM + `routers/projects.py` 31KB + 前端 `/projects` 列表 + `/project/[id]` 详情 + `users.department VARCHAR` 字段 + `trends.py / dashboard.py` 内部 `group_by(department)` 聚合。
  - ❌ 未实现:**`departments` 独立表 ORM/migration(只有 user 上的字符串字段)** / **`/api/admin/reports?group_by=department\|project` 对外端点** / **前端总经理看板的 Tabs 切换器(全员/按部门/按项目)**。
- **Phase 10 第一步定位:勘察先行,落盘后再投实施任务**。本轮(T-1001)是**纯文档勘察 + 落盘任务**,Worker 仅做只读 grep + 文档写入,**严禁写任何业务 src 代码 / 迁移 / 测试**。
- 当前 alembic head:`e8c4a1d9f2b0`(`20260527_1722_phase9_rename_metric_objective_completion.py`),Phase 10 后续任何 migration 必须以此为 `down_revision`。
- 工作树干净,仅 4 既定 untracked(`.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md` / `backend/uv.lock` 继续不动)。

## 任务看板

### 勘察 (Survey & Documentation)
- [x] **Task 1 (T-1001): §10 实物盘点 + plan 实际落地路径段落落盘**
  - 对 `models/project.py / project_member.py / project_stage.py / user.py`、`routers/projects.py / dashboard.py / trends.py` 做只读勘察,提取 6 个维度对照(参见 T-1001_spec §3)。
  - 在 `docs/implementation-plan.md §10` 末尾**追加**「实际落地路径(Phase 10 勘察)」段,与 §9 末尾的「实际落地路径(Phase 9)」格式对齐:6 列对照表 + 已实现 API 路径表 + 待补齐清单。
  - **完整执行契约见 `docs/T-1001_spec.md`**(必读)。
  - **不许写任何业务 src 代码 / 不许新建 alembic migration / 不许动测试**。

### 漏洞修复 (Drift Fixes)
- [x] **Task 2 (T-1002): `ProjectMember` 联合 UNIQUE 补丁**
  - 出处:T-1001 勘察时发现 —— `ProjectMember` 已存在多年但**缺 `UNIQUE(project_id, user_id)` 约束**(只有单字段 index),意味着可以重复插入同一员工到同一项目,后续 `health_engine` 按成员聚合时会出现重复计数。
  - 修复:**partial unique index** `WHERE left_at IS NULL` —— 软删除友好(允许员工离开后重新加入,生成新行),不破坏现有「离职/再入项目」工作流。
  - 同步:`ProjectMember.__table_args__` 加 `Index(..., unique=True, postgresql_where=text("left_at IS NULL"))`,保持 ORM ↔ DB schema 一致。
  - 不动种子数据 / 不动任何 service / router / 前端 / 测试 —— 纯 schema 补丁。
  - **完整执行契约见 `docs/T-1002_spec.md`**(必读)。

### 后续任务(T-1003 已起草,T-1004 及以后由指挥官在 T-1003 完工后接力起草)
- [x] **Task 3 (T-1003): `departments` 独立表 + ORM + 7 seed**
  - 新建 `backend/app/models/department.py`(`Department(BaseMixin, Base)`,字段:`id UUID PK / name String(64) UNIQUE / manager_id UUID FK→users.id ON DELETE SET NULL nullable=True index=True`)。
  - 新建 Alembic migration:`upgrade()` 建表 + 2 个 index + bulk_insert 7 seed(技术部/生产部/采购部/财务部/商务部/销售部/仓储部,顺序锁定,manager_id 全 NULL,tenant_id="default",id 用 Python `uuid.uuid4()` 预生成);`downgrade()` 反向 drop_index ×2 + drop_table。
  - 在 `app/models/__init__.py` 暴露 `Department`(插入式,不重排其他 import),加入 `__all__`(插入式,不重排其他字符串)。
  - **不**改 `User.department: VARCHAR(64)` 字段(增量并存,FK 迁移延后到 Phase 11+)。
  - **不**写 service / router / schema(留给 T-1004) / 前端 / 测试 / `scripts/seed_data.py`。
  - **完整执行契约见 `docs/T-1003_spec.md`**(必读)。

- [x] **Task 4 (T-1004): `/api/v1/admin/departments` 服务 + 路由(5 端点 CRUD + members 反查)**
  - 新建 `backend/app/schemas/department.py`(`DepartmentIn / DepartmentUpdate / DepartmentOut / DepartmentMember / DepartmentWithMembers` 共 5 个 Pydantic V2 schemas)。
  - 新建 `backend/app/services/department_service.py`(5 个 async 公开函数 `list_departments / create_department / update_department / delete_department / get_department_with_members`,**不 raise HTTPException**,统一 ValueError("not_found"|"name_conflict"|"manager_not_found") 错误信号)。
  - 新建 `backend/app/routers/departments.py`(`prefix="/api/v1/admin/departments"`, `tags=["Departments"]`),5 端点 + `_map_value_error` 映射:GET `/`(列表) / POST `/`(201) / GET `/{id}/members` / **PATCH `/{id}`(部分更新)** / **DELETE `/{id}`(204 硬删除)**,RBAC `require_role(admin, manager)`。
  - 改 `backend/app/main.py`(插入式 2 行:import 块 `departments,` 在 `dashboard` 与 `erp` 之间;`app.include_router(departments.router)` 紧邻 `kpi` 之后)。
  - 成员反查口径:`GET /{id}/members` 从 `User.department: String(64)` 等值反查 + `User.is_active.is_(True)` + `tenant_id = "default"` 过滤(**本仓库 User 模型无 `deleted_at` 字段**,软删除信号 = `is_active=False`,详见 `T-1004_spec.md §3.2 User 活跃字段说明`),按 `name asc` 排序,字段裁剪到 `id / name / role / department`。
  - **完整执行契约见 `docs/T-1004_spec.md`**(必读)。
  - **验收回执(指挥官 `[2026-05-27 20:22:00]`)**:§8 验收清单 16 项 100% 通过。文件隔离正确(feat 4 文件 / chore 1 文件,零夹带 alembic/tests/frontend/models/seed_data.py);代码闸门全绿(ruff All passed / mypy 目标 4 文件 0 error[现有 analytics.py + scheduled_tasks.py 4 个存量 error 不在本契约范围] / pytest `160 passed, 2 skipped` 零回归 / alembic check `No new upgrade operations detected.` / 前端 lint+typecheck 干净);RBAC 锁定 `admin + manager`,端点+错误码表 100% 对齐 §3.3 / §3.2 ValueError 字面量;commit message 均带 `Worker timestamp:` 行;`update_department` 中 `_ = actor` unused-argument 抑制属合规小冗余,不阻断验收。

- [x] **Task 5 (T-1005): `/api/v1/admin/reports?group_by=` 对外分组聚合端点**
  - **新建** `backend/app/routers/admin_reports.py`(`APIRouter(prefix="/api/v1/admin/reports", tags=["Admin Reports"])`,1 个 GET 端点)。
  - **新建** `backend/app/services/admin_reports_service.py`(2 个 async 公开函数 `group_reports_by_department / group_reports_by_project` + 2 个 `_` 私有助手,**不 raise HTTPException**,统一 ValueError("date_range_invalid") 错误信号)。
  - **新建** `backend/app/schemas/admin_reports.py`(`GroupBy = Literal["department", "project"]` + `ReportGroupRow`(4 项指标) + `GroupedReportsResponse`)。
  - **改** `backend/app/main.py`(插入式 2 行:import 块 `admin_reports,` 字母序在 `analytics,` 之前;`app.include_router(admin_reports.router)` 紧邻 `app.include_router(departments.router)` 之后)。
  - 端点契约:`GET /api/v1/admin/reports?group_by=department|project&project_id=&start_date=&end_date=` → `GroupedReportsResponse`(200);`group_by` 必传(`GroupBy` Literal 自动 422);`project_id / start_date / end_date` 全 optional(默认 `end_date=today, start_date=today-30`);`start_date > end_date` → 400("start_date 不能晚于 end_date");RBAC `require_role(admin, manager)`(零 employee)。
  - 聚合指标 4 项(对齐 `trends.py L92-101`):`report_count` / `avg_score`(COALESCE 0 round 1 位) / `pass_count`(FILTER pass_check=True) / `pass_rate`(round(pass_count/max(report_count,1)*100, 1))。
  - 过滤口径锁定:**强制** `DailyReport.deleted_at.is_(None) + DailyReport.tenant_id == "default"`;`group_by=project` 额外叠加 `Project.deleted_at.is_(None)` + `inner join Project`(剔除未挂项目日报);**不**过滤 `User.is_active`(用户状态不影响历史日报聚合权重)。
  - 与现有端点并存(签字):`trends.py /department-stats` / `dashboard.py /temp-ticket-summary` / `dashboard.py /weekly-stats` **保留不动**,T-1005 新增端点供 T-1006 前端 Dashboard Tabs 切换器消费,**禁止**改既有端点。
  - **完整执行契约见 `docs/T-1005_spec.md`**(必读)。
  - **验收回执(指挥官 `[2026-05-27 20:49:30]`)**:§8 验收清单 17 项 100% 通过。文件隔离正确(feat 4 文件 = main.py 插入式 2 行 + 3 新建 / chore 1 文件 dev_tasks.md +1 -1,零夹带 alembic/tests/frontend/models/dashboard.py/trends.py/reports.py/departments.py);代码闸门全绿(ruff All passed / mypy 目标 4 文件 0 error[现有 analytics.py + scheduled_tasks.py 4 个存量 error 与 T-1004 同源,spec §6 已签字不修] / pytest `160 passed, 2 skipped` 零回归 / alembic check `No new upgrade operations detected.` head 仍 `b58bb129c24b` / 前端 lint+typecheck 干净);Schema 3 公开类型对齐 §3.1 / Service 2 公开 + 2 `_*` 私有零 HTTPException 对齐 §3.2 / Router 1 GET + `_map_value_error` 仅映射 `date_range_invalid` + 兜底 500 对齐 §3.3 / RBAC `admin + manager` 零 employee / 过滤口径强制 `DailyReport.deleted_at.is_(None) + tenant_id == "default" + Project.deleted_at.is_(None)`(仅 project 路径) + **不**过滤 `User.is_active`;`group_by=project` 用 inner join 剔除 NULL project_id 行;两 commit 均含 `Worker timestamp:` 行;📣 锚点 T-1005 持牌保留待统一替换。

- [x] **Task 6 (T-1006): 前端 Dashboard Tabs 切换器 + admin/departments 管理页** — Done by Codex(`[2026-05-27 21:57:16]`)
  - **新建** `frontend/src/api/admin.ts`(~110 行,6 函数 + 6 类型:`listDepartments / createDepartment / getDepartmentWithMembers / updateDepartment / deleteDepartment / getGroupedReports`)。
  - **新建** `frontend/src/app/admin/departments/page.tsx`(~280 行,表格 5 列 + Modal 新建/编辑共用 + 删除 confirm,字段 name + manager_id,RBAC 守卫仿 `/admin/kpi`)。
  - **改造** `frontend/src/app/dashboard/page.tsx`(+60/-0 局部插入 5 个插入点:imports / state / effect / Tabs JSX / sections wrap,**严禁**重排现有 5 sections 内部 markup;`viewMode === 'all'` 时所有现有行为 100% 不变)。
  - **改造** `frontend/src/components/sidebar.tsx`(+1/-0:`Building2` import + ADMIN_ITEMS 数组在 recycle-bin 之前插入 `{href: '/admin/departments', label: '部门管理', icon: Building2}`)。
  - **改** `docs/dev_tasks.md`(Task 6 → `[x]`,与最后一个 commit 一起 add)。**不动** 📣 锚点(留给指挥官在起草 T-1008 时统一替换)。
  - **完整执行契约见 `docs/T-1006_spec.md`**(必读,~660 行 10 章 + 📣 附录)。

- [x] **Task 7 (T-1007): 后端测试 `test_phase10_dept_group.py`** — Done by Codex(`[2026-05-27 21:27:47]`)
  - **新建** `backend/tests/test_phase10_dept_group.py`(~380 行,~19 个 `async def test_*` case)。
  - **覆盖**:Model 层 3 case(ProjectMember partial UNIQUE `(project_id, user_id) WHERE left_at IS NULL` + `left_at` 非空允许重复 + Department.name UNIQUE) + Service 层 5 case(`get_department_with_members` 反查活跃用户 + 空部门返回 `[]` + `group_reports_by_department` 4 指标聚合精确 + `group_reports_by_project` inner join 剔除 NULL project_id + `_validate_date_range` start>end 抛 `ValueError("date_range_invalid")`) + Router 层 10 case(T-1004 5 端点 admin/manager/employee RBAC + name_conflict 409 + manager_not_found 400 + T-1005 admin/manager 200 + employee 403 + `?group_by=invalid` 422 + `start_date>end_date` 400 detail 字面量)。
  - **fixtures**:消费 `conftest.py` 已有 `db_session(auto-rollback) + client(dependency_overrides)`,**不**新建 fixture。私有 helpers 6 个(`_cleanup_phase10_test_data / _make_user / _headers / _make_department / _make_project / _make_daily_report`)。每 case 入口**强制** `await _cleanup_phase10_test_data(db_session)`。
  - **改** `docs/dev_tasks.md`(Task 7 → `[x]`,与最后一个 commit 一起 add)。**不动** 📣 锚点(留给指挥官在起草 T-1006 / T-1008 时统一替换)。
  - **完整执行契约见 `docs/T-1007_spec.md`**(必读)。
  - **指挥官二次验收(`[2026-05-27 21:32:50]`)**:✅ PASS。§8 验收清单 **19/19 全通过**:① commit 链路 `bb18476 → 359c1e8 → 5b6b01f` 干净 ② feat 仅 1 文件新建 420 行(契约预估 ~380 +10% 内合理) ③ chore 仅 `dev_tasks.md` +1/-1 ④ **18/18 case 命名 100% 对齐契约**(grep 校验通过) ⑤ 6/6 helpers `_cleanup_phase10_test_data / _make_user / _headers / _make_department / _make_project / _make_daily_report` 完整 ⑥ **零 mock/skip/print/logger/monkeypatch**(grep 严禁项校验 0 hit) ⑦ `ruff check .` All passed ⑧ `mypy tests/test_phase10_dept_group.py` 0 error ⑨ **pytest 新文件 18/18 passed in 7.29s** ⑩ **pytest 全量 178 passed, 2 skipped**(从 T-1005 的 160 准确 +18 case,**零回归**) ⑪ `alembic check` No new upgrade operations(head 仍 `b58bb129c24b`) ⑫ 前端 `npm run lint && npm run typecheck` 全干净(零改动应清白) ⑬ `git diff 5b6b01f..HEAD -- backend/app/ backend/alembic/ frontend/ docs/T-1007_spec.md` 完全空(零夹带验证) ⑭ Worker timestamp 双 commit 均带(`21:27:12` / `21:28:26`) ⑮ 📣 锚点保留 T-1007 持牌(留给指挥官替换) ⑯ 4 既定 untracked 保留未污染 ⑰ `_cleanup_phase10_test_data` 入口存在(L48,作用域至 wechat_userid like "phase10_%") ⑱ Task 7 = `[x] Done by Codex` ⑲ 测试目录零 `.pyc / __pycache__` 夹带。**Phase 10 后端契约护栏闭环完成**,Codex 此次质量稳定连续两轮(T-1005 + T-1007)零小冗余、零踩雷。

- [ ] **Task 8 (T-1008): 文档收尾**
  - 在 `docs/implementation-plan.md §10` 末尾再追加「实际落地路径(Phase 10 实施)」段,记录 6 列对照表对应维度从 ❌ → ✅ 的变化与最终对外路径。
  - 更新 `docs/recap.md`「当前阶段」→ Phase 11 候选,新增 Phase 10 全 task bullet + 历史移交记录条目。

## 质量闸门(Codex 提交前必跑)

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/mypy app/models/kpi_target.py app/services/kpi_service.py app/routers/kpi.py
cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic check
cd backend && .venv/bin/pytest tests/test_kpi_phase9.py -v
cd frontend && npm run lint && npm run typecheck
```

全绿后才能打 `feat(kpi):` 原子提交。

---

> **执行协议提醒 (Codex 请注意)**:
> 1. 每次认领任务前,将上方对应方括号修改为 `[/]`,并立即提交 `chore(lock): wip for task X`。
> 2. 完成后修改为 `[x]` 并打原子 `feat(kpi):` 或 `fix(kpi):` 提交。
> 3. **不要回填或删改** `kpi_targets` 之外的任何表 —— Phase 9 是纯增量。
> 4. Alembic 新 migration 必须 `Revises` 指向当前 `alembic heads` 输出,**不要硬编码上一个 revision id**;`alembic downgrade -1` 必须可回滚。
> 5. `backend/uv.lock` 继续保持未跟踪,不要 `git add`。
> 6. 完工后更新 `docs/recap.md`,然后由 QA Agent(我)接手跑全套质量闸门 + 数据库级集成测试补强。

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌,供 PM 探针自动提取**
> **更新时间戳**: `[2026-05-27 21:35:00]`(指挥官 T-1007 验收闭环 + T-1006 spec 落盘 + 锚点替换)

- **当前持牌任务**: **T-1006**(指挥官已通过本 `chore(spec)` commit 一并加锁,Task 6 = `[/]`)—— Phase 10 **第六份代码任务,前端管理后台 + Dashboard Tabs 切换器主线轮**:**3 新建 + 2 改造,共 5 文件 ±0 夹带**。新建 `frontend/src/api/admin.ts`(~110 行,6 函数 + 6 类型) + `frontend/src/app/admin/departments/page.tsx`(~280 行,表格 + Modal 新建/编辑 + 删除 confirm,字段 name + manager_id);改造 `frontend/src/app/dashboard/page.tsx`(+60/-0 5 个局部插入点:imports / state / effect / Tabs JSX / sections wrap) + `frontend/src/components/sidebar.tsx`(+1/-0 ADMIN_ITEMS 数组追加 `/admin/departments`)。**严禁夹带任何 backend/ / 既有 test_*.py / 既有 admin 子路由 / Dashboard 现有 5 sections 内部 markup 改动**。
- **执行入口**: 阅读 `docs/T-1006_spec.md`(~660 行,10 章 + 📣 附录),不要重复 `chore(lock)`(已由指挥官打过),直接进入实施阶段。**前置勘察已由指挥官完成,无需 Codex 再验**:① `frontend/src/app/admin/kpi/page.tsx` 是镜像参考(role guard L86-103 + Modal + form state + toast 错误模式,**照搬体例不变形**);② `frontend/src/api/kpi.ts` 是 API 客户端镜像参考(`request.get/post + as unknown as Promise<T>` 体例);③ `frontend/src/components/sidebar.tsx` L48-62 已锁定 ADMIN_ITEMS 插入位(`/admin/recycle-bin` 之前一行);④ `frontend/src/app/dashboard/page.tsx` 是 1212 行大文件,L386 `return (` 之后 L392 "监控台"标题之后插 Tabs,**所有插入点为局部**,严禁重排;⑤ 项目**无 shadcn UI kit**,Modal 用原生 `<div fixed inset-0>` 自绘,**不要**新建 `@/components/ui`;⑥ 项目有 `sonner` toast + `lucide-react`(`Building2 / Pencil / Plus / Trash2` 现有图标),**不要**新引入 npm 依赖;⑦ 后端 contract 已锁(`DepartmentIn = {name, manager_id?}` / `DepartmentOut = {id, name, manager_id, created_at, updated_at, created_by, tenant_id}` / `GroupedReportsResponse = {group_by, start_date, end_date, project_id, groups: [{key, report_count, avg_score, pass_count, pass_rate}]}`,详见 §3.6 完整骨架)。
- **核心动作**(严格按 T-1006_spec §4 5 步顺序):
  1. **新建** `frontend/src/api/admin.ts` —— 按 §3.6 完整骨架照搬 ~110 行,6 函数 + 6 类型,**禁止**改名(`listDepartments / createDepartment / getDepartmentWithMembers / updateDepartment / deleteDepartment / getGroupedReports`)。
  2. **新建** `frontend/src/app/admin/departments/page.tsx` —— 按 §3.4 + §4 Step 2 骨架照搬 ~280 行,**UUID_REGEX 正则字面量** = `/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i`;错误码 4 项 mapping 落齐(409 name_conflict / 400 manager_not_found / 400 department_not_found / 403 → redirect /);**严禁**引入 manager dropdown。
  3. **改造** `frontend/src/app/dashboard/page.tsx` —— 5 个**局部插入点**(imports / state `ViewMode = 'all' | 'by_department' | 'by_project'` / effect 监听 viewMode / Tabs JSX 三按钮组 / 现有 5 sections 外包 `{viewMode === 'all' && (...)}`),**严禁**重排现有 5 sections 内部 markup,`viewMode === 'all'` 时所有现有行为 100% 不变(零回归);**`canSeeTabs` 不新建独立 state**,直接 `userRole === 'admin' || userRole === 'manager'` 内联判断。
  4. **改造** `frontend/src/components/sidebar.tsx` —— lucide-react import 追加 `Building2` + `ADMIN_ITEMS` 数组在 `{ href: '/admin/recycle-bin', ... }` **之前**插入 `{ href: '/admin/departments', label: '部门管理', icon: Building2 }` 一行。**严禁**改其它 admin 项的顺序 / 图标。
  5. **改** `docs/dev_tasks.md` —— Phase 10 看板 Task 6 从 `[/] In Progress by Codex` 改为 `[x]`(放最后一个 commit 一起 add)。**不动** 📣 锚点(留给指挥官在起草 T-1008 时统一替换)。
- **严禁项**(违反则立即回滚,详见 §5 红线表 20 项):
  - **严禁**改 `backend/` 任何文件(后端契约护栏完毕,纯前端 task)。
  - **严禁**改任何已有测试文件 / `seed_data.py` / `conftest.py`。
  - **严禁**引入新 npm 依赖(只用 `react / next / @/api/request / sonner / lucide-react` 现有库)。
  - **严禁**改 `package.json` / `tsconfig.json` / `next.config.*` / `tailwind.config.*` / `postcss.config.*`。
  - **严禁**改 4 既定 untracked 文件(`.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md` / `backend/uv.lock`)。
  - **严禁**动 `/admin/kpi` / `/admin/recycle-bin` 路由文件(沿用,只新增 `/admin/departments`)。
  - **严禁**动 dashboard 现有 5 sections **内部 markup**(只在最外层加 `{viewMode === 'all' && (...)}` 包装)。
  - **严禁**引入图表(`CompareBarChart` / `TrendLineChart`)到分组视图,只用原生 `<table>`(T-1008 后再视情况补)。
  - **严禁**引入 manager dropdown / date picker(降复杂度,UUID 文本输入足够)。
  - **严禁**写自动化测试(本 task 纯 UI,后端 178 case 已护栏)。
  - **严禁**持久化 `viewMode` 到 localStorage / URL(避免污染 router 模式)。
  - **严禁**调 `/users` 拉取 manager 列表(避免爆炸面)。
  - **严禁**传 `start_date / end_date / project_id` 到 `/admin/reports`(让后端走默认窗口 today-30 ~ today)。
  - **严禁**破坏 employee 视图(employee 仍看到现有 Dashboard 全员视图,只是 Tabs 不显示)。
  - **严禁** 改 📣 锚点(留给指挥官 T-1006 验收闭环时替换)。
  - **严禁** 自动 `git push`。
  - **严禁** 自启 T-1008。
  - **严禁** 新建 `@/components/ui`(项目无 shadcn,Modal 用原生 div 自绘)。
  - **严禁** commit 时夹带 `node_modules` / `.next` / `.cache`。
- **设计决策签字锁定**(T-1006_spec §3,Worker 不得偏离):

  | 决策 | 锁定值 |
  |------|--------|
  | Tabs 位置 | "监控台"标题下方,4 个统计卡片之上一行 |
  | Tabs 形态 | 3 个原生 button(全员视图 / 按部门聚合 / 按项目聚合) |
  | Tabs 可见性 | 仅 `admin + manager`(employee 不显示) |
  | viewMode 默认值 | `'all'`(进入页第一次始终全员) |
  | viewMode 持久化 | **不持久化**(无 localStorage / URL) |
  | 'all' 行为 | 现有 5 sections 100% 不变 |
  | 'by_*' 行为 | **隐藏** 5 sections + 显示 1 个 5 列表格 |
  | 表格 5 列 | 部门 (or project_id 前 8 位...) / 日报数 / 均分 / 通过数 / 通过率 |
  | 分组数据源参数 | 不传 start_date / end_date / project_id(后端默认窗口 today-30 ~ today) |
  | departments 页 RBAC | useEffect 内 toast + router.replace('/')(模仿 kpi 页 L98-103) |
  | departments 页 Modal 字段 | name(必填,1-64) + manager_id(可选,UUID 正则) |
  | UUID_REGEX | `/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i` |
  | 删除 confirm | `window.confirm(\`确认删除部门「${row.name}」?\`)` |
  | 错误码 mapping | 409 name_conflict / 400 manager_not_found / 400 department_not_found / 403 redirect / fallback "操作失败" |
  | sidebar 插入位 | ADMIN_ITEMS 数组 `/admin/recycle-bin` 之前 |
  | sidebar 图标 | `Building2`(lucide-react 现有) |
  | sidebar label | "部门管理" |

- **闸门**(全绿才提交):
  ```bash
  cd frontend
  npm run lint          # eslint 全过,零 warning
  npm run typecheck     # tsc --noEmit 0 error
  ```
  **手动验证 4 场景**(指挥官 T-1006 验收会按此核验):
  1. admin 账户 → `/admin/departments` → 加载列表 → 新建部门 → 编辑 → 删除。
  2. admin / manager 账户 → `/dashboard` → 顶部 Tabs 3 按钮切换:全员视图 / 按部门聚合 / 按项目聚合。
  3. employee 账户 → `/dashboard` → **不显示** Tabs(canSeeTabs=false)。
  4. employee 账户访问 `/admin/departments` → toast 报错 + redirect `/`。
- **完工提交序列**(原子 2 commit,**顺序不可乱**):
  1. `feat(admin): Phase 10 前端 admin/departments 管理页 + Dashboard Tabs 切换器`(4 文件:2 新建 `api/admin.ts` + `admin/departments/page.tsx` + 2 改造 `dashboard/page.tsx` + `sidebar.tsx`)
  2. `chore(progress): close T-1006 — Phase 10 前端管理后台 + Tabs 切换器上线`(只含 `docs/dev_tasks.md`,Task 6 → `[x]`)
- **时间戳纪律**: 所有 commit message 末尾(`Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 一行)、终端汇报、任何写入 `dev_tasks.md` 的段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。
- **完工后**: 立即停手汇报「T-1006 完工,等待指挥官二次验收 + 起草 T-1008 (文档收尾) 实施契约」。**不要**自行启动 T-1008。
