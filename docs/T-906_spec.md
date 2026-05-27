# T-906 执行契约 — Dashboard KPI 达成率面板

> **任务编号**: T-906
> **任务名**: Phase 9 KPI 达成率仪表盘组件（dashboard 内嵌面板）
> **指挥官**: Claude (QA & Refactor Specialist)
> **执行人**: Codex (Worker)
> **前置**: T-905 已落地（HEAD: `79ba44d`）。前端三大闸门全绿（lint/typecheck/build），admin/manager 真机 200，employee 403，`/admin/kpi` 路由可加载。
> **依赖**: 既有 `frontend/src/api/kpi.ts`（T-905 已新建,本契约**extend**)、`frontend/src/components/charts/compare-bar-chart.tsx`（Phase 7,**不改**）、`frontend/src/app/dashboard/page.tsx` (现有 `canManageAlerts` 守卫模式)、`frontend/src/api/request.ts`。
> **后端契约**: `GET /api/v1/admin/kpi/achievement?period=monthly` （T-902/T-903 已交付，period 默认 monthly，支持 `weekly|monthly|quarterly`）。

---

## 1. 任务目标

在 `/dashboard` 增加一个 **「KPI 达成率」面板**：

1. 默认拉 `period=monthly` 的达成率快照，admin/manager 可见，员工身份不渲染（沿用 `canManageAlerts` 守卫）。
2. 顶部条带：标题「KPI 达成率」+ period 选择器（周/月/季）+ 数据快照时间。
3. 图表区：`CompareBarChart` 渲染「目标 vs 实际」对比柱，每行一个 KPI 目标（scope + metric 拼接为 label）。
4. 详细表格区：列出每行的 `范围 / 范围值 / 指标 / 目标值 / 实际值 / 缺口 / 达成率 / 状态`，**状态用彩色 tag**：绿(`on_track`) / 红(`below_target`) / 灰(`no_data`)。

---

## 2. 范围边界

### 范围内 (IN)

- **extend** `frontend/src/api/kpi.ts` —— 增加 3 个 TS 类型（`AchievementStatus / KpiAchievementRow / KpiAchievementResponse`）+ 1 个端点函数 `getKpiAchievement(period?: KpiPeriod)`。
- **新建** `frontend/src/components/dashboard/kpi-achievement-panel.tsx` —— 客户端组件，含 period 选择 + CompareBarChart + 详细表格（预计 200-250 行）。
- **改** `frontend/src/app/dashboard/page.tsx` —— 引入 `<KpiAchievementPanel />` 并嵌入到 `canManageAlerts` 守卫块中（**仅 1 个 import 行 + 1 个 JSX section 块**，不动其它 dashboard 业务逻辑）。

### 范围外 (OUT)

- **绝对不要**改 `frontend/src/components/charts/compare-bar-chart.tsx`（Phase 7 凝固，按 plan §9 「用现有 CompareBarChart」）。
- **绝对不要**改 `frontend/src/app/admin/kpi/page.tsx`（T-905 凝固）。
- **绝对不要**改 后端任何文件。
- **绝对不要**改 `frontend/src/stores/use-auth-store.ts`。
- **绝对不要**改 sidebar / navigation。
- **绝对不要**写前端测试。
- **绝对不要**重复实现 `canManageAlerts` 守卫 —— dashboard 已有，复用即可。

---

## 3. API 客户端扩展（`frontend/src/api/kpi.ts`）

### 3.1 新增类型

在文件末尾追加（**不动**既有 `KpiScope / KpiMetric / KpiPeriod / KpiTargetOut / KpiTargetIn / listKpiTargets / upsertKpiTarget`）:

```ts
export type AchievementStatus = 'on_track' | 'below_target' | 'no_data'

export interface KpiAchievementRow {
  scope: KpiScope
  scope_value: string | null
  metric: KpiMetric
  period: KpiPeriod
  target_value: number
  actual_value: number | null
  gap: number | null
  achievement_rate: number | null
  status: AchievementStatus
}

export interface KpiAchievementResponse {
  period: KpiPeriod
  snapshot_at: string
  rows: KpiAchievementRow[]
}

export const getKpiAchievement = (period?: KpiPeriod): Promise<KpiAchievementResponse> =>
  request.get('/admin/kpi/achievement', { params: period ? { period } : {} }) as unknown as Promise<KpiAchievementResponse>
```

> **要点**:
> - `actual_value / gap / achievement_rate` 都可能为 `null`（status=no_data 时）。
> - `period` 不传时让后端走默认 `monthly`，**不要**前端硬编码。
> - 路径 **不带尾斜杠** —— `@router.get("/achievement")` 是无尾斜杠路径（与 `@router.get("/")` 不同）。

---

## 4. 面板组件契约（`frontend/src/components/dashboard/kpi-achievement-panel.tsx`）

### 4.1 文件头

```tsx
/**
 * components/dashboard/kpi-achievement-panel.tsx — Phase 9 KPI 达成率面板
 *
 * 渲染位置: /dashboard 内, canManageAlerts 守卫块下方。
 * 数据源: GET /api/v1/admin/kpi/achievement?period=<weekly|monthly|quarterly>
 * 业务规则: 达成绿 / 未达成红 / 暂无数据灰。
 */
'use client'
```

### 4.2 组件骨架

