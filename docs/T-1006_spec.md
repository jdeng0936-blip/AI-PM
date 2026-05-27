# T-1006 实施契约 — Phase 10 前端管理后台 + Dashboard Tabs 切换器

> **签字时间戳**: `[2026-05-27 21:34:30]`
> **指挥官**: Claude(Opus 4.7 1M context)
> **执行者**: Codex
> **当前 HEAD(契约签字时)**: `63986fa docs(tasks): T-1007 验收通过`
> **前置依赖**(全部已完工 ✅):T-1003(Department / ProjectMember ORM) + T-1004(/admin/departments 5 端点) + T-1005(/admin/reports 1 端点) + T-1007(后端 18 case 测试护栏)

---

## §1 任务背景

Phase 10 后端契约护栏(T-1003~T-1005 + T-1007)已全部闭环,178 个测试 case 零回归。**T-1006 是 Phase 10 唯一剩余的功能性任务**,任务范围是把后端两个新端点(`/admin/departments` + `/admin/reports`)接入前端:

- **管理后台页**:新建 `/admin/departments` 路由,提供部门增删改查 UI(列表 + Modal 新建/编辑 + 删除确认)。
- **监控台分组切换器**:在现有 `/dashboard` 顶部追加一个三态 Tabs(全员 / 按部门 / 按项目),`按部门` / `按项目` 切换时调 `/admin/reports?group_by=department|project` 并以 5 列表格渲染。

**为什么选 T-1006 而非 T-1008**:① T-1008 是文档收尾(implementation-plan §10 + recap),需要在所有功能性任务完工后才能记录完整 6 列对照表;② T-1006 是 Phase 10 闭环的最后一块功能拼图,完工后才能开始 T-1008;③ 后端 API 已 178 测试护栏,前端实施风险面已经最小化。

---

## §2 任务范围

### 2.1 文件变更清单(锁定 ±0,严禁夹带)

| 类型 | 路径 | 行数估计 | 说明 |
|------|------|----------|------|
| **新建** | `frontend/src/api/admin.ts` | ~110 行 | 6 个 API 函数 + 6 个类型导出 |
| **新建** | `frontend/src/app/admin/departments/page.tsx` | ~280 行 | 列表 + Modal(新建/编辑) + 删除 confirm |
| **修改** | `frontend/src/app/dashboard/page.tsx` | +60 / -0 行(局部插入) | Tabs 切换器 + 分组表格 |
| **修改** | `frontend/src/components/sidebar.tsx` | +1 / -0 行 | `ADMIN_ITEMS` 数组追加部门管理 |
| **修改** | `docs/dev_tasks.md` | +1 / -1 行 | Task 6 状态 → `[x]` |

### 2.2 严禁触碰边界(违反立即回滚)

1. **不动后端** — 不改任何 `backend/` 下文件,包括 `app/` / `tests/` / `alembic/`。
2. **不动 conftest.py** / 任何既有测试文件 / `seed_data.py`。
3. **不引入新 npm 依赖** — 全部使用 `package.json` 现有库(`@/api/request` axios / lucide-react / sonner / react / next)。
4. **不动现有 UI 体例** — `Dashboard` 5 个 sections(统计卡片 / AI 日报明细 / 未汇报名单 / 项目健康矩阵 / 风险阻碍池)在 `viewMode='all'` 时保持 100% 现状,**严禁**重排/重写。
5. **不动 `@/components/charts`** / `KpiAchievementPanel` / `FilterBar` / `ListActionBar` / `Sidebar` 之外的现有组件。
6. **不动其它 admin 子路由**(`/admin/kpi` / `/admin/recycle-bin`)。
7. **不动 `@/stores/use-auth-store`** / `@/lib/axios` / `@/api/request` 既有逻辑。
8. **不动 4 既定 untracked 文件**:`.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md` / `backend/uv.lock`,永远 untracked。
9. **不动 📣 锚点**(留给指挥官 T-1006 验收后统一替换)。
10. **不写自动化测试**(本契约纯前端 UI 工作,T-1007 已覆盖后端 18 case;前端测试不在 Phase 10 SOW)。
11. **不引入 date picker / manager dropdown**(降复杂度,见 §3.3 / §3.4 设计签字)。
12. **不 `git push`** / 不自启 T-1008。

---

## §3 设计决策签字(指挥官锁定,Worker 不得偏离)

### 3.1 Tabs 切换器组件签字

