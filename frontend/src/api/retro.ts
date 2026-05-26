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
  // V2.5 Stage 3:后端已改为软删,接口签名不变
  await request.delete(`/retro/items/${id}`)
}

export async function generateRetro(payload: GenerateRequest): Promise<GenerateResponse> {
  return request.post<unknown, GenerateResponse>('/retro/generate', payload, {
    timeout: 240_000, // 复盘生成较慢
  })
}

// ────────────────────────────────────────────────────────────────
// V2.5 Stage 3:KnowledgeItem 批量软删 / 恢复 / 回收站(复盘和普通知识共用 knowledge_items 表)
// ────────────────────────────────────────────────────────────────

export type KnowledgeBatchResult = {
  requested: number
  deleted_count?: number
  deleted_ids?: string[]
  restored_count?: number
  restored_ids?: string[]
}

export type DeletedKnowledgeItem = {
  id: string
  title: string
  category: string
  tags: string | null
  source_type: string
  source_id: string | null
  project_id: string | null
  view_count: number
  helpful_count: number
  created_at: string | null
  deleted_at: string | null
}

export const batchDeleteKnowledgeItems = (ids: string[]) =>
  request.delete<unknown, KnowledgeBatchResult>('/knowledge/items/batch', { data: { ids } })

export const batchRestoreKnowledgeItems = (ids: string[]) =>
  request.patch<unknown, KnowledgeBatchResult>('/knowledge/items/batch-restore', { ids })

export const getDeletedKnowledgeItems = () =>
  request.get<unknown, { items: DeletedKnowledgeItem[]; total: number }>('/knowledge/items/deleted')
