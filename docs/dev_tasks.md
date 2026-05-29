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
- [x] **Task 3 (T-1103): 测试隔离 fixture 全局化 + T-1102 议题 C 残留 11 处 `.replace` 硬编码收口** — Done by Codex `[2026-05-28 18:43:06]`
  - **议题 A — 测试隔离 fixture 全局化**:T-1102 议题 A 只修了 `test_notifications.py` 一个文件,其余 10 个引用 settings 的 test file 仍依赖跑测试者本机 `.env`。修复路径:新建 `backend/tests/_isolation.py`(~80 行,`clean_external_settings(monkeypatch)` helper,清空 **28 项**外部敏感 settings = wechat 6 + dingtalk 5 + smtp 4 + new_api 2 + xunfei 3 + oss 5 + erp 1 + sentry 2),在 `conftest.py` 加全局 `@pytest.fixture(autouse=True)` `_isolation_external_settings` fixture 调用 helper。**移除** `test_notifications.py:111-134` `_clean_notification_settings` fixture(T-1102 版本,共 24 行),由 conftest.py 全局 fixture 替代(去重,单一真理源)。
  - **议题 B — T-1102 议题 C 残留 11 处统一收口**(🚨 T-1102 spec 起草盲点):全仓 grep `replace.*aipm_db.*aipm_db_test` 命中 **13 处**,T-1102 只修了 2 处(conftest.py + test_notifications.py),其余 **11 处**(`test_okr.py` / `test_daily_report_relations.py` / `test_analytics.py` / `test_sprints.py` / `test_retro.py` / `test_capacity.py` / `test_kpi_phase9.py` / `test_phase10_dept_group.py` / `test_attachments.py` / `test_chat_tools.py` / `test_me_deletions.py`)继承同源**红线风险**(DB 名非 `aipm_db` 时 `drop_all` 清生产库)。修复路径:每文件 2 行变更 — ① import `from tests._db_url import derive_test_database_url` + ② 替换 `.replace(...)` 为 `derive_test_database_url(settings.database_url)`,**逐文件 Read + 精确 Edit**,**严禁** sed 一刀切。同步更新 `_db_url.py` docstring L4-7 从「双处」改为「双处 + T-1103 扩展为全仓 13 处」。
  - **不**改 `backend/app/`、`backend/alembic/`、`frontend/`、`DEPLOY.md`、`backend/.env`、`backend/.env.example`、`README.md` 任何文件(T-1102 已闭环的配置漂移议题不重做)。
  - **完整执行契约见 `docs/T-1103_spec.md`**(必读,~620 行 10 章 + 📣 附录)。
  - **指挥官二次验收(`[2026-05-28 18:35:00]`)**:✅ **PASS — 28/28 验收清单全通过(零减分)**。Codex 双 commit `e343db3` fix + `045533d` chore 完美闭环。**改动面 100% 精准**:fix commit 严格 **15 文件**(`backend/tests/_isolation.py` +86 行新建 / `_db_url.py` docstring +6 -X / `conftest.py` +14 / `test_notifications.py` -26 去重 / 11 处 test file 各 +3 -1),chore commit 严格 1 文件(`dev_tasks.md`),零 src / 零 alembic / 零 frontend / 零 DEPLOY.md / 零 README.md / 零 backend/.env / 零 .env.example。**议题 A 实测**:`_isolation.py` 28 项字段精准对齐 spec(wechat 6 + dingtalk 5 + smtp 4 + new_api 2 + xunfei 3 + oss 5 + erp 1 + sentry 2 = 28)+ 8 类别注释全到位 + `from app.config import settings` L83 延迟 import(防循环依赖正确)+ conftest.py L75-76 autouse fixture 入位 + `test_notifications.py::_clean_notification_settings` 0 hit(完美去重)。**议题 B 红线根除**:11 处 test file 逐文件 `import=1, cutover=1, orig=0` 完美(test_okr / test_daily_report_relations / test_analytics / test_sprints / test_retro / test_capacity / test_kpi_phase9 / test_phase10_dept_group / test_attachments / test_chat_tools / test_me_deletions),**全仓零残留闸门** `grep -rn 'replace.*aipm_db.*aipm_db_test' backend/tests/ \| grep -v _db_url.py \| wc -l` = **0**(议题 B 全仓收口)。**闸门**:`ruff check tests/` All passed / `mypy` 2 文件 0 error / **`pytest -q` 178 passed + 2 skipped in 50.37s 零回归** / `test_asr.py 11 passed`(议题 A monkeypatch later wins 机制不破坏 33 case)/ `test_notifications.py 8 passed`(去重后 isolation 由 conftest.py autouse 提供仍生效)。**Worker timestamp** 双 commit 均带(feat `[2026-05-28 18:42:36]` / chore `[2026-05-28 18:43:06]`)。**亮点 4 项**:① **chore commit body 大幅改进**(T-1102 chore 仅 1 行 Worker timestamp 减分 → T-1103 chore **11 行 body** 含完工概要 + 文件清单 + 验证结果 + 严禁项遵守证据,审计可读性收紧);② **议题 A monkeypatch 顺序覆盖兼容**(test_asr.py 33 case 全 PASS,证明 autouse fixture 不破坏现有 setattr later wins 机制);③ **议题 B 红线 100% 根除**(T-1102 spec 起草盲点 11 处遗漏 → T-1103 全仓收口,无论 DB 名是 `aipm_db / qiaocai / 自定义` 都安全派生 test 库);④ **零 src 防线**(15 文件全在 test / docs,backend/app + alembic + frontend + DEPLOY.md + README.md + backend/.env + .env.example 全冻结)。**减分**:无。**Phase 11 三任 Task(T-1101 ~ T-1103)全闭环 ✅**,等待指挥官启动 T-1104 / Phase 12 规划。

