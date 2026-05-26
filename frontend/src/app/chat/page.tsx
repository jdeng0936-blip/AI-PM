/**
 * app/chat/page.tsx — 总经理 AI 对话页(Function Calling 版本)
 *
 * 改造:
 * - 接入新版 /chat/ask: 拿到 answer + tool_calls + rounds
 * - Tool 调用过程逐条揭示(模拟流式),让用户看到 AI 的思考过程
 * - Answer 用 Markdown 渲染 + 打字机效果
 * - 顶部加「📑 一键生成本周周报」按钮
 */
'use client'

import { useState, useRef, useEffect } from 'react'
import {
  askAI,
  triggerWeeklyReport,
  type ChatResponse,
  type ToolCallTrace,
} from '@/api/chat'
import { toast } from 'sonner'
import {
  Send,
  Loader2,
  Bot,
  User,
  Wrench,
  ChevronDown,
  ChevronRight,
  FileText,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'

interface AssistantMessage {
  role: 'ai'
  question: string
  answer: string         // 已渲染完成的部分
  fullAnswer: string     // 完整文本(打字机源)
  toolCalls: ToolCallTrace[]
  visibleToolCount: number  // 已揭示几个 trace
  rounds: number
  model: string
  done: boolean
  timestamp: string
}

interface UserMessage {
  role: 'user'
  content: string
  timestamp: string
}

type Message = UserMessage | AssistantMessage

const QUICK_QUESTIONS = [
  '本周谁延期最多?',
  '采购部进度怎么样?',
  '目前有哪些未解决的风险?',
  '帮我列出表现最好的 5 位员工',
  '206 项目什么状况?',
  '今天哪些人没交日报?',
]

const TYPEWRITER_INTERVAL = 18      // 每字符延迟 ms
const TOOL_REVEAL_INTERVAL = 500    // tool trace 之间间隔 ms


export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [reportLoading, setReportLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── 收到完整 ChatResponse 后,启动「揭示 + 打字机」动画 ──
  function animateAssistantReply(resp: ChatResponse) {
    const ts = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    const initial: AssistantMessage = {
      role: 'ai',
      question: resp.question,
      answer: '',
      fullAnswer: resp.answer,
      toolCalls: resp.tool_calls,
      visibleToolCount: 0,
      rounds: resp.rounds,
      model: resp.model,
      done: false,
      timestamp: ts,
    }
    setMessages((prev) => [...prev, initial])

    // Step 1: 逐个揭示 tool_calls
    let toolIdx = 0
    const revealTool = () => {
      toolIdx += 1
      setMessages((prev) => {
        const next = [...prev]
        const last = next[next.length - 1] as AssistantMessage
        if (last?.role === 'ai') {
          next[next.length - 1] = { ...last, visibleToolCount: toolIdx }
        }
        return next
      })
      if (toolIdx < resp.tool_calls.length) {
        setTimeout(revealTool, TOOL_REVEAL_INTERVAL)
      } else {
        // Step 2: 打字机
        let charIdx = 0
        const typeChar = () => {
          charIdx += 1
          setMessages((prev) => {
            const next = [...prev]
            const last = next[next.length - 1] as AssistantMessage
            if (last?.role === 'ai') {
              const slice = resp.answer.slice(0, charIdx)
              const done = charIdx >= resp.answer.length
              next[next.length - 1] = { ...last, answer: slice, done }
            }
            return next
          })
          if (charIdx < resp.answer.length) {
            setTimeout(typeChar, TYPEWRITER_INTERVAL)
          }
        }
        typeChar()
      }
    }

    if (resp.tool_calls.length === 0) {
      // 没有 tool 调用直接进入打字机
      let charIdx = 0
      const typeChar = () => {
        charIdx += 1
        setMessages((prev) => {
          const next = [...prev]
          const last = next[next.length - 1] as AssistantMessage
          if (last?.role === 'ai') {
            next[next.length - 1] = {
              ...last,
              answer: resp.answer.slice(0, charIdx),
              done: charIdx >= resp.answer.length,
            }
          }
          return next
        })
        if (charIdx < resp.answer.length) setTimeout(typeChar, TYPEWRITER_INTERVAL)
      }
      typeChar()
    } else {
      setTimeout(revealTool, TOOL_REVEAL_INTERVAL)
    }
  }

  async function handleSend(question?: string) {
    const q = (question || input).trim()
    if (!q || loading) return

    const ts = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    setMessages((prev) => [...prev, { role: 'user', content: q, timestamp: ts }])
    setInput('')
    setLoading(true)

    try {
      const data = await askAI(q)
      animateAssistantReply(data)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'AI 回答失败,请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  async function handleGenerateWeeklyReport() {
    if (reportLoading) return
    setReportLoading(true)
    const ts = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: '📑 一键生成本周管理周报', timestamp: ts },
    ])
    try {
      const r = await triggerWeeklyReport('last_week')
      const fakeResp: ChatResponse = {
        question: '生成本周管理周报',
        answer: `📅 **周期**: ${r.week_range.start} → ${r.week_range.end}\n\n${r.markdown}`,
        tool_calls: [
          {
            tool: 'generate_weekly_report',
            arguments: { scope: 'last_week' },
            result_preview: `range=${r.week_range.start}→${r.week_range.end},日报${r.stats.report_count}条,风险${r.stats.risk_count}条`,
          },
        ],
        rounds: 1,
        model: 'deep_analysis',
      }
      animateAssistantReply(fakeResp)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '周报生成失败')
    } finally {
      setReportLoading(false)
    }
  }

  return (
    <div className="page-container flex flex-col" style={{ height: 'calc(100vh - 60px)' }}>
      {/* 标题 + 周报按钮 */}
      <div className="mb-4 shrink-0 flex items-center justify-between animate-in">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
            AI 战情助手
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            基于业务数据的智能问答 · Function Calling · 13 个 Tool
          </p>
        </div>
        <button
          onClick={handleGenerateWeeklyReport}
          disabled={reportLoading || loading}
          className="px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50 transition-all flex items-center gap-2"
          style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)' }}
        >
          {reportLoading ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <FileText size={16} />
          )}
          {reportLoading ? '生成中...' : '📑 生成本周周报'}
        </button>
      </div>

      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-2">
        {messages.length === 0 && (
          <EmptyState onPick={(q) => handleSend(q)} />
        )}

        {messages.map((msg, i) =>
          msg.role === 'user' ? (
            <UserBubble key={i} msg={msg} />
          ) : (
            <AssistantBubble key={i} msg={msg} />
          ),
        )}

        {loading && <LoadingBubble />}
        <div ref={bottomRef} />
      </div>

      {/* 输入区 */}
      <div className="shrink-0 flex gap-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
          placeholder="请输入您的问题(如:本周采购部表现怎么样?)"
          disabled={loading}
          className="flex-1 px-4 py-3 rounded-xl text-sm outline-none"
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            color: 'var(--color-text-primary)',
          }}
        />
        <button
          onClick={() => handleSend()}
          disabled={loading || !input.trim()}
          className="px-5 py-3 rounded-xl text-white font-medium text-sm disabled:opacity-50 transition-all"
          style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  )
}