**位置**:`Dashboard` 标题"监控台"下方,4 个统计卡片**之上一行**(`page.tsx` 现有 L392 之后插入)。

**形态**:扁平按钮组(3 个 button),非真正的 Tabs 组件库。

```tsx
<div className="flex items-center gap-2 mb-4">
  <button
    type="button"
    onClick={() => setViewMode('all')}
    className="px-4 py-1.5 rounded-md text-sm transition-colors"
    style={{
      background: viewMode === 'all' ? '#3b82f6' : 'transparent',
      color: viewMode === 'all' ? '#fff' : '#94a3b8',
      border: viewMode === 'all' ? 'none' : '1px solid #334155',
    }}
  >
    全员视图
  </button>
  {/* by_department 按钮 */}
  {/* by_project 按钮 */}
</div>
```

**可见性**:**仅 admin + manager 可见**;employee 在 `Dashboard` 不显示此 Tabs(employee 默认看到现有全员视图)。

```tsx
const canSeeTabs = userRole === 'admin' || userRole === 'manager'
// JSX 中:
{canSeeTabs && <TabsBlock />}
```

**默认值**:`viewMode = 'all'`(进入页第一次始终是全员)。

**不持久化** — 不写 localStorage / URLSearchParams(避免污染现有 router pattern;切换是临时操作)。

### 3.2 数据源切换签字

| viewMode | 行为 | 数据源 |
|----------|------|--------|
| `'all'` | 显示现有 5 sections(统计卡片 / AI 日报明细 / 未汇报名单 / 项目健康矩阵 / 风险阻碍池),**完全保持现状** | 现有 `getMorningBriefing / getRiskAlerts / getProjectsOverview / getAnalytics*` 调用链 |
| `'by_department'` | **隐藏**现有 5 sections,**显示** 1 个 5 列表格(部门名 / 日报数 / 均分 / 通过数 / 通过率) | `getGroupedReports({group_by: 'department'})` |
| `'by_project'` | **隐藏**现有 5 sections,**显示** 1 个 5 列表格(project_id 短串 / 日报数 / 均分 / 通过数 / 通过率) | `getGroupedReports({group_by: 'project'})` |

**关键约束**:
- 切换到 `by_*` 时**不要清除**现有 sections 的 state(只是不渲染),避免回切 `all` 时重复 fetch。
- `by_*` 模式下**不传** `start_date / end_date / project_id`,让后端走默认窗口(`today-30 ~ today`)。
- 数据加载状态:`useEffect(() => { if (viewMode !== 'all') { loadGrouped() } }, [viewMode])`。

### 3.3 分组表格签字

**形态**:简易 HTML `<table>`,沿用 `Dashboard` 现有表格样式(`bg-slate-900` / `border-slate-800` 同色系)。

```tsx
{viewMode !== 'all' && (
  <section className="rounded-lg border p-6" style={{ borderColor: '#334155', background: '#0f172a' }}>
    <h2 className="text-lg font-semibold mb-4" style={{ color: '#e2e8f0' }}>
      {viewMode === 'by_department' ? '按部门聚合' : '按项目聚合'}
    </h2>
    {groupedLoading ? (
      <div className="text-sm text-slate-400">加载中...</div>
    ) : groupedData.length === 0 ? (
      <div className="text-sm text-slate-400">最近 30 天暂无数据</div>
    ) : (
      <table className="w-full text-sm">
        <thead>
          <tr style={{ color: '#94a3b8' }}>
            <th className="text-left py-2">{viewMode === 'by_department' ? '部门' : '项目 ID'}</th>
            <th className="text-right py-2">日报数</th>
            <th className="text-right py-2">均分</th>
            <th className="text-right py-2">通过数</th>
            <th className="text-right py-2">通过率</th>
          </tr>
        </thead>
        <tbody>
          {groupedData.map((row) => (
            <tr key={row.key} className="border-t" style={{ borderColor: '#1e293b' }}>
              <td className="py-2" style={{ color: '#e2e8f0' }}>{row.key || '(未挂部门)'}</td>
              <td className="text-right py-2" style={{ color: '#e2e8f0' }}>{row.report_count}</td>
              <td className="text-right py-2" style={{ color: '#e2e8f0' }}>{row.avg_score.toFixed(1)}</td>
              <td className="text-right py-2" style={{ color: '#e2e8f0' }}>{row.pass_count}</td>
              <td className="text-right py-2" style={{ color: '#22c55e' }}>{row.pass_rate.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    )}
  </section>
)}
```

