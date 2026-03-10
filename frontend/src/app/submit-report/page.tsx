'use client'

import { useState, useRef } from 'react'
import request from '@/api/request'
import { useAuthStore } from '@/stores/use-auth-store'

type ReportMode = 'plan' | 'review'
type InputStyle = 'form' | 'free'

// ─── 表单字段定义 ─────────────────────────────────────
const FORM_FIELDS = {
  plan: [
    { key: 'tasks', label: '📌 今日计划', placeholder: '今天打算做什么？（如：完成微信机器人语音指令模块开发）', required: true },
    { key: 'goal', label: '🎯 目标描述', placeholder: '具体目标是什么？（如：实现语音转文字后触发电脑操作）', required: true },
    { key: 'progress', label: '📊 进度预期', placeholder: '预计从多少推进到多少？（如：从40%推进到70%）', required: true },
    { key: 'acceptance', label: '✅ 验收标准', placeholder: '怎样算完成？（如：发送3种指令后5秒内响应）', required: false },
    { key: 'deliverable', label: '📦 预期交付', placeholder: '产出什么成果？（如：可演示的语音控制Demo）', required: false },
    { key: 'support', label: '🤝 需要协助', placeholder: '需要谁帮忙？（如：需要后端同事配置WebSocket）', required: false },
  ],
  review: [
    { key: 'tasks', label: '📌 完成任务', placeholder: '今天实际做了什么？', required: true },
    { key: 'progress', label: '📊 实际进度', placeholder: '完成了多少？（如：80%）', required: true },
    { key: 'git', label: '🔖 代码提交', placeholder: '如有代码提交填写（如：commit abc1234 或 v1.2.3），无代码项目可留空', required: false },
    { key: 'acceptance', label: '✅ 验收结果', placeholder: '验收是否通过？（如：3项测试全部通过）', required: false },
    { key: 'reviewer', label: '👤 验收人', placeholder: '谁验收的？（如：张毅）', required: false },
    { key: 'blocker', label: '🚧 遗留卡点', placeholder: '还有什么没解决？无则留空', required: false },
    { key: 'support', label: '🤝 所需支持', placeholder: '需要谁帮忙解决卡点？', required: false },
  ],
}

