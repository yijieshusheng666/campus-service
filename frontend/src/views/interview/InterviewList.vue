<template>
  <div class="page">
    <div class="page-header">
      <h2>AI 模拟面试</h2>
      <el-button type="primary" @click="showCreate = true">开始新面试</el-button>
    </div>

    <el-empty v-if="!loading && !items.length" description="还没有面试记录，开始第一场吧" />
    <el-card v-for="it in items" :key="it.id" class="item" shadow="hover" @click="goChat(it)">
      <div class="item-row">
        <div class="info">
          <span class="pos">{{ it.job_position }}</span>
          <el-tag :type="it.status === 'ongoing' ? 'success' : 'info'" size="small">
            {{ it.status === 'ongoing' ? '进行中' : '已结束' }}
          </el-tag>
        </div>
        <div class="meta">
          <span>{{ it.message_count }} 条消息 · {{ formatTime(it.updated_at) }}</span>
          <el-button
            class="del-btn"
            type="danger"
            size="small"
            plain
            @click.stop="onDelete(it)"
          >删除</el-button>
        </div>
      </div>
      <div class="last">{{ it.last_content }}</div>
    </el-card>

    <el-dialog v-model="showCreate" title="开始新面试" width="420">
      <el-form label-width="70px">
        <el-form-item label="简历">
          <el-select v-model="form.resume_id" placeholder="可不选（通用面试）" clearable style="width: 100%">
            <el-option v-for="r in resumes" :key="r.id" :label="r.file_name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标岗位">
          <el-input v-model="form.job_position" placeholder="如：Python 后端开发" maxlength="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :disabled="!form.job_position.trim()" :loading="creating" @click="create">
          开始面试
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createInterviewSse, deleteInterview, myInterviews } from '@/api/interview'
import { myResumes } from '@/api/resume'

const router = useRouter()
const items = ref([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const resumes = ref([])
const form = reactive({ resume_id: null, job_position: '' })

const load = async () => {
  loading.value = true
  try {
    const res = await myInterviews()
    items.value = res.data
  } finally {
    loading.value = false
  }
}

const loadResumes = async () => {
  try {
    const res = await myResumes()
    resumes.value = (res.data || []).filter((r) => r.parse_status === 'completed')
  } catch { /* 无简历时忽略 */ }
}

const create = async () => {
  creating.value = true
  let interviewId = null
  try {
    await createInterviewSse(
      { resume_id: form.resume_id || null, job_position: form.job_position.trim() },
      (event, data) => {
        if (event === 'start') interviewId = data.interview_id
        if (event === 'error') ElMessage.error(data.detail)
      }
    )
    if (interviewId) router.push({ name: 'InterviewChat', params: { id: interviewId } })
  } finally {
    creating.value = false
  }
}

const goChat = (it) => {
  router.push(
    it.status === 'completed'
      ? { name: 'InterviewReport', params: { id: it.id } }
      : { name: 'InterviewChat', params: { id: it.id } }
  )
}

const onDelete = async (it) => {
  try {
    await ElMessageBox.confirm(
      `确定删除「${it.job_position}」这场面试吗？删除后消息记录将一并移除。`,
      '删除面试',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  try {
    await deleteInterview(it.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

const formatTime = (t) => new Date(t).toLocaleString('zh-CN', { hour12: false })

onMounted(() => { load(); loadResumes() })
</script>

<style scoped>
.page { max-width: 800px; margin: 0 auto; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 18px; }
.item { margin-bottom: 12px; cursor: pointer; }
.item-row { display: flex; justify-content: space-between; align-items: center; }
.pos { font-weight: 600; margin-right: 8px; }
.meta { color: var(--el-text-color-secondary); font-size: 13px; }
.last { margin-top: 8px; color: var(--el-text-color-secondary); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
