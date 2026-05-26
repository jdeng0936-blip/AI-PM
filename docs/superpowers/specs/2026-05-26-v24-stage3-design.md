# V2.4 Stage 3 — 软删配套功能完整化(Design Spec)

**作者**: Claude (Opus 4.7)
**日期**: 2026-05-26
**前置**: V2.4 Stage 1 (`c61b570`) + Stage 2 (`dfee00b` / `1e787d7` / `826fbd4`)
**状态**: 已通过用户两轮澄清,等待最终 spec 审核

---

## 1. 背景

V2.4 Stage 2 已经在 `daily_reports` / `projects` 两张表加了 `deleted_at TIMESTAMPTZ` 列,并在 3 个金路径(reports / projects / users)接入了多选 + 批量软删 UI。但当时为了控制范围,**有意没做**几件事:

- **C1 · 软删过滤的"长尾"覆盖**:Stage 2 只审了"列表/详情/聚合"主路径;`chat_tools/*`(AI 工具)、`kr_progress_extractor`、`retro/collectors`、`gates`、`simulate`、`export` 等共 8 个文件直接 `select(DailyReport)` 没加 `.where(deleted_at.is_(None))` — 后果是**AI 周报/季报/导出能看到已删的脏数据**。
- **C2 · users 还原分页**:Stage 1 把 `USERS_PAGE_SIZE` 从 20 临时调到 100 让前端能纯客户端筛全员;tech debt 必须还原。
- **C3 · 撤销功能**:Stage 2 删完只 toast 一句"已删除 N 条",误删无救济。
- **C4 · 回收站**:已删数据完全藏起来,admin 想找都找不到。

Stage 3 一次性把这 4 项配套功能补齐,关单 V2.4 大需求。

---

## 2. 范围(已通过用户澄清)

### 2.1 决策日志

| # | 议题 | 决策 | 理由 |
|---|---|---|---|
| Q1 | 回收站是否支持"永久删除"(hard DELETE) | **否,只支持恢复** | 与 V2.4 一贯"保护历史数据完整性"原则一致;避免破坏 FK(daily_report.user_id、ai_score 上游、OKR KR 关联) |
| Q2 | users pageSize 还原后筛选怎么办 | **后端加 query 参数,前端改 server-side 筛选** | 体验完整(能跨全量筛);后端代价低(+30 行 query) |

### 2.2 任务包

```
C1 · chat_tools/* + 5 个文件补 deleted_at IS NULL 过滤
C2 · users 还原 pageSize=20 + 后端 query 参数(role/department/is_active)
C3 · 撤销端点 + toast undo action
C4 · 回收站页面 /admin/recycle-bin(admin only)
C5 · §15 文档 + 通过数 /14 → /15
```

### 2.3 串行/并行

```
C1 ─┐
C2 ─┤
    ├─→ C5 (docs)
C3 ─┤
C4 ─┘
```

C1/C2/C3/C4 4 个任务无关键路径,可全并行;C5 在 C1-C4 全部 land 后写。**C3 和 C4 共享后端 batch-restore 端点,C3 先实现端点,C4 直接复用**。

---

## 3. API 契约

### 3.1 新增:批量恢复(C3 + C4 共享)

```
PATCH /api/v1/reports/batch-restore
Body: { "ids": ["uuid", ...] }       # 1..200
Permission:
  - admin / manager: 任意 ids
  - employee: 服务端 AND user_id == current_user.id(不信前端)
Logic:
  UPDATE daily_reports
     SET deleted_at = NULL
   WHERE id IN (...) AND deleted_at IS NOT NULL
     [AND user_id = $current_user_id]   -- employee 角色加这条
RETURNING id
Response: { requested: int, restored_count: int, restored_ids: [str] }
```

