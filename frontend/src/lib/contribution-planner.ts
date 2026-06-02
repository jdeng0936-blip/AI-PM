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
    { role: '需求文档', pct: 10 },
    { role: '软件研发', pct: 40 },
    { role: '功能测试', pct: 20 },
    { role: '联调', pct: 15 },
    { role: '交付上线', pct: 10 },
    { role: '项目负责人', pct: 5 },
  ],
  hardware: [
    { role: '方案设计', pct: 12 },
    { role: 'ID/结构设计', pct: 18 },
    { role: '硬件设计', pct: 30 },
    { role: '测试/调试', pct: 20 },
    { role: '试产导入', pct: 10 },
    { role: '客户验收', pct: 5 },
    { role: '项目负责人', pct: 5 },
  ],
  structure: [
    { role: 'ID', pct: 18 },
    { role: '结构设计', pct: 38 },
    { role: '硬件配合', pct: 12 },
    { role: '测试/调试', pct: 15 },
    { role: '试产导入', pct: 10 },
    { role: '项目负责人', pct: 7 },
  ],
  test_debug: [
    { role: '测试方案', pct: 20 },
    { role: '功能测试', pct: 30 },
    { role: '联调', pct: 25 },
    { role: '验收测试', pct: 15 },
    { role: '项目负责人', pct: 10 },
  ],
  mixed: [
    { role: '需求文档', pct: 8 },
    { role: 'ID/结构设计', pct: 15 },
    { role: '硬件设计', pct: 20 },
    { role: '软件研发', pct: 25 },
    { role: '测试/联调', pct: 17 },
    { role: '交付验收', pct: 8 },
    { role: '项目负责人', pct: 7 },
  ],
  support: [
    { role: '需求确认', pct: 12 },
    { role: '研发/配置', pct: 25 },
    { role: '测试/调试', pct: 20 },
    { role: '交付上线', pct: 15 },
    { role: '采购支持', pct: 10 },
    { role: '生产/仓储支持', pct: 8 },
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
  const text = `${node.title} ${node.description || ''}`
  if (text.includes('需求') || text.includes('范围') || text.includes('文档')) return 0.12
  if (text.includes('ID') || text.includes('设计') || text.includes('方案')) return 0.12
  if (text.includes('研发') || text.includes('实现') || text.includes('MVP')) return 0.24
  if (text.includes('样机')) return 0.18
  if (text.includes('联调') || text.includes('自测')) return 0.12
  if (text.includes('测试') || text.includes('验证')) return 0.16
  if (text.includes('试产')) return 0.08
  if (text.includes('交付') || text.includes('上线') || text.includes('验收')) return 0.08
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
