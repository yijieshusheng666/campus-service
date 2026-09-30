<template>
  <div class="ann-page">
    <div class="page-header">
      <h2>平台公告</h2>
      <p class="sub">平台通知与重要安排，置顶公告优先展示</p>
    </div>

    <div v-loading="loading" class="ann-list">
      <el-empty v-if="!loading && items.length === 0" description="暂无公告" />
      <div
        v-for="item in items"
        :key="item.id"
        class="ann-card"
        @click="openDetail(item.id)"
      >
        <div class="ann-card-head">
          <el-tag v-if="item.is_pinned" type="danger" size="small" effect="dark">置顶</el-tag>
          <span class="ann-title">{{ item.title }}</span>
          <span class="ann-time">{{ fmtTime(item.created_at) }}</span>
        </div>
        <p class="ann-summary">{{ item.summary || '（摘要生成中…）' }}</p>
      </div>
    </div>

    <el-pagination
      v-if="total > pageSize"
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next"
      class="pager"
      @current-change="fetchList"
    />

    <el-dialog v-model="detailVisible" :title="detail?.title" width="640px">
      <div v-if="detail" class="detail-body">
        <div class="detail-meta">
          <span>{{ detail.publisher?.nickname || detail.publisher?.username }}</span>
          <span>{{ fmtTime(detail.created_at) }}</span>
        </div>
        <p class="detail-content">{{ detail.content }}</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listAnnouncements, getAnnouncement } from '@/api/announcement'

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(false)

const detailVisible = ref(false)
const detail = ref(null)

function fmtTime(t) {
  return t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : ''
}

async function fetchList() {
  loading.value = true
  try {
    const res = await listAnnouncements({ page: page.value, page_size: pageSize })
    items.value = res.data.items
    total.value = res.data.total
  } catch (e) {
    /* 401 由拦截器处理 */
  } finally {
    loading.value = false
  }
}

async function openDetail(id) {
  try {
    const res = await getAnnouncement(id)
    detail.value = res.data
    detailVisible.value = true
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '公告加载失败')
  }
}

onMounted(fetchList)
</script>

<style scoped>
.ann-page { max-width: 860px; margin: 0 auto; padding: 24px 16px; }
.page-header h2 { margin: 0; font-size: 20px; color: #1d2129; }
.page-header .sub { margin: 6px 0 18px; font-size: 13px; color: #86909c; }

.ann-card {
  background: #fff;
  border: 1px solid #eef0f4;
  border-radius: 10px;
  padding: 14px 18px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.ann-card:hover { border-color: #ffb98a; box-shadow: 0 4px 14px rgba(255, 107, 0, 0.08); }
.ann-card-head { display: flex; align-items: center; gap: 8px; }
.ann-title { font-size: 15px; font-weight: 600; color: #1d2129; flex: 1; }
.ann-time { font-size: 12px; color: #a0a5b2; }
.ann-summary {
  margin: 8px 0 0;
  font-size: 13px;
  color: #5a6070;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pager { justify-content: center; margin-top: 16px; }

.detail-meta { display: flex; gap: 14px; font-size: 12px; color: #a0a5b2; margin-bottom: 12px; }
.detail-content { font-size: 14px; line-height: 1.8; color: #1d2129; white-space: pre-wrap; }
</style>
