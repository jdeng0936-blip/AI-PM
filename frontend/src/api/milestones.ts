import request from '@/api/request'

export type MilestoneNodeType =
  | 'software_req'
  | 'software_mvp'
  | 'software_validate'
  | 'software_launch'
  | 'hardware_review'
  | 'hardware_proto'
  | 'hardware_finalize'
  | 'temporary_done'
  | 'custom'

export type MilestoneStatus = 'pending' | 'in_review' | 'approved' | 'void'
export type AllocationStatus = 'pending' | 'approved' | 'reverted'
export type LedgerDirection = 'income' | 'refund' | 'adjustment'
export type ContributionPeriod = 'all' | 'year' | 'quarter' | 'month'

export interface MilestoneTemplateNode {
  node_type: MilestoneNodeType
  title: string
  suggested_initial_points: number
  node_order: number
}

export interface MilestoneTemplateResponse {
  track: string
  is_temporary: boolean
  nodes: MilestoneTemplateNode[]
}

export interface MilestoneNodeIn {
  node_type: MilestoneNodeType
  title: string
  description?: string | null
  node_order: number
  initial_points: number
  target_date?: string | null
  planned_allocations?: Array<{
    user_id: string
    contribution_ratio: number
  }> | null
}

export interface MilestoneOut extends MilestoneNodeIn {
  id: string
  project_id: string
  final_points?: number | null
  adjustment_reason?: string | null
  status: MilestoneStatus
  requested_by?: string | null
  requested_at?: string | null
  approved_by?: string | null
  approved_at?: string | null
  created_at: string
}

export interface MilestoneListResponse {
  project_id: string
  items: MilestoneOut[]
}

export interface MilestoneSeedRequest {
  nodes: MilestoneNodeIn[]
}

export interface MilestoneSeedResponse {
  project_id: string
  created: number
  milestones: MilestoneOut[]
}

export interface AllocationOut {
  id: string
  milestone_id: string
  user_id: string
  contribution_ratio: string | number
  initial_points: number
  final_points?: number | null
  status: AllocationStatus
  proposed_by?: string | null
  proposed_at?: string | null
  reverted_at?: string | null
  revert_reason?: string | null
  created_at: string
}

export interface AllocationProposalRequest {
  allocations: Array<{
    user_id: string
    contribution_ratio: number
  }>
}

export interface MilestoneApprovalRequest {
  final_points: number
  adjustment_reason?: string | null
}

export interface MilestoneApprovalResponse {
  milestone: MilestoneOut
  allocations: AllocationOut[]
  ledger_entries_created: number
}

export interface AllocationRevertRequest {
  reason: string
}

export interface LedgerEntryOut {
  id: string
  user_id: string
  milestone_id?: string | null
  milestone_title?: string | null
  project_id?: string | null
  project_name?: string | null
  allocation_id?: string | null
  direction: LedgerDirection
  amount: number
  occurred_at: string
  reason: string
}

export interface LedgerHistoryResponse {
  items: LedgerEntryOut[]
  next_cursor?: string | null
}

export interface ContributionSummary {
  user_id: string
  period: ContributionPeriod
  total_points: number
  income_points: number
  refund_points: number
  adjustment_points: number
  milestone_count: number
}

export interface UserContributionResponse {
  summary: ContributionSummary
  recent_ledger: LedgerEntryOut[]
}

export interface AdminMilestoneListResponse {
  items: Array<MilestoneOut & { project_name?: string | null }>
}

export const getMilestoneTemplates = (track: string, isTemporary: boolean) =>
  request.get<unknown, MilestoneTemplateResponse>('/admin/milestones/templates', {
    params: { track, is_temporary: isTemporary },
  })

export const listAdminMilestones = (status?: MilestoneStatus) =>
  request.get<unknown, AdminMilestoneListResponse>('/admin/milestones', {
    params: status ? { status } : {},
  })

export const seedProjectMilestones = (projectId: string, payload: MilestoneSeedRequest) =>
  request.post<unknown, MilestoneSeedResponse>(`/projects/${projectId}/milestones/seed`, payload)

export const listProjectMilestones = (projectId: string, options: { mineOnly?: boolean } = {}) =>
  request.get<unknown, MilestoneListResponse>(`/projects/${projectId}/milestones`, {
    params: options.mineOnly ? { mine_only: true } : {},
  })

export const createMilestone = (projectId: string, payload: MilestoneNodeIn) =>
  request.post<unknown, MilestoneOut>(`/projects/${projectId}/milestones`, payload)

export const patchMilestone = (projectId: string, milestoneId: string, payload: Partial<MilestoneNodeIn>) =>
  request.patch<unknown, MilestoneOut>(`/projects/${projectId}/milestones/${milestoneId}`, payload)

export const deleteMilestone = (projectId: string, milestoneId: string) =>
  request.delete(`/projects/${projectId}/milestones/${milestoneId}`)

export const requestReview = (projectId: string, milestoneId: string) =>
  request.post<unknown, MilestoneOut>(`/projects/${projectId}/milestones/${milestoneId}/request-review`)

export const proposeAllocations = (projectId: string, milestoneId: string, payload: AllocationProposalRequest) =>
  request.post<unknown, { milestone_id: string; allocations: AllocationOut[] }>(
    `/projects/${projectId}/milestones/${milestoneId}/allocations`,
    payload,
  )

export const approveMilestone = (milestoneId: string, payload: MilestoneApprovalRequest) =>
  request.post<unknown, MilestoneApprovalResponse>(`/admin/milestones/${milestoneId}/approve`, payload)

export const revertAllocation = (allocationId: string, payload: AllocationRevertRequest) =>
  request.post<unknown, { allocation: AllocationOut; ledger_entry: LedgerEntryOut }>(
    `/admin/milestones/allocations/${allocationId}/revert`,
    payload,
  )

export const getMyContribution = (period: ContributionPeriod) =>
  request.get<unknown, UserContributionResponse>('/me/contribution', { params: { period } })

export const getMyLedger = (limit: number, cursor?: string | null) =>
  request.get<unknown, LedgerHistoryResponse>('/me/contribution/ledger', {
    params: { limit, ...(cursor ? { cursor } : {}) },
  })
