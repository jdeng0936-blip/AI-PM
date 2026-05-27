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

- [ ] **Task 5 (T-1005): `/api/v1/admin/reports?group_by=` 对外分组端点**
  - 在 `routers/dashboard.py` 或新建 `routers/admin_reports.py` 中新增 `GET /api/v1/admin/reports?group_by=department|project&project_id=&start_date=&end_date=` 端点,把现有 `dashboard.py L319 / trends.py L99` 的内部 SQL `GROUP BY` 包装成对外 query param。
  - 返回结构:`{ "技术部": [report...], "生产部": [...] }` 或 `{ "<project_id>": [...] }`。
  - RBAC `require_role(admin, manager)`,参数校验 Pydantic 枚举。

- [ ] **Task 6 (T-1006): 前端 Dashboard Tabs 切换器 + admin/departments 管理页**
  - 新建 `frontend/src/app/admin/departments/page.tsx`(表格 + 新建 Modal,字段 name + manager_id,调 `/api/v1/admin/departments`)。
  - 在 `/dashboard` 顶部加 `<Tabs>` 全员/按部门/按项目,按选择动态切换数据源(全员=现有 / 按部门=新端点 group_by=department / 按项目=新端点 group_by=project)。

- [ ] **Task 7 (T-1007): 后端测试 `test_phase10_dept_group.py`**
  - Model 层:ProjectMember 重复 `(project_id, user_id)` WHERE `left_at IS NULL` 必须抛 IntegrityError,但 `left_at` 不为空时允许重复;Department UNIQUE name 冲突。
  - Service 层:`get_with_members` 反查正确性 + 空部门返回空列表。
  - Router 层:200 路径 + RBAC + `group_by` 参数校验(`?group_by=invalid` 422)。
  - 跑通后所有 quality gates 全绿,`pytest tests/` 必须无回归。

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
> **更新时间戳**: `[2026-05-27 20:05:00]`(指挥官 T-1004 spec 勘误 — User 模型无 `deleted_at`,过滤改用 `is_active.is_(True)`;初次落盘时间 `[2026-05-27 19:30:00]`)

- **当前持牌任务**: **T-1004**(指挥官已通过本 `chore(spec)` commit 一并加锁,Task 4 = `[/]`)—— Phase 10 **第三份代码任务,服务/路由层主线轮**:新建 `/api/v1/admin/departments` 5 端点(CRUD + 成员反查),`schemas + service + router` 三件套 + `main.py` 注册。**4 个 src 文件改动(3 新建 + 1 插入式) + 1 个 dev_tasks.md 收口,严禁夹带任何 ORM / migration / 测试 / 前端 / `User.department` 字段改造**。
- **执行入口**: 阅读 `docs/T-1004_spec.md`,不要重复 `chore(lock)`(已由指挥官打过),直接进入实施阶段。**前置勘察已由指挥官完成,无需 Codex 再验**:① `User` 模型**无** `deleted_at` 字段,软删除信号 = `User.is_active.is_(True)`(已在多处使用,见 `chat_tools/people.py:117 / chat_tools/reports.py:315 / export/reports_excel.py:117 / routers/users.py:72,237,256`);② `User` 不继承 `BaseMixin`(避免 `created_by` FK 循环依赖,见 `models/user.py` L4-7 注释);③ `main.py` import 块按字母序排列(L13-26),`departments` 插入点在 `dashboard,` 之后 `erp,` 之前。
- **核心动作**(严格按 T-1004_spec §3 顺序):
  1. **新建** `backend/app/schemas/department.py` —— Pydantic V2,5 个 class:`DepartmentIn(name str 1-64, manager_id UUID|None)` / `DepartmentUpdate(name?, manager_id?)` / `DepartmentOut(id, name, manager_id, created_at, updated_at, created_by, tenant_id, ConfigDict(from_attributes=True))` / `DepartmentMember(id, name, role: UserRole, department, ConfigDict(from_attributes=True))` / `DepartmentWithMembers(DepartmentOut + members: list[DepartmentMember])`。**严禁**加 validator / @property / Computed。
  2. **新建** `backend/app/services/department_service.py` —— 5 个公开 async 函数 + 2 个 `_` 私有助手:`_get_department_or_raise(db, dept_id) -> Department`(404 → `raise ValueError("not_found")`);`_verify_manager_exists(db, manager_id)`(校验 `User.id == manager_id AND User.is_active.is_(True)`,失败 → `raise ValueError("manager_not_found")`);`list_departments` / `create_department(payload, actor)` / `update_department(dept_id, payload, actor)`(都在 `IntegrityError` 时 `raise ValueError("name_conflict")`) / `delete_department(dept_id)` / `get_department_with_members(dept_id)`(从 `User.department` 等值反查 + `User.is_active.is_(True)` + `tenant_id="default"` + `order_by(User.name.asc())`)。**严禁 raise HTTPException**(违反 kpi_service 体例);**严禁** 引入 `app.routers.*`;**严禁** print / logger。**严禁** 使用 `User.deleted_at`(该字段在本仓库不存在)。常量 `TENANT_ID = "default"`。
  3. **新建** `backend/app/routers/departments.py` —— `router = APIRouter(prefix="/api/v1/admin/departments", tags=["Departments"])` + `_mgr_or_admin = require_role(UserRole.admin, UserRole.manager)` + `_map_value_error(exc) -> HTTPException`(映射 `not_found→404` / `name_conflict→409` / `manager_not_found→400`,兜底 500)。5 端点:`GET /` (`list[DepartmentOut]`) / `POST /` (201 `DepartmentOut`) / `GET /{dept_id}/members` (`DepartmentWithMembers`) / `PATCH /{dept_id}` (`DepartmentOut`) / `DELETE /{dept_id}` (204 `Response`)。每个端点 try/except ValueError + `raise _map_value_error(e) from None`。**严禁** router 层做 ORM 查询;**严禁** RBAC 加 employee 或去 manager;**严禁** 加 / 减端点。
  4. **改** `backend/app/main.py` —— 插入式 2 行:① 在 `from app.routers import (...)` 块中 `departments,` 插在 `dashboard,` 之后 `erp,` 之前(字母序);② `app.include_router(departments.router)` 紧邻 `app.include_router(kpi.router)` 之后。**严禁** 重排其他 import 或 include_router 顺序;**严禁** 改 Sentry 初始化 / lifespan / 中间件挂载。
  5. **改** `docs/dev_tasks.md` —— Phase 10 看板 Task 4 从 `[/] In Progress by Codex` 改为 `[x]`(放最后一个 commit 一起 add)。**不动** 📣 锚点(留给指挥官在起草 T-1005 时统一替换)。
