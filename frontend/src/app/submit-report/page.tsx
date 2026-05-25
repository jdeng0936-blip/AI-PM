'use client'

import { useState, useRef, useEffect } from 'react'
import request from '@/api/request'
import { getTodayPlan } from '@/api/reports'
import { getProjectsOverview } from '@/api/projects'
import { getProjectSprints, getSprintTasks } from '@/api/sprints'
import { useAuthStore } from '@/stores/use-auth-store'
import AttachmentsPanel from '@/components/attachments-panel'
import type { Attachment } from '@/api/attachments'

type ReportMode = 'plan' | 'review'
type InputStyle = 'form' | 'free'

// V2.2 — 结构化关联:项目 + Sprint 任务下拉数据形态
// V2.3 — 增加 is_temporary 标识,临时工单项目下拉置顶 + chip
type ProjectOption = {
  id: string
  name: string
  code: string
  health_status?: string
  is_temporary?: boolean
}
type TaskOption = { id: string; title: string; status: string; priority: string; story_points: number }

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
  const [morningPlan, setMorningPlan] = useState<any>(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [attachments, setAttachments] = useState<Attachment[]>([])

  // ─── V2.2 结构化关联:项目 + Sprint 任务联动选择器 ───────────
  const [projects, setProjects] = useState<ProjectOption[]>([])
  const [tasks, setTasks] = useState<TaskOption[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string>('')
  const [selectedTaskId, setSelectedTaskId] = useState<string>('')
  const [tasksLoading, setTasksLoading] = useState(false)

  // 进入页面拉项目列表(含临时工单项目,V2.3)
  useEffect(() => {
    getProjectsOverview(false, null, true) // includeTemporary=true
      .then((res: any) => {
        const items = Array.isArray(res) ? res : res?.items || res?.projects || []
        const mapped: ProjectOption[] = items.map((p: any) => ({
          // 后端返回的是 project_id;兼容 id 字段以防其它接口形态
          id: p.project_id ?? p.id,
          name: p.name,
          code: p.code,
          health_status: p.health_status,
          is_temporary: !!p.is_temporary,
        }))
        // V2.3:临时工单项目置顶,便于员工快速选择
        mapped.sort((a, b) => {
          if (a.is_temporary !== b.is_temporary) return a.is_temporary ? -1 : 1
          return (a.code || '').localeCompare(b.code || '')
        })
        setProjects(mapped)
      })
      .catch(() => setProjects([]))
  }, [])

  // 派生:当前选中的是否为临时工单项目
  const selectedProject = projects.find((p) => p.id === selectedProjectId)
  const isTempProjectSelected = !!selectedProject?.is_temporary

  // 项目变化 → 联动加载该项目当前 active Sprint 的 task 列表
  useEffect(() => {
    if (!selectedProjectId) {
      setTasks([])
      setSelectedTaskId('')
      return
    }
    setTasksLoading(true)
    ;(async () => {
      try {
        const sprintsRes: any = await getProjectSprints(selectedProjectId)
        const sprints = Array.isArray(sprintsRes) ? sprintsRes : sprintsRes?.items || []
        const active = sprints.find((s: any) => s.status === 'active') || sprints[0]
        if (!active) {
          setTasks([])
          setSelectedTaskId('')
          return
        }
        const taskList: any = await getSprintTasks(active.id)
        const arr = Array.isArray(taskList) ? taskList : taskList?.items || []
        const mapped = arr.map((t: any) => ({
          id: t.id,
          title: t.title,
          status: t.status,
          priority: t.priority,
          story_points: t.story_points || 0,
        }))
        setTasks(mapped)
        // 若当前选中的 task 不在新列表里,清空(支持晨规划继承场景)
        setSelectedTaskId((prev) => (prev && mapped.some((t: TaskOption) => t.id === prev) ? prev : ''))
      } catch {
        setTasks([])
        setSelectedTaskId('')
      } finally {
        setTasksLoading(false)
      }
    })()
  }, [selectedProjectId])

  // ─── 晚复核模式自动拉取今日晨规划 ─────────────────
  useEffect(() => {
    if (mode === 'review') {
      setPlanLoading(true)
      getTodayPlan()
        .then((res: any) => {
          setMorningPlan(res.plan)
          // V2.2:晚复核默认继承晨规划的项目/任务关联
          if (res.plan?.project_id) {
            setSelectedProjectId(res.plan.project_id)
            if (res.plan.sprint_task_id) {
              // 等 tasks 加载完会自动可选;这里先记下,联动 effect 不会覆盖
              setSelectedTaskId(res.plan.sprint_task_id)
            }
          }
        })
        .catch(() => setMorningPlan(null))
        .finally(() => setPlanLoading(false))
    } else {
      setMorningPlan(null)
    }
  }, [mode])

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

  // ─── 表单字段变更时自动重置提交状态 ──────────────────
  const updateField = (key: string, value: string) => {
    setFormData(prev => ({ ...prev, [key]: value }))
    if (result) { setResult(null); setError('') }
  }
  const updateFreeText = (value: string) => {
    setFreeText(value)
    if (result) { setResult(null); setError('') }
  }

  // ─── 提交 ──────────────────────────────────────────
  const handleSubmit = async () => {
    const text = getRawText()
    if (!text.trim()) { setError('请填写内容'); return }
    setSubmitting(true); setError(''); setResult(null)
    try {
      // V2.2:把 project_id + sprint_task_id 一并发给后端
      const payload: Record<string, any> = {
        raw_text: `[${mode === 'plan' ? '晨规划' : '晚复核'}] ${text}`,
      }
      if (selectedProjectId) payload.project_id = selectedProjectId
      if (selectedTaskId) payload.sprint_task_id = selectedTaskId
      const res = await request.post('/simulate/web-submit', payload)
      setResult(res)
    } catch (err: any) {
      const status = err.response?.status
      const detail = err.response?.data?.detail
      if (status === 409) {
        setError(detail || '该内容今天已经提交过，请勿重复提交')
      } else {
        setError(detail || '提交失败')
      }
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
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-all ${mode === 'plan' ? 'bg-amber-600 text-white shadow-lg shadow-amber-600/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}>
          ☀️ 晨规划 {defaultMode === 'plan' && <span className="text-xs opacity-70">(当前)</span>}
        </button>
        <button onClick={() => switchMode('review')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-all ${mode === 'review' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}>
          🌙 晚复核 {defaultMode === 'review' && <span className="text-xs opacity-70">(当前)</span>}
        </button>
        <div className="flex-1" />

        {/* 输入方式切换 */}
        <div className="flex items-center bg-gray-800 rounded-lg p-0.5">
          <button onClick={() => setInputStyle('form')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${inputStyle === 'form' ? 'bg-gray-600 text-white' : 'text-gray-400 hover:text-gray-300'
              }`}>
            📋 结构化填写
          </button>
          <button onClick={() => setInputStyle('free')}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${inputStyle === 'free' ? 'bg-gray-600 text-white' : 'text-gray-400 hover:text-gray-300'
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

      {/* ═══ 晨规划参考卡片（晚复核模式下显示） ═══ */}
      {mode === 'review' && (
        <div className="bg-amber-950/20 rounded-xl border border-amber-800/40 p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-amber-400 font-medium text-sm">📋 今日晨规划参考</span>
            {planLoading && <span className="text-xs text-gray-500 animate-pulse">加载中...</span>}
          </div>
          {!planLoading && !morningPlan && (
            <div className="text-sm text-gray-500 py-2">今日暂无已通过的晨规划记录</div>
          )}
          {morningPlan && morningPlan.parsed_content && (
            <div className="space-y-2">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {[
                  { label: '🎯 计划任务', value: morningPlan.parsed_content.tasks },
                  { label: '📊 进度预期', value: morningPlan.parsed_content.progress != null ? `${morningPlan.parsed_content.progress}%` : null },
                  { label: '✅ 验收标准', value: morningPlan.parsed_content.acceptance_criteria },
                  { label: '📦 预期交付', value: morningPlan.parsed_content.deliverable },
                  { label: '🔧 所需支持', value: morningPlan.parsed_content.support_needed },
                ].filter(f => f.value).map((field, i) => (
                  <div key={i} className="bg-amber-900/20 rounded-lg p-3">
                    <div className="text-xs text-amber-400/70">{field.label}</div>
                    <div className="text-sm text-gray-300 mt-1">{field.value}</div>
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between pt-1">
                <span className="text-xs text-gray-600">
                  提交于 {morningPlan.created_at ? new Date(morningPlan.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '-'}
                </span>
                <span className="text-xs text-amber-400/60">AI 评分: {morningPlan.ai_score ?? '-'}</span>
              </div>
            </div>
          )}
        </div>
      )}


      {/* ═══ V2.2 关联项目 + 任务选择器(可选)═══ */}
      <div className="bg-slate-800/40 rounded-xl border border-slate-700/50 p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-slate-300 font-medium text-sm">🔗 关联项目 / 任务</span>
          <span className="text-xs text-slate-500">(可选 — 关联到项目和任务后,本日报会自动挂到 OKR KR)</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {/* 项目下拉 */}
          <div>
            <label className="text-xs text-slate-400 block mb-1">📁 项目</label>
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="w-full bg-gray-900/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-slate-500"
            >
              <option value="">— 不挂钩项目 —</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.is_temporary ? '🎫 ' : ''}[{p.code}] {p.name}
                  {p.is_temporary
                    ? ' · 临时工单'
                    : p.health_status === 'yellow'
                      ? ' ⚠️'
                      : p.health_status === 'red'
                        ? ' 🔴'
                        : ''}
                </option>
              ))}
            </select>
            {isTempProjectSelected && (
              <div className="mt-1.5 text-[11px] text-purple-300/80">
                🎫 已选临时工单项目,本日报将自动归入「Backlog 池」,无须挂具体任务
              </div>
            )}
          </div>
          {/* 任务下拉(联动) */}
          <div>
            <label className="text-xs text-slate-400 block mb-1">
              📋 Sprint 任务{' '}
              {tasksLoading && <span className="text-slate-600 animate-pulse">加载中…</span>}
            </label>
            <select
              value={selectedTaskId}
              onChange={(e) => setSelectedTaskId(e.target.value)}
              disabled={!selectedProjectId || tasksLoading || isTempProjectSelected}
              className="w-full bg-gray-900/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-slate-500 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <option value="">
                {!selectedProjectId
                  ? '请先选项目'
                  : isTempProjectSelected
                    ? '— 临时工单无须选任务 —'
                    : tasks.length
                      ? '— 仅挂钩项目,不指定任务 —'
                      : '该项目当前无 active Sprint'}
              </option>
              {!isTempProjectSelected &&
                tasks.map((t) => (
                  <option key={t.id} value={t.id}>
                    [{t.priority.toUpperCase()}·{t.story_points}pt·{t.status}] {t.title}
                  </option>
                ))}
            </select>
          </div>
        </div>
      </div>

      {/* ═══ 结构化表单 ═══ */}
      {inputStyle === 'form' && (
        <div className={`bg-gray-800/50 rounded-xl border p-6 space-y-4 ${mode === 'plan' ? 'border-amber-800/50' : 'border-indigo-800/50'
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
                  onChange={e => updateField(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  rows={2}
                  className={`w-full bg-gray-900/50 border rounded-lg p-3 text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 resize-none text-sm ${mode === 'plan' ? 'border-amber-900/30 focus:ring-amber-500' : 'border-indigo-900/30 focus:ring-indigo-500'
                    }`}
                />
              ) : (
                <input
                  type="text"
                  value={formData[f.key] || ''}
                  onChange={e => updateField(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  className={`w-full bg-gray-900/50 border rounded-lg p-3 text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 text-sm ${mode === 'plan' ? 'border-amber-900/30 focus:ring-amber-500' : 'border-indigo-900/30 focus:ring-indigo-500'
                    }`}
                />
              )}
            </div>
          ))}

          {/* 附件上传(仓管拍照/采购合同/语音备注) */}
          <AttachmentsPanel onChange={setAttachments} />

          <div className="flex items-center justify-between pt-2">
            <span className="text-xs text-gray-500">当前用户: {userName || '未登录'}</span>
            <button onClick={handleSubmit} disabled={submitting || result?.status === 'ok'}
              className={`px-6 py-2.5 text-white rounded-lg font-medium transition-colors flex items-center gap-2 disabled:cursor-not-allowed ${result?.status === 'ok' ? 'bg-emerald-700' : submitting ? 'bg-gray-600' : mode === 'plan' ? 'bg-amber-600 hover:bg-amber-500' : 'bg-indigo-600 hover:bg-indigo-500'
                }`}>
              {result?.status === 'ok' ? (
                <>{mode === 'plan' ? '✅ 计划已提交' : '✅ 复核已提交'}</>
              ) : submitting ? (
                <><svg className="animate-spin h-4 w-4" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> AI 分析中...</>
              ) : mode === 'plan' ? '📋 提交计划' : '🚀 提交复核'}
            </button>
          </div>
        </div>
      )}

      {/* ═══ 自由文本输入 ═══ */}
      {inputStyle === 'free' && (
        <div className={`bg-gray-800/50 rounded-xl border p-6 ${mode === 'plan' ? 'border-amber-800/50' : 'border-indigo-800/50'
          }`}>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-gray-300">自由描述</label>
            <button onClick={isRecording ? stopVoiceInput : startVoiceInput}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${isRecording ? 'bg-red-600 hover:bg-red-500 text-white animate-pulse' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                }`}>
              {isRecording ? (
                <><span className="relative flex h-2.5 w-2.5"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-300 opacity-75"></span><span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-400"></span></span>录音中… 点击停止</>
              ) : '🎤 语音输入'}
            </button>
          </div>
          <textarea value={freeText} onChange={e => updateFreeText(e.target.value)}
            placeholder="像跟同事说话一样，描述今天的工作内容…也可以点击🎤语音输入"
            rows={6}
            className={`w-full bg-gray-900/50 border rounded-lg p-4 text-gray-200 placeholder:text-gray-500 focus:outline-none focus:ring-2 resize-none ${mode === 'plan' ? 'border-amber-900/50 focus:ring-amber-500' : 'border-indigo-900/50 focus:ring-indigo-500'
              }`}
          />
          {/* 附件 & 服务端 ASR(浏览器原生 SpeechRecognition 之外的补充选项) */}
          <div className="mt-4">
            <AttachmentsPanel
              onChange={setAttachments}
              onTranscribed={(text) => updateFreeText((freeText ? freeText + ' ' : '') + text)}
            />
          </div>
          <div className="flex items-center justify-between mt-4">
            <span className="text-xs text-gray-500">当前用户: {userName || '未登录'}</span>
            <button onClick={handleSubmit} disabled={submitting || !freeText.trim() || result?.status === 'ok'}
              className={`px-6 py-2.5 text-white rounded-lg font-medium transition-colors flex items-center gap-2 disabled:cursor-not-allowed ${result?.status === 'ok' ? 'bg-emerald-700' : submitting ? 'bg-gray-600' : mode === 'plan' ? 'bg-amber-600 hover:bg-amber-500' : 'bg-indigo-600 hover:bg-indigo-500'
                }`}>
              {result?.status === 'ok' ? (mode === 'plan' ? '✅ 计划已提交' : '✅ 复核已提交') :
                submitting ? 'AI 分析中...' : mode === 'plan' ? '📋 提交计划' : '🚀 提交复核'}
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