```
PATCH /api/v1/projects/batch-restore
Body: { "ids": ["uuid", ...] }       # 1..50
Permission: admin only
Logic:
  UPDATE projects
     SET deleted_at = NULL
   WHERE id IN (...) AND deleted_at IS NOT NULL AND is_temporary = true
RETURNING id
Response: { requested: int, restored_count: int, restored_ids: [str] }
```

**主干项目(非 is_temporary)的"撤销归档"复用现有 `unarchive_project` 端点**,不在本 Stage 新增。

### 3.2 扩展:users 列表 query

```
GET /api/v1/users (扩展)
Query (新增):
  role: enum?              # admin / manager / employee
  department: str?         # 精确匹配
  is_active: bool?         # true / false
  (search / page / page_size 保留不变)
Permission: admin (沿用现有)
```

### 3.3 扩展:回收站列表 query

```
GET /api/v1/reports?include_deleted=true
  - 默认 false(沿用 Stage 2:仅返回 deleted_at IS NULL 的)
  - true 时仅返回 deleted_at IS NOT NULL 的(注意:不是"全部",是"仅已删")
  - Permission: admin only(非 admin 即使传 true 也强制改回 false)

GET /api/v1/projects?include_deleted=true
  - 同上,仅返回 deleted_at IS NOT NULL 且 is_temporary=true 的
  - Permission: admin only
```

**users 没有"回收站"端点** — V2.4 Stage 2 的 `POST /users/batch-enable` 已是 restore 语义,前端"已禁用用户"过滤已可实现"软回收站"。

---

## 4. 前端组件与数据流

### 4.1 C3 · toast undo 改造(零新组件,改 5 处调用)

**核心模式**(sonner 标准用法):

```typescript
toast.success(`已删除 ${n} 条`, {
  duration: 5000,
  action: {
    label: '撤销',
    onClick: async () => {
      await batchRestoreReports(ids)
      await refreshList()
      toast.success(`已撤销恢复 ${n} 条`)
    }
  }
})
```

**改造点清单**:

| 文件 | 调用 | 撤销端点 |
|---|---|---|
| `frontend/src/app/reports/page.tsx` | 批量软删 toast | `batchRestoreReports` |
| `frontend/src/app/dashboard/page.tsx` | 批量软删 toast | `batchRestoreReports` |
| `frontend/src/app/projects/page.tsx` | 批量软删 toast(临时项目) | `batchRestoreProjects` |
| `frontend/src/app/projects/page.tsx` | 批量归档 toast(主干项目) | `unarchiveProject` 循环(已存在) |

**Stage 2 已确认 reports / dashboard / projects 三页面都有批量删入口**,无 "if branch"。实现时按本表 4 个改造点逐一接入。

**不涵盖单条删/归档的 undo**:Stage 2 没做单条软删 UI,本 Stage 也不补 — 单条操作走"页面直接刷新"反馈即可,不引入 toast undo 复杂度。

### 4.2 C4 · 回收站页面

**路径**: `frontend/src/app/admin/recycle-bin/page.tsx`(新建,~200 行)

**结构**:

```
┌─────────────────────────────────────────┐
│ 🗑 回收站 (仅 admin 可见)                │
├─────────────────────────────────────────┤
│ [日报 (3)] [临时项目 (2)]   ← Tab 切换  │
├─────────────────────────────────────────┤
│ ☐ 全选            [恢复选中] (purple)   │
│ ☐ 2026-05-25 · 张三 · 测试日报           │
│ ☐ 2026-05-24 · 李四 · ...               │
│ ...                                      │
└─────────────────────────────────────────┘
```

**复用现有组件**:
- `useMultiSelect` Hook (Stage 2 成果)
- `ListActionBar` 组件
- 不复用 `FilterBar`(V1 不加 filter,保持页面极简)

**权限保护**(双层):

1. **客户端**:页面顶部 `useEffect` 检查 `currentUser?.role === 'admin'`,非 admin 时 `router.replace('/')` + `toast.error('需 admin 权限')`
2. **服务端**:GET 端点对 `include_deleted=true` 强制校验 admin role

