import type { MilestoneNodeIn } from '@/api/milestones'

export type ContributionProjectKind = 'software' | 'hardware' | 'structure' | 'test_debug' | 'mixed' | 'support'
export type ContributionComplexity = 'small' | 'standard' | 'complex' | 'strategic'
export type ContributionUrgency = 'normal' | 'urgent' | 'critical'
export type ContributionCollaboration = 'low' | 'medium' | 'high'

export const CONTRIBUTION_KIND_OPTIONS: Array<{ value: ContributionProjectKind; label: string }> = [
  { value: 'software', label: '软件功能' },
  { value: 'hardware', label: '硬件研发' },
  { value: 'structure', label: '结构设计' },
  { value: 'test_debug', label: '测试/调试' },
  { value: 'mixed', label: '软硬混合' },
  { value: 'support', label: '日常支撑' },
]

export const CONTRIBUTION_COMPLEXITY_OPTIONS: Array<{ value: ContributionComplexity; label: string }> = [
  { value: 'small', label: '小型维护' },
  { value: 'standard', label: '标准功能' },
  { value: 'complex', label: '复杂交付' },
  { value: 'strategic', label: '战略攻坚' },
]

export const CONTRIBUTION_URGENCY_OPTIONS: Array<{ value: ContributionUrgency; label: string }> = [
  { value: 'normal', label: '普通' },
  { value: 'urgent', label: '紧急' },
  { value: 'critical', label: '攻坚' },
]

export const CONTRIBUTION_COLLABORATION_OPTIONS: Array<{ value: ContributionCollaboration; label: string }> = [
  { value: 'low', label: '少' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '多' },
]

const complexityBase: Record<ContributionComplexity, number> = {
  small: 80,
  standard: 240,
  complex: 600,
  strategic: 1200,
}

const urgencyFactor: Record<ContributionUrgency, number> = {
  normal: 1,
  urgent: 1.2,
  critical: 1.35,
}

const collaborationFactor: Record<ContributionCollaboration, number> = {
  low: 1,
  medium: 1.15,
  high: 1.3,
}

const roleMix: Record<ContributionProjectKind, Array<{ role: string; pct: number }>> = {
  software: [
    { role: '软件', pct: 45 },
    { role: '测试', pct: 20 },
    { role: '调试', pct: 15 },
    { role: '项目负责人', pct: 10 },
    { role: '文档/验收', pct: 10 },
  ],
  hardware: [
    { role: '硬件', pct: 35 },
    { role: '测试', pct: 18 },
    { role: '调试', pct: 18 },
    { role: '结构', pct: 14 },
    { role: '项目负责人', pct: 10 },
    { role: '文档/验收', pct: 5 },
  ],
  structure: [
    { role: '结构', pct: 40 },
    { role: '硬件', pct: 15 },
    { role: '测试', pct: 15 },
    { role: '调试', pct: 15 },
    { role: '项目负责人', pct: 10 },
    { role: '文档/验收', pct: 5 },
  ],
  test_debug: [
    { role: '测试', pct: 35 },
    { role: '调试', pct: 30 },
    { role: '软件', pct: 15 },
    { role: '硬件', pct: 10 },
    { role: '项目负责人', pct: 10 },
  ],
  mixed: [
    { role: '软件', pct: 28 },
    { role: '硬件', pct: 22 },
    { role: '结构', pct: 15 },
    { role: '测试', pct: 15 },
    { role: '调试', pct: 10 },
    { role: '项目负责人', pct: 10 },
  ],
  support: [
    { role: '软件', pct: 25 },
    { role: '测试', pct: 20 },
    { role: '调试', pct: 20 },
    { role: '采购支持', pct: 15 },
    { role: '生产支持', pct: 10 },
    { role: '项目负责人', pct: 10 },
  ],
}

export function recommendContributionTotal(
  complexity: ContributionComplexity,
  urgency: ContributionUrgency,
  collaboration: ContributionCollaboration,
) {
  const raw = complexityBase[complexity] * urgencyFactor[urgency] * collaborationFactor[collaboration]
  return Math.max(10, Math.round(raw / 10) * 10)
}

function nodeWeight(node: MilestoneNodeIn, index: number, total: number) {
  if (node.node_type === 'software_req') return 0.15
  if (node.node_type === 'software_mvp') return 0.35
  if (node.node_type === 'software_validate') return 0.25
  if (node.node_type === 'software_launch') return 0.25
  if (node.node_type === 'hardware_review') return 0.25
  if (node.node_type === 'hardware_proto') return 0.35
  if (node.node_type === 'hardware_finalize') return 0.4
  if (node.node_type === 'temporary_done') return 1
  if (total <= 1) return 1
  if (index === 0) return 0.18
  if (index === total - 1) return 0.24
  return 0.58 / Math.max(total - 2, 1)
}

export function applyContributionRecommendation(
  nodes: MilestoneNodeIn[],
  totalPoints: number,
  projectKind: ContributionProjectKind,
) {
  if (nodes.length === 0) return []
  const weights = nodes.map((node, index) => nodeWeight(node, index, nodes.length))
  const weightTotal = weights.reduce((sum, weight) => sum + weight, 0) || 1
  let allocated = 0
  return nodes.map((node, index) => {
    const isLast = index === nodes.length - 1
    const points = isLast ? Math.max(totalPoints - allocated, 0) : Math.round((totalPoints * weights[index]) / weightTotal / 10) * 10
    allocated += points
    return {
      ...node,
      initial_points: points,
      description: roleMix[projectKind].map((item) => `${item.role}${item.pct}%`).join(' / '),
    }
  })
}

export function roleMixText(projectKind: ContributionProjectKind) {
  return roleMix[projectKind].map((item) => `${item.role} ${item.pct}%`).join(' · ')
}

export function nodesPointTotal(nodes: MilestoneNodeIn[]) {
  return nodes.reduce((sum, node) => sum + (Number(node.initial_points) || 0), 0)
}
