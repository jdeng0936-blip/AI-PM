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

// V2.5 Stage 2:批量移出成员(软退场,SET left_at = today())
export const batchRemoveProjectMembers = (projectId: string, memberIds: string[]) =>
  request.delete<unknown, {
    requested: number
    removed_count: number
    removed_member_ids: string[]
  }>(`/projects/${projectId}/members/batch`, { data: { member_ids: memberIds } })

// T-1105 立项时一站式指派成员(可选,默认空 -> 走"零成员"路径)
export interface ProjectMemberInit {
  user_id: string  // UUID
  track: 'hardware' | 'software' | 'both'
  role_in_project?: string
  name?: string
  department?: string
}

export interface CreateProjectPayload {
  name: string
  code?: string
  description?: string
  track?: string
  planned_launch_date?: string  // ISO date
  budget_total?: number
  contribution_total_points?: number
  budget_alert_threshold?: number
  is_temporary?: boolean
  members?: ProjectMemberInit[]  // T-1105 新增
  seed_milestones?: boolean  // T-1401:默认 true,立项时种入标准模板
}

export const createProject = (data: CreateProjectPayload) => request.post('/projects/', data)
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

// V2.4 Stage 3 C4:回收站 — 已软删的临时项目列表(admin only)
export const getDeletedProjects = () => request.get('/projects/deleted')

// T-1106 项目跟进记录(轻量时间轴)
export interface ProjectFollowUp {
  id: string
  project_id: string
  content: string
  created_by: string | null
  created_by_name: string | null
  created_at: string  // ISO timestamp
}

export const createFollowup = (projectId: string, content: string) =>
  request.post<unknown, { id: string; project_id: string; content: string; created_at: string }>(
    `/projects/${projectId}/followups`,
    { content },
  )

export const listFollowups = (projectId: string, limit = 50) =>
  request.get<unknown, ProjectFollowUp[]>(`/projects/${projectId}/followups`, { params: { limit } })
