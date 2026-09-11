<template>
  <div class="smart-support">
    <!-- 悬浮按钮 -->
    <div class="support-float-btn" :class="{ active: visible }" @click="toggle">
      <el-icon :size="24" color="#fff"><Service /></el-icon>
      <el-badge v-if="unreadCount > 0" :value="unreadCount > 99 ? '99+' : unreadCount" class="support-badge" />
    </div>

    <!-- 聊天窗口 -->
    <Transition name="support-fade">
      <div v-if="visible" class="support-chat-box">
        <!-- 头部 -->
        <div class="support-header">
          <div class="support-header-left">
            <el-icon :size="18" color="#fff"><Service /></el-icon>
            <span class="support-title">智能客服</span>
            <el-tag size="small" type="success" effect="light" class="online-tag">在线</el-tag>
          </div>
          <div class="support-header-actions">
            <el-icon class="header-action" title="清空对话" @click="onClear"><Delete /></el-icon>
            <el-icon class="header-action" title="收起" @click="toggle"><ArrowDown /></el-icon>
          </div>
        </div>

        <!-- 消息区域 -->
        <div ref="msgBox" class="support-body" @scroll="onScroll">
          <!-- 欢迎语 -->
          <div class="msg-row assistant">
            <div class="msg-avatar assistant-avatar">
              <el-icon :size="16" color="#fff"><Service /></el-icon>
            </div>
            <div class="msg-content">
              <div class="msg-bubble assistant-bubble">
                <p>你好！我是校园综合服务平台的智能客服。</p>
                <p>我可以帮你解答问题，也可以直接帮你发布商品、管理订单。试试说“我要发布商品”。</p>
              </div>
              <div class="quick-questions">
                <div v-for="q in quickQuestions" :key="q" class="quick-q-btn" @click="sendQuick(q)">{{ q }}</div>
              </div>
            </div>
          </div>

          <!-- 历史消息 -->
          <div v-for="(msg, idx) in messages" :key="idx" class="msg-row" :class="msg.role">
            <div class="msg-avatar" :class="msg.role + '-avatar'">
              <el-icon v-if="msg.role === 'assistant'" :size="16" color="#fff"><Service /></el-icon>
              <span v-else class="user-initial">{{ userInitial }}</span>
            </div>
            <div class="msg-content">
              <div v-if="msg.type === 'text' || !msg.type" class="msg-bubble" :class="msg.role + '-bubble'">
                <template v-if="msg.role === 'assistant' && msg.isTyping && !msg.content">
                  <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
                </template>
                <template v-else>{{ msg.content }}</template>
              </div>
              <div v-if="msg.type === 'image'" class="msg-bubble user-bubble image-bubble">
                <el-image :src="msg.content" fit="cover" class="chat-img" :preview-src-list="[msg.content]" />
              </div>
            </div>
          </div>
        </div>

        <!-- 输入区 -->
        <div class="support-footer">
          <!-- 已选图片预览 -->
          <div v-if="previewImages.length" class="preview-row">
            <div v-for="(url, i) in previewImages" :key="i" class="preview-item">
              <el-image :src="url" fit="cover" class="preview-thumb" />
              <el-icon class="preview-del" @click="removeImage(i)"><CircleClose /></el-icon>
            </div>
          </div>

          <!-- 阶段提示条 -->
          <div v-if="phaseHint" class="phase-hint">{{ phaseHint }}</div>

          <!-- 行动按钮 -->
          <div v-if="actionButtons.length" class="action-row">
            <el-button v-for="btn in actionButtons" :key="btn.label" :type="btn.type" size="small" @click="sendAction(btn.value)">{{ btn.label }}</el-button>
          </div>

          <div class="input-row">
            <el-input v-model="inputText" type="textarea" :rows="2" placeholder="输入你的问题，按 Enter 发送..." maxlength="500" show-word-limit resize="none" @keydown.enter.prevent="onSend" />
            <div class="input-actions">
              <el-upload ref="uploader" action="#" :auto-upload="false" :show-file-list="false" :on-change="onImageSelect" :multiple="true" :limit="6" accept="image/jpeg,image/png,image/webp">
                <el-button type="default" class="upload-btn" :disabled="uploading || previewImages.length >= 6" :loading="uploading"><el-icon><Picture /></el-icon></el-button>
              </el-upload>
              <el-button type="primary" class="send-btn" :loading="loading" :disabled="!inputText.trim() && !previewImages.length" @click="onSend"><el-icon><Promotion /></el-icon></el-button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Service, Delete, ArrowDown, Promotion, Picture, CircleClose } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { clearSupportHistory, getSupportHistory } from '@/api/support'