export default function SubmitReportPage() {
  const { userName } = useAuthStore()
  const defaultMode: ReportMode = new Date().getHours() < 12 ? 'plan' : 'review'
  const [mode, setMode] = useState<ReportMode>(defaultMode)
  const [inputStyle, setInputStyle] = useState<InputStyle>('form')
  const [formData, setFormData] = useState<Record<string, string>>({})
  const [freeText, setFreeText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const recognitionRef = useRef<any>(null)

  // ─── 表单 → 结构化文本 ─────────────────────────────
  const formToText = (): string => {
    const fields = FORM_FIELDS[mode]
    const parts: string[] = []
    for (const f of fields) {
      const val = formData[f.key]?.trim()
      if (val) {
        parts.push(`【${f.label.replace(/^.{2}\s/, '')}】${val}`)
      }
    }
    return parts.join('\n')
  }

  const getRawText = (): string => {
    return inputStyle === 'form' ? formToText() : freeText
  }

  // ─── 语音输入 ──────────────────────────────────────
  const startVoiceInput = () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) { setError('请使用 Chrome 浏览器以启用语音输入'); return }
    const recognition = new SR()
    recognition.lang = 'zh-CN'; recognition.continuous = true; recognition.interimResults = true
    recognitionRef.current = recognition
    let final = freeText
    recognition.onresult = (e: any) => {
      let interim = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) final += e.results[i][0].transcript
        else interim += e.results[i][0].transcript
      }
      setFreeText(final + interim)
    }
    recognition.onerror = () => setIsRecording(false)
    recognition.onend = () => { setIsRecording(false); setFreeText(final) }
    recognition.start(); setIsRecording(true); setError('')
  }
  const stopVoiceInput = () => { recognitionRef.current?.stop(); setIsRecording(false) }

  // ─── 提交 ──────────────────────────────────────────
  const handleSubmit = async () => {
    const text = getRawText()
    if (!text.trim()) { setError('请填写内容'); return }
    setSubmitting(true); setError(''); setResult(null)
    try {
      const res = await request.post('/simulate/web-submit', {
        raw_text: `[${mode === 'plan' ? '晨规划' : '晚复核'}] ${text}`,
      })
      setResult(res)
    } catch (err: any) {
      setError(err.response?.data?.detail || '提交失败')
    } finally { setSubmitting(false) }
  }

  const switchMode = (m: ReportMode) => {
    setMode(m); setFormData({}); setFreeText(''); setResult(null); setError('')
  }

  const fields = FORM_FIELDS[mode]
  const modeLabel = mode === 'plan' ? '晨规划' : '晚复核'

  return (
    <div className="space-y-6">
      {/* 顶部: 模式切换 + 输入方式切换 */}
      <div className="flex items-center gap-4 flex-wrap">
        <button onClick={() => switchMode('plan')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-all ${
            mode === 'plan' ? 'bg-amber-600 text-white shadow-lg shadow-amber-600/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}>
          ☀️ 晨规划 {defaultMode === 'plan' && <span className="text-xs opacity-70">(当前)</span>}
        </button>
        <button onClick={() => switchMode('review')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-all ${
            mode === 'review' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}>
          🌙 晚复核 {defaultMode === 'review' && <span className="text-xs opacity-70">(当前)</span>}
        </button>
        <div className="flex-1" />

        {/* 输入方式切换 */}
        <div className="flex items-center bg-gray-800 rounded-lg p-0.5">
          <button onClick={() => setInputStyle('form')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              inputStyle === 'form' ? 'bg-gray-600 text-white' : 'text-gray-400 hover:text-gray-300'
            }`}>
            📋 结构化填写
          </button>
          <button onClick={() => setInputStyle('free')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              inputStyle === 'free' ? 'bg-gray-600 text-white' : 'text-gray-400 hover:text-gray-300'
            }`}>
            ✏️ 自由输入
          </button>
        </div>

        <span className="text-xs text-gray-500">
          {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}
        </span>
      </div>

      {/* 页头 */}
      <div>
        <h1 className="text-2xl font-bold text-white">
          {mode === 'plan' ? '☀️ 晨规划' : '🌙 晚复核'}
        </h1>
        <p className="text-gray-400 mt-1">
          {mode === 'plan'
            ? '规划今日工作目标、计划任务和预期交付物'
            : '汇报今日实际完成情况、代码提交、卡点和明日规划'}
        </p>
      </div>

      {/* ═══ 结构化表单 ═══ */}
      {inputStyle === 'form' && (
        <div className={`bg-gray-800/50 rounded-xl border p-6 space-y-4 ${
          mode === 'plan' ? 'border-amber-800/50' : 'border-indigo-800/50'
        }`}>
          {fields.map((f) => (
            <div key={f.key}>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-300 mb-1.5">
                {f.label}
                {f.required && <span className="text-red-400 text-xs">必填</span>}
                {!f.required && <span className="text-gray-600 text-xs">选填（加分项）</span>}
              </label>
              {f.key === 'tasks' || f.key === 'goal' ? (
                <textarea
                  value={formData[f.key] || ''}
                  onChange={e => setFormData(prev => ({ ...prev, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  rows={2}
                  className={`w-full bg-gray-900/50 border rounded-lg p-3 text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 resize-none text-sm ${
                    mode === 'plan' ? 'border-amber-900/30 focus:ring-amber-500' : 'border-indigo-900/30 focus:ring-indigo-500'
                  }`}
                />
              ) : (
                <input
                  type="text"
                  value={formData[f.key] || ''}
                  onChange={e => setFormData(prev => ({ ...prev, [f.key]: e.target.value }))}
                  placeholder={f.placeholder}
                  className={`w-full bg-gray-900/50 border rounded-lg p-3 text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 text-sm ${
                    mode === 'plan' ? 'border-amber-900/30 focus:ring-amber-500' : 'border-indigo-900/30 focus:ring-indigo-500'
                  }`}
                />
              )}
            </div>
          ))}

          <div className="flex items-center justify-between pt-2">
            <span className="text-xs text-gray-500">当前用户: {userName || '未登录'}</span>
            <button onClick={handleSubmit} disabled={submitting}
              className={`px-6 py-2.5 text-white rounded-lg font-medium transition-colors flex items-center gap-2 disabled:bg-gray-600 disabled:cursor-not-allowed ${
                mode === 'plan' ? 'bg-amber-600 hover:bg-amber-500' : 'bg-indigo-600 hover:bg-indigo-500'
              }`}>
              {submitting ? (
                <><svg className="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg> AI 分析中...</>
              ) : mode === 'plan' ? '📋 提交计划' : '🚀 提交复核'}
            </button>
          </div>
        </div>
      )}

      {/* ═══ 自由文本输入 ═══ */}
      {inputStyle === 'free' && (
        <div className={`bg-gray-800/50 rounded-xl border p-6 ${
          mode === 'plan' ? 'border-amber-800/50' : 'border-indigo-800/50'
        }`}>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-gray-300">自由描述</label>
            <button onClick={isRecording ? stopVoiceInput : startVoiceInput}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                isRecording ? 'bg-red-600 hover:bg-red-500 text-white animate-pulse' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}>
              {isRecording ? (
                <><span className="relative flex h-2.5 w-2.5"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-300 opacity-75"></span><span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-400"></span></span>录音中… 点击停止</>
              ) : '🎤 语音输入'}
            </button>
          </div>
          <textarea value={freeText} onChange={e => setFreeText(e.target.value)}
            placeholder="像跟同事说话一样，描述今天的工作内容…也可以点击🎤语音输入"
            rows={6}
            className={`w-full bg-gray-900/50 border rounded-lg p-4 text-gray-200 placeholder:text-gray-500 focus:outline-none focus:ring-2 resize-none ${
              mode === 'plan' ? 'border-amber-900/50 focus:ring-amber-500' : 'border-indigo-900/50 focus:ring-indigo-500'
            }`}
          />
          <div className="flex items-center justify-between mt-4">
            <span className="text-xs text-gray-500">当前用户: {userName || '未登录'}</span>
            <button onClick={handleSubmit} disabled={submitting || !freeText.trim()}
              className={`px-6 py-2.5 text-white rounded-lg font-medium transition-colors flex items-center gap-2 disabled:bg-gray-600 disabled:cursor-not-allowed ${
                mode === 'plan' ? 'bg-amber-600 hover:bg-amber-500' : 'bg-indigo-600 hover:bg-indigo-500'
              }`}>
              {submitting ? 'AI 分析中...' : mode === 'plan' ? '📋 提交计划' : '🚀 提交复核'}
            </button>
          </div>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-400">❌ {error}</div>
      )}

      {/* ═══ 质检驳回 ═══ */}
      {result && !result.pass_check && (
        <div className="bg-red-950/40 rounded-xl border-2 border-red-700 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-red-400">🚫 质检未通过 — 请修改后重新提交</h2>
            <span className="text-2xl font-bold text-red-400">{result.ai_score}分</span>
          </div>
          <div className="bg-red-900/30 rounded-lg p-4 border border-red-800">
            <div className="text-sm text-red-300 font-medium mb-1">❌ 驳回原因</div>
            <div className="text-red-200">{result.reject_reason}</div>
          </div>
          {result.suggested_guidance && (
            <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
              <div className="text-sm text-amber-400 font-medium mb-2">📝 修改建议</div>
              <div className="text-gray-300 whitespace-pre-line text-sm">{result.suggested_guidance}</div>
            </div>
          )}
          <div className="bg-gray-900/50 rounded-lg p-4">
            <div className="text-sm text-gray-400 mb-1">💬 AI 点评</div>
            <div className="text-gray-200">{result.ai_comment}</div>
          </div>
          <button onClick={() => { setResult(null); window.scrollTo({ top: 0, behavior: 'smooth' }) }}
            className="w-full py-3 bg-amber-600 hover:bg-amber-500 text-white rounded-lg font-medium transition-colors">
            ✏️ 修改内容后重新提交
          </button>
          <div className="text-xs text-gray-600 text-right">
            Token 消耗: prompt {result.tokens_used?.prompt} + completion {result.tokens_used?.completion} · 此次未入库
          </div>
        </div>
      )}

      {/* ═══ 质检通过 ═══ */}
      {result && result.pass_check && (
        <div className="bg-gray-800/50 rounded-xl border-2 border-green-700 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">
              {mode === 'plan' ? '📋 计划已提交' : '📊 复核已提交'}
            </h2>
            <div className="flex items-center gap-3">
              <span className="px-3 py-1 rounded-full text-sm font-medium bg-green-900/50 text-green-400 border border-green-700">
                ✅ 质检通过 · 已入库
              </span>
              <span className="text-2xl font-bold text-green-400">{result.ai_score}分</span>
            </div>
          </div>
          <div className="bg-gray-900/50 rounded-lg p-4">
            <div className="text-sm text-gray-400 mb-1">💬 AI 点评</div>
            <div className="text-gray-200">{result.ai_comment}</div>
          </div>
          {result.parsed_content && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {(mode === 'plan' ? [
                { label: '🎯 今日目标', value: result.parsed_content.tasks },
                { label: '✅ 验收标准', value: result.parsed_content.acceptance_criteria },
                { label: '📦 预期交付', value: result.parsed_content.deliverable },
                { label: '🔧 所需支持', value: result.parsed_content.support_needed },
                { label: '📊 进度预期', value: result.parsed_content.progress != null ? `${result.parsed_content.progress}%` : null },
              ] : [
                { label: '📌 完成任务', value: result.parsed_content.tasks },
                { label: '📊 实际进度', value: result.parsed_content.progress != null ? `${result.parsed_content.progress}%` : null },
                { label: '🔖 Git 版本', value: result.parsed_content.git_version },
                { label: '✅ 验收人', value: result.parsed_content.reviewer },
                { label: '🚧 遗留卡点', value: result.parsed_content.blocker },
                { label: '🔧 所需支持', value: result.parsed_content.support_needed },
              ]).map((field, i) => (
                <div key={i} className="bg-gray-900/30 rounded-lg p-3">
                  <div className="text-xs text-gray-500">{field.label}</div>
                  <div className="text-sm text-gray-300 mt-1">
                    {field.value || <span className="text-gray-600">—</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
          {result.management_alert && (
            <div className="bg-amber-900/30 border border-amber-700 rounded-lg p-4">
              <div className="text-sm text-amber-400 font-medium">⚠️ 管理预警</div>
              <div className="text-sm text-amber-300 mt-1">{result.management_alert}</div>
            </div>
          )}
          <div className="text-xs text-gray-600 text-right">
            Token 消耗: prompt {result.tokens_used?.prompt} + completion {result.tokens_used?.completion}
          </div>
        </div>
      )}
    </div>
  )
}
