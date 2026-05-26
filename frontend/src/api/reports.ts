/**
 * API 模块 — 日报
 */
import request from '@/api/request'

export const getReports = (params?: any) => request.get('/reports', { params })
export const getReportDetail = (id: string) => request.get(`/reports/${id}`)
export const getTodayPlan = () => request.get('/reports/today-plan')

// V2.4 Stage 2:批量软删日报
export const batchSoftDeleteReports = (ids: string[]) =>
  request.delete('/reports/batch', { data: { ids } })

// V2.4 Stage 3 C3:批量恢复日报(撤销 / 回收站共用)
export const batchRestoreReports = (ids: string[]) =>
  request.patch('/reports/batch-restore', { ids })
