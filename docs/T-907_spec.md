# T-907 执行契约 —— Phase 9 文档收尾 + 后端测试补全

> 类型: **Worker (Codex) 任务卡** · 唯一持牌任务
> 上游: T-906(前端 KPI 达成率面板)已交付并由指挥官二次验收通过(commit `9d7d16c`+ `b31b83f`)
> 目的: 完成 Phase 9 闭环 —— 同步文档 + 补全 3 个高价值后端测试,**不动任何 src 代码**

---

## §1 任务定义

T-907 是 **Phase 9 收尾契约**,所有 Phase 9 主线代码已经落地并通过验收:

- T-901 / T-901-FIX: `kpi_targets` 表 + Model + 两条 Alembic migration(已合并)
- T-902: `app/schemas/kpi.py` + `app/services/kpi_service.py`(已合并)
- T-903: `/api/v1/admin/kpi/{,achievement}` 三端点(已合并)
- T-904: `backend/tests/test_kpi_phase9.py` 9 个三层测试(已合并,9/9 PASS)
- T-905: `frontend/src/app/admin/kpi/page.tsx` 管理页(已合并)
- T-906: `frontend/src/components/dashboard/kpi-achievement-panel.tsx` 达成率面板(已合并)

剩下两件未完工:

1. **文档同步**(原 dev_tasks Task 7 范围):`docs/recap.md` 追加 Phase 9 章节,`docs/implementation-plan.md §9` 补「实际落地路径」段。
2. **后端测试补全**(用户在最新指令中明确扩展进 T-907 的内容):在现有 9 个测试基础上追加 3 个用例,覆盖
   - service 层 `calculate_kpi_achievement` 在 **有实际数据时**的正路径(当前只测了 `no_data`)
   - router 层 **POST 创建新行**(当前只测了 422 入参 + GET)
   - router 层 **manager 角色 200**(当前只测了 admin 200 + employee 403,manager 路径未明)

---

## §2 现状勘察(Phase 9 已落地代码事实,作 plan §9 「实际落地路径」段的素材)

| 维度 | plan §9 原文 | 实际落地 | 备注 |
|---|---|---|---|
| 主键 id | `SERIAL PRIMARY KEY` | SQLAlchemy `Integer primary_key=True autoincrement=True` | ORM 等价,声明方式不同 |
| created_by | `INT REFERENCES users(id)` | `UUID FK → users.id`,可空 | **校正**: 本项目 `users.id` 是 UUID 不是 INT |
| 路由前缀 | `/api/admin/kpi` | `/api/v1/admin/kpi` | **校正**: 全局规约 `/api/v1/` |
| 字段集 | 7 字段(含 updated_at) | +3 字段: `tenant_id` `created_at` `updated_at`(继承 `BaseMixin`)| 自动注入 |
| UNIQUE | (未提及) | `UNIQUE(scope, scope_value, metric, period) NULLS NOT DISTINCT` | T-901-FIX 补,plan 漏列 |
| metric 枚举 | `submit_rate / avg_score / sprint_completion / blocker_resolve_days` | `submit_rate / avg_score / blocker_resolve_days / objective_completion` | **校正**: `sprint_completion` → `objective_completion`(对齐 OKR 模块) |
| 响应字段 | (未提及) | `KpiAchievementRow` 含 `gap / achievement_rate / status('on_track'\|'below_target'\|'no_data')` | 数据契约扩展 |

---

## §3 文档同步 —— docs/recap.md

### §3.1 「最新进度摘要」段位置

文件当前结构(`docs/recap.md`):
- 第 1 节 `## 最新进度摘要`(line 3-13,Phase 7/8 bullet)
- 第 2 节 `## 历史移交记录`(line 15-25,时间戳条目)

### §3.2 修改

**A. line 5 「当前阶段」**:
```diff
- - **当前阶段**: **Phase 8 数据导出**。
+ - **当前阶段**: **Phase 9 KPI 目标设定**(已闭环)。
```

**B. line 13 之后,line 14 空行之前,追加 6 条 Phase 9 bullet**:

```markdown
- **Phase 9 Task 1 (T-901 + T-901-FIX)**: 已新增 `kpi_targets` 表与 `KpiTarget` ORM 模型(`KpiScope/KpiMetric/KpiPeriod` 三 Enum),两条 Alembic migration(建表 + UNIQUE NULLS NOT DISTINCT 修复)+ 4 行 seed,`alembic upgrade head` 与 `alembic check` 全绿。
- **Phase 9 Task 2 (T-902)**: 已落地 `app/schemas/kpi.py`(4 个 Pydantic V2 schema)+ `app/services/kpi_service.py`(`list_kpi_targets` / `upsert_kpi_target` / `calculate_kpi_achievement`);达成率服务复用 Phase 7 MV `mv_daily_user_stats` / `mv_weekly_dept_stats`,缺数据返回 `actual=None / status='no_data'`。
- **Phase 9 Task 3 (T-903)**: 已新增 `/api/v1/admin/kpi/` 三端点(GET 列表 / POST upsert / GET achievement),`require_role(admin, manager)` RBAC 守卫,period 参数 Pydantic 校验。
- **Phase 9 Task 4 (T-904)**: 已新增 `backend/tests/test_kpi_phase9.py` 9 个三层测试(Model 2 + Service 3 + Router 4),NULLS NOT DISTINCT 负向 + Enum 校验 + upsert UPDATE 路径 + no_data 路径 + RBAC + 422 全部覆盖。
- **Phase 9 Task 5 (T-905)**: 已新增 `frontend/src/app/admin/kpi/page.tsx` admin/manager 管理页(表格 + Modal 新建/编辑 + 编辑模式四元组锁 + 三层客户端校验 + hydrate 安全占位 + 422 detail 解析)。
- **Phase 9 Task 6 (T-906)**: 已新增 `frontend/src/components/dashboard/kpi-achievement-panel.tsx`(period 切换器 + `CompareBarChart` 目标蓝/实际绿双柱 + 7 列状态彩色 tag 详情表),在 `/dashboard` 通过 `canManageAlerts` 守卫嵌入,不动 Phase 7 `CompareBarChart` 与 T-905 管理页。
- **Phase 9 Task 7 (T-907)**: 文档收尾 + 后端测试补全 3 个用例(achievement 真路径计算 / router POST 创建 / manager RBAC),Phase 9 全闭环。
```

**C. 「历史移交记录」段(line 15 之后)**:
在 line 16(原 `Phase 8 Task 7/8` 条目)之前,按时间倒序追加 7 条:

```markdown
- [2026-05-27] Phase 9 Task 7 完成:`docs/recap.md` + `docs/implementation-plan.md §9` 同步,后端测试补全 3 个用例。Phase 9 闭环。
- [2026-05-27] Phase 9 Task 6 (T-906) 完成:Dashboard `KpiAchievementPanel` 面板,target-vs-actual `CompareBarChart` + 状态彩色 tag 详情表;`/dashboard` 12.8 kB / 338 kB First Load。
- [2026-05-27] Phase 9 Task 5 (T-905) 完成:`/admin/kpi` 管理页,admin/manager RBAC + scope 联动 + 四元组编辑锁 + 422 detail 数组解析;`/admin/kpi` 4.17 kB / 220 kB First Load。
- [2026-05-27] Phase 9 Task 4 (T-904) 完成:`tests/test_kpi_phase9.py` 9 个三层测试,全套后端 `pytest tests/` 157 passed / 2 skipped 无回归。
- [2026-05-27] Phase 9 Task 3 (T-903) 完成:`/api/v1/admin/kpi/{,achievement}` 三端点,`require_role` admin/manager + period 枚举校验。
- [2026-05-27] Phase 9 Task 2 (T-902) 完成:`KpiTargetIn/Out + KpiAchievementRow/Response` Pydantic + `kpi_service` 三函数,达成率复用 Phase 7 MV。
- [2026-05-27] Phase 9 Task 1 / T-901-FIX 完成:`kpi_targets` 表 + UNIQUE NULLS NOT DISTINCT 修复,4 行 seed 与 BaseMixin 字段就位。
```

⚠️ 「当前阶段」一行必须改完 —— 如果 Phase 10 还没开,可加备注 `(下一阶段待规划)`。

---

## §4 文档同步 —— docs/implementation-plan.md §9

### §4.1 插入位置

`docs/implementation-plan.md` 当前 `## 9. KPI 目标设定` 在 line 653,内部子节顺序:

```
653: ## 9. KPI 目标设定
655: ### 数据库模型
677: ### API 端点
685: ### KPI 达成率计算
703: (代码块结束)
704: (空行)
705: ---
706: ## 10. 部门与项目分组
```