### 外键迁移(议题 ① · 3 任务渐进 T-1104 → T-1105 → T-1106)
- [x] **Task 4 (T-1104): `User.department` → `Department.id` FK 双轨迁移 第一阶段(Migration + Model + Resolver helper + `department_service.get_department_with_members` 接入)** — Done by Codex `[2026-05-29 10:59:02]`
  - **新建** `backend/alembic/versions/20260529_HHMM_phase11_user_department_id_fk.py`(~80 行)— `users.department_id UUID FK→departments.id ON DELETE SET NULL nullable=True` + `fk_users_department_id_departments` 约束 + `ix_users_department_id` 索引 + 一次性 backfill(严格 LEFT JOIN unmapped 留 NULL + `[T-1104 backfill]` stdout dry-run 报告)+ downgrade 反向 drop_index → drop_constraint → drop_column 可回滚。`down_revision = "9a1b2c3d4e5f"`(T-1102 head;Codex 接手时 alembic heads 二次核验)。
  - **新建** `backend/app/services/_department_resolver.py`(~65 行)— `resolve_user_department_name(db, user)`(FK 优先 → fallback VARCHAR)+ `resolve_department_id_by_name(db, name)`(T-1105 写路径用)2 公开 async helper,零 HTTPException。
  - **改** `backend/app/models/user.py`(插入式 +5~8 行)— L53 `department: Mapped[str]` 字段**不动**,L54 起插入 `department_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), index=True, nullable=True, ...)`;import 块视需补 `Optional` / `ForeignKey` / `uuid`。**不**加 `relationship("Department", ...)`(留给 T-1105 评估 N+1 风险)。
  - **改** `backend/app/services/department_service.py`(单函数 +5 / -3)— 仅 `get_department_with_members` 内 stmt 改双轨 OR(`or_(department_id == dept.id, and_(department_id IS NULL, department == dept.name))`);**严禁**改 `list_departments / create_department / update_department / delete_department / _map_value_error` 等其他函数。
  - **新建** `backend/tests/test_phase11_dept_fk.py`(~280 行 ~15 case)— Model 3 + Backfill 3 + Resolver 4 + Service 5,消费 `db_session + _isolation_external_settings` autouse fixture(T-1102/1103),`_cleanup_phase11_test_data` 入口必跑,作用域 `wechat_userid like "phase11_%"` + `departments.name like "phase11_%"`,零 mock/skip/print/logger/monkeypatch ORM。
  - **3 任务渐进路径锁定**:T-1104 本任 = Migration + Model + Resolver + 1 处接入(双轨纯增量);T-1105 候选 = 切剩余 36+ 处后端 routers/services 读路径用 Resolver + frontend schemas 扩 `department_id` output + 写路径(`routers/users.py:188` 等 7 处);T-1106 候选 = drop column `User.department VARCHAR(64)` + 删 Resolver fallback 路径。
  - **不**改 `backend/app/routers/`(20 处读路径全留给 T-1105)、`backend/app/services/` 除白名单外(16 处其他 services 读路径全留给 T-1105)、`backend/app/schemas/`(留给 T-1105 扩 output)、`frontend/`(留给 T-1105)、`backend/conftest.py + tests/_isolation.py + tests/_db_url.py`(T-1102/1103 已闭环)、`backend/.env*` / `README.md` / `DEPLOY.md`(T-1102 已闭环)、`backend/pyproject.toml + requirements.txt + uv.lock`。
  - **测试基线**:T-1103 完工 178 passed → T-1104 完工预期 `193 passed + 2 skipped`(新 15 case 全 PASS + 旧 178 case 零回归)。
  - **完整执行契约见 `docs/T-1104_spec.md`**(必读,~600 行 10 章 + 📣 附录;指挥官 `[2026-05-29]` 4 决策签字 — 方案 A 双轨纯增量 / i 严格保留 NULL / SET NULL / 拆 3 任务渐进)。
  - **Codex 完工实绩(`[2026-05-29 10:59:02]`)**:commit `64b45a9 feat(models)` 严格 5 文件闭环。Migration `20260529_1037_phase11_user_department_id_fk.py` 新增 `users.department_id` + FK + index + backfill/downgrade;`User.department` 字符串字段保留;`_department_resolver.py` 暴露 2 个 helper;`get_department_with_members` 改双轨 OR;`test_phase11_dept_fk.py` 新增 15 case。闸门全绿:`ruff check` 4 文件 PASS / `mypy` 3 source PASS / Alembic `upgrade head → downgrade -1 → upgrade head` PASS 且 stdout 命中 `[T-1104 backfill]` / 新测试 `15 passed` / 全量 `193 passed, 2 skipped` / frontend `npm run lint` + `npm run typecheck` PASS。`alembic check` 依 T-1101/T-1102/T-1103 既定 Supervisor 特批跳过(local DB drift 误报)。严禁项遵守:0 router / 0 schema / 0 frontend staged / 0 conftest / 0 `_isolation` / 0 `_db_url` / 0 `.env*` / 0 README / 0 DEPLOY / 0 pyproject / 0 requirements / 0 uv.lock / 0 push / 0 stash / 0 amend / 0 rebase / 0 T-1105 自启。注:ORM `department_id` FK 显式命名为 `fk_users_department_id_departments`,与 migration 对齐,用于拆解 `users ↔ departments` metadata drop 环。
  - **指挥官二次验收回执**:**Codex 工程完工已接受(commit `a532041`),28 项验收清单逐项核对 follow-up 推迟至 T-1105 完工后批量回补**(用户 `[2026-05-29 临时插队]` 指令打断常规验收流转;基线 `a532041` 工程层面 PASS,无 BLOCKER 风险)。

