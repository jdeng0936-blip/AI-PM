/**
 * TaskLedgerRow — 我的任务列表中的一行（自定义行，非 .stat-card，以规避其 hover 抬升阴影）
 *
 * 左缘 3px type-dash：金色=里程碑/贡献节点，淡灰=Sprint；配冗余的状态化贡献文字，
 * 即使色条读起来很弱，里程碑 vs Sprint 仍能一眼分辨。整行可点 → 项目页。
 * 未设截止保持视觉平静(不染色)、上游已排除临期统计、排到末尾。
 */
'use client'

import { useRouter } from 'next/navigation'
import { ContributionPill } from './contribution-pill'
import {
  DECK_GOLD,
  dueLabel,
  dueTint,
  priorityLabel,
  statusTextColor,
  taskStatusLabel,
  type LedgerTaskRow,
} from './workbench-utils'

export function TaskLedgerRow({ row }: { row: LedgerTaskRow }) {
  const router = useRouter()
  const isMilestone = row.source === 'milestone'
  const dashColor = isMilestone ? DECK_GOLD : 'var(--color-border-strong)'

  return (
    <div
      onClick={() => router.push(`/project/${row.projectId}`)}
      className="group flex cursor-pointer items-start gap-3 px-2 py-3.5 transition-colors hover:bg-[var(--color-bg-hover)]"
      style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
    >
      {/* type-dash */}
      <div
        className="shrink-0 self-stretch transition-colors"
        style={{ width: 3, minHeight: 34, background: dashColor, borderRadius: 2 }}
      />

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            {row.title}
          </span>
          {isMilestone && (
            <span className="shrink-0 text-[11px]" style={{ color: DECK_GOLD }}>
              · 贡献节点
            </span>
          )}
          {row.isOnCriticalPath && (
            <span className="shrink-0 text-[11px]" style={{ color: 'var(--color-status-red)' }}>
              · 关键路径
            </span>
          )}
        </div>
        <div className="mt-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {row.projectCode} · {row.projectName}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] tabular-nums">
          <span style={{ color: statusTextColor(row.status) }}>
            {taskStatusLabel[row.status] || row.status}
          </span>
          {row.source === 'sprint' && row.priority && (
            <span style={{ color: 'var(--color-text-secondary)' }}>
              · 优先级 {priorityLabel[row.priority] || row.priority}
            </span>
          )}
          <span style={{ color: 'var(--color-text-muted)' }}>·</span>
          <ContributionPill source={row.source} points={row.points} milestoneState={row.milestoneState} />
        </div>
      </div>

      <div className="flex shrink-0 flex-col items-end text-right">
        <div className="text-sm font-semibold tabular-nums" style={{ color: dueTint(row.daysLeft) }}>
          {dueLabel(row.daysLeft)}
        </div>
        {row.plannedEnd && (
          <div className="mt-1 text-[11px] tabular-nums" style={{ color: 'var(--color-text-muted)' }}>
            {row.plannedEnd}
          </div>
        )}
        <div className="mt-2 flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              router.push('/submit-report')
            }}
            className="rounded px-2 py-0.5 text-[11px] font-medium transition-colors hover:bg-[rgba(59,130,246,0.08)]"
            style={{ color: 'var(--color-brand-blue)', border: '1px solid rgba(59,130,246,0.24)' }}
          >
            写今日计划
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              router.push(`/project/${row.projectId}`)
            }}
            className="rounded px-2 py-0.5 text-[11px] font-medium transition-opacity hover:opacity-80"
            style={{ color: 'var(--color-text-secondary)', border: '1px solid var(--color-border-subtle)' }}
          >
            进入项目
          </button>
        </div>
      </div>
    </div>
  )
}
