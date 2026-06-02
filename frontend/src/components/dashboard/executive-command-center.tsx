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
import type {
  ContributionPeriod,
  PeopleContributionItem,
  PeopleContributionResponse,
  PersonnelProbeItem,
  PersonnelProbesResponse,
} from '@/api/dashboard'

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

const contributionPeriodLabel: Record<ContributionPeriod, string> = {
  month: '本月',
  quarter: '本季',
  year: '今年',
  all: '全部',
}

const contributionRiskLabel: Record<string, string> = {
  normal: '正常',
  watch: '观察',
  risk: '风险',
}

const contributionRiskColor = (risk: string) =>
  ({ normal: '#22c55e', watch: '#d4a24e', risk: '#ef4444' }[risk] || '#94a3b8')

function percent(value: number | null | undefined) {
  if (value === null || value === undefined) return '-'
  return `${value}%`
}

function scoreColor(score: number | null) {
  if (score == null) return 'var(--color-text-secondary)'
  if (score >= 90) return '#22c55e'
  if (score >= 60) return '#eab308'
  return '#ef4444'
}

function healthColor(status: string) {
  return ({ green: '#22c55e', yellow: '#eab308', red: '#ef4444', locked: '#4b5563' }[status] || '#4b5563')
}

function healthLabel(status: string) {
  return ({ green: '正常', yellow: '观察', red: '风险', locked: '锁定' }[status] || status || '-')
}

function shortDate(value?: string | null) {
  if (!value) return '未设截止'
  return value.slice(5).replace('-', '/')
}

