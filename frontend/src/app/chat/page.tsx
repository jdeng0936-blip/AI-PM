/**
 * app/chat/page.tsx — 总经理 AI 对话页
 *
 * 自然语言向 AI 提问，获取基于业务数据的智能回答。
 */
'use client'

import { useState, useRef, useEffect } from 'react'
import { askAI } from '@/api/trends'
import { toast } from 'sonner'
import { MessageSquare, Send, Loader2, Bot, User } from 'lucide-react'

interface Message {
  role: 'user' | 'ai'
  content: string
  timestamp: string
  dataContext?: Record<string, number>
}

const QUICK_QUESTIONS = [
  '本周谁延期最多？',
  '采购部进度怎么样？',
  '目前有哪些未解决的风险？',
  '帮我总结一下全员工作状态',
]

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend(question?: string) {
    const q = (question || input).trim()
    if (!q || loading) return

    const userMsg: Message = {
      role: 'user',
      content: q,
      timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setLoading(true)

    try {
      const data = await askAI(q) as any
      const aiMsg: Message = {
        role: 'ai',
        content: data.answer,
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        dataContext: data.data_context,
      }
      setMessages((prev) => [...prev, aiMsg])
    } catch {
      toast.error('AI 回答失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-container flex flex-col" style={{ height: 'calc(100vh - 60px)' }}>
      {/* 标题 */}
      <div className="mb-4 shrink-0 animate-in">
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
          AI 管理助手
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
          基于业务数据的智能问答 · 支持日报/风险/项目查询
        </p>
      </div>

      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto space-y-4 mb-4">
        {messages.length === 0 && (
          <div className="text-center py-16 animate-in">
            <Bot size={48} className="mx-auto mb-4 opacity-30" style={{ color: 'var(--color-text-secondary)' }} />
            <p className="text-sm mb-6" style={{ color: 'var(--color-text-secondary)' }}>
              我是您的 AI 管理助手，您可以用自然语言向我提问
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {QUICK_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => handleSend(q)}
                  className="px-4 py-2 rounded-lg text-xs transition-colors"
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
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-3 animate-in ${msg.role === 'user' ? 'justify-end' : ''}`}
          >
            {msg.role === 'ai' && (
              <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center"
                style={{ background: 'linear-gradient(135deg, #3b82f6, #a855f7)' }}>
                <Bot size={16} color="white" />
              </div>
            )}
            <div
              className="max-w-[75%] rounded-2xl px-4 py-3"
              style={{
                background: msg.role === 'user' ? 'linear-gradient(135deg, #3b82f6, #6366f1)' : 'var(--color-bg-card)',
                color: msg.role === 'user' ? 'white' : 'var(--color-text-primary)',
                border: msg.role === 'ai' ? '1px solid var(--color-border-subtle)' : 'none',
              }}
            >
              <div className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</div>
              <div className="text-[10px] mt-2 opacity-60">{msg.timestamp}</div>
              {msg.dataContext && (
                <div className="text-[10px] mt-1 opacity-50">
                  📊 检索了 {msg.dataContext.reports_count} 条日报、{msg.dataContext.risks_count} 条风险
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center"
                style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}>
                <User size={16} color="white" />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-3 animate-in">
            <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center"
              style={{ background: 'linear-gradient(135deg, #3b82f6, #a855f7)' }}>
              <Bot size={16} color="white" />
            </div>
            <div className="stat-card flex items-center gap-2 px-4 py-3">
              <Loader2 size={16} className="animate-spin" style={{ color: '#3b82f6' }} />
              <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>AI 正在分析数据...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 输入区 */}
      <div className="shrink-0 flex gap-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
          placeholder="请输入您的问题..."
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
