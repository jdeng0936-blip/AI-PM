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

- **当前持牌任务**: **T-908**(已自动锁定为 `[/]`)—— Phase 9 **修补任务 + PR push 前最后一份契约**:统一前后端 KPI metric 枚举命名,**改后端单边**(ORM + Pydantic schema docstring + 新增 alembic migration `ALTER TYPE kpi_metric RENAME VALUE`),**不动前端、不动历史 migration、不动测试**。
- **执行入口**: 阅读 `docs/T-908_spec.md`,不要重复 `chore(lock)`,直接动手。先 `cd backend && .venv/bin/alembic heads` 拿当前 head id(应为 `b4f6a8d2c9e1`),抄到新 migration 的 `down_revision`,**不要硬编码**。
- **核心动作**:
  1. **新建** `backend/alembic/versions/20260527_<HHMM>_phase9_rename_metric_objective_completion.py` —— `upgrade()` 执行 `ALTER TYPE kpi_metric RENAME VALUE 'sprint_completion' TO 'objective_completion'`,`downgrade()` 反向 RENAME。docstring 按本仓库模板写实际背景/变更/实现说明,**不要保留模板占位**(pre-commit hook 会拒绝)。
  2. **改** `backend/app/models/kpi_target.py:35` —— `sprint_completion = "sprint_completion"` → `objective_completion = "objective_completion"`,**Python Enum 顺序保持原位**(改名不重排)。
  3. **改** `backend/app/schemas/kpi.py:7` 顶部 docstring —— metric 集合改为 `{submit_rate, avg_score, blocker_resolve_days, objective_completion}`。
  4. **改** `docs/implementation-plan.md §9 实际落地路径(Phase 9)` 段 —— metric 枚举那一行从「漂移待修」改成「T-908 已统一」,数据源段把 `sprint_completion` 改成 `objective_completion`。详见 T-908_spec §3.4。
  5. **改** `docs/recap.md` —— 在「最新进度摘要」段尾追加 1 条 Task 8 bullet,在「历史移交记录」顶部插入 1 条 [2026-05-27] 时间戳条目。详见 T-908_spec §3.5。
  6. **改** `docs/dev_tasks.md` —— Task 8 从 `[/] In Progress` 改为 `[x]`(在最后一个 commit 一起 add)。
- **重要不要做**:
  - **不要**改 `frontend/` 任何文件 —— 前端 `api/kpi.ts` / `admin/kpi/page.tsx` / `kpi-achievement-panel.tsx` 已经是目标命名。
  - **不要**改历史 alembic migration(`20260527_1234_phase9_add_kpi_targets.py` + `_1317_phase9_fix_kpi_targets_unique_nulls.py`),即使其中 docstring/字面量含 `sprint_completion` —— 历史事实保留,alembic 顺序执行最终态正确。
  - **不要**写 `UPDATE kpi_targets SET metric = ...` —— enum RENAME VALUE 自动同步元数据,自己 UPDATE 会因 enum cast 失败。
  - **不要**改 `backend/app/services/kpi_service.py` —— `objective_completion` 继续走 no_data 分支,这是预期行为(actual 聚合留待 Phase 11+)。
  - **不要**改测试代码 —— 现有 12 个测试不引用 `sprint_completion`,T-908 不补新测试,`pytest -v` 应自动仍 12 passed。
  - **不要**碰 `backend/uv.lock`(继续 untracked)。
  - **不要**自动 `git push`(完工后由指挥官最终 sign-off 后统一推送 51+ commit)。
  - **不要**自行启动 Phase 10。
- **闸门**(都必须绿):
  ```bash
  cd backend
  .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head && .venv/bin/alembic check
  .venv/bin/pytest tests/test_kpi_phase9.py -v                # 必须 12 passed
  .venv/bin/pytest tests/                                      # 必须 160 passed + 2 skipped
  .venv/bin/ruff check . && .venv/bin/mypy app/models/kpi_target.py app/services/kpi_service.py app/routers/kpi.py
  cd ../frontend && npm run lint && npm run typecheck         # 前端无破坏验证
  ```
- **完工提交序列**(原子 3 commit,**顺序不可乱**):
  1. `fix(kpi): rename metric sprint_completion to objective_completion`(只含 `backend/app/models/kpi_target.py` + `backend/app/schemas/kpi.py` + 新 alembic migration)
  2. `docs(kpi): mark Phase 9 metric drift resolved by T-908`(只含 `docs/implementation-plan.md` + `docs/recap.md`)
  3. `chore(progress): close T-908 + Phase 9 PR ready`(只含 `docs/dev_tasks.md`,Task 8 → `[x]`)
- **完工后**: 立即停手,等指挥官最终二次验收 + Phase 9 PR 整体 sign-off + 统一推送 51+ commit。T-908 是 Phase 9 PR push 前**最后一份**契约。