function milestoneStatusLabel(status?: string | null) {
  return ({ pending: '待推进', in_review: '待验收', approved: '已完成', void: '已作废' }[status || ''] || status || '未设节点')
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
  peopleContribution: PeopleContributionResponse | null
  contributionPeriod: ContributionPeriod
  onContributionPeriodChange: (period: ContributionPeriod) => void
  onContributionPersonClick: (person: PeopleContributionItem) => void
  onNavigate?: (route: string) => void
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
  peopleContribution,
  contributionPeriod,
  onContributionPeriodChange,
  onContributionPersonClick,
  onNavigate,
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
      route: '#risk-pool',
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
      const healthDelta = (order[a.health_status] ?? 4) - (order[b.health_status] ?? 4)
      if (healthDelta !== 0) return healthDelta
      const aOverdue = a.current_node?.overdue_days || a.delivery_overdue_days || 0
      const bOverdue = b.current_node?.overdue_days || b.delivery_overdue_days || 0
      if (aOverdue !== bOverdue) return bOverdue - aOverdue
      return (a.days_to_deadline ?? 9999) - (b.days_to_deadline ?? 9999)
    })
    .slice(0, 6)
  const probeItems = probes?.items || []
  const contributionItems = peopleContribution?.items || []
  const contributionByUserId = new Map(contributionItems.map((item) => [item.user_id, item]))
  const probeUserIds = new Set(probeItems.map((item) => item.user_id))
  const mergedPeople = [
    ...probeItems.map((probe) => ({
      key: probe.user_id,
      probe,
      contribution: contributionByUserId.get(probe.user_id) || null,
    })),
    ...contributionItems
      .filter((contribution) => !probeUserIds.has(contribution.user_id))
      .map((contribution) => ({
        key: contribution.user_id,
        probe: null,
        contribution,
      })),
  ]

  return (
    <div className="space-y-8">
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {[
          { label: '今日提交率', value: `${submitRate}%`, sub: `${morningStats.total_reports || 0}/${totalPeople || 0} 人`, icon: FileCheck2, tone: submitRate >= 90 ? 'green' : submitRate >= 70 ? 'gold' : 'red', route: '#people-probe' },
          { label: '今日活跃', value: morningStats.total_reports || 0, sub: '已提交日报人数', icon: Users, tone: 'blue', route: '#people-probe' },
          { label: '未汇报', value: missingMembers.length, sub: '今天需要提醒', icon: Clock3, tone: missingMembers.length ? 'red' : 'green', route: '#people-probe' },
          { label: '红黄项目', value: redYellowProjects, sub: `红 ${overview.red_count || 0} / 黄 ${overview.yellow_count || 0}`, icon: Gauge, tone: redYellowProjects ? 'red' : 'green', route: '/projects' },
          { label: '未解卡点', value: riskAlerts.length, sub: '当前风险池', icon: AlertTriangle, tone: riskAlerts.length ? 'red' : 'green', route: '#risk-pool' },
          { label: '日报均分', value: morningStats.avg_score ?? '-', sub: `合格 ${morningStats.pass_count || 0} / 退回 ${failedReports}`, icon: CheckCircle2, tone: failedReports ? 'gold' : 'green', route: '#report-quality' },
        ].map((item) => {
          const Icon = item.icon
          const color = item.tone === 'red' ? '#ef4444' : item.tone === 'gold' ? '#d4a24e' : item.tone === 'blue' ? '#3b82f6' : '#22c55e'
          return (
            <button
              key={item.label}
              type="button"
              onClick={() => {
                if (onNavigate) {
                  onNavigate(item.route)
                } else if (item.route.startsWith('#')) {
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
                    if (onNavigate) {
                      onNavigate(item.route)
                    } else if (item.route.startsWith('#')) {
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
            <div className="space-y-2.5">
              {projectRows.map((project) => {
                const node = project.current_node
                const nodeOverdueDays = node?.overdue_days || 0
                const deliveryOverdueDays = project.delivery_overdue_days || 0
                const hasOverdue = nodeOverdueDays > 0 || deliveryOverdueDays > 0
                const ownerNames = project.owner_names || []
                const memberNames = project.member_names || []
                const milestoneSummary = project.milestone_summary || {}
                const totalNodes = milestoneSummary.total ?? 0
                const approvedNodes = milestoneSummary.approved ?? 0
                const nodeProgress = totalNodes > 0 ? Math.round((approvedNodes / totalNodes) * 100) : (project.progress_pct ?? 0)
                const nodeOwners = node?.owner_names?.length ? node.owner_names.join('、') : '节点负责人未分配'
                const ownerText = ownerNames.length ? ownerNames.join('、') : '负责人未指定'
                const memberText = memberNames.length ? memberNames.slice(0, 3).join('、') : '暂无成员'
                const deadlineText = node
                  ? nodeOverdueDays > 0
                    ? `节点超时 ${nodeOverdueDays} 天`
                    : node.days_left === null || node.days_left === undefined
                      ? '节点未设截止'
                      : `节点剩余 ${node.days_left} 天`
                  : '节点已完成'
                const deliveryText = deliveryOverdueDays > 0
                  ? `交付超时 ${deliveryOverdueDays} 天`
                  : project.days_to_deadline === null || project.days_to_deadline === undefined
                    ? '交付未设截止'
                    : `距交付 ${project.days_to_deadline} 天`

                return (
                  <button
                    key={project.project_id}
                    type="button"
                    onClick={() => router.push(`/project/${project.project_id}`)}
                    className="w-full rounded-md px-3 py-3 text-left transition-colors hover:bg-[var(--color-bg-hover)]"
                    style={{
                      border: `1px solid ${hasOverdue ? '#ef4444' : 'var(--color-border-subtle)'}`,
                      background: hasOverdue ? 'rgba(239,68,68,0.06)' : 'transparent',
                    }}
                  >
                    <div className="flex items-start gap-3">
                      <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: hasOverdue ? '#ef4444' : healthColor(project.health_status) }} />
                      <span className="min-w-0 flex-1">
                        <span className="flex min-w-0 items-start justify-between gap-3">
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                              {project.code} · {project.name}
                            </span>
                            <span className="mt-0.5 block truncate text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
                              第{project.current_stage}阶段 · {project.stage_name || '未设阶段'} · 节点 {approvedNodes}/{totalNodes} ({nodeProgress}%)
                            </span>
                          </span>
                          <span className="shrink-0 text-right text-xs tabular-nums" style={{ color: hasOverdue ? '#ef4444' : healthColor(project.health_status) }}>
                            {hasOverdue ? '需处理' : healthLabel(project.health_status)}
                            <span className="block text-[11px]" style={{ color: hasOverdue ? '#ef4444' : 'var(--color-text-muted)' }}>
                              {hasOverdue ? '处理' : '进入'}
                            </span>
                          </span>
                        </span>

                        <span className="mt-2 grid gap-1.5 text-[11px] md:grid-cols-2" style={{ color: 'var(--color-text-secondary)' }}>
                          <span className="truncate">
                            负责人：
                            <span style={{ color: ownerNames.length ? 'var(--color-text-primary)' : '#d4a24e' }}>{ownerText}</span>
                            {!ownerNames.length && <span className="ml-1" style={{ color: 'var(--color-text-muted)' }}>成员 {memberText}</span>}
                          </span>
                          <span className="truncate">
                            当前节点：
                            <span style={{ color: nodeOverdueDays > 0 ? '#ef4444' : 'var(--color-text-primary)' }}>
                              {node ? `${node.title} · ${milestoneStatusLabel(node.status)}` : '全部节点已完成'}
                            </span>
                          </span>
                          <span className="truncate">
                            节点负责人：
                            <span style={{ color: node?.owner_names?.length ? 'var(--color-text-primary)' : '#d4a24e' }}>{nodeOwners}</span>
                          </span>
                          <span className="truncate">
                            截止：
                            <span style={{ color: hasOverdue ? '#ef4444' : 'var(--color-text-secondary)' }}>
                              {node ? `${shortDate(node.target_date)} · ${deadlineText}` : deliveryText}
                            </span>
                            {node && deliveryOverdueDays > 0 && <span className="ml-1" style={{ color: '#ef4444' }}>· {deliveryText}</span>}
                          </span>
                        </span>
                      </span>
                    </div>
                  </button>
                )
              })}
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
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>状态窗口</span>
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
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>贡献周期</span>
            {(['month', 'quarter', 'year', 'all'] as ContributionPeriod[]).map((period) => (
              <button
                key={period}
                type="button"
                onClick={() => onContributionPeriodChange(period)}
                className="rounded px-3 py-1 text-xs transition-colors"
                style={{
                  background: contributionPeriod === period ? 'rgba(59,130,246,0.18)' : 'transparent',
                  color: contributionPeriod === period ? 'var(--color-brand-blue)' : 'var(--color-text-secondary)',
                  border: '1px solid var(--color-border-subtle)',
                }}
              >
                {contributionPeriodLabel[period]}
              </button>
            ))}
          </div>
        </div>

        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
          {(['risk', 'needs_talk', 'watch', 'normal'] as const).map((status) => (
            <div key={status} className="rounded-md px-3 py-2" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
              <div className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>{statusLabel[status]}</div>
              <div className="mt-1 text-xl font-semibold tabular-nums" style={{ color: statusColor[status] }}>
                {probes?.summary?.[status] ?? 0}
              </div>
            </div>
          ))}
          {[
            { label: '已入账', value: peopleContribution?.summary.earned_points ?? '-', color: '#22c55e' },
            { label: '待验收', value: peopleContribution?.summary.pending_points ?? '-', color: '#d4a24e' },
            { label: '逾期节点', value: peopleContribution?.summary.overdue_milestone_count ?? '-', color: '#ef4444' },
            { label: '贡献风险', value: peopleContribution?.summary.risk_people_count ?? '-', color: '#ef4444' },
          ].map((item) => (
            <div key={item.label} className="rounded-md px-3 py-2" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
              <div className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>{item.label}</div>
              <div className="mt-1 text-xl font-semibold tabular-nums" style={{ color: item.color }}>{item.value}</div>
            </div>
          ))}
        </div>

        <div className="overflow-x-auto rounded-md" style={{ border: '1px solid var(--color-border-subtle)' }}>
          <table className="w-full min-w-[1180px] text-sm">
            <thead style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)' }}>
              <tr>
                <th className="px-3 py-2 text-left font-medium">人员</th>
                <th className="px-3 py-2 text-left font-medium">状态</th>
                <th className="px-3 py-2 text-left font-medium">日报表现</th>
                <th className="px-3 py-2 text-left font-medium">风险信号</th>
                <th className="px-3 py-2 text-right font-medium">贡献积分</th>
                <th className="px-3 py-2 text-right font-medium">项目进度</th>
                <th className="px-3 py-2 text-right font-medium">节点逾期</th>
                <th className="px-3 py-2 text-left font-medium">最近异常</th>
              </tr>
            </thead>
            <tbody>
              {mergedPeople.map(({ key, probe, contribution }) => {
                const rowStatus: PersonnelProbeItem['probe_status'] =
                  probe?.probe_status || (contribution?.risk_level === 'risk' ? 'risk' : contribution?.risk_level === 'watch' ? 'watch' : 'normal')
                const name = probe?.name || contribution?.name || '-'
                const department = probe?.department || contribution?.department || '未填部门'
                const jobTitle = probe?.job_title || contribution?.job_title || probe?.role || contribution?.role || '成员'
                const submittedDays = probe?.submitted_days ?? contribution?.report_count ?? 0
                const missingDays = probe?.missing_days ?? 0
                const reportCount = contribution?.report_count ?? probe?.report_count ?? 0
                const reportScore = probe?.avg_score ?? contribution?.avg_report_score ?? null
                const openRiskCount = probe?.open_risk_count ?? contribution?.open_risk_count ?? 0
                const overdueTaskCount = probe?.overdue_task_count ?? 0
                const maxRiskDays = probe?.max_risk_days ?? 0
                const earnedPoints = contribution?.earned_points ?? (peopleContribution ? 0 : null)
                const pendingPoints = contribution?.pending_points ?? (peopleContribution ? 0 : null)
                const projectCount = contribution?.project_count ?? (peopleContribution ? 0 : null)
                const milestoneCount = contribution?.milestone_count ?? (peopleContribution ? 0 : null)
                const completedMilestoneCount = contribution?.completed_milestone_count ?? (peopleContribution ? 0 : null)
                const progressPct = contribution?.progress_pct ?? (peopleContribution ? 0 : null)
                const overdueMilestoneCount = contribution?.overdue_milestone_count ?? (peopleContribution ? 0 : null)
                const note =
                  probe?.note ||
                  (contribution?.risk_level === 'risk'
                    ? '贡献或节点存在风险'
                    : contribution?.risk_level === 'watch'
                      ? '贡献或节点需要观察'
                      : '暂无异常')

                return (
                  <tr key={key} style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
                    <td className="px-3 py-2 align-top">
                      <div className="font-medium" style={{ color: 'var(--color-text-primary)' }}>{name}</div>
                      <div className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>{department} · {jobTitle}</div>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <span className="rounded px-2 py-0.5 text-xs" style={{ color: statusColor[rowStatus], border: `1px solid ${statusColor[rowStatus]}` }}>
                        {statusLabel[rowStatus]}
                      </span>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <div className="tabular-nums" style={{ color: 'var(--color-text-primary)' }}>
                        提交 {submittedDays}
                        <span className="ml-2" style={{ color: missingDays ? '#ef4444' : 'var(--color-text-secondary)' }}>
                          缺报 {missingDays}
                        </span>
                      </div>
                      <div className="mt-1 text-[11px] tabular-nums" style={{ color: 'var(--color-text-secondary)' }}>
                        周期日报 {reportCount} · 通过 {percent(probe?.pass_rate)}
                        <span className="ml-2" style={{ color: scoreColor(reportScore) }}>均分 {reportScore ?? '-'}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2 align-top">
                      <div className="tabular-nums" style={{ color: openRiskCount || overdueTaskCount ? '#ef4444' : 'var(--color-text-secondary)' }}>
                        卡点 {openRiskCount} · 超时 {overdueTaskCount}
                      </div>
                      <div className="mt-1 text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                        {maxRiskDays > 0 ? `未解最长 ${maxRiskDays} 天` : '无长期未解'}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right align-top tabular-nums">
                      <div style={{ color: earnedPoints ? '#22c55e' : 'var(--color-text-secondary)' }}>已入账 {earnedPoints ?? '-'}</div>
                      <div className="mt-1 text-[11px]" style={{ color: pendingPoints ? '#d4a24e' : 'var(--color-text-muted)' }}>
                        待验收 {pendingPoints ?? '-'}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right align-top tabular-nums">
                      <div style={{ color: 'var(--color-text-primary)' }}>项目 {projectCount ?? '-'}</div>
                      <div className="mt-1 text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
                        节点 {completedMilestoneCount ?? '-'}/{milestoneCount ?? '-'}
                        {progressPct !== null && <span className="ml-1">{progressPct}%</span>}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right align-top tabular-nums" style={{ color: overdueMilestoneCount ? '#ef4444' : 'var(--color-text-secondary)' }}>
                      {overdueMilestoneCount ?? '-'}
                      {contribution && (
                        <div className="mt-1 text-[11px]" style={{ color: contributionRiskColor(contribution.risk_level) }}>
                          {contributionRiskLabel[contribution.risk_level]}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2 align-top" style={{ color: 'var(--color-text-secondary)' }}>
                      <div>{note}</div>
                      {contribution && (
                        <button
                          type="button"
                          onClick={() => onContributionPersonClick(contribution)}
                          className="mt-1 inline-flex items-center gap-1 text-[11px] transition-opacity hover:opacity-80"
                          style={{ color: 'var(--color-brand-blue)' }}
                        >
                          证据链 <ArrowRight size={12} />
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
              {!mergedPeople.length && (
                <tr>
                  <td colSpan={8} className="px-3 py-8 text-center text-sm" style={{ color: 'var(--color-text-secondary)' }}>
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