### 立项指派成员(临时插队 · 议题 ① backlog 推后,Phase 11 第五任)
- [/] **Task 5 (T-1105): 立项时一站式指派成员(项目成员批量初始化 + Manager 端 RBAC gap 修复)** — in progress by Codex `[2026-05-29 11:25:12]`
  - **改** `backend/app/schemas/project.py`(+22 行)— 新增 `ProjectMemberInit` 类(`user_id: UUID / track: str / role_in_project: Optional[str]`)+ 扩 `ProjectCreate.members: Optional[list[ProjectMemberInit]] = Field(None, max_length=50, ...)`,默认 None 向后兼容。
  - **改** `backend/app/routers/projects.py`(~+70 行)— imports 块插入 `ProjectMemberInit` + `create_project` 函数在 `db.flush()` 之后、临时项目 if 分支之前插入成员批量插入逻辑(payload dedup + 一次性存在性校验 + 单事务批插)+ 临时/主干分支返回体均扩 `members_added: int`。**严禁**改 `create_project` 外的任何 router 函数(`add_project_member / batch_remove_members / list_project_members / update_project / archive_project / batch_soft_delete_projects / batch_restore_projects / get_deleted_projects / projects_overview` 等 9 函数全部冻结)。
  - **改** `backend/app/routers/users.py`(~+50 行)— 末尾**插入式**新增 `UserPickerItem` Pydantic 类 + `GET /api/v1/users/picker` 端点(RBAC = admin + manager,精简字段 id/name/department/role/is_active,默认过滤 is_active=True,弥补 manager 立项时无法列用户的 RBAC gap)。**严禁**改 `list_users / create_user / update_user / delete_user / batch_disable_users / batch_enable_users / reset_password / update_user_status / get_resource_load` 9 个现有端点。
  - **新建** `backend/tests/test_phase11_project_members.py`(~280 行 ~12 case)— Schema 3 + 主干 4 + 临时 1 + Picker 3 + 跨 tenant 1。私有 helpers `_phase11_picker_*` 前缀(对齐 T-1104 `_phase11_*` + T-1007 `_phase10_*` 体例),每 case 入口必跑 `_cleanup_phase11_picker_test_data`,作用域 `wechat_userid like "phase11_picker_%"` + `projects.code like "phase11_picker_%"`,零 mock/skip/print/logger/monkeypatch。
  - **改** `frontend/src/api/projects.ts`(~+15 行)— 新增 `ProjectMemberInit` + `CreateProjectPayload` interface + 替换 `createProject = (data: any)` 为 `(data: CreateProjectPayload)` 类型安全。
  - **改** `frontend/src/api/users.ts`(~+8 行)— 末尾追加 `UserPickerItem` interface + `getUserPicker` 函数(支持 `search` + `include_inactive` query)。
  - **新建** `frontend/src/components/member-picker.tsx`(~200 行)— 可控组件(`value: ProjectMemberInit[] + onChange`),搜索 + 已选列表 + 候选列表三区,track default `'both'`,maxLength=64 role 输入,maxMembers=50 默认上限。
  - **改** `frontend/src/app/projects/page.tsx`(~+70 行)— imports +2(`MemberPicker` + `ProjectMemberInit type`)+ `projectForm` state 加 `members: [] as ProjectMemberInit[]` + `handleCreateProject` payload 显式 spread 注入 members(`projectForm.members.length > 0 ? { members: ... } : {}`)+ toast 提示带成员指派数 + reset state 含 `members: []` + Modal JSX 在预算字段之后、按钮区域之前插入 `<MemberPicker value={...} onChange={...} />`。**严禁**动 编辑 Modal / 归档 Modal / 卡片列表 / 统计条 / 搜索 / FilterBar / 切换 toggle / 批量操作栏。
  - **零 schema 改动 + 零 migration + 零 service**:本任全在 router 层完成事务,**不**动 `backend/app/models/` / `backend/alembic/` / `backend/app/services/`;`ProjectMember` partial UNIQUE(T-1002)兜底新建项目场景 user_id dedup,无需新约束。
  - **零回归承诺**:T-1104 5 backend 文件不动 + 现有 POST/DELETE/GET `/{id}/members` 三端点不动 + 项目详情页 `activeTab='members'` UI 不动 + `backend/.env*` / conftest / `_isolation` / `_db_url` / README / DEPLOY 不动 + T-1102/1103 闭环议题不重做。
  - **测试基线**:T-1104 完工 193 passed → T-1105 完工预期 `205 passed + 2 skipped`(+12 case)。
  - **完整执行契约见 `docs/T-1105_spec.md`**(必读,~1184 行 10 章 + 📣 附录;指挥官 `[2026-05-29 11:10:44]` Auto Mode 下 6 决策签字 — A. 扩 ProjectCreate.members / 否 允许 0 成员 / 是 临时项目共享指派 / 新建 GET /users/picker 弥补 RBAC gap / track 默认 'both' / 现有单加路径完全冻结)。

