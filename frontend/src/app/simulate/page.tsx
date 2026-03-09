/**
 * app/simulate/page.tsx — 模拟提交日报 (port from Vue SimulateReport.vue)
 */
'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Send, RotateCcw } from 'lucide-react'
import request from '@/lib/axios'

const TEAM = [
  { name: '张毅', department: '软件研发部', wechat: 'wx_zhangyi' },
  { name: '郭震', department: '软件研发部', wechat: 'wx_guozhen' },
  { name: '林跃文', department: '采购部', wechat: 'wx_linyuewen' },
  { name: '郑韬慧', department: '硬件测试部', wechat: 'wx_zhengtaohui' },
  { name: '陶群', department: '仓储物流部', wechat: 'wx_taoqun' },
  { name: '陈家云', department: '仓储物流部', wechat: 'wx_chenjiayun' },
]

export default function SimulatePage() {
  const [selectedUser, setSelectedUser] = useState(TEAM[0].wechat)
  const [reportText, setReportText] = useState('')
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<any>(null)

  async function handleSubmit() {
    if (!reportText.trim()) { toast.warning('请输入汇报内容'); return }
    setSending(true); setResult(null)
    try {
      const res: any = await request.post('/simulate/report', {
        wechat_userid: selectedUser,
        content: reportText,
      })
      setResult(res)
      toast.success('模拟提交成功，AI 已解析')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '模拟提交失败')
    } finally { setSending(false) }
  }

  const scoreColor = (s: number | null) => {
    if (s == null) return 'var(--color-text-secondary)'
    if (s >= 90) return '#22c55e'
    if (s >= 60) return '#eab308'
    return '#ef4444'
  }

  const pc = result?.parsed_content || {}

  return (
    <div className="page-container">
      <div className="mb-6 animate-in">
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>模拟提交</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>模拟企微日报提交，测试 AI 解析效果</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 输入区 */}
        <div className="stat-card animate-in" style={{ animationDelay: '0.1s' }}>
          <div className="section-title">📝 汇报输入</div>
          <div className="mb-4">
            <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>选择员工</label>
            <select value={selectedUser} onChange={(e) => setSelectedUser(e.target.value)} className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}>
              {TEAM.map((t) => <option key={t.wechat} value={t.wechat}>{t.name} ({t.department})</option>)}
            </select>
          </div>
          <div className="mb-4">
            <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>汇报内容</label>
            <textarea value={reportText} onChange={(e) => setReportText(e.target.value)} rows={10} placeholder="像在企微里打字一样，自然语言描述今天的工作内容..." className="w-full px-3 py-2 rounded-lg text-sm outline-none resize-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)', lineHeight: 1.8 }} />
          </div>
          <div className="flex gap-3">
            <button onClick={handleSubmit} disabled={sending} className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm text-white font-medium disabled:opacity-60" style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}>
              <Send size={16} />{sending ? 'AI 解析中...' : '提交 & AI 解析'}
            </button>
            <button onClick={() => { setReportText(''); setResult(null) }} className="px-4 py-2.5 rounded-lg text-sm" style={{ border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)' }}>
              <RotateCcw size={16} />
            </button>
          </div>
        </div>

        {/* 结果区 */}
        <div className="stat-card animate-in" style={{ animationDelay: '0.2s' }}>
          <div className="section-title">🤖 AI 解析结果</div>
          {result ? (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="text-center">
                  <div className="text-4xl font-bold" style={{ color: scoreColor(result.ai_score) }}>{result.ai_score ?? '-'}</div>
                  <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>AI 评分</div>
                </div>
                <div>
                  <span className="px-3 py-1 rounded-full text-xs font-medium" style={{ background: result.pass_check ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)', color: result.pass_check ? '#22c55e' : '#ef4444' }}>
                    {result.pass_check ? '✅ 合格' : '❌ 退回'}
                  </span>
                  {result.ai_comment && <div className="text-xs mt-2" style={{ color: 'var(--color-text-secondary)' }}>{result.ai_comment}</div>}
                </div>
              </div>
              {!result.pass_check && result.reject_reason && (
                <div className="rounded-lg p-3" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)' }}>
                  <div className="text-xs font-semibold mb-1" style={{ color: '#ef4444' }}>⚠️ 退回原因</div>
                  <div className="text-xs whitespace-pre-wrap" style={{ color: 'var(--color-text-secondary)' }}>{result.reject_reason}</div>
                </div>
              )}
              {result.suggested_guidance && (
                <div className="rounded-lg p-3" style={{ background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.25)' }}>
                  <div className="text-xs font-semibold mb-1" style={{ color: '#3b82f6' }}>📋 修改建议</div>
                  <div className="text-xs whitespace-pre-wrap" style={{ color: 'var(--color-text-secondary)' }}>{result.suggested_guidance}</div>
                </div>
              )}
              <div>
                <div className="text-xs font-semibold mb-2" style={{ color: '#3b82f6' }}>解析字段</div>
                <div className="space-y-2 text-xs">
                  {[['今日任务', pc.tasks], ['验收标准', pc.acceptance_criteria], ['完成进度', pc.progress != null ? `${pc.progress}%` : null], ['核心卡点', pc.blocker], ['解决方案', pc.next_step], ['预计解决', pc.eta]].map(([l, v]: any) => (
                    <div key={l} className="flex gap-2">
                      <span className="shrink-0" style={{ color: 'var(--color-text-secondary)', minWidth: 60 }}>{l}</span>
                      <span style={{ color: l === '核心卡点' && v ? '#ef4444' : 'var(--color-text-primary)' }}>{v || '-'}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center py-16" style={{ color: 'var(--color-text-muted)' }}>
              <div className="text-center">
                <Send size={48} className="mx-auto mb-3 opacity-30" />
                <p className="text-sm">提交汇报后，AI 解析结果将在此展示</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
