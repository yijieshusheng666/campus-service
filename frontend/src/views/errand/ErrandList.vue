<template>
  <div class="page">
    <div class="page-header">
      <h2>快递代拿</h2>
      <el-button type="primary" @click="$router.push({ name: 'ErrandPublish' })">发布需求</el-button>
    </div>

    <el-tabs v-model="activeTab" @tab-change="load">
      <el-tab-pane label="接单大厅" name="all" />
      <el-tab-pane label="我发布的" name="published" />
      <el-tab-pane label="我接的" name="accepted" />
    </el-tabs>

    <el-empty v-if="!loading && !items.length" description="暂无数据" />
    <el-card v-for="e in items" :key="e.id" class="item" shadow="hover" @click="goDetail(e)">
      <div class="item-row">
        <div class="route">
          <span class="loc">{{ e.pickup_location }}</span>
          <el-icon class="arrow"><ArrowRight /></el-icon>
          <span class="loc">{{ e.dropoff_location }}</span>
        </div>
        <div class="reward">¥{{ e.reward }}</div>
      </div>
      <div class="meta">
        <el-tag :type="statusType(e.status)" size="small">{{ statusText(e.status) }}</el-tag>
        <el-tag v-if="isMine(e)" type="warning" size="small" effect="plain">我的发布</el-tag>
        <span class="info">{{ e.package_info }}</span>
        <span v-if="e.deadline" class="info">期望 {{ formatTime(e.deadline) }} 前</span>
        <span class="info publisher">发布者：{{ e.publisher?.nickname || e.publisher?.username }}</span>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import { listErrands } from '@/api/errand'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const items = ref([])
const loading = ref(false)
const activeTab = ref('all')

const isMine = (e) => e.user_id === auth.user?.id

const load = async () => {
  loading.value = true
  try {
    const res = await listErrands(activeTab.value)
    items.value = res.data
  } finally {
    loading.value = false
  }
}

const goDetail = (e) => router.push({ name: 'ErrandDetail', params: { id: e.id } })

const STATUS = {
  pending: { text: '待接单', type: 'success' },
  accepted: { text: '配送中', type: 'warning' },
  delivered: { text: '已送达', type: 'primary' },
  completed: { text: '已完成', type: 'info' },
  cancelled: { text: '已取消', type: 'danger' }
}
const statusText = (s) => STATUS[s]?.text || s
const statusType = (s) => STATUS[s]?.type || 'info'

const formatTime = (t) =>
  new Date(t).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })

onMounted(load)
</script>

<style scoped>
.page { max-width: 800px; margin: 0 auto; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.page-header h2 { margin: 0; font-size: 18px; }
.item { margin-bottom: 12px; cursor: pointer; }
.item-row { display: flex; justify-content: space-between; align-items: center; }
.route { display: flex; align-items: center; gap: 8px; min-width: 0; }
.loc { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.arrow { color: var(--el-color-primary); flex-shrink: 0; }
.reward { color: #ff6b00; font-weight: 700; font-size: 16px; flex-shrink: 0; margin-left: 12px; }
.meta { margin-top: 8px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.info { color: var(--el-text-color-secondary); font-size: 13px; }
.publisher { margin-left: auto; }
</style>