import { createGoods } from '@/api/goods'
import { uploadImage } from '@/api/goods'

const auth = useAuthStore()
const visible = ref(false)
const messages = ref([])
const inputText = ref('')
const loading = ref(false)
const msgBox = ref(null)
const unreadCount = ref(0)

const previewImages = ref([])
const rawFiles = ref([])
const uploading = ref(false)
const uploader = ref(null)

const taskState = ref('idle')
const phase = ref(null)
const actionData = ref(null)

const quickQuestions = [
  '我要发布商品',
  '怎么发布二手商品？',
  '跑腿怎么接单？',
  'AI模拟面试怎么用？',
]

const userInitial = computed(() => {
  const name = auth.user?.nickname || auth.user?.username || 'U'
  return name.charAt(0).toUpperCase()
})

const phaseHint = computed(() => {
  if (phase.value === 'collecting_images') return '请上传商品图片（最多6张）并补充描述'
  if (phase.value === 'analyzing') return 'AI 正在识别商品信息，请稍候...'
  if (phase.value === 'awaiting_confirm') return '请确认商品分析结果'
  if (phase.value === 'awaiting_publish') return '请确认是否正式发布'
  return ''
})

const actionButtons = computed(() => {
  const type = actionData.value?.type
  if (type === 'analysis_confirm') {
    return [
      { label: '确认', value: '确认', type: 'primary' },
      { label: '修改', value: '修改', type: 'default' },
      { label: '取消', value: '取消', type: 'danger' },
    ]
  }
  if (type === 'publish_confirm') {
    return [
      { label: '确认发布', value: '确认发布', type: 'primary' },
      { label: '取消', value: '取消', type: 'danger' },
    ]
  }
  return []
})

function toggle() {
  visible.value = !visible.value
  if (visible.value) {
    unreadCount.value = 0
    nextTick(() => scrollToBottom())
  }
}

async function loadHistory() {
  if (!auth.isAuthenticated) return
  try {
    const res = await getSupportHistory()
    if (res.data && Array.isArray(res.data)) {
      messages.value = res.data.map(m => ({ ...m, type: 'text' }))
    }
  } catch (e) {
    // 静默失败
  }
}

function onImageSelect(file, fileList) {
  const raw = fileList.map(f => f.raw || f)
  const newFiles = raw.filter(f => !rawFiles.value.includes(f))
  rawFiles.value.push(...newFiles)
  newFiles.forEach(f => {
    if (f instanceof File) previewImages.value.push(URL.createObjectURL(f))
  })
}

function removeImage(index) {
  previewImages.value.splice(index, 1)
  rawFiles.value.splice(index, 1)
}

async function uploadAllImages() {
  const urls = []
  for (const file of rawFiles.value) {
    try {
      const res = await uploadImage(file)
      if (res.data?.url) urls.push(res.data.url)
    } catch (e) {
      ElMessage.warning(`图片上传失败：${file.name || ''}`)
    }
  }
  return urls
}

