import request from './request'

export interface ToolCallTrace {
  tool: string
  arguments: Record<string, unknown>
  result_preview: string
  error?: string | null
}

export interface ChatResponse {
  question: string
  answer: string
  tool_calls: ToolCallTrace[]
  rounds: number
  model: string
  session_id: string
}

export interface ToolItem {
  name: string
  description: string
}

export interface ToolListResponse {
  count: number
  tools: ToolItem[]
}

export interface WeeklyReportResponse {
  week_range: { start: string; end: string }
  markdown: string
  stats: {
    report_count: number
    department_count: number
    risk_count: number
    project_count: number
  }
}

export async function askAI(
  question: string,
  sessionId?: string,
  allowedTools?: string[],
): Promise<ChatResponse> {
  const payload: Record<string, unknown> = { question }
  if (sessionId) payload.session_id = sessionId
  if (allowedTools && allowedTools.length > 0) payload.allowed_tools = allowedTools
  return request.post<unknown, ChatResponse>('/chat/ask', payload)
}

export async function listChatTools(): Promise<ToolListResponse> {
  return request.get<unknown, ToolListResponse>('/chat/tools')
}

export async function triggerWeeklyReport(
  scope: 'last_week' | 'this_week' = 'last_week',
): Promise<WeeklyReportResponse> {
  return request.post<unknown, WeeklyReportResponse>('/chat/weekly-report', { scope }, {
    timeout: 180_000, // 周报渲染较慢
  })
}

// ──────────────────────────────────────
// T-1201: 会话历史
// ──────────────────────────────────────

export interface ChatSessionListItem {
  id: string
  title: string
  message_count: number
  last_message_at: string | null
  created_at: string
}

export interface ChatSessionListResponse {
  items: ChatSessionListItem[]
  total: number
}

export type ChatRole = 'user' | 'assistant' | 'tool' | 'system'

export interface ChatMessageOut {
  id: string
  role: ChatRole
  content: string
  tool_calls?: Array<Record<string, unknown>> | null
  tool_call_id?: string | null
  created_at: string
}

export interface ChatSessionDetail {
  id: string
  title: string
  message_count: number
  last_message_at: string | null
  created_at: string
  messages: ChatMessageOut[]
}

export async function listChatSessions(params: {
  page?: number
  page_size?: number
  search?: string
} = {}): Promise<ChatSessionListResponse> {
  return request.get<unknown, ChatSessionListResponse>('/chat/sessions', { params })
}

export async function getChatSession(sessionId: string): Promise<ChatSessionDetail> {
  return request.get<unknown, ChatSessionDetail>(`/chat/sessions/${sessionId}`)
}

export async function updateChatSession(
  sessionId: string,
  title: string,
): Promise<ChatSessionListItem> {
  return request.patch<unknown, ChatSessionListItem>(`/chat/sessions/${sessionId}`, { title })
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  return request.delete<unknown, void>(`/chat/sessions/${sessionId}`)
}
