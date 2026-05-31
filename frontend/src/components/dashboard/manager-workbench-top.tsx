/**
 * ManagerWorkbenchTop — manager 轻量作战台顶部（仅 showLightManagerView 分支渲染）
 *
 *   战台栏 DeckBand → 建议今天先推进 RecommendationSpine → 我的任务 TaskLedgerRow 列表
 *
 * 纯组合 + 编排，不触碰 admin 监控台。所有数据由 dashboard/page.tsx 派生后传入。
 */
'use client'

import { useRouter } from 'next/navigation'
import { DeckBand } from './deck-band'
import { RecommendationSpine } from './recommendation-spine'
import { TaskLedgerRow } from './task-ledger-row'
import type { LedgerTaskRow, RecRow } from './workbench-utils'

interface ManagerWorkbenchTopProps {
  taskRows: LedgerTaskRow[]
  recommendedTasks: RecRow[]
  activeProjectCount: number
  pendingContribution: number
  pendingNodeCount: number
  urgentCount: number
  hasOverdue: boolean
  totalPoints: number | null
}

export function ManagerWorkbenchTop({
  taskRows,
  recommendedTasks,
  activeProjectCount,
  pendingContribution,
  pendingNodeCount,
  urgentCount,
  hasOverdue,
  totalPoints,
}: ManagerWorkbenchTopProps) {
  const router = useRouter()

  return (
    <>
      <div className="mb-8 animate-in" style={{ animationDelay: '0.05s' }}>
        <DeckBand
          todayCount={taskRows.length}
          projectCount={activeProjectCount}
          pendingContribution={pendingContribution}
          pendingNodeCount={pendingNodeCount}
          urgentCount={urgentCount}
          hasOverdue={hasOverdue}
          totalPoints={totalPoints}
        />
      </div>

      {recommendedTasks.length > 0 && (
        <div className="mb-8 animate-in" style={{ animationDelay: '0.12s' }}>
          <RecommendationSpine rows={recommendedTasks} />
        </div>
      )}

      <div id="my-tasks" className="mb-8 scroll-mt-6 animate-in" style={{ animationDelay: '0.18s' }}>
        <div className="section-title flex flex-wrap items-center gap-2">
          我的任务
          <span className="text-[11px] font-normal" style={{ color: 'var(--color-text-muted)' }}>
            {taskRows.length} 项 · {pendingNodeCount} 个贡献节点
          </span>
          <button
            type="button"
            onClick={() => router.push('/submit-report')}
            className="ml-auto rounded px-2 py-0.5 text-[11px]"
            style={{ color: 'var(--color-brand-blue)', border: '1px solid rgba(59,130,246,0.3)' }}
          >
            写今日计划
          </button>
        </div>

        {taskRows.length === 0 ? (
          <div
            className="stat-card py-8 text-center text-sm"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            暂无指派给你的进行中任务。可以从项目页查看参与项目，或在写日报时补充计划外事项。
          </div>
        ) : (
          <div>
            {taskRows.map((row) => (
              <TaskLedgerRow key={row.id} row={row} />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
