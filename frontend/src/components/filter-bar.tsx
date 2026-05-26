/**
 * frontend/src/components/filter-bar.tsx — 通用筛选条 UI
 *
 * V2.4 Stage 1 全站列表筛选的展示层;搭配 useListFilters Hook 使用。
 *
 * 设计:
 *  - 根据 spec 自动渲染对应控件(select / multi-select / range / date-range / boolean)
 *  - 选中项不在控件里"隐式"展示,而是显式渲染成 chip,鼠标 hover 显 X 单独移除
 *  - 右侧"清空全部"按钮,有任意 filter 激活时才显示
 *  - extra slot 留给 Stage 2 的批量操作栏(选中 N 条 / 批量删 / 批量禁用)
 *  - 视觉风格对齐现有 stat-card / 紫色 accent
 */
'use client'

import { useState } from 'react'
import { ChevronDown, X, Filter as FilterIcon, RotateCcw } from 'lucide-react'
import type { FilterSpec, FilterValue, FilterValues } from '@/lib/hooks/use-list-filters'

interface FilterBarProps {
  spec: FilterSpec[]
  filters: FilterValues
  setFilter: (key: string, value: FilterValue) => void
  clearFilter: (key: string) => void
  clearAll: () => void
  activeCount: number
  /** 右侧自定义区(Stage 2 用来挂批量操作栏) */
  extra?: React.ReactNode
  /** 整条 bar 隐藏控件区,只显示 chip(用于数据量很小时省空间);默认 false */
  chipOnly?: boolean
}

