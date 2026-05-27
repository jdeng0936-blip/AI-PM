import request from '@/api/request'

export type AnalyticsUserTrend = {
  user_id: string
  user_name: string
  department: string
  period_days: number
  summary: {
    report_days: number
    total_reports: number
    avg_score: number
    max_score: number
    min_score: number
    pass_rate: number
  }
  daily: Array<{
    date: string
    report_count: number
    avg_score: number
    max_score: number | null
    min_score: number | null
    pass_check: boolean
    submitted: boolean
    last_submitted_at: string | null
    submit_delay_minutes: number | null
  }>
}

export type AnalyticsDepartmentCompare = {
  period: string
  weeks: string[]
  departments: Array<{
    department: string
    total_users: number
    latest_avg_score: number
    latest_pass_rate: number
    latest_submitter_rate: number
    trend: Array<{
      week_start: string
      total_reports: number
      active_users: number
      total_users: number
      avg_score: number
      pass_count: number
      pass_rate: number
      submitter_rate: number
    }>
  }>
}

export type AnalyticsProjectHealth = {
  project_id: string
  project_code: string
  project_name: string
  current_health_score: number
  current_health_status: string | null
  period_days: number
  daily: Array<{
    date: string
    report_count: number
    avg_score: number
    pass_rate: number
    avg_progress: number
  }>
}

export type AnalyticsSprintEfficiency = {
  project_id: string | null
  count: number
  summary: {
    avg_velocity: number
    avg_completion_rate: number
  }
  sprints: Array<{
    project_id: string
    project_code: string
    project_name: string
    sprint_id: string
    sprint_number: number
    start_date: string
    end_date: string
    planned_story_points: number
    completed_story_points: number
    completion_rate: number
    velocity: number
    points_per_day: number
    health_score: number
  }>
}

const analyticsConfig = { baseURL: '/api' }

export const getAnalyticsUserTrend = (params?: { user_id?: string; days?: number }) =>
  request.get<unknown, AnalyticsUserTrend>('/analytics/user-trend', { ...analyticsConfig, params })

export const getAnalyticsDepartmentCompare = (params?: { period?: 'week'; weeks?: number }) =>
  request.get<unknown, AnalyticsDepartmentCompare>('/analytics/department-compare', { ...analyticsConfig, params })

export const getAnalyticsProjectHealth = (params: { project_id: string; days?: number }) =>
  request.get<unknown, AnalyticsProjectHealth>('/analytics/project-health', { ...analyticsConfig, params })

export const getAnalyticsSprintEfficiency = (params?: { project_id?: string; last_n?: number }) =>
  request.get<unknown, AnalyticsSprintEfficiency>('/analytics/sprint-efficiency', { ...analyticsConfig, params })
