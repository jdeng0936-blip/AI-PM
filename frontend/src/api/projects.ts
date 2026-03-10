/**
 * API 模块 — 项目 (1:1 port from Vue api/projects.ts)
 */
import request from '@/api/request'

export const getProjectsOverview = () => request.get('/projects/overview')
export const getProject = (id: string) => request.get(`/projects/${id}`)
export const getProjectGantt = (id: string) => request.get(`/projects/${id}/gantt`)
export const getProjectMembers = (id: string) => request.get(`/projects/${id}/members`)
export const addProjectMember = (id: string, data: any) => request.post(`/projects/${id}/members`, data)
export const createProject = (data: any) => request.post('/projects/', data)
export const getGateReviews = (projectId: string) => request.get(`/gates/project/${projectId}`)
export const submitGateReview = (data: any) => request.post('/gates/review', data)