export default function FilterBar({
  spec,
  filters,
  setFilter,
  clearFilter,
  clearAll,
  activeCount,
  extra,
  chipOnly = false,
}: FilterBarProps) {
  return (
    <div
      className="rounded-xl p-3 mb-4 relative z-50"
      style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
    >
      {/* 控件区 */}
      {!chipOnly && (
        <div className="flex items-center gap-2 flex-wrap">
          <FilterIcon size={14} style={{ color: 'var(--color-text-secondary)' }} className="shrink-0" />
          {spec.map((s) => (
            <FilterControl
              key={s.key}
              spec={s}
              value={filters[s.key] ?? null}
              onChange={(v) => setFilter(s.key, v)}
            />
          ))}
          <div className="flex-1" />
          {activeCount > 0 && (
            <button
              onClick={clearAll}
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] transition-colors"
              style={{ color: '#a855f7', border: '1px solid rgba(168,85,247,0.4)' }}
              title="清空全部筛选"
            >
              <RotateCcw size={11} />
              清空全部 ({activeCount})
            </button>
          )}
          {extra && <div className="ml-2">{extra}</div>}
        </div>
      )}

      {/* 选中项 chip 区(有激活时才显示) */}
      {activeCount > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap mt-2 pt-2" style={{ borderTop: '1px dashed var(--color-border-subtle)' }}>
          <span className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>已筛:</span>
          {spec.map((s) => {
            const v = filters[s.key]
            if (v === null || v === undefined) return null
            if (Array.isArray(v) && (v as unknown[]).length === 0) return null
            return (
              <SelectedChip
                key={s.key}
                spec={s}
                value={v}
                onClear={() => clearFilter(s.key)}
              />
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── 单个控件 ────────────────────────────────────────────────────

function FilterControl({
  spec,
  value,
  onChange,
}: {
  spec: FilterSpec
  value: FilterValue
  onChange: (v: FilterValue) => void
}) {
  if (spec.type === 'select') {
    return (
      <select
        value={(value as string) || ''}
        onChange={(e) => onChange(e.target.value || (null as unknown as FilterValue))}
        className="px-2 py-1 rounded text-xs outline-none"
        style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
        title={spec.label}
      >
        <option value="">{spec.label}: 全部</option>
        {spec.options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    )
  }

  if (spec.type === 'multi-select') {
    return <MultiSelectControl spec={spec} value={(value as string[]) || []} onChange={onChange as (v: string[]) => void} />
  }

  if (spec.type === 'range') {
    const [lo, hi] = (value as [number, number]) || [spec.min, spec.max]
    return <RangeControl spec={spec} value={[lo, hi]} onChange={onChange as (v: [number, number]) => void} />
  }

  if (spec.type === 'date-range') {
    const [a, b] = (value as [string, string]) || ['', '']
    return (
      <div className="flex items-center gap-1 px-2 py-1 rounded text-xs"
        style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}>
        <span style={{ color: 'var(--color-text-secondary)' }}>{spec.label}:</span>
        <input
          type="date"
          value={a}
          onChange={(e) => onChange([e.target.value, b])}
          className="bg-transparent outline-none w-[120px]"
        />
        <span style={{ color: 'var(--color-text-secondary)' }}>→</span>
        <input
          type="date"
          value={b}
          onChange={(e) => onChange([a, e.target.value])}
          className="bg-transparent outline-none w-[120px]"
        />
      </div>
    )
  }

  // boolean — 三态:全部 / 是 / 否
  const cur = value === true ? 'true' : value === false ? 'false' : ''
  return (
    <select
      value={cur}
      onChange={(e) => {
        const v = e.target.value
        onChange(v === 'true' ? true : v === 'false' ? false : (null as unknown as FilterValue))
      }}
      className="px-2 py-1 rounded text-xs outline-none"
      style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
      title={spec.label}
    >
      <option value="">{spec.label}: 全部</option>
      <option value="true">{spec.trueLabel || '是'}</option>
      <option value="false">{spec.falseLabel || '否'}</option>
    </select>
  )
}

// ─── 多选下拉 ──────────────────────────────────────────────────────

function MultiSelectControl({
  spec,
  value,
  onChange,
}: {
  spec: Extract<FilterSpec, { type: 'multi-select' }>
  value: string[]
  onChange: (v: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const toggle = (v: string) => {
    if (value.includes(v)) onChange(value.filter((x) => x !== v))
    else onChange([...value, v])
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        className="flex items-center gap-1 px-2 py-1 rounded text-xs"
        style={{
          background: value.length ? 'rgba(168,85,247,0.12)' : 'var(--color-bg-secondary)',
          border: `1px solid ${value.length ? '#a855f7' : 'var(--color-border-subtle)'}`,
          color: 'var(--color-text-primary)',
        }}
        title={spec.label}
      >
        {spec.label}
        {value.length > 0 && (
          <span className="px-1 rounded-full text-[10px]" style={{ background: '#a855f7', color: '#fff' }}>
            {value.length}
          </span>
        )}
        <ChevronDown size={12} />
      </button>
      {open && (
        <div
          className="absolute left-0 top-full mt-1 z-20 min-w-[160px] rounded-lg py-1 shadow-xl"
          style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
        >
          {spec.options.map((o) => {
            const checked = value.includes(o.value)
            return (
              <label
                key={o.value}
                className="flex items-center gap-2 px-2 py-1.5 text-xs cursor-pointer hover:bg-white/5"
                style={{ color: 'var(--color-text-primary)' }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(o.value)}
                  className="cursor-pointer"
                />
                {o.label}
              </label>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ─── 区间 ───────────────────────────────────────────────────────────

function RangeControl({
  spec,
  value,
  onChange,
}: {
  spec: Extract<FilterSpec, { type: 'range' }>
  value: [number, number]
  onChange: (v: [number, number]) => void
}) {
  const [lo, hi] = value
  const unit = spec.unit || ''
  const active = lo > spec.min || hi < spec.max
  return (
    <div
      className="flex items-center gap-1.5 px-2 py-1 rounded text-xs"
      style={{
        background: active ? 'rgba(168,85,247,0.12)' : 'var(--color-bg-secondary)',
        border: `1px solid ${active ? '#a855f7' : 'var(--color-border-subtle)'}`,
        color: 'var(--color-text-primary)',
      }}
    >
      <span style={{ color: 'var(--color-text-secondary)' }}>{spec.label}:</span>
      <input
        type="number"
        value={lo}
        min={spec.min}
        max={hi}
        step={spec.step || 1}
        onChange={(e) => onChange([Number(e.target.value) || spec.min, hi])}
        className="bg-transparent outline-none w-[40px] text-right"
      />
      <span>~</span>
      <input
        type="number"
        value={hi}
        min={lo}
        max={spec.max}
        step={spec.step || 1}
        onChange={(e) => onChange([lo, Number(e.target.value) || spec.max])}
        className="bg-transparent outline-none w-[40px] text-right"
      />
      {unit && <span style={{ color: 'var(--color-text-secondary)' }}>{unit}</span>}
    </div>
  )
}

// ─── 已选 chip ─────────────────────────────────────────────────────

function SelectedChip({
  spec,
  value,
  onClear,
}: {
  spec: FilterSpec
  value: FilterValue
  onClear: () => void
}) {
  const text = formatChip(spec, value)
  if (!text) return null
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px]"
      style={{ background: 'rgba(168,85,247,0.18)', color: '#e9d5ff' }}
    >
      <span style={{ color: '#a855f7' }}>{spec.label}:</span>
      {text}
      <button onClick={onClear} className="hover:text-white transition-colors" title="移除此筛选">
        <X size={10} />
      </button>
    </span>
  )
}

function formatChip(spec: FilterSpec, value: FilterValue): string {
  if (value === null || value === undefined) return ''
  switch (spec.type) {
    case 'select':
      return spec.options.find((o) => o.value === value)?.label || String(value)
    case 'multi-select': {
      const arr = value as string[]
      if (!arr.length) return ''
      return arr.map((v) => spec.options.find((o) => o.value === v)?.label || v).join(' / ')
    }
    case 'range': {
      const [a, b] = value as [number, number]
      return `${a}~${b}${spec.unit || ''}`
    }
    case 'date-range': {
      const [a, b] = value as [string, string]
      if (!a && !b) return ''
      return `${a || '*'} → ${b || '*'}`
    }
    case 'boolean':
      return value ? spec.trueLabel || '是' : spec.falseLabel || '否'
  }
}
