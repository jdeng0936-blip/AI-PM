/**
 * API 模块 — Phase 10 管理后台
 *
 * 对接后端:
 *  - /api/v1/admin/departments  (5 endpoints, T-1004)
 *  - /api/v1/admin/reports      (1 endpoint, T-1005)
 *
 * RBAC: 后端 require_role(admin, manager);前端入口同步收敛。
 */
import request from '@/api/request'

// ===== /admin/departments =====

export interface DepartmentOut {
  id: string
  name: string
  manager_id: string | null
  created_at: string | null
  updated_at: string | null
  created_by: string | null
  tenant_id: string
}

export interface DepartmentMember {
  id: string
  name: string
  role: 'admin' | 'manager' | 'employee'
  department: string
}

export interface DepartmentWithMembers extends DepartmentOut {
  members: DepartmentMember[]
}

export interface DepartmentIn {
  name: string
  manager_id: string | null
}

export const listDepartments = (): Promise<DepartmentOut[]> =>
  request.get('/admin/departments/') as unknown as Promise<DepartmentOut[]>

export const createDepartment = (payload: DepartmentIn): Promise<DepartmentOut> =>
  request.post('/admin/departments/', payload) as unknown as Promise<DepartmentOut>

export const getDepartmentWithMembers = (id: string): Promise<DepartmentWithMembers> =>
  request.get(`/admin/departments/${id}/members`) as unknown as Promise<DepartmentWithMembers>

export const updateDepartment = (id: string, payload: Partial<DepartmentIn>): Promise<DepartmentOut> =>
  request.patch(`/admin/departments/${id}`, payload) as unknown as Promise<DepartmentOut>

export const deleteDepartment = (id: string): Promise<void> =>
  request.delete(`/admin/departments/${id}`) as unknown as Promise<void>

// ===== /admin/reports =====

export type GroupBy = 'department' | 'project'

export interface ReportGroupRow {
  key: string
  report_count: number
  avg_score: number
  pass_count: number
  pass_rate: number
}

export interface GroupedReportsResponse {
  group_by: GroupBy
  start_date: string
  end_date: string
  project_id: string | null
  groups: ReportGroupRow[]
}

export interface GroupedReportsParams {
  group_by: GroupBy
  project_id?: string
  start_date?: string
  end_date?: string
}

export const getGroupedReports = (params: GroupedReportsParams): Promise<GroupedReportsResponse> =>
  request.get('/admin/reports/', { params }) as unknown as Promise<GroupedReportsResponse>