**严禁**:不引入 `<CompareBarChart>` / `<TrendLineChart>` 图表组件(降复杂度,T-1008 后再视情况补)。

**`project_id` 展示**:**短串前 8 位**(`row.key.slice(0, 8)` 后加 `...`),完整 UUID 留给 T-1008 加项目名 join 时再优化。

### 3.4 `/admin/departments` 页面签字

**路由**:`frontend/src/app/admin/departments/page.tsx`,使用 `'use client'`。

**RBAC 守卫**:模仿 `frontend/src/app/admin/kpi/page.tsx` L86-103:

```tsx
const { userRole } = useAuthStore()
const canManage = userRole === 'admin' || userRole === 'manager'

useEffect(() => {
  if (userRole && !canManage) {
    toast.error('需 admin 或 manager 权限')
    router.replace('/')
  }
}, [userRole, canManage, router])
```

**页面结构**(从上到下):
1. 标题"部门管理"+ 描述 + "+ 新建部门"按钮(右上角)。
2. 列表 `<table>`,5 列:**部门名 / 负责人 ID / 创建时间 / 更新时间 / 操作**(编辑按钮 + 删除按钮)。
3. Modal 新建/编辑(共用,根据 `editingId` 区分):
   - 字段 1:**部门名称**(text,`min 1 / max 64`,必填)
   - 字段 2:**负责人 user.id**(UUID 文本输入,可选,客户端用 `UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i` 校验,空 = null)
   - 取消 / 确认按钮
4. 删除 confirm(`window.confirm('确认删除部门「' + row.name + '」?')`)。

**严禁**:不引入 `<Select>` / `<Combobox>` / Manager dropdown(避免拉取 `/users?role=manager` 的爆炸面;UUID 复制粘贴足够 admin 使用)。

**错误码 mapping**(toast):
- HTTP 409 `name_conflict` → "部门名称已存在"
- HTTP 400 `manager_not_found` → "指定的 user.id 不存在或非 manager 角色"
- HTTP 400 `department_not_found` → "部门不存在"
- HTTP 403 → "权限不足" + `router.replace('/')`
- 其他 → fallback "操作失败,请重试" + `console.error(error)`

**复用 helper**(从 `frontend/src/app/admin/kpi/page.tsx` L80-84 照搬):

```tsx
function getErrorMessage(error: any, fallback = '操作失败') {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) return detail[0]?.msg || fallback
  return detail || fallback
}
```

### 3.5 侧边栏签字

**`frontend/src/components/sidebar.tsx` L56-62** 的 `ADMIN_ITEMS` 数组,在 `/admin/recycle-bin` **之前**插入一行:

```ts
const ADMIN_ITEMS: NavItem[] = [
  { href: '/chat', label: 'AI 对话', icon: MessageSquare },
  { href: '/users', label: '用户管理', icon: Users },
  { href: '/stats', label: '系统统计', icon: BarChart3 },
  { href: '/export', label: '数据导出', icon: Download },
  { href: '/admin/departments', label: '部门管理', icon: Building2 },  // ← Phase 10 / T-1006 新增
  { href: '/admin/recycle-bin', label: '回收站', icon: Trash2 },
]
```

**Building2** 来自 `lucide-react`,在 sidebar import 列表追加:`import { ..., Building2 } from 'lucide-react'`。

**严禁**:不动 `MAIN_NAV_ITEMS` / `ADVANCED_ITEMS` / 其他 admin 项的顺序或图标。

### 3.6 API 客户端签字 — `frontend/src/api/admin.ts`

完整 ~110 行骨架(签字 6 函数 + 6 类型,**Worker 照搬**):

