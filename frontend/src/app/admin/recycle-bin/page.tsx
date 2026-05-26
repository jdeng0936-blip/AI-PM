/**
 * frontend/src/app/admin/recycle-bin/page.tsx — 回收站(仅 admin)
 *
 * V2.4 Stage 3 C4:展示已软删的日报与临时项目,只支持"恢复",不暴露
 * 永久删除(spec §2.1 Q1 决策 — 保护历史数据完整性)。
 *
 * 数据源:
 *  - 日报: GET /api/v1/reports?include_deleted=true (仅 admin)
 *  - 项目: GET /api/v1/projects/deleted (仅 admin,临时项目 only)
 *
 * 权限双层:
 *  - 客户端:useEffect 检查 isAdmin,非 admin 跳转 / + toast.error
 *  - 服务端:include_deleted=true 对非 admin 强制 fallback,/deleted 端点 require_role(admin)
 */
'use client'

import { useEffect, useState, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Trash2 } from 'lucide-react'
import { useAuthStore } from '@/stores/use-auth-store'
import { useMultiSelect } from '@/lib/hooks/use-multi-select'
import ListActionBar from '@/components/list-action-bar'
import { getReports, batchRestoreReports } from '@/api/reports'
import { getDeletedProjects, batchRestoreProjects } from '@/api/projects'
import { getDeletedTasks, batchRestoreTasks, type DeletedSprintTask } from '@/api/sprint-tracking'

type Tab = 'reports' | 'projects' | 'sprint-tasks'