**在 line 703 代码块结束之后、line 705 `---` 分隔符之前**,插入新的 `### 实际落地路径(Phase 9)` 子节,**完全模仿 §8 Phase 8 同名段的格式**(参见 plan line 639-651)。

### §4.2 「实际落地路径(Phase 9)」段内容

```markdown
### 实际落地路径(Phase 9)

Phase 9 实际落地相对 plan 原文存在以下偏差,均已在 `T-901` ~ `T-907` 系列契约中校正:

| 维度 | plan 原文 | 实际落地 | 原因 |
|------|---------|---------|------|
| 主键 | `id SERIAL PRIMARY KEY` | SQLAlchemy `Integer, primary_key=True, autoincrement=True` | ORM 等价,声明形式不同 |
| created_by | `INT REFERENCES users(id)` | `UUID, FK → users.id`,可空 | 本项目 `users.id` 类型为 UUID,plan 误写为 INT |
| 路由前缀 | `/api/admin/kpi` | `/api/v1/admin/kpi` | 全局规约 `/api/v1/` |
| BaseMixin 字段 | 仅 `updated_at` | `+ tenant_id` `+ created_at`(继承 `app.models.base_mixin.BaseMixin`) | 多租户与审计字段统一注入 |
| UNIQUE 约束 | (未提及) | `UNIQUE(scope, scope_value, metric, period) NULLS NOT DISTINCT` (PG 15+ 语义) | T-901-FIX 补,解决 `scope_value IS NULL` 时默认 NULL DISTINCT 失效 |
| metric 枚举 | `submit_rate / avg_score / sprint_completion / blocker_resolve_days` | `submit_rate / avg_score / blocker_resolve_days / objective_completion` | `sprint_completion` 重命名为 `objective_completion`,对齐 OKR 模块语义 |

实际对外 API 路径(沿用 FastAPI router `prefix="/api/v1/admin/kpi"`):

| 方法 | 实际路径 | 说明 |
|------|----------|------|
| GET  | `/api/v1/admin/kpi/` | 列出全部 KPI 目标,`require_role(admin, manager)` |
| POST | `/api/v1/admin/kpi/` | upsert 目标(UNIQUE 冲突走 ON CONFLICT DO UPDATE),`require_role(admin, manager)` |
| GET  | `/api/v1/admin/kpi/achievement?period=weekly\|monthly\|quarterly` | 达成率快照,**不带尾斜杠**;默认 `monthly`,非法值 422 |

达成率响应 `KpiAchievementRow` 扩展字段(plan 未覆盖):

- `gap = actual_value - target_value`,缺数据时 `None`
- `achievement_rate = round(actual_value / target_value * 100, 2)`,缺数据时 `None`
- `status` 三态: `on_track`(达成) / `below_target`(未达成) / `no_data`(缺源)

实际 actual_value 数据源:
- `submit_rate` / `avg_score` → Phase 7 `mv_daily_user_stats` 按 period 聚合
- `objective_completion` → `mv_weekly_dept_stats`(部门 scope)或 OKR 服务聚合(global scope)
- `blocker_resolve_days` → 暂无聚合源,固定返回 `no_data`(后续 Phase 11 实现)
```

⚠️ 严禁删改 §9 plan 原文,只在末尾**追加**新子节。

---

## §5 后端测试补全 —— backend/tests/test_kpi_phase9.py

### §5.1 现状

当前 9 个测试(line 181-362)已覆盖:

| 层 | 测试 | 覆盖 |
|---|---|---|
| Model | `test_unique_null_scope_value_blocks_duplicate` | NULLS NOT DISTINCT 负向 |
| Model | `test_invalid_enum_value_rejected` | Enum 校验 |
| Service | `test_upsert_updates_existing_row` | upsert UPDATE 路径 |
| Service | `test_calculate_achievement_no_data_returns_none` | actual=None / status='no_data' |
| Service | `test_list_kpi_targets_stable_order` | 排序稳定 |
| Router | `test_router_admin_get_returns_200` | admin GET 200 |
| Router | `test_router_employee_forbidden` | employee 403 |
| Router | `test_router_invalid_period_returns_422` | invalid period 422 |
| Router | `test_router_post_invalid_payload_returns_422` | scope=global 带 scope_value 非空 → 422 |

### §5.2 缺口

