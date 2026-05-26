import request from './request'

// ────────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────────

export type TaskStatus = 'todo' | 'in_progress' | 'blocked' | 'done' | 'cancelled'
export type TaskPriority = 'p0' | 'p1' | 'p2' | 'p3'

export interface SprintTaskItem {
  id: string
  sprint_id: string
  title: string
  description?: string | null
  kr_id?: string | null
  assignee_id?: string | null
  story_points: number
  actual_story_points?: number | null
  status: TaskStatus
  priority: TaskPriority
  is_on_critical_path: boolean
  depends_on: string[]
  planned_start?: string | null
  planned_end?: string | null
  actual_start?: string | null
  actual_end?: string | null
}

export interface SprintSummary {
  sprint_id: string
  sprint_number: number
  goal?: string | null
  start_date: string
  end_date: string
  status: 'planning' | 'active' | 'completed'
  health_score: number
  planned_sp: number
  completed_sp: number
  velocity_pct?: number | null
  retrospective?: any
}

export interface BurndownPoint {
  date: string
  points: number
  completed?: number
  blocked?: number
  done_count?: number
  in_progress_count?: number
}

export interface BurndownData {
  sprint: {
    id: string
    sprint_number: number
    goal?: string | null
    start_date: string
    end_date: string
    status: string
    planned_story_points: number
    completed_story_points: number
    health_score: number
  }
  total_points: number
  task_count: number
  ideal_line: BurndownPoint[]
  actual_line: BurndownPoint[]
  today_estimate: {
    burn_rate_per_day?: number
    projected_end_date?: string
    planned_end_date?: string
    on_track?: boolean
    days_delta?: number
  }
}

export interface CriticalPathTask {
  id: string
  title: string
  weight: number
  status: TaskStatus
  priority: TaskPriority
  is_on_critical_path: boolean
  assignee_id?: string | null
  blocked: boolean
}

export interface CriticalPathResult {
  tasks: CriticalPathTask[]
  edges: { from: string; to: string }[]
  critical_path: string[]
  critical_length: number
  has_cycle: boolean
}

export interface VelocityHistory {
  project_id: string
  history: Array<{
    sprint_number: number
    planned: number
    completed: number
    end_date: string
    health_score: number
  }>
  avg_velocity: number
  count: number
}


// ────────────────────────────────────────────────────────────────
// API
// ────────────────────────────────────────────────────────────────


export async function listSprints(projectId: string): Promise<SprintSummary[]> {
  return request.get<unknown, SprintSummary[]>(`/sprints/project/${projectId}`)
}

export async function listTasks(sprintId: string): Promise<SprintTaskItem[]> {
  return request.get<unknown, SprintTaskItem[]>(`/sprints/${sprintId}/tasks`)
}

export async function createTask(sprintId: string, payload: {
  title: string
  description?: string
  story_points?: number
  priority?: TaskPriority
  assignee_id?: string
  depends_on?: string[]
  planned_start?: string
  planned_end?: string
}): Promise<SprintTaskItem> {
  return request.post<unknown, SprintTaskItem>(`/sprints/${sprintId}/tasks`, {
    sprint_id: sprintId,
    ...payload,
  })
}

export async function updateTask(
  taskId: string,
  payload: Partial<Pick<
    SprintTaskItem,
    'title' | 'description' | 'status' | 'priority' | 'story_points'
    | 'actual_story_points' | 'depends_on' | 'planned_start' | 'planned_end'
    | 'actual_start' | 'actual_end'
  >>,
): Promise<SprintTaskItem> {
  return request.patch<unknown, SprintTaskItem>(`/sprints/tasks/${taskId}`, payload)
}

export async function deleteTask(taskId: string): Promise<void> {
  await request.delete(`/sprints/tasks/${taskId}`)
}

// V2.5 Stage 2:Sprint 任务批量软删 / 恢复 / 已删列表
export interface BatchTaskResult {
  requested: number
  deleted_count?: number
  restored_count?: number
  deleted_ids?: string[]
  restored_ids?: string[]
}

export async function batchDeleteTasks(ids: string[]): Promise<BatchTaskResult> {
  return request.delete<unknown, BatchTaskResult>('/sprints/tasks/batch', { data: { ids } })
}

export async function batchRestoreTasks(ids: string[]): Promise<BatchTaskResult> {
  return request.patch<unknown, BatchTaskResult>('/sprints/tasks/batch-restore', { ids })
}

export interface DeletedSprintTask {
  id: string
  title: string
  story_points: number
  status: TaskStatus
  priority: TaskPriority
  sprint_id: string
  sprint_number: number
  project_id: string
  deleted_at: string | null
}

export async function getDeletedTasks(): Promise<{ items: DeletedSprintTask[]; total: number }> {
  return request.get<unknown, { items: DeletedSprintTask[]; total: number }>(
    '/sprints/tasks/deleted',
  )
}

export async function getBurndown(sprintId: string): Promise<BurndownData> {
  return request.get<unknown, BurndownData>(`/sprints/${sprintId}/burndown`)
}

export async function triggerSnapshot(sprintId: string): Promise<{ snapshot_date: string }> {
  return request.post<unknown, any>(`/sprints/${sprintId}/snapshot`)
}

export async function getCriticalPath(
  sprintId: string,
  persist = false,
): Promise<CriticalPathResult> {
  return request.get<unknown, CriticalPathResult>(
    `/sprints/${sprintId}/critical-path`,
    { params: { persist } },
  )
}

export async function getVelocityHistory(
  projectId: string,
  lastN = 6,
): Promise<VelocityHistory> {
  return request.get<unknown, VelocityHistory>(
    `/sprints/project/${projectId}/velocity`,
    { params: { last_n: lastN } },
  )
}
