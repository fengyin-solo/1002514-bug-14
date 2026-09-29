/** 转辙机台账的查询口径：列表页与详情页共用，避免两边各拼一套参数、给出两套顺序。 */

export const PAGE_SIZE = 10
export const STATUS_OPTIONS = ['正常', '电流偏高', '润滑不足', '已更换']

export type SortKey = 'code' | 'action' | 'friction'
export type SortOrder = 'asc' | 'desc'

/** 可排序列与后端字段的对应；动作电流、摩擦电流由后端按数值比较。 */
export const SORT_OPTIONS: ReadonlyArray<{ key: SortKey; label: string; numeric: boolean }> = [
  { key: 'code', label: '转辙机编号', numeric: false },
  { key: 'action', label: '动作电流', numeric: true },
  { key: 'friction', label: '摩擦电流', numeric: true },
]

export interface ListQuery {
  keyword: string
  turnout: string
  model: string
  status: string
  sort: SortKey
  order: SortOrder
  page: number
}

const DEFAULT_QUERY: ListQuery = {
  keyword: '',
  turnout: '',
  model: '',
  status: '',
  sort: 'code',
  order: 'asc',
  page: 1,
}

export function isSortKey(value: string | null): value is SortKey {
  return value === 'code' || value === 'action' || value === 'friction'
}

/** 从路由 query 还原筛选/排序/页码：刷新或从详情返回后定位保持不变。 */
export function parseRouteQuery(search: Record<string, string | null>): ListQuery {
  const sort = search.sort ?? ''
  const order = search.order ?? ''
  const page = Number(search.page)
  return {
    keyword: search.keyword ?? '',
    turnout: search.turnout ?? '',
    model: search.model ?? '',
    status: search.status ?? '',
    sort: isSortKey(sort) ? sort : DEFAULT_QUERY.sort,
    order: order === 'desc' ? 'desc' : 'asc',
    page: Number.isInteger(page) && page > 0 ? page : 1,
  }
}

/** 列表查询参数，带固定分页大小；空条件不下发，保持 URL 干净。 */
export function toListParams(query: ListQuery): URLSearchParams {
  const params = new URLSearchParams()
  if (query.keyword) params.set('keyword', query.keyword)
  if (query.turnout) params.set('turnout', query.turnout)
  if (query.model) params.set('model', query.model)
  if (query.status) params.set('status', query.status)
  params.set('sort', query.sort)
  params.set('order', query.order)
  params.set('page', String(query.page))
  params.set('size', String(PAGE_SIZE))
  return params
}

/** 路由 query：完整保留当前定位（页码、排序、筛选），用于翻页与跳转详情。 */
export function toRouteQuery(query: ListQuery): Record<string, string> {
  const route: Record<string, string> = {
    sort: query.sort,
    order: query.order,
    page: String(query.page),
  }
  if (query.keyword) route.keyword = query.keyword
  if (query.turnout) route.turnout = query.turnout
  if (query.model) route.model = query.model
  if (query.status) route.status = query.status
  return route
}

/** 详情接口参数：沿用列表的筛选与排序（含页码，便于返回时落回原来的页）。 */
export function toDetailParams(query: ListQuery): URLSearchParams {
  return new URLSearchParams(toRouteQuery(query))
}

export function sortLabel(key: SortKey): string {
  return SORT_OPTIONS.find((item) => item.key === key)?.label ?? key
}
