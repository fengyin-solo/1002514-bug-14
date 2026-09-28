<template>
  <section class="page" data-module="pointmachine-detail">
    <header class="page-head">
      <div>
        <h2>转辙机记录详情</h2>
        <p class="page-desc">
          当前为台账列表中第 <strong>{{ position ?? '—' }}</strong> / {{ total ?? '—' }} 条记录，
          排列方式与列表页完全一致。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="backToList">返回台账列表</button>
      </div>
    </header>

    <div v-if="errorMessage" class="notice-bar error" role="alert">
      <span>{{ errorMessage }}</span>
      <button class="link" type="button" @click="loadDetail">重试加载</button>
    </div>

    <div v-if="loading" class="detail-card">
      <p class="empty-state">正在读取转辙机记录详情…</p>
    </div>

    <article v-else-if="entry" class="detail-card">
      <dl class="detail-grid">
        <template v-for="field in fields" :key="field">
          <dt>{{ field }}</dt>
          <dd :class="{ missing: isMissing(entry[field]) }">{{ isMissing(entry[field]) ? '未填写' : entry[field] }}</dd>
        </template>
        <dt>记录ID</dt>
        <dd>{{ entry.id }}</dd>
      </dl>

      <p v-if="position === null" class="context-tip">
        该记录不属于列表当前筛选结果，因此没有在列表中的位置；返回列表可查看全部匹配记录。
      </p>

      <footer class="detail-nav">
        <button class="btn" type="button" :disabled="prevId === null" @click="goSibling(prevId)">
          ← 上一条（列表第 {{ position !== null && position > 1 ? position - 1 : '' }} 条）
        </button>
        <button class="btn" type="button" :disabled="nextId === null" @click="goSibling(nextId)">
          下一条（列表第 {{ position !== null ? position + 1 : '' }} 条）→
        </button>
      </footer>
    </article>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface DetailPayload {
  entry: Row
  position: number | null
  total: number
  prev_id: number | null
  next_id: number | null
}

const fields = ["转辙机编号", "所属道岔", "转辙机型号", "动作电流", "摩擦电流", "表示缺口", "润滑状态", "转辙机状态"]

const route = useRoute()
const router = useRouter()

const entry = ref<Row | null>(null)
const position = ref<number | null>(null)
const total = ref<number | null>(null)
const prevId = ref<number | null>(null)
const nextId = ref<number | null>(null)
const loading = ref(false)
const errorMessage = ref('')

const recordId = computed(() => Number.parseInt(String(route.params.id ?? ''), 10))

function isMissing(value: unknown): boolean {
  return value === null || value === undefined || String(value) === ''
}

// 详情请求原样带上列表的筛选与排序参数，后端按同一套口径定位，
// 因此这里显示的「第 N 条」、上一条/下一条都与列表逐行对得上。
function buildDetailQuery(): string {
  const allowed = ['keyword', 'status', 'sort_by', 'sort_dir']
  const params = new URLSearchParams()
  for (const key of allowed) {
    const value = route.query[key]
    if (typeof value === 'string' && value !== '') params.set(key, value)
  }
  return params.toString()
}

async function loadDetail() {
  if (!Number.isInteger(recordId.value) || recordId.value <= 0) {
    errorMessage.value = '转辙机记录编号无效，请从台账列表重新进入'
    entry.value = null
    return
  }
  loading.value = true
  errorMessage.value = ''
  try {
    const query = buildDetailQuery()
    const response = await request(`/api/pointmachine/${recordId.value}${query ? `?${query}` : ''}`)
    if (!response.ok) {
      let detail = ''
      try {
        const body = (await response.json()) as { detail?: unknown }
        if (typeof body.detail === 'string') detail = body.detail
      } catch {
        // 忽略非 JSON 错误体
      }
      throw new Error(detail || `详情接口返回 ${response.status}`)
    }
    const payload = (await response.json()) as DetailPayload
    entry.value = payload.entry
    position.value = payload.position
    total.value = payload.total
    prevId.value = payload.prev_id
    nextId.value = payload.next_id
  } catch (error) {
    const reason = error instanceof Error ? error.message : '网络异常'
    errorMessage.value = `转辙机记录（ID ${recordId.value}）详情没有取到：${reason}`
    entry.value = null
  } finally {
    loading.value = false
  }
}

function goSibling(id: number | null) {
  if (id === null) return
  void router.push({ name: 'pointmachine-detail', params: { id: String(id) }, query: route.query })
}

function backToList() {
  // 回到列表时保留页码、排序与筛选条件，列表会停在进入详情前的位置。
  void router.push({ name: 'pointmachine', query: route.query })
}

watch(() => route.params.id, () => { void loadDetail() }, { immediate: true })
</script>

<style scoped>
.detail-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 20px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 10px 16px;
  margin: 0;
}
.detail-grid dt { color: var(--muted); font-size: 13px; }
.detail-grid dd { margin: 0; font-size: 13px; }
.detail-grid dd.missing { color: var(--muted); }
.context-tip { margin-top: 14px; font-size: 12px; color: var(--muted); }
.detail-nav { display: flex; justify-content: space-between; margin-top: 18px; }
.detail-nav .btn[disabled] { opacity: 0.45; cursor: not-allowed; }
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
</style>
