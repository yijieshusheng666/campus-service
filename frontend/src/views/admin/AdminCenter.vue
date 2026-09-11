<template>
  <div class="admin-page">
    <div class="page-header">
      <span class="header-title">管理后台</span>
      <span class="header-hint">仅管理员可见</span>
    </div>

    <!-- 非管理员访问时的说明。后端已经返回 403，这里只是把原因讲清楚 -->
    <el-alert
      v-if="forbidden"
      type="error"
      :closable="false"
      show-icon
      class="alert"
      title="当前账号没有管理员权限"
      description="管理后台只对 is_admin 账号开放。请在服务器上执行：cd /opt/campus/backend && .venv/bin/python scripts/create_admin.py --promote 你的用户名"
    />

    <el-tabs v-if="!forbidden" v-model="tab" class="admin-tabs" @tab-change="onTabChange">
      <!-- ================= 总览 ================= -->
      <el-tab-pane label="总览" name="stats">
        <div v-loading="loading.stats" class="stat-grid">
          <div v-for="c in statCards" :key="c.key" class="stat-card">
            <div class="stat-label">{{ c.label }}</div>
            <div class="stat-value">{{ stats[c.key] ?? 0 }}</div>
            <div v-if="c.sub" class="stat-sub">{{ c.sub }}</div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ================= 用户 ================= -->
      <el-tab-pane label="用户" name="users">
        <div class="toolbar">
          <el-input
            v-model="userKeyword"
            placeholder="按用户名或邮箱搜索"
            clearable
            style="width: 260px"
            @keyup.enter="loadUsers"
            @clear="loadUsers"
          />
          <el-button type="primary" @click="loadUsers">搜索</el-button>
          <span class="toolbar-hint">共 {{ users.length }} 条</span>
        </div>
        <el-table :data="users" v-loading="loading.users" stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="username" label="用户名" min-width="120" />
          <el-table-column prop="nickname" label="昵称" min-width="110" />
          <el-table-column prop="email" label="邮箱" min-width="190" />
          <el-table-column label="角色" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.is_admin" type="warning" size="small">管理员</el-tag>
              <el-tag v-else type="info" size="small">普通用户</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
                {{ row.is_active ? '正常' : '已封禁' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="注册时间" width="170">
            <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="110" fixed="right">
            <template #default="{ row }">
              <el-button
                size="small"
                text
                :type="row.is_active ? 'danger' : 'success'"
                :disabled="row.is_admin"
                @click="toggleUser(row)"
              >
                {{ row.is_active ? '封禁' : '解封' }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ================= 商品 ================= -->
      <el-tab-pane label="商品" name="goods">
        <div class="toolbar">
          <el-select v-model="goodsStatus" placeholder="全部状态" clearable style="width: 150px" @change="loadGoods">
            <el-option label="在售" value="on_sale" />
            <el-option label="已售" value="sold" />
            <el-option label="已下架" value="off_shelf" />
          </el-select>
          <el-button @click="loadGoods">刷新</el-button>
          <span class="toolbar-hint">共 {{ goods.length }} 条</span>
        </div>
        <el-table :data="goods" v-loading="loading.goods" stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
          <el-table-column label="价格" width="100">
            <template #default="{ row }">¥{{ row.price }}</template>
          </el-table-column>
          <el-table-column prop="category" label="分类" width="100" />
          <el-table-column label="卖家" min-width="120">
            <template #default="{ row }">{{ row.seller_name }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="goodsTagType(row.status)" size="small">
                {{ GOODS_STATUS[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status !== 'off_shelf'"
                size="small"
                text
                type="warning"
                @click="changeGoodsStatus(row, 'off_shelf')"
              >
                下架
              </el-button>
              <el-button
                v-else
                size="small"
                text
                type="success"
                @click="changeGoodsStatus(row, 'on_sale')"
              >
                恢复上架
              </el-button>
              <el-button size="small" text type="danger" @click="removeGoods(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ================= 订单 ================= -->
      <el-tab-pane label="订单" name="orders">
        <div class="toolbar">
          <el-button @click="loadOrders">刷新</el-button>
          <span class="toolbar-hint">共 {{ orders.length }} 条（只读）</span>
        </div>
        <el-table :data="orders" v-loading="loading.orders" stripe>
          <el-table-column prop="order_no" label="订单号" width="190" />
          <el-table-column label="商品" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.goods_title || row.goods?.title }}</template>
          </el-table-column>
          <el-table-column label="买家" width="110">
            <template #default="{ row }">{{ row.buyer?.username }}</template>
          </el-table-column>
          <el-table-column label="卖家" width="110">
            <template #default="{ row }">{{ row.seller?.username }}</template>
          </el-table-column>
          <el-table-column label="金额" width="100">
            <template #default="{ row }">¥{{ row.price }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="orderTagType(row.status)" size="small">
                {{ ORDER_STATUS[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="下单时间" width="170">
            <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ================= 跑腿 ================= -->
      <el-tab-pane label="校园跑腿" name="errands">
        <div class="toolbar">
          <el-button @click="loadErrands">刷新</el-button>
          <span class="toolbar-hint">共 {{ errands.length }} 条</span>
        </div>
        <el-table :data="errands" v-loading="loading.errands" stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="pickup_location" label="取件点" min-width="140" show-overflow-tooltip />
          <el-table-column prop="dropoff_location" label="送达点" min-width="140" show-overflow-tooltip />
          <el-table-column label="悬赏" width="90">
            <template #default="{ row }">¥{{ row.reward }}</template>
          </el-table-column>
          <el-table-column label="发布者" width="110">
            <template #default="{ row }">{{ row.publisher?.username }}</template>
          </el-table-column>
          <el-table-column label="接单人" width="110">
            <template #default="{ row }">{{ row.runner?.username || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="errandTagType(row.status)" size="small">
                {{ ERRAND_STATUS[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90" fixed="right">
            <template #default="{ row }">
              <el-button size="small" text type="danger" @click="removeErrand(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ================= 私信 ================= -->
      <el-tab-pane label="站内私信" name="messages">
        <div class="toolbar">
          <el-button @click="loadMessages">刷新</el-button>
          <span class="toolbar-hint">共 {{ messages.length }} 条（只读，仅用于风控排查）</span>
        </div>
        <el-table :data="messages" v-loading="loading.messages" stripe>
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="sender_id" label="发送者 ID" width="100" />
          <el-table-column prop="receiver_id" label="接收者 ID" width="100" />
          <el-table-column prop="content" label="内容" min-width="260" show-overflow-tooltip />
          <el-table-column label="已读" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_read ? 'success' : 'info'" size="small">
                {{ row.is_read ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import {
  deleteErrand,
  deleteGoods,
  getStats,
  listErrands,
  listGoods,
  listMessages,
  listOrders,
  listUsers,
  setGoodsStatus,
  setUserActive
} from '@/api/admin'

const auth = useAuthStore()

const tab = ref('stats')
const forbidden = ref(false)

const stats = ref({})
const users = ref([])
const goods = ref([])
const orders = ref([])
const errands = ref([])
const messages = ref([])

const loading = reactive({ stats: false, users: false, goods: false, orders: false, errands: false, messages: false })

const userKeyword = ref('')
const goodsStatus = ref('')

const GOODS_STATUS = { on_sale: '在售', sold: '已售', off_shelf: '已下架' }
const ORDER_STATUS = { pending: '待确认', paid: '已付款', shipped: '已发货', completed: '已完成', cancelled: '已取消' }
const ERRAND_STATUS = { pending: '待接单', accepted: '已接单', delivered: '已送达', completed: '已完成', cancelled: '已取消' }

const statCards = computed(() => [
  { key: 'users', label: '用户总数', sub: `管理员 ${stats.value.admins ?? 0} · 正常 ${stats.value.users_active ?? 0}` },
  { key: 'goods', label: '商品总数', sub: `在售 ${stats.value.goods_on_sale ?? 0} · 下架 ${stats.value.goods_off_shelf ?? 0}` },
  { key: 'orders', label: '订单总数', sub: `已完成 ${stats.value.orders_completed ?? 0}` },
  { key: 'errands', label: '跑腿需求', sub: `待接单 ${stats.value.errands_pending ?? 0}` },
  { key: 'messages', label: '私信条数', sub: '仅统计，不展示内容' },
  { key: 'resumes', label: '简历份数', sub: '隐私数据，不提供浏览' },
  { key: 'interviews', label: '模拟面试场次', sub: '隐私数据，不提供浏览' },
  { key: 'admins', label: '管理员数量', sub: '仅能通过服务器脚本增减' }
])

function fmtTime(s) {
  if (!s) return '—'
  return new Date(s).toLocaleString('zh-CN', { hour12: false })
}
function goodsTagType(s) {
  return { on_sale: 'success', sold: 'info', off_shelf: 'warning' }[s] || 'info'
}
function orderTagType(s) {
  return { pending: 'warning', paid: 'primary', shipped: 'primary', completed: 'success', cancelled: 'info' }[s] || 'info'
}
function errandTagType(s) {
  return { pending: 'warning', accepted: 'primary', delivered: 'primary', completed: 'success', cancelled: 'info' }[s] || 'info'
}

// 统一包一层：403 代表「登录了但不是管理员」，与 401（未登录，拦截器已处理）区分开
async function guard(fn, flag) {
  if (flag) loading[flag] = true
  try {
    await fn()
  } catch (e) {
    if (e.response?.status === 403) forbidden.value = true
  } finally {
    if (flag) loading[flag] = false
  }
}

const loadStats = () => guard(async () => { stats.value = (await getStats()).data }, 'stats')
const loadUsers = () => guard(async () => {
  users.value = (await listUsers({ keyword: userKeyword.value || undefined })).data
}, 'users')
const loadGoods = () => guard(async () => {
  goods.value = (await listGoods({ status: goodsStatus.value || undefined })).data
}, 'goods')
const loadOrders = () => guard(async () => { orders.value = (await listOrders()).data }, 'orders')
const loadErrands = () => guard(async () => { errands.value = (await listErrands()).data }, 'errands')
const loadMessages = () => guard(async () => { messages.value = (await listMessages()).data }, 'messages')

// 每个页签首次点开才加载，避免一进页面就打 6 个请求
const loaders = {
  stats: loadStats,
  users: loadUsers,
  goods: loadGoods,
  orders: loadOrders,
  errands: loadErrands,
  messages: loadMessages
}
const loaded = new Set()
function onTabChange(name) {
  if (loaded.has(name)) return
  loaded.add(name)
  loaders[name]?.()
}

async function toggleUser(row) {
  const action = row.is_active ? '封禁' : '解封'
  await ElMessageBox.confirm(`确定要${action}用户「${row.username}」吗？`, '确认', { type: 'warning' })
  await setUserActive(row.id, !row.is_active)
  ElMessage.success(`已${action}`)
  loadUsers()
}

async function changeGoodsStatus(row, status) {
  await setGoodsStatus(row.id, status)
  ElMessage.success(status === 'off_shelf' ? '已下架' : '已恢复上架')
  loadGoods()
}

async function removeGoods(row) {
  await ElMessageBox.confirm(`确定删除商品「${row.title}」？此操作不可恢复。`, '删除确认', {
    type: 'warning',
    confirmButtonText: '确认删除',
    confirmButtonClass: 'el-button--danger'
  })
  try {
    await deleteGoods(row.id)
    ElMessage.success('已删除')
    loadGoods()
  } catch (e) {
    // 后端会在「该商品已有订单」时返回 400 并说明原因，这里原样透出即可
    ElMessage.warning(e.response?.data?.detail || '删除失败')
  }
}

async function removeErrand(row) {
  await ElMessageBox.confirm(`确定删除跑腿需求 #${row.id}？`, '删除确认', {
    type: 'warning',
    confirmButtonText: '确认删除',
    confirmButtonClass: 'el-button--danger'
  })
  await deleteErrand(row.id)
  ElMessage.success('已删除')
  loadErrands()
}

onMounted(() => {
  loaded.add('stats')
  loadStats()
})
</script>

<style scoped>
.admin-page {
  min-height: 100%;
  background: #f5f7fa;
}
.page-header {
  background: #fff;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.05);
}
.header-title {
  font-size: 16px;
  font-weight: 600;
  color: #1d2129;
}
.header-hint {
  font-size: 12px;
  color: #a0a5b2;
}
.alert {
  margin: 12px;
}
.admin-tabs {
  padding: 0 12px 12px;
}
.admin-tabs :deep(.el-tabs__header) {
  background: #fff;
  margin: 0 -12px 12px;
  padding: 0 12px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}
.stat-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px 16px;
}
.stat-label {
  font-size: 13px;
  color: #86909c;
}
.stat-value {
  font-size: 26px;
  font-weight: 700;
  color: #1d2129;
  line-height: 1.4;
}
.stat-sub {
  font-size: 12px;
  color: #a0a5b2;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.toolbar-hint {
  font-size: 12px;
  color: #86909c;
  margin-left: auto;
}
:deep(.el-table) {
  border-radius: 10px;
  overflow: hidden;
}
</style>
