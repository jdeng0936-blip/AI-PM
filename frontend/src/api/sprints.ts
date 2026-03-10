/**
 * API 模块 — Sprint (1:1 port from Vue api/sprints.ts)
 */
import request from '@/api/request'

export const getProjectSprints = (projectId: string) => request.get(`/sprints/project/${projectId}`)
export const createSprint = (data: any) => request.post('/sprints/', data)
export const startSprint = (sprintId: string) => request.patch(`/sprints/${sprintId}/start`)
export const completeSprint = (sprintId: string, data: any) => request.patch(`/sprints/${sprintId}/complete`, data)
