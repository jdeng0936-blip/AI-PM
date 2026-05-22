/**
 * API 模块 — 通知/站内信
 */
import request from '@/api/request'

export type NotificationItem = {
  id: string
  user_id: string | null
  channel: string
  template: string
  status: string
  title: string | null
  body: string
  related_type: string | null
  related_id: string | null
  error_message: string | null
  retry_count: number
  sent_at: string | null
  read_at: string | null
  created_at: string
}

export type NotificationListResponse = {
  total: number
  items: NotificationItem[]
}

export const getUnreadCount = () =>
  request.get('/notifications/unread-count') as unknown as Promise<{ unread: number }>

export const getNotifications = (params: {
  page?: number
  page_size?: number
  channel?: string
  template?: string
  status?: string
} = {}) =>
  request.get('/notifications/', { params }) as unknown as Promise<NotificationListResponse>

export const markRead = (payload: { ids?: string[]; all?: boolean }) =>
  request.post('/notifications/mark-read', payload) as unknown as Promise<{ updated: number }>
