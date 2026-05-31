/**
 * app/projects/page.tsx — 项目列表页
 *
 * 展示所有项目的健康矩阵卡片 + 新建项目入口 + 阶段过滤
 */
'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/use-auth-store'
import {
  getProjectsOverview, createProject, updateProject, archiveProject,
  batchSoftDeleteProjects,
  batchRestoreProjects,
} from '@/api/projects'
import {
  MAIN_TRACK_OPTIONS,
  TEMP_TRACK_OPTIONS,
  TRACK_LABELS,
  trackLabel,
} from '@/lib/project-track'
import { useListFilters, type FilterSpec } from '@/lib/hooks/use-list-filters'
import { useMultiSelect } from '@/lib/hooks/use-multi-select'
import FilterBar from '@/components/filter-bar'
import ListActionBar from '@/components/list-action-bar'
import { toast } from 'sonner'
import MemberPicker from '@/components/member-picker'
import MilestoneTemplateEditor from '@/components/milestone-template-editor'
import type { ProjectMemberInit } from '@/api/projects'
import { seedProjectMilestones, type MilestoneNodeIn } from '@/api/milestones'
import {
  FolderKanban, Plus, ArrowRight, RefreshCw, Search, Calendar, Wallet,
  MoreVertical, Pencil, PauseCircle, PlayCircle, Archive, ArchiveRestore,
  Ticket, Trash2,
} from 'lucide-react'


const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  active:    { label: '进行中', color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
  paused:    { label: '暂停中', color: '#eab308', bg: 'rgba(234,179,8,0.15)' },
  completed: { label: '已完成', color: '#3b82f6', bg: 'rgba(59,130,246,0.15)' },
  cancelled: { label: '已取消', color: '#9ca3af', bg: 'rgba(156,163,175,0.15)' },
}

// V2.4 Stage 1:项目列表筛选维度(track / status / current_stage)
// 健康度走三色统计条(L271+)单独点击;includeArchived/includeTemporary 是后端 query 参数
// 都不进 FilterBar
const PROJECT_FILTER_SPEC: FilterSpec[] = [
  {
    key: 'track',
    type: 'multi-select',
    label: '轨道',
    options: [
      { value: 'dual', label: TRACK_LABELS.dual },
      { value: 'software', label: TRACK_LABELS.software },
      { value: 'hardware', label: TRACK_LABELS.hardware },
      { value: 'support', label: TRACK_LABELS.support },
      { value: 'other', label: TRACK_LABELS.other },
    ],
  },
  {
    key: 'status',
    type: 'multi-select',
    label: '状态',
    options: [
      { value: 'active', label: '进行中' },
      { value: 'paused', label: '暂停中' },
      { value: 'completed', label: '已完成' },
      { value: 'cancelled', label: '已取消' },
    ],
  },
  {
    key: 'current_stage',
    type: 'multi-select',
    label: '阶段',
    options: [
      { value: '1', label: '阶段 1·概念立项' },
      { value: '2', label: '阶段 2·计划设计' },
      { value: '3', label: '阶段 3·开发执行' },
      { value: '4', label: '阶段 4·验证试产' },
      { value: '5', label: '阶段 5·发布收尾' },
    ],
  },
]

const formatDate = (d?: string | null) => {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
  } catch {
    return d
  }
}

const budgetColor = (pct: number | null | undefined) => {
  if (pct == null) return 'var(--color-text-secondary)'
  if (pct >= 90) return '#ef4444'
  if (pct >= 70) return '#eab308'
  return '#22c55e'
}

