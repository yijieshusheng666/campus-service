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
      <div class="input-main">
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          :placeholder="placeholder"
          :disabled="streaming || detail?.status !== 'ongoing'"
          @keydown.enter.exact.prevent="send"
        />

        <div class="tools">
          <el-button
            class="mic-btn"
            :class="{ active: recording }"
            circle
            :title="micTitle"
            :disabled="!recordOk || streaming || detail?.status !== 'ongoing'"
            @click="toggleRecord"
          >
            <el-icon><Microphone /></el-icon>
          </el-button>

          <span v-if="recording" class="rec-status">
            <span class="rec-dot" />
            <span>{{ recordSeconds }} 秒</span>
            <span class="level"><i :style="{ width: levelPercent + '%' }" /></span>
            <span class="rec-hint">静音 2 秒自动结束</span>
          </span>
          <span v-else-if="transcribing" class="rec-status muted">语音识别中…</span>

          <span class="spacer" />

          <label class="speak-toggle" :class="{ disabled: !speechOk }">
            <el-switch v-model="autoSpeak" size="small" :disabled="!speechOk" />
            <span>朗读问题</span>
            <span v-if="speaking" class="speaking">朗读中</span>
          </label>
        </div>
      </div>

      <el-button
        type="primary"
        :loading="streaming"
        :disabled="!input.trim() || streaming || transcribing || detail?.status !== 'ongoing'"
        @click="send"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { chatInterviewSse, finishInterview, getInterview, transcribeAudio } from '@/api/interview'
import { createRecorder, isRecordingSupported } from '@/utils/recorder'
import { createSpeaker, isSpeechSupported, loadSpeakPref, saveSpeakPref } from '@/utils/speech'

const route = useRoute()
const router = useRouter()
const detail = ref(null)
const messages = ref([])
const input = ref('')
const streaming = ref(false)
const pending = ref('')
const chatBox = ref(null)

// ---- 语音：录入（ASR）----
const recordOk = isRecordingSupported()
const recording = ref(false)
const transcribing = ref(false)
const recordSeconds = ref(0)
const level = ref(0)

let recorder = null
let timer = null
// 本段回答已转写出的文本片段：既用于拼接完整回答，也作为下一片的 prompt 上下文
let sliceTexts = []
// 分片串行提交：prompt 依赖前一段结果，必须保证顺序
let transcribeChain = Promise.resolve()

// ---- 语音：播出（TTS）----
const speechOk = isSpeechSupported()
// 开关跨页持久化：创建面试发生在列表页，首题在那儿生成
const autoSpeak = ref(speechOk && loadSpeakPref())
const speaking = ref(false)
const speaker = createSpeaker({ onStateChange: (s) => { speaking.value = s } })
speaker.setEnabled(autoSpeak.value)

const placeholder = computed(() =>
  recording.value
    ? '正在录音，说不完可以再点一次麦克风结束…'
    : '输入你的回答，或点左侧麦克风直接说'
)
const micTitle = computed(() => {
  if (!recordOk) return '当前浏览器不支持录音，请用 Chrome / Edge'
  return recording.value ? '结束录音' : '开始语音回答'
})
const levelPercent = computed(() => Math.min(100, Math.round(level.value * 500)))

const scrollToBottom = async () => {
  await nextTick()
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}

const load = async () => {
  const res = await getInterview(route.params.id)
  detail.value = res.data
  messages.value = res.data.messages || []
  scrollToBottom()
}

