/**
 * workbench-utils — 静默战台 Quiet Deck 共享逻辑 / token 常量
 *
 * 工程师轻量作战台 (manager / 张毅 角色群体) 专用的纯函数与类型，
 * 与 admin 监控台完全隔离。所有积分只来自真实 initial_points / story_points。
 */

/** 贡献/认可 暖金，比 status-yellow(#eab308) 更克制；仅用于贡献数值、临期(≤2天未逾期)、脊线 */
export const DECK_GOLD = '#d4a24e'
/** 贡献药丸底色；药丸文字仍用实色 DECK_GOLD 以在 #1e2030 上过 4.5:1 对比 */
export const DECK_GOLD_SOFT = 'rgba(212, 162, 78, 0.10)'

export type MilestoneState = 'future' | 'unlocking' | 'inReview'
export type RecSource = 'sprint' | 'milestone' | 'followup'

/** 推荐区一行（建议今天先推进），已含折叠进来的待跟进合成行 */
export interface RecRow {
  key: string
  rank: number
  title: string
  projectCode: string | null
  projectName: string | null
  status: string | null
  source: RecSource
  points: number | null
  milestoneState?: MilestoneState
  isOnCriticalPath: boolean
  daysLeft: number | null
  dueText: string
  actionLabel: string
  route: string
}

/** 任务列表一行（我的任务），Sprint 任务 + 里程碑节点统一结构 */
export interface LedgerTaskRow {
  id: string
  title: string
  projectId: string
  projectCode: string
  projectName: string
  status: string
  source: 'sprint' | 'milestone'
  points: number
  priority?: string
  isOnCriticalPath: boolean
  plannedEnd: string | null
  daysLeft: number | null
  milestoneState?: MilestoneState
}

/** 距今天数；无日期返回 null（不参与临期统计） */
export function daysUntil(value?: string | null): number | null {
  if (!value) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(value)
  target.setHours(0, 0, 0, 0)
  return Math.ceil((target.getTime() - today.getTime()) / 86400000)
}

/** 截止文案：未设截止 / 已超 N 天 / 今天到期 / 还剩 N 天 */
export function dueLabel(daysLeft: number | null): string {
  if (daysLeft === null) return '未设截止'
  if (daysLeft < 0) return `已超 ${Math.abs(daysLeft)} 天`
  if (daysLeft === 0) return '今天到期'
  return `还剩 ${daysLeft} 天`
}

/** 截止着色：逾期红 / ≤2天金 / 其余次级 / 未设截止灰 */
export function dueTint(daysLeft: number | null): string {
  if (daysLeft === null) return 'var(--color-text-muted)'
  if (daysLeft < 0) return 'var(--color-status-red)'
  if (daysLeft <= 2) return DECK_GOLD
  return 'var(--color-text-secondary)'
}

/** 推荐排序档位（越小越优先）：逾期 > 今天 > ≤2天 > 其余 */
export function recTier(daysLeft: number): number {
  if (daysLeft < 0) return 0
  if (daysLeft === 0) return 1
  if (daysLeft <= 2) return 2
  return 3
}

/** 里程碑节点的贡献生命周期态 */
export function milestoneState(status: string, daysLeft: number | null): MilestoneState {
  if (status === 'in_review') return 'inReview'
  if (daysLeft !== null && daysLeft <= 2) return 'unlocking'
  return 'future'
}

export const taskStatusLabel: Record<string, string> = {
  todo: '待开始',
  in_progress: '进行中',
  blocked: '受阻',
  done: '已完成',
  pending: '待完成',
  in_review: '验收中',
  approved: '已验收',
  void: '已作废',
}

export const priorityLabel: Record<string, string> = {
  low: '低',
  medium: '中',
  high: '高',
  urgent: '紧急',
}

/** 状态语义色（纯文本上色，非彩块） */
export function statusTextColor(status: string): string {
  if (status === 'done' || status === 'approved') return 'var(--color-status-green)'
  if (status === 'blocked') return 'var(--color-status-red)'
  if (status === 'in_progress') return 'var(--color-text-primary)'
  return 'var(--color-text-secondary)'
}
