import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
    const token = ref(localStorage.getItem('aipm_token') || '')
    const userName = ref(localStorage.getItem('aipm_user_name') || '')
    const userRole = ref(localStorage.getItem('aipm_user_role') || '')

    const isLoggedIn = computed(() => !!token.value)
    const isAdmin = computed(() => userRole.value === 'admin')

    function login(jwt: string, name: string, role: string = 'employee') {
        token.value = jwt
        userName.value = name
        userRole.value = role
        localStorage.setItem('aipm_token', jwt)
        localStorage.setItem('aipm_user_name', name)
        localStorage.setItem('aipm_user_role', role)
    }

    function logout() {
        token.value = ''
        userName.value = ''
        userRole.value = ''
        localStorage.removeItem('aipm_token')
        localStorage.removeItem('aipm_user_name')
        localStorage.removeItem('aipm_user_role')
    }

    return { token, userName, userRole, isLoggedIn, isAdmin, login, logout }
})

