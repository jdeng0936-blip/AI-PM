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

// T-1301:零选择智能铺盘 + 晨晚闭环 + 督导追踪
export interface MyActiveTaskItem {
  id: string
  title: string
  status: string
  priority: string
  story_points: number
  planned_end: string | null
  is_on_critical_path: boolean
}

export interface MyActiveProjectItem {
  id: string
  code: string
  name: string
  health_status: string
  is_temporary: boolean
  member_track: string
  role_in_project: string | null
  tasks: MyActiveTaskItem[]
}

export interface MyActiveProjectsResponse {
  projects: MyActiveProjectItem[]
  total_projects: number
  total_tasks: number
}

export interface MorningPlanCardIn {
  project_id?: string
  sprint_task_id?: string
  work_tags?: string[]
  note?: string
}

export interface MorningBatchRequest {
  items: MorningPlanCardIn[]
  report_date?: string
}

export interface MorningBatchResponse {
  inserted: number
  report_ids: string[]
}

export type PlannedStatus = 'done' | 'partial' | 'delayed' | 'cancelled'

export interface EveningReviewCardIn {
  parent_report_id: string
  planned_status: PlannedStatus
  actual_note?: string
}

export interface EveningAdHocCardIn {
  project_id?: string
  sprint_task_id?: string
  work_tags?: string[]
  note: string
}

export interface EveningBatchRequest {
  reviews?: EveningReviewCardIn[]
  extras?: EveningAdHocCardIn[]
  report_date?: string
}

export interface EveningBatchResponse {
  review_count: number
  extra_count: number
  supervised_created: number
  supervised_closed: number
  evening_report_ids: string[]
}

export interface PendingFollowUpItem {
  supervised_id: string
  project_id: string | null
  project_name: string | null
  sprint_task_id: string | null
  sprint_task_title: string | null
  source_report_id: string
  source_planned_status: PlannedStatus
  source_note: string | null
  created_at: string
}

export interface PendingFollowUpsResponse {
  items: PendingFollowUpItem[]
  total: number
}

export const WORK_TAG_CHOICES = [
  '研发',
  '测试',
  '评审',
  '部署',
  '沟通',
  '调研',
  '文档',
  '学习',
] as const
export type WorkTag = (typeof WORK_TAG_CHOICES)[number]

export async function getMyActiveProjects(): Promise<MyActiveProjectsResponse> {
  return request.get<unknown, MyActiveProjectsResponse>('/reports/projects/my-active')
}

export async function submitMorningBatch(body: MorningBatchRequest): Promise<MorningBatchResponse> {
  return request.post<unknown, MorningBatchResponse>('/reports/morning-batch', body)
}

export async function submitEveningBatch(body: EveningBatchRequest): Promise<EveningBatchResponse> {
  return request.post<unknown, EveningBatchResponse>('/reports/evening-batch', body)
}

export async function getPendingFollowUps(): Promise<PendingFollowUpsResponse> {
  return request.get<unknown, PendingFollowUpsResponse>('/reports/pending-follow-ups')
}
