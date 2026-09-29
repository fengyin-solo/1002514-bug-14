<template>
  <section class="page" data-module="pointmachine">
    <header class="page-head">
      <div>
        <h2>转辙机管理</h2>
        <p class="page-desc">维护转辙机，围绕转辙机编号、所属道岔、转辙机型号、动作电流做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记转辙机</button>
        <button class="btn" type="button" @click="exportRows">导出转辙机清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="search">
      <label class="filter-item">
        <span>转辙机编号</span>
        <input v-model="filters.keyword" placeholder="按转辙机编号检索" />
      </label>
      <label class="filter-item">
        <span>所属道岔</span>
        <input v-model="filters.turnout" placeholder="按所属道岔检索" />
      </label>
      <label class="filter-item">
        <span>转辙机型号</span>
        <input v-model="filters.model" placeholder="按转辙机型号检索" />
      </label>
      <label class="filter-item">
        <span>转辙机状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="item in STATUS_OPTIONS" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="feedback" class="feedback-banner" :class="feedback.kind" role="status">
      <span>{{ feedback.text }}</span>
    </div>
    <div v-if="errorMessage" class="feedback-banner error" role="alert">
      <span>{{ errorMessage }}</span>
      <button class="btn" type="button" :disabled="loading" @click="load">{{ loading ? '重试中…' : '重试本页' }}</button>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column.key">
            <button
              v-if="column.sortable"
              type="button"
              class="sort-header"
              :aria-label="`按${column.label}排序`"
              @click="toggleSort(column.key)"
            >
              {{ column.label }}
              <span class="sort-arrow">{{ sortArrow(column.key) }}</span>
            </button>
            <template v-else>{{ column.label }}</template>
          </th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column.key">
            <RouterLink
              v-if="column.key === 'code'"
              class="link"
              :to="{ name: 'pointmachine-detail', params: { id: row.id }, query: toRouteQuery(query) }"
            >
              {{ cellText(row, column.key) }}
            </RouterLink>
            <template v-else>{{ cellText(row, column.key) }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!loading && !rows.length && !errorMessage">
          <td :colspan="columns.length + 1" class="empty-state">暂无转辙机数据，可先登记转辙机</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot pager">
      <div class="pager-info">
        <span>共 {{ total }} 条转辙机记录</span>
        <span v-if="loading" class="loading-text">正在读取{{ pageHint }}…</span>
      </div>
      <div class="pager-controls">
        <button class="btn" type="button" :disabled="query.page <= 1 || loading" @click="gotoPage(query.page - 1)">上一页</button>
        <span>第 {{ query.page }} / {{ totalPages }} 页</span>
        <button class="btn" type="button" :disabled="query.page >= totalPages || loading" @click="gotoPage(query.page + 1)">下一页</button>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import {
  PAGE_SIZE,
  STATUS_OPTIONS,
  isSortKey,
  parseRouteQuery,
  sortLabel,
  toListParams,
  toRouteQuery,
  type ListQuery,
  type SortKey,
} from './query'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/pointmachine'

const columns: ReadonlyArray<{ key: string; label: string; sortable: boolean }> = [
  { key: 'code', label: '转辙机编号', sortable: true },
  { key: 'turnout', label: '所属道岔', sortable: false },
  { key: 'model', label: '转辙机型号', sortable: false },
  { key: 'action', label: '动作电流', sortable: true },
  { key: 'friction', label: '摩擦电流', sortable: true },
  { key: 'gap', label: '表示缺口', sortable: false },
  { key: 'lubrication', label: '润滑状态', sortable: false },
  { key: 'state', label: '转辙机状态', sortable: false },
]
// 后端返回字段名（中文列名）与表格列的映射
const FIELD_NAMES: Record<string, string> = {
  code: '转辙机编号',
  turnout: '所属道岔',
  model: '转辙机型号',
  action: '动作电流',
  friction: '摩擦电流',
  gap: '表示缺口',
  lubrication: '润滑状态',
  state: '转辙机状态',
}
const actions = ['登记异常', '安排润滑', '办理更换']
const stats = [{ label: '正常转辙机', value: 0 }, { label: '异常转辙机', value: 0 }, { label: '待润滑转辙机', value: 0 }]

const route = useRoute()
const router = useRouter()

const query = ref<ListQuery>(parseRouteQuery(route.query as Record<string, string | null>))
const filters = ref({
  keyword: query.value.keyword,
  turnout: query.value.turnout,
  model: query.value.model,
  status: query.value.status,
})
const rows = ref<Row[]>([])
const total = ref(0)
const loading = ref(false)
const errorMessage = ref('')
const feedback = ref<{ kind: 'success' | 'error'; text: string } | null>(null)
let requestToken = 0

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const orderText = computed(() => `${sortLabel(query.value.sort)}${query.value.order === 'desc' ? '降序' : '升序'}`)
const pageHint = computed(() => `第 ${query.value.page} 页（按${orderText.value}）`)

function cellText(row: Row, key: string): string {
  const value = row[FIELD_NAMES[key]]
  if (value === null || value === undefined || String(value).trim() === '') {
    return key === 'code' ? '未填写编号' : '—'
  }
  return String(value)
}

function sortArrow(key: string): string {
  if (!isSortKey(key) || query.value.sort !== key) return '↕'
  return query.value.order === 'desc' ? '▼' : '▲'
}

/** 把筛选/排序/页码写进 URL；与当前一致时直接取数，避免重复请求。 */
async function commitQuery(next: ListQuery) {
  const target = toRouteQuery(next)
  const same = JSON.stringify(route.query) === JSON.stringify(target)
  if (same) {
    await load()
    return
  }
  await router.replace({ name: 'pointmachine', query: target })
}

async function gotoPage(page: number) {
  await commitQuery({ ...query.value, page })
}

async function toggleSort(key: string) {
  if (!isSortKey(key)) return
  const order = query.value.sort === key && query.value.order === 'asc' ? 'desc' : 'asc'
  // 换一种排列后从第一页开始，避免落在越界页或错位页。
  await commitQuery({ ...query.value, sort: key, order, page: 1 })
}

async function search() {
  await commitQuery({
    ...query.value,
    keyword: filters.value.keyword.trim(),
    turnout: filters.value.turnout.trim(),
    model: filters.value.model.trim(),
    status: filters.value.status,
    page: 1,
  })
}

async function resetFilters() {
  filters.value = { keyword: '', turnout: '', model: '', status: '' }
  await commitQuery({ ...query.value, keyword: '', turnout: '', model: '', status: '', page: 1 })
}

async function load() {
  // 防并发：后发的请求才算数，避免慢响应把早响应的顺序盖掉。
  const token = ++requestToken
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${toListParams(query.value).toString()}`)
    if (!response.ok) {
      let detail = `后端返回 ${response.status}`
      try {
        const body = await response.json()
        if (body?.detail) detail = body.detail
      } catch {
        // 错误体不是 JSON 时保留状态码说明
      }
      throw new Error(detail)
    }
    const payload = await response.json()
    if (token !== requestToken) return
    rows.value = payload.items ?? []
    total.value = payload.total ?? 0
    // 后端若把页码纠正了（越界等），以服务端结论为准同步定位。
    if (typeof payload.page === 'number' && payload.page !== query.value.page) {
      query.value = { ...query.value, page: payload.page }
    }
  } catch (error) {
    if (token !== requestToken) return
    const reason = error instanceof Error ? error.message : '网络异常'
    errorMessage.value = `第 ${query.value.page} 页（按${orderText.value}）没有取到数据：${reason}。请检查后端服务后重试本页。`
  } finally {
    if (token === requestToken) {
      loading.value = false
    }
  }
}

async function runAction(action: string, row: Row) {
  feedback.value = null
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    let body: { ok?: boolean; message?: string } = {}
    try {
      body = await response.json()
    } catch {
      // 后端没给出结构化结论时按失败处理，不假装操作已生效
    }
    if (!response.ok || body.ok === false) {
      feedback.value = { kind: 'error', text: body.message || `「${action}」未被后端确认（${response.status}），记录未改动` }
      return
    }
    // 以后端返回的结论为准：成功才刷新当前页当前排序
    feedback.value = { kind: 'success', text: body.message || `「${action}」已生效` }
    await load()
  } catch (error) {
    const reason = error instanceof Error ? error.message : '网络异常'
    feedback.value = { kind: 'error', text: `「${action}」请求未送达后端：${reason}，记录未改动，可稍后重试` }
  }
}

function exportRows() {
  const params = new URLSearchParams({ sort: query.value.sort, order: query.value.order })
  window.open(`${ENDPOINT}/export?${params.toString()}`, '_blank')
}

function openCreate() {
  feedback.value = { kind: 'error', text: '转辙机登记入口尚未接入审批流，暂不能提交' }
}

// 浏览器前进/后退、从详情返回：URL 变化即按其中的页码与排序重新取数，定位保持。
watch(
  () => route.query,
  (next) => {
    query.value = parseRouteQuery(next as Record<string, string | null>)
    filters.value = {
      keyword: query.value.keyword,
      turnout: query.value.turnout,
      model: query.value.model,
      status: query.value.status,
    }
    void load()
  },
)

onMounted(load)
</script>

<style scoped>
.page-actions {
  display: flex;
  gap: 8px;
}
.filter-item select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 13px;
  min-width: 120px;
}
.sort-header {
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  font-weight: inherit;
  color: inherit;
  cursor: pointer;
}
.sort-arrow {
  color: var(--muted);
  font-size: 11px;
  margin-left: 2px;
}
.pager {
  align-items: center;
}
.pager-info,
.pager-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pager-controls .btn[disabled] {
  opacity: 0.5;
  cursor: not-allowed;
}
.loading-text {
  color: var(--brand);
}
.feedback-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid;
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 10px;
  font-size: 13px;
}
.feedback-banner.success {
  border-color: #abdfc1;
  background: #edf9f2;
  color: #17663a;
}
.feedback-banner.error {
  border-color: #f2b6b0;
  background: #fef3f2;
  color: #b42318;
}
.feedback-banner.error .btn {
  white-space: nowrap;
}
</style>
