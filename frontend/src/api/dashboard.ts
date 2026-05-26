/**
 * API 模块 — Dashboard (1:1 port from Vue api/dashboard.ts)
 */
import request from '@/api/request'

export const getMorningBriefing = () => request.get('/dashboard/morning-briefing')
export const getRiskAlerts = () => request.get('/dashboard/risk-alerts')
export const getTokenUsage = () => request.get('/dashboard/token-usage')
export const getWeeklyStats = () => request.get('/dashboard/weekly-stats')

// V2.3 临时工单看板:本月 TOP N 员工工时 + 临时 vs 主干占比
export const getTempTicketSummary = (params?: { month_start?: string; month_end?: string; top_n?: number }) =>
  request.get('/dashboard/temp-ticket-summary', { params })

// V2.5 Stage 3:RiskAlert 批量软删 / 恢复 / 回收站
export type RiskAlertBatchResult = {
  requested: number
  deleted_count?: number
  deleted_ids?: string[]
  restored_count?: number
  restored_ids?: string[]
}

export type DeletedRiskAlert = {
  alert_id: string
  member: string
  department: string | null
  type: string
  description: string
  days_unresolved: number
  status: string
  created_at: string | null
  deleted_at: string | null
}

export const batchDeleteRiskAlerts = (ids: string[]) =>
  request.delete<unknown, RiskAlertBatchResult>('/dashboard/risk-alerts/batch', { data: { ids } })

export const batchRestoreRiskAlerts = (ids: string[]) =>
  request.patch<unknown, RiskAlertBatchResult>('/dashboard/risk-alerts/batch-restore', { ids })

export const getDeletedRiskAlerts = () =>
  request.get<unknown, { items: DeletedRiskAlert[]; total: number }>('/dashboard/risk-alerts/deleted')
