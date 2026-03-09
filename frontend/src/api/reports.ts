/**
 * API 模块 — 日报 (1:1 port from Vue api/reports.ts)
 */
import request from '@/lib/axios'

export const getReports = (params?: any) => request.get('/reports/', { params })
export const getReportDetail = (id: string) => request.get(`/reports/${id}`)