---

## 📣 恢复执行指令

> **更新时间戳(T-1105 spec 起草落盘,等待 Codex 接手)**:`[2026-05-29 11:10:44]`
>
> **当前持牌任务**:T-1105(Phase 11 第五任 — 临时插队:立项时一站式指派成员)。**严禁** `git push`(等 Codex 完工 + 指挥官二次验收)。**严禁** 自启 T-1106 / T-1107 / 其他 Phase 11 候选议题。
>
> **T-1104 二次验收并行说明**:
> - T-1104 工程完工(`a532041`)已默认接受,28 项验收清单逐项核对推迟至 T-1105 完工后批量回补
> - Codex 接手 T-1105 不依赖 T-1104 二次验收 PASS(基线 `a532041` 即可)
>
> **Codex 接手指令(8 步)**:
> 1. **静默 Git 探针**(CLAUDE.md #1):`git status --short --branch && git log -5 --oneline && git diff && git diff --cached && git rev-list --left-right --count origin/main...HEAD`(期望 0 5:本地领先 5 commit = T-1104 4 + T-1105 spec 1)
> 2. **读盘**:`docs/T-1105_spec.md` 全文 + 本节 📣 锚点 + `backend/app/schemas/project.py:84` + `backend/app/routers/projects.py:248-423` + `backend/app/routers/users.py:1-71` + `frontend/src/api/projects.ts:30` + `frontend/src/api/users.ts:70` + `frontend/src/app/projects/page.tsx:111-119 / L166-200 / L795-863`
> 3. **二次确认 alembic head**:`cd backend && .venv/bin/alembic heads`(本任零 migration,head 应当是 T-1104 `20260529_1037_phase11_user_department_id_fk.py` 内 revision id)
> 4. **`dev_tasks.md` Task 5 `[ ]` → `[/]`** + 单 commit `chore(lock): T-1105 开工 — Phase 11 第五任 立项时一站式指派成员(临时插队)`
> 5. **按 spec §3 实施细则 8 文件改动**(3 改 backend + 1 新建 test + 2 改 frontend + 1 新建 frontend + 1 改 frontend)
> 6. **质量闸门 6+ 项**:ruff(4 backend)+ mypy(3 backend src)+ pytest 子集(12/12 PASS)+ 全量(205 passed + 2 skipped)+ frontend lint + typecheck + alembic check 跳过(Supervisor 既定特批)+ §3.9 fail-safe self-check 7 项 grep 全 0
> 7. **commit 纪律 2 commit 原子收口**:
>    - Commit 1:`feat(projects): T-1105 立项时一站式指派成员 — ProjectCreate.members 扩展 + GET /users/picker + MemberPicker 组件` 8 文件,Worker timestamp 必带,body 含业务点 + 后端扩展 + 前端接入 + 零回归承诺
>    - Commit 2:`chore(progress): close T-1105 — 立项时一站式指派成员(临时插队,Phase 11 第五任)` 1 文件,body 含完工概要 + 文件清单 + 11 项严禁项遵守证据
> 8. **完工后停手汇报**:`「T-1105 完工,等待指挥官二次验收 + T-1104 二次验收回补 + T-1106 候选起草」`
>
> **严禁项再确认(BLOCKER 红线 13 项)**:
> - 🚫 严禁 `git push`(等指挥官二次验收)
> - 🚫 严禁 自启 T-1106 / T-1107 / 其他 Phase 11 候选议题(原 FK 第二阶段 / drop column / 物化视图 / KPI 钻取 / 前端看板)
> - 🚫 严禁 改 `backend/app/models/` / `backend/alembic/` / `backend/app/services/` / `backend/app/schemas/user.py` / `backend/app/routers/` 除 `projects.py + users.py` 外任何文件
> - 🚫 严禁 改 `backend/app/routers/projects.py` 除 `create_project` 单函数外任何 router 函数
> - 🚫 严禁 改 `backend/app/routers/users.py` 除末尾**插入式**追加 `UserPickerItem` + `GET /picker` 端点外任何代码
> - 🚫 严禁 改 `backend/conftest.py` / `tests/_isolation.py` / `tests/_db_url.py` / `.env*` / `README.md` / `DEPLOY.md` / `pyproject.toml` / `requirements.txt` / `uv.lock`
> - 🚫 严禁 改 T-1104 5 backend 文件
> - 🚫 严禁 改 前端项目详情页 `frontend/src/app/project/[id]/page.tsx`(`activeTab='members'` UI 完全冻结)
> - 🚫 严禁 改 前端 dashboard / admin / users / sidebar / components/dashboard / components/charts 任何文件
> - 🚫 严禁 改 `frontend/src/app/projects/page.tsx` 现有非"新建项目 Modal"区块
> - 🚫 严禁 `git stash` / amend / rebase / `--no-verify` 跳过 hook
> - 🚫 严禁 测试 mock / monkeypatch / skip / print / logger / sleep / 直接读 os.environ
> - 🚫 严禁 改 `📣 附录` 位置 / 删除指挥官签字痕迹
>
> **候选 backlog(顺延,未启动)**:
> - T-1106 候选(原 T-1105 顺延):切剩余后端读路径用 Resolver + schemas/frontend 扩 `department_id` output + 写路径接入 `resolve_department_id_by_name`
> - T-1107 候选(原 T-1106 顺延):drop `User.department VARCHAR(64)` + 删除 Resolver fallback
> - T-1108+ 候选:Phase 11 候选议题 ②③④(物化视图增量 / KPI 钻取 / 前端 Tabs 加权重柱状图)
>
> **二次验收基线**:`a532041`(T-1104 chore(progress) 完工)。验收口径见 `docs/T-1105_spec.md` §8(28 项验收清单)。
