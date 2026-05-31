/**
 * RecommendationSpine — 「建议今天先推进」编辑式发丝列表（全页最高优先级区段）
 *
 * 最多 3 行，由从战台中心巨号下方降下来的金脊线串联：脊线是一根定位包裹内的
 * 绝对定位竖轨(固定 left-X，保证跨行共线)，每行在轨上焊一个节点圆点——
 * #1 实心金点(此事最先)，#2/#3 空心点。序号 01/02/03 是排版优先级线索，
 * 明确「不是名次/不与人比较」。空(无推荐且无待跟进)时整块不渲染。
 */
'use client'

import { useRouter } from 'next/navigation'
import { Sparkles } from 'lucide-react'
import { ContributionPill } from './contribution-pill'
import { DECK_GOLD, dueTint, taskStatusLabel, type RecRow } from './workbench-utils'

const RAIL_LEFT = 13 // px，脊线竖轨的固定 X（节点圆点居中覆盖其上）

function metaLine(row: RecRow): string {
  const parts = [row.projectCode, row.projectName, row.status ? taskStatusLabel[row.status] || row.status : null]
  return parts.filter(Boolean).join(' · ')
}

export function RecommendationSpine({ rows }: { rows: RecRow[] }) {
  const router = useRouter()
  if (rows.length === 0) return null

  const scrollToTasks = () => {
    const target = document.getElementById('my-tasks')
    target?.scrollIntoView({
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'start',
    })
  }

  return (
    <div>
      <div className="section-title flex flex-wrap items-center gap-2">
        <Sparkles size={15} style={{ color: DECK_GOLD }} />
        建议今天先推进
        <span className="text-[11px] font-normal" style={{ color: 'var(--color-text-muted)' }}>
          按截止时间和贡献价值自动排序
        </span>
        <button
          type="button"
          onClick={scrollToTasks}
          className="ml-auto text-[11px] transition-opacity hover:opacity-80"
          style={{ color: 'var(--color-text-muted)' }}
        >
          查看我的任务 ↓
        </button>
      </div>

      <div className="relative">
        {/* 金脊线竖轨（line/stroke，不计入金色"强调面"预算） */}
        <div
          className="absolute"
          style={{ left: RAIL_LEFT, top: 10, bottom: 10, width: 2, background: 'var(--deck-spine)' }}
        />

        {rows.map((row) => {
          const solid = row.rank === 1
          const meta = metaLine(row)
          return (
            <div
              key={row.key}
              className="relative"
              style={{ paddingLeft: 32, borderBottom: '1px solid var(--color-border-subtle)' }}
            >
              {/* 节点圆点 */}
              <span
                aria-hidden
                className="absolute"
                style={{
                  left: RAIL_LEFT - 4,
                  top: 21,
                  width: 9,
                  height: 9,
                  borderRadius: 9999,
                  background: solid ? DECK_GOLD : 'var(--color-bg-primary)',
                  border: solid ? 'none' : `1.5px solid ${DECK_GOLD}`,
                }}
              />

              <div className="flex items-start gap-3 py-3.5">
                <span
                  className="shrink-0 tabular-nums text-[13px]"
                  style={{ color: 'var(--color-text-muted)', width: 20, lineHeight: '20px' }}
                >
                  {String(row.rank).padStart(2, '0')}
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-3">
                    <span
                      className="truncate text-[15px] font-semibold"
                      style={{ color: 'var(--color-text-primary)' }}
                    >
                      {row.title}
                    </span>
                    <span
                      className="shrink-0 text-[13px] font-semibold tabular-nums"
                      style={{ color: dueTint(row.daysLeft) }}
                    >
                      {row.dueText}
                    </span>
                  </div>

                  <div className="mt-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                    {meta}
                    {row.source === 'milestone' && <span style={{ color: DECK_GOLD }}> · 贡献节点</span>}
                    {row.source === 'followup' && (
                      <span style={{ color: 'var(--color-status-red)' }}> · 昨日延期 · 继续跟进</span>
                    )}
                  </div>

                  <div className="mt-2 flex items-center justify-between gap-3">
                    <ContributionPill
                      source={row.source}
                      points={row.points}
                      milestoneState={row.milestoneState}
                    />
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        router.push(row.route)
                      }}
                      className="shrink-0 text-[12px] font-medium transition-opacity hover:opacity-80 hover:underline"
                      style={{ color: 'var(--color-brand-blue)' }}
                    >
                      {row.actionLabel}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
