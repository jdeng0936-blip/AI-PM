# T-905 执行契约 — KPI 管理页前端 `/admin/kpi`

> **任务编号**: T-905
> **任务名**: Phase 9 KPI 目标管理页（`/admin/kpi`）+ API 客户端模块
> **指挥官**: Claude (QA & Refactor Specialist)
> **执行人**: Codex (Worker)
> **前置**: T-904 已落地（HEAD: `bcdb990`），后端三层（model / service / router）+ 9 个 pytest 全绿。整 backend 测试套 **157 passed + 2 skipped**，无回归。
> **依赖**: 既有 `frontend/src/api/request.ts` (axios + JWT 拦截器)、`frontend/src/stores/use-auth-store.ts` (`userRole / isAdmin`)、`frontend/src/app/users/page.tsx` (admin 表格 + Modal 样板)、sonner toast、lucide-react icon。
> **后端契约**: `GET /api/v1/admin/kpi/` (list) / `POST /api/v1/admin/kpi/` (upsert, 200) / `GET /api/v1/admin/kpi/achievement` (T-906 才用,本契约不调)。RBAC: admin + manager。

---

## 1. 任务目标

让 admin / manager 可以通过 Web UI **管理 KPI 目标**：

1. 列表展示：表格列出所有 KPI 目标（`scope / scope_value / metric / period / target_value / 更新时间`）。
2. 新增目标：点「+ 新建目标」打开 Modal，填四元组 + target_value，POST 后刷新表格。
3. 编辑目标：表格行点「编辑」回填 Modal，target_value 可改，四元组保持只读（因为后端 upsert 走 UNIQUE 约束，改四元组等于换主键）。
4. 权限：页面入口仅 `admin` 或 `manager` 可见 —— 其它角色 redirect `/`。

**不在本契约范围**：达成率仪表盘（T-906 另发）、删除目标（plan §9 暂未要求 DELETE 端点，后端也未提供）、批量操作。

---

## 2. 范围边界

### 范围内 (IN)

- **新建** `frontend/src/api/kpi.ts` —— API 客户端封装 + TS 类型（约 50 行）。
- **新建** `frontend/src/app/admin/kpi/page.tsx` —— 管理页主组件（预计 300-400 行，对标 `users/page.tsx` 但更轻量,只有一种 Modal）。
- **不**改 `frontend/src/stores/use-auth-store.ts`（auth-store 未导出 `isManager`,本契约直接用 `userRole === 'admin' || userRole === 'manager'` 判,避免污染全局 store）。
- **不**改 `frontend/src/components/sidebar.tsx`（侧边栏入口的添加由用户后续手动 PR 或 T-905 Codex 在交付摘要里 propose，但**契约不强制改 sidebar** —— 防止改坏导航顺序）。

### 范围外 (OUT)

- 不改后端任何文件（T-901/T-902/T-903 凝固，T-904 测试凝固）。
- 不写前端测试（前端测试惯例此项目暂未铺开，看板没要求）。
- 不写 `frontend/src/app/dashboard/page.tsx`（T-906 是 dashboard 面板的契约）。
- 不动 `lib/axios.ts`（虽和 `api/request.ts` 双份冗余，但本契约不做技术债清理）。
- 不写 i18n key、不动 `tailwind.config.js`、不动主题变量。

---

## 3. API 客户端契约（`frontend/src/api/kpi.ts`）

### 3.1 文件头与 import

```ts
/**
 * API 模块 — KPI 目标管理 (Phase 9)
 *
 * 对接后端 /api/v1/admin/kpi:
 *  - GET  /              列出全部目标
 *  - POST /              创建/更新目标 (后端走 upsert, 200)
 *  - GET  /achievement   达成率快照 (T-906 才用)
 *
 * RBAC: 后端 require_role(admin, manager); 前端入口同步收敛。
 */
import request from '@/api/request'
```

