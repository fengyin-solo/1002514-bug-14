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

    <form class="filter-bar" @submit.prevent="applyFilters">
      <label class="filter-item">
        <span>转辙机编号</span>
        <input v-model="keywordInput" placeholder="按转辙机编号检索" />
      </label>
      <label class="filter-item">
        <span>转辙机状态</span>
        <select v-model="statusInput">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div v-if="notice" class="notice-bar" :class="notice.kind" role="alert">
      <span>{{ notice.text }}</span>
      <button v-if="notice.action" class="link" type="button" @click="notice.action">{{ notice.actionText }}</button>
    </div>

    <table class="data-table" :class="{ 'is-stale': loadError }">
      <thead>
        <tr>
          <th
            v-for="column in columns"
            :key="column"
            :class="{ sortable: SORTABLE.has(column), sorted: sortBy === column }"
          >
            <button
              v-if="SORTABLE.has(column)"
              type="button"
              class="sort-btn"
              :title="`按${column}排序`"
              @click="toggleSort(column)"
            >
              {{ column }}<span class="sort-mark">{{ sortMark(column) }}</span>
            </button>
            <template v-else>{{ column }}</template>
          </th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ displayValue(row, column) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
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
        <tr v-if="!loading && !rows.length && !loadError">
          <td :colspan="columns.length + 1" class="empty-state">暂无转辙机数据，可先登记转辙机</td>
        </tr>
        <tr v-if="loading">
          <td :colspan="columns.length + 1" class="empty-state">正在读取第 {{ page }} 页转辙机数据…</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条转辙机记录</span>
      <nav class="pager" aria-label="转辙机列表分页">
        <button class="btn" type="button" :disabled="page <= 1 || loading" @click="goPage(1)">首页</button>
        <button class="btn" type="button" :disabled="page <= 1 || loading" @click="goPage(page - 1)">上一页</button>
        <span class="pager-info">第 {{ page }} / {{ totalPages }} 页</span>
        <button class="btn" type="button" :disabled="page >= totalPages || loading" @click="goPage(page + 1)">下一页</button>
        <button class="btn" type="button" :disabled="page >= totalPages || loading" @click="goPage(totalPages)">末页</button>
      </nav>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface PagePayload {
  items: Row[]
  total: number
  page: number
  size: number
}

interface Notice {
  kind: 'error' | 'success'
  text: string
  action?: () => void
  actionText?: string
}

const ENDPOINT = '/api/pointmachine'
const PAGE_SIZE = 10
const columns = ["转辙机编号", "所属道岔", "转辙机型号", "动作电流", "摩擦电流", "表示缺口", "润滑状态", "转辙机状态"] as const
const actions = ["登记异常", "安排润滑", "办理更换"]
const statuses = ["正常", "电流偏高", "润滑不足", "已更换"]
const stats = [{"label": "正常转辙机", "value": 0}, {"label": "异常转辙机", "value": 0}, {"label": "待润滑转辙机", "value": 0}]

// 只有这三列支持排序，且必须与后端白名单一致；电流类按数值排序。
const SORTABLE = new Set<string>(["转辙机编号", "动作电流", "摩擦电流"])

const route = useRoute()
const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const loading = ref(false)
const loadError = ref('')
const notice = ref<Notice | null>(null)

// 筛选输入框里的值；真正参与请求的是 URL 上的 keyword/status，
// 这样点「查询」才生效，输入过程中不触发请求。
const keywordInput = ref('')
const statusInput = ref('')

const page = computed(() => readPositiveInt(route.query.page, 1))
const sortBy = computed(() => {
  const value = route.query.sort_by
  return typeof value === 'string' && SORTABLE.has(value) ? value : null
})
const sortDir = computed(() => (route.query.sort_dir === 'desc' ? 'desc' : 'asc'))
const keyword = computed(() => (typeof route.query.keyword === 'string' ? route.query.keyword : ''))
const status = computed(() => (typeof route.query.status === 'string' ? route.query.status : ''))

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function readPositiveInt(value: unknown, fallback: number): number {
  const n = Number.parseInt(String(value ?? ''), 10)
  return Number.isInteger(n) && n >= 1 ? n : fallback
}

// 把列表状态写进 URL：刷新、从详情返回、浏览器前进后退都能保持排序与定位。
async function syncQuery(patch: Record<string, string | number | null>) {
  const query: Record<string, string> = {}
  const merged = {
    keyword: keyword.value,
    status: status.value,
    page: page.value,
    sort_by: sortBy.value ?? '',
    sort_dir: sortBy.value ? sortDir.value : '',
    ...patch,
  }
  for (const [key, value] of Object.entries(merged)) {
    if (value !== '' && value !== null && value !== undefined) {
      query[key] = String(value)
    }
  }
  await router.replace({ name: 'pointmachine', query })
}

function buildListQuery(): string {
  const params = new URLSearchParams({
    page: String(page.value),
    size: String(PAGE_SIZE),
    sort_dir: sortDir.value,
  })
  if (keyword.value) params.set('keyword', keyword.value)
  if (status.value) params.set('status', status.value)
  if (sortBy.value) params.set('sort_by', sortBy.value)
  return params.toString()
}

