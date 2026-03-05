/**
 * useNotifications — 侧边栏通知徽标数据源
 *
 * 轮询晨报 API，提取：
 *   - alertCount: 当日管理预警数
 *   - failCount: 当日退回日报数
 *   - missingCount: 当日未汇报人数
 */
import { ref, onMounted, onUnmounted } from 'vue'
import { getMorningBriefing } from '../api/dashboard'

const alertCount = ref(0)
const failCount = ref(0)
const missingCount = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
let initialized = false

async function refresh() {
    try {
        const data = await getMorningBriefing() as any
        const stats = data?.stats || {}
        alertCount.value = data?.alerts?.length || 0
        failCount.value = stats.fail_count || 0
        missingCount.value = data?.missing_members?.length || 0
    } catch {
        // Silently fail — badges just show 0
    }
}

export function useNotifications() {
    if (!initialized) {
        initialized = true
        refresh()
        timer = setInterval(refresh, 60_000) // 每分钟刷新
    }

    onUnmounted(() => {
        // Only cleanup if component tree unmounts (rare for App.vue)
    })

    return { alertCount, failCount, missingCount, refresh }
}
