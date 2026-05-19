import request from './request'

export type RetroScope = 'okr_cycle' | 'project' | 'monthly' | 'incident'

export interface RetroItem {
  id: string
  title: string
  category: string
  scope?: RetroScope | null
  tags?: string | null
  source_type: string
  source_id?: string | null
  project_id?: string | null
  created_by?: string | null
  created_at?: string | null
}

export interface RetroItemDetail extends RetroItem {
  content: string
}

export interface RetroListResponse {
  total: number
  items: RetroItem[]
}

export interface GenerateRequest {
  scope: RetroScope
  target_id?: string
  project_id?: string
  incident_id?: string
  year?: number
  month?: number
  persist?: boolean
}

export interface GenerateResponse {
  scope: string
  title: string
  markdown: string
  knowledge_item_id?: string | null
}

export async function listRetros(params: {
  scope?: RetroScope
  page?: number
  page_size?: number
  project_id?: string
} = {}): Promise<RetroListResponse> {
  return request.get<unknown, RetroListResponse>('/retro/items', { params })
}

export async function getRetro(id: string): Promise<RetroItemDetail> {
  return request.get<unknown, RetroItemDetail>(`/retro/items/${id}`)
}

export async function deleteRetro(id: string): Promise<void> {
  await request.delete(`/retro/items/${id}`)
}

export async function generateRetro(payload: GenerateRequest): Promise<GenerateResponse> {
  return request.post<unknown, GenerateResponse>('/retro/generate', payload, {
    timeout: 240_000, // 复盘生成较慢
  })
}
