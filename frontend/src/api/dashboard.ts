/**
 * API 模块 — Dashboard (1:1 port from Vue api/dashboard.ts)
 */
import request from '@/api/request'

export const getMorningBriefing = () => request.get('/dashboard/morning-briefing')
export const getRiskAlerts = () => request.get('/dashboard/risk-alerts')
export const getTokenUsage = () => request.get('/dashboard/token-usage')
export const getWeeklyStats = () => request.get('/dashboard/weekly-stats')

export type ProbeStatus = 'normal' | 'watch' | 'needs_talk' | 'risk'

export interface PersonnelProbeItem {
  user_id: string
  name: string
  department: string
  role: string
  job_title: string
  work_status: string
  status_until: string | null
  probe_status: ProbeStatus
  note: string
  submitted_days: number
  missing_days: number
  report_count: number
  pass_rate: number | null
  avg_score: number | null
  fail_count: number
  blocker_count: number
  open_risk_count: number
  max_risk_days: number
  overdue_task_count: number
  max_overdue_days: number
  points_income: number
  points_adjustment: number
  latest_report_at: string | null
}

export interface PersonnelProbesResponse {
  window_days: number
  start_date: string
  end_date: string
  summary: Record<ProbeStatus, number>
  items: PersonnelProbeItem[]
}

export const getPersonnelProbes = (days: number) =>
  request.get<unknown, PersonnelProbesResponse>('/dashboard/personnel-probes', { params: { days } })

export type ContributionPeriod = 'month' | 'quarter' | 'year' | 'all'
export type ContributionRiskLevel = 'normal' | 'watch' | 'risk'

export interface PeopleContributionItem {
  user_id: string
  name: string
  department: string
  job_title: string
  role: string
  earned_points: number
  pending_points: number
  project_count: number
  milestone_count: number
  completed_milestone_count: number
  overdue_milestone_count: number
  progress_pct: number
  report_count: number
  avg_report_score: number | null
  open_risk_count: number
  risk_level: ContributionRiskLevel
}

export interface PeopleContributionResponse {
  period: ContributionPeriod
  start_date: string | null
  end_date: string
  summary: {
    people_count: number
    earned_points: number
    pending_points: number
    overdue_milestone_count: number
    risk_people_count: number
  }
  items: PeopleContributionItem[]
}

export interface PeopleContributionDetail {
  period: ContributionPeriod
  start_date: string | null
  end_date: string
  user: {
    user_id: string
    name: string
    department: string
    job_title: string
    role: string
  }
  projects: Array<{
    project_id: string
    code: string
    name: string
    health_status: string
    track: string
    role_in_project: string | null
    member_track: string
  }>
  milestones: Array<{
    allocation_id: string
    milestone_id: string
    project_id: string
    project_code: string
    project_name: string
    title: string
    node_order: number
    target_date: string | null
    milestone_status: string
    allocation_status: string
    initial_points: number
    final_points: number | null
    overdue: boolean
  }>
  ledger: Array<{
    ledger_id: string
    milestone_id: string | null
    milestone_title: string | null
    project_id: string | null
    project_name: string | null
    direction: string
    amount: number
    occurred_at: string
    reason: string
  }>
  reports: Array<{
    report_id: string
    report_date: string
    project_id: string | null
    ai_score: number | null
    pass_check: boolean | null
    tasks: string | null
    progress: number | string | null
    blocker: string | null
  }>
}

export const getPeopleContribution = (params?: {
  period?: ContributionPeriod
  department?: string
  project_id?: string
}) => request.get<unknown, PeopleContributionResponse>('/dashboard/people-contribution', { params })

export const getPeopleContributionDetail = (
  userId: string,
  params?: { period?: ContributionPeriod; project_id?: string },
) => request.get<unknown, PeopleContributionDetail>(`/dashboard/people-contribution/${userId}`, { params })

// V2.3 临时工单看板:本月 TOP N 员工工时 + 临时 vs 主干占比
export const getTempTicketSummary = (params?: { month_start?: string; month_end?: string; top_n?: number }) =>
  request.get('/dashboard/temp-ticket-summary', { params })

// V2.5 Stage 3:RiskAlert 批量软删 / 恢复 / 回收站
export type RiskAlertBatchResult = {
  requested: number
  deleted_count?: number
  deleted_ids?: string[]
  restored_count?: number
  restored_ids?: string[]
}

export type DeletedRiskAlert = {
  alert_id: string
  member: string
  department: string | null
  type: string
  description: string
  days_unresolved: number
  status: string
  created_at: string | null
  deleted_at: string | null
}

export const batchDeleteRiskAlerts = (ids: string[]) =>
  request.delete<unknown, RiskAlertBatchResult>('/dashboard/risk-alerts/batch', { data: { ids } })

export const batchRestoreRiskAlerts = (ids: string[]) =>
  request.patch<unknown, RiskAlertBatchResult>('/dashboard/risk-alerts/batch-restore', { ids })

export const getDeletedRiskAlerts = () =>
  request.get<unknown, { items: DeletedRiskAlert[]; total: number }>('/dashboard/risk-alerts/deleted')

// V2.6 数据生命周期治理
export const getDeletionGovernance = () =>
  request.get('/dashboard/deletion-governance')
