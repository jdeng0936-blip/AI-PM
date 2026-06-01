'use client'

import { useRouter } from 'next/navigation'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  FileCheck2,
  Gauge,
  Users,
} from 'lucide-react'
import type { PersonnelProbeItem, PersonnelProbesResponse } from '@/api/dashboard'

const PROBE_WINDOWS = [
  { label: '3 天', value: 3 },
  { label: '7 天', value: 7 },
  { label: '15 天', value: 15 },
  { label: '1 个月', value: 30 },
  { label: '3 个月', value: 90 },
  { label: '半年', value: 180 },
  { label: '全年', value: 365 },
]

const statusLabel: Record<PersonnelProbeItem['probe_status'], string> = {
  normal: '正常',
  watch: '观察',
  needs_talk: '需沟通',
  risk: '风险',
}

const statusColor: Record<PersonnelProbeItem['probe_status'], string> = {
  normal: 'var(--color-status-green)',
  watch: '#d4a24e',
  needs_talk: '#f97316',
  risk: 'var(--color-status-red)',
}

function percent(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  return `${value}%`
}

function healthColor(status: string) {
  return ({ green: '#22c55e', yellow: '#eab308', red: '#ef4444', locked: '#4b5563' }[status] || '#4b5563')
}

function healthLabel(status: string) {
  return ({ green: '正常', yellow: '观察', red: '风险', locked: '锁定' }[status] || status || '-')
}

interface ExecutiveCommandCenterProps {
  overview: any
  morningStats: any
  missingMembers: any[]
  morningReports: any[]
  riskAlerts: any[]
  projects: any[]
  probes: PersonnelProbesResponse | null
  probeDays: number
  onProbeDaysChange: (days: number) => void
}