| 缺口 | 影响 | 优先级 |
|---|---|---|
| 服务层 `calculate_kpi_achievement` **正路径**(actual 有值时算 gap/achievement_rate/status='on_track'\|'below_target')未测 | gap 公式、achievement_rate 计算精度、status 判定阈值若回归不会被发现 | **高** |
| Router POST 创建**新行**(insert 路径)未测,只测了 422 入参错和 service 层 UPDATE | DB 持久化 + 200 响应字段完整性可能被回归 | **高** |
| Router manager 角色未测 RBAC 路径,只测了 admin 200 + employee 403 | manager 因任何配置变更被意外排除时不会被发现 | **中** |

### §5.3 追加测试(3 个,在文件末尾添加,**不动现有 9 个**)

#### §5.3.1 T-907-A: `test_calculate_achievement_with_real_data`

**目的**: 验证 `calculate_kpi_achievement` 正路径 —— 种入 `daily_reports` → REFRESH MV → 调服务 → 断言 `actual_value/gap/achievement_rate/status` 计算正确。

**关键点**:
1. **种入 daily_reports 行** —— 用 `sqlalchemy.text` INSERT 几条,带 `ai_score`、`report_date`、`tenant_id`、`user_id`,字段名以 `app/models/daily_report.py` 为准(自查)。
2. **必须 commit** 后才能 `REFRESH MATERIALIZED VIEW mv_daily_user_stats`(MV 读快照,非事务可见)。
3. upsert 一个 `global` `submit_rate` `target_value=50.0` 的目标(用低 target 让 status='on_track' 才好断言)。
4. 调 `calculate_kpi_achievement(db, KpiPeriod.monthly)`,断言:
   - `actual_value` 非 `None` 且为 float
   - `gap` 数值等于 `actual_value - target_value`(允许 1e-6 浮点误差)
   - `achievement_rate` 等于 `round(actual / target * 100, 2)` 或近似
   - `status == "on_track"` 当 `actual >= target`,否则 `"below_target"`
5. 清理: fixture 自动回滚 + 在 setup 阶段先 `_cleanup_kpi_test_data` 重置(看现有 fixture 模式)。

⚠️ **daily_reports 列名不要凭记忆**,运行前 `grep -n "Column" backend/app/models/daily_report.py` 确认 `ai_score / report_date / tenant_id / user_id` 是否存在,以及类型;如有列名不一致,以源码为准,不要改 model。

#### §5.3.2 T-907-B: `test_router_post_creates_new_target`

**目的**: 验证 `POST /api/v1/admin/kpi/` 创建新行(insert 路径)。

```python
@pytest.mark.asyncio
async def test_router_post_creates_new_target(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _make_user(db_session, UserRole.admin, "POST_ADM")
    payload = {
        "scope": "department",
        "scope_value": "测试部",
        "metric": "avg_score",
        "target_value": 80.0,
        "period": "monthly",
    }
    response = await client.post("/api/v1/admin/kpi/", headers=_headers(admin), json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "department"
    assert body["scope_value"] == "测试部"
    assert body["target_value"] == 80.0
    assert body["created_by"] == str(admin.id)

    # DB 持久化校验
    row = (await db_session.execute(
        select(KpiTarget).where(
            KpiTarget.scope == KpiScope.department,
            KpiTarget.scope_value == "测试部",
            KpiTarget.metric == KpiMetric.avg_score,
            KpiTarget.period == KpiPeriod.monthly,
        )
    )).scalar_one()
    assert row.target_value == 80.0
```

⚠️ 状态码 `200` 是当前 `kpi_service.upsert_kpi_target` + router 的实际返回(plan §9 没规定,以源码为准);如果实际返回 201 改成 201。

#### §5.3.3 T-907-C: `test_router_manager_get_returns_200`

**目的**: 闭环 RBAC 矩阵 —— admin 200 / **manager 200** / employee 403。

```python
@pytest.mark.asyncio
async def test_router_manager_get_returns_200(client: AsyncClient, db_session: AsyncSession) -> None:
    manager = await _make_user(db_session, UserRole.manager, "MGR")
    response = await client.get("/api/v1/admin/kpi/", headers=_headers(manager))
    assert response.status_code == 200
    assert isinstance(response.json(), list)
```

### §5.4 测试文件位置约束

