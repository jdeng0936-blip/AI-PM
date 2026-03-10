import axios from 'axios'

const request = axios.create({
    baseURL: '/api/v1',   // Vite proxy → http://127.0.0.1:8001/api/v1
    timeout: 120_000,  // Gemini thinking model 需要 20-60s
    headers: { 'Content-Type': 'application/json' },
})

// ── 请求拦截器：注入 JWT ──
request.interceptors.request.use((config) => {
    const token = localStorage.getItem('aipm_token')
    if (token) {
        config.headers.Authorization = `Bearer ${token}`
    }
    return config
})

// ── 响应拦截器：统一错误处理 ──
request.interceptors.response.use(
    (res) => res.data,
    (err) => {
        if (err.response?.status === 401) {
            localStorage.removeItem('aipm_token')
            window.location.href = '/login'
        }
        return Promise.reject(err)
    }
)

export default request
