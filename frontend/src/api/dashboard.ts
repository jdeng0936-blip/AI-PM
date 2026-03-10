/**
 * API 模块 — Dashboard (1:1 port from Vue api/dashboard.ts)
 */
import request from '@/api/request'

export const getMorningBriefing = () => request.get('/dashboard/morning-briefing')
export const getRiskAlerts = () => request.get('/dashboard/risk-alerts')
export const getTokenUsage = () => request.get('/dashboard/token-usage')
export const getWeeklyStats = () => request.get('/dashboard/weekly-stats')