async function loadPage() {
  loading.value = true
  loadError.value = ''
  const requestedPage = page.value
  try {
    const response = await request(`${ENDPOINT}?${buildListQuery()}`)
    if (!response.ok) {
      const detail = await readErrorDetail(response)
      throw new Error(detail || `后端返回 ${response.status}`)
    }
    const payload = (await response.json()) as PagePayload
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    const reason = error instanceof Error ? error.message : '网络异常'
    // 明确告诉用户是哪一页没取到，并提供就地重试入口；旧数据保留在表格里（置灰）。
    loadError.value = `第 ${requestedPage} 页转辙机数据没有取到：${reason}`
    notice.value = {
      kind: 'error',
      text: loadError.value,
      actionText: '重试本页',
      action: () => void loadPage(),
    }
  } finally {
    loading.value = false
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // 非 JSON 错误响应时忽略，退回状态码说明
  }
  return ''
}

function sortMark(column: string): string {
  if (sortBy.value !== column) return '↕'
  return sortDir.value === 'asc' ? '▲' : '▼'
}

async function toggleSort(column: string) {
  // 未排序 → 升序 → 降序 → 取消；换列默认先升序。切换排序后回到第一页。
  if (sortBy.value !== column) {
    await syncQuery({ sort_by: column, sort_dir: 'asc', page: 1 })
  } else if (sortDir.value === 'asc') {
    await syncQuery({ sort_dir: 'desc', page: 1 })
  } else {
    await syncQuery({ sort_by: null, sort_dir: null, page: 1 })
  }
}

async function goPage(target: number) {
  const next = Math.min(Math.max(target, 1), totalPages.value)
  if (next === page.value) return
  await syncQuery({ page: next })
}

function applyFilters() {
  void syncQuery({ keyword: keywordInput.value.trim(), status: statusInput.value, page: 1 })
}

async function resetFilters() {
  keywordInput.value = ''
  statusInput.value = ''
  await syncQuery({ keyword: '', status: '', page: 1 })
}

function exportRows() {
  const params = new URLSearchParams({ sort_dir: sortDir.value })
  if (sortBy.value) params.set('sort_by', sortBy.value)
  if (status.value) params.set('status', status.value)
  window.open(`${ENDPOINT}/export?${params.toString()}`, '_blank')
}

function openCreate() {
  notice.value = { kind: 'error', text: '转辙机登记入口尚未接入审批流' }
}

function displayValue(row: Row, column: string): string {
  const value = row[column]
  // 空字符串、null、undefined 都显示占位符，让「没填」与「正常数据」区分开，
  // 但记录本身绝不因为字段为空而从列表里消失。
  return value === null || value === undefined || String(value) === '' ? '—' : String(value)
}

// 详情链接带上列表当前的全部定位参数，详情据此算出与列表一致的位置。
function openDetail(row: Row) {
  void router.push({
    name: 'pointmachine-detail',
    params: { id: String(row.id) },
    query: route.query,
  })
}

async function runAction(action: string, row: Row) {
  notice.value = null
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload) {
      const detail = await readErrorDetail(response).catch(() => '')
      throw new Error(detail || '转辙机动作未生效，请稍后重试')
    }
    // 后端会对不允许的动作返回 ok=false + 明确原因，必须把结论反馈给用户。
    notice.value = {
      kind: payload.ok ? 'success' : 'error',
      text: payload.message || (payload.ok ? '操作已生效' : '操作未生效'),
    }
    if (payload.ok) await loadPage()
  } catch (error) {
    notice.value = {
      kind: 'error',
      text: error instanceof Error ? error.message : '转辙机操作失败',
      actionText: '重试',
      action: () => void runAction(action, row),
    }
  }
}

// 输入框跟随 URL（从详情返回时也能还原筛选条件）。
watch([keyword, status], ([kw, st]) => {
  keywordInput.value = kw
  statusInput.value = st
}, { immediate: true })

// 只有真正影响查询结果的 URL 参数变化才重新拉取，保持当前页与排序。
watch(
  () => [route.query.page, route.query.keyword, route.query.status, route.query.sort_by, route.query.sort_dir],
  () => { void loadPage() },
  { immediate: true },
)
</script>

<style scoped>
.sort-btn {
  border: none;
  background: none;
  padding: 0;
  font: inherit;
  color: inherit;
  cursor: pointer;
  display: inline-flex;
  gap: 4px;
  align-items: center;
}
.sortable .sort-mark { color: var(--muted); font-size: 11px; }
.sorted .sort-mark { color: var(--brand); }
.pager { display: flex; align-items: center; gap: 8px; }
.pager-info { color: #1f2937; }
.pager .btn[disabled] { opacity: 0.45; cursor: not-allowed; }
.data-table.is-stale { opacity: 0.55; }
.notice-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 10px;
  font-size: 13px;
}
.notice-bar.error { background: #fef3f2; border: 1px solid #fda29b; color: #b42318; }
.notice-bar.success { background: #ecfdf3; border: 1px solid #73e2a3; color: #067647; }
.filter-item select { padding: 4px 8px; }
</style>
