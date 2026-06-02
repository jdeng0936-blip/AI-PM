'use client'

import { useEffect, useRef, useState } from 'react'
import { Plus, Trash2, Wand2 } from 'lucide-react'
import {
  getMilestoneTemplates,
  type MilestoneNodeIn,
} from '@/api/milestones'
import type { ProjectMemberInit } from '@/api/projects'

type Props = {
  track: string
  isTemporary: boolean
  value: MilestoneNodeIn[]
  onChange: (nodes: MilestoneNodeIn[]) => void
  members?: ProjectMemberInit[]
  disabled?: boolean
}

const emptyNode = (order: number): MilestoneNodeIn => ({
  node_type: 'custom',
  title: '',
  node_order: order,
  initial_points: 0,
  target_date: null,
})

const memberTrackLabel: Record<ProjectMemberInit['track'], string> = {
  hardware: '硬件',
  software: '软件',
  both: '全项目',
}

const nodeRoleHints: Partial<Record<MilestoneNodeIn['node_type'], string[]>> = {
  software_req: ['需求文档', '产品/需求', '文档/验收', '项目负责人', '软件研发'],
  software_mvp: ['软件研发', '前端研发', '后端研发', '研发', '项目负责人'],
  software_validate: ['功能测试', '测试/调试', '联调', '测试', '软件研发'],
  software_launch: ['交付上线', '客户验收', '文档/验收', '运维支持', '项目负责人'],
  hardware_review: ['方案设计', '硬件设计', '结构设计', 'ID', '项目负责人'],
  hardware_proto: ['ID', '工业设计', '结构设计', '硬件设计', 'BOM/采购', '硬件'],
  hardware_finalize: ['验收测试', '试产导入', '交付上线', '客户验收', '生产支持', '硬件'],
  temporary_done: ['项目负责人', '产品/需求', '需求文档', '研发', '设计', '测试/调试', '交付上线'],
}

function memberLabel(member: ProjectMemberInit) {
  const name = member.name || member.user_id.slice(0, 8)
  const role = member.role_in_project?.trim()
  return role ? `${name} · ${role}` : `${name} · ${memberTrackLabel[member.track]}`
}

function memberMatchText(member: ProjectMemberInit) {
  return [
    member.name,
    member.department,
    member.role_in_project,
    member.track === 'both'
      ? '全项目 项目负责人 产品/需求 需求文档 ID 工业设计 方案设计 研发 设计 软件 硬件 结构 测试 调试 交付上线 客户验收'
      : memberTrackLabel[member.track],
  ]
    .filter(Boolean)
    .join(' ')
}

function nodeKeywords(node: MilestoneNodeIn) {
  const hints = [...(nodeRoleHints[node.node_type] || [])]
  const text = `${node.title} ${node.description || ''}`
  if (text.includes('需求')) hints.unshift('需求文档', '产品/需求')
  if (text.includes('文档')) hints.unshift('文档/验收', '需求文档')
  if (text.includes('ID') || text.includes('工业设计')) hints.unshift('ID', '工业设计')
  if (text.includes('设计') || text.includes('方案') || text.includes('评审')) hints.unshift('方案设计', '设计')
  if (text.includes('测试') || text.includes('验证')) hints.unshift('功能测试', '测试')
  if (text.includes('调试') || text.includes('联调')) hints.unshift('联调', '测试/调试', '调试')
  if (text.includes('交付') || text.includes('上线') || text.includes('验收') || text.includes('发布')) {
    hints.unshift('交付上线', '客户验收', '文档/验收')
  }
  if (text.includes('硬件') || text.includes('PCB')) hints.unshift('硬件设计', '硬件')
  if (text.includes('BOM') || text.includes('采购')) hints.unshift('BOM/采购', '采购支持')
  if (text.includes('结构')) hints.unshift('结构设计', '结构')
  if (text.includes('软件') || text.includes('MVP') || text.includes('功能') || text.includes('研发')) {
    hints.unshift('软件研发', '研发', '软件')
  }
  if (text.includes('试产') || text.includes('生产')) hints.unshift('试产导入', '生产支持')
  return Array.from(new Set(hints))
}

