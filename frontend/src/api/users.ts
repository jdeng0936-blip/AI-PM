import request from './request'

// ── 认证 API ────────────────────────────────────────────────
export function login(username: string, password: string) {
    return request.post('/auth/login', { username, password })
}

export function getMe() {
    return request.get('/auth/me')
}

export function changePassword(old_password: string, new_password: string) {
    return request.post('/auth/change-password', { old_password, new_password })
}

// ── 用户管理 API ────────────────────────────────────────────
export function getUsers(params: { page?: number; page_size?: number; search?: string } = {}) {
    return request.get('/users', { params })
}

export function createUser(data: {
    name: string
    wechat_userid: string
    phone?: string
    department?: string
    role?: string
    password?: string
}) {
    return request.post('/users', data)
}

export function updateUser(userId: string, data: {
    name?: string
    phone?: string
    department?: string
    role?: string
    is_active?: boolean
}) {
    return request.put(`/users/${userId}`, data)
}

export function deleteUser(userId: string) {
    return request.delete(`/users/${userId}`)
}

export function resetPassword(userId: string) {
    return request.post(`/users/${userId}/reset-password`)
}
