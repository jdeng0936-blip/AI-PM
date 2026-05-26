/**
 * frontend/src/components/list-action-bar.tsx — 批量操作浮动栏
 *
 * V2.4 Stage 2 全站批量软删 UI。配合 useMultiSelect Hook 使用。
 *
 * 设计:
 *  - selectedCount > 0 才显示;sticky top-2 紫色 accent
 *  - 内容:"已选 N 项 · [清除选择] · {actions 业务方塞按钮}"
 *  - 不接触 FilterBar(独立 sticky);如果要嵌入 FilterBar 的 extra slot,
 *    用 ListActionBarInline 紧凑版
 *  - children 提供业务按钮(批量删 / 批量归档 / 批量禁用 ...)
 */
'use client'

import { X } from 'lucide-react'

export interface ListActionBarProps {
  selectedCount: number
  onClear: () => void
  /** 业务按钮区(批量删除 / 归档 / 禁用 ...) */
  children?: React.ReactNode
  /** 选中信息附加描述(如"含 3 个临时项目 / 2 个主干") */
  hint?: string
}

export default function ListActionBar({
  selectedCount,
  onClear,
  children,
  hint,
}: ListActionBarProps) {
  if (selectedCount === 0) return null
  return (
    <div
      className="sticky top-2 z-40 rounded-xl px-4 py-2.5 mb-4 flex items-center gap-3 shadow-lg backdrop-blur"
      style={{
        background: 'rgba(168,85,247,0.18)',
        border: '1px solid #a855f7',
        color: 'var(--color-text-primary)',
      }}
    >
      <span className="text-sm font-medium" style={{ color: '#e9d5ff' }}>
        已选 <span className="px-1.5 py-0.5 rounded text-xs" style={{ background: '#a855f7', color: '#fff' }}>{selectedCount}</span> 项
      </span>
      {hint && (
        <span className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
          {hint}
        </span>
      )}
      <button
        onClick={onClear}
        className="flex items-center gap-1 px-2 py-1 rounded text-[11px] transition-colors"
        style={{ color: '#e9d5ff', border: '1px solid rgba(233,213,255,0.3)' }}
        title="清除选择"
      >
        <X size={11} />
        清除
      </button>
      <div className="flex-1" />
      {children}
    </div>
  )
}