```ts
/**
 * API 模块 — Phase 10 管理后台
 *
 * 对接后端:
 *  - /api/v1/admin/departments  (5 endpoints, T-1004)
 *  - /api/v1/admin/reports      (1 endpoint, T-1005)
 *
 * RBAC: 后端 require_role(admin, manager);前端入口同步收敛。
 */
import request from '@/api/request'

// ===== /admin/departments =====

export interface DepartmentOut {
  id: string
  name: string
  manager_id: string | null
  created_at: string | null
  updated_at: string | null
  created_by: string | null
  tenant_id: string
}

export interface DepartmentMember {
  id: string
  name: string
  role: 'admin' | 'manager' | 'employee'
  department: string
}

export interface DepartmentWithMembers extends DepartmentOut {
  members: DepartmentMember[]
}

export interface DepartmentIn {
  name: string
  manager_id: string | null
}

export const listDepartments = (): Promise<DepartmentOut[]> =>
  request.get('/admin/departments/') as unknown as Promise<DepartmentOut[]>

export const createDepartment = (payload: DepartmentIn): Promise<DepartmentOut> =>
  request.post('/admin/departments/', payload) as unknown as Promise<DepartmentOut>

export const getDepartmentWithMembers = (id: string): Promise<DepartmentWithMembers> =>
  request.get(`/admin/departments/${id}/members`) as unknown as Promise<DepartmentWithMembers>

export const updateDepartment = (id: string, payload: Partial<DepartmentIn>): Promise<DepartmentOut> =>
  request.patch(`/admin/departments/${id}`, payload) as unknown as Promise<DepartmentOut>

export const deleteDepartment = (id: string): Promise<void> =>
  request.delete(`/admin/departments/${id}`) as unknown as Promise<void>

// ===== /admin/reports =====

export type GroupBy = 'department' | 'project'

export interface ReportGroupRow {
  key: string
  report_count: number
  avg_score: number
  pass_count: number
  pass_rate: number
}

export interface GroupedReportsResponse {
  group_by: GroupBy
  start_date: string
  end_date: string
  project_id: string | null
  groups: ReportGroupRow[]
}

export interface GroupedReportsParams {
  group_by: GroupBy
  project_id?: string
  start_date?: string
  end_date?: string
}

export const getGroupedReports = (params: GroupedReportsParams): Promise<GroupedReportsResponse> =>
  request.get('/admin/reports/', { params }) as unknown as Promise<GroupedReportsResponse>
```

**严禁**:不引入 SWR / React Query;沿用 `@/api/request` 体例(对齐 `kpi.ts` L11)。

---

## §4 原子执行步骤(严格按顺序)

### Step 1 — 新建 `frontend/src/api/admin.ts`

按 §3.6 骨架照搬 110 行,**禁止**改字段名 / 函数名 / 类型导出。

### Step 2 — 新建 `frontend/src/app/admin/departments/page.tsx`

骨架(~280 行,Worker 按此实施,字段命名 100% 对齐):