// ────────────────────────────────────────────────────────────────
// 子组件
// ────────────────────────────────────────────────────────────────


function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="text-center py-16 animate-in">
      <Bot
        size={48}
        className="mx-auto mb-4 opacity-30"
        style={{ color: 'var(--color-text-secondary)' }}
      />
      <p className="text-sm mb-6" style={{ color: 'var(--color-text-secondary)' }}>
        我是您的 AI 战情助手,可以查询日报 / 风险 / 项目 / 人员表现。
        <br />
        试试这些问题👇
      </p>
      <div className="flex flex-wrap justify-center gap-2 max-w-3xl mx-auto">
        {QUICK_QUESTIONS.map((q) => (
          <button
            key={q}
            onClick={() => onPick(q)}
            className="px-4 py-2 rounded-lg text-xs transition-colors hover:opacity-80"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
            }}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  )
}


function UserBubble({ msg }: { msg: UserMessage }) {
  return (
    <div className="flex gap-3 justify-end animate-in">
      <div
        className="max-w-[75%] rounded-2xl px-4 py-3"
        style={{
          background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
          color: 'white',
        }}
      >
        <div className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</div>
        <div className="text-[10px] mt-2 opacity-60">{msg.timestamp}</div>
      </div>
      <div
        className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center"
        style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
      >
        <User size={16} color="white" />
      </div>
    </div>
  )
}


