/**
 * frontend/src/lib/hooks/use-multi-select.ts — 通用列表多选 Hook
 *
 * V2.4 Stage 2 全站批量软删的状态管理基础设施。
 * 设计与 useListFilters 配对:items 通常是 filteredItems(筛选后的可见项)
 *
 * 关键行为:
 *  - 切换 filter / 重新 fetch 数据(items 引用变)时自动清空选中态,
 *    避免"勾完日报后切换部门,以为是新一批 actually 还是旧的"
 *  - selectAll/isAllSelected 只针对"当前传入的 items"(不是后端全集)
 *  - 不引第三方依赖,~100 行可读代码
 */
'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'

export interface UseMultiSelectOptions<T> {
  /** 取 item 的唯一 id;默认 (item) => (item as any).id */
  idKey?: keyof T | ((item: T) => string)
}

export interface UseMultiSelectResult<T> {
  /** 当前选中的 id 集合(Set 便于 O(1) 判定) */
  selectedIds: Set<string>
  /** 选中条数 */
  selectedCount: number
  /** 当前选中的完整 item 列表(从 items 里映射出来) */
  selectedItems: T[]
  /** 切换某个 id 的选中态 */
  toggle: (id: string) => void
  /** 设置某个 id 的选中态(true=选中) */
  setSelected: (id: string, selected: boolean) => void
  /** 是否被选中 */
  isSelected: (id: string) => boolean
  /** 当前 items 是否全选(items 非空且全部都在 selectedIds 里) */
  isAllSelected: boolean
  /** 是否处于部分选中态(用于头部 checkbox 的 indeterminate 显示) */
  isIndeterminate: boolean
  /** 全选当前 items(覆盖式;之前其它选中也保留 — 因为 items 是 filtered 后的) */
  selectAll: () => void
  /** 清空所有选中 */
  clearAll: () => void
}

function defaultGetId<T>(idKey: UseMultiSelectOptions<T>['idKey']): (item: T) => string {
  if (typeof idKey === 'function') return idKey
  const key = (idKey as keyof T) || ('id' as keyof T)
  return (item: T) => String((item as Record<string, unknown>)[key as string])
}

export function useMultiSelect<T>(
  items: T[],
  options: UseMultiSelectOptions<T> = {},
): UseMultiSelectResult<T> {
  const getId = useMemo(() => defaultGetId<T>(options.idKey), [options.idKey])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // items 引用变化(filter 切换 / refetch)时清空选中态
  // 注意:这里依赖 items 引用,所以调用方不要每次 render 都新建数组
  // (useListFilters 的 filteredItems 走 useMemo,引用稳定)
  useEffect(() => {
    setSelectedIds(new Set())
  }, [items])

  const toggle = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const setSelected = useCallback((id: string, selected: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (selected) next.add(id)
      else next.delete(id)
      return next
    })
  }, [])

  const isSelected = useCallback((id: string) => selectedIds.has(id), [selectedIds])

  const selectAll = useCallback(() => {
    setSelectedIds(new Set(items.map(getId)))
  }, [items, getId])

  const clearAll = useCallback(() => {
    setSelectedIds(new Set())
  }, [])

  const { selectedCount, selectedItems, isAllSelected, isIndeterminate } = useMemo(() => {
    const visibleIds = items.map(getId)
    const visibleSelectedCount = visibleIds.filter((id) => selectedIds.has(id)).length
    const all = items.length > 0 && visibleSelectedCount === items.length
    const partial = visibleSelectedCount > 0 && visibleSelectedCount < items.length
    return {
      selectedCount: selectedIds.size,
      selectedItems: items.filter((item) => selectedIds.has(getId(item))),
      isAllSelected: all,
      isIndeterminate: partial,
    }
  }, [items, selectedIds, getId])

  return {
    selectedIds,
    selectedCount,
    selectedItems,
    toggle,
    setSelected,
    isSelected,
    isAllSelected,
    isIndeterminate,
    selectAll,
    clearAll,
  }
}