**入口位置**:右上角用户菜单下拉 → `🗑 回收站`(admin 才显示)。具体在 `frontend/src/components/layout/header.tsx`(或对应处)加一项;实现时若该组件不存在,沿用项目现有的菜单挂载方式。

### 4.3 C2 · users 改 server-side 筛选

**改法**:保留 `useListFilters` 的 UI 控件,把内部 `filteredItems` 用 `useEffect` 监听 filter 变化时触发后端 fetch。

```typescript
const { filters, setFilter, clearAll } = useListFilters(users, FILTER_SPEC)

useEffect(() => {
  loadUsers({
    page: 1,
    page_size: 20,
    role: filters.role,
    department: filters.department,
    is_active: filters.is_active,
  })
  setCurrentPage(1)
}, [filters.role, filters.department, filters.is_active])
```

**关键**:`useListFilters` 返回的 `filteredItems` 在 server-side 模式下应直接等于原 `items`(避免重复过滤);Hook 已有"传 raw items 就不过滤"的语义,实现时验证。

`USERS_PAGE_SIZE` 还原为 `20`;Stage 1 的注释删除。

---

## 5. C1 长尾过滤增补清单

Stage 2 已确认"漏审"的文件列表(由 `grep -rln "DailyReport\." backend/app/services/ backend/app/routers/`)排查得出):

| # | 文件 | 用途 | 改法 |
|---|---|---|---|
| 1 | `backend/app/services/chat_tools/reports.py` | AI 工具:查日报 | 所有 `select(DailyReport)` 加 `.where(DailyReport.deleted_at.is_(None))` |
| 2 | `backend/app/services/chat_tools/weekly_report.py` | AI 工具:周报生成 | 同上 |
| 3 | `backend/app/services/chat_tools/people.py` | AI 工具:查人员动态 | 同上 |
| 4 | `backend/app/services/kr_progress_extractor.py` | KR 自动抽取 | 同上(注意参数是单个 report,但调用方需过滤) |
| 5 | `backend/app/services/retro/collectors.py` | 复盘数据收集 | 同上 |
| 6 | `backend/app/routers/gates.py` | 阶段闸门检查 | 同上 |
| 7 | `backend/app/routers/simulate.py` | 模拟 dry-run | 同上 |
| 8 | `backend/app/routers/export.py` | 数据导出 | 同上 |

**Project 模型也需 grep 一遍**:命令 `grep -rln "select(Project\." backend/app/`,把 Stage 2 漏掉的同样补 `.where(Project.deleted_at.is_(None))`。

**按子目录分组 commit**(避免 8 个琐碎提交,但保留 review 友好):

1. `fix(soft-delete): chat_tools/* 补 daily_report deleted_at 过滤`(3 个文件)
2. `fix(soft-delete): kr_progress_extractor + retro/collectors 补 deleted_at 过滤`(2 个文件)
3. `fix(soft-delete): gates/simulate/export routers 补 deleted_at 过滤`(3 个文件)

Project 模型若有漏审则合并到对应 commit,不另起。

---

## 6. 测试策略

| 任务 | 验证方式 |
|---|---|
| C1 | grep 确认所有文件加了过滤;手动:删一条日报 → AI 周报问"上周谁写了日报"→ 已删的不出现 |
| C2 | `curl 'GET /users?role=manager'` 只返回 manager;浏览器切 FilterBar 看 Network 触发 fetch;翻页正常 |
| C3 | 删一批 → toast 弹出 → 5 秒内点撤销 → 列表恢复;5 秒后 toast 消失,按钮不可点 |
| C4 | admin 进 /admin/recycle-bin 看见已删项;勾 2 条点恢复;回到 /reports 看见;employee 直接访问被踢回首页 |
| C5 | docs/MVP_VERIFICATION.md §15 三段操作步骤可被人手动跑通 |

---

## 7. 风险与取舍

