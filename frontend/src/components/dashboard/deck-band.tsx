/**
 * DeckBand — 三列发丝战台栏（取代旧的三张等大统计卡）
 *
 *   今日战力 (左, 1fr)  ·  待解锁贡献 (中, 1.5fr)  ·  临期节点 (右, 1fr)
 *
 * 无卡片 chrome、无圆角、无阴影、无图标芯片——仅靠 1px 竖向发丝(border-strong)分隔，
 * 靠尺度落差与排版纪律取胜。待解锁贡献是全页唯一尺度焦点：居中巨号「白字」(永不金、
 * 永不发光)，下方一道 88px 金色起点条 = 贯穿全页金脊线的源头。
 * 临期着色只落在数字本身，且含义由副文案文字承载(WCAG 1.4.1，非纯色编码)。
 */
import Link from 'next/link'
import { DECK_GOLD } from './workbench-utils'

interface DeckBandProps {
  todayCount: number
  projectCount: number
  pendingContribution: number
  pendingNodeCount: number
  urgentCount: number
  hasOverdue: boolean
  /** 已入账累计积分；取数失败为 null → 隐藏对照行，绝不造假数 */
  totalPoints: number | null
}

const eyebrowStyle: React.CSSProperties = {
  fontSize: 'var(--text-deck-eyebrow)',
  letterSpacing: '0.06em',
  color: 'var(--color-text-muted)',
}

export function DeckBand({
  todayCount,
  projectCount,
  pendingContribution,
  pendingNodeCount,
  urgentCount,
  hasOverdue,
  totalPoints,
}: DeckBandProps) {
  const hasPending = pendingContribution > 0

  const urgentColor =
    urgentCount === 0 ? 'var(--color-text-primary)' : hasOverdue ? 'var(--color-status-red)' : DECK_GOLD
  const urgentSub = urgentCount === 0 ? '节奏稳定' : hasOverdue ? '已有逾期 · 建议优先推进' : '建议优先推进'
  const urgentSubColor = urgentCount === 0 ? 'var(--color-status-green)' : urgentColor

  return (
    <div className="grid grid-cols-1 gap-6 md:gap-0 md:grid-cols-[1fr_1.5fr_1fr]">
      {/* 今日战力 —— 最安静的上下文锚点，无强调色 */}
      <div className="px-1 md:px-5 py-1">
        <div style={eyebrowStyle}>今日战力</div>
        <div
          className="mt-2 font-semibold tabular-nums leading-none"
          style={{ fontSize: 'var(--text-deck-figure)', color: 'var(--color-text-primary)' }}
        >
          {todayCount}
        </div>
        <div className="mt-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          在账 {todayCount} 笔 · 来自 {projectCount} 个项目
        </div>
      </div>

      {/* 待解锁贡献 —— 情感主格：居中巨号白字 + 金脊起点 */}
      <div
        className="px-1 md:px-7 py-1 md:border-x"
        style={{ borderColor: 'var(--color-border-strong)' }}
      >
        <div style={eyebrowStyle}>待解锁贡献</div>
        <div className="mt-2 flex items-baseline gap-1.5">
          <span
            className="font-semibold tabular-nums leading-none"
            style={{
              fontSize: 'var(--text-deck-hero)',
              color: hasPending ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
            }}
          >
            {pendingContribution}
          </span>
          {hasPending && (
            <span className="text-base" style={{ color: 'var(--color-text-muted)' }}>
              分
            </span>
          )}
        </div>
        {/* 金脊线起点（全页唯一的金色"强调面"） */}
        <div style={{ height: 2, width: 88, marginTop: 12, background: 'var(--deck-spine-origin)' }} />
        <div className="mt-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
          {hasPending ? '完成节点后进入积分池' : '暂无待结算节点'}
        </div>
        {hasPending && (
          <div className="mt-1 text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
            来自 {pendingNodeCount} 个待结算节点
          </div>
        )}
        {totalPoints !== null && (
          <Link
            href="/me/contribution"
            className="mt-2.5 inline-block text-[11px] transition-opacity hover:opacity-80"
            style={{ color: 'var(--color-text-muted)' }}
          >
            已入账{' '}
            <span className="tabular-nums" style={{ color: 'var(--color-status-green)' }}>
              {totalPoints}
            </span>{' '}
            · 查看积分流水 →
          </Link>
        )}
      </div>

      {/* 临期节点 —— 唯一允许染紧迫色之处，色彩只落在数字，含义由文字承载 */}
      <div className="px-1 md:px-5 py-1 md:text-right">
        <div style={eyebrowStyle}>临期节点</div>
        <div
          className="mt-2 font-semibold tabular-nums leading-none"
          style={{ fontSize: 'var(--text-deck-figure)', color: urgentColor }}
        >
          {urgentCount}
        </div>
        {urgentCount > 0 && (
          <div
            className="md:ml-auto"
            style={{ height: 3, width: 32, marginTop: 8, background: urgentColor, borderRadius: 2 }}
          />
        )}
        <div className="mt-3 text-xs" style={{ color: urgentSubColor }}>
          {urgentSub}
        </div>
      </div>
    </div>
  )
}
