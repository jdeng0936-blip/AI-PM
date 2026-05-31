/**
 * ContributionPill — 三态贡献徽记（单一真相源）
 *
 *   里程碑 future    → 金色描边药丸 `+30 贡献`
 *   里程碑 unlocking → 金色描边药丸 `待解锁 30`（临期 ≤2 天的"就快到手"强调）
 *   里程碑 inReview  → 纯文本 `完成后入账`（无药丸，已提交待验收）
 *   Sprint           → 中性灰药丸 `30 pt`（工作量估点，绝不带"贡献"字样、绝不金色）
 *   followup / null  → 不渲染
 *
 * 绝不做奖杯 / 纸屑 / 名次。数字只来自真实 initial_points / story_points。
 */
import { DECK_GOLD, DECK_GOLD_SOFT, type MilestoneState, type RecSource } from './workbench-utils'

interface ContributionPillProps {
  source: RecSource
  points: number | null
  milestoneState?: MilestoneState
}

export function ContributionPill({ source, points, milestoneState }: ContributionPillProps) {
  if (source === 'followup' || points === null) return null

  if (source === 'sprint') {
    return (
      <span
        className="inline-flex items-center rounded-md px-2 text-[11px] font-semibold tabular-nums"
        style={{ height: 20, background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)' }}
      >
        {points} pt
      </span>
    )
  }

  // milestone
  if (milestoneState === 'inReview') {
    return (
      <span className="text-[11px] font-medium" style={{ color: 'var(--color-text-secondary)' }}>
        完成后入账
      </span>
    )
  }

  const text = milestoneState === 'unlocking' ? `待解锁 ${points}` : `+${points} 贡献`
  return (
    <span
      className="inline-flex items-center rounded-md px-2 text-[11px] font-semibold tabular-nums"
      style={{ height: 20, background: DECK_GOLD_SOFT, color: DECK_GOLD, border: `1px solid ${DECK_GOLD}` }}
    >
      {text}
    </span>
  )
}
