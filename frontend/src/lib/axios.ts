/**
 * lib/axios.ts — Axios 全局实例 (Rule 01-Stack-Frontend: 网络请求统一用 Axios 拦截器注入 Token)
 *
 * 从 Vue 版本 api/request.ts 1:1 迁移。
 */
import axios from 'axios'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
})

// ── 请求拦截器：注入 JWT ──
request.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('aipm_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  return config
})

// ── 响应拦截器：统一错误处理 ──
request.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('aipm_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default request