### 3.2 TS 类型

```ts
export type KpiScope = 'global' | 'department' | 'role'
export type KpiMetric = 'submit_rate' | 'avg_score' | 'blocker_resolve_days' | 'objective_completion'
export type KpiPeriod = 'weekly' | 'monthly' | 'quarterly'

export interface KpiTargetOut {
  id: number
  scope: KpiScope
  scope_value: string | null
  metric: KpiMetric
  target_value: number
  period: KpiPeriod
  created_at: string
  updated_at: string
  created_by: string | null
  tenant_id: string
}

export interface KpiTargetIn {
  scope: KpiScope
  scope_value: string | null
  metric: KpiMetric
  target_value: number
  period: KpiPeriod
}
```

> **要点**:
> - `id` 是 `number`（后端 SQLAlchemy Integer autoincrement，不是 UUID）。
> - `created_by` 是 `string | null`（UUID 字符串，可能为 null —— seed 4 行的 created_by 都是 null）。
> - `scope` 字面量用 `'global'`（不是 `'global_'`，因为后端 Pydantic 用 `values_callable` 已经把 `KpiScope.global_` 映射成 DB 字符串 `'global'`）。

### 3.3 API 调用

```ts
export const listKpiTargets = (): Promise<KpiTargetOut[]> =>
  request.get('/admin/kpi/')

export const upsertKpiTarget = (payload: KpiTargetIn): Promise<KpiTargetOut> =>
  request.post('/admin/kpi/', payload)
```

> **要点**:
> - 路径末尾**必须带斜杠** `/admin/kpi/`（FastAPI `prefix="/api/v1/admin/kpi"` + `@router.get("/")` 合成 `/api/v1/admin/kpi/`；request.ts `baseURL='/api/v1'`，所以前端传 `'/admin/kpi/'`）。
> - 响应拦截器已经把 `.data` 解出来，所以返回类型直接是 payload（不是 AxiosResponse 包裹）。

---

## 4. 页面契约（`frontend/src/app/admin/kpi/page.tsx`）

### 4.1 文件头

```tsx
/**
 * frontend/src/app/admin/kpi/page.tsx — KPI 目标管理 (Phase 9 / admin + manager)
 *
 * 业务流程:
 *  1. 进入页 → 校验 userRole ∈ {admin, manager},否则 toast + redirect /
 *  2. 加载列表 (loadTargets) → 表格展示
 *  3. 点「+ 新建目标」 → Modal 打开,空表单,提交走 upsert
 *  4. 点行「编辑」 → Modal 打开,四元组只读,target_value 可改,提交走 upsert (后端复用现有 id)
 *
 * 后端 RBAC: admin + manager;前端入口双层守卫,后端是真正的安全边界。
 */
'use client'
```

### 4.2 组件骨架与状态