- **仅追加**到 `backend/tests/test_kpi_phase9.py` 末尾,不要新建文件。
- 复用现有 `db_session` / `client` / `_make_user` / `_headers` / `_cleanup_kpi_test_data` fixture。
- 不要修改 `_ensure_analytics_views` —— 它已经自建 MV,T-907-A 直接用即可。

---

## §6 闸门(提交前 must 全绿)

```bash
# 1. 后端测试(应 12 passed,9 旧 + 3 新)
cd backend && .venv/bin/pytest tests/test_kpi_phase9.py -v

# 2. 全套防回归
cd backend && .venv/bin/pytest tests/

# 3. 静态检查
cd backend && .venv/bin/ruff check . && .venv/bin/mypy app/models/kpi_target.py app/services/kpi_service.py app/routers/kpi.py

# 4. 文档 lint(可选,如本机有 markdownlint)
npx markdownlint-cli 'docs/recap.md' 'docs/implementation-plan.md' 'docs/T-907_spec.md' 2>/dev/null || echo "(markdownlint not installed, skip)"
```

---

## §7 完工提交序列(原子 3 commit)

```bash
# 第 1 个 commit: 测试补全
git add backend/tests/test_kpi_phase9.py
git commit -m "test(kpi): backfill achievement-with-data + POST insert + manager RBAC"

# 第 2 个 commit: 文档同步
git add docs/recap.md docs/implementation-plan.md
git commit -m "docs(kpi): Phase 9 recap + plan §9 actual landing path"

# 第 3 个 commit: 收口
# 修改 docs/dev_tasks.md Task 7 → [x]
git add docs/dev_tasks.md
git commit -m "chore(progress): close T-907 + Phase 9 closeout"
```

---

## §8 红线(严禁踩)

1. **不动任何 src 代码** —— 包括 `app/models/kpi_target.py`、`app/schemas/kpi.py`、`app/services/kpi_service.py`、`app/routers/kpi.py`、`frontend/src/app/admin/kpi/page.tsx`、`frontend/src/components/dashboard/kpi-achievement-panel.tsx`、`frontend/src/api/kpi.ts`、`frontend/src/app/dashboard/page.tsx`。T-907 是纯文档 + 纯测试任务。
2. **不动 Alembic migration** —— 已有的两条迁移 T-901/T-901-FIX 是 schema 真相源,不允许新增、修改、合并、压缩。
3. **不动 backend/uv.lock** —— 继续保持 untracked。
4. **不动 §9 plan 原文** —— 只在 §9 末尾**追加**「实际落地路径(Phase 9)」子节,plan 原始 SQL 和 API 表保留作为「设计意图」存证。
5. **不要回填 kpi_targets 之外的表** —— Phase 9 仍是纯增量。
6. **不要扩大测试范围** —— T-907 是 closeout,不引入前端测试基础设施,不补 Phase 7/8 回归测试。

---

## §9 风险与坑(实战经验,务必看完再动手)

1. **MV 刷新的事务边界**: PostgreSQL `REFRESH MATERIALIZED VIEW` 不在事务隔离里读未提交 INSERT。T-907-A 种入 `daily_reports` 后,**必须 `await db.commit()`**,再 `await db.execute(text("REFRESH MATERIALIZED VIEW mv_daily_user_stats"))`,然后再 `calculate_kpi_achievement`,顺序错了会拿到旧快照导致 `actual=None`。
2. **daily_reports 列名以源码为准**: 不要凭脑补写 INSERT SQL。先 `grep -nE "^[ ]*(report_date|ai_score|tenant_id|user_id)" backend/app/models/daily_report.py` 拿真实列名,字段缺一行 INSERT 会 IntegrityError。
3. **fixture loop_scope 对齐**: 现有 `db_session` fixture 是本地的(看 `test_kpi_phase9.py` 顶部),不要切到全局 conftest 的 fixture。任何 `pytest-asyncio` 1.x 事件循环错配会导致 `RuntimeError: attached to a different loop`。
4. **scope=global + scope_value 非空的 422** 已经覆盖(`test_router_post_invalid_payload_returns_422`),T-907-B 不要再测这个 case。T-907-B 用 `scope=department + scope_value='测试部'` 的合法 payload。
5. **`created_by` 是 UUID 字符串**: 响应 JSON 的 `created_by` 字段是 UUID `str`,断言时用 `str(admin.id)` 而非 `admin.id`(UUID 对象 != str)。
6. **manager 角色和 admin 角色都能 GET**: 不要把 T-907-C 写成 POST manager(理论上 POST 也可以,但 contract §1.3 router 描述是 GET 列表的 RBAC 验证,聚焦那个就好)。
7. **`/api/v1/admin/kpi/` 带尾斜杠 vs `/achievement` 不带**: 这是 T-905/T-906 已经踩过的坑,T-907 测试沿用现有写法即可。
8. **plan §9 的 SQL 块不要 markdown 转义** —— 原文是 ```sql ... ``` fenced block,新增「实际落地路径」段也用 fenced block,不要混用缩进语法。
9. **recap.md 「当前阶段」一行必改** —— 如果 Phase 10 还没规划好,写成 `Phase 9 KPI 目标设定(已闭环)`,不要留 `Phase 8` 矛盾状态。
10. **markdownlint 可能告警「表格管道前后空格」或「行尾空格」** —— 不要为了过 lint 而压缩表格,如有警告手动修齐即可,不要全文 reformat。

