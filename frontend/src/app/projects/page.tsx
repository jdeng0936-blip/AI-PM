/**
 * app/projects/page.tsx — 项目列表页
 *
 * 展示所有项目的健康矩阵卡片 + 新建项目入口
 */
'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/use-auth-store'
import { getProjectsOverview, createProject } from '@/api/projects'
import { toast } from 'sonner'
import { FolderKanban, Plus, ArrowRight, RefreshCw, Search } from 'lucide-react'

export default function ProjectsPage() {
  const router = useRouter()
  const { isAdmin } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [projects, setProjects] = useState<any[]>([])
  const [overview, setOverview] = useState<any>({})
  const [searchQuery, setSearchQuery] = useState('')

  const healthColor = (s: string) =>
    ({ green: '#22c55e', yellow: '#eab308', red: '#ef4444' }[s] || '#4b5563')

  const fetchProjects = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getProjectsOverview() as any
      setOverview(data)
      setProjects(data.projects || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchProjects() }, [fetchProjects])

  const filtered = projects.filter(
    (p) =>
      p.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      p.code?.toLowerCase().includes(searchQuery.toLowerCase())
  )

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
        </div>
      </div>

      {/* 统计条 */}
      <div className="flex gap-4 mb-6 animate-in" style={{ animationDelay: '0.1s' }}>
        <div className="stat-card flex items-center gap-3 flex-1">
          <FolderKanban size={20} color="#3b82f6" />
          <span className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>总计</span>
          <span className="text-lg font-bold" style={{ color: 'var(--color-text-primary)' }}>{overview.total ?? 0}</span>
        </div>
        {['green', 'yellow', 'red'].map((s) => (
          <div key={s} className="stat-card flex items-center gap-2 flex-1">
            <div className="w-3 h-3 rounded-full" style={{ background: healthColor(s) }} />
            <span className="text-lg font-bold" style={{ color: healthColor(s) }}>
              {overview[`${s}_count`] ?? 0}
            </span>
          </div>
        ))}
      </div>

      {/* 搜索 */}
      <div className="mb-5 animate-in" style={{ animationDelay: '0.15s' }}>
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

      {/* 项目卡片列表 */}
      <div className="grid grid-cols-1 gap-4">
        {filtered.map((p: any, i: number) => (
          <div
            key={p.project_id}
            className="stat-card cursor-pointer flex items-center gap-5 animate-in"
            style={{ animationDelay: `${0.2 + i * 0.05}s` }}
            onClick={() => router.push(`/project/${p.project_id}`)}
          >
            <div className="w-3 h-3 rounded-full shrink-0" style={{ background: healthColor(p.health_status) }} />
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-sm" style={{ color: 'var(--color-text-primary)' }}>
                {p.code} · {p.name}
              </div>
              <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                第{p.current_stage}阶段「{p.stage_name}」 · {p.track === 'dual' ? '软硬双轨' : p.track}
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
            <ArrowRight size={16} color="#4b5563" />
          </div>
        ))}
      </div>
    </div>
  )
}