function pickBestMember(node: MilestoneNodeIn, members: ProjectMemberInit[], fallbackIndex: number) {
  const keywords = nodeKeywords(node)
  const scores = members.map((member) => {
    const text = memberMatchText(member)
    const score = keywords.reduce((sum, keyword, index) => (
      text.includes(keyword) ? sum + Math.max(20 - index, 1) : sum
    ), 0)
    return { member, score }
  })
  const bestScore = Math.max(...scores.map((item) => item.score))
  const tied = scores.filter((item) => item.score === bestScore)
  return tied[fallbackIndex % tied.length]?.member || members[fallbackIndex % members.length]
}

export default function MilestoneTemplateEditor({
  track,
  isTemporary,
  value,
  onChange,
  members = [],
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

  const updateAssignee = (index: number, userId: string) => {
    updateNode(index, {
      planned_allocations: userId ? [{ user_id: userId, contribution_ratio: 1 }] : null,
    })
  }

  const matchMembersToNodes = () => {
    if (members.length === 0) return
    onChange(value.map((node, index) => {
      const member = pickBestMember(node, members, index)
      return {
        ...node,
        planned_allocations: member ? [{ user_id: member.user_id, contribution_ratio: 1 }] : null,
      }
    }))
  }

  return (
    <div className="rounded-lg p-3 space-y-3" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            工作节点分工
            {loading && <span className="ml-2 font-normal" style={{ color: 'var(--color-text-secondary)' }}>加载中...</span>}
          </div>
          <div className="mt-1 text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
            每行对应一段具体工作，立项后写入负责人和积分。
          </div>
        </div>
        <div className="flex items-center gap-2">
          {members.length > 0 && (
            <button
              type="button"
              onClick={matchMembersToNodes}
              disabled={disabled}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs disabled:opacity-50"
              style={{ border: '1px solid rgba(59,130,246,0.35)', color: 'var(--color-brand-blue)' }}
            >
              <Wand2 size={12} />
              匹配成员
            </button>
          )}
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
      </div>

      <div className="space-y-2">
        <div className="grid grid-cols-[44px_minmax(150px,1fr)_72px_112px_minmax(136px,0.9fr)_32px] gap-2 px-1 text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
          <span>序号</span>
          <span>工作内容</span>
          <span>积分</span>
          <span>截止</span>
          <span>负责人</span>
          <span />
        </div>
        {value.map((node, index) => {
          const titleInvalid = !node.title.trim()
          const pointsInvalid = node.initial_points < 0
          const assigneeId = node.planned_allocations?.[0]?.user_id || ''
          return (
            <div key={`${node.node_order}-${index}`} className="grid grid-cols-[44px_minmax(150px,1fr)_72px_112px_minmax(136px,0.9fr)_32px] gap-2 items-center">
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
              <select
                value={assigneeId}
                disabled={disabled || members.length === 0}
                onChange={(event) => updateAssignee(index, event.target.value)}
                className="w-full rounded-md px-2 py-1.5 text-xs outline-none disabled:opacity-60"
                style={{
                  background: 'var(--color-bg-card)',
                  border: `1px solid ${node.initial_points > 0 && !assigneeId && members.length > 0 ? '#d4a24e' : 'var(--color-border-subtle)'}`,
                  color: 'var(--color-text-primary)',
                }}
              >
                <option value="">{members.length > 0 ? '未指派负责人' : '先选项目成员'}</option>
                {members.map((member) => (
                  <option key={member.user_id} value={member.user_id}>
                    {memberLabel(member)}
                  </option>
                ))}
              </select>
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
              {node.description && (
                <div className="col-start-2 col-span-5 -mt-1 text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
                  分配建议：{node.description}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