- **严禁项**(违反则立即回滚):
  - **严禁**改 `backend/app/models/` 任何文件(`department.py / user.py / __init__.py / *` 全冻)。
  - **严禁**新增任何 alembic migration(本任务零 DB schema 改动)。
  - **严禁**改 `User.department: String(64)` 字段定义。
  - **严禁**写测试(留给 T-1007 集中补 Phase 10 测试套件)。
  - **严禁**改 `frontend/src/` 任何文件(留给 T-1006 前端 Tabs + admin/departments 页)。
  - **严禁**改 `backend/scripts/seed_data.py`。
  - **严禁** service 层 raise `HTTPException`(违反 kpi_service 体例)。
  - **严禁** router 层做 ORM 查询(全部走 service 函数)。
  - **严禁** 自行扩端点(PUT / OPTIONS / HEAD)或减端点 —— 必须严格 5 个。
  - **严禁** RBAC 范围加 `employee` 或去掉 `manager`。
  - **严禁** 重排 `main.py` import 块或 `include_router` 的其他元素。
  - **严禁** 给 service / router 加 `print` 或 `logger.info` 副作用。
  - **严禁** 碰 `backend/uv.lock` / `.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md`(继续 untracked)。
  - **严禁** 自动 `git push`。
  - **严禁** 自行启动 T-1005 / T-1006 / T-1007 / T-1008。
  - **严禁** 改 📣 锚点("当前持牌任务: T-1004" 保留,留给指挥官在起草 T-1005 时统一替换)。
- **端点 + 错误码 + RBAC 锁定表**(必须 100% 对齐,T-1007 测试会按此 assert):

  | 方法 | 路径 | 响应模型 | 状态码 | RBAC |
  |------|------|----------|--------|------|
  | GET    | `/api/v1/admin/departments/`              | `list[DepartmentOut]`     | 200 | admin + manager |
  | POST   | `/api/v1/admin/departments/`              | `DepartmentOut`           | 201 | admin + manager |
  | GET    | `/api/v1/admin/departments/{dept_id}/members` | `DepartmentWithMembers` | 200 | admin + manager |
  | PATCH  | `/api/v1/admin/departments/{dept_id}`     | `DepartmentOut`           | 200 | admin + manager |
  | DELETE | `/api/v1/admin/departments/{dept_id}`     | (无 body)                  | 204 | admin + manager |

  | service ValueError 字面量 | router HTTPException | detail |
  |--------------------------|----------------------|--------|
  | `"not_found"`            | 404 | `"部门不存在"` |
  | `"name_conflict"`        | 409 | `"部门名称已存在"` |
  | `"manager_not_found"`    | 400 | `"manager_id 对应的用户不存在或已删除"` |

- **闸门**(都必须绿):
  ```bash
  cd backend
  .venv/bin/ruff check .
  .venv/bin/mypy app/schemas/department.py app/services/department_service.py app/routers/departments.py app/main.py
  .venv/bin/pytest tests/ -q                                   # 必须零回归(与 T-1003 完工基线一致)
  .venv/bin/alembic upgrade head && .venv/bin/alembic check    # 本任务零 migration,head 不变
  cd ../frontend && npm run lint && npm run typecheck          # 前端无破坏验证
  ```
- **完工提交序列**(原子 2 commit,**顺序不可乱**):
  1. `feat(department): add Department service + router + 5 endpoints (CRUD + members)`(只含 `backend/app/schemas/department.py` 新建 + `backend/app/services/department_service.py` 新建 + `backend/app/routers/departments.py` 新建 + `backend/app/main.py` 插入式 2 行 共 4 个文件)
  2. `chore(progress): close T-1004 — /api/v1/admin/departments 5 端点 + 成员反查上线`(只含 `docs/dev_tasks.md`,Task 4 → `[x]`)
- **时间戳纪律**: 所有 commit message 末尾、终端汇报、任何写入 `dev_tasks.md` 的段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。
- **完工后**: 立即停手汇报「T-1004 完工,等待指挥官二次验收 + 起草 T-1005 (`/api/v1/admin/reports?group_by=` 分组端点) 或 T-1007 (测试集中补) 实施契约」。**不要**自行启动任何下游 task。
