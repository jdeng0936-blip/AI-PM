/**
 * API 模块 — 项目 (1:1 port from Vue api/projects.ts)
 */
import request from '@/api/request'

export const getProjectsOverview = (
  includeArchived = false,
  healthStatus: 'green' | 'yellow' | 'red' | null = null,
  includeTemporary = false,
) =>
  request.get('/projects/overview', {
    params: {
      include_archived: includeArchived,
      include_temporary: includeTemporary,
      ...(healthStatus ? { health_status: healthStatus } : {}),
    },
  })
export const getProject = (id: string) => request.get(`/projects/${id}`)
export const getProjectGantt = (id: string) => request.get(`/projects/${id}/gantt`)
export const getProjectMembers = (id: string) => request.get(`/projects/${id}/members`)
export const addProjectMember = (id: string, data: any) => request.post(`/projects/${id}/members`, data)
export const createProject = (data: any) => request.post('/projects/', data)
export const updateProject = (id: string, data: any) => request.patch(`/projects/${id}`, data)
export const archiveProject = (id: string) => request.delete(`/projects/${id}`)
export const getGateReviews = (projectId: string) => request.get(`/gates/project/${projectId}`)
export const submitGateReview = (data: any) => request.post('/gates/review', data)
export const updateStage = (stageId: string, data: any) => request.patch(`/stages/${stageId}`, data)

// V2.4 Stage 2:批量软删项目(仅允许临时工单)
export const batchSoftDeleteProjects = (ids: string[]) =>
  request.delete('/projects/batch', { data: { ids } })

// V2.4 Stage 3 C3:批量恢复临时项目(仅 admin)
export const batchRestoreProjects = (ids: string[]) =>
  request.patch('/projects/batch-restore', { ids })
