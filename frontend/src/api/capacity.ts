import request from './request'

export type CapacityLevel = 'idle' | 'healthy' | 'high' | 'overload'

export interface MemberCapacity {
  user_id: string
  user_name: string
  department: string
  user_status: string
  base_capacity: number
  effective_capacity: number
  velocity_factor: number
  status_factor: number
  allocated_points: number
  completed_points: number
  active_task_count: number
  blocked_task_count: number
  critical_path_task_count: number
  utilization: number
  level: CapacityLevel
  active_tasks: Array<{
    id: string
    title: string
    story_points: number
    status: string
    priority: string
    is_on_critical_path: boolean
  }>
}

export interface SprintCapacityResponse {
  sprint_id: string
  sprint_number?: number
  sprint_goal?: string | null
  count: number
  members: MemberCapacity[]
  summary?: { overload: number; high: number; healthy: number; idle: number }
}

export interface RebalanceMove {
  task_id: string
  title: string
  points: number
  from_user: string
  from_user_id: string
  to_user: string
  to_user_id: string
  department_match: boolean
}

export interface RebalanceResponse {
  overloaded: any[]
  idle: any[]
  moves: RebalanceMove[]
}

export interface DeptCapacity {
  department: string
  member_count: number
  total_capacity: number
  total_allocated: number
  total_completed: number
  utilization: number
  level: CapacityLevel
  avg_member_util: number
}

export interface DeptSummaryResponse {
  departments: DeptCapacity[]
  count: number
}

export interface CapacityTimelinePoint {
  sprint_id: string
  sprint_number: number
  start_date: string
  end_date: string
  utilization: number
  level: CapacityLevel
  allocated_points: number
  completed_points: number
  effective_capacity: number
}


// ────────────────────────────────────────────────────────────────
// API
// ────────────────────────────────────────────────────────────────


export async function getSprintCapacity(sprintId: string): Promise<SprintCapacityResponse> {
  return request.get<unknown, SprintCapacityResponse>(`/capacity/sprint/${sprintId}`)
}

export async function snapshotSprintCapacity(sprintId: string): Promise<{ snapshot_count: number }> {
  return request.post<unknown, any>(`/capacity/sprint/${sprintId}/snapshot`)
}

export async function getRebalance(sprintId: string): Promise<RebalanceResponse> {
  return request.get<unknown, RebalanceResponse>(`/capacity/sprint/${sprintId}/rebalance`)
}

export async function getDepartmentSummary(
  sprintId?: string,
): Promise<DeptSummaryResponse> {
  return request.get<unknown, DeptSummaryResponse>('/capacity/department-summary', {
    params: sprintId ? { sprint_id: sprintId } : {},
  })
}

export async function getUserCapacityTimeline(
  userId: string, limit = 12,
): Promise<{ user: any; count: number; timeline: CapacityTimelinePoint[] }> {
  return request.get<unknown, any>(`/capacity/users/${userId}/timeline`, {
    params: { limit },
  })
}
