import request from './request'

export type MyDeletionBatch = {
  id: string
  table_name: string
  record_count: number
  deleted_at: string
  expires_at: string
  restored_at: string | null
  restored_by: string | null
  days_remaining: number | null
}

export type MyDeletionsResponse = {
  items: MyDeletionBatch[]
  total: number
}

export type RestoreMyDeletionResponse = {
  restored_count: number
  table_name: string
  batch_id: string
}

export const getMyDeletions = () =>
  request.get<unknown, MyDeletionsResponse>('/me/deletions')

export const restoreMyDeletionBatch = (batchId: string) =>
  request.patch<unknown, RestoreMyDeletionResponse>(`/me/deletions/${batchId}/restore`)