```tsx
import { useEffect, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Plus, Pencil } from 'lucide-react'
import { useAuthStore } from '@/stores/use-auth-store'
import {
  listKpiTargets,
  upsertKpiTarget,
  type KpiScope,
  type KpiMetric,
  type KpiPeriod,
  type KpiTargetOut,
} from '@/api/kpi'

const SCOPE_OPTIONS: { value: KpiScope; label: string }[] = [
  { value: 'global', label: '全公司' },
  { value: 'department', label: '部门' },
  { value: 'role', label: '岗位' },
]

const METRIC_OPTIONS: { value: KpiMetric; label: string }[] = [
  { value: 'submit_rate', label: '日报提交率(%)' },
  { value: 'avg_score', label: '日报均分' },
  { value: 'blocker_resolve_days', label: '阻塞解决天数' },
  { value: 'objective_completion', label: 'OKR 完成率(%)' },
]

const PERIOD_OPTIONS: { value: KpiPeriod; label: string }[] = [
  { value: 'weekly', label: '周' },
  { value: 'monthly', label: '月' },
  { value: 'quarterly', label: '季' },
]

export default function KpiAdminPage() {
  const router = useRouter()
  const { userRole } = useAuthStore()
  const canManage = userRole === 'admin' || userRole === 'manager'

  const [rows, setRows] = useState<KpiTargetOut[]>([])
  const [loading, setLoading] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState<{
    scope: KpiScope
    scope_value: string
    metric: KpiMetric
    period: KpiPeriod
    target_value: string  // 保持 string，submit 时 parseFloat
  }>({
    scope: 'global',
    scope_value: '',
    metric: 'submit_rate',
    period: 'monthly',
    target_value: '',
  })

  // 权限守卫 (后端是真边界,前端只是体验)
  useEffect(() => {
    if (userRole && !canManage) {
      toast.error('需 admin 或 manager 权限')
      router.replace('/')
    }
  }, [userRole, canManage, router])

  const loadTargets = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await listKpiTargets()
      setRows(Array.isArray(res) ? res : [])
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '加载 KPI 目标失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (canManage) {
      loadTargets()
    }
  }, [canManage, loadTargets])
  // ... (open/submit/render 见 §4.3 ~ §4.5)
}
```

### 4.3 Modal 打开 / 编辑 / 提交逻辑

```tsx
function openCreate() {
  setEditingId(null)
  setForm({ scope: 'global', scope_value: '', metric: 'submit_rate', period: 'monthly', target_value: '' })
  setDialogOpen(true)
}

function openEdit(row: KpiTargetOut) {
  setEditingId(row.id)
  setForm({
    scope: row.scope,
    scope_value: row.scope_value ?? '',
    metric: row.metric,
    period: row.period,
    target_value: String(row.target_value),
  })
  setDialogOpen(true)
}

async function handleSubmit() {
  // 客户端校验 (避免无谓 422)
  const targetNum = parseFloat(form.target_value)
  if (!Number.isFinite(targetNum) || targetNum <= 0) {
    toast.error('target_value 必须 > 0')
    return
  }
  if (form.scope === 'global' && form.scope_value.trim() !== '') {
    toast.error('全公司 scope 必须留空 scope_value')
    return
  }
  if ((form.scope === 'department' || form.scope === 'role') && form.scope_value.trim() === '') {
    toast.error('部门/岗位 scope 必须填写 scope_value')
    return
  }

  setSubmitting(true)
  try {
    await upsertKpiTarget({
      scope: form.scope,
      scope_value: form.scope === 'global' ? null : form.scope_value.trim(),
      metric: form.metric,
      period: form.period,
      target_value: targetNum,
    })
    toast.success(editingId ? '已更新目标' : '已创建目标')
    setDialogOpen(false)
    await loadTargets()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || '提交失败')
  } finally {
    setSubmitting(false)
  }
}
```

### 4.4 渲染：表格

参考 `users/page.tsx:300-420` 表格样式（thead / tbody / 行样式 + Pencil icon 列）。**必须**用主题 CSS 变量（`var(--color-bg-card) / var(--color-text-primary) / var(--color-border-subtle)` 等），**不要**写死颜色 hex。

表格列：

| 列 | 来源 | 渲染 |
|---|---|---|
| 范围 | `scope` | `SCOPE_OPTIONS.find(o => o.value === row.scope)?.label` |
| 范围值 | `scope_value` | `row.scope_value ?? '—'` |
| 指标 | `metric` | `METRIC_OPTIONS.find(...)?.label` |
| 周期 | `period` | `PERIOD_OPTIONS.find(...)?.label` |
| 目标值 | `target_value` | 直接显示数字（avg_score 不带单位，rate 类显示 `%`） |
| 更新时间 | `updated_at` | `new Date(row.updated_at).toLocaleString('zh-CN')` |
| 操作 | — | `<button onClick={() => openEdit(row)}>编辑</button>` (lucide Pencil 图标 + 文字) |

