'use client'

import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import request from '@/api/request'
import {
  getMyActiveProjects,
  getPendingFollowUps,
  getTodayPlan,
  submitEveningBatch,
  submitMorningBatch,
  WORK_TAG_CHOICES,
  type EveningAdHocCardIn,
  type EveningReviewCardIn,
  type MorningPlanCardIn,
  type MyActiveProjectItem,
  type PendingFollowUpItem,
  type PlannedStatus,
  type WorkTag,
} from '@/api/reports'
import { getProjectsOverview } from '@/api/projects'
import { getProjectSprints, getSprintTasks } from '@/api/sprints'
import { useAuthStore } from '@/stores/use-auth-store'
import AttachmentsPanel from '@/components/attachments-panel'
import type { Attachment } from '@/api/attachments'

type ReportMode = 'plan' | 'review'
type InputStyle = 'zero-select' | 'form' | 'free'

type ProjectOption = {
  id: string
  name: string
  code: string
  health_status?: string
  is_temporary?: boolean
}
type TaskOption = { id: string; title: string; status: string; priority: string; story_points: number }
type TodayPlanItem = {
  id: string
  project_id: string | null
  project_name: string | null
  sprint_task_id: string | null
  sprint_task_title: string | null
  work_tags: string[]
  raw_input_text: string
  parsed_content?: Record<string, any> | null
  ai_score?: number | null
  created_at?: string | null
}

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

const statusLabels: Record<PlannedStatus, string> = {
  done: '已完成',
  partial: '部分完成',
  delayed: '延期',
  cancelled: '取消',
}

function getApiErrorMessage(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail
  if (Array.isArray(detail)) {
    const message = detail
      .map((d: any) => {
        if (typeof d === 'string') return d
        if (typeof d?.msg === 'string') return d.msg
        if (typeof d?.message === 'string') return d.message
        return ''
      })
      .filter(Boolean)
      .join(', ')
    return message || fallback
  }
  if (typeof detail === 'string') return detail
  if (detail) return JSON.stringify(detail)
  if (typeof err?.message === 'string') return err.message
  return fallback
}

