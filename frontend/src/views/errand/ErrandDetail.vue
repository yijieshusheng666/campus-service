<template>
  <div v-if="errand" class="page">
    <div class="page-header">
      <h2>代拿详情</h2>
      <el-tag :type="statusType(errand.status)" size="large">{{ statusText(errand.status) }}</el-tag>
    </div>

    <el-card class="section">
      <div class="route-row">
        <div class="route">
          <div class="stop">
            <span class="label">取件</span>
            <span class="loc">{{ errand.pickup_location }}</span>
          </div>
          <el-icon class="arrow"><ArrowDown /></el-icon>
          <div class="stop">
            <span class="label">送达</span>
            <span class="loc">{{ errand.dropoff_location }}</span>
          </div>
        </div>
        <div class="reward">¥{{ errand.reward }}</div>
      </div>
      <el-descriptions :column="1" border class="desc">
        <el-descriptions-item label="快递信息">{{ errand.package_info }}</el-descriptions-item>
        <el-descriptions-item label="期望送达">
          {{ errand.deadline ? formatTime(errand.deadline) : '不限时' }}
        </el-descriptions-item>
        <el-descriptions-item label="备注">{{ errand.remark || '—' }}</el-descriptions-item>
        <el-descriptions-item label="发布者">{{ publisherName }}（联系：{{ errand.contact || '—' }}）</el-descriptions-item>
        <el-descriptions-item v-if="errand.runner" label="接单人">{{ runnerName }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <div class="actions">
      <!-- 大厅用户：接单 -->
      <el-button
        v-if="errand.status === 'pending' && !isPublisher"
        type="primary" size="large" :loading="acting" @click="onAccept"
      >
        接单赚 ¥{{ errand.reward }}
      </el-button>

      <!-- 跑腿员：确认送达 -->
      <el-button
        v-if="errand.status === 'accepted' && isRunner"
        type="warning" size="large" :loading="acting" @click="onStatus('delivered')"
      >
        已送达
      </el-button>

      <!-- 发布者：结算 -->
      <el-button
        v-if="errand.status === 'delivered' && isPublisher"
        type="success" size="large" :loading="acting" @click="onStatus('completed')"
      >
        确认结算
      </el-button>

      <!-- 发布者：取消（仅待接单），需二次确认 -->
      <el-button
        v-if="errand.status === 'pending' && isPublisher"
        type="danger" plain size="large" :loading="acting" @click="onCancel"
      >
        取消需求
      </el-button>

      <el-button size="large" @click="$router.push({ name: 'ErrandList' })">返回列表</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { acceptErrand, getErrand, updateErrandStatus } from '@/api/errand'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const auth = useAuthStore()
const errand = ref(null)
const acting = ref(false)

const isPublisher = computed(() => errand.value?.user_id === auth.user?.id)
const isRunner = computed(() => errand.value?.runner_id === auth.user?.id)
const publisherName = computed(() => errand.value?.publisher?.nickname || errand.value?.publisher?.username || '')
const runnerName = computed(() => errand.value?.runner?.nickname || errand.value?.runner?.username || '')

const load = async () => {
  const res = await getErrand(route.params.id)
  errand.value = res.data
}

const onAccept = async () => {
  acting.value = true
  try {
    await acceptErrand(route.params.id)
    ElMessage.success('接单成功')
    await load()
  } catch { /* 拦截器已提示 */ } finally {
    acting.value = false
  }
}

const onStatus = async (status) => {
  acting.value = true
  try {
    await updateErrandStatus(route.params.id, status)
    ElMessage.success('操作成功')
    await load()
  } catch { /* 拦截器已提示 */ } finally {
    acting.value = false
  }
}

const onCancel = async () => {
  try {
    await ElMessageBox.confirm(
      '确定要取消该代拿需求吗？取消后将不再显示在列表中。',
      '取消需求',
      { confirmButtonText: '确定取消', cancelButtonText: '再想想', type: 'warning' }
    )
  } catch {
    return
  }
  await onStatus('cancelled')
}

const STATUS = {
  pending: { text: '待接单', type: 'success' },
  accepted: { text: '配送中', type: 'warning' },
  delivered: { text: '已送达', type: 'primary' },
  completed: { text: '已完成', type: 'info' },
  cancelled: { text: '已取消', type: 'danger' }
}
const statusText = (s) => STATUS[s]?.text || s
const statusType = (s) => STATUS[s]?.type || 'info'

const formatTime = (t) => new Date(t).toLocaleString('zh-CN', { hour12: false })

onMounted(load)
</script>

<style scoped>
.page { max-width: 640px; margin: 0 auto; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 18px; }
.route-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.route { display: flex; flex-direction: column; gap: 6px; }
.stop { display: flex; align-items: center; gap: 10px; }
.label { font-size: 12px; color: var(--el-text-color-secondary); background: #f5f6f8; padding: 2px 8px; border-radius: 4px; }
.loc { font-weight: 600; }
.arrow { color: var(--el-color-primary); margin-left: 14px; }
.reward { color: #ff6b00; font-weight: 700; font-size: 24px; }
.desc { margin-top: 4px; }
.actions { margin-top: 20px; display: flex; gap: 12px; flex-wrap: wrap; }
</style>