function AssistantBubble({ msg }: { msg: AssistantMessage }) {
  return (
    <div className="flex gap-3 animate-in">
      <div
        className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center"
        style={{ background: 'linear-gradient(135deg, #3b82f6, #a855f7)' }}
      >
        <Bot size={16} color="white" />
      </div>
      <div
        className="max-w-[85%] rounded-2xl px-4 py-3"
        style={{
          background: 'var(--color-bg-card)',
          color: 'var(--color-text-primary)',
          border: '1px solid var(--color-border-subtle)',
        }}
      >
        {/* Tool 调用过程 */}
        {msg.toolCalls.length > 0 && (
          <ToolTraceList traces={msg.toolCalls} visibleCount={msg.visibleToolCount} />
        )}

        {/* 答案 Markdown */}
        {msg.answer && (
          <div className="prose prose-sm prose-invert max-w-none text-sm leading-relaxed">
            <ReactMarkdown>{msg.answer}</ReactMarkdown>
            {!msg.done && <span className="cursor-blink">▍</span>}
          </div>
        )}

        {/* 元信息 */}
        <div className="text-[10px] mt-2 opacity-60 flex items-center gap-2">
          <span>{msg.timestamp}</span>
          {msg.done && (
            <>
              <span>·</span>
              <span>🔧 {msg.toolCalls.length} 次工具调用</span>
              <span>·</span>
              <span>🔁 {msg.rounds} 轮</span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}


function ToolTraceList({
  traces,
  visibleCount,
}: {
  traces: ToolCallTrace[]
  visibleCount: number
}) {
  return (
    <div className="mb-3 space-y-1.5">
      {traces.slice(0, visibleCount).map((tc, i) => (
        <ToolTraceItem key={i} trace={tc} />
      ))}
      {visibleCount < traces.length && (
        <div
          className="flex items-center gap-2 text-xs"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          <Loader2 size={12} className="animate-spin" />
          <span>正在调用 {traces[visibleCount]?.tool || '...'}</span>
        </div>
      )}
    </div>
  )
}


function ToolTraceItem({ trace }: { trace: ToolCallTrace }) {
  const [expanded, setExpanded] = useState(false)
  const hasError = !!trace.error
  return (
    <div
      className="rounded-md px-2.5 py-1.5 text-xs"
      style={{
        background: hasError ? 'rgba(239, 68, 68, 0.08)' : 'rgba(99, 102, 241, 0.08)',
        border: '1px solid var(--color-border-subtle)',
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center gap-1.5 w-full text-left"
        style={{ color: 'var(--color-text-primary)' }}
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {hasError ? (
          <AlertCircle size={12} className="text-rose-400" />
        ) : (
          <CheckCircle2 size={12} className="text-emerald-400" />
        )}
        <Wrench size={12} />
        <span className="font-medium">{trace.tool}</span>
        {!expanded && (
          <span className="opacity-60 truncate flex-1">
            ({Object.keys(trace.arguments).length} 个参数)
          </span>
        )}
      </button>
      {expanded && (
        <div className="mt-1.5 pl-5 space-y-1.5 opacity-90">
          <div>
            <span className="font-mono opacity-60">入参:</span>{' '}
            <code className="text-[11px] break-all">
              {JSON.stringify(trace.arguments)}
            </code>
          </div>
          <div>
            <span className="font-mono opacity-60">结果:</span>{' '}
            <code className="text-[11px] break-all">{trace.result_preview}</code>
          </div>
          {hasError && (
            <div className="text-rose-400">
              <span className="font-mono opacity-60">错误:</span> {trace.error}
            </div>
          )}
        </div>
      )}
    </div>
  )
}


function LoadingBubble() {
  return (
    <div className="flex gap-3 animate-in">
      <div
        className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center"
        style={{ background: 'linear-gradient(135deg, #3b82f6, #a855f7)' }}
      >
        <Bot size={16} color="white" />
      </div>
      <div className="stat-card flex items-center gap-2 px-4 py-3">
        <Loader2 size={16} className="animate-spin" style={{ color: '#3b82f6' }} />
        <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
          AI 正在思考(可能调用 Tool 取数据)...
        </span>
      </div>
    </div>
  )
}