export default function ProjectsPage() {
  const router = useRouter()
  const { isAdmin } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [projects, setProjects] = useState<any[]>([])
  const [overview, setOverview] = useState<any>({})
  const [searchQuery, setSearchQuery] = useState('')
  const [includeArchived, setIncludeArchived] = useState(false)
  const [healthFilter, setHealthFilter] = useState<'green' | 'yellow' | 'red' | null>(null)

  // 新建项目弹窗
  const [showCreate, setShowCreate] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [projectForm, setProjectForm] = useState({
    name: '',
    code: '',
    description: '',
    track: 'dual',
    planned_launch_date: '',
    budget_total: 100000,
    is_temporary: false, // V2.3 临时工单项目
    members: [] as ProjectMemberInit[], // T-1105 新增
    seed_milestones: true,
    milestone_nodes: [] as MilestoneNodeIn[],
  })

  // 卡片右上角菜单(项目操作)
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null)

  // 编辑项目弹窗
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editForm, setEditForm] = useState({
    name: '',
    description: '',
    track: 'dual',
    planned_launch_date: '',
    budget_total: 0,
    is_temporary: false, // V2.3:决定 track select 显示主干 / 临时哪组
  })

  // 归档确认
  const [archiveTarget, setArchiveTarget] = useState<any>(null)
  const [archiving, setArchiving] = useState(false)

  // 菜单：点击外部关闭
  useEffect(() => {
    if (!menuOpenId) return
    const close = () => setMenuOpenId(null)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [menuOpenId])

  const healthColor = (s: string) =>
    ({ green: '#22c55e', yellow: '#eab308', red: '#ef4444' }[s] || '#4b5563')

  // 是否在列表中也展示临时工单项目(默认隐藏,避免污染红黄绿矩阵)
  const [includeTemporary, setIncludeTemporary] = useState(false)

  const fetchProjects = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getProjectsOverview(includeArchived, healthFilter, includeTemporary) as any
      setOverview(data)
      setProjects(data.projects || [])
    } finally {
      setLoading(false)
    }
  }, [includeArchived, healthFilter, includeTemporary])

  useEffect(() => { fetchProjects() }, [fetchProjects])

  async function handleCreateProject() {
    if (!projectForm.name) {
      toast.error('项目名称必填')
      return
    }
    if (!projectForm.planned_launch_date) {
      toast.error('项目截止时间必填')
      return
    }
    if (projectForm.seed_milestones) {
      if (projectForm.milestone_nodes.length === 0) {
        toast.error('里程碑模板尚未加载完成')
        return
      }
      const invalidNode = projectForm.milestone_nodes.some((node) => !node.title.trim() || node.initial_points < 0)
      if (invalidNode) {
        toast.error('里程碑节点名称必填,积分不可为负数')
        return
      }
    }
    setSubmitting(true)
    try {
      // 临时工单项目只传精简字段；项目截止时间仍为必填
      const payload: any = projectForm.is_temporary
        ? {
            name: projectForm.name,
            code: projectForm.code || undefined,
            description: projectForm.description || undefined,
            planned_launch_date: projectForm.planned_launch_date,
            is_temporary: true,
            track: projectForm.track, // 临时项目也允许选择轨道 (如日常支撑)
            seed_milestones: false,
            // T-1105:临时项目也支持立项指派成员
            ...(projectForm.members.length > 0 ? { members: projectForm.members } : {}),
          }
        : {
            // T-1105:主干项目 payload 展开,显式列出字段以便注入 members
            name: projectForm.name,
            code: projectForm.code || undefined,
            description: projectForm.description || undefined,
            track: projectForm.track,
            planned_launch_date: projectForm.planned_launch_date,
            budget_total: projectForm.budget_total,
            is_temporary: false,
            seed_milestones: false,
            ...(projectForm.members.length > 0 ? { members: projectForm.members } : {}),
          }
      const created = await createProject(payload) as any
      if (projectForm.seed_milestones && created?.project_id) {
        await seedProjectMilestones(created.project_id, {
          nodes: projectForm.milestone_nodes.map((node) => ({
            ...node,
            description: node.description || undefined,
            target_date: node.target_date || undefined,
          })),
        })
      }
      const membersHint = projectForm.members.length > 0 ? ` · 已指派 ${projectForm.members.length} 名成员` : ''
      const milestoneHint = projectForm.seed_milestones ? ` · 已种入 ${projectForm.milestone_nodes.length} 个节点` : ''
      toast.success(
        projectForm.is_temporary
          ? `🎫 临时工单项目 ${created?.code || projectForm.name} 创建成功${membersHint}${milestoneHint}`
          : `项目 ${created?.code || projectForm.code || projectForm.name} 立项成功${membersHint}${milestoneHint}`,
      )
      setShowCreate(false)
      setProjectForm({
        name: '',
        code: '',
        description: '',
        track: 'dual',
        planned_launch_date: '',
        budget_total: 100000,
        is_temporary: false,
        members: [],
        seed_milestones: true,
        milestone_nodes: [],
      })
      // 创建临时项目后,自动开启 includeTemporary 让用户能立即看到
      if (projectForm.is_temporary) setIncludeTemporary(true)
      fetchProjects()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '立项失败')
    } finally {
      setSubmitting(false)
    }
  }

  function openEditModal(p: any) {
    setEditingId(p.project_id)
    setEditForm({
      name: p.name || '',
      description: p.description || '',
      track: p.track || (p.is_temporary ? 'support' : 'dual'),
      planned_launch_date: p.planned_launch_date ? String(p.planned_launch_date).slice(0, 10) : '',
      budget_total: p.budget_total ? Number(p.budget_total) : 0,
      is_temporary: !!p.is_temporary,
    })
  }

  async function handleSaveEdit() {
    if (!editingId) return
    if (!editForm.name) {
      toast.error('项目名称必填')
      return
    }
    setSubmitting(true)
    try {
      const payload: any = {
        name: editForm.name,
        description: editForm.description || null,
        track: editForm.track,
      }
      if (editForm.planned_launch_date) payload.planned_launch_date = editForm.planned_launch_date
      if (editForm.budget_total > 0) payload.budget_total = editForm.budget_total
      await updateProject(editingId, payload)
      toast.success('项目已更新')
      setEditingId(null)
      fetchProjects()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '更新失败')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleToggleStatus(p: any) {
    const next = p.status === 'paused' ? 'active' : 'paused'
    const verb = next === 'paused' ? '暂停' : '恢复'
    try {
      await updateProject(p.project_id, { status: next })
      toast.success(`已${verb}项目「${p.name}」`)
      fetchProjects()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || `${verb}失败`)
    }
  }

  async function handleRestore(p: any) {
    try {
      await updateProject(p.project_id, { status: 'active' })
      toast.success(`已恢复项目「${p.name}」`, { description: '已切回"进行中"' })
      fetchProjects()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '恢复失败')
    }
  }

  async function handleArchive() {
    if (!archiveTarget) return
    setArchiving(true)
    try {
      await archiveProject(archiveTarget.project_id)
      toast.success(
        `已归档项目「${archiveTarget.name}」`,
        { description: '默认列表已隐藏;开启右上「显示已归档」可查看与恢复' },
      )
      setArchiveTarget(null)
      fetchProjects()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '归档失败')
    } finally {
      setArchiving(false)
    }
  }

  // V2.4 Stage 1:用统一筛选 Hook(URL 同步默认开,刷新不丢)
  // FilterBar 维度:track / status / current_stage;搜索 + 三色 + includeXxx 走独立路径
  const {
    filteredItems: filteredByBar,
    filters,
    setFilter,
    clearFilter,
    clearAll,
    activeCount,
  } = useListFilters(projects, PROJECT_FILTER_SPEC, { urlPrefix: 'proj_' })

  // 搜索框叠加在 FilterBar 之后过滤(不进 spec,因为是模糊匹配多字段)
  const filtered = useMemo(() => {
    return filteredByBar.filter((p) => {
      const q = searchQuery.toLowerCase()
      return !q || p.name?.toLowerCase().includes(q) || p.code?.toLowerCase().includes(q)
    })
  }, [filteredByBar, searchQuery])

  // V2.4 Stage 2:项目多选 + 严格分路批量操作(临时软删 / 主干归档)
  const {
    selectedIds: projSelectedIds,
    selectedCount: projSelectedCount,
    selectedItems: selectedProjects,
    isSelected: isProjSelected,
    toggle: toggleProj,
    clearAll: clearProjSelection,
  } = useMultiSelect(filtered, { idKey: 'project_id' as any })
  const [bulkActing, setBulkActing] = useState(false)

  // 按选中类型决定 ActionBar 按钮
  const allTempSelected = projSelectedCount > 0 && selectedProjects.every((p) => p.is_temporary)
  const allMainSelected = projSelectedCount > 0 && selectedProjects.every((p) => !p.is_temporary)

  async function handleBatchSoftDelete() {
    if (!allTempSelected) {
      toast.error('仅允许批量删除临时工单项目;选中里包含主干项目')
      return
    }
    if (!confirm(`确定软删除选中的 ${projSelectedCount} 个临时工单项目?\n(数据库标 deleted_at,挂在它下面的历史日报不受影响)`)) return
    setBulkActing(true)
    try {
      const ids = Array.from(projSelectedIds)
      const res: any = await batchSoftDeleteProjects(ids)
      const deletedIds: string[] = res?.deleted_ids ?? ids
      clearProjSelection()
      await fetchProjects()
      // V2.4 Stage 3 C3:toast 内 5 秒撤销(仅 admin 后端会接受恢复)
      toast.success(`已删除 ${deletedIds.length} 个临时项目`, {
        duration: 5000,
        action: {
          label: '撤销',
          onClick: async () => {
            try {
              const r: any = await batchRestoreProjects(deletedIds)
              await fetchProjects()
              toast.success(`已撤销恢复 ${r?.restored_count ?? deletedIds.length} 个`)
            } catch (e: any) {
              toast.error(e?.response?.data?.detail || '撤销失败(需 admin)')
            }
          },
        },
      })
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '批量删除失败')
    } finally {
      setBulkActing(false)
    }
  }

  async function handleBatchArchive() {
    if (!confirm(`确定归档选中的 ${projSelectedCount} 个项目?\n(status → cancelled,可在"显示已归档"中恢复)`)) return
    setBulkActing(true)
    let okCount = 0
    let failCount = 0
    try {
      for (const p of selectedProjects) {
        if (p.status === 'cancelled') continue
        try {
          await archiveProject(p.project_id)
          okCount++
        } catch {
          failCount++
        }
      }
      // V2.4 Stage 3 C3:批量归档撤销 — 复用 updateProject 把 status 改回 active
      const archivedIds = selectedProjects
        .filter((p) => p.status !== 'cancelled')
        .map((p) => p.project_id)
      if (okCount > 0) {
        toast.success(
          `已归档 ${okCount} 个项目${failCount > 0 ? `(${failCount} 个失败)` : ''}`,
          {
            duration: 5000,
            action: {
              label: '撤销',
              onClick: async () => {
                try {
                  await Promise.all(
                    archivedIds.map((id) => updateProject(id, { status: 'active' })),
                  )
                  await fetchProjects()
                  toast.success(`已撤销归档 ${archivedIds.length} 个`)
                } catch (e: any) {
                  toast.error(e?.response?.data?.detail || '撤销归档失败')
                }
              },
            },
          },
        )
      } else if (failCount > 0) {
        toast.error('批量归档全部失败')
      }
      clearProjSelection()
      await fetchProjects()
    } finally {
      setBulkActing(false)
    }
  }

  return (
    <div className="page-container">
      <div className="flex items-center justify-between mb-6 animate-in">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
            项目列表
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            全部项目 · 健康矩阵总览
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchProjects}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
            style={{ border: '1px solid var(--color-brand-blue)', color: 'var(--color-brand-blue)' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            刷新
          </button>
          {isAdmin && (
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white"
              style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
            >
              <Plus size={14} />
              新建项目
            </button>
          )}
        </div>
      </div>

      {/* 统计条(可点击过滤) */}
      <div className="flex gap-4 mb-6 animate-in" style={{ animationDelay: '0.1s' }}>
        <button
          onClick={() => setHealthFilter(null)}
          className="stat-card flex items-center gap-3 flex-1 cursor-pointer transition-all hover:scale-[1.02]"
          style={{
            borderColor: healthFilter == null ? '#3b82f6' : 'transparent',
            borderWidth: 2,
            borderStyle: 'solid',
            background: healthFilter == null ? 'rgba(59,130,246,0.08)' : undefined,
          }}
          title="显示全部健康度"
        >
          <FolderKanban size={20} color="#3b82f6" />
          <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>总计</span>
          <span className="text-lg font-bold" style={{ color: 'var(--color-text-primary)' }}>{overview.total ?? 0}</span>
        </button>
        {(['green', 'yellow', 'red'] as const).map((s) => {
          const active = healthFilter === s
          const count = overview[`${s}_count`] ?? 0
          const label = s === 'green' ? '健康' : s === 'yellow' ? '关注' : '严重'
          return (
            <button
              key={s}
              onClick={() => setHealthFilter(active ? null : s)}
              disabled={count === 0 && !active}
              className="stat-card flex items-center gap-2 flex-1 cursor-pointer transition-all hover:scale-[1.02] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
              style={{
                borderColor: active ? healthColor(s) : 'transparent',
                borderWidth: 2,
                borderStyle: 'solid',
                background: active ? `${healthColor(s)}1a` : undefined, // 1a = 10% alpha
              }}
              title={`仅看${label}(${s})项目`}
            >
              <div className="w-3 h-3 rounded-full" style={{ background: healthColor(s) }} />
              <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
              <span className="text-lg font-bold" style={{ color: healthColor(s) }}>
                {count}
              </span>
            </button>
          )
        })}
      </div>

      {/* 搜索 */}
      <div className="mb-4 animate-in" style={{ animationDelay: '0.15s' }}>
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-secondary)' }} />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索项目名称或编号..."
            className="w-full pl-10 pr-4 py-2.5 rounded-lg text-sm outline-none"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
          />
        </div>
      </div>

      {/* V2.4 Stage 1:统一筛选条(track / status / 阶段);搜索/三色/归档/临时走独立路径 */}
      {/* relative z-50 — 打破 animate-in 创建的层叠上下文,让 multi-select 下拉能盖住兄弟节点 */}
      <div className="relative z-50 animate-in" style={{ animationDelay: '0.18s' }}>
        <FilterBar
          spec={PROJECT_FILTER_SPEC}
          filters={filters}
          setFilter={setFilter}
          clearFilter={clearFilter}
          clearAll={clearAll}
          activeCount={activeCount}
        />
      </div>

      {/* 数据范围 toggle 行(包含 / 排除已归档与临时工单 — 驱动后端 query 参数) */}
      <div className="flex flex-wrap items-center gap-2 mb-5 animate-in" style={{ animationDelay: '0.2s' }}>
        <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          数据范围:共 {projects.length} 条 · 显示 {filtered.length} 条
        </span>
        {/* 显示临时工单项目开关 */}
        <button
          onClick={() => setIncludeTemporary((v) => !v)}
          className="ml-auto px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5"
          style={{
            background: includeTemporary ? 'rgba(168,85,247,0.18)' : 'var(--color-bg-card)',
            color: includeTemporary ? '#e9d5ff' : 'var(--color-text-secondary)',
            border: `1px solid ${includeTemporary ? '#a855f7' : 'var(--color-border-subtle)'}`,
          }}
          title="切换是否显示临时工单项目(V2.3):默认隐藏,避免污染红黄绿矩阵"
        >
          <Ticket size={13} />
          {includeTemporary ? '隐藏临时工单' : '显示临时工单'}
        </button>
        {/* 显示已归档开关 */}
        <button
          onClick={() => setIncludeArchived((v) => !v)}
          className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all flex items-center gap-1.5"
          style={{
            background: includeArchived ? 'rgba(156,163,175,0.2)' : 'var(--color-bg-card)',
            color: includeArchived ? '#e5e7eb' : 'var(--color-text-secondary)',
            border: `1px solid ${includeArchived ? '#9ca3af' : 'var(--color-border-subtle)'}`,
          }}
          title="切换是否显示已归档(已取消)与已完成的项目"
        >
          <ArchiveRestore size={13} />
          {includeArchived ? '隐藏已归档' : '显示已归档'}
        </button>
      </div>

      {/* V2.4 Stage 2:批量操作栏 — 按选中类型严格分路 */}
      <ListActionBar
        selectedCount={projSelectedCount}
        onClear={clearProjSelection}
        hint={
          allTempSelected
            ? '全部为临时工单 — 可批量软删'
            : allMainSelected
              ? '全部为主干项目 — 仅批量归档'
              : '混合选中 — 只能批量归档(临时项目也走归档,避免歧义)'
        }
      >
        {allTempSelected ? (
          <button
            onClick={handleBatchSoftDelete}
            disabled={bulkActing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium disabled:opacity-60"
            style={{ background: '#ef4444', color: '#fff' }}
          >
            <Trash2 size={13} />
            {bulkActing ? '处理中...' : '批量软删'}
          </button>
        ) : (
          <button
            onClick={handleBatchArchive}
            disabled={bulkActing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium disabled:opacity-60"
            style={{ background: '#9ca3af', color: '#fff' }}
          >
            <Archive size={13} />
            {bulkActing ? '处理中...' : '批量归档'}
          </button>
        )}
      </ListActionBar>

      {/* 项目卡片列表 */}
      <div className="grid grid-cols-1 gap-4">
        {filtered.length === 0 && (
          <div className="stat-card text-center py-10 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            {projects.length === 0 ? '暂无项目数据' : '无符合条件的项目'}
          </div>
        )}
        {filtered.map((p: any, i: number) => {
          const statusMeta = STATUS_META[p.status] || STATUS_META.active
          const isCancelled = p.status === 'cancelled'
          const isPaused = p.status === 'paused'
          return (
            <div
              key={p.project_id}
              className="stat-card cursor-pointer flex items-center gap-5 animate-in"
              style={{
                animationDelay: `${0.2 + i * 0.05}s`,
                opacity: isCancelled ? 0.55 : 1,
                position: 'relative',
                zIndex: menuOpenId === p.project_id ? 40 : 1,
                borderColor: isProjSelected(p.project_id) ? '#a855f7' : undefined,
                borderWidth: isProjSelected(p.project_id) ? 1 : undefined,
                borderStyle: isProjSelected(p.project_id) ? 'solid' : undefined,
              }}
              onClick={() => {
                if (menuOpenId === p.project_id) { setMenuOpenId(null); return }
                router.push(`/project/${p.project_id}`)
              }}
            >
              {/* V2.4 Stage 2:多选 checkbox(点击不冒泡到卡片导航) */}
              {isAdmin && (
                <input
                  type="checkbox"
                  checked={isProjSelected(p.project_id)}
                  onChange={() => toggleProj(p.project_id)}
                  onClick={(e) => e.stopPropagation()}
                  className="shrink-0 cursor-pointer"
                  title="选中该项目用于批量操作"
                />
              )}
              <div className="w-3 h-3 rounded-full shrink-0" style={{ background: healthColor(p.health_status) }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm" style={{ color: 'var(--color-text-primary)' }}>
                    {p.code} · {p.name}
                  </span>
                  {/* V2.3 临时工单项目徽章 */}
                  {p.is_temporary && (
                    <span
                      className="px-2 py-0.5 rounded text-[10px] font-medium shrink-0 flex items-center gap-1"
                      style={{ background: 'rgba(168,85,247,0.18)', color: '#e9d5ff' }}
                      title="临时工单项目:承载日常 bug、改价、临时维护类零散工单"
                    >
                      <Ticket size={10} />
                      临时工单
                    </span>
                  )}
                  {/* 状态徽章 */}
                  <span
                    className="px-2 py-0.5 rounded text-[10px] font-medium shrink-0"
                    style={{ background: statusMeta.bg, color: statusMeta.color }}
                  >
                    {statusMeta.label}
                  </span>
                </div>
                <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                  {p.is_temporary
                    ? `🎫 轻量项目 · ${trackLabel(p.track)} · 无 IPD 阶段`
                    : `第${p.current_stage}阶段「${p.stage_name}」 · ${trackLabel(p.track)}`}
                </div>
                {/* 第二行:计划交付 + 预算 */}
                <div className="flex items-center gap-4 mt-1.5 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  <span className="flex items-center gap-1">
                    <Calendar size={11} />
                    计划 {formatDate(p.planned_launch_date)}
                  </span>
                  <span className="flex items-center gap-1">
                    <Wallet size={11} />
                    预算
                    <span style={{ color: budgetColor(p.budget_usage_pct), fontWeight: 600 }}>
                      {p.budget_usage_pct != null ? `${p.budget_usage_pct}%` : '未设置'}
                    </span>
                  </span>
                </div>
              </div>
              {/* 进度环 */}
              <div className="text-center shrink-0">
                <div
                  className="w-11 h-11 rounded-full border-[3px] flex items-center justify-center text-xs font-bold"
                  style={{
                    borderColor: (p.progress_pct || 0) >= 80 ? '#22c55e' : (p.progress_pct || 0) >= 50 ? '#eab308' : '#ef4444',
                    color: 'var(--color-text-primary)',
                  }}
                >
                  {p.progress_pct || 0}%
                </div>
              </div>
              <div className="text-right shrink-0" style={{ minWidth: 70 }}>
                <div className="text-lg font-bold" style={{ color: healthColor(p.health_status) }}>{p.health_score}</div>
                <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  {p.days_to_deadline != null ? `${p.days_to_deadline}天` : '—'}
                </div>
              </div>
              {/* 操作菜单(仅 admin) */}
              {isAdmin ? (
                <div className="relative shrink-0" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      setMenuOpenId(menuOpenId === p.project_id ? null : p.project_id)
                    }}
                    className="w-8 h-8 flex items-center justify-center rounded-lg transition-all hover:scale-110"
                    style={{
                      background: menuOpenId === p.project_id ? 'var(--color-brand-blue)' : 'rgba(255,255,255,0.06)',
                      border: '1px solid var(--color-border-subtle)',
                    }}
                    title="项目操作(编辑 / 暂停 / 归档)"
                  >
                    <MoreVertical size={18} color={menuOpenId === p.project_id ? '#fff' : '#e5e7eb'} strokeWidth={2.5} />
                  </button>
                  {menuOpenId === p.project_id && (
                    <div
                      className="absolute right-0 top-9 z-20 min-w-[140px] rounded-lg py-1 shadow-xl"
                      style={{
                        background: 'var(--color-bg-card)',
                        border: '1px solid var(--color-border-subtle)',
                      }}
                    >
                      {isCancelled ? (
                        // 已归档:仅"恢复运行"
                        <button
                          onClick={() => { setMenuOpenId(null); handleRestore(p) }}
                          className="w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-white/5"
                          style={{ color: '#22c55e' }}
                        >
                          <ArchiveRestore size={13} /> 恢复运行
                        </button>
                      ) : (
                        <>
                          <button
                            onClick={() => { setMenuOpenId(null); openEditModal(p) }}
                            className="w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-white/5"
                            style={{ color: 'var(--color-text-primary)' }}
                          >
                            <Pencil size={13} /> 编辑
                          </button>
                          <button
                            onClick={() => { setMenuOpenId(null); handleToggleStatus(p) }}
                            disabled={p.status === 'completed'}
                            className="w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-white/5 disabled:opacity-40"
                            style={{ color: 'var(--color-text-primary)' }}
                          >
                            {isPaused ? <><PlayCircle size={13} /> 恢复</> : <><PauseCircle size={13} /> 暂停</>}
                          </button>
                          <div className="my-1 mx-2 h-px" style={{ background: 'var(--color-border-subtle)' }} />
                          <button
                            onClick={() => { setMenuOpenId(null); setArchiveTarget(p) }}
                            className="w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-red-500/10"
                            style={{ color: '#ef4444' }}
                          >
                            <Archive size={13} /> 归档
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <ArrowRight size={16} color="#4b5563" />
              )}
            </div>
          )
        })}
      </div>

      {/* 新建项目弹窗 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowCreate(false)}>
          <div
            className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl p-6"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold mb-5" style={{ color: 'var(--color-text-primary)' }}>新建项目</h2>
            <div className="space-y-4">
              {/* V2.3 临时工单项目复选框 */}
              <label
                className="flex items-start gap-2.5 p-3 rounded-lg cursor-pointer transition-colors"
                style={{
                  background: projectForm.is_temporary ? 'rgba(168,85,247,0.12)' : 'var(--color-bg-secondary)',
                  border: `1px solid ${projectForm.is_temporary ? '#a855f7' : 'var(--color-border-subtle)'}`,
                }}
              >
                <input
                  type="checkbox"
                  checked={projectForm.is_temporary}
                  onChange={(e) => {
                    const next = e.target.checked
                    // 联动:勾上时把 track 默认重置为 support(临时组首项);
                    // 取消时重置为 dual(主干组首项)
                    setProjectForm({
                      ...projectForm,
                      is_temporary: next,
                      track: next ? 'support' : 'dual',
                    })
                  }}
                  className="mt-0.5"
                />
                <div className="flex-1">
                  <div className="text-sm font-medium flex items-center gap-1.5" style={{ color: 'var(--color-text-primary)' }}>
                    <Ticket size={14} />
                    临时工单项目(轻量模式)
                  </div>
                  <div className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                    用于承载日常 bug、改价、临时维护类零散工单。<br />
                    跳过 IPD 5 阶段初始化,不进项目健康矩阵,自动生成 Backlog 占位。
                  </div>
                </div>
              </label>

              {[
                { label: '项目名称', key: 'name', placeholder: projectForm.is_temporary ? '例如:日常支撑与临时工单' : '例如:206样机研发及落地', type: 'text' },
                { label: '项目编号', key: 'code', placeholder: projectForm.is_temporary ? '留空则自动生成 (如 P2026-T01)' : '留空则自动生成 (如 P2026-001)', type: 'text' },
              ].map((f) => (
                <div key={f.key}>
                  <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>{f.label}</label>
                  <input
                    type={f.type}
                    value={(projectForm as any)[f.key]}
                    onChange={(e) => setProjectForm({ ...projectForm, [f.key]: e.target.value })}
                    placeholder={f.placeholder}
                    className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                    style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                  />
                </div>
              ))}
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>项目描述 / 任务简述</label>
                <textarea
                  value={projectForm.description}
                  onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })}
                  rows={2}
                  placeholder={projectForm.is_temporary ? '简要描述该临时工单的任务内容...' : '输入项目背景或描述...'}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none resize-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                />
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>轨道</label>
                <select
                  value={projectForm.track}
                  onChange={(e) => setProjectForm({ ...projectForm, track: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                >
                  {(projectForm.is_temporary ? TEMP_TRACK_OPTIONS : MAIN_TRACK_OPTIONS).map((t) => (
                    <option key={t} value={t}>
                      {TRACK_LABELS[t]}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>项目截止时间 *</label>
                <input
                  type="date"
                  required
                  value={projectForm.planned_launch_date}
                  min={new Date().toISOString().split('T')[0]}
                  onChange={(e) => setProjectForm({ ...projectForm, planned_launch_date: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                />
              </div>
              {/* 临时项目只隐藏预算 */}
              {!projectForm.is_temporary && (
                <>
                  <div>
                    <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>预算总额(元)</label>
                    <input
                      type="number"
                      value={projectForm.budget_total}
                      onChange={(e) => setProjectForm({ ...projectForm, budget_total: Number(e.target.value) || 0 })}
                      className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                      style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                    />
                  </div>
                </>
              )}
              {/* T-1105 立项指派成员选择器(可选,主干 + 临时项目共享) */}
              <MemberPicker
                value={projectForm.members}
                onChange={(next) => setProjectForm({ ...projectForm, members: next })}
              />
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                  <input
                    type="checkbox"
                    checked={projectForm.seed_milestones}
                    onChange={(e) => setProjectForm({ ...projectForm, seed_milestones: e.target.checked })}
                  />
                  立项时种入贡献节点
                </label>
                {projectForm.seed_milestones && (
                  <MilestoneTemplateEditor
                    track={projectForm.track}
                    isTemporary={projectForm.is_temporary}
                    value={projectForm.milestone_nodes}
                    onChange={(nodes) => setProjectForm((current) => ({ ...current, milestone_nodes: nodes }))}
                    disabled={submitting}
                  />
                )}
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded-lg text-sm"
                style={{ color: 'var(--color-text-secondary)', border: '1px solid var(--color-border-subtle)' }}
              >
                取消
              </button>
              <button
                onClick={handleCreateProject}
                disabled={submitting}
                className="px-4 py-2 rounded-lg text-sm text-white font-medium disabled:opacity-60"
                style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
              >
                {submitting ? '提交中...' : '立项'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 编辑项目弹窗 */}
      {editingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setEditingId(null)}>
          <div
            className="w-full max-w-md rounded-2xl p-6"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold mb-5" style={{ color: 'var(--color-text-primary)' }}>编辑项目</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>项目名称</label>
                <input
                  type="text"
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                />
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>项目描述</label>
                <textarea
                  value={editForm.description}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  rows={2}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none resize-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                />
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>轨道</label>
                <select
                  value={editForm.track}
                  onChange={(e) => setEditForm({ ...editForm, track: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                >
                  {(editForm.is_temporary ? TEMP_TRACK_OPTIONS : MAIN_TRACK_OPTIONS).map((t) => (
                    <option key={t} value={t}>
                      {TRACK_LABELS[t]}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>计划交付</label>
                <input
                  type="date"
                  value={editForm.planned_launch_date}
                  min={new Date().toISOString().split('T')[0]}
                  onChange={(e) => setEditForm({ ...editForm, planned_launch_date: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                />
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>预算总额(元)</label>
                <input
                  type="number"
                  value={editForm.budget_total}
                  onChange={(e) => setEditForm({ ...editForm, budget_total: Number(e.target.value) || 0 })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                />
              </div>
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setEditingId(null)}
                className="px-4 py-2 rounded-lg text-sm"
                style={{ color: 'var(--color-text-secondary)', border: '1px solid var(--color-border-subtle)' }}
              >
                取消
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={submitting}
                className="px-4 py-2 rounded-lg text-sm text-white font-medium disabled:opacity-60"
                style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
              >
                {submitting ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 归档确认 */}
      {archiveTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => !archiving && setArchiveTarget(null)}>
          <div
            className="w-full max-w-sm rounded-2xl p-6"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 mb-3">
              <div
                className="w-10 h-10 rounded-full flex items-center justify-center"
                style={{ background: 'rgba(239,68,68,0.15)' }}
              >
                <Archive size={20} color="#ef4444" />
              </div>
              <h2 className="text-base font-semibold" style={{ color: 'var(--color-text-primary)' }}>确认归档项目?</h2>
            </div>
            <p className="text-sm mb-2" style={{ color: 'var(--color-text-secondary)' }}>
              即将归档:<span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{archiveTarget.code} · {archiveTarget.name}</span>
            </p>
            <p className="text-xs mb-5" style={{ color: 'var(--color-text-secondary)' }}>
              归档后项目状态变为「已取消」,所有历史数据(阶段、成员、日报关联)保留。如需恢复请联系管理员。
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setArchiveTarget(null)}
                disabled={archiving}
                className="px-4 py-2 rounded-lg text-sm disabled:opacity-60"
                style={{ color: 'var(--color-text-secondary)', border: '1px solid var(--color-border-subtle)' }}
              >
                取消
              </button>
              <button
                onClick={handleArchive}
                disabled={archiving}
                className="px-4 py-2 rounded-lg text-sm text-white font-medium disabled:opacity-60"
                style={{ background: '#ef4444' }}
              >
                {archiving ? '归档中...' : '确认归档'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