async function onSend() {
  const text = inputText.value.trim()
  const hasImages = previewImages.value.length > 0
  if (!text && !hasImages) return
  if (!auth.isAuthenticated) {
    ElMessage.warning('请先登录')
    return
  }

  if (text) messages.value.push({ role: 'user', content: text, type: 'text' })
  if (hasImages) {
    previewImages.value.forEach(url => {
      messages.value.push({ role: 'user', content: url, type: 'image' })
    })
  }

  inputText.value = ''
  loading.value = true
  scrollToBottom()

  let imageUrls = []
  if (hasImages) {
    uploading.value = true
    try {
      imageUrls = await uploadAllImages()
    } catch (e) {
      // 图片上传已在 uploadAllImages 中提示
    }
    uploading.value = false
    previewImages.value = []
    rawFiles.value = []
    if (!imageUrls.length && !text) {
      messages.value.push({ role: 'assistant', content: '图片上传失败，请重试。', type: 'text' })
      loading.value = false
      return
    }
  }

  // ---- SSE 流式接收 ----
  let assistantMsg = { role: 'assistant', content: '', type: 'text', isTyping: true }
  messages.value.push(assistantMsg)
  let controller = null

  try {
    controller = new AbortController()
    const token = auth.token || ''
    const resp = await fetch('/api/v1/support/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
      },
      body: JSON.stringify({ question: text, image_urls: imageUrls }),
      signal: controller.signal,
    })

    if (!resp.ok) {
      const err = await resp.text().catch(() => '请求失败')
      throw new Error(err)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const events = buffer.split('\n\n')
      buffer = events.pop() // 最后一个可能不完整，留到下次

      for (const eventStr of events) {
        const lines = eventStr.trim().split('\n')
        let eventType = 'message'
        let dataStr = ''
        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            dataStr = line.slice(5).trim()
          }
        }
        if (!dataStr) continue

        try {
          const data = JSON.parse(dataStr)
          if (eventType === 'delta' && data.text) {
            assistantMsg.isTyping = false
            assistantMsg.content += data.text
            // 触发 Vue 响应式更新
            messages.value = [...messages.value]
          } else if (eventType === 'state') {
            taskState.value = data.task_state || 'idle'
            phase.value = data.phase || null
            actionData.value = data.action || null
          } else if (eventType === 'error') {
            assistantMsg.isTyping = false
            assistantMsg.content = data.text || '服务暂时不可用，请稍后再试。'
            messages.value = [...messages.value]
          }
          // done 事件不处理额外内容（已在前面的 delta/state 中累积）
          nextTick(() => scrollToBottom())
        } catch (e) {
          // 忽略格式错误的 SSE 行
        }
      }
    }
  } catch (e) {
    assistantMsg.isTyping = false
    assistantMsg.content = '抱歉，服务暂时不可用，请稍后再试。'
    messages.value = [...messages.value]
  } finally {
    assistantMsg.isTyping = false
    loading.value = false
    // 如果后端标记为 published，实际写入数据库
    if (actionData.value?.type === 'published') {
      const payload = actionData.value?.data
      if (payload) {
        createGoods({
          title: payload.title,
          description: payload.description,
          price: payload.price,
          category: payload.category,
          condition: payload.condition,
          image_urls: payload.image_urls || [],
        }).then(() => {
          assistantMsg.content += '\n\n✅ 商品已发布成功！'
          messages.value = [...messages.value]
          nextTick(() => scrollToBottom())
        }).catch(err => {
          const detail = err?.response?.data?.detail || err.message || '网络错误'
          assistantMsg.content += `\n\n❌ 发布入库失败：${detail}。请联系管理员。`
          messages.value = [...messages.value]
          nextTick(() => scrollToBottom())
        })
      }
    }
    nextTick(() => scrollToBottom())
  }
}

function sendQuick(q) {
  inputText.value = q
  onSend()
}

function sendAction(value) {
  inputText.value = value
  onSend()
}

async function onClear() {
  try {
    await ElMessageBox.confirm('确定要清空当前对话历史吗？', '提示', {
      confirmButtonText: '清空',
      cancelButtonText: '取消',
      type: 'warning',
    })
    messages.value = []
    previewImages.value = []
    rawFiles.value = []
    taskState.value = 'idle'
    phase.value = null
    actionData.value = null
    if (auth.isAuthenticated) await clearSupportHistory()
    ElMessage.success('对话已清空')
  } catch {
    // 取消
  }
}

function scrollToBottom() {
  if (msgBox.value) msgBox.value.scrollTop = msgBox.value.scrollHeight
}

function onScroll() {
  // 可扩展：标记消息已读逻辑
}

watch(() => messages.value.length, () => nextTick(() => scrollToBottom()))

onMounted(() => loadHistory())
</script>

