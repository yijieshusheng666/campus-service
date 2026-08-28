<template>
  <div class="chat-page">
    <!-- 左侧：会话列表 -->
    <div class="conv-panel">
      <div class="conv-header">
        <span>我的私信</span>
      </div>
      <div class="conv-list">
        <div
          v-for="c in conversations"
          :key="c.user_id"
          class="conv-item"
          :class="{ active: c.user_id === peerId }"
          @click="selectConversation(c.user_id)"
        >
          <div class="conv-avatar">{{ avatarChar(c.nickname || c.username) }}</div>
          <div class="conv-main">
            <div class="conv-top">
              <span class="conv-name">{{ c.nickname || c.username }}</span>
              <span class="conv-time">{{ shortTime(c.last_time) }}</span>
            </div>
            <div class="conv-bottom">
              <span class="conv-last">{{ c.last_message }}</span>
              <span v-if="c.unread > 0" class="conv-unread">
                {{ c.unread > 99 ? '99+' : c.unread }}
              </span>
            </div>
          </div>
        </div>
        <el-empty v-if="!conversations.length" description="暂无私信" :image-size="60" />
      </div>
    </div>

    <!-- 右侧：聊天区 -->
    <div class="chat-panel">
      <template v-if="peerId">
        <div class="chat-header">
          <span class="chat-peer">{{ peerName || `用户 ${peerId}` }}</span>
          <span class="ws-dot" :class="wsState" :title="wsTitle"></span>
        </div>

        <div ref="msgListRef" class="msg-list" @scroll="onScroll">
          <div v-if="hasMore" class="load-more" @click="loadMore">查看更早的消息</div>
          <div
            v-for="m in messages"
            :key="m.id"
            class="msg-row"
            :class="{ mine: m.sender_id === myId, pending: m.pending }"
          >
            <div class="msg-avatar">{{ avatarChar(m.sender_name) }}</div>
            <div class="msg-body">
              <div class="msg-bubble">{{ m.content }}</div>
              <div class="msg-time">{{ fullTime(m.created_at) }}</div>
            </div>
          </div>
        </div>

        <div class="chat-input">
          <el-input
            v-model="draft"
            placeholder="输入消息，Enter 发送"
            :disabled="wsState !== 'open'"
            @keyup.enter="send"
          />
          <el-button
            type="primary"
            :disabled="wsState !== 'open' || !draft.trim()"
            @click="send"
          >
            发送
          </el-button>
        </div>
        <div v-if="wsState !== 'open'" class="ws-tip">连接已断开，正在自动重连…</div>
      </template>

      <div v-else class="chat-placeholder">
        <el-icon :size="52" color="#dcdfe6"><ChatDotRound /></el-icon>
        <p>选择一个会话，或从商品页点击「聊一聊」开始私聊</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatDotRound } from '@element-plus/icons-vue'
import { getConversations, getMessages, markRead } from '@/api/message'
import { getUser } from '@/api/users'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const myId = computed(() => auth.user?.id)

const conversations = ref([])
const peerId = ref(route.params.userId ? Number(route.params.userId) : null)
const peerName = ref('')
const messages = ref([])
const hasMore = ref(false)
const draft = ref('')

const msgListRef = ref(null)
const ws = ref(null)
const wsState = ref('connecting') // connecting | open | closed
const wsTitle = computed(
  () => ({ connecting: '连接中', open: '实时在线', closed: '已断开' }[wsState.value])
)

let heartbeatTimer = null
let reconnectDelay = 1000

