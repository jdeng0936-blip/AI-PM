/**
 * frontend/src/lib/hooks/use-list-filters.ts — 通用列表筛选 Hook
 *
 * V2.4 Stage 1 全站列表筛选基础设施。
 *
 * 设计要点:
 *  - 一个 Hook 支持 5 种筛选控件:select / multi-select / range / date-range / boolean
 *  - filterSpec 是声明式的,UI 组件 (<FilterBar />) 根据 spec 自动渲染
 *  - URL params 双向同步(默认开),刷新不丢筛选状态;多列表同页面用 urlPrefix 防冲突
 *  - 直接用 window.history.replaceState 绕开 Next.js useSearchParams 的 Suspense 限制
 *  - 不引第三方依赖,~200 行可读代码
 *
 * Stage 2 衔接:返回的 filteredItems 数组可以直接喂给即将到来的
 * useMultiSelect(filteredItems) Hook,做批量软删的选中态管理。
 */
'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// ─── 类型 ──────────────────────────────────────────────────────────

export type FilterOption = { value: string; label: string }

export type FilterSpec =
  | { key: string; type: 'select'; label: string; options: FilterOption[] }
  | { key: string; type: 'multi-select'; label: string; options: FilterOption[] }
  | { key: string; type: 'range'; label: string; min: number; max: number; step?: number; unit?: string }
  | { key: string; type: 'date-range'; label: string }
  | { key: string; type: 'boolean'; label: string; trueLabel?: string; falseLabel?: string }

// 单个 filter 的当前值
export type FilterValue =
  | string                     // select
  | string[]                   // multi-select
  | [number, number]           // range (含两端)
  | [string, string]           // date-range (YYYY-MM-DD,含两端)
  | boolean                    // boolean
  | null                       // 未设置 / 已清空

export type FilterValues = Record<string, FilterValue>

export interface UseListFiltersOptions<T> {
  /** 是否把当前筛选同步到 URL query string,默认 true(刷新不丢) */
  syncToUrl?: boolean
  /** 多个列表同页面时用前缀防 key 冲突,如 'f_' / 'rep_' */
  urlPrefix?: string
  /**
   * 取 item 上某字段值的自定义 getter。
   * 默认 (item, key) => (item as any)[key]
   * 适用于嵌套字段,如 'department' 实际是 item.user.department
   */
  getValue?: (item: T, key: string) => unknown
}

export interface UseListFiltersResult<T> {
  filteredItems: T[]
  filters: FilterValues
  setFilter: (key: string, value: FilterValue) => void
  clearFilter: (key: string) => void
  clearAll: () => void
  /** 当前激活的 filter 数(用于 UI 上显示 badge) */
  activeCount: number
}

// ─── URL 序列化 ────────────────────────────────────────────────────

function serializeValue(spec: FilterSpec, value: FilterValue): string | null {
  if (value === null || value === undefined) return null
  switch (spec.type) {
    case 'select':
      return value ? String(value) : null
    case 'multi-select': {
      const arr = value as string[]
      return arr.length ? arr.join(',') : null
    }
    case 'range': {
      const [a, b] = value as [number, number]
      // 与 spec 边界相同就视为未筛
      if (a === spec.min && b === spec.max) return null
      return `${a}-${b}`
    }
    case 'date-range': {
      const [a, b] = value as [string, string]
      if (!a && !b) return null
      return `${a || ''}~${b || ''}`
    }
    case 'boolean':
      return typeof value === 'boolean' ? (value ? 'true' : 'false') : null
  }
}

function deserializeValue(spec: FilterSpec, raw: string): FilterValue | null {
  if (!raw) return null
  switch (spec.type) {
    case 'select':
      return spec.options.some((o) => o.value === raw) ? raw : null
    case 'multi-select': {
      const arr = raw.split(',').filter((v) => spec.options.some((o) => o.value === v))
      return arr.length ? arr : null
    }
    case 'range': {
      const [a, b] = raw.split('-').map(Number)
      if (Number.isFinite(a) && Number.isFinite(b)) {
        const lo = Math.max(spec.min, Math.min(a, b))
        const hi = Math.min(spec.max, Math.max(a, b))
        return [lo, hi]
      }
      return null
    }
    case 'date-range': {
      const [a, b] = raw.split('~')
      return [a || '', b || ''] as [string, string]
    }
    case 'boolean':
      if (raw === 'true') return true
      if (raw === 'false') return false
      return null
  }
}

