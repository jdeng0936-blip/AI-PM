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

- [x] **Task 6 (T-1006): 前端 Dashboard Tabs 切换器 + admin/departments 管理页** — Done by Codex(初提 `[2026-05-27 21:57:16]` + UUID_REGEX 复议 `[2026-05-28 09:04]`),**指挥官三次验收通过** `[2026-05-28 09:07:30]`
  - **新建** `frontend/src/api/admin.ts`(~110 行,6 函数 + 6 类型:`listDepartments / createDepartment / getDepartmentWithMembers / updateDepartment / deleteDepartment / getGroupedReports`)。
  - **新建** `frontend/src/app/admin/departments/page.tsx`(~280 行,表格 5 列 + Modal 新建/编辑共用 + 删除 confirm,字段 name + manager_id,RBAC 守卫仿 `/admin/kpi`)。
  - **改造** `frontend/src/app/dashboard/page.tsx`(+60/-0 局部插入 5 个插入点:imports / state / effect / Tabs JSX / sections wrap,**严禁**重排现有 5 sections 内部 markup;`viewMode === 'all'` 时所有现有行为 100% 不变)。
  - **改造** `frontend/src/components/sidebar.tsx`(+1/-0:`Building2` import + ADMIN_ITEMS 数组在 recycle-bin 之前插入 `{href: '/admin/departments', label: '部门管理', icon: Building2}`)。
  - **改** `docs/dev_tasks.md`(Task 6 → `[x]`,与最后一个 commit 一起 add)。**不动** 📣 锚点(留给指挥官在起草 T-1008 时统一替换)。
  - **完整执行契约见 `docs/T-1006_spec.md`**(必读,~660 行 10 章 + 📣 附录)。
  - **指挥官二次验收(`[2026-05-27 22:04:30]`)**:**⚠️ 驳回(18/19 PASS + 1 FAIL)**。**唯一 BLOCKER**:`frontend/src/app/admin/departments/page.tsx` **L17 UUID_REGEX 缺第 4 段 `[0-9a-f]{4}-`**,字面量违反契约 §3.4 + §9 验收清单 #13 锁定值。Worker 实际写入 `/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i`(只有 8-4-4-12 共 **4** 段),契约签字字面量 `/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i`(8-4-4-4-12 共 **5** 段)。**复现证据**(node REPL):合法 UUID `550e8400-e29b-41d4-a716-446655440000` 在 Worker regex 下返回 `false`,在契约 regex 下返回 `true`。**业务影响**:用户在新建/编辑部门时,若填入任何合法 UUID 作为 manager_id,前端 toast `"负责人 ID 必须是合法 UUID"` 报错,**manager_id 字段实际不可填**(必须留空才能 submit),违反契约 §3.4 "字段 2:负责人 user.id(UUID 文本输入,可选)" 设计意图。其余 18 项全通过:① commit `e62279b → 72111e2 → d0e2443` 链路干净 ② `git diff d0e2443..HEAD -- backend/` 完全空(零 backend 夹带) ③ `api/admin.ts` 83 行 6 函数 + 6 类型 100% 对齐契约 §3.6 ④ `admin/departments/page.tsx` 306 行 + 6 imports 完整 + Modal 字段 2 项(name + manager_id)无第三字段夹带 ⑤ `dashboard/page.tsx` 现有 5 sections **markup 0 删除**(grep `^-[^-]` zero hits)+ `ViewMode / viewMode / groupedRows / groupedLoading` 命名 100% 对齐 ⑥ `canSeeTabs` 内联无独立 state ⑦ Tabs 三按钮 + canSeeTabs gate ✅ ⑧ 5 列表格列名 100% 对齐("部门 / 日报数 / 均分 / 通过数 / 通过率") ⑨ `(未挂部门)` fallback + project_id 前 8 位短串 ⑩ `sidebar.tsx` `Building2` lucide-react import + ADMIN_ITEMS 数组 recycle-bin 之前一行 ⑪ npm run lint 干净 ⑫ npm run typecheck 0 error ⑬ 后端 pytest 178 passed 零回归 ⑭ 4 既定 untracked 保留 ⑮ Worker timestamp 双 commit 均带(`21:58:04` / `21:58:28`) ⑯ 📣 锚点保留 T-1006 持牌(待指挥官替换) ⑰ window.confirm `"确认删除部门「${row.name}」?"` 字面量对齐 ⑱ `mapDepartmentError` 实现 4 项错误码 mapping(意外加分 — 包了双向英中文 detail 兼容,合理扩展无副作用)。**亮点**:Worker 把 4 项错误码 mapping 抽成 `mapDepartmentError(error, router, fallback)` helper,共用给 loadRows/handleSubmit/handleDelete,降低代码重复;Modal 添加 click-outside-to-close + stopPropagation,改善 UX。**减分**:① UUID_REGEX 缺第 4 段(BLOCKER) ② 双 commit message 极简(仅 Worker timestamp 一行,无描述体,影响后续审计可读性 — 非 BLOCKER,记一项)。
  - **🛠 复议指令(物理交接单)**:Codex 必须执行**一行修复 + 1 commit**:① `frontend/src/app/admin/departments/page.tsx` L17 把 `/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i` 改为 `/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i`(插入第 4 段 `[0-9a-f]{4}-`)。② `docs/dev_tasks.md` 本行 `[/]` 改为 `[x]`,同时本「指挥官二次验收」段保留(不擦除)。③ 闸门:`cd frontend && npm run lint && npm run typecheck` + Node REPL 复检 `550e8400-e29b-41d4-a716-446655440000` 必须 `true`。④ 单一原子 commit:`fix(admin): T-1006 复议 — UUID_REGEX 补回缺失第 4 段 [0-9a-f]{4}-`,2 文件改动(`departments/page.tsx` + `dev_tasks.md`)。**严禁**改其他文件,**严禁**改 `mapDepartmentError` / Modal 行为 / 任何其他逻辑,**严禁** `git push`。完工后停手汇报「T-1006 复议完工,等待指挥官三次验收 + T-1008 起草」。
  - **指挥官三次验收(`[2026-05-28 09:07:30]`)**:✅ **PASS — 19/19 全通过**。Codex `d169039 fix(admin): T-1006 复议 — UUID_REGEX 补回缺失第 4 段 [0-9a-f]{4}-` 单一原子 commit 完美闭环。**改动面 100% 精准**:`git diff d169039^..d169039 --stat` = 2 文件 +2 -2(`docs/dev_tasks.md` Task 6 `[/]` → `[x]` + `frontend/src/app/admin/departments/page.tsx` L17 regex 插入 `[0-9a-f]{4}-` 第 4 段),零夹带、零顺手优化。**L17 复检**:`grep -n "UUID_REGEX" frontend/src/app/admin/departments/page.tsx` 输出 `17:const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i`(5 段对齐契约 §3.4 + §9 #13 签字字面量)。**Node REPL 三向**:合法 UUID `550e8400-e29b-41d4-a716-446655440000` → `true` ✅;垃圾串 `not-a-uuid` → `false` ✅;空串 `''` → `false`(双保险:L128 已用 `trimmedManager && !UUID_REGEX.test()` 短路)。**闸门全绿**:`cd frontend && npm run lint`(eslint 零输出)+ `npm run typecheck`(tsc --noEmit 零 error)。**严禁项 100% 遵守**:未改 `mapDepartmentError` / Modal / 表格 / 其他逻辑 / `api/admin.ts` / `dashboard/page.tsx` / `sidebar.tsx` / backend / 测试 / 4 既定 untracked / 📣 锚点;无 `git push`;无 T-1008 自启;commit 是叠加而非 revert。**commit message body** Codex 已在 fix commit 中补充了修复说明(对比 72111e2/e62279b 极简风格已收紧,审计可读性升级 — 减分项已修复)。**Phase 10 全功能闭环达成**:T-1001 ~ T-1007 全部 `[x]`,只剩 T-1008(文档收尾)— 指挥官立即起草。

- [x] **Task 7 (T-1007): 后端测试 `test_phase10_dept_group.py`** — Done by Codex(`[2026-05-27 21:27:47]`)
  - **新建** `backend/tests/test_phase10_dept_group.py`(~380 行,~19 个 `async def test_*` case)。
  - **覆盖**:Model 层 3 case(ProjectMember partial UNIQUE `(project_id, user_id) WHERE left_at IS NULL` + `left_at` 非空允许重复 + Department.name UNIQUE) + Service 层 5 case(`get_department_with_members` 反查活跃用户 + 空部门返回 `[]` + `group_reports_by_department` 4 指标聚合精确 + `group_reports_by_project` inner join 剔除 NULL project_id + `_validate_date_range` start>end 抛 `ValueError("date_range_invalid")`) + Router 层 10 case(T-1004 5 端点 admin/manager/employee RBAC + name_conflict 409 + manager_not_found 400 + T-1005 admin/manager 200 + employee 403 + `?group_by=invalid` 422 + `start_date>end_date` 400 detail 字面量)。
  - **fixtures**:消费 `conftest.py` 已有 `db_session(auto-rollback) + client(dependency_overrides)`,**不**新建 fixture。私有 helpers 6 个(`_cleanup_phase10_test_data / _make_user / _headers / _make_department / _make_project / _make_daily_report`)。每 case 入口**强制** `await _cleanup_phase10_test_data(db_session)`。
  - **改** `docs/dev_tasks.md`(Task 7 → `[x]`,与最后一个 commit 一起 add)。**不动** 📣 锚点(留给指挥官在起草 T-1006 / T-1008 时统一替换)。
  - **完整执行契约见 `docs/T-1007_spec.md`**(必读)。
  - **指挥官二次验收(`[2026-05-27 21:32:50]`)**:✅ PASS。§8 验收清单 **19/19 全通过**:① commit 链路 `bb18476 → 359c1e8 → 5b6b01f` 干净 ② feat 仅 1 文件新建 420 行(契约预估 ~380 +10% 内合理) ③ chore 仅 `dev_tasks.md` +1/-1 ④ **18/18 case 命名 100% 对齐契约**(grep 校验通过) ⑤ 6/6 helpers `_cleanup_phase10_test_data / _make_user / _headers / _make_department / _make_project / _make_daily_report` 完整 ⑥ **零 mock/skip/print/logger/monkeypatch**(grep 严禁项校验 0 hit) ⑦ `ruff check .` All passed ⑧ `mypy tests/test_phase10_dept_group.py` 0 error ⑨ **pytest 新文件 18/18 passed in 7.29s** ⑩ **pytest 全量 178 passed, 2 skipped**(从 T-1005 的 160 准确 +18 case,**零回归**) ⑪ `alembic check` No new upgrade operations(head 仍 `b58bb129c24b`) ⑫ 前端 `npm run lint && npm run typecheck` 全干净(零改动应清白) ⑬ `git diff 5b6b01f..HEAD -- backend/app/ backend/alembic/ frontend/ docs/T-1007_spec.md` 完全空(零夹带验证) ⑭ Worker timestamp 双 commit 均带(`21:27:12` / `21:28:26`) ⑮ 📣 锚点保留 T-1007 持牌(留给指挥官替换) ⑯ 4 既定 untracked 保留未污染 ⑰ `_cleanup_phase10_test_data` 入口存在(L48,作用域至 wechat_userid like "phase10_%") ⑱ Task 7 = `[x] Done by Codex` ⑲ 测试目录零 `.pyc / __pycache__` 夹带。**Phase 10 后端契约护栏闭环完成**,Codex 此次质量稳定连续两轮(T-1005 + T-1007)零小冗余、零踩雷。

- [x] **Task 8 (T-1008): 文档收尾** — Done by Codex(`[2026-05-28 09:48:24]`),**指挥官二次验收通过** `[2026-05-28 09:53:30]`
  - 在 `docs/implementation-plan.md §10` 末尾再追加「实际落地路径(Phase 10 实施)」段,记录 6 列对照表对应维度从 ❌ → ✅ 的变化与最终对外路径。
  - 更新 `docs/recap.md`「当前阶段」→ Phase 11 候选,新增 Phase 10 全 task bullet + 历史移交记录条目。
  - **完整执行契约见 `docs/T-1008_spec.md`**(必读,~530 行 10 章 + 📣 附录)。
  - **指挥官二次验收(`[2026-05-28 09:53:30]`)**:✅ **PASS — 17/17 全通过**。**改动面 100% 精准**:`5e5ce2b` feat 严格 2 文件(`implementation-plan.md` +36 / `recap.md` +20 -2);`7b4e9fe` chore 严格 1 文件(`dev_tasks.md` +15 -52,锚点段整体替换)。① commit 链路 `1746309 → 5e5ce2b → 7b4e9fe` 干净 ② feat 严格 2 文件无第三文件夹带 ③ chore 严格 1 文件 ④ **implementation-plan.md 纯追加**(`git diff 5e5ce2b^..5e5ce2b -- docs/implementation-plan.md | grep "^-[^-]" | wc -l` = 0,零删除行) ⑤ §10 实施段头部在 L819(`grep "^### 实际落地路径(Phase 10 实施)"` 1 hit) ⑥ 6 维度对照表完整(部门表 / 部门字段 / 项目成员关联 / 项目路由 / 部门分组端点 / 前端 Tabs 切换器) ⑦ **6 commit 短哈希 100% 在位**:`ad6643a` ×2(T-1003 部门表 + 部门字段双轨)、`6e2b94a` ×1、`d8737d9` ×1、`02f3d58` ×2(T-1005 项目路由 + 部门分组端点)、`72111e2` ×1、`d169039` ×1 ⑧ 实际对外 API 路径表 6 行(5 端点 departments + 1 行 reports) ⑨ 前端落地路径表 3 行(`/admin/departments` 页 + `/dashboard` Tabs + sidebar 入口) ⑩ Phase 11 候选 4 项全到位(① FK 迁移 / ② 物化视图增量 / ③ 加权柱状图 / ④ KPI scope 打通) ⑪ recap.md L4 替换为 Phase 10 Task 1~8 八行结构化摘要(L4-11) ⑫ recap.md L6 → L13 替换为 `Phase 11 候选(Phase 10 已闭环,T-1001 ~ T-1008 八任务全收口)` ⑬ recap.md 历史移交记录 L32-40 插入 9 行(1 Commander 闭环 + 8 task entries 倒序,2026-05-28 在最上 — 注:spec §3.2.3 字面量 9 行 / §8 #13 文案"8 行"为微小自洽差异,Codex 正确选择字面量优先,**加分**) ⑭ dev_tasks.md Task 8 L168 `[ ]` → `[x]` ⑮ dev_tasks.md L195+ 📣 锚点整体替换为「当前无持牌任务,等待指挥官 Phase 11 发牌」终态字面量,Phase 11 候选 4 项 + 严禁项 4 项 + 时间戳纪律全口径在位 ⑯ Worker timestamp 双 commit 均带(grep `Worker timestamp` 各 1 hit) ⑰ 4 既定 untracked 保留未污染。**亮点**:Codex 在 📣 锚点中实际填入完工时间戳 `[2026-05-28 09:48:24]` 替换 spec placeholder「待 Worker 填实际完工时间戳」,精准执行 spec 意图;两条 commit message 均含 multi-line body(对比 T-1005/T-1007 风格收紧审计可读性);spec §3.2.3 字面量 9 行 vs §8 #13 文案"8 行"的自洽差异 Codex 正确按字面量优先执行(9 行实际落地)。**减分**:无。**Phase 10 八任务(T-1001~T-1008)全数闭环 ✅**,代码 / 测试 / 文档三轴全收口,等待指挥官启动 Phase 11 规划。

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

# Phase 11: 测试基线回归修复(远程 fix 后)

## 当前状态与上下文

- Phase 10 已 100% 闭环并 push origin/main(全 34 commit 已合并)。
- 后续 push 引入 2 条破坏性 fix(由 ericdv111 在 12:54 + 13:34):
  - `b5e77c3 fix: harden security and deployment readiness` — RBAC middleware 加 `must_change_password` 强制改密检查(`backend/app/middleware/rbac.py` `get_current_user` 拒绝 `must_change_password=True` 的 user 访问非 `/auth/me` 或 `/auth/change-password` 路径)。
  - `8459a5b fix: tighten tenant scope and report idempotency` — `department_service` + `admin_reports_service` 删除 `TENANT_ID = "default"` 常量,改由 router 从 `actor.tenant_id` 注入(`list_departments / delete_department / get_department_with_members` 加 `*, tenant_id: str` keyword-only;`group_reports_by_department / group_reports_by_project` 加 `tenant_id: str` 位置参数)。
- 后端 pytest 出现 **26 failures**(从 Phase 10 收口 `178 passed` 退化到 `152 passed`,2 skipped):
  - 12 in `test_phase10_dept_group.py`(混合 Type A signature + Type B RBAC 403)
  - 8 in `test_kpi_phase9.py`(Type B RBAC 403)
  - 1 in `test_me_deletions.py`(Type B RBAC 403)
  - 5 散落其他(原因同 Type A/B)
- 工作树干净,4 既定 untracked + 项目级 ECC symlinks(`.claude/skills/` 16 个 + `.gitignore` 已排除,见 `c9693a9 chore: ignore .claude/`)。
- 当前 alembic head:`9a1b2c3d4e5f`(`20260528_1000_security_readiness_constraints.py`,由 `b5e77c3` 加)。
- ⚠️ **本机验证风险**(`backend/.env` 漂移):`backend/.env` 已被 `.gitignore` 忽略(个人本机配置)。若缺 `JWT_SECRET_KEY`(`backend/app/config.py:112` 无默认值,pydantic 必填),本机 `pytest collection`(`conftest.py:19 from app.config import settings`)与 `uvicorn app.main:app` 都会 hard fail。Worker 在本机跑 T-1101 闸门前需先确认 `backend/.env` 含 `JWT_SECRET_KEY`(否则除 26 failures 还会叠加 ImportError),且 `.env` 变量名需与 `config.py` 对齐(`AIPM_ENV` / `SMTP_SERVER` / `WECHAT_CORP_ID` / `DINGTALK_APP_KEY` / `NEW_API_*` 等;`extra="ignore"` 会让旧名 silent miss)。**仓库层面修复待 T-1102**(Option α:改 `backend/.env.example` + README/DEPLOY 启动检查清单 + `config.py` 友好错误提示;**严禁 Agent 直接改 `backend/.env`**)。

## 任务看板

### 测试回归修复 (Test Baseline Restoration)
- [x] **Task 1 (T-1101): 修复 26 个 test failure(`tenant_id` 签名 + `must_change_password` RBAC)** — **Done by Codex `[2026-05-28 16:47:55]`**
  - **实改** `backend/tests/test_phase10_dept_group.py`:`_make_user` helper 加 `must_change_password=False` + 全部实际 service call 加 `tenant_id=TENANT_ID` 关键字参数(`get_department_with_members / group_reports_by_department / group_reports_by_project`)。
  - **实改** `backend/tests/test_kpi_phase9.py`:`_make_user` helper 加 `must_change_password=False` + 3 处 KPI service call 补 `tenant_id="default"`。
  - **实改** `backend/tests/test_me_deletions.py`:inline `User(...)` 加 `must_change_password=False`。
  - **Supervisor 特批扩展白名单** `backend/tests/test_analytics.py` + `backend/tests/test_export_phase8.py`:各自 `_make_user` helper 加 `must_change_password=False`,修复剩余 4 个 RBAC 403。
  - **pytest-only closure(`[2026-05-28 16:47:55]`)**:清空本机 `aipm_db_test` 表数据 + 进程级清空通知渠道 env 后,`pytest -q` 实测 **`178 passed, 2 skipped`**。全局 `ruff/mypy/alembic check` 的现存 src/local DB drift blocker 经 Supervisor 授权跳过,不纳入 T-1101。
  - **不**改 `backend/app/` 任何 src 代码(远程 fix 是有意改动)。
  - **不**改 `backend/alembic/`、`backend/conftest.py`、`backend/pyproject.toml`、`backend/requirements.txt`。
  - **不**改 T-1101 修复面以外的其他 `tests/test_*.py` 文件。
  - **完整执行契约见 `docs/T-1101_spec.md`**(必读,~450 行 10 章 + 📣 附录)。
  - **指挥官二次验收(`[2026-05-28 16:03:00]`)**:✅ **PASS — 接受 Codex pytest-only closure**(Worker timestamp `[2026-05-28 16:47:22]`)。Codex 双 commit `1c67bd4 fix(tests) → 19ac08e chore(progress)` 改动 5 个 test files(spec §2 原白名单 3 文件 + Supervisor 特批扩展 `test_analytics.py` + `test_export_phase8.py`),Codex 环境实测 178 passed + 2 skipped。**指挥官本机抽样验证**(`[2026-05-28 16:03]`):`JWT_SECRET_KEY` inline 注入跑 `pytest -q --tb=no` 实测 **177 passed + 1 failed + 2 skipped**;唯一 failed 是 `test_notifications.py::test_notify_unconfigured_channels_skipped`(Codex closure 明确说明需要"进程级清空通知渠道 env",属环境依赖非测试代码 bug,**留作 T-1102 议题 A 测试隔离污染下沉**)。**注**:指挥官 16:00 之前误判 T-1101 为"自然解决"(基于本机 6 failures baseline),实际 Codex 在它环境跑到 26 failures 并真做 fix Edit,**判断错误已纠正,Codex 工作完整有效,不撤回 1c67bd4 / 19ac08e**。**Phase 11 首任 Task 闭环**,T-1102 候选议题待指挥官起草 spec。

### 测试隔离污染 + 配置漂移 (Test Isolation & Config Drift) — T-1102 候选 backlog
- [x] **Task 2 (T-1102): 测试隔离污染 + 配置漂移仓库层面修复(议题 A + B + C 三合一)** — Done by Codex [2026-05-28 18:05:00]
  - **议题 A — `test_notifications.py` 测试自治**(T-1101 closure 后剩余,`[2026-05-28 16:03]` 指挥官实测):全套 `pytest -q` 跑出 **1 failed / 177 passed / 2 skipped**(`test_notifications.py::test_notify_unconfigured_channels_skipped` 在 Codex env-cleanup 前是 6 failures 之一,Codex 通过"进程级清空通知渠道 env"绕过,但**测试本身仍依赖外部环境而非 isolation 自治**)。修复路径:加 `_clean_notification_settings(monkeypatch)` autouse fixture,主动清空 13 项通道 settings(wechat 5 + dingtalk 5 + smtp 4),让测试**完全不依赖跑测试者本机 .env 状态**。
  - **议题 B — `backend/.env.example` 兼容别名注释 + `README.md` 最小必填 env 清单**:
    - `.env.example` 在 4 处章节头(WECHAT / DINGTALK / NEW_API / SMTP)加 `# 兼容别名(config.py AliasChoices):XXX` 注释行(L66 OSS 已有兼容别名注释,保留不动)。
    - `README.md`「开发环境启动」Step 1 之后插入 7 行最小必填项清单(`JWT_SECRET_KEY` + `DATABASE_URL` + `REDIS_URL` + `AIPM_ENV` + `POSTGRES_PASSWORD`,其余字段缺失时优雅降级)。
    - **不**改 `backend/app/config.py`(pydantic 必填 + AliasChoices 已生效,过度封装风险高)。
    - **不**改 `DEPLOY.md`(它是生产部署清单,本任务只面向本地开发)。
  - **议题 C — `conftest.py:25` + `test_notifications.py:93` 双处硬编码 `replace("/aipm_db", "/aipm_db_test")` 隐患升级为 T-1102 主线**:**红线风险** — DB 名非 `aipm_db` 时(如 `qiaocai` / 用户自定义)replace 不命中,`TEST_DATABASE_URL` = 生产 URL,`Base.metadata.drop_all` 会**清生产表**。修复路径:抽 helper `derive_test_database_url(source_url, suffix="_test")` 到新建 `backend/tests/_db_url.py`(~50 行),用 `sqlalchemy.engine.url.make_url` 精确替换 `database` 字段 + production-同名防御性 assert;`conftest.py` + `test_notifications.py` 双调用点同步切换。
  - **不**改 `backend/.env`(个人本机配置,**严禁 Agent 直接改**)。
  - **不**改 `backend/app/`、`backend/alembic/`、`frontend/`、`DEPLOY.md` 任何文件。
  - **完整执行契约见 `docs/T-1102_spec.md`**(必读,~620 行 10 章 + 📣 附录)。
  - **指挥官二次验收(`[2026-05-28 17:45:00]`)**:✅ **PASS — 22/22 验收清单全通过**。Codex 双 commit `ddc41ba` fix + `9f6ab11` chore 完美闭环。**改动面 100% 精准**:6 文件改动(`backend/tests/_db_url.py` 新建 ~46 行 + `__init__.py` 新建空文件 + `conftest.py` + `test_notifications.py` + `.env.example` +4 / `README.md` +8),零 src / 零 alembic / 零 frontend / 零 DEPLOY.md / 零 backend/.env。**议题 A 实测**:`pytest tests/test_notifications.py::test_notify_unconfigured_channels_skipped -v` = **1 passed in 0.71s**(本机原 1 failed → 修复后 1 passed)。**议题 B 字面量**:`.env.example` 4 处兼容别名注释命中(WECOM / DINGTALK / LITELLM / MAIL),`README.md` 最小必填项清单 + 5 项 env 名全到位,零删除。**议题 C 红线根除**:`derive_test_database_url` helper 4 用例全 PASS(aipm_db / qiaocai / query string / 空 db RuntimeError),防御性 assert 实际生效。**全套 pytest**:`178 passed, 2 skipped in 42.89s`,从 T-1101 完工基线零回归。**ruff + mypy** 3 文件全绿;`alembic check` FAIL 是 T-1101 已知 local DB drift,Supervisor 签字跳过(spec §6 严禁项无相关红线)。**减分**:① chore commit body 偏简(仅 Worker timestamp 1 行,无完工概要 — 审计可读性扣分,非 BLOCKER);② Codex 选 spec §3.6.2「整体替换」而非 §10 #8「末尾追加保留」清理 📣 锚点 — spec 内部矛盾(指挥官签字),不归因于 Codex。**亮点**:Codex 完美对齐 §3.3.2 字面量(autouse=True + 13 项 setattr 顺序锁定:wechat 4 + dingtalk 5 + smtp 4)+ 严格 §3.5 README.md L33-38 7 行最小必填项 + 严格 §3.4.1 .env.example 4 处兼容别名注释 + 严格 §3.2.2 条件分支正确探针 `__init__.py` 不存在 → 新建空文件。

### 测试隔离彻底化 + T-1102 议题 C 残留收口
- [/] **Task 3 (T-1103): 测试隔离 fixture 全局化 + T-1102 议题 C 残留 11 处 `.replace` 硬编码收口** — In Progress by Codex `[2026-05-28 18:25:08]`(指挥官契约起草中)
  - **议题 A — 测试隔离 fixture 全局化**:T-1102 议题 A 只修了 `test_notifications.py` 一个文件,其余 10 个引用 settings 的 test file 仍依赖跑测试者本机 `.env`。修复路径:新建 `backend/tests/_isolation.py`(~80 行,`clean_external_settings(monkeypatch)` helper,清空 **28 项**外部敏感 settings = wechat 6 + dingtalk 5 + smtp 4 + new_api 2 + xunfei 3 + oss 5 + erp 1 + sentry 2),在 `conftest.py` 加全局 `@pytest.fixture(autouse=True)` `_isolation_external_settings` fixture 调用 helper。**移除** `test_notifications.py:111-134` `_clean_notification_settings` fixture(T-1102 版本,共 24 行),由 conftest.py 全局 fixture 替代(去重,单一真理源)。
  - **议题 B — T-1102 议题 C 残留 11 处统一收口**(🚨 T-1102 spec 起草盲点):全仓 grep `replace.*aipm_db.*aipm_db_test` 命中 **13 处**,T-1102 只修了 2 处(conftest.py + test_notifications.py),其余 **11 处**(`test_okr.py` / `test_daily_report_relations.py` / `test_analytics.py` / `test_sprints.py` / `test_retro.py` / `test_capacity.py` / `test_kpi_phase9.py` / `test_phase10_dept_group.py` / `test_attachments.py` / `test_chat_tools.py` / `test_me_deletions.py`)继承同源**红线风险**(DB 名非 `aipm_db` 时 `drop_all` 清生产库)。修复路径:每文件 2 行变更 — ① import `from tests._db_url import derive_test_database_url` + ② 替换 `.replace(...)` 为 `derive_test_database_url(settings.database_url)`,**逐文件 Read + 精确 Edit**,**严禁** sed 一刀切。同步更新 `_db_url.py` docstring L4-7 从「双处」改为「双处 + T-1103 扩展为全仓 13 处」。
  - **不**改 `backend/app/`、`backend/alembic/`、`frontend/`、`DEPLOY.md`、`backend/.env`、`backend/.env.example`、`README.md` 任何文件(T-1102 已闭环的配置漂移议题不重做)。
  - **完整执行契约见 `docs/T-1103_spec.md`**(必读,~620 行 10 章 + 📣 附录)。

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌,供 PM 探针自动提取**
> **更新时间戳**: `[2026-05-28 18:25:08]`(指挥官 T-1103 契约起草完成 — Phase 11 第三任 Task 测试隔离彻底化 + T-1102 议题 C 残留收口发牌)

- **当前持牌任务**: **T-1103**(Phase 11 **第三任** — 测试隔离 fixture 全局化 + T-1102 议题 C 残留 11 处统一收口,**零业务 src 改动**)—— ① **议题 A**:把 T-1102 议题 A 的 `_clean_notification_settings` 模式从单文件推广为 `conftest.py` 全局 autouse fixture(28 项外部 settings 锁定);② **议题 B(🚨 T-1102 spec 起草盲点)**:11 处其他 test file 的 `.replace("/aipm_db", "/aipm_db_test")` 硬编码统一切换为 `derive_test_database_url`,根除全仓红线风险。

- **执行入口**: **必须读完整** `docs/T-1103_spec.md`(本契约 ~620 行 10 章 + 📣 附录)。**必须**在改动前跑前置探针(`git status --short --branch` / `git log -3 --oneline` / `git diff` / `git diff --cached`),核验 HEAD = `chore(spec): T-1103 契约起草` commit 之后,工作树干净(`dev_tasks.md` Task 3 已被指挥官加锁 `[/]`),4 既定 untracked + `.claude/` 保留。

- **核心动作**(2 commit / 16 文件 = 1 helper 新建 + 1 helper docstring 同步 + 1 conftest.py + 1 test_notifications 去重 + 11 test_*.py 切换 + 1 dev_tasks.md):

  **Commit 1 (fix)** — `fix(tests): T-1103 testsuite-wide isolation hardening — global _isolation_external_settings autouse fixture + 11 derive_test_database_url cutovers`:

  **议题 A 主修复**(优先做,后续依赖 helper 存在):
  1. **新建** `backend/tests/_isolation.py`(spec §3.1 完整字面量,~80 行,**28 项**字段顺序锁定:wechat 6 + dingtalk 5 + smtp 4 + new_api 2 + xunfei 3 + oss 5 + erp 1 + sentry 2,延迟 import `app.config.settings` 防循环依赖)。
  2. **改** `backend/tests/conftest.py`:
     - 在 `from tests._db_url import derive_test_database_url`(T-1102 已加)之后插入 `from tests._isolation import clean_external_settings`(spec §3.2.1)。
     - 在 `setup_test_db` fixture 体结束之后(`await test_engine.dispose()` 后)/ `db_session` fixture 之前,插入 `_isolation_external_settings(monkeypatch)` autouse fixture(spec §3.2.1 完整字面量,function scope,**不**用 `@pytest_asyncio.fixture`)。
  3. **改** `backend/tests/test_notifications.py`:**整段删除** L111-134 共 **24 行** `_clean_notification_settings` fixture(spec §3.3.1)。保留 L109 `await engine.dispose()` + L135 空行 + L136 `@pytest.mark.asyncio` 不动。

  **议题 B 主修复**:
  4. **改** `backend/tests/_db_url.py`:更新 L4-7 docstring 4 行 → 5 行(spec §3.4 字面量,纯注释同步,**零功能改动**)。
  5. **改** 11 处 test file(spec §3.5 表 #1~#11),每文件 **逐文件 Read + 精确 Edit**,严禁 sed:
     - `test_okr.py`(L33) / `test_daily_report_relations.py`(L34) / `test_analytics.py`(L23) / `test_sprints.py`(L42) / `test_retro.py`(L34) / `test_capacity.py`(L43) / `test_kpi_phase9.py`(L31) / `test_phase10_dept_group.py`(L44) / `test_attachments.py`(L32) / `test_chat_tools.py`(L27) / `test_me_deletions.py`(L21)
     - 每文件 2 行变更:① 在 `from app.config import settings` 之后插入 `from tests._db_url import derive_test_database_url`;② 替换 `TEST_DATABASE_URL = settings.database_url.replace("/aipm_db", "/aipm_db_test")` 为 `TEST_DATABASE_URL = derive_test_database_url(settings.database_url)`。

  **Commit 2 (chore)** — `chore(progress): close T-1103 — Phase 11 测试隔离全局化 + 议题 C 残留 11 处收口`:
  6. **改** `docs/dev_tasks.md`:Phase 11 Task 3 (T-1103) `[/]` → `[x]` + ` — Done by Codex [YYYY-MM-DD HH:MM:SS]`;**保留**子 bullet 全部不动;在 📣 锚点段重写为「Phase 11 T-1103 完工,当前无持牌任务」终态文字(参考 T-1102 chore commit 风格,**但 commit body 不要极简一行**,必须含完工概要 + 文件清单)。

- **严禁项**(违反立即驳回,详见 spec §6 完整 28 项):
  - **严禁**改 `backend/app/` / `backend/alembic/` / `frontend/` 任何文件。
  - **严禁**改 `DEPLOY.md` / `README.md` / `backend/.env` / `backend/.env.example`(T-1102 已闭环议题,不重做)。
  - **严禁**改 11 处之外的 test file(`test_distributed_lock.py` / `test_e2e_ipd.py` / `test_export_phase8.py` / `test_models_init.py` / `test_simulate_reports.py` / `test_deletion_cleanup.py` / `test_deletion_history.py` 无 `.replace` 硬编码,不动)。
  - **严禁**篡改 `_EXTERNAL_SETTINGS_FIELDS` 28 项(加 `database_url` 等核心字段会破坏 fixture / test 自身;减项会覆盖不全)。
  - **严禁** sed / awk / 一刀切批量 replace 11 处(必须 Read + 精确 Edit 每处)。
  - **严禁**在 11 处某文件没加 import(只替换 .replace 那行,会引发 NameError)。
  - **严禁** `_isolation.py` 顶部 import `app.config`(必须延迟 import 防循环依赖)。
  - **严禁**保留 test_notifications.py:111-134 `_clean_notification_settings` fixture(必须去重,单一真理源)。
  - **严禁** `git push`(留给指挥官决策推送时机)。
  - **严禁**自启 T-1104 / Phase 11 后续任务。
  - **严禁** revert `8459a5b` / `b5e77c3` / `c9693a9` / `1c67bd4` / `19ac08e` / `8d69ca8` / `ddc41ba` / `9f6ab11` 任何已落地 commit。
  - **严禁**在 feat / chore commit 之外打额外提交(`chore(lock)` 已由指挥官代办)。
  - **严禁**在两条 commit message 中遗漏 `Worker timestamp:` 行 或 写极简一行 commit message(T-1102 chore 已记一分,本任务必须含完工概要 + 文件清单)。
  - **严禁**改 dev_tasks.md Task 1 / Task 2 历史 `[x]` 状态或验收回执(历史已闭环,不动)。

- **闸门**(全绿才提交,详见 spec §5):
  ```bash
  cd backend
  .venv/bin/ruff check tests/
  .venv/bin/mypy tests/_isolation.py tests/conftest.py
  .venv/bin/pytest -q   # 0 failed, 178 passed, 2 skipped(从 T-1102 完工基线零回归)

  # 议题 A 抽样
  .venv/bin/pytest -q tests/test_asr.py -v
  .venv/bin/pytest -q tests/test_notifications.py -v

  # alembic check 跳过(T-1101 已知 local DB drift)
  ```

  **议题 B 全仓零残留闸门**(关键):
  ```bash
  cd ..
  grep -rn 'replace.*aipm_db.*aipm_db_test' backend/tests/ --include='*.py' | grep -v '_db_url.py'   # 必须 0 hit
  ```

  改动面校验:
  ```bash
  git diff <fix-sha>^..<fix-sha> --name-only | sort   # 严格 15 文件
  git diff <fix-sha>^..<fix-sha> -- backend/app/ backend/alembic/ frontend/ DEPLOY.md README.md backend/.env backend/.env.example   # 必须空
  ```

- **完工提交序列**(2 commit,顺序锁定):
  1. `fix(tests): T-1103 testsuite-wide isolation hardening — global _isolation_external_settings autouse fixture + 11 derive_test_database_url cutovers` —— **15 文件**(`_isolation.py` 新建 + `_db_url.py` docstring + `conftest.py` + `test_notifications.py` + 11 处其他 test file)。
  2. `chore(progress): close T-1103 — Phase 11 测试隔离全局化 + 议题 C 残留 11 处收口` —— **1 文件**(`dev_tasks.md`)。

  两条 commit message 都**必须**包含 multi-line body(参考 T-1101/T-1005/T-1008 风格,**特别**:chore commit body 必须含完工概要 + 文件清单 — T-1102 chore 极简已减一分,本任务收紧)+ 末尾 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 行。

- **时间戳纪律**: 所有 commit message 末尾、终端汇报、任何写入 `dev_tasks.md` 的段落必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。

- **完工后**: 立即停手汇报「T-1103 完工,议题 A 全局 fixture + 议题 B 11 处统一收口,pytest 178 passed + 2 skipped 零回归。等待指挥官二次验收 + Phase 11 后续 task 起草」。**绝对不要**自启 T-1104。**绝对不要** `git push`。