export function ExecutiveCommandCenter({
  overview,
  morningStats,
  missingMembers,
  morningReports,
  riskAlerts,
  projects,
  probes,
  probeDays,
  onProbeDaysChange,
}: ExecutiveCommandCenterProps) {
  const router = useRouter()
  const totalPeople = (morningStats.total_reports || 0) + missingMembers.length
  const submitRate = totalPeople > 0 ? Math.round(((morningStats.total_reports || 0) / totalPeople) * 100) : 0
  const redYellowProjects = (overview.red_count || 0) + (overview.yellow_count || 0)
  const failedReports = morningStats.fail_count || 0
  const focusItems = [
    ...riskAlerts.slice(0, 3).map((alert) => ({
      key: `risk-${alert.alert_id}`,
      tone: 'risk' as const,
      title: `${alert.member} 的卡点未解决`,
      meta: `${alert.department || '未填部门'} · 已 ${alert.days_unresolved || 0} 天`,
      action: '查看风险',
      route: '/dashboard',
    })),
    ...projects
      .filter((project) => project.health_status === 'red' || project.health_status === 'yellow')
      .slice(0, 3)
      .map((project) => ({
        key: `project-${project.project_id}`,
        tone: project.health_status === 'red' ? ('risk' as const) : ('watch' as const),
        title: `${project.code} · ${project.name}`,
        meta: `${healthLabel(project.health_status)} · 距交付 ${project.days_to_deadline ?? '-'} 天`,
        action: '进入项目',
        route: `/project/${project.project_id}`,
      })),
    missingMembers.length > 0
      ? {
          key: 'missing-members',
          tone: 'watch' as const,
          title: `${missingMembers.length} 人今日未汇报`,
          meta: missingMembers.slice(0, 5).map((m) => m.name).join('、'),
          action: '查看名单',
          route: '#people-probe',
        }
      : null,
    failedReports > 0
      ? {
          key: 'failed-reports',
          tone: 'watch' as const,
          title: `${failedReports} 条日报被 AI 退回`,
          meta: '建议关注质量和表达是否稳定',
          action: '查看日报',
          route: '#report-quality',
        }
      : null,
  ].filter(Boolean).slice(0, 5) as Array<{
    key: string
    tone: 'risk' | 'watch'
    title: string
    meta: string
    action: string
    route: string
  }>

  const projectRows = [...projects]
    .sort((a, b) => {
      const order: Record<string, number> = { red: 0, yellow: 1, green: 2, locked: 3 }
      return (order[a.health_status] ?? 4) - (order[b.health_status] ?? 4)
    })
    .slice(0, 6)

  return (
    <div className="space-y-8">
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {[
          { label: '今日提交率', value: `${submitRate}%`, sub: `${morningStats.total_reports || 0}/${totalPeople || 0} 人`, icon: FileCheck2, tone: submitRate >= 90 ? 'green' : submitRate >= 70 ? 'gold' : 'red', route: '#people-probe' },
          { label: '今日活跃', value: morningStats.total_reports || 0, sub: '已提交日报人数', icon: Users, tone: 'blue', route: '#people-probe' },
          { label: '未汇报', value: missingMembers.length, sub: '今天需要提醒', icon: Clock3, tone: missingMembers.length ? 'red' : 'green', route: '#people-probe' },
          { label: '红黄项目', value: redYellowProjects, sub: `红 ${overview.red_count || 0} / 黄 ${overview.yellow_count || 0}`, icon: Gauge, tone: redYellowProjects ? 'red' : 'green', route: '/projects' },
          { label: '未解卡点', value: riskAlerts.length, sub: '当前风险池', icon: AlertTriangle, tone: riskAlerts.length ? 'red' : 'green', route: '/dashboard' },
          { label: '日报均分', value: morningStats.avg_score ?? '-', sub: `合格 ${morningStats.pass_count || 0} / 退回 ${failedReports}`, icon: CheckCircle2, tone: failedReports ? 'gold' : 'green', route: '#report-quality' },
        ].map((item) => {
          const Icon = item.icon
          const color = item.tone === 'red' ? '#ef4444' : item.tone === 'gold' ? '#d4a24e' : item.tone === 'blue' ? '#3b82f6' : '#22c55e'
          return (
            <button
              key={item.label}
              type="button"
              onClick={() => {
                if (item.route.startsWith('#')) {
                  document.querySelector(item.route)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                } else {
                  router.push(item.route)
                }
              }}
              className="stat-card p-4 text-left w-full transition-colors hover:opacity-80 cursor-pointer"
            >
              <div className="mb-3 flex items-center justify-between gap-3">
                <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{item.label}</span>
                <Icon size={15} style={{ color }} />
              </div>
              <div className="text-2xl font-semibold tabular-nums" style={{ color: 'var(--color-text-primary)' }}>
                {item.value}
              </div>
              <div className="mt-2 text-[11px]" style={{ color: 'var(--color-text-muted)' }}>{item.sub}</div>
            </button>
          )
        })}
      </section>

      <section className="grid grid-cols-1 gap-5 xl:grid-cols-[1.1fr_1fr]">
        <div>
          <div className="section-title">今天需要我关注</div>
          {focusItems.length === 0 ? (
            <div className="stat-card py-8 text-center text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              今日暂无需要总经理介入的事项。
            </div>
          ) : (
            <div className="divide-y" style={{ borderColor: 'var(--color-border-subtle)' }}>
              {focusItems.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => {
                    if (item.route.startsWith('#')) {
                      document.querySelector(item.route)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                    } else {
                      router.push(item.route)
                    }
                  }}
                  className="flex w-full items-center gap-3 px-1 py-3 text-left transition-colors hover:bg-[var(--color-bg-hover)]"
                  style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
                >
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: item.tone === 'risk' ? '#ef4444' : '#d4a24e' }}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                      {item.title}
                    </span>
                    <span className="mt-1 block truncate text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                      {item.meta || '-'}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs" style={{ color: 'var(--color-brand-blue)' }}>{item.action}</span>
                  <ArrowRight size={14} style={{ color: 'var(--color-text-muted)' }} />
                </button>
              ))}
            </div>
          )}
        </div>

        <div>
          <div className="section-title">项目速览</div>
          {projectRows.length === 0 ? (
            <div className="stat-card py-8 text-center text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              暂无项目。可以从右上角新建项目开始测试。
            </div>
          ) : (
            <div className="space-y-2">
              {projectRows.map((project) => (
                <button
                  key={project.project_id}
                  type="button"
                  onClick={() => router.push(`/project/${project.project_id}`)}
                  className="flex w-full items-center gap-3 rounded-md px-2 py-2 text-left transition-colors hover:bg-[var(--color-bg-hover)]"
                >
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: healthColor(project.health_status) }} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                      {project.code} · {project.name}
                    </span>
                    <span className="mt-0.5 block truncate text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
                      第{project.current_stage}阶段 · {project.stage_name || '未设阶段'}
                    </span>
                  </span>
                  <span className="shrink-0 text-right text-xs tabular-nums" style={{ color: healthColor(project.health_status) }}>
                    {healthLabel(project.health_status)}
                    <span className="block text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                      {project.days_to_deadline ?? '-'} 天
                    </span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      <section id="people-probe" className="scroll-mt-6">
        <div className="section-title flex flex-wrap items-center gap-2">
          人员实时状态探针
          <span className="text-[11px] font-normal" style={{ color: 'var(--color-text-muted)' }}>
            用日报连续性、超时、卡点、质量和贡献入账识别异常苗头
          </span>
        </div>
        <div className="mb-4 flex flex-wrap gap-2">
          {PROBE_WINDOWS.map((windowItem) => (
            <button
              key={windowItem.value}
              type="button"
              onClick={() => onProbeDaysChange(windowItem.value)}
              className="rounded px-3 py-1 text-xs transition-colors"
              style={{
                background: probeDays === windowItem.value ? '#3b82f6' : 'transparent',
                color: probeDays === windowItem.value ? '#fff' : 'var(--color-text-secondary)',
                border: probeDays === windowItem.value ? '1px solid #3b82f6' : '1px solid var(--color-border-subtle)',
              }}
            >
              {windowItem.label}
            </button>
          ))}
        </div>

        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          {(['risk', 'needs_talk', 'watch', 'normal'] as const).map((status) => (
            <div key={status} className="rounded-md px-3 py-2" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
              <div className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>{statusLabel[status]}</div>
              <div className="mt-1 text-xl font-semibold tabular-nums" style={{ color: statusColor[status] }}>
                {probes?.summary?.[status] ?? 0}
              </div>
            </div>
          ))}
        </div>

        <div className="overflow-x-auto rounded-md" style={{ border: '1px solid var(--color-border-subtle)' }}>
          <table className="w-full min-w-[920px] text-sm">
            <thead style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)' }}>
              <tr>
                <th className="px-3 py-2 text-left font-medium">人员</th>
                <th className="px-3 py-2 text-left font-medium">状态</th>
                <th className="px-3 py-2 text-right font-medium">提交天数</th>
                <th className="px-3 py-2 text-right font-medium">缺报</th>
                <th className="px-3 py-2 text-right font-medium">通过率</th>
                <th className="px-3 py-2 text-right font-medium">均分</th>
                <th className="px-3 py-2 text-right font-medium">超时</th>
                <th className="px-3 py-2 text-right font-medium">卡点</th>
                <th className="px-3 py-2 text-right font-medium">贡献入账</th>
                <th className="px-3 py-2 text-left font-medium">最近异常</th>
              </tr>
            </thead>
            <tbody>
              {(probes?.items || []).map((person) => (
                <tr key={person.user_id} style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
                  <td className="px-3 py-2">
                    <div className="font-medium" style={{ color: 'var(--color-text-primary)' }}>{person.name}</div>
                    <div className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>{person.department} · {person.job_title || person.role}</div>
                  </td>
                  <td className="px-3 py-2">
                    <span className="rounded px-2 py-0.5 text-xs" style={{ color: statusColor[person.probe_status], border: `1px solid ${statusColor[person.probe_status]}` }}>
                      {statusLabel[person.probe_status]}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums" style={{ color: 'var(--color-text-primary)' }}>{person.submitted_days}</td>
                  <td className="px-3 py-2 text-right tabular-nums" style={{ color: person.missing_days ? '#ef4444' : 'var(--color-text-secondary)' }}>{person.missing_days}</td>
                  <td className="px-3 py-2 text-right tabular-nums" style={{ color: 'var(--color-text-secondary)' }}>{percent(person.pass_rate)}</td>
                  <td className="px-3 py-2 text-right tabular-nums" style={{ color: 'var(--color-text-secondary)' }}>{person.avg_score ?? '-'}</td>
                  <td className="px-3 py-2 text-right tabular-nums" style={{ color: person.overdue_task_count ? '#ef4444' : 'var(--color-text-secondary)' }}>
                    {person.overdue_task_count}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums" style={{ color: person.open_risk_count ? '#ef4444' : 'var(--color-text-secondary)' }}>
                    {person.open_risk_count}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums" style={{ color: person.points_income ? '#22c55e' : 'var(--color-text-secondary)' }}>
                    {person.points_income}
                  </td>
                  <td className="px-3 py-2" style={{ color: 'var(--color-text-secondary)' }}>{person.note}</td>
                </tr>
              ))}
              {!probes?.items?.length && (
                <tr>
                  <td colSpan={10} className="px-3 py-8 text-center text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                    暂无人员数据。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section id="report-quality" className="scroll-mt-6">
        <div className="section-title">今日日报质量</div>
        {morningReports.length === 0 ? (
          <div className="stat-card py-6 text-center text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            今天还没有日报提交。
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            {morningReports.slice(0, 6).map((report) => (
              <div key={report.id || report.member} className="rounded-md px-3 py-2" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>{report.member}</div>
                    <div className="mt-0.5 truncate text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>{report.tasks || report.ai_comment || '-'}</div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="text-sm font-semibold tabular-nums" style={{ color: report.pass_check ? '#22c55e' : '#ef4444' }}>{report.ai_score ?? '-'}</div>
                    <div className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>{report.pass_check ? '合格' : '退回'}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
