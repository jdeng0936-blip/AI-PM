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

export async function askAI(question: string): Promise<ChatResponse> {
  return request.post<unknown, ChatResponse>('/chat/ask', { question })
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
