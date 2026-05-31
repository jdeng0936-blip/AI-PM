/**
 * frontend/src/lib/project-track.ts — 项目轨道(track)枚举的统一映射
 *
 * 与后端 backend/app/models/project.py:ProjectTrack 保持同步。
 *
 * 设计:
 *  - 主干项目(is_temporary=false)在 UI 上 3 选 1:dual / software / hardware
 *  - 临时工单项目(is_temporary=true)在 UI 上 2 选 1:support / other
 *  - 严格分隔,弹窗按 is_temporary 切换选项列表
 *  - trackLabel() 兜底显示 raw value,避免新增 enum 未同步时白屏
 */

export const TRACK_LABELS: Record<string, string> = {
  dual: '软硬协同',
  software: '纯软件',
  hardware: '纯硬件',
  support: '日常支撑',
  other: '其它临时',
}

export const MAIN_TRACK_OPTIONS = ['dual', 'software', 'hardware'] as const
export const TEMP_TRACK_OPTIONS = ['support', 'other'] as const

export type MainTrack = (typeof MAIN_TRACK_OPTIONS)[number]
export type TempTrack = (typeof TEMP_TRACK_OPTIONS)[number]
export type ProjectTrack = MainTrack | TempTrack

/** 把 track 字符串翻译成中文显示;未知值兜底原值;空值显示 — */
export const trackLabel = (t?: string | null): string => {
  if (!t) return '—'
  return TRACK_LABELS[t] || t
}

/** 是否为临时工单专用轨道 */
export const isTempTrack = (t?: string | null): boolean =>
  !!t && (TEMP_TRACK_OPTIONS as readonly string[]).includes(t)
