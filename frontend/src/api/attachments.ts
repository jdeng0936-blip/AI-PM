import request from './request'

export interface Attachment {
  id: string
  uploaded_by: string
  related_report_id?: string | null
  kind: 'image' | 'voice' | 'document' | 'other'
  file_name: string
  mime_type: string
  size_bytes: number
  file_url: string
  transcript?: string | null
  duration_ms?: number | null
  created_at?: string | null
}

export interface AttachmentListResponse {
  total: number
  items: Attachment[]
}

/** 上传单个附件文件(图片/PDF/文档等),返回元数据 + URL */
export async function uploadAttachment(
  file: File,
  relatedReportId?: string,
): Promise<Attachment> {
  const form = new FormData()
  form.append('file', file)
  if (relatedReportId) form.append('related_report_id', relatedReportId)
  return request.post<unknown, Attachment>('/attachments/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/** 列出当前用户的附件 */
export async function listMyAttachments(params?: {
  page?: number
  page_size?: number
  kind?: Attachment['kind']
}): Promise<AttachmentListResponse> {
  return request.get<unknown, AttachmentListResponse>('/attachments/', { params })
}

/** 列出某份日报的所有附件 */
export async function listAttachmentsByReport(
  reportId: string,
): Promise<Attachment[]> {
  return request.get<unknown, Attachment[]>(`/attachments/by-report/${reportId}`)
}

/** 删除一个附件(本人或 admin) */
export async function deleteAttachment(attachmentId: string): Promise<void> {
  await request.delete(`/attachments/${attachmentId}`)
}

// ──────────────────────────────────────────────────────────────
// ASR 语音转写
// ──────────────────────────────────────────────────────────────

export interface AsrStatus {
  configured: boolean
  provider: 'xunfei' | 'gemini' | 'none'
}

export interface TranscribeResponse {
  attachment_id?: string | null
  file_url?: string | null
  transcript?: string | null
  provider: string
  configured: boolean
}

export async function getAsrStatus(): Promise<AsrStatus> {
  return request.get<unknown, AsrStatus>('/asr/status')
}

/**
 * 上传音频文件 → 后端转写 → 返回文本(可选落库)。
 * save_attachment=false 时只转写,不保留文件。
 */
export async function transcribeAudio(
  file: Blob,
  options?: { save_attachment?: boolean; file_name?: string },
): Promise<TranscribeResponse> {
  const form = new FormData()
  const fname = options?.file_name || 'voice.webm'
  form.append('file', file, fname)
  form.append('save_attachment', String(options?.save_attachment ?? true))
  return request.post<unknown, TranscribeResponse>('/asr/transcribe', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 180_000, // ASR 可能较慢
  })
}