function readUrl(spec: FilterSpec[], prefix: string): FilterValues {
  if (typeof window === 'undefined') return {}
  const params = new URLSearchParams(window.location.search)
  const out: FilterValues = {}
  for (const s of spec) {
    const raw = params.get(prefix + s.key)
    if (raw == null) continue
    const v = deserializeValue(s, raw)
    if (v !== null) out[s.key] = v
  }
  return out
}

function writeUrl(spec: FilterSpec[], prefix: string, values: FilterValues): void {
  if (typeof window === 'undefined') return
  const params = new URLSearchParams(window.location.search)
  for (const s of spec) {
    const v = values[s.key]
    const serialized = v == null ? null : serializeValue(s, v)
    if (serialized == null) params.delete(prefix + s.key)
    else params.set(prefix + s.key, serialized)
  }
  const qs = params.toString()
  const newUrl = window.location.pathname + (qs ? '?' + qs : '') + window.location.hash
  window.history.replaceState(null, '', newUrl)
}

// ─── 过滤逻辑 ──────────────────────────────────────────────────────

function matches(spec: FilterSpec, value: FilterValue, itemVal: unknown): boolean {
  if (value === null || value === undefined) return true
  switch (spec.type) {
    case 'select':
      return String(itemVal) === String(value)
    case 'multi-select': {
      const arr = value as string[]
      if (arr.length === 0) return true
      return arr.includes(String(itemVal))
    }
    case 'range': {
      const [a, b] = value as [number, number]
      const n = Number(itemVal)
      if (!Number.isFinite(n)) return false
      return n >= a && n <= b
    }
    case 'date-range': {
      const [a, b] = value as [string, string]
      const v = itemVal ? String(itemVal).slice(0, 10) : ''
      if (a && v < a) return false
      if (b && v > b) return false
      return true
    }
    case 'boolean':
      return Boolean(itemVal) === value
  }
}

// ─── Hook 主体 ────────────────────────────────────────────────────

export function useListFilters<T>(
  items: T[],
  spec: FilterSpec[],
  options: UseListFiltersOptions<T> = {},
): UseListFiltersResult<T> {
  const { syncToUrl = true, urlPrefix = 'f_', getValue } = options

  // spec 在组件生命周期内通常稳定;用 ref 拿最新版本,避免初始化时反复 readUrl
  const specRef = useRef(spec)
  specRef.current = spec

  // 初始化:如果开启 syncToUrl,从 URL 读初始值
  const [filters, setFilters] = useState<FilterValues>(() => {
    if (!syncToUrl) return {}
    return readUrl(spec, urlPrefix)
  })

  // filters 变化时回写 URL(只在开启时)
  useEffect(() => {
    if (!syncToUrl) return
    writeUrl(specRef.current, urlPrefix, filters)
  }, [filters, syncToUrl, urlPrefix])

  const setFilter = useCallback((key: string, value: FilterValue) => {
    setFilters((prev) => ({ ...prev, [key]: value }))
  }, [])

  const clearFilter = useCallback((key: string) => {
    setFilters((prev) => {
      if (!(key in prev)) return prev
      const next = { ...prev }
      delete next[key]
      return next
    })
  }, [])

  const clearAll = useCallback(() => {
    setFilters({})
  }, [])

  const filteredItems = useMemo(() => {
    const activeSpecs = spec.filter((s) => {
      const v = filters[s.key]
      if (v === null || v === undefined) return false
      if (Array.isArray(v) && (v as unknown[]).length === 0) return false
      return true
    })
    if (activeSpecs.length === 0) return items

    return items.filter((item) =>
      activeSpecs.every((s) => {
        const itemVal = getValue ? getValue(item, s.key) : (item as Record<string, unknown>)[s.key]
        return matches(s, filters[s.key], itemVal)
      }),
    )
  }, [items, spec, filters, getValue])

  const activeCount = useMemo(
    () =>
      spec.reduce((n, s) => {
        const v = filters[s.key]
        if (v === null || v === undefined) return n
        if (Array.isArray(v) && (v as unknown[]).length === 0) return n
        return n + 1
      }, 0),
    [filters, spec],
  )

  return { filteredItems, filters, setFilter, clearFilter, clearAll, activeCount }
}
