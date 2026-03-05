import request from './request'

export const getReports = (params?: any) => request.get('/reports/', { params })
export const getReportDetail = (id: string) => request.get(`/reports/${id}`)
