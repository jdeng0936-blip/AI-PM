import { createRouter, createWebHistory } from 'vue-router'

const routes = [
    { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { public: true } },
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
    { path: '/project/:id', name: 'ProjectDetail', component: () => import('../views/ProjectDetail.vue') },
    { path: '/reports', name: 'ReportList', component: () => import('../views/ReportList.vue') },
    { path: '/users', name: 'UserManagement', component: () => import('../views/UserManagement.vue') },
    { path: '/stats', name: 'SystemStats', component: () => import('../views/SystemStats.vue') },
    { path: '/simulate', name: 'SimulateReport', component: () => import('../views/SimulateReport.vue') },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

// 导航守卫：未登录跳转 Login
router.beforeEach((to) => {
    const token = localStorage.getItem('aipm_token')
    if (!to.meta.public && !token) {
        return { name: 'Login' }
    }
})

export default router