页头：`<h1>KPI 目标管理</h1>` + 右上角 `<button onClick={openCreate}><Plus /> 新建目标</button>` 渐变蓝紫（参考 `users/page.tsx:284-286` 既有样式）。

空态：`rows.length === 0 && !loading` 时显示 `<div className="text-center py-12">暂无 KPI 目标</div>`。

### 4.5 渲染：Modal

完全照 `users/page.tsx:429-472` 的样板（`fixed inset-0 z-50 bg-black/50` 外层 + `rounded-2xl p-6` 卡片）。

字段顺序：scope (select) → scope_value (input,scope='global' 时 disabled) → metric (select) → period (select) → target_value (input type="number" step="0.01")。

**编辑模式下 scope/scope_value/metric/period 全部 `disabled`**，提示文字「该目标已存在,只能修改目标值」。

按钮：「取消」+「保存」（提交中显示「提交中...」），渐变蓝紫。

---

## 5. 验证标准

```bash
cd frontend

# 1) 静态检查
npm run lint
npm run typecheck

# 2) 构建烟测（最权威的 Next.js 类型/路由完整性闸门）
npm run build
```

三项必须全绿。

### 5.2 真机手测（指挥官二次验收会跑，Codex 可选自测）

启动后端 + 前端：

```bash
# 后端 (假设已启)
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8001
# 前端
cd frontend && npm run dev
```

浏览器登录 admin 身份 → 访问 `http://localhost:3000/admin/kpi`：

- 进入页表格显示 4 行 seed 目标。
- 「+ 新建目标」打开 Modal,填 `scope=department / scope_value=技术部 / metric=avg_score / period=monthly / target_value=85` → 成功 toast + 表格增到 5 行。
- 行点「编辑」→ Modal 四元组全 disabled,只 target_value 可改 → 改成 90 提交 → toast 「已更新目标」+ 表格行更新。

登录 employee 身份 → 访问 `/admin/kpi` → toast 红色 + 立即 redirect `/`。

---

## 6. 提交规约

**两条原子 commit**：

1. `feat(kpi): add admin KPI targets management page`
   - 含 `frontend/src/api/kpi.ts`（新建）+ `frontend/src/app/admin/kpi/page.tsx`（新建）2 个文件。
   - Body 简述：admin/manager 可访问、列表/upsert 双流程、Modal 编辑时四元组锁、客户端三层校验（target_value>0 / global 不带 scope_value / dept&role 必须带 scope_value）匹配后端 422。
2. 修改 `docs/dev_tasks.md` Task 5 方括号 `[/]` → `[x]`，然后：
   - `chore(progress): close T-905`

---

## 7. 不在本契约内的事项

- **不要**改 `frontend/src/components/sidebar.tsx`。如果觉得入口缺失，写在 commit body 里 propose，由指挥官在 T-906 或之后一并处理。
- **不要**改 auth-store 增加 `isManager`。本契约规定用 `userRole === 'admin' || userRole === 'manager'` 直接判断。
- **不要**写 `delete` API 或按钮（后端无端点）。
- **不要**做 `apiFetch` helper 重构（项目里 axios 实例已经统一）。
- **不要**碰 `frontend/src/app/dashboard/page.tsx`（T-906 contract）。
- **不要**写前端测试（项目里 frontend 测试惯例尚未铺开，本任务不破坏现状）。
- **不要**自作主张引入 shadcn/ui 或 react-hook-form（项目当前没有这些依赖，引入是大改）。

---

## 8. 风险与注意点

