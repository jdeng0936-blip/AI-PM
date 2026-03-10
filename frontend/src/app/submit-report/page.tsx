'use client'

import { useState, useRef } from 'react'
import request from '@/api/request'
import { useAuthStore } from '@/stores/use-auth-store'

type ReportMode = 'plan' | 'review'

export default function SubmitReportPage() {
  const { userName } = useAuthStore()
  // 根据当前时间自动选择模式: 12:00 之前 → 晨规划, 之后 → 晚复核
  const defaultMode: ReportMode = new Date().getHours() < 12 ? 'plan' : 'review'
  const [mode, setMode] = useState<ReportMode>(defaultMode)
  const [rawText, setRawText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const recognitionRef = useRef<any>(null)

  // ─── 语音输入 (Web Speech API) ────────────────────────
  const startVoiceInput = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      setError('您的浏览器不支持语音输入，请使用 Chrome 浏览器')
      return
    }
    const recognition = new SpeechRecognition()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    recognitionRef.current = recognition

    let finalTranscript = rawText
    recognition.onresult = (event: any) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript
        } else {
          interim += event.results[i][0].transcript
        }
      }
      setRawText(finalTranscript + interim)
    }
    recognition.onerror = () => setIsRecording(false)
    recognition.onend = () => { setIsRecording(false); setRawText(finalTranscript) }
    recognition.start()
    setIsRecording(true)
    setError('')
  }

  const stopVoiceInput = () => {
    recognitionRef.current?.stop()
    setIsRecording(false)
  }

  // ─── 提交 ────────────────────────────────────────────
  const handleSubmit = async () => {
    if (!rawText.trim()) { setError('请输入内容'); return }
    setSubmitting(true); setError(''); setResult(null)
    try {
      const res = await request.post('/api/v1/simulate/web-submit', {
        raw_text: `[${mode === 'plan' ? '晨规划' : '晚复核'}] ${rawText}`,
      })
      setResult(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || '提交失败，请稍后重试')
    } finally { setSubmitting(false) }
  }

  // ─── 模板配置 ─────────────────────────────────────────
  const TEMPLATES = {
    plan: [
      {
        title: '📋 标准计划',
        text: '今天计划完成用户认证模块的开发，预计进度从60%推进到90%。需要产品确认登录交互流程。预期交付：登录注册功能可演示。',
      },
      {
        title: '🔧 研发计划',
        text: '今天计划：1) 完成数据库索引优化方案设计 2) 编写单元测试覆盖率达到80%。预期交付：优化方案文档 + 测试报告。需要DBA协助审核SQL。',
      },
      {
        title: '📦 采购计划',
        text: '今天计划跟进3家供应商的报价对比，完成采购申请审批流程。预期交付：供应商评估表。需要财务确认预算额度。',
      },
    ],
    review: [
      {
        title: '📝 标准复核',
        text: '今天完成了用户认证模块的开发，进度从60%推进到95%。成果已提交到Git仓库 v1.2.3。遗留卡点：微信OAuth回调需后端配合，预计明天解决。',
      },
      {
        title: '🔧 研发复核',
        text: '完成了数据库索引优化，查询性能提升50%。提交版本: commit abc1234, PR #42 已合并。单测覆盖率82%。无卡点，今日计划100%完成。',
      },
      {
        title: '📦 采购复核',
        text: '完成了3家供应商报价对比，选定A供应商（性价比最优）。已下单PCB板50片，预计周三到货。卡点：B物料延迟1天，已通知生产部并更新排期。',
      },
    ],
  }

  const modeConfig = {
    plan: {
      title: '☀️ 晨规划',
      subtitle: '规划今日工作目标、计划任务和预期交付物',
      placeholder: '描述今天计划做什么、目标是什么、预期交付什么成果、需要什么支持…',
      btnText: '📋 提交计划',
      btnTextLoading: 'AI 分析中...',
    },
    review: {
      title: '🌙 晚复核',
      subtitle: '汇报今日实际完成情况、代码提交、卡点和明日规划',
      placeholder: '描述今天实际做了什么、进度多少、Git提交了什么版本、遇到了什么卡点…',
      btnText: '🚀 提交复核',
      btnTextLoading: 'AI 解析中...',
    },
  }

  const cfg = modeConfig[mode]
  const templates = TEMPLATES[mode]

  return (
    <div className="space-y-6">
      {/* 模式切换 Tab */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => { setMode('plan'); setRawText(''); setResult(null); setError('') }}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-all ${
            mode === 'plan'
              ? 'bg-amber-600 text-white shadow-lg shadow-amber-600/30'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          ☀️ 晨规划
          {defaultMode === 'plan' && <span className="text-xs opacity-70">(当前)</span>}
        </button>
        <button
          onClick={() => { setMode('review'); setRawText(''); setResult(null); setError('') }}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-all ${
            mode === 'review'
              ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          🌙 晚复核
          {defaultMode === 'review' && <span className="text-xs opacity-70">(当前)</span>}
        </button>
        <div className="flex-1" />
        <span className="text-xs text-gray-500">
          {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}
        </span>
      </div>

      {/* 页头 */}
      <div>
        <h1 className="text-2xl font-bold text-white">{cfg.title}</h1>
        <p className="text-gray-400 mt-1">{cfg.subtitle}</p>
      </div>

      {/* 快捷模板 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {templates.map((t, i) => (
          <button
            key={`${mode}-${i}`}
            onClick={() => setRawText(t.text)}
            className="text-left p-3 rounded-lg border border-gray-700 bg-gray-800/50 hover:bg-gray-700/50 transition-colors"
          >
            <div className="text-sm font-medium text-gray-300">{t.title}</div>
            <div className="text-xs text-gray-500 mt-1 line-clamp-2">{t.text}</div>
          </button>
        ))}
      </div>

      {/* 输入区域 */}
      <div className={`bg-gray-800/50 rounded-xl border p-6 ${
        mode === 'plan' ? 'border-amber-800/50' : 'border-indigo-800/50'
      }`}>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-gray-300">
            {mode === 'plan' ? '今日计划内容' : '工作复核内容'}
          </label>
          <button
            onClick={isRecording ? stopVoiceInput : startVoiceInput}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
              isRecording
                ? 'bg-red-600 hover:bg-red-500 text-white animate-pulse'
                : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
            }`}
          >
            {isRecording ? (
              <>
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-300 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-400"></span>
                </span>
                录音中… 点击停止
              </>
            ) : '🎤 语音输入'}
          </button>
        </div>

        <textarea
          value={rawText}
          onChange={e => setRawText(e.target.value)}
          placeholder={cfg.placeholder}
          rows={6}
          className={`w-full bg-gray-900/50 border rounded-lg p-4 text-gray-200 placeholder:text-gray-500 focus:outline-none focus:ring-2 resize-none ${
            mode === 'plan'
              ? 'border-amber-900/50 focus:ring-amber-500'
              : 'border-indigo-900/50 focus:ring-indigo-500'
          }`}
        />

        {/* 晚复核额外字段: Git 提交 */}
        {mode === 'review' && (
          <div className="mt-3 flex items-center gap-2 text-xs text-gray-500">
            <span>💡 提示：在内容中提及 Git 版本号、PR 编号、commit ID，AI 会自动提取到「Git 版本」字段</span>
          </div>
        )}

        <div className="flex items-center justify-between mt-4">
          <span className="text-xs text-gray-500">当前用户: {userName || '未登录'}</span>
          <button
            onClick={handleSubmit}
            disabled={submitting || !rawText.trim()}
            className={`px-6 py-2.5 text-white rounded-lg font-medium transition-colors flex items-center gap-2 disabled:bg-gray-600 disabled:cursor-not-allowed ${
              mode === 'plan'
                ? 'bg-amber-600 hover:bg-amber-500'
                : 'bg-indigo-600 hover:bg-indigo-500'
            }`}
          >
            {submitting ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                {cfg.btnTextLoading}
              </>
            ) : cfg.btnText}
          </button>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-400">
          ❌ {error}
        </div>
      )}

      {/* AI 解析结果 */}
      {result && (
        <div className="bg-gray-800/50 rounded-xl border border-gray-700 p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">
              {mode === 'plan' ? '📋 计划分析结果' : '📊 复核解析结果'}
            </h2>
            <div className="flex items-center gap-3">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                result.pass_check
                  ? 'bg-green-900/50 text-green-400 border border-green-700'
                  : 'bg-red-900/50 text-red-400 border border-red-700'
              }`}>
                {result.pass_check ? '✅ 质检通过' : '❌ 需补充'}
              </span>
              <span className="text-2xl font-bold text-indigo-400">{result.ai_score}分</span>
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
                { label: '📊 起始进度', value: result.parsed_content.progress != null ? `${result.parsed_content.progress}%` : null },
                { label: '📅 预计完成', value: result.parsed_content.eta },
              ] : [
                { label: '📌 完成任务', value: result.parsed_content.tasks },
                { label: '📊 实际进度', value: result.parsed_content.progress != null ? `${result.parsed_content.progress}%` : null },
                { label: '🔖 Git 版本', value: result.parsed_content.git_version },
                { label: '✅ 验收人', value: result.parsed_content.reviewer },
                { label: '🚧 遗留卡点', value: result.parsed_content.blocker },
                { label: '💡 解决方案', value: result.parsed_content.next_step },
                { label: '📅 预计解决', value: result.parsed_content.eta },
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
