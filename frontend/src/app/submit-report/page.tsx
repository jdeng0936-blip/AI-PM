'use client'

import { useState, useRef } from 'react'
import request from '@/api/request'
import { useAuthStore } from '@/stores/use-auth-store'

export default function SubmitReportPage() {
  const { userName } = useAuthStore()
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

    recognition.onerror = (event: any) => {
      setIsRecording(false)
      if (event.error === 'not-allowed') {
        setError('请允许麦克风权限后重试')
      }
    }

    recognition.onend = () => {
      setIsRecording(false)
      setRawText(finalTranscript)
    }

    recognition.start()
    setIsRecording(true)
    setError('')
  }

  const stopVoiceInput = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
    }
    setIsRecording(false)
  }

  // ─── 提交日报（使用 JWT 鉴权，不需要传 wechat_userid）────
  const handleSubmit = async () => {
    if (!rawText.trim()) {
      setError('请输入今日工作汇报内容')
      return
    }

    setSubmitting(true)
    setError('')
    setResult(null)

    try {
      const res = await request.post('/api/v1/simulate/web-submit', {
        raw_text: rawText,
      })
      setResult(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || err.response?.data?.error || '提交失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  const templates = [
    {
      title: '📋 标准模板',
      text: '今天完成了XX功能的开发，进度80%。成果已提交到Git仓库 v1.2.3。目前卡点：等待产品确认交互细节。预计明天解决。',
    },
    {
      title: '🔧 研发模板',
      text: '完成了数据库索引优化，查询性能提升50%。提交版本: commit abc1234。无卡点，进度100%。验收人：张毅。',
    },
    {
      title: '📦 采购模板',
      text: '今天跟进了3家供应商的报价，A供应商最优。已下单PCB板50片，预计周三到货。卡点：B物料延迟1天，已通知生产部。',
    },
  ]

  return (
    <div className="space-y-6">
      {/* 页头 */}
      <div>
        <h1 className="text-2xl font-bold text-white">📝 提交日报</h1>
        <p className="text-gray-400 mt-1">
          用自然语言或语音描述今日工作，AI 自动解析为结构化报告
        </p>
      </div>

      {/* 快捷模板 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {templates.map((t, i) => (
          <button
            key={i}
            onClick={() => setRawText(t.text)}
            className="text-left p-3 rounded-lg border border-gray-700 bg-gray-800/50 hover:bg-gray-700/50 transition-colors"
          >
            <div className="text-sm font-medium text-gray-300">{t.title}</div>
            <div className="text-xs text-gray-500 mt-1 line-clamp-2">{t.text}</div>
          </button>
        ))}
      </div>

      {/* 输入区域 */}
      <div className="bg-gray-800/50 rounded-xl border border-gray-700 p-6">
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-medium text-gray-300">
            工作汇报内容
          </label>
          {/* 语音输入按钮 */}
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
            ) : (
              <>🎤 语音输入</>
            )}
          </button>
        </div>

        <textarea
          value={rawText}
          onChange={e => setRawText(e.target.value)}
          placeholder="像跟同事说话一样，描述今天做了什么、进展多少、有什么卡点… 也可以点击右上角🎤语音输入"
          rows={6}
          className="w-full bg-gray-900/50 border border-gray-600 rounded-lg p-4 text-gray-200 placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
        />

        <div className="flex items-center justify-between mt-4">
          <span className="text-xs text-gray-500">
            当前用户: {userName || '未登录'}
          </span>
          <button
            onClick={handleSubmit}
            disabled={submitting || !rawText.trim()}
            className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors flex items-center gap-2"
          >
            {submitting ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                AI 解析中...
              </>
            ) : '🚀 提交日报'}
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
            <h2 className="text-lg font-semibold text-white">AI 解析结果</h2>
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

          {/* AI 点评 */}
          <div className="bg-gray-900/50 rounded-lg p-4">
            <div className="text-sm text-gray-400 mb-1">💬 AI 点评</div>
            <div className="text-gray-200">{result.ai_comment}</div>
          </div>

          {/* 解析字段 */}
          {result.parsed_content && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {[
                { label: '📌 今日任务', value: result.parsed_content.tasks },
                { label: '✅ 验收标准', value: result.parsed_content.acceptance_criteria },
                { label: '📊 完成进度', value: `${result.parsed_content.progress}%` },
                { label: '🔧 所需支持', value: result.parsed_content.support_needed },
                { label: '🚧 核心卡点', value: result.parsed_content.blocker },
                { label: '💡 解决方案', value: result.parsed_content.next_step },
                { label: '📅 预计解决', value: result.parsed_content.eta },
                { label: '🔖 Git 版本', value: result.parsed_content.git_version },
              ].map((field, i) => (
                <div key={i} className="bg-gray-900/30 rounded-lg p-3">
                  <div className="text-xs text-gray-500">{field.label}</div>
                  <div className="text-sm text-gray-300 mt-1">
                    {field.value || <span className="text-gray-600">—</span>}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 管理预警 */}
          {result.management_alert && (
            <div className="bg-amber-900/30 border border-amber-700 rounded-lg p-4">
              <div className="text-sm text-amber-400 font-medium">⚠️ 管理预警</div>
              <div className="text-sm text-amber-300 mt-1">{result.management_alert}</div>
            </div>
          )}

          {/* Token 用量 */}
          <div className="text-xs text-gray-600 text-right">
            Token 消耗: prompt {result.tokens_used?.prompt} + completion {result.tokens_used?.completion}
          </div>
        </div>
      )}
    </div>
  )
}