export default function SubmitReportPage() {
  const { userName } = useAuthStore()
  const defaultMode: ReportMode = new Date().getHours() < 12 ? 'plan' : 'review'
  const [mode, setMode] = useState<ReportMode>(defaultMode)
  const [inputStyle, setInputStyle] = useState<InputStyle>('zero-select')
  const [formData, setFormData] = useState<Record<string, string>>({})
  const [freeText, setFreeText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const recognitionRef = useRef<any>(null)
  const [morningPlan, setMorningPlan] = useState<any>(null)
  const [planLoading, setPlanLoading] = useState(false)
  const [, setAttachments] = useState<Attachment[]>([])

  const [projects, setProjects] = useState<ProjectOption[]>([])
  const [tasks, setTasks] = useState<TaskOption[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string>('')
  const [selectedTaskId, setSelectedTaskId] = useState<string>('')
  const [tasksLoading, setTasksLoading] = useState(false)

  const [activeProjects, setActiveProjects] = useState<MyActiveProjectItem[]>([])
  const [pendingFollowUps, setPendingFollowUps] = useState<PendingFollowUpItem[]>([])
  const [zeroSelectLoading, setZeroSelectLoading] = useState(false)
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [cardTags, setCardTags] = useState<Record<string, WorkTag[]>>({})
  const [cardNotes, setCardNotes] = useState<Record<string, string>>({})
  const [adHocCards, setAdHocCards] = useState<MorningPlanCardIn[]>([])
  const [todayPlanItems, setTodayPlanItems] = useState<TodayPlanItem[]>([])
  const [reviewStatuses, setReviewStatuses] = useState<Record<string, PlannedStatus>>({})
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({})
  const [eveningExtras, setEveningExtras] = useState<EveningAdHocCardIn[]>([])
  const initialLoadRef = useRef(true)

  useEffect(() => {
    getProjectsOverview(false, null, true)
      .then((res: any) => {
        const items = Array.isArray(res) ? res : res?.items || res?.projects || []
        const mapped: ProjectOption[] = items.map((p: any) => ({
          id: p.project_id ?? p.id,
          name: p.name,
          code: p.code,
          health_status: p.health_status,
          is_temporary: !!p.is_temporary,
        }))
        mapped.sort((a, b) => {
          if (a.is_temporary !== b.is_temporary) return a.is_temporary ? -1 : 1
          return (a.code || '').localeCompare(b.code || '')
        })
        setProjects(mapped)
      })
      .catch(() => setProjects([]))
  }, [])

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
        setSelectedTaskId((prev) => (prev && mapped.some((t: TaskOption) => t.id === prev) ? prev : ''))
      } catch {
        setTasks([])
        setSelectedTaskId('')
      } finally {
        setTasksLoading(false)
      }
    })()
  }, [selectedProjectId])

  useEffect(() => {
    if (mode === 'review' && inputStyle !== 'zero-select') {
      setPlanLoading(true)
      getTodayPlan()
        .then((res: any) => {
          setMorningPlan(res.plan)
          if (res.plan?.project_id) {
            setSelectedProjectId(res.plan.project_id)
            if (res.plan.sprint_task_id) setSelectedTaskId(res.plan.sprint_task_id)
          }
        })
        .catch(() => setMorningPlan(null))
        .finally(() => setPlanLoading(false))
    } else {
      setMorningPlan(null)
    }
  }, [mode, inputStyle])

  useEffect(() => {
    if (inputStyle !== 'zero-select') return
    setZeroSelectLoading(true)
    Promise.all([getMyActiveProjects(), getPendingFollowUps(), getTodayPlan()])
      .then(([active, pending, today]: any[]) => {
        setActiveProjects(active.projects || [])
        setPendingFollowUps(pending.items || [])
        const items = (today?.items || []) as TodayPlanItem[]
        setTodayPlanItems(items)
        if (initialLoadRef.current) {
          if (items.length > 0 && mode === 'plan' && new Date().getHours() >= 12) {
            setMode('review')
          }
          initialLoadRef.current = false
        }
      })
      .catch((e) => {
        const message = getApiErrorMessage(e, '加载零选择数据失败')
        setError(message)
        toast.error(message)
      })
      .finally(() => setZeroSelectLoading(false))
  }, [inputStyle, mode])

  const selectedProject = projects.find((p) => p.id === selectedProjectId)
  const isTempProjectSelected = !!selectedProject?.is_temporary
  const fields = FORM_FIELDS[mode]

  const switchMode = (next: ReportMode) => {
    setMode(next)
    setFormData({})
    setFreeText('')
    setResult(null)
    setError('')
  }

  const updateField = (key: string, value: string) => {
    setFormData((prev) => ({ ...prev, [key]: value }))
    if (result) { setResult(null); setError('') }
  }

  const updateFreeText = (value: string) => {
    setFreeText(value)
    if (result) { setResult(null); setError('') }
  }

  const formToText = (): string => {
    const parts: string[] = []
    for (const field of fields) {
      const val = formData[field.key]?.trim()
      if (val) parts.push(`【${field.label.replace(/^.{2}\s/, '')}】${val}`)
    }
    return parts.join('\n')
  }

  const getRawText = (): string => inputStyle === 'form' ? formToText() : freeText

  const startVoiceInput = () => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SR) { setError('请使用 Chrome 浏览器以启用语音输入'); return }
    const recognition = new SR()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    recognitionRef.current = recognition
    let final = freeText
    recognition.onresult = (event: any) => {
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) final += event.results[i][0].transcript
        else interim += event.results[i][0].transcript
      }
      setFreeText(final + interim)
    }
    recognition.onerror = () => setIsRecording(false)
    recognition.onend = () => { setIsRecording(false); setFreeText(final) }
    recognition.start()
    setIsRecording(true)
    setError('')
  }

  const stopVoiceInput = () => {
    recognitionRef.current?.stop()
    setIsRecording(false)
  }

  const toggleKey = (key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleTag = (key: string, tag: WorkTag) => {
    setCardTags((prev) => {
      const current = prev[key] || []
      const next = current.includes(tag) ? current.filter((t) => t !== tag) : [...current, tag]
      return { ...prev, [key]: next }
    })
  }

  const submitLegacy = async () => {
    const text = getRawText()
    if (!text.trim()) { setError('请填写内容'); return }
    setSubmitting(true)
    setError('')
    setResult(null)
    try {
      const payload: Record<string, any> = {
        raw_text: `[${mode === 'plan' ? '晨规划' : '晚复核'}] ${text}`,
      }
      if (selectedProjectId) payload.project_id = selectedProjectId
      if (selectedTaskId) payload.sprint_task_id = selectedTaskId
      const res = await request.post('/reports/web-submit', payload)
      setResult(res)
    } catch (err: any) {
      setError(getApiErrorMessage(err, '提交失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const submitZeroSelectPlan = async () => {
    const items: MorningPlanCardIn[] = []
    for (const follow of pendingFollowUps) {
      const key = `supervised:${follow.supervised_id}`
      items.push({
        project_id: follow.project_id ?? undefined,
        sprint_task_id: follow.sprint_task_id ?? undefined,
        work_tags: cardTags[key] || [],
        note: `[督导持续跟进] ${(follow.source_note || '').slice(0, 100)}`,
      })
    }
    for (const project of activeProjects) {
      const projectKey = `project:${project.id}`
      if (project.tasks.length === 0 && selectedKeys.has(projectKey)) {
        items.push({
          project_id: project.id,
          work_tags: cardTags[projectKey] || [],
          note: cardNotes[projectKey] || '',
        })
      }
      for (const task of project.tasks) {
        const taskKey = `task:${task.id}`
        if (selectedKeys.has(taskKey)) {
          items.push({
            project_id: project.id,
            sprint_task_id: task.id,
            work_tags: cardTags[taskKey] || [],
            note: cardNotes[taskKey] || '',
          })
        }
      }
    }
    items.push(...adHocCards.filter((card) => (card.note || '').trim()))
    if (items.length === 0) {
      toast.error('请至少勾选一项任务或新增计划外任务')
      return
    }
    setSubmitting(true)
    try {
      const response = await submitMorningBatch({ items })
      toast.success(`已提交 ${response.inserted} 条晨规划`)
      setSelectedKeys(new Set())
      setCardTags({})
      setCardNotes({})
      setAdHocCards([])
      const today: any = await getTodayPlan()
      setTodayPlanItems(today?.items || [])
      setMode('review')
    } catch (err: any) {
      toast.error(getApiErrorMessage(err, '提交晨规划失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const submitZeroSelectReview = async () => {
    const reviews: EveningReviewCardIn[] = todayPlanItems
      .filter((item) => reviewStatuses[item.id])
      .map((item) => ({
        parent_report_id: item.id,
        planned_status: reviewStatuses[item.id],
        actual_note: reviewNotes[item.id] || undefined,
      }))
    const extras = eveningExtras.filter((card) => (card.note || '').trim())
    if (reviews.length === 0 && extras.length === 0) {
      toast.error('请至少对账一条或追加一条完成任务')
      return
    }
    setSubmitting(true)
    try {
      const response = await submitEveningBatch({ reviews, extras })
      toast.success(
        `已对账 ${response.review_count} 条 / 新增 ${response.extra_count} 条 / 督导 ${response.supervised_created} 条 / 自动闭环 ${response.supervised_closed} 条`
      )
      setReviewStatuses({})
      setReviewNotes({})
      setEveningExtras([])
      const pending = await getPendingFollowUps()
      setPendingFollowUps(pending.items)
    } catch (err: any) {
      toast.error(getApiErrorMessage(err, '提交晚复核失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleSubmit = async () => {
    if (inputStyle === 'zero-select') {
      if (mode === 'plan') return submitZeroSelectPlan()
      return submitZeroSelectReview()
    }
    return submitLegacy()
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4 flex-wrap">
        <button onClick={() => switchMode('plan')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-all ${mode === 'plan' ? 'bg-amber-600 text-white shadow-lg shadow-amber-600/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
          ☀️ 晨规划 {defaultMode === 'plan' && <span className="text-xs opacity-70">(当前)</span>}
        </button>
        <button onClick={() => switchMode('review')}
          className={`flex items-center gap-2 px-5 py-2.5 rounded-lg font-medium transition-all ${mode === 'review' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
          🌙 晚复核 {defaultMode === 'review' && <span className="text-xs opacity-70">(当前)</span>}
        </button>
        <div className="flex-1" />
        <div className="flex items-center bg-gray-800 rounded-lg p-0.5">
          {(['zero-select', 'form', 'free'] as InputStyle[]).map((style) => (
            <button key={style} onClick={() => setInputStyle(style)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${inputStyle === style ? 'bg-gray-600 text-white' : 'text-gray-400 hover:text-gray-300'}`}>
              {style === 'zero-select' ? '智能铺盘' : style === 'form' ? '结构化' : '自由输入'}
            </button>
          ))}
        </div>
        <span className="text-xs text-gray-500">
          {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}
        </span>
      </div>

      <div>
        <h1 className="text-2xl font-bold text-white">{mode === 'plan' ? '☀️ 晨规划' : '🌙 晚复核'}</h1>
        <p className="text-gray-400 mt-1">
          {inputStyle === 'zero-select'
            ? '零选择智能铺盘:直接勾选名下项目、任务与督导追踪项'
            : mode === 'plan'
              ? '规划今日工作目标、计划任务和预期交付物'
              : '汇报今日实际完成情况、代码提交、卡点和明日规划'}
        </p>
      </div>

      {inputStyle === 'zero-select' && (
        <ZeroSelectPanel
          mode={mode}
          loading={zeroSelectLoading}
          activeProjects={activeProjects}
          pendingFollowUps={pendingFollowUps}
          todayPlanItems={todayPlanItems}
          selectedKeys={selectedKeys}
          cardTags={cardTags}
          cardNotes={cardNotes}
          adHocCards={adHocCards}
          reviewStatuses={reviewStatuses}
          reviewNotes={reviewNotes}
          eveningExtras={eveningExtras}
          submitting={submitting}
          onToggleKey={toggleKey}
          onToggleTag={toggleTag}
          onNoteChange={(key, value) => setCardNotes((prev) => ({ ...prev, [key]: value }))}
          onAdHocChange={setAdHocCards}
          onReviewStatusChange={(id, value) => setReviewStatuses((prev) => ({ ...prev, [id]: value }))}
          onReviewNoteChange={(id, value) => setReviewNotes((prev) => ({ ...prev, [id]: value }))}
          onEveningExtrasChange={setEveningExtras}
          onSubmit={handleSubmit}
        />
      )}

      {mode === 'review' && inputStyle !== 'zero-select' && (
        <LegacyMorningPlanCard morningPlan={morningPlan} planLoading={planLoading} />
      )}

      {inputStyle !== 'zero-select' && (
        <LegacyProjectPicker
          projects={projects}
          tasks={tasks}
          selectedProjectId={selectedProjectId}
          selectedTaskId={selectedTaskId}
          tasksLoading={tasksLoading}
          isTempProjectSelected={isTempProjectSelected}
          onProjectChange={setSelectedProjectId}
          onTaskChange={setSelectedTaskId}
        />
      )}

      {inputStyle === 'form' && (
        <div className={`bg-gray-800/50 rounded-xl border p-6 space-y-4 ${mode === 'plan' ? 'border-amber-800/50' : 'border-indigo-800/50'}`}>
          {fields.map((field) => (
            <div key={field.key}>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-300 mb-1.5">
                {field.label}
                {field.required && <span className="text-red-400 text-xs">必填</span>}
                {!field.required && <span className="text-gray-600 text-xs">选填</span>}
              </label>
              {field.key === 'tasks' || field.key === 'goal' ? (
                <textarea value={formData[field.key] || ''} onChange={(e) => updateField(field.key, e.target.value)}
                  placeholder={field.placeholder} rows={2}
                  className={`w-full bg-gray-900/50 border rounded-lg p-3 text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 resize-none text-sm ${mode === 'plan' ? 'border-amber-900/30 focus:ring-amber-500' : 'border-indigo-900/30 focus:ring-indigo-500'}`} />
              ) : (
                <input type="text" value={formData[field.key] || ''} onChange={(e) => updateField(field.key, e.target.value)}
                  placeholder={field.placeholder}
                  className={`w-full bg-gray-900/50 border rounded-lg p-3 text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 text-sm ${mode === 'plan' ? 'border-amber-900/30 focus:ring-amber-500' : 'border-indigo-900/30 focus:ring-indigo-500'}`} />
              )}
            </div>
          ))}
          <AttachmentsPanel onChange={setAttachments} />
          <SubmitBar userName={userName} mode={mode} submitting={submitting} result={result} onSubmit={handleSubmit} />
        </div>
      )}

      {inputStyle === 'free' && (
        <div className={`bg-gray-800/50 rounded-xl border p-6 ${mode === 'plan' ? 'border-amber-800/50' : 'border-indigo-800/50'}`}>
          <div className="flex items-center justify-between mb-2">
            <label className="text-sm font-medium text-gray-300">自由描述</label>
            <button onClick={isRecording ? stopVoiceInput : startVoiceInput}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${isRecording ? 'bg-red-600 hover:bg-red-500 text-white animate-pulse' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'}`}>
              {isRecording ? '录音中… 点击停止' : '🎤 语音输入'}
            </button>
          </div>
          <textarea value={freeText} onChange={(e) => updateFreeText(e.target.value)}
            placeholder="像跟同事说话一样，描述今天的工作内容…也可以点击语音输入"
            rows={6}
            className={`w-full bg-gray-900/50 border rounded-lg p-4 text-gray-200 placeholder:text-gray-500 focus:outline-none focus:ring-2 resize-none ${mode === 'plan' ? 'border-amber-900/50 focus:ring-amber-500' : 'border-indigo-900/50 focus:ring-indigo-500'}`} />
          <div className="mt-4">
            <AttachmentsPanel
              onChange={setAttachments}
              onTranscribed={(text) => updateFreeText((freeText ? `${freeText} ` : '') + text)}
            />
          </div>
          <SubmitBar userName={userName} mode={mode} submitting={submitting} result={result} onSubmit={handleSubmit} disabled={!freeText.trim()} />
        </div>
      )}

      {error && <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-400">❌ {error}</div>}
      {result && !result.pass_check && <RejectedResult result={result} onRetry={() => { setResult(null); window.scrollTo({ top: 0, behavior: 'smooth' }) }} />}
      {result && result.pass_check && <PassedResult result={result} mode={mode} />}
    </div>
  )
}

function ZeroSelectPanel(props: {
  mode: ReportMode
  loading: boolean
  activeProjects: MyActiveProjectItem[]
  pendingFollowUps: PendingFollowUpItem[]
  todayPlanItems: TodayPlanItem[]
  selectedKeys: Set<string>
  cardTags: Record<string, WorkTag[]>
  cardNotes: Record<string, string>
  adHocCards: MorningPlanCardIn[]
  reviewStatuses: Record<string, PlannedStatus>
  reviewNotes: Record<string, string>
  eveningExtras: EveningAdHocCardIn[]
  submitting: boolean
  onToggleKey: (key: string) => void
  onToggleTag: (key: string, tag: WorkTag) => void
  onNoteChange: (key: string, value: string) => void
  onAdHocChange: (cards: MorningPlanCardIn[]) => void
  onReviewStatusChange: (id: string, value: PlannedStatus) => void
  onReviewNoteChange: (id: string, value: string) => void
  onEveningExtrasChange: (cards: EveningAdHocCardIn[]) => void
  onSubmit: () => void
}) {
  if (props.loading) return <div className="bg-gray-800/50 border border-gray-700 rounded-xl p-6 text-gray-400">加载零选择数据中…</div>
  return props.mode === 'plan' ? <MorningZeroSelect {...props} /> : <EveningZeroSelect {...props} />
}

function MorningZeroSelect(props: Parameters<typeof ZeroSelectPanel>[0]) {
  return (
    <div className="space-y-5">
      {props.pendingFollowUps.length > 0 && (
        <section className="bg-red-950/30 border border-red-700/60 rounded-xl p-5 space-y-3">
          <h2 className="text-red-300 font-semibold">督导追踪顶置</h2>
          {props.pendingFollowUps.map((item) => {
            const key = `supervised:${item.supervised_id}`
            return (
              <SelectableWorkCard key={key} cardKey={key} title={item.sprint_task_title || item.project_name || '督导事项'}
                subtitle={item.source_note || '待继续跟进'} checked locked tags={props.cardTags[key] || []}
                note={props.cardNotes[key] || ''} onToggle={() => undefined} onTagToggle={props.onToggleTag}
                onNoteChange={props.onNoteChange} />
            )
          })}
        </section>
      )}

      <section className="bg-gray-800/50 border border-gray-700 rounded-xl p-5 space-y-4">
        <h2 className="text-white font-semibold">我的活跃项目与任务</h2>
        {props.activeProjects.length === 0 && <div className="text-sm text-gray-500">暂无参与中的项目</div>}
        {props.activeProjects.map((project) => (
          <div key={project.id} className="border border-gray-700 rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-white font-medium">[{project.code}] {project.name}</div>
                <div className="text-xs text-gray-500">{project.member_track} · {project.role_in_project || '成员'}</div>
              </div>
              {project.is_temporary && <span className="text-xs text-purple-300 bg-purple-900/30 px-2 py-1 rounded">临时工单</span>}
            </div>
            {project.tasks.length === 0 ? (
              <SelectableWorkCard cardKey={`project:${project.id}`} title="项目级工作" subtitle="该项目当前无分配给你的进行中 Sprint 任务"
                checked={props.selectedKeys.has(`project:${project.id}`)} tags={props.cardTags[`project:${project.id}`] || []}
                note={props.cardNotes[`project:${project.id}`] || ''} onToggle={props.onToggleKey}
                onTagToggle={props.onToggleTag} onNoteChange={props.onNoteChange} />
            ) : project.tasks.map((task) => {
              const key = `task:${task.id}`
              return (
                <SelectableWorkCard key={key} cardKey={key} title={task.title}
                  subtitle={`${task.priority.toUpperCase()} · ${task.story_points}pt · ${task.status}`}
                  checked={props.selectedKeys.has(key)} tags={props.cardTags[key] || []} note={props.cardNotes[key] || ''}
                  onToggle={props.onToggleKey} onTagToggle={props.onToggleTag} onNoteChange={props.onNoteChange} />
              )
            })}
          </div>
        ))}
      </section>

      <AdHocEditor cards={props.adHocCards} onChange={props.onAdHocChange} />
      <ZeroSelectSubmit label="提交晨规划" submitting={props.submitting} onSubmit={props.onSubmit} />
    </div>
  )
}

function EveningZeroSelect(props: Parameters<typeof ZeroSelectPanel>[0]) {
  return (
    <div className="space-y-5">
      <section className="bg-gray-800/50 border border-gray-700 rounded-xl p-5 space-y-3">
        <h2 className="text-white font-semibold">晨规划对账</h2>
        {props.todayPlanItems.length === 0 && <div className="text-sm text-gray-500">今日暂无晨规划记录,可在下方追加自主完成项</div>}
        {props.todayPlanItems.map((item) => (
          <div key={item.id} className="border border-gray-700 rounded-lg p-4 space-y-3">
            <div>
              <div className="text-white font-medium">{item.sprint_task_title || item.project_name || '计划外任务'}</div>
              <div className="text-sm text-gray-400 mt-1">{item.raw_input_text}</div>
              {item.work_tags?.length > 0 && <div className="text-xs text-gray-500 mt-1">{item.work_tags.join(' / ')}</div>}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {(Object.keys(statusLabels) as PlannedStatus[]).map((status) => (
                <button key={status} onClick={() => props.onReviewStatusChange(item.id, status)}
                  className={`px-3 py-2 rounded-lg text-sm border ${props.reviewStatuses[item.id] === status ? 'bg-indigo-600 border-indigo-500 text-white' : 'bg-gray-900/50 border-gray-700 text-gray-400 hover:text-gray-200'}`}>
                  {statusLabels[status]}
                </button>
              ))}
            </div>
            <textarea value={props.reviewNotes[item.id] || ''} onChange={(e) => props.onReviewNoteChange(item.id, e.target.value)}
              placeholder="完成说明、延期原因或取消原因"
              rows={2}
              className="w-full bg-gray-900/50 border border-gray-700 rounded-lg p-3 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
          </div>
        ))}
      </section>

      <EveningExtrasEditor cards={props.eveningExtras} onChange={props.onEveningExtrasChange} />
      <ZeroSelectSubmit label="提交晚复核" submitting={props.submitting} onSubmit={props.onSubmit} />
    </div>
  )
}

function SelectableWorkCard(props: {
  cardKey: string
  title: string
  subtitle: string
  checked: boolean
  locked?: boolean
  tags: WorkTag[]
  note: string
  onToggle: (key: string) => void
  onTagToggle: (key: string, tag: WorkTag) => void
  onNoteChange: (key: string, value: string) => void
}) {
  return (
    <div className={`rounded-lg border p-4 space-y-3 ${props.checked ? 'border-amber-500/70 bg-amber-950/20' : 'border-gray-700 bg-gray-900/30'}`}>
      <label className="flex items-start gap-3">
        <input type="checkbox" checked={props.checked} disabled={props.locked} onChange={() => props.onToggle(props.cardKey)}
          className="mt-1 h-4 w-4 rounded border-gray-600 bg-gray-900" />
        <span className="min-w-0">
          <span className="block text-sm font-medium text-gray-100">{props.title}</span>
          <span className="block text-xs text-gray-500 mt-0.5">{props.subtitle}</span>
        </span>
      </label>
      <TagPicker cardKey={props.cardKey} selected={props.tags} onToggle={props.onTagToggle} />
      <textarea value={props.note} onChange={(e) => props.onNoteChange(props.cardKey, e.target.value)}
        placeholder="备注(选填)"
        rows={2}
        className="w-full bg-gray-950/50 border border-gray-700 rounded-lg p-2 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none" />
    </div>
  )
}

function TagPicker(props: { cardKey: string; selected: WorkTag[]; onToggle: (key: string, tag: WorkTag) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {WORK_TAG_CHOICES.map((tag) => (
        <button key={tag} type="button" onClick={() => props.onToggle(props.cardKey, tag)}
          className={`px-2.5 py-1 rounded-full text-xs border ${props.selected.includes(tag) ? 'bg-emerald-700 border-emerald-500 text-white' : 'bg-gray-900 border-gray-700 text-gray-400 hover:text-gray-200'}`}>
          {tag}
        </button>
      ))}
    </div>
  )
}

function AdHocEditor(props: { cards: MorningPlanCardIn[]; onChange: (cards: MorningPlanCardIn[]) => void }) {
  return (
    <section className="bg-gray-800/50 border border-gray-700 rounded-xl p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-white font-semibold">计划外补充</h2>
        <button onClick={() => props.onChange([...props.cards, { note: '', work_tags: [] }])}
          className="px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-200">+ 新增</button>
      </div>
      {props.cards.map((card, index) => (
        <div key={index} className="border border-gray-700 rounded-lg p-3 space-y-2">
          <textarea value={card.note || ''} onChange={(e) => {
            const next = [...props.cards]
            next[index] = { ...card, note: e.target.value }
            props.onChange(next)
          }} placeholder="计划外事项" rows={2}
            className="w-full bg-gray-900/50 border border-gray-700 rounded-lg p-3 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none" />
        </div>
      ))}
    </section>
  )
}

function EveningExtrasEditor(props: { cards: EveningAdHocCardIn[]; onChange: (cards: EveningAdHocCardIn[]) => void }) {
  return (
    <section className="bg-gray-800/50 border border-gray-700 rounded-xl p-5 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-white font-semibold">自主新增完成项</h2>
        <button onClick={() => props.onChange([...props.cards, { note: '', work_tags: [] }])}
          className="px-3 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-sm text-gray-200">+ 追加</button>
      </div>
      {props.cards.map((card, index) => (
        <textarea key={index} value={card.note} onChange={(e) => {
          const next = [...props.cards]
          next[index] = { ...card, note: e.target.value }
          props.onChange(next)
        }} placeholder="自主完成事项" rows={2}
          className="w-full bg-gray-900/50 border border-gray-700 rounded-lg p-3 text-sm text-gray-200 placeholder:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none" />
      ))}
    </section>
  )
}

function ZeroSelectSubmit(props: { label: string; submitting: boolean; onSubmit: () => void }) {
  return (
    <div className="flex justify-end">
      <button onClick={props.onSubmit} disabled={props.submitting}
        className="px-6 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:bg-gray-600 text-white font-medium">
        {props.submitting ? '提交中...' : props.label}
      </button>
    </div>
  )
}

function LegacyMorningPlanCard({ morningPlan, planLoading }: { morningPlan: any; planLoading: boolean }) {
  return (
    <div className="bg-amber-950/20 rounded-xl border border-amber-800/40 p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-amber-400 font-medium text-sm">📋 今日晨规划参考</span>
        {planLoading && <span className="text-xs text-gray-500 animate-pulse">加载中...</span>}
      </div>
      {!planLoading && !morningPlan && <div className="text-sm text-gray-500 py-2">今日暂无已通过的晨规划记录</div>}
      {morningPlan?.parsed_content && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {[
            { label: '🎯 计划任务', value: morningPlan.parsed_content.tasks },
            { label: '📊 进度预期', value: morningPlan.parsed_content.progress != null ? `${morningPlan.parsed_content.progress}%` : null },
            { label: '✅ 验收标准', value: morningPlan.parsed_content.acceptance_criteria },
            { label: '📦 预期交付', value: morningPlan.parsed_content.deliverable },
          ].filter((field) => field.value).map((field, index) => (
            <div key={index} className="bg-amber-900/20 rounded-lg p-3">
              <div className="text-xs text-amber-400/70">{field.label}</div>
              <div className="text-sm text-gray-300 mt-1">{field.value}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function LegacyProjectPicker(props: {
  projects: ProjectOption[]
  tasks: TaskOption[]
  selectedProjectId: string
  selectedTaskId: string
  tasksLoading: boolean
  isTempProjectSelected: boolean
  onProjectChange: (id: string) => void
  onTaskChange: (id: string) => void
}) {
  return (
    <div className="bg-slate-800/40 rounded-xl border border-slate-700/50 p-5">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-slate-300 font-medium text-sm">🔗 关联项目 / 任务</span>
        <span className="text-xs text-slate-500">(legacy 备用路径)</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <select value={props.selectedProjectId} onChange={(e) => props.onProjectChange(e.target.value)}
          className="w-full bg-gray-900/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-slate-500">
          <option value="">— 不挂钩项目 —</option>
          {props.projects.map((project) => (
            <option key={project.id} value={project.id}>[{project.code}] {project.name}</option>
          ))}
        </select>
        <select value={props.selectedTaskId} onChange={(e) => props.onTaskChange(e.target.value)}
          disabled={!props.selectedProjectId || props.tasksLoading || props.isTempProjectSelected}
          className="w-full bg-gray-900/60 border border-slate-700 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:ring-2 focus:ring-slate-500 disabled:opacity-40">
          <option value="">{props.tasksLoading ? '加载中...' : '— 仅挂钩项目,不指定任务 —'}</option>
          {!props.isTempProjectSelected && props.tasks.map((task) => (
            <option key={task.id} value={task.id}>[{task.priority.toUpperCase()}·{task.story_points}pt·{task.status}] {task.title}</option>
          ))}
        </select>
      </div>
    </div>
  )
}

function SubmitBar({ userName, mode, submitting, result, disabled, onSubmit }: {
  userName?: string | null
  mode: ReportMode
  submitting: boolean
  result: any
  disabled?: boolean
  onSubmit: () => void
}) {
  return (
    <div className="flex items-center justify-between pt-4">
      <span className="text-xs text-gray-500">当前用户: {userName || '未登录'}</span>
      <button onClick={onSubmit} disabled={submitting || disabled || result?.status === 'ok'}
        className={`px-6 py-2.5 text-white rounded-lg font-medium transition-colors disabled:cursor-not-allowed ${result?.status === 'ok' ? 'bg-emerald-700' : submitting ? 'bg-gray-600' : mode === 'plan' ? 'bg-amber-600 hover:bg-amber-500' : 'bg-indigo-600 hover:bg-indigo-500'}`}>
        {result?.status === 'ok' ? (mode === 'plan' ? '✅ 计划已提交' : '✅ 复核已提交') : submitting ? 'AI 分析中...' : mode === 'plan' ? '📋 提交计划' : '🚀 提交复核'}
      </button>
    </div>
  )
}

function RejectedResult({ result, onRetry }: { result: any; onRetry: () => void }) {
  return (
    <div className="bg-red-950/40 rounded-xl border-2 border-red-700 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-red-400">🚫 质检未通过 — 请修改后重新提交</h2>
        <span className="text-2xl font-bold text-red-400">{result.ai_score}分</span>
      </div>
      <div className="bg-red-900/30 rounded-lg p-4 border border-red-800">
        <div className="text-sm text-red-300 font-medium mb-1">❌ 驳回原因</div>
        <div className="text-red-200">{result.reject_reason}</div>
      </div>
      {result.suggested_guidance && <div className="text-gray-300 whitespace-pre-line text-sm">{result.suggested_guidance}</div>}
      <button onClick={onRetry} className="w-full py-3 bg-amber-600 hover:bg-amber-500 text-white rounded-lg font-medium transition-colors">
        ✏️ 修改内容后重新提交
      </button>
    </div>
  )
}

function PassedResult({ result, mode }: { result: any; mode: ReportMode }) {
  return (
    <div className="bg-gray-800/50 rounded-xl border-2 border-green-700 p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">{mode === 'plan' ? '📋 计划已提交' : '📊 复核已提交'}</h2>
        <span className="px-3 py-1 rounded-full text-sm font-medium bg-green-900/50 text-green-400 border border-green-700">
          ✅ 质检通过 · 已入库
        </span>
      </div>
      <div className="bg-gray-900/50 rounded-lg p-4">
        <div className="text-sm text-gray-400 mb-1">💬 AI 点评</div>
        <div className="text-gray-200">{result.ai_comment}</div>
      </div>
    </div>
  )
}
