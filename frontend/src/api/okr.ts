import request from './request'

// ────────────────────────────────────────────────────────────────
// Types
// ────────────────────────────────────────────────────────────────

export interface OKRCycle {
  id: string
  name: string
  cycle_type: string
  start_date: string
  end_date: string
  status: string
}

export interface Objective {
  id: string
  cycle_id: string
  title: string
  description?: string | null
  owner_id: string
  owner_name?: string | null
  weight: number
  progress: number
  status: string
}

export interface KeyResult {
  id: string
  objective_id: string
  title: string
  description?: string | null
  metric_type: string
  unit?: string | null
  target_value: number
  current_value: number
  progress: number
  confidence: number
}

export interface TreeObjective {
  objective: Objective
  key_results: KeyResult[]
}

export interface OKRTreeResponse {
  cycle: OKRCycle
  objectives: TreeObjective[]
  summary: {
    objective_count: number
    kr_count: number
    avg_progress: number
    on_track?: number
    at_risk?: number
    behind?: number
  }
}

export interface ProgressLog {
  id: string
  kr_id: string
  report_id?: string | null
  previous_value: number
  new_value: number
  source: 'manual' | 'ai_extracted' | 'sprint_close' | 'system'
  confidence?: number | null
  note?: string | null
  created_at?: string | null
}

// ────────────────────────────────────────────────────────────────
// API
// ────────────────────────────────────────────────────────────────

export async function listCycles(): Promise<OKRCycle[]> {
  return request.get<unknown, OKRCycle[]>('/okr/cycles')
}

export async function createCycle(payload: {
  name: string
  cycle_type?: string
  start_date: string
  end_date: string
}): Promise<OKRCycle> {
  return request.post<unknown, OKRCycle>('/okr/cycles', payload)
}

export async function fetchTree(cycleId?: string): Promise<OKRTreeResponse> {
  return request.get<unknown, OKRTreeResponse>('/okr/tree', {
    params: cycleId ? { cycle_id: cycleId } : {},
  })
}

export async function createObjective(payload: {
  cycle_id: string
  title: string
  description?: string
  weight?: number
}): Promise<Objective> {
  return request.post<unknown, Objective>('/okr/objectives', payload)
}

export async function updateObjective(
  id: string,
  payload: Partial<{ title: string; description: string; weight: number; status: string }>,
): Promise<Objective> {
  return request.patch<unknown, Objective>(`/okr/objectives/${id}`, payload)
}

export async function deleteObjective(id: string): Promise<void> {
  await request.delete(`/okr/objectives/${id}`)
}

export async function createKR(payload: {
  objective_id: string
  title: string
  description?: string
  metric_type?: string
  target_value: number
  unit?: string
}): Promise<KeyResult> {
  return request.post<unknown, KeyResult>('/okr/key-results', payload)
}

export async function updateKR(
  id: string,
  payload: Partial<{
    title: string
    description: string
    current_value: number
    target_value: number
    confidence: number
    unit: string
    note: string
  }>,
): Promise<KeyResult> {
  return request.patch<unknown, KeyResult>(`/okr/key-results/${id}`, payload)
}

export async function deleteKR(id: string): Promise<void> {
  await request.delete(`/okr/key-results/${id}`)
}

export async function listProgressLogs(krId: string): Promise<ProgressLog[]> {
  return request.get<unknown, ProgressLog[]>(`/okr/key-results/${krId}/progress-logs`)
}