const send = async () => {
  const content = input.value.trim()
  if (!content || streaming.value) return
  if (transcribing.value) {
    ElMessage.warning('语音还在识别中，请稍候再发送')
    return
  }
  input.value = ''
  sliceTexts = []
  messages.value.push({ role: 'user', content })
  streaming.value = true
  pending.value = ''
  scrollToBottom()
  await chatInterviewSse(route.params.id, content, (event, data) => {
    if (event === 'delta') {
      pending.value += data.text
      // 逐字增量不能逐字念：交给朗读器按标点缓冲成句
      if (autoSpeak.value) speaker.feed(data.text)
      scrollToBottom()
    } else if (event === 'done') {
      if (autoSpeak.value) speaker.flush()
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

// ---- 录音 / 转写 ----

const stopTimer = () => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

const stopRecord = () => {
  if (!recording.value) return
  recording.value = false
  stopTimer()
  level.value = 0
  const current = recorder
  recorder = null
  // stop() 会产出最后一片（可能不足 30 秒），转写完成后回填输入框
  current?.stop()
}

const toggleRecord = async () => {
  if (recording.value) {
    stopRecord()
    return
  }
  if (streaming.value) return
  // 用户开口前先停掉朗读，避免麦克风把面试官的声音录进去
  speaker.cancel()

  sliceTexts = []
  input.value = ''
  level.value = 0
  transcribeChain = Promise.resolve()

  recorder = createRecorder({
    onSlice: (blob) => enqueueTranscribe(blob),
    onLevel: (v) => { level.value = v },
    // 静音触底是在音频回调里同步发生的，挪到下一个事件循环再关 AudioContext
    onAutoStop: () => setTimeout(stopRecord, 0),
    onError: (e) => {
      ElMessage.error(e.message)
      recording.value = false
      stopTimer()
    }
  })

  const ok = await recorder.start()
  if (!ok) {
    recorder = null
    return
  }
  recording.value = true
  recordSeconds.value = 0
  timer = setInterval(() => { recordSeconds.value += 1 }, 1000)
}

const enqueueTranscribe = (blob) => {
  transcribeChain = transcribeChain.then(() => runTranscribe(blob)).catch(() => {})
}

const runTranscribe = async (blob) => {
  transcribing.value = true
  try {
    const text = await transcribeAudio(route.params.id, blob, sliceTexts.join(''))
    if (text) {
      sliceTexts.push(text)
      // 实时回填：用户能看到识别进度，也能顺手改掉错字
      input.value = sliceTexts.join('')
      scrollToBottom()
    }
  } catch (e) {
    ElMessage.error(e.message || '语音转写失败，请重试或直接输入文字')
  } finally {
    transcribing.value = false
  }
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

watch(autoSpeak, (v) => {
  speaker.setEnabled(v)
  saveSpeakPref(v)
  if (v) ElMessage.info('已开启朗读，面试官的问题会被读出来')
})

/** 朗读最后一道面试官提问（首题在列表页生成，跳转过来时补读一次）。 */
const speakLastQuestion = () => {
  const last = [...messages.value].reverse().find((m) => m.role === 'assistant')
  if (!last?.content) return
  speaker.feed(last.content)
  speaker.flush()
}

onMounted(async () => {
  await load()
  if (route.query.autoplay === '1' && autoSpeak.value) speakLastQuestion()
})

onBeforeUnmount(() => {
  stopRecord()
  stopTimer()
  speaker.cancel()
})
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
.input-main { flex: 1; }
.input-main :deep(.el-textarea) { flex: 1; }
.tools { display: flex; align-items: center; gap: 10px; margin-top: 8px; min-height: 32px; }
.mic-btn.active { background: var(--el-color-danger); border-color: var(--el-color-danger); color: #fff; animation: mic-pulse 1.4s infinite; }
@keyframes mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 108, 108, 0.5); }
  50% { box-shadow: 0 0 0 7px rgba(245, 108, 108, 0); }
}
.rec-status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--el-color-danger); }
.rec-status.muted { color: var(--el-text-color-secondary); }
.rec-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--el-color-danger); }
.rec-hint { color: var(--el-text-color-secondary); }
.level { display: inline-block; width: 56px; height: 6px; border-radius: 3px; background: var(--el-border-color-lighter); overflow: hidden; }
.level i { display: block; height: 100%; background: var(--el-color-success); transition: width 0.1s linear; }
.spacer { flex: 1; }
.speak-toggle { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--el-text-color-secondary); cursor: pointer; }
.speak-toggle.disabled { opacity: 0.5; cursor: not-allowed; }
.speaking { color: var(--el-color-primary); }
</style>
