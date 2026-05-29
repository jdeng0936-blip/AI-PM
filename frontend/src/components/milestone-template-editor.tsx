'use client'

import { useEffect, useRef, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import {
  getMilestoneTemplates,
  type MilestoneNodeIn,
} from '@/api/milestones'

type Props = {
  track: string
  isTemporary: boolean
  value: MilestoneNodeIn[]
  onChange: (nodes: MilestoneNodeIn[]) => void
  disabled?: boolean
}

const emptyNode = (order: number): MilestoneNodeIn => ({
  node_type: 'custom',
  title: '',
  node_order: order,
  initial_points: 0,
  target_date: null,
})

export default function MilestoneTemplateEditor({
  track,
  isTemporary,
  value,
  onChange,
  disabled = false,
}: Props) {
  const [loading, setLoading] = useState(false)
  const onChangeRef = useRef(onChange)

  useEffect(() => {
    onChangeRef.current = onChange
  }, [onChange])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getMilestoneTemplates(track, isTemporary)
      .then((template) => {
        if (cancelled) return
        onChangeRef.current(template.nodes.map((node) => ({
          node_type: node.node_type,
          title: node.title,
          node_order: node.node_order,
          initial_points: node.suggested_initial_points,
          target_date: null,
        })))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [track, isTemporary])

  const updateNode = (index: number, patch: Partial<MilestoneNodeIn>) => {
    onChange(value.map((node, i) => (i === index ? { ...node, ...patch } : node)))
  }

  const removeNode = (index: number) => {
    onChange(value.filter((_, i) => i !== index).map((node, i) => ({ ...node, node_order: i + 1 })))
  }

  const addNode = () => {
    onChange([...value, emptyNode(value.length + 1)])
  }

  return (
    <div className="rounded-lg p-3 space-y-3" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs font-semibold" style={{ color: 'var(--color-text-primary)' }}>
          标准节点
          {loading && <span className="ml-2 font-normal" style={{ color: 'var(--color-text-secondary)' }}>加载中...</span>}
        </div>
        <button
          type="button"
          onClick={addNode}
          disabled={disabled}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs disabled:opacity-50"
          style={{ border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
        >
          <Plus size={12} />
          增加节点
        </button>
      </div>

      <div className="space-y-2">
        {value.map((node, index) => {
          const titleInvalid = !node.title.trim()
          const pointsInvalid = node.initial_points < 0
          return (
            <div key={`${node.node_order}-${index}`} className="grid grid-cols-[44px_1fr_72px_112px_32px] gap-2 items-center">
              <input
                type="number"
                value={node.node_order}
                min={1}
                disabled={disabled}
                onChange={(event) => updateNode(index, { node_order: Number(event.target.value) || index + 1 })}
                className="w-full rounded-md px-2 py-1.5 text-xs outline-none"
                style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
              />
              <input
                value={node.title}
                disabled={disabled}
                onChange={(event) => updateNode(index, { title: event.target.value })}
                className="w-full rounded-md px-2 py-1.5 text-xs outline-none"
                style={{
                  background: 'var(--color-bg-card)',
                  border: `1px solid ${titleInvalid ? '#ef4444' : 'var(--color-border-subtle)'}`,
                  color: 'var(--color-text-primary)',
                }}
              />
              <input
                type="number"
                value={node.initial_points}
                min={0}
                disabled={disabled}
                onChange={(event) => updateNode(index, { initial_points: Math.max(0, Number(event.target.value) || 0) })}
                className="w-full rounded-md px-2 py-1.5 text-xs outline-none"
                style={{
                  background: 'var(--color-bg-card)',
                  border: `1px solid ${pointsInvalid ? '#ef4444' : 'var(--color-border-subtle)'}`,
                  color: 'var(--color-text-primary)',
                }}
              />
              <input
                type="date"
                value={node.target_date || ''}
                disabled={disabled}
                onChange={(event) => updateNode(index, { target_date: event.target.value || null })}
                className="w-full rounded-md px-2 py-1.5 text-xs outline-none"
                style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
              />
              <button
                type="button"
                onClick={() => removeNode(index)}
                disabled={disabled || value.length <= 1}
                className="inline-flex h-8 w-8 items-center justify-center rounded-md disabled:opacity-40"
                style={{ border: '1px solid var(--color-border-subtle)', color: '#ef4444' }}
                aria-label="删除节点"
              >
                <Trash2 size={13} />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