1. **C1 grep 漏审** — 已 grep 列出 8 个文件;C1 第一步 reconfirm 一遍 grep,以防后续提交里又有新增。
2. **C3 toast 撤销过期后用户找不到** — 默认行为(sonner 标准),回收站(C4)是兜底;不另加 IndexedDB / localStorage 持久化撤销栈。
3. **C4 回收站无分页** — 假设软删数据 < 1000 条;若运营场景大量软删,V2.5 加分页。
4. **C2 filter 变化无 debounce** — useEffect 依赖 filter 字段变化即 fetch;15 人公司无性能瓶颈,V2.5 加 debounce。
5. **路由权限弱** — Next.js 无中间件层,仅客户端 useEffect + 后端 API 双校验;短时间内 admin 短链分享可被滥用,但与项目现有权限模式一致,不破新规。
6. **撤销 archive 项目复用 unarchive** — `unarchive_project` 已存在;若批量归档撤销需"一次撤多个",前端需循环调单端点;< 50 个项目可接受,不开新批量端点。
7. **C2 useListFilters server-side 改造可能引入 race condition** — 用户快速切多个 filter 时 fetch 会有并发,后到的结果覆盖先到的可能造成"看到不是当前选择"的数据。本 Stage 不解决(< 200ms 后端响应 + 单用户场景概率极低);V2.5 加 AbortController。

---

## 8. Critical Files

**后端新增**:
- `backend/app/routers/reports.py`(加 `/batch-restore` + 扩展 list query `include_deleted`)
- `backend/app/routers/projects.py`(加 `/batch-restore` + 扩展 list query `include_deleted`)
- `backend/app/routers/users.py`(扩展 list query `role` / `department` / `is_active`)

**后端补过滤**:
- `backend/app/services/chat_tools/{reports,weekly_report,people}.py`
- `backend/app/services/kr_progress_extractor.py`
- `backend/app/services/retro/collectors.py`
- `backend/app/routers/{gates,simulate,export}.py`

**前端新增**:
- `frontend/src/app/admin/recycle-bin/page.tsx`(新建)
- `frontend/src/api/{reports,projects}.ts`(加 `batchRestoreReports` / `batchRestoreProjects`)
- `frontend/src/api/users.ts`(扩展 `getUsers` query 参数)

**前端改造**:
- `frontend/src/app/users/page.tsx`(还原 pageSize=20 + server-side filter)
- `frontend/src/app/reports/page.tsx`(toast undo)
- `frontend/src/app/projects/page.tsx`(toast undo)
- `frontend/src/app/dashboard/page.tsx`(toast undo,若有删入口)
- 用户菜单组件(加"回收站"入口,仅 admin)

**文档**:
- `docs/MVP_VERIFICATION.md`(§15 + /15)

---

## 9. 不做(留 V2.5+)

- 永久删除 / 30 天自动清理(用户已明确否决)
- 撤销栈持久化(关页刷新仍可撤销)
- 回收站分页 / FilterBar
- 回收站操作审计日志(谁恢复了什么)
- C2 filter debounce + AbortController
- `<CreateProjectModal />` 共享组件(V2.3 / V2.4 都遗留过的 tech debt)

---

## 10. 验收标准(Definition of Done)

- [ ] C1 8 个文件都加了 `.where(DailyReport.deleted_at.is_(None))`(grep 验证)
- [ ] 删一条日报后,AI 周报 / 数据导出 / 闸门检查 / 复盘 都不再看到该日报
- [ ] C2 `GET /users?role=manager&is_active=true` 工作正常;前端 FilterBar 触发 fetch;USERS_PAGE_SIZE=20
- [ ] C3 reports / projects 批量删后 5 秒内可撤销;过期不可撤销
- [ ] C4 admin 进 /admin/recycle-bin 可恢复已删日报/项目;employee 被拦截
- [ ] C5 §15 三段操作步骤跑通;通过数 /15
- [ ] 所有 commit 走 ruff/eslint pre-commit 不破网;tsc 不报错