```tsx
import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Target } from 'lucide-react'
import { CompareBarChart } from '@/components/charts'
import {
  getKpiAchievement,
  type AchievementStatus,
  type KpiAchievementResponse,
  type KpiAchievementRow,
  type KpiMetric,
  type KpiPeriod,
  type KpiScope,
} from '@/api/kpi'

const PERIOD_OPTIONS: { value: KpiPeriod; label: string }[] = [
  { value: 'weekly', label: '周' },
  { value: 'monthly', label: '月' },
  { value: 'quarterly', label: '季' },
]

const SCOPE_LABELS: Record<KpiScope, string> = {
  global: '全公司',
  department: '部门',
  role: '岗位',
}

const METRIC_LABELS: Record<KpiMetric, string> = {
  submit_rate: '日报提交率',
  avg_score: '日报均分',
  blocker_resolve_days: '阻塞解决天数',
  objective_completion: 'OKR 完成率',
}

const STATUS_STYLE: Record<AchievementStatus, { label: string; color: string; bg: string }> = {
  on_track: { label: '已达成', color: '#16a34a', bg: 'rgba(34,197,94,0.15)' },
  below_target: { label: '未达成', color: '#dc2626', bg: 'rgba(239,68,68,0.15)' },
  no_data: { label: '暂无数据', color: '#64748b', bg: 'rgba(100,116,139,0.15)' },
}

function rowLabel(row: KpiAchievementRow): string {
  const scopeLabel = SCOPE_LABELS[row.scope]
  const scopePart = row.scope_value ? `${scopeLabel}·${row.scope_value}` : scopeLabel
  return `${scopePart}/${METRIC_LABELS[row.metric]}`
}

function formatNumber(value: number | null, suffix = ''): string {
  if (value === null || value === undefined) return '—'
  const text = Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, '')
  return `${text}${suffix}`
}

function metricSuffix(metric: KpiMetric): string {
  return metric === 'submit_rate' || metric === 'objective_completion' ? '%' : ''
}

export function KpiAchievementPanel() {
  const [period, setPeriod] = useState<KpiPeriod>('monthly')
  const [data, setData] = useState<KpiAchievementResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const loadData = useCallback(async (p: KpiPeriod) => {
    setLoading(true)
    try {
      const res = await getKpiAchievement(p)
      setData(res)
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      toast.error(Array.isArray(detail) ? detail[0]?.msg || '加载达成率失败' : detail || '加载达成率失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData(period)
  }, [period, loadData])

  // 图表 data: 每行 label + target_value + actual_value (null 留空)
  const chartData = useMemo(() => {
    if (!data) return []
    return data.rows.map((row) => ({
      label: rowLabel(row),
      target: row.target_value,
      actual: row.actual_value,  // null 时 recharts 自动不画该柱
    }))
  }, [data])

  return (
    <div className="mb-8 animate-in" style={{ animationDelay: '0.36s' }}>
      <div className="section-title flex items-center gap-2">
        <Target size={16} color="#22c55e" />
        KPI 达成率
        {data?.snapshot_at && (
          <span className="text-[10px] font-normal" style={{ color: 'var(--color-text-secondary)' }}>
            快照 · {new Date(data.snapshot_at).toLocaleString('zh-CN')}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>周期</span>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value as KpiPeriod)}
            className="px-2 py-1 rounded-lg text-xs outline-none"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
          >
            {PERIOD_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </div>
      </div>

      <div className="stat-card mb-4">
        <CompareBarChart
          data={chartData}
          bars={[
            { dataKey: 'target', name: '目标', color: '#3b82f6' },
            { dataKey: 'actual', name: '实际', color: '#22c55e' },
          ]}
          xKey="label"
          yDomain={[0, 100]}
          emptyLabel={loading ? '加载中...' : '暂无 KPI 目标'}
        />
      </div>

      <div className="rounded-xl overflow-hidden" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr style={{ background: 'var(--color-bg-secondary)' }}>
                {['范围', '指标', '目标值', '实际值', '缺口', '达成率', '状态'].map((h) => (
                  <th key={h} className="text-left py-2.5 px-4 text-xs font-semibold" style={{ color: 'var(--color-text-primary)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(!data || data.rows.length === 0) && (
                <tr><td colSpan={7} className="text-center py-10 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{loading ? '加载中...' : '暂无 KPI 数据'}</td></tr>
              )}
              {data?.rows.map((row, idx) => {
                const style = STATUS_STYLE[row.status]
                const suffix = metricSuffix(row.metric)
                return (
                  <tr key={`${row.scope}-${row.scope_value ?? '_'}-${row.metric}-${idx}`} style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    <td className="py-2.5 px-4" style={{ color: 'var(--color-text-primary)' }}>
                      {SCOPE_LABELS[row.scope]}{row.scope_value ? ` · ${row.scope_value}` : ''}
                    </td>
                    <td className="py-2.5 px-4" style={{ color: 'var(--color-text-secondary)' }}>{METRIC_LABELS[row.metric]}</td>
                    <td className="py-2.5 px-4" style={{ color: 'var(--color-text-primary)' }}>{formatNumber(row.target_value, suffix)}</td>
                    <td className="py-2.5 px-4" style={{ color: row.actual_value === null ? 'var(--color-text-secondary)' : 'var(--color-text-primary)' }}>{row.actual_value === null ? '暂无数据' : formatNumber(row.actual_value, suffix)}</td>
                    <td className="py-2.5 px-4" style={{ color: 'var(--color-text-secondary)' }}>{formatNumber(row.gap, suffix)}</td>
                    <td className="py-2.5 px-4" style={{ color: 'var(--color-text-secondary)' }}>{row.achievement_rate === null ? '—' : `${row.achievement_rate.toFixed(1)}%`}</td>
                    <td className="py-2.5 px-4">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-medium" style={{ color: style.color, background: style.bg }}>{style.label}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
```

> **要点**:
> - **不要**用 `default export`（dashboard 习惯具名 import）。
> - CompareBarChart 的 `actual = null` 时 recharts 自动跳过该柱 —— **不需要**前端二次处理。
> - 状态颜色在**表格 tag** 里表现（绿/红/灰），**不**在图表柱子上（避免触碰 CompareBarChart）。这是 plan §9 「达成的绿色，未达成的红色」的合理变体（颜色信号通过 status tag 传递）。
> - `yDomain=[0, 100]` 假设主要 metric（submit_rate / objective_completion）是 0-100 区间；`avg_score` 也是 0-100；`blocker_resolve_days` 通常 < 10。本契约**不**做 metric 分组渲染，所有柱共享一个 Y 轴。

