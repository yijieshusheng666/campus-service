<template>
  <div class="orders-page">
    <div class="top-nav">
      <el-icon class="back-btn" @click="$router.push('/goods')"><ArrowLeft /></el-icon>
      <span class="nav-title">我的订单</span>
      <span></span>
    </div>

    <!-- 角色切换 -->
    <div class="role-tabs">
      <span
        class="role-tab"
        :class="{ active: activeRole === 'buyer' }"
        @click="switchRole('buyer')"
      >我买到的</span>
      <span
        class="role-tab"
        :class="{ active: activeRole === 'seller' }"
        @click="switchRole('seller')"
      >我卖出的</span>
    </div>

    <!-- 订单列表 -->
    <div class="orders-list" v-loading="loading">
      <div v-for="order in orders" :key="order.id" class="order-card">
        <div class="order-header">
          <span class="order-no">订单号：{{ order.order_no }}</span>
          <span class="order-status" :class="'status-' + order.status">
            {{ statusText[order.status] }}
          </span>
        </div>
        <div class="order-goods" @click="$router.push(`/goods/${order.goods_id}`)">
          <div class="goods-img-wrap">
            <img v-if="order.goods_cover" :src="order.goods_cover" class="goods-img" />
            <div v-else class="goods-img-placeholder">
              <el-icon :size="28" color="#ccc"><Picture /></el-icon>
            </div>
          </div>
          <div class="goods-info">
            <div class="goods-title">{{ order.goods_title }}</div>
            <div class="goods-price">
              <span class="price-symbol">¥</span>
              <span class="price-num">{{ order.price }}</span>
            </div>
            <div class="goods-party">
              <template v-if="activeRole === 'buyer'">
                卖家：{{ order.seller?.username }}
              </template>
              <template v-else>
                买家：{{ order.buyer?.username }}
              </template>
            </div>
          </div>
        </div>
        <div v-if="order.remark" class="order-remark">备注：{{ order.remark }}</div>
        <div class="order-footer">
          <span class="order-time">{{ formatTime(order.created_at) }}</span>
          <div class="order-actions">
            <!-- 买家视角 -->
            <template v-if="activeRole === 'buyer'">
              <el-button
                v-if="order.status === 'pending'"
                size="small"
                type="primary"
                @click="payOrder(order)"
              >付款</el-button>
              <el-button
                v-if="order.status === 'shipped'"
                size="small"
                type="success"
                @click="confirmReceive(order)"
              >确认收货</el-button>
              <el-button
                v-if="order.status === 'pending'"
                size="small"
                text
                type="danger"
                @click="cancelOrder(order)"
              >取消订单</el-button>
            </template>
            <!-- 卖家视角 -->
            <template v-else>
              <el-button
                v-if="order.status === 'paid'"
                size="small"
                type="warning"
                @click="shipOrder(order)"
              >发货</el-button>
              <el-button
                v-if="order.status === 'pending'"
                size="small"
                text
                type="danger"
                @click="cancelOrder(order)"
              >取消订单</el-button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-if="!loading && !orders.length" description="暂无订单" :image-size="100" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Picture } from '@element-plus/icons-vue'
import { myOrders, updateOrderStatus } from '@/api/orders'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const orders = ref([])
const loading = ref(false)
const activeRole = ref('buyer')

const statusText = {
  pending: '待付款',
  paid: '待发货',
  shipped: '待收货',
  completed: '已完成',
  cancelled: '已取消'
}

function formatTime(timeStr) {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  return `${d.getMonth()+1}-${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

async function load() {
  if (!auth.isAuthenticated) {
    router.push('/login')
    return
  }
  loading.value = true
  try {
    const res = await myOrders(activeRole.value)
    orders.value = res.data
  } finally {
    loading.value = false
  }
}

function switchRole(role) {
  activeRole.value = role
  load()
}

async function payOrder(order) {
  await ElMessageBox.confirm('确认已付款给卖家？', '提示', { type: 'warning' })
  await updateOrderStatus(order.id, 'paid')
  ElMessage.success('已标记付款，等待卖家发货')
  load()
}

async function shipOrder(order) {
  await ElMessageBox.confirm('确认已发货？', '提示', { type: 'warning' })
  await updateOrderStatus(order.id, 'shipped')
  ElMessage.success('已发货')
  load()
}

async function confirmReceive(order) {
  await ElMessageBox.confirm('确认已收到商品？确认后订单完成', '提示', { type: 'warning' })
  await updateOrderStatus(order.id, 'completed')
  ElMessage.success('交易完成')
  load()
}

async function cancelOrder(order) {
  await ElMessageBox.confirm('确定取消该订单？', '提示', { type: 'warning' })
  await updateOrderStatus(order.id, 'cancelled')
  ElMessage.success('已取消订单')
  load()
}

onMounted(load)
</script>

<style scoped>
.orders-page {
  min-height: 100%;
  background: #f5f5f5;
}
.top-nav {
  position: sticky;
  top: 0;
  z-index: 20;
  background: #fff;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
.back-btn { font-size: 22px; cursor: pointer; color: #333; }
.nav-title { font-size: 16px; font-weight: 600; color: #333; }

.role-tabs {
  display: flex;
  background: #fff;
  border-bottom: 1px solid #f0f0f0;
}
.role-tab {
  flex: 1;
  text-align: center;
  padding: 12px 0;
  font-size: 15px;
  color: #666;
  cursor: pointer;
  position: relative;
}
.role-tab.active {
  color: #333;
  font-weight: 600;
}
.role-tab.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 28px;
  height: 3px;
  background: #ff6b00;
  border-radius: 2px;
}

.orders-list { padding: 10px; }
.order-card {
  background: #fff;
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 10px;
}
.order-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 10px;
  border-bottom: 1px solid #f5f5f5;
}
.order-no { font-size: 12px; color: #999; }
.order-status { font-size: 13px; font-weight: 500; }
.status-pending { color: #ff6b00; }
.status-paid { color: #e6a23c; }
.status-shipped { color: #409eff; }
.status-completed { color: #67c23a; }
.status-cancelled { color: #999; }

.order-goods {
  display: flex;
  gap: 12px;
  padding: 12px 0;
  cursor: pointer;
}
.goods-img-wrap {
  width: 80px;
  height: 80px;
  border-radius: 8px;
  overflow: hidden;
  background: #f8f8f8;
  flex-shrink: 0;
}
.goods-img { width: 100%; height: 100%; object-fit: cover; }
.goods-img-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
.goods-info { flex: 1; display: flex; flex-direction: column; }
.goods-title {
  font-size: 14px;
  color: #333;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.goods-price {
  margin-top: 6px;
  display: flex;
  align-items: baseline;
}
.price-symbol { font-size: 12px; color: #ff4400; font-weight: 600; }
.price-num { font-size: 17px; color: #ff4400; font-weight: 700; }
.goods-party { font-size: 12px; color: #999; margin-top: auto; }

.order-remark {
  font-size: 13px;
  color: #666;
  padding: 8px 0;
  border-top: 1px solid #f5f5f5;
}

.order-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 10px;
  border-top: 1px solid #f5f5f5;
}
.order-time { font-size: 12px; color: #bbb; }
.order-actions { display: flex; gap: 8px; }
</style>