1. **`scope` 字面量陷阱**: 后端 Python enum 写 `KpiScope.global_`（带下划线，因为 `global` 是保留字），但 DB 字符串和 Pydantic 序列化都是 `'global'`。前端 TS 一定用 `'global'`，**不要**抄成 `'global_'`。
2. **路径斜杠**: `'/admin/kpi/'` **必须**带尾斜杠。FastAPI 会把不带尾斜杠的请求 307 重定向到带尾斜杠，axios 默认会跟随重定向但有性能损失。
3. **`target_value` 类型**: 后端 Pydantic `gt=0`（严格大于 0），前端先 `parseFloat` 校验。`avg_score` 没有百分号语义,`submit_rate` 是 0-100 的百分数,Modal 里**不**强制约束 100 上限（plan §9 没有这个约束,后端也没设）。
4. **`scope_value` null 与空字符串**: 后端 Pydantic `@model_validator` 把 `''` strip 成 None,但**前端最好显式发 null**（`form.scope === 'global' ? null : form.scope_value.trim()`），避免依赖后端 normalization。
5. **编辑时锁四元组**: 后端走 ON CONFLICT DO UPDATE，按 UNIQUE 约束 `(scope, scope_value, metric, period)` 匹配。如果用户在编辑时改了四元组，后端**不会**报错而是**创建一条新行**（因为新四元组没有冲突）。所以前端必须 disable，防止"编辑变创建"的意外。
6. **Toast 错误展开**: 后端 422 的错误体是 `{detail: [{loc, msg, type}, ...]}`，直接 `e?.response?.data?.detail` 会是数组。Codex **可以**保持现样板（数组 toast 会显示 `[object Object]`），也**可以**做一行 `Array.isArray(detail) ? detail[0]?.msg : detail`。**契约不强制**，但写在 commit body 里说明你选了哪种。
7. **`userRole` hydrate 时序**: auth-store hydrate 是异步的（参考 `auth-guard.tsx:21-27`），首次渲染 `userRole === ''`。`useEffect` 守卫 `if (userRole && !canManage)` 的 `userRole &&` 是关键 —— 没它会在 hydrate 前误判为非法角色把 admin 也 redirect 走。
8. **构建闸门权威性**: `npm run typecheck` 走 `tsc --noEmit`，而 `npm run build` 走 Next.js 完整构建 + 路由扫描。**两个都要绿** —— typecheck 漏掉 app router 的路由层错误（如 `default export` 缺失），build 会抓到。

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌，供 PM 探针自动提取**

- **当前持牌任务**: **T-905** —— Phase 9 KPI 管理页前端（`/admin/kpi` + API 客户端模块）。看板已锁 `[/]`，不要重复 `chore(lock)`。
- **执行入口**: 阅读本契约 §3 / §4，对标 `frontend/src/app/users/page.tsx` 既有 admin 表格 + Modal 样板和 `frontend/src/api/users.ts` API 模块样板，直接编码。
- **核心交付**:
  1. `frontend/src/api/kpi.ts` —— 类型 + 2 个端点封装（`listKpiTargets` / `upsertKpiTarget`），约 50 行。
  2. `frontend/src/app/admin/kpi/page.tsx` —— 主页面（约 300-400 行），包含表格 + Modal + 三层客户端校验 + auth-store hydrate 友好的角色守卫。
- **闸门**: `cd frontend && npm run lint && npm run typecheck && npm run build` 三连必须全绿。详见 §5。
- **完工提交序列**:
  1. `feat(kpi): add admin KPI targets management page`
  2. 改 `docs/dev_tasks.md` Task 5 → `[x]`，再提 `chore(progress): close T-905`
- **完工后**: 立即停手，等指挥官二次验收（指挥官会跑 lint/typecheck/build + 真机手测 admin 路径 + employee redirect）。**不要**自行进入 T-906（达成率仪表盘面板是 T-905 二次验收通过后另发的契约）。
- **验收通过的判定**: §5 三个 npm 命令全绿；指挥官能复现 §5.2 三个真机场景（admin 列出 seed 4 行 / 新建 + 编辑成功 / employee 被 redirect）。

**契约生效。Codex 收到后请确认 `git log -1 --oneline` 包含 `chore(spec): T-905`，然后开干。**
