<template>
  <section class="page" data-module="pointmachine-detail">
    <header class="page-head">
      <div>
        <h2>转辙机记录详情</h2>
        <p class="page-desc">
          <RouterLink :to="backLink" class="link">← 返回转辙机台账</RouterLink>
        </p>
      </div>
    </header>

    <div v-if="errorMessage" class="feedback-banner error" role="alert">
      <span>{{ errorMessage }}</span>
      <button class="btn" type="button" :disabled="loading" @click="load">{{ loading ? '重试中…' : '重试加载本记录' }}</button>
    </div>

    <template v-else-if="detail">
      <div class="position-banner" :class="{ 'is-out': !detail.in_scope }">
        <template v-if="detail.in_scope">
          当前台账按<strong>{{ detail.sort_label }}{{ detail.order === 'desc' ? '降序' : '升序' }}</strong
          >排列，本记录位于第 <strong>{{ detail.rank }}</strong> / {{ detail.total }} 条
          <span class="position-page">（第 {{ positionPage }} 页）</span>
        </template>
        <template v-else>
          本记录不在当前筛选结果内；以下位置是按
          <strong>{{ detail.sort_label }}{{ detail.order === 'desc' ? '降序' : '升序' }}</strong
          >在全量台账中给出的：第 <strong>{{ detail.rank }}</strong> / {{ detail.total }} 条
        </template>
      </div>

      <article class="detail-card">
        <h3 class="detail-title">{{ entryText('转辙机编号', '未填写编号') }}</h3>
        <dl class="detail-grid">
          <div v-for="field in fields" :key="field" class="detail-item">
            <dt>{{ field }}</dt>
            <dd :class="{ 'is-empty': isEmpty(entry[field]) }">{{ entryText(field) }}</dd>
          </div>
        </dl>
        <div class="detail-meta">
          <span>记录主键 id：{{ entry.id }}</span>
          <span>业务状态（status）：{{ entry.status ?? '—' }}</span>
        </div>
      </article>

      <nav class="detail-nav">
        <RouterLink
          v-if="detail.prev_id !== null"
          class="btn"
          :to="neighborLink(detail.prev_id)"
        >
          上一条（第 {{ detail.rank - 1 }} 条）
        </RouterLink>
        <span v-else class="nav-placeholder">已是第一条</span>
        <RouterLink :to="backLink" class="btn ghost">返回台账第 {{ query.page }} 页</RouterLink>
        <RouterLink
          v-if="detail.next_id !== null"
          class="btn"
          :to="neighborLink(detail.next_id)"
        >
          下一条（第 {{ detail.rank + 1 }} 条）
        </RouterLink>
        <span v-else class="nav-placeholder">已是最后一条</span>
      </nav>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'
import {
  PAGE_SIZE,
  parseRouteQuery,
  toDetailParams,
  toRouteQuery,
  type ListQuery,
} from './query'

interface DetailPayload {
  entry: Record<string, string | number | null>
  sort: string
  sort_label: string
  numeric: boolean
  order: 'asc' | 'desc'
  in_scope: boolean
  rank: number
  total: number
  prev_id: number | null
  next_id: number | null
}

const fields = ['所属道岔', '转辙机型号', '动作电流', '摩擦电流', '表示缺口', '润滑状态', '转辙机状态']

const route = useRoute()

const query = ref<ListQuery>(parseRouteQuery(route.query as Record<string, string | null>))
const detail = ref<DetailPayload | null>(null)
const loading = ref(false)
const errorMessage = ref('')

const entry = computed(() => detail.value?.entry ?? {})
const positionPage = computed(() => Math.max(1, Math.ceil((detail.value?.rank ?? 1) / PAGE_SIZE)))

const backLink = computed(() => ({
  name: 'pointmachine',
  query: toRouteQuery(query.value),
}))

function neighborLink(id: number) {
  return {
    name: 'pointmachine-detail',
    params: { id },
    query: toRouteQuery(query.value),
  }
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || String(value).trim() === ''
}

function entryText(field: string, fallback = '—'): string {
  const value = entry.value[field]
  return isEmpty(value) ? fallback : String(value)
}

async function load() {
  loading.value = true
  errorMessage.value = ''
  detail.value = null
  const id = route.params.id
  try {
    const response = await request(`/api/pointmachine/${id}/detail?${toDetailParams(query.value).toString()}`)
    if (!response.ok) {
      let text = `后端返回 ${response.status}`
      try {
        const body = await response.json()
        if (body?.detail) text = body.detail
      } catch {
        // 保留状态码说明
      }
      throw new Error(text)
    }
    detail.value = (await response.json()) as DetailPayload
  } catch (error) {
    const reason = error instanceof Error ? error.message : '网络异常'
    errorMessage.value = `转辙机记录（id=${id}，按当前排序第 ${query.value.page} 页附近）没有取到：${reason}。后端未确认前页面不臆造顺序。`
  } finally {
    loading.value = false
  }
}

watch(
  () => [route.params.id, route.query],
  async () => {
    query.value = parseRouteQuery(route.query as Record<string, string | null>)
    await load()
  },
  { immediate: true },
)
</script>

<style scoped>
.position-banner {
  border: 1px solid #abdfc1;
  background: #edf9f2;
  color: #17663a;
  border-radius: 6px;
  padding: 10px 14px;
  font-size: 13px;
  margin-bottom: 12px;
}
.position-banner.is-out {
  border-color: #f5d28a;
  background: #fef8e7;
  color: #92600a;
}
.position-page {
  color: var(--muted);
}
.detail-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 18px;
}
.detail-title {
  margin: 0 0 12px;
  font-size: 17px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 24px;
  margin: 0;
}
.detail-item dt {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 2px;
}
.detail-item dd {
  margin: 0;
  font-size: 14px;
}
.detail-item dd.is-empty {
  color: var(--muted);
}
.detail-meta {
  display: flex;
  gap: 20px;
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px dashed var(--border);
  font-size: 12px;
  color: var(--muted);
}
.detail-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 14px;
}
.nav-placeholder {
  color: var(--muted);
  font-size: 13px;
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
.feedback-banner.error {
  border-color: #f2b6b0;
  background: #fef3f2;
  color: #b42318;
}
.feedback-banner.error .btn {
  white-space: nowrap;
}
</style>
