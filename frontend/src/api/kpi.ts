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

export const listKpiTargets = (): Promise<KpiTargetOut[]> =>
  request.get('/admin/kpi/') as unknown as Promise<KpiTargetOut[]>

export const upsertKpiTarget = (payload: KpiTargetIn): Promise<KpiTargetOut> =>
  request.post('/admin/kpi/', payload) as unknown as Promise<KpiTargetOut>