// ---- WebSocket ----
function connect() {
  if (!auth.token) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const sock = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(auth.token)}`)
  ws.value = sock
  wsState.value = 'connecting'

  sock.onopen = () => {
    wsState.value = 'open'
    reconnectDelay = 1000
    // 心跳：30s 一次 ping 保活
    clearInterval(heartbeatTimer)
    heartbeatTimer = setInterval(() => {
      if (sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify({ type: 'ping' }))
    }, 30000)
  }

  sock.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'chat_ack') {
      // 发送确认：把 pending 消息替换为落库消息
      const idx = messages.value.findIndex((m) => m.pending)
      const confirmed = {
        id: data.message_id,
        sender_id: myId.value,
        sender_name: auth.user?.nickname || auth.user?.username,
        receiver_id: data.receiver_id,
        content: data.content,
        created_at: data.created_at,
      }
      if (idx >= 0) messages.value.splice(idx, 1, confirmed)
      else messages.value.push(confirmed)
      scrollToBottom()
      refreshConversations()
    } else if (data.type === 'new_message') {
      // 收到新消息：当前会话直接展示并标记已读，否则仅更新会话列表未读数
      if (data.sender_id === peerId.value) {
        messages.value.push({
          id: data.id,
          sender_id: data.sender_id,
          sender_name: peerName.value,
          receiver_id: myId.value,
          content: data.content,
          created_at: data.created_at,
        })
        markRead(peerId.value).catch(() => {})
        scrollToBottom()
      }
      refreshConversations()
    }
  }

  sock.onclose = (event) => {
    clearInterval(heartbeatTimer)
    wsState.value = 'closed'
    if (event.code === 4401) {
      auth.logout()
      router.push({ name: 'Login', query: { redirect: route.fullPath } })
      return
    }
    // 断线重连：指数退避，上限 30s
    setTimeout(connect, reconnectDelay)
    reconnectDelay = Math.min(reconnectDelay * 2, 30000)
  }
}

// ---- 会话与历史 ----
async function refreshConversations() {
  try {
    const res = await getConversations()
    conversations.value = res.data
  } catch (e) {
    /* 401 已由拦截器处理 */
  }
}

async function openConversation(userId) {
  if (!userId) {
    peerId.value = null
    peerName.value = ''
    messages.value = []
    return
  }
  peerId.value = userId
  messages.value = []
  hasMore.value = false
  // 对方昵称：优先从会话列表取，否则拉用户信息（首次私聊场景）
  const conv = conversations.value.find((c) => c.user_id === userId)
  if (conv) {
    peerName.value = conv.nickname || conv.username
  } else {
    try {
      const res = await getUser(userId)
      peerName.value = res.data.nickname || res.data.username
      // 新会话置入列表，便于切换后回来
      conversations.value.unshift({
        user_id: userId,
        username: res.data.username,
        nickname: res.data.nickname,
        last_message: '',
        last_time: null,
        unread: 0,
      })
    } catch (e) {
      peerName.value = ''
    }
  }
  await loadHistory()
  await markRead(userId).catch(() => {})
  await refreshConversations()
}

async function loadHistory() {
  const res = await getMessages(peerId.value, { limit: 50 })
  messages.value = res.data.map((m) => ({
    ...m,
    sender_name: m.sender_id === myId.value ? auth.user?.nickname || auth.user?.username : peerName.value,
  }))
  hasMore.value = res.data.length === 50
  scrollToBottom()
}

async function loadMore() {
  if (loadingMore) return
  loadingMore = true
  try {
    const first = messages.value[0]
    if (!first) return
    const res = await getMessages(peerId.value, { before_id: first.id, limit: 50 })
    const older = res.data.map((m) => ({
      ...m,
      sender_name: m.sender_id === myId.value ? auth.user?.nickname || auth.user?.username : peerName.value,
    }))
    hasMore.value = res.data.length === 50
    const el = msgListRef.value
    const prevHeight = el ? el.scrollHeight : 0
    messages.value = [...older, ...messages.value]
    // 保持滚动位置不跳动
    await nextTick()
    if (el) el.scrollTop = el.scrollHeight - prevHeight
  } finally {
    loadingMore = false
  }
}
let loadingMore = false

function selectConversation(userId) {
  if (userId === peerId.value) return
  router.push({ name: 'Chat', params: { userId } })
}

// ---- 发送 ----
function send() {
  const content = draft.value.trim()
  if (!content || wsState.value !== 'open') return
  draft.value = ''
  // 乐观展示 pending 消息，chat_ack 到达后替换为落库结果
  messages.value.push({
    id: -Date.now(),
    sender_id: myId.value,
    sender_name: auth.user?.nickname || auth.user?.username,
    receiver_id: peerId.value,
    content,
    created_at: new Date().toISOString(),
    pending: true,
  })
  scrollToBottom()
  ws.value.send(
    JSON.stringify({ type: 'chat', receiver_id: peerId.value, content })
  )
}

// ---- 滚动 ----
function scrollToBottom() {
  nextTick(() => {
    if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight
  })
}

function onScroll() {
  const el = msgListRef.value
  if (el && el.scrollTop <= 40 && hasMore.value) loadMore()
}

// ---- 工具 ----
function avatarChar(name) {
  return (name || '?').charAt(0).toUpperCase()
}
function shortTime(t) {
  if (!t) return ''
  const d = new Date(t)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  }
  return `${d.getMonth() + 1}/${d.getDate()}`
}
function fullTime(t) {
  if (!t) return ''
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// ---- 生命周期与路由变化 ----
watch(
  () => route.params.userId,
  (val) => {
    if (route.name === 'Chat') openConversation(val ? Number(val) : null)
  }
)

onMounted(async () => {
  if (!auth.isAuthenticated) {
    router.push({ name: 'Login', query: { redirect: route.fullPath } })
    return
  }
  await refreshConversations()
  if (peerId.value) await openConversation(peerId.value)
  connect()
})

onUnmounted(() => {
  clearInterval(heartbeatTimer)
  if (ws.value) {
    ws.value.onclose = null // 主动关闭不触发重连
    ws.value.close()
  }
})
</script>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
  background: #fff;
  overflow: hidden;
}

/* ===== 左侧会话列表 ===== */
.conv-panel {
  width: 280px;
  border-right: 1px solid #eef0f4;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.conv-header {
  height: 56px;
  line-height: 56px;
  padding: 0 16px;
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
  border-bottom: 1px solid #eef0f4;
  flex-shrink: 0;
}
.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}
.conv-item {
  display: flex;
  gap: 10px;
  padding: 10px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
}
.conv-item:hover {
  background: #f5f6f8;
}
.conv-item.active {
  background: #fff5ec;
}
.conv-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #ff9500, #ff6b00);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
}
.conv-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.conv-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.conv-name {
  font-size: 14px;
  font-weight: 600;
  color: #1d2129;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-time {
  font-size: 11px;
  color: #a0a5b2;
  flex-shrink: 0;
  margin-left: 6px;
}
.conv-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 3px;
  gap: 8px;
}
.conv-last {
  font-size: 12px;
  color: #86909c;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-unread {
  background: #f56c6c;
  color: #fff;
  font-size: 11px;
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  border-radius: 9px;
  padding: 0 5px;
  flex-shrink: 0;
}

/* ===== 右侧聊天区 ===== */
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.chat-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  border-bottom: 1px solid #eef0f4;
  flex-shrink: 0;
}
.chat-peer {
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}
.ws-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #d0d3d9;
}
.ws-dot.open {
  background: #67c23a;
}
.ws-dot.connecting {
  background: #e6a23c;
}
.ws-dot.closed {
  background: #f56c6c;
}

.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  background: #f7f8fa;
}
.load-more {
  text-align: center;
  font-size: 12px;
  color: #ff6b00;
  cursor: pointer;
  margin-bottom: 12px;
}
.msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}
.msg-row.mine {
  flex-direction: row-reverse;
}
.msg-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: #e8ebf0;
  color: #4e5969;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  flex-shrink: 0;
}
.mine .msg-avatar {
  background: linear-gradient(135deg, #ff9500, #ff6b00);
  color: #fff;
}
.msg-body {
  max-width: 70%;
  display: flex;
  flex-direction: column;
}
.mine .msg-body {
  align-items: flex-end;
}
.msg-bubble {
  background: #fff;
  padding: 10px 14px;
  border-radius: 12px;
  border-top-left-radius: 2px;
  font-size: 14px;
  color: #1d2129;
  line-height: 1.6;
  word-break: break-word;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.mine .msg-bubble {
  background: linear-gradient(135deg, #ff9500, #ff6b00);
  color: #fff;
  border-top-left-radius: 12px;
  border-top-right-radius: 2px;
}
.msg-row.pending .msg-bubble {
  opacity: 0.55;
}
.msg-time {
  font-size: 11px;
  color: #a0a5b2;
  margin-top: 4px;
}

.chat-input {
  display: flex;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid #eef0f4;
  flex-shrink: 0;
}
.ws-tip {
  text-align: center;
  font-size: 12px;
  color: #e6a23c;
  padding-bottom: 8px;
  background: #fdf6ec;
}

.chat-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
}
.chat-placeholder p {
  font-size: 13px;
  color: #a0a5b2;
}
</style>