---

## §10 完工后停手位

T-907 是 Phase 9 **最后一个**任务。完工后:

1. 提交 3 个原子 commit(见 §7)。
2. 修改 `docs/dev_tasks.md` Task 7 → `[x]`。
3. **立即停手**,等指挥官最终二次验收。
4. **不要**自行开启 Phase 10(部门与项目分组),那是另一份独立的 PM 决策,需要新立项契约。
5. **不要**自动 `git push` —— 推送由指挥官在 Phase 9 整体 sign-off 后统一操作。

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌,供 PM 探针自动提取**

- **当前持牌任务**: **T-907**(已自动锁定为 `[/]`)—— Phase 9 文档收尾 + 后端测试补全 3 个用例,**纯文档 + 纯测试**,**严禁动 src 代码**。
- **执行入口**: 阅读本文件 `docs/T-907_spec.md`,不要重复 `chore(lock)`,直接编码。
- **核心动作**:
  1. **改** `docs/recap.md` —— 按 §3 改「当前阶段」+ 追加 6 条 Phase 9 bullet + 追加 7 条 [2026-05-27] 时间戳记录。
  2. **追加** `docs/implementation-plan.md §9` —— 在第 703 行代码块结束后、第 705 行 `---` 之前,新增 `### 实际落地路径(Phase 9)` 子节,内容见 §4.2。
  3. **追加** `backend/tests/test_kpi_phase9.py` —— 在文件末尾追加 3 个测试 `test_calculate_achievement_with_real_data` / `test_router_post_creates_new_target` / `test_router_manager_get_returns_200`,细节见 §5.3。
  4. **改** `docs/dev_tasks.md` —— Task 7 从 `[/] In Progress` 改为 `[x]`(完工 commit 时一起 add)。
- **重要不要做**:
  - **不要**改任何 `app/` `frontend/src/` 下的源代码(model/schema/router/service/页面/组件/api 客户端)。
  - **不要**新建 Alembic migration。
  - **不要**新建任何 src 文件(包括新 test 文件 —— 测试只追加到 `test_kpi_phase9.py`)。
  - **不要**碰 `backend/uv.lock`(继续 untracked)。
  - **不要**重新生成 seed 数据或改 `seed_admin.py`。
  - **不要**改 `plan §9` 原 SQL/API 表(只追加新子节)。
- **闸门**:
  ```bash
  cd backend && .venv/bin/pytest tests/test_kpi_phase9.py -v       # 必须 12 passed
  cd backend && .venv/bin/pytest tests/                            # 防回归全套
  cd backend && .venv/bin/ruff check . && .venv/bin/mypy app/models/kpi_target.py app/services/kpi_service.py app/routers/kpi.py
  ```
- **完工提交序列**:
  1. `test(kpi): backfill achievement-with-data + POST insert + manager RBAC`(只含 `backend/tests/test_kpi_phase9.py`)
  2. `docs(kpi): Phase 9 recap + plan §9 actual landing path`(只含 `docs/recap.md` + `docs/implementation-plan.md`)
  3. `chore(progress): close T-907 + Phase 9 closeout`(只含 `docs/dev_tasks.md`,Task 7 → `[x]`)
- **完工后**: 立即停手,等指挥官最终二次验收 + Phase 9 整体 PR 闭环。**不要**自动进 Phase 10,**不要**自动 `git push`。