```tsx
'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Building2, Pencil, Plus, Trash2 } from 'lucide-react'
import { useAuthStore } from '@/stores/use-auth-store'
import {
  listDepartments,
  createDepartment,
  updateDepartment,
  deleteDepartment,
  type DepartmentIn,
  type DepartmentOut,
} from '@/api/admin'

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

type DeptFormState = {
  name: string
  manager_id: string  // 文本输入,空字符串 = null
}

const emptyForm: DeptFormState = { name: '', manager_id: '' }

function getErrorMessage(error: any, fallback = '操作失败') {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) return detail[0]?.msg || fallback
  return detail || fallback
}

function formatDate(value: string | null) {
  if (!value) return '-'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString('zh-CN')
}

export default function DepartmentsAdminPage() {
  const router = useRouter()
  const { userRole } = useAuthStore()
  const canManage = userRole === 'admin' || userRole === 'manager'

  const [rows, setRows] = useState<DepartmentOut[]>([])
  const [loading, setLoading] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState<DeptFormState>(emptyForm)

  useEffect(() => {
    if (userRole && !canManage) {
      toast.error('需 admin 或 manager 权限')
      router.replace('/')
    }
  }, [userRole, canManage, router])

  const loadRows = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listDepartments()
      setRows(Array.isArray(res) ? res : [])
    } catch (error: any) {
      toast.error(getErrorMessage(error, '加载部门列表失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (canManage) {
      loadRows()
    }
  }, [canManage, loadRows])

  function openCreate() {
    setEditingId(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  function openEdit(row: DepartmentOut) {
    setEditingId(row.id)
    setForm({ name: row.name, manager_id: row.manager_id ?? '' })
    setDialogOpen(true)
  }

  function closeDialog() {
    setDialogOpen(false)
    setEditingId(null)
    setForm(emptyForm)
  }

  async function handleSubmit() {
    const trimmedName = form.name.trim()
    if (!trimmedName) {
      toast.error('部门名称必填')
      return
    }
    if (trimmedName.length > 64) {
      toast.error('部门名称不能超过 64 字符')
      return
    }
    const trimmedManager = form.manager_id.trim()
    if (trimmedManager && !UUID_REGEX.test(trimmedManager)) {
      toast.error('负责人 ID 必须是合法 UUID')
      return
    }
    const payload: DepartmentIn = {
      name: trimmedName,
      manager_id: trimmedManager || null,
    }
    setSubmitting(true)
    try {
      if (editingId) {
        await updateDepartment(editingId, payload)
        toast.success('部门更新成功')
      } else {
        await createDepartment(payload)
        toast.success('部门创建成功')
      }
      closeDialog()
      await loadRows()
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      if (detail === 'name_conflict') toast.error('部门名称已存在')
      else if (detail === 'manager_not_found') toast.error('指定的 user.id 不存在或非 manager 角色')
      else if (detail === 'department_not_found') toast.error('部门不存在')
      else toast.error(getErrorMessage(error, '保存失败'))
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(row: DepartmentOut) {
    if (!window.confirm(`确认删除部门「${row.name}」?`)) return
    try {
      await deleteDepartment(row.id)
      toast.success('部门已删除')
      await loadRows()
    } catch (error: any) {
      toast.error(getErrorMessage(error, '删除失败'))
    }
  }

  if (!canManage) return null

  return (
    <main className="p-8 max-w-7xl mx-auto">
      <header className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Building2 size={24} style={{ color: '#3b82f6' }} />
          <h1 className="text-2xl font-semibold" style={{ color: '#e2e8f0' }}>部门管理</h1>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center gap-2 px-4 py-2 rounded-md text-sm"
          style={{ background: '#3b82f6', color: '#fff' }}
        >
          <Plus size={16} /> 新建部门
        </button>
      </header>

      {/* 表格 — 5 列 */}
      <section
        className="rounded-lg border overflow-hidden"
        style={{ borderColor: '#334155', background: '#0f172a' }}
      >
        {loading ? (
          <div className="text-sm p-6 text-slate-400">加载中...</div>
        ) : rows.length === 0 ? (
          <div className="text-sm p-6 text-slate-400">暂无部门</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: '#94a3b8', background: '#1e293b' }}>
                <th className="text-left px-4 py-3">部门名</th>
                <th className="text-left px-4 py-3">负责人 ID</th>
                <th className="text-left px-4 py-3">创建时间</th>
                <th className="text-left px-4 py-3">更新时间</th>
                <th className="text-right px-4 py-3">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t" style={{ borderColor: '#334155' }}>
                  <td className="px-4 py-3" style={{ color: '#e2e8f0' }}>{row.name}</td>
                  <td className="px-4 py-3 font-mono text-xs" style={{ color: '#94a3b8' }}>
                    {row.manager_id ?? '-'}
                  </td>
                  <td className="px-4 py-3" style={{ color: '#94a3b8' }}>{formatDate(row.created_at)}</td>
                  <td className="px-4 py-3" style={{ color: '#94a3b8' }}>{formatDate(row.updated_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => openEdit(row)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded mr-2 text-xs"
                      style={{ background: '#1e293b', color: '#3b82f6' }}
                    >
                      <Pencil size={12} /> 编辑
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDelete(row)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs"
                      style={{ background: '#1e293b', color: '#ef4444' }}
                    >
                      <Trash2 size={12} /> 删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {/* Modal 新建/编辑 */}
      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.7)' }}>
          <div className="w-full max-w-md rounded-lg p-6" style={{ background: '#0f172a', border: '1px solid #334155' }}>
            <h2 className="text-lg font-semibold mb-4" style={{ color: '#e2e8f0' }}>
              {editingId ? '编辑部门' : '新建部门'}
            </h2>
            <label className="block mb-3 text-sm">
              <span style={{ color: '#94a3b8' }}>部门名称 *</span>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                maxLength={64}
                className="w-full mt-1 px-3 py-2 rounded text-sm"
                style={{ background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155' }}
              />
            </label>
            <label className="block mb-4 text-sm">
              <span style={{ color: '#94a3b8' }}>负责人 user.id(可选,UUID)</span>
              <input
                type="text"
                value={form.manager_id}
                onChange={(e) => setForm({ ...form, manager_id: e.target.value })}
                placeholder="留空表示无负责人"
                className="w-full mt-1 px-3 py-2 rounded font-mono text-xs"
                style={{ background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155' }}
              />
            </label>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={closeDialog}
                className="px-4 py-2 rounded text-sm"
                style={{ background: '#1e293b', color: '#94a3b8' }}
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={submitting}
                className="px-4 py-2 rounded text-sm"
                style={{ background: '#3b82f6', color: '#fff', opacity: submitting ? 0.6 : 1 }}
              >
                {submitting ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
```

### Step 3 — 改造 `frontend/src/app/dashboard/page.tsx`

**插入点 1:imports 区(L17-65)** 追加:

```tsx
import { getGroupedReports, type ReportGroupRow } from '@/api/admin'
```

**插入点 2:状态声明区** 在现有 state 声明后追加:

```tsx
type ViewMode = 'all' | 'by_department' | 'by_project'

const [viewMode, setViewMode] = useState<ViewMode>('all')
const [groupedRows, setGroupedRows] = useState<ReportGroupRow[]>([])
const [groupedLoading, setGroupedLoading] = useState(false)
```

**插入点 3:effect 区** 在现有 `useEffect` 后追加(monitor `viewMode` 切换):

```tsx
useEffect(() => {
  if (viewMode === 'all') return
  let cancelled = false
  ;(async () => {
    setGroupedLoading(true)
    try {
      const res = await getGroupedReports({
        group_by: viewMode === 'by_department' ? 'department' : 'project',
      })
      if (!cancelled) setGroupedRows(res.groups)
    } catch (error: any) {
      if (!cancelled) toast.error('加载分组数据失败')
    } finally {
      if (!cancelled) setGroupedLoading(false)
    }
  })()
  return () => { cancelled = true }
}, [viewMode])
```

**插入点 4:JSX 区(L386 `return (` 之后,"监控台"标题渲染区附近)** 紧跟标题之后,4 个统计卡片**之前**插入:

```tsx
{canSeeTabs && (
  <div className="flex items-center gap-2 mb-4">
    {(['all', 'by_department', 'by_project'] as const).map((mode) => (
      <button
        key={mode}
        type="button"
        onClick={() => setViewMode(mode)}
        className="px-4 py-1.5 rounded-md text-sm transition-colors"
        style={{
          background: viewMode === mode ? '#3b82f6' : 'transparent',
          color: viewMode === mode ? '#fff' : '#94a3b8',
          border: viewMode === mode ? 'none' : '1px solid #334155',
        }}
      >
        {mode === 'all' ? '全员视图' : mode === 'by_department' ? '按部门聚合' : '按项目聚合'}
      </button>
    ))}
  </div>
)}
```

`canSeeTabs` 取 `userRole === 'admin' || userRole === 'manager'` —— 复用现有 `canManageAlerts` 同等条件,**不新建** state,直接写常量。

**插入点 5:JSX 区 — 现有 5 sections 外包 condition**:

```tsx
{viewMode === 'all' && (
  <>
    {/* 现有 5 sections 整体包进来,不动 markup */}
  </>
)}

{viewMode !== 'all' && (
  <section className="...">{/* §3.3 表格骨架 */}</section>
)}
```

**严禁**:不动现有 5 sections 内部 markup;只在最外层包 `{viewMode === 'all' && (...)}`。

### Step 4 — 改造 `frontend/src/components/sidebar.tsx`

**L48-65 imports + ADMIN_ITEMS**:

1. 在 lucide-react import 中追加 `Building2`(保持现有 import 顺序整洁,放在 alphabetical 合适位置)。
2. 在 `ADMIN_ITEMS` 数组中,**`/admin/recycle-bin` 之前**插入一行(§3.5 已签字)。

### Step 5 — 改 `docs/dev_tasks.md`

Task 6 `[/] → [x]`,与最后一个 commit 一起 add。**不动** 📣 锚点。

**严禁**:在本 commit 内同时改其它 task 的 checkbox 状态。

---

## §5 防越界红线表(20 项)

1. ❌ 不改 `backend/`
2. ❌ 不改任何已有测试文件
3. ❌ 不引入新 npm 依赖
4. ❌ 不改 `package.json` / `tsconfig.json` / `next.config.*` / `tailwind.config.*` / `postcss.config.*`
5. ❌ 不改 4 既定 untracked 文件
6. ❌ 不动 `/admin/kpi` / `/admin/recycle-bin` 路由文件
7. ❌ 不动现有 dashboard 5 sections 内部 markup
8. ❌ 不引入图表(`CompareBarChart`/`TrendLineChart`)到分组视图
9. ❌ 不引入 manager dropdown / date picker
10. ❌ 不写自动化测试
11. ❌ 不持久化 `viewMode` 到 localStorage / URL
12. ❌ 不调用 `/users` 拉取 manager 列表
13. ❌ 不传 `start_date / end_date / project_id` 到 `/admin/reports`
14. ❌ 不破坏 employee 视图 — employee 仍看到现有 Dashboard 全员视图
15. ❌ 不动 📣 锚点(留给指挥官替换)
16. ❌ 不 `git push`
17. ❌ 不动 `Sidebar` 其它项的顺序 / 图标
18. ❌ 不引入 `@/components/ui`(项目无 shadcn,不要新建)
19. ❌ 不自启 T-1008
20. ❌ commit 时不夹带 `node_modules` / `.next` / `.cache`

---

## §6 数据风险评估

- **零 DDL** — 本契约无任何后端改动。
- **零数据库迁移** — alembic head 仍 `b58bb129c24b` 不变。
- **零生产数据风险** — 纯前端 UI 工作。
- **运行时风险**:
  - `/admin/reports` 在大数据量下窗口(today-30)聚合,后端已用索引(`ix_daily_reports_report_date`)+ trends.py 相同 SQL 模式,实测 <100ms。
  - Modal 重复 submit 防护通过 `submitting` state lock。

---

## §7 质量闸门(全绿才提交)

```bash
cd frontend
npm run lint          # eslint 全过,零 warning
npm run typecheck     # tsc --noEmit 0 error
```

**手动验证(4 个场景)**:
1. `/admin/departments` 入口加载列表 + 新建一个部门 + 编辑 + 删除(admin 账户登录)。
2. `/dashboard` 顶部 Tabs 3 按钮切换 — `all` 显示现有 sections,`by_department` / `by_project` 显示表格。
3. employee 账户登录 `/dashboard` — 不显示 Tabs(canSeeTabs=false)。
4. employee 访问 `/admin/departments` — toast 报错 + redirect `/`。

---

## §8 完工提交序列(原子 2 commit,顺序不可乱)

1. `feat(admin): Phase 10 前端 admin/departments 管理页 + Dashboard Tabs 切换器` —— 包含 `frontend/src/api/admin.ts`(新建) + `frontend/src/app/admin/departments/page.tsx`(新建) + `frontend/src/app/dashboard/page.tsx`(改) + `frontend/src/components/sidebar.tsx`(改) 4 文件。
2. `chore(progress): close T-1006 — Phase 10 前端管理后台 + Tabs 切换器上线` —— 仅 `docs/dev_tasks.md` Task 6 → `[x]`。

每个 commit message 末尾必须含 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 一行。

---

## §9 验收清单(指挥官二次验收按此 19 项)

1. commit 链路完整(feat 4 文件 + chore 1 文件,先后顺序对)
2. `git diff <T-1006 spec commit>..HEAD -- backend/` 完全空
3. `git diff <T-1006 spec commit>..HEAD -- frontend/src/api/admin.ts` 新建 ~110 行,6 函数 + 6 类型
4. `git diff <T-1006 spec commit>..HEAD -- frontend/src/app/admin/departments/page.tsx` 新建 ~280 行
5. `git diff <T-1006 spec commit>..HEAD -- frontend/src/app/dashboard/page.tsx` +60/-0 局部插入,**现有 5 sections 内部 markup 0 改动**(grep "现有 component 调用" 完全一致)
6. `git diff <T-1006 spec commit>..HEAD -- frontend/src/components/sidebar.tsx` +1/-0(`Building2` import + ADMIN_ITEMS 一行)
7. 4 既定 untracked 保留
8. `npm run lint` zero warning
9. `npm run typecheck` zero error
10. 后端 pytest 全量 178 passed 不变(零回归)
11. `ViewMode` 类型 + 3 个 state 命名 100% 对齐契约
12. `canSeeTabs` 不新建独立 state,使用现有 userRole 直接判断
13. UUID_REGEX 正则 100% 对齐契约字面量
14. 5 列表格列名 100% 对齐契约(部门 / 日报数 / 均分 / 通过数 / 通过率)
15. Modal 字段 2 项(name + manager_id),无第三字段夹带
16. Sidebar `Building2` 图标 + label "部门管理" + href `/admin/departments`
17. Worker timestamp 双 commit 均带
18. 📣 锚点保留 T-1006 持牌(留给指挥官替换)
19. dev_tasks.md Task 6 = `[x]`

---

## §10 与其他任务的关系

- **完工后**:T-1008(文档收尾)契约由指挥官起草,完整 6 列对照表落地 + recap.md 更新。
- **不影响**:T-1007 已闭环,后端 178 case 测试护栏继续保护(纯前端改动不会破)。
- **employee 视图**:仍能正常访问 `/dashboard`,但看不到 Tabs 也访问不了 `/admin/departments`(双层守卫:前端 + 后端 RBAC)。

---

## 📣 附录:给 Worker 的物理交接单

> **更新时间戳**:`[2026-05-27 21:34:30]`
> **当前持牌任务**:**T-1006**(指挥官 `chore(spec)` commit 已加锁,Task 6 = `[/]`)
> **任务全称**:Phase 10 前端管理后台 + Dashboard Tabs 切换器 —— **3 新建 + 2 改造,5 文件 ±0 夹带**

**执行入口**:阅读 `docs/T-1006_spec.md`(本契约),严格按 §3 设计签字 + §4 原子步骤实施,不要重复 `chore(lock)`。**前置勘察已由指挥官完成**:① `frontend/src/app/admin/kpi/page.tsx` 是镜像参考(role guard + form state + Modal + toast 错误模式) ② `frontend/src/api/kpi.ts` 是 API 客户端镜像参考(`request.get/post + as unknown as Promise<T>` 体例) ③ `frontend/src/components/sidebar.tsx` L48-62 已锁定 ADMIN_ITEMS 插入位 ④ `frontend/src/app/dashboard/page.tsx` 是 1212 行大文件,**所有插入点为局部**,严禁重排 ⑤ 项目**无 shadcn UI kit**,Modal 用原生 `<div fixed inset-0>` 自绘 ⑥ 项目有 `sonner` toast 和 `lucide-react` icon,**不要**新引入 ⑦ Building2 是 lucide-react 现有图标,直接 import 即可。

**核心动作(5 步,严格按 §4 顺序)**

1. **新建** `frontend/src/api/admin.ts` —— 按 §3.6 完整骨架照搬 ~110 行,6 函数 + 6 类型,**禁止改名**(`listDepartments / createDepartment / getDepartmentWithMembers / updateDepartment / deleteDepartment / getGroupedReports`)。
2. **新建** `frontend/src/app/admin/departments/page.tsx` —— 按 §3.4 + §4 Step 2 骨架照搬 ~280 行,UUID_REGEX 正则字面量 100% 对齐,错误码 mapping 4 项落齐。
3. **改造** `frontend/src/app/dashboard/page.tsx` —— 5 个**局部插入点**(imports / state / effect / Tabs JSX / sections wrap),**严禁**重排现有 5 sections 内部 markup;`viewMode === 'all'` 时所有现有行为 100% 不变(零回归)。
4. **改造** `frontend/src/components/sidebar.tsx` —— lucide-react import 追加 `Building2` + ADMIN_ITEMS 数组在 recycle-bin 之前插入一行。
5. **改** `docs/dev_tasks.md` —— Task 6 `[/] → [x]`(放最后一个 commit 一起 add)。**不动** 📣 锚点。

**严禁项(违反立即回滚)**:见 §5 红线表 20 项。**重点重复**:① 不动 backend / ② 不动 dashboard 现有 5 sections 内部 markup / ③ 不引入新 npm 依赖 / ④ 不引入图表到分组视图 / ⑤ 不引入 manager dropdown / ⑥ 不动 📣 锚点 / ⑦ 不 `git push` / ⑧ 不自启 T-1008。

**闸门(全绿才提交)**
```bash
cd frontend
npm run lint
npm run typecheck
# 手动 4 场景(详见 §7):
#   1. admin 登录,/admin/departments 加载列表 → 新建 → 编辑 → 删除
#   2. /dashboard 顶部 Tabs 切换:全员/按部门/按项目
#   3. employee 登录,/dashboard 不显示 Tabs
#   4. employee 访问 /admin/departments,toast 报错 + redirect /
```

**完工提交序列(原子 2 commit,顺序不可乱)**
1. `feat(admin): Phase 10 前端 admin/departments 管理页 + Dashboard Tabs 切换器` —— 4 文件(2 新建 + 2 改造)
2. `chore(progress): close T-1006 — Phase 10 前端管理后台 + Tabs 切换器上线` —— 仅 `docs/dev_tasks.md` Task 6 → `[x]`

每个 commit message 末尾必须含 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 一行。

**完工后**:停手汇报「T-1006 完工,等待二次验收 + T-1008 文档收尾起草」,**不要**自启 T-1008。