export default function RecycleBinPage() {
  const router = useRouter()
  const { isAdmin } = useAuthStore()
  const [tab, setTab] = useState<Tab>('reports')
  const [reports, setReports] = useState<any[]>([])
  const [projects, setProjects] = useState<any[]>([])
  const [tasks, setTasks] = useState<DeletedSprintTask[]>([])
  const [loading, setLoading] = useState(false)

  // 权限保护
  useEffect(() => {
    if (!isAdmin) {
      toast.error('需 admin 权限')
      router.replace('/')
    }
  }, [isAdmin, router])

  const loadReports = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await getReports({ include_deleted: true, page_size: 100 })
      setReports(res?.items || [])
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '加载已删日报失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadProjects = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await getDeletedProjects()
      setProjects(res?.items || [])
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '加载已删项目失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTasks = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getDeletedTasks()
      setTasks(res?.items || [])
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '加载已删任务失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!isAdmin) return
    if (tab === 'reports') loadReports()
    else if (tab === 'projects') loadProjects()
    else loadTasks()
  }, [tab, isAdmin, loadReports, loadProjects, loadTasks])

  // 当前 tab 对应的 items + id key — 用 useMemo 锁定引用,避免 useMultiSelect 内 useEffect 误清空
  const items = useMemo<any[]>(() => {
    if (tab === 'reports') return reports
    if (tab === 'projects') return projects
    return tasks
  }, [tab, reports, projects, tasks])
  const idKey = tab === 'projects' ? 'project_id' : 'id'
  const ms = useMultiSelect(items, { idKey: idKey as any })

  async function handleRestore() {
    const ids = Array.from(ms.selectedIds) as string[]
    if (ids.length === 0) return
    try {
      const fn =
        tab === 'reports' ? batchRestoreReports
        : tab === 'projects' ? batchRestoreProjects
        : batchRestoreTasks
      const res: any = await fn(ids)
      toast.success(`已恢复 ${res?.restored_count ?? ids.length} 条`)
      ms.clearAll()
      if (tab === 'reports') await loadReports()
      else if (tab === 'projects') await loadProjects()
      else await loadTasks()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '恢复失败')
    }
  }

  if (!isAdmin) return null

  return (
    <div className="p-6 max-w-6xl mx-auto animate-in">
      <div className="flex items-center gap-3 mb-2">
        <Trash2 size={24} style={{ color: '#a855f7' }} />
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
          回收站
        </h1>
      </div>
      <p className="text-sm mb-4" style={{ color: 'var(--color-text-secondary)' }}>
        展示已软删的日报与临时工单项目。点击「恢复」可还原。本页仅 admin 可见,不提供永久删除(保护历史数据完整性)。
      </p>

      {/* Tab 切换 */}
      <div
        className="flex gap-1 mb-4"
        style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
      >
        {(['reports', 'projects', 'sprint-tasks'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t)
              ms.clearAll()
            }}
            className="px-4 py-2 text-sm transition-colors"
            style={{
              color: tab === t ? '#a855f7' : 'var(--color-text-secondary)',
              borderBottom: tab === t ? '2px solid #a855f7' : '2px solid transparent',
              marginBottom: '-1px',
              fontWeight: tab === t ? 600 : 400,
            }}
          >
            {t === 'reports'
              ? `已删日报 (${reports.length})`
              : t === 'projects'
                ? `已删临时项目 (${projects.length})`
                : `已删 Sprint 任务 (${tasks.length})`}
          </button>
        ))}
      </div>

      {/* relative z-50 — 防止 sticky 操作栏被下方 table 创建的层叠上下文困住 */}
      <div className="relative z-50">
        <ListActionBar
          selectedCount={ms.selectedCount}
          onClear={ms.clearAll}
          hint={
            tab === 'reports'
              ? '恢复后日报重新出现在主列表'
              : tab === 'projects'
                ? '恢复后项目重新出现在项目列表'
                : '恢复后任务回到 Sprint 看板,燃尽与关键路径会自动重算'
          }
        >
          <button
            onClick={handleRestore}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium"
            style={{ background: '#22c55e', color: '#fff' }}
          >
            🔄 恢复选中
          </button>
        </ListActionBar>
      </div>

      {/* 列表 */}
      {loading ? (
        <div className="text-sm py-8 text-center" style={{ color: 'var(--color-text-secondary)' }}>
          加载中…
        </div>
      ) : items.length === 0 ? (
        <div className="text-sm py-12 text-center" style={{ color: 'var(--color-text-secondary)' }}>
          {tab === 'reports'
            ? '没有已删日报 ✨'
            : tab === 'projects'
              ? '没有已删临时项目 ✨'
              : '没有已删 Sprint 任务 ✨'}
        </div>
      ) : (
        <div
          className="rounded-xl overflow-hidden"
          style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
        >
          <div
            className="flex items-center gap-3 px-4 py-2.5 text-xs font-semibold"
            style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)' }}
          >
            <input
              type="checkbox"
              checked={ms.isAllSelected}
              ref={(el) => {
                if (el) el.indeterminate = ms.isIndeterminate
              }}
              onChange={() => (ms.isAllSelected ? ms.clearAll() : ms.selectAll())}
              className="cursor-pointer"
              title="全选"
            />
            <span>全选</span>
            <span className="flex-1" />
            <span style={{ color: 'var(--color-text-secondary)', fontWeight: 400 }}>
              共 {items.length} 条
            </span>
          </div>
          <div>
            {items.map((it: any) => {
              const id = String(it[idKey])
              return (
                <div
                  key={id}
                  className="flex items-center gap-3 px-4 py-3 text-sm"
                  style={{
                    borderTop: '1px solid var(--color-border-subtle)',
                    background: ms.isSelected(id) ? 'rgba(168,85,247,0.06)' : undefined,
                  }}
                >
                  <input
                    type="checkbox"
                    checked={ms.isSelected(id)}
                    onChange={() => ms.toggle(id)}
                    className="cursor-pointer"
                  />
                  {tab === 'reports' ? (
                    <>
                      <span className="font-medium" style={{ minWidth: 100 }}>
                        {it.report_date}
                      </span>
                      <span style={{ color: 'var(--color-text-secondary)', minWidth: 60 }}>·</span>
                      <span style={{ minWidth: 80 }}>{it.user_name || it.member}</span>
                      <span className="flex-1 truncate" style={{ color: 'var(--color-text-secondary)' }}>
                        {(it.parsed_content?.summary || it.raw_input_text || '').toString().slice(0, 80)}
                      </span>
                    </>
                  ) : tab === 'projects' ? (
                    <>
                      <span className="font-medium">{it.name}</span>
                      <span style={{ color: 'var(--color-text-secondary)' }}>·</span>
                      <span style={{ color: 'var(--color-text-secondary)' }}>{it.code}</span>
                      <span className="flex-1 text-xs" style={{ color: 'var(--color-text-muted)' }}>
                        删除于 {it.deleted_at ? new Date(it.deleted_at).toLocaleString('zh-CN') : '-'}
                      </span>
                    </>
                  ) : (
                    <>
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded shrink-0"
                        style={{ background: 'rgba(99,102,241,0.18)', color: '#a5b4fc' }}
                        title="Sprint 编号"
                      >
                        S#{it.sprint_number}
                      </span>
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded shrink-0"
                        style={{
                          background:
                            it.priority === 'p0' ? 'rgba(239,68,68,0.18)'
                            : it.priority === 'p1' ? 'rgba(245,158,11,0.18)'
                            : it.priority === 'p2' ? 'rgba(59,130,246,0.18)'
                            : 'rgba(148,163,184,0.18)',
                          color:
                            it.priority === 'p0' ? '#fca5a5'
                            : it.priority === 'p1' ? '#fcd34d'
                            : it.priority === 'p2' ? '#93c5fd'
                            : '#cbd5e1',
                        }}
                      >
                        {it.priority?.toUpperCase()}
                      </span>
                      <span className="font-medium flex-1 truncate">{it.title}</span>
                      <span className="text-[11px] shrink-0" style={{ color: 'var(--color-text-secondary)' }}>
                        {it.story_points}pt · {it.status}
                      </span>
                      <span className="text-[11px] shrink-0" style={{ color: 'var(--color-text-muted)' }}>
                        删除于 {it.deleted_at ? new Date(it.deleted_at).toLocaleString('zh-CN') : '-'}
                      </span>
                    </>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
