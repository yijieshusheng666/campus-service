<template>
  <div class="page">
    <div class="page-header">
      <h2>AI 模拟面试 · {{ detail?.job_position }}</h2>
      <el-button v-if="detail?.status === 'ongoing'" type="danger" plain :disabled="streaming" @click="finish">
        结束面试并生成报告
      </el-button>
      <el-button v-else type="primary" @click="goReport">查看评估报告</el-button>
    </div>

    <div ref="chatBox" class="chat-box">
      <div v-for="m in messages" :key="m.id ?? 'tmp'" class="bubble" :class="m.role">
        <div class="name">{{ m.role === 'assistant' ? '面试官' : '我' }}</div>
        <div class="content">{{ m.content }}</div>
      </div>
      <div v-if="streaming && pending" class="bubble assistant">
        <div class="name">面试官</div>
        <div class="content">{{ pending }}</div>
      </div>
    </div>

    <div class="input-row">
      <el-input
        v-model="input" type="textarea" :rows="3" placeholder="输入你的回答…"
        :disabled="streaming || detail?.status !== 'ongoing'" @keydown.enter.exact.prevent="send"
      />
      <el-button type="primary" :loading="streaming" :disabled="!input.trim() || detail?.status !== 'ongoing'" @click="send">
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { chatInterviewSse, finishInterview, getInterview } from '@/api/interview'

const route = useRoute()
const router = useRouter()
const detail = ref(null)
const messages = ref([])
const input = ref('')
const streaming = ref(false)
const pending = ref('')
const chatBox = ref(null)

const load = async () => {
  const res = await getInterview(route.params.id)
  detail.value = res.data
  messages.value = res.data.messages || []
  scrollToBottom()
}

const send = async () => {
  const content = input.value.trim()
  if (!content || streaming.value) return
  input.value = ''
  messages.value.push({ role: 'user', content })
  streaming.value = true
  pending.value = ''
  scrollToBottom()
  await chatInterviewSse(route.params.id, content, (event, data) => {
    if (event === 'delta') { pending.value += data.text; scrollToBottom() }
    else if (event === 'done') {
      messages.value.push({ role: 'assistant', content: pending.value })
      pending.value = ''
    } else if (event === 'error') {
      ElMessage.error(data.detail)
      if (pending.value) messages.value.push({ role: 'assistant', content: pending.value })
      pending.value = ''
    }
  })
  streaming.value = false
  scrollToBottom()
}

const finish = async () => {
  streaming.value = true
  try {
    await finishInterview(route.params.id)
    goReport()
  } catch { /* 拦截器已提示 */ } finally {
    streaming.value = false
  }
}

const goReport = () => router.push({ name: 'InterviewReport', params: { id: route.params.id } })

const scrollToBottom = async () => {
  await nextTick()
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}

onMounted(load)
</script>

<style scoped>
.page { max-width: 800px; margin: 0 auto; display: flex; flex-direction: column; height: calc(100vh - 90px); padding: 20px 20px 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.page-header h2 { margin: 0; font-size: 18px; }
.chat-box { flex: 1; overflow-y: auto; padding: 12px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: #fafafa; }
.bubble { max-width: 75%; margin-bottom: 14px; }
.bubble.user { margin-left: auto; }
.bubble.user .content { background: var(--el-color-primary); color: #fff; }
.bubble.assistant .content { background: #fff; border: 1px solid var(--el-border-color-lighter); }
.name { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.content { padding: 10px 12px; border-radius: 8px; white-space: pre-wrap; line-height: 1.6; }
.input-row { display: flex; gap: 12px; margin-top: 12px; align-items: flex-end; padding-bottom: 20px; }
.input-row :deep(.el-textarea) { flex: 1; }
</style>