---

## 5. Dashboard 集成（`frontend/src/app/dashboard/page.tsx`）

**最小改动 2 处**:

### 5.1 import 行

参考 dashboard 既有 import 风格（`line 47: import { CompareBarChart, TrendLineChart } from '@/components/charts'`），在 import 块合理位置追加：

```tsx
import { KpiAchievementPanel } from '@/components/dashboard/kpi-achievement-panel'
```

### 5.2 JSX 插入位置

在 dashboard.tsx **既有 Phase 7 历史趋势看板**（`{canManageAlerts && (<div ...>...</div>)}` 块，约 lines 481-587）**之后**，紧贴下一个 section 之前，新增一个块：

```tsx
{canManageAlerts && <KpiAchievementPanel />}
```

> 一行 JSX，**复用 dashboard 既有 `canManageAlerts` 守卫**，与 Phase 7 看板共用同样的 RBAC 收敛。**不要**在 KpiAchievementPanel 组件内部再写 useAuthStore 守卫（双重守卫=污染）。

---

## 6. 验证标准

```bash
cd frontend

# 1) 静态检查
npm run lint
npm run typecheck

# 2) 构建烟测
npm run build
```

三项必须全绿。

### 6.2 真机手测（指挥官二次验收会跑）

启后端 + 前端 `npm run start`，admin 身份登录 → 访问 `/dashboard`:

- 滚动到「KPI 达成率」面板（在历史趋势看板之后）。
- 顶部应显示 period select（默认月）+ 快照时间。
- 切到「周/季」select 下拉,数据应刷新（loading 短暂闪现）。
- 表格应列出 4 行 seed 目标 + status tag (`submit_rate` 大概率 `no_data` 因为 MV 可能空；`avg_score`/`blocker_resolve_days`/`objective_completion` 视实际数据)。
- employee 登录 → `/dashboard` 应**不显示**「KPI 达成率」面板（被 `canManageAlerts` 守卫挡住），且不应触发 `/admin/kpi/achievement` 请求（network 面板无该请求）。

---

## 7. 提交规约

**两条原子 commit**：

1. `feat(kpi): add dashboard KPI achievement panel`
   - 含 `frontend/src/api/kpi.ts`（extend）+ `frontend/src/components/dashboard/kpi-achievement-panel.tsx`（新建）+ `frontend/src/app/dashboard/page.tsx`（+2 行）3 个文件。
   - Body 简述：复用既有 `canManageAlerts` 守卫，新增 period 切换面板（CompareBarChart 目标 vs 实际 + 状态 tag 表格），未碰 Phase 7 CompareBarChart 与 admin/kpi 管理页。
2. 修改 `docs/dev_tasks.md` Task 6 方括号 `[ ]` → `[x]`，然后：
   - `chore(progress): close T-906`

---

## 8. 不在本契约内的事项

- **不要**改 CompareBarChart 内部（即使想让 actual 按 status 着色，也禁止；status 颜色走表格 tag）。
- **不要**改 `frontend/src/app/admin/kpi/page.tsx`（T-905 凝固）。
- **不要**在 KpiAchievementPanel 内重写 auth 守卫（dashboard 父级已守卫）。
- **不要**写前端测试（项目惯例尚未铺开）。
- **不要**做 i18n 抽取 / 主题扩展。
- **不要**改 sidebar 导航。
- **不要**让面板支持「点击柱子跳转 /admin/kpi」之类的快捷链接（产品需求里没要求）。

---

## 9. 风险与注意点

1. **CompareBarChart `actual=null` 行为**: recharts `<Bar>` 对 null/undefined 自动跳过该数据点，不会绘制柱子。表格里需要显式写「暂无数据」。
2. **yDomain 假设**: `[0, 100]` 适合大多数 metric。`blocker_resolve_days` 通常 < 10，在 0-100 范围里柱子会很矮但不报错。**契约不要求**前端按 metric 分组渲染（保持简单），如果用户后续提需求再做。
3. **`achievement_rate` 单位**: 后端返回的是百分数（如 `95.0` 表示 95%），不是小数（不是 `0.95`）。前端直接 `.toFixed(1) + '%'`。
4. **`gap` 正负**: 后端定义 `gap = actual - target`（负数=未达成,正数=超额）。前端只展示数字 + 单位,**不**额外加 +/-  prefix（数字本身的符号已经表达）。
5. **快照时间渲染**: `snapshot_at` 是 ISO 字符串（`2026-05-27T...Z`),`new Date(snapshot_at).toLocaleString('zh-CN')` 会自动转本地时区。
6. **period 切换的 hydrate 时序**: `useEffect(() => loadData(period), [period, loadData])` 首次 mount 会触发一次。如果 dashboard 父级 hydrate 慢，KpiAchievementPanel 会比 dashboard 主表更早发请求 —— 没问题，因为 axios 401 拦截器 fallback 仍然生效。
7. **section-title / stat-card / animate-in CSS class**: 这些是 dashboard 既有的全局 class（`globals.css` 或 module 级别 class），新组件复用即可。**不要**自创新的 CSS class。
8. **不能 cast `as unknown as Promise<T>` 太重?**: T-905 的 `kpi.ts` 已经用了这种 cast 模式（因为 axios 响应拦截器把 `.data` 解出但 TS 类型还指向 AxiosResponse）。保持一致,**不要**改 axios 实例的类型签名。

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌，供 PM 探针自动提取**

- **当前持牌任务**: **T-906** —— Phase 9 KPI 达成率仪表盘面板（`/dashboard` 内嵌）。看板已锁 `[/]`，不要重复 `chore(lock)`。
- **执行入口**: 阅读 `docs/T-906_spec.md`,对标 `frontend/src/app/dashboard/page.tsx:481-587` 既有 Phase 7 历史趋势看板的卡片模板,直接编码。
- **核心交付**:
  1. **extend** `frontend/src/api/kpi.ts` —— 追加 3 类型 (`AchievementStatus / KpiAchievementRow / KpiAchievementResponse`) + 1 端点函数 `getKpiAchievement(period?)`,路径 `/admin/kpi/achievement` **不带**尾斜杠。
  2. **新建** `frontend/src/components/dashboard/kpi-achievement-panel.tsx` —— 含 period 选择器 + `CompareBarChart` (target vs actual 蓝绿双柱) + 详细表格 (状态 tag 绿/红/灰)。**不要** import useAuthStore (守卫由父级 dashboard 收敛)。
  3. **改** `frontend/src/app/dashboard/page.tsx` —— 1 行 import + 在 Phase 7 历史趋势看板 (`canManageAlerts && (...)`) **之后**插入 `{canManageAlerts && <KpiAchievementPanel />}`,**不动**其它业务逻辑。
- **闸门**: `cd frontend && npm run lint && npm run typecheck && npm run build` 三连全绿。
- **完工提交序列**:
  1. `feat(kpi): add dashboard KPI achievement panel`
  2. 改 `docs/dev_tasks.md` Task 6 → `[x]`,再提 `chore(progress): close T-906`
- **完工后**: 立即停手,等指挥官二次验收。**不要**自行进入 T-907(文档收尾)—— 那是 Phase 9 收官前的最后一份契约,由指挥官二次验收 T-906 通过后另发。
- **验收通过的判定**: §6 三个 npm 命令全绿;指挥官能复现 §6.2 admin 看到面板 + period 切换刷新 + employee 不见面板的三场景。

**契约生效。Codex 收到后请确认 `git log -1 --oneline` 包含 `chore(spec): T-906`,然后开干。**
