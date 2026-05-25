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