<style scoped>
.smart-support { position: fixed; bottom: 24px; right: 24px; z-index: 9999; }
.support-float-btn { width: 56px; height: 56px; border-radius: 50%; background: linear-gradient(135deg, #ff6b00, #ff9500); display: flex; align-items: center; justify-content: center; cursor: pointer; box-shadow: 0 4px 16px rgba(255, 107, 0, 0.35); transition: all 0.3s ease; position: relative; }
.support-float-btn:hover { transform: scale(1.08); box-shadow: 0 6px 24px rgba(255, 107, 0, 0.45); }
.support-float-btn.active { background: linear-gradient(135deg, #ff5500, #ff8800); }
.support-badge { position: absolute; top: -2px; right: -2px; }

.support-chat-box { position: absolute; bottom: 72px; right: 0; width: 400px; height: 560px; background: #fff; border-radius: 16px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); display: flex; flex-direction: column; overflow: hidden; }

.support-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; background: linear-gradient(135deg, #ff6b00, #ff9500); flex-shrink: 0; }
.support-header-left { display: flex; align-items: center; gap: 8px; }
.support-title { font-size: 15px; font-weight: 600; color: #fff; }
.online-tag { margin-left: 4px; --el-tag-bg-color: rgba(255,255,255,0.25); --el-tag-text-color: #fff; }
.support-header-actions { display: flex; gap: 10px; }
.header-action { font-size: 18px; color: rgba(255,255,255,0.85); cursor: pointer; padding: 4px; border-radius: 4px; transition: all 0.2s; }
.header-action:hover { color: #fff; background: rgba(255,255,255,0.2); }

.support-body { flex: 1; overflow-y: auto; padding: 14px 16px; background: #f8f9fa; }
.msg-row { display: flex; gap: 10px; margin-bottom: 14px; }
.msg-row.user { flex-direction: row-reverse; }
.msg-avatar { width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }
.assistant-avatar { background: linear-gradient(135deg, #ff6b00, #ff9500); }
.user-avatar { background: linear-gradient(135deg, #667eea, #764ba2); }
.user-initial { font-size: 13px; font-weight: 600; color: #fff; }
.msg-content { max-width: 78%; }
.msg-bubble { padding: 10px 14px; border-radius: 14px; font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.assistant-bubble { background: #fff; color: #1d2129; border: 1px solid #e8eaed; border-top-left-radius: 4px; }
.user-bubble { background: linear-gradient(135deg, #ff6b00, #ff9500); color: #fff; border-top-right-radius: 4px; }
.image-bubble { padding: 6px; max-width: 200px; }
.chat-img { width: 100%; height: 160px; border-radius: 10px; object-fit: cover; }

.quick-questions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.quick-q-btn { padding: 5px 12px; background: #fff; border: 1px solid #e8eaed; border-radius: 16px; font-size: 12px; color: #ff6b00; cursor: pointer; transition: all 0.2s; }
.quick-q-btn:hover { background: #fff5ec; border-color: #ff6b00; }

.loading-bubble { display: flex; align-items: center; gap: 4px; padding: 14px 16px; }
.typing-dot { width: 6px; height: 6px; background: #a0a5b2; border-radius: 50%; animation: typing 1.4s infinite ease-in-out both; }
.typing-dot:nth-child(1) { animation-delay: -0.32s; }
.typing-dot:nth-child(2) { animation-delay: -0.16s; }
@keyframes typing { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; } 40% { transform: scale(1); opacity: 1; } }

.support-footer { padding: 10px 14px; background: #fff; border-top: 1px solid #eef0f4; flex-shrink: 0; }
.preview-row { display: flex; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.preview-item { position: relative; width: 56px; height: 56px; border-radius: 8px; overflow: hidden; border: 1px solid #e8eaed; }
.preview-thumb { width: 100%; height: 100%; object-fit: cover; }
.preview-del { position: absolute; top: 2px; right: 2px; width: 16px; height: 16px; background: rgba(0,0,0,0.5); color: #fff; border-radius: 50%; font-size: 12px; cursor: pointer; display: flex; align-items: center; justify-content: center; }

.phase-hint { font-size: 12px; color: #ff6b00; margin-bottom: 6px; padding: 4px 8px; background: #fff5ec; border-radius: 6px; display: inline-block; }
.action-row { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }

.input-row { display: flex; gap: 8px; align-items: flex-end; }
.input-row :deep(.el-textarea__inner) { border-radius: 10px; background: #f5f6f8; border-color: #e8eaed; }
.input-actions { display: flex; gap: 6px; align-items: center; }
.upload-btn { width: 40px; height: 40px; border-radius: 50%; padding: 0; }
.send-btn { width: 40px; height: 40px; border-radius: 50%; padding: 0; flex-shrink: 0; }

.support-fade-enter-active, .support-fade-leave-active { transition: all 0.25s ease; }
.support-fade-enter-from, .support-fade-leave-to { opacity: 0; transform: translateY(12px) scale(0.96); }

/* ===== 移动端适配 ===== */
@media (max-width: 640px) {
  /* 悬浮按钮往屏幕内收一点，避免被边缘裁掉 */
  .smart-support { bottom: 16px; right: 12px; }

  /* 400px 宽的聊天窗在 375px 的手机上会直接超出可视区域，
     改成几乎撑满全屏（左右各留 12px），高度用视口高度封顶 */
  .support-chat-box {
    width: calc(100vw - 24px);
    height: min(72vh, 560px);
    right: 0;
    bottom: 72px;
    border-radius: 14px;
  }
  .support-header { padding: 12px 14px; }
  .support-body { padding: 12px; }
  /* 气泡占比放宽，小屏上 78% 的限宽会让文字过早换行 */
  .msg-content { max-width: 86%; }
}
</style>