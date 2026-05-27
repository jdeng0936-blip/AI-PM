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

- [ ] **Task 4 (T-1004): `/api/v1/admin/departments` 服务 + 路由**
  - 新建 `backend/app/schemas/department.py`(`DepartmentIn / Out / WithMembers`)。
  - 新建 `backend/app/services/department_service.py`(`list / create / get_with_members` 三函数,后者从 `User` 反查 `department == name`)。
  - 新建 `backend/app/routers/departments.py`(`prefix="/api/v1/admin/departments"`, `tags=["Departments"]`),3 端点:GET 列表 / POST 新建 / GET `{id}/members`,RBAC `require_role(admin, manager)`。

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
> **更新时间戳**: `[2026-05-27 19:00:00]`(指挥官 T-1003 spec 落盘 + 锚点替换)

- **当前持牌任务**: **T-1003**(指挥官已通过本 `chore(spec)` commit 一并加锁,Task 3 = `[/]`)—— Phase 10 **第二份代码任务,数据层主线轮**:新建 `departments` 独立表 + ORM `Department` 类 + Alembic migration 建表 + bulk_insert 7 seed(技术部/生产部/采购部/财务部/商务部/销售部/仓储部)。**3 个 src 文件改动 + 1 条 migration,严禁夹带任何 service / router / schema / 前端 / 测试 / `User.department` 字段改造**。
- **执行入口**: 阅读 `docs/T-1003_spec.md`,不要重复 `chore(lock)`(已由指挥官打过),直接进入实施阶段。先 `cd backend && .venv/bin/alembic heads` 拿当前 head id(应为 `4f8e370435ea`,即 T-1002 落地后的 head),抄到新 migration 的 `down_revision`,**不要硬编码**。
- **核心动作**(严格按 T-1003_spec §3 顺序):
  1. **新建** `backend/app/models/department.py` —— `class Department(BaseMixin, Base)`,3 字段:`id UUID PK default uuid.uuid4` / `name Mapped[str] = mapped_column(String(64), unique=True, nullable=False, comment=...)` / `manager_id Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True, comment=...)`。BaseMixin 自动注入 `created_at/updated_at/created_by/tenant_id`。**严禁**加 `relationship` / `__table_args__` / 业务方法 / classmethod / property。
  2. **新建** `backend/alembic/versions/20260527_<HHMM>_phase10_create_departments_table.py` —— `revision_id` 12 位随机 hex(`python -c "import secrets; print(secrets.token_hex(6))"`);`down_revision = "4f8e370435ea"`(或 `alembic heads` 实测值)。`upgrade()` 执行:① `op.create_table("departments", ...)` 含 7 列(`id UUID PK` + `name String(64) NOT NULL` + `manager_id UUID FK→users.id ON DELETE SET NULL nullable=True` + BaseMixin 4 列 `created_at/updated_at/created_by/tenant_id`) + `sa.UniqueConstraint("name", name="uq_departments_name")`;② `op.create_index("ix_departments_manager_id", ..., ["manager_id"])` + `op.create_index("ix_departments_tenant_id", ..., ["tenant_id"])`;③ `op.bulk_insert(sa.table("departments", ...), [...])` 写入 7 seed,**顺序严格锁定**为 `技术部/生产部/采购部/财务部/商务部/销售部/仓储部`,每行 `manager_id=None`,`tenant_id="default"`,`id` 用 Python 端 `uuid.uuid4()` 预生成(`import uuid as _uuid` + `"id": _uuid.uuid4()`)。`downgrade()` 反向 `drop_index` ×2 + `drop_table("departments")`。docstring 按本仓库模板写**实际背景/变更/实现说明**,**不要保留模板占位**(pre-commit hook 会拒绝)。
  3. **改** `backend/app/models/__init__.py` —— ① **插入** 1 行 `from app.models.department import Department`(放在 `from app.models.deletion_history import DeletionHistory` 之后,`from app.models.gate_review import GateReview` 之前);② 在 `__all__` 列表中**插入** 1 个 `"Department",`(放在 `"DeletionHistory",` 之后,`"RiskAlert",` 之前)。**严禁**重排其他 import 或 `__all__` 元素,**严禁**删除任何分块注释(`# --- Mixin ---` 等)。
  4. **改** `docs/dev_tasks.md` —— Phase 10 看板 Task 3 从 `[/] In Progress by Codex` 改为 `[x]`(放最后一个 commit 一起 add)。**不动** 📣 锚点(留给指挥官在起草 T-1004 时统一替换)。
- **严禁项**(违反则立即回滚):
  - **严禁**改 `User.department` 字段(`String(64), nullable=False, default=""` 保留原样;FK 化迁移延后到 Phase 11+)。
  - **严禁**改任何其他 model(`User / Project / ProjectMember / KpiTarget` 等全冻结)。
  - **严禁**写 service / router / schema(留给 T-1004) —— 这次只动 `department.py` 新建 + `__init__.py` 插入 + 1 个新 migration。
  - **严禁**改 `frontend/src/` 任何文件(留给 T-1006)。
  - **严禁**补任何测试(留给 T-1007 集中补 Phase 10 测试套件)。
  - **严禁**改 `backend/scripts/seed_data.py`(本 task seed 走 alembic `bulk_insert`,与初始化脚本解耦)。
  - **严禁**给 `Department` 加 `relationship` / `back_populates` / `members` 反向关系(留给 Phase 11+)。
  - **严禁**碰 `backend/uv.lock`(继续 untracked)。
  - **严禁**在迁移里写 `UPDATE / DELETE` 任何数据 SQL,**严禁**触动 `users` 表的数据 —— 若 upgrade 失败,**不要自行清洗**,立即停手向指挥官报告。
  - **严禁**改 `__init__.py` 时重排其他 import 或 `__all__` 元素顺序(只允许插入)。
  - **严禁**自动 `git push`。
  - **严禁**自行启动 T-1004。
  - **严禁**改 📣 锚点("当前持牌任务: T-1003" 保留,留给指挥官在起草 T-1004 时统一替换)。
- **7 seed 顺序锁定**:`SEED_DEPARTMENTS = ["技术部", "生产部", "采购部", "财务部", "商务部", "销售部", "仓储部"]` —— **不可重排**,T-1007 测试会按此顺序 assert。
- **闸门**(都必须绿):
  ```bash
  cd backend
  .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head && .venv/bin/alembic check
  .venv/bin/pytest tests/                                      # 必须 160 passed + 2 skipped(零回归)
  .venv/bin/ruff check . && .venv/bin/mypy app/models/department.py app/models/__init__.py
  cd ../frontend && npm run lint && npm run typecheck          # 前端无破坏验证
  ```
- **完工提交序列**(原子 2 commit,**顺序不可乱**):
  1. `feat(department): add Department model + migration + 7 seed (技术部/生产部/采购部/财务部/商务部/销售部/仓储部)`(只含 `backend/app/models/department.py` 新建 + `backend/app/models/__init__.py` 插入式改动 + 新 alembic migration 共 3 个文件)
  2. `chore(progress): close T-1003 — departments 表 + 7 seed 落地`(只含 `docs/dev_tasks.md`,Task 3 → `[x]`)
- **时间戳纪律**: 所有 commit message 末尾、终端汇报、任何写入 `dev_tasks.md` 的段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。
- **完工后**: 立即停手汇报「T-1003 完工,等待指挥官二次验收 + 起草 T-1004 (`/api/v1/admin/departments` 服务 + 路由) 实施契约」。**不要**自行启动 T-1004。
