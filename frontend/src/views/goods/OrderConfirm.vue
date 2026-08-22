<template>
  <div class="order-page">
    <div class="top-nav">
      <el-icon class="back-btn" @click="$router.back()"><ArrowLeft /></el-icon>
      <span class="nav-title">确认订单</span>
      <span></span>
    </div>

    <div v-if="goods" class="order-content">
      <!-- 收货地址/联系方式 -->
      <div class="form-section">
        <div class="section-title">联系方式</div>
        <el-input
          v-model="form.contact"
          placeholder="请填写联系方式（微信号/QQ/手机号）"
          class="simple-input"
        >
          <template #prefix><el-icon><User /></el-icon></template>
        </el-input>
        <el-input
          v-model="form.remark"
          type="textarea"
          :rows="3"
          placeholder="备注信息（选填，如交易地点、取货时间等）"
          class="mt-12 simple-textarea"
          maxlength="200"
          show-word-limit
        />
      </div>

      <!-- 商品信息 -->
      <div class="goods-section">
        <div class="section-title">商品信息</div>
        <div class="goods-card">
          <div class="goods-img-wrap">
            <img v-if="goods.images?.length" :src="goods.images[0].url" class="goods-img" />
            <div v-else class="goods-img-placeholder">
              <el-icon :size="32" color="#ccc"><Picture /></el-icon>
            </div>
          </div>
          <div class="goods-info">
            <div class="goods-title">{{ goods.title }}</div>
            <div class="goods-meta">
              <el-tag size="small" type="warning" effect="plain">{{ goods.condition }}</el-tag>
              <span class="goods-seller">卖家：{{ goods.seller_name }}</span>
            </div>
            <div class="goods-price-row">
              <span class="price-symbol">¥</span>
              <span class="price-num">{{ goods.price }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 价格汇总 -->
      <div class="price-section">
        <div class="price-row">
          <span>商品金额</span>
          <span class="price-text">¥{{ goods.price }}</span>
        </div>
        <div class="price-row total">
          <span>实付款</span>
          <span class="price-total">¥{{ goods.price }}</span>
        </div>
      </div>

      <div class="bottom-placeholder"></div>
    </div>

    <!-- 底部提交栏 -->
    <div class="bottom-bar" v-if="goods">
      <div class="bar-left">
        <span class="total-label">实付款：</span>
        <span class="bar-price-symbol">¥</span>
        <span class="bar-price">{{ goods.price }}</span>
      </div>
      <el-button
        type="primary"
        class="submit-btn"
        :loading="submitting"
        @click="submitOrder"
      >
        提交订单
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Picture, User } from '@element-plus/icons-vue'
import { getGoods } from '@/api/goods'
import { createOrder } from '@/api/orders'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const goods = ref(null)
const submitting = ref(false)
const form = reactive({
  contact: auth.user?.username || '',
  remark: ''
})

onMounted(async () => {
  if (!auth.isAuthenticated) {
    ElMessage.warning('请先登录')
    router.push('/login')
    return
  }
  const goodsId = route.query.goods_id
  if (!goodsId) {
    ElMessage.error('参数错误')
    router.back()
    return
  }
  const res = await getGoods(goodsId)
  goods.value = res.data
})

async function submitOrder() {
  if (!form.contact.trim()) {
    ElMessage.warning('请填写联系方式')
    return
  }
  submitting.value = true
  try {
    await createOrder({
      goods_id: Number(route.query.goods_id),
      contact: form.contact,
      remark: form.remark
    })
    ElMessage.success('下单成功！')
    router.push('/my-orders')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '下单失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.order-page {
  min-height: 100%;
  background: #f5f5f5;
  padding-bottom: 80px;
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

.order-content { padding: 10px; }
.form-section, .goods-section, .price-section {
  background: #fff;
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 10px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
  margin-bottom: 12px;
}
.mt-12 { margin-top: 12px; }
.simple-input :deep(.el-input__wrapper) {
  box-shadow: none;
  background: #f8f8f8;
  border-radius: 8px;
}
.simple-textarea :deep(.el-textarea__inner) {
  box-shadow: none;
  background: #f8f8f8;
  border-radius: 8px;
  border: none;
}

.goods-card {
  display: flex;
  gap: 12px;
}
.goods-img-wrap {
  width: 90px;
  height: 90px;
  border-radius: 8px;
  overflow: hidden;
  background: #f8f8f8;
  flex-shrink: 0;
}
.goods-img { width: 100%; height: 100%; object-fit: cover; }
.goods-img-placeholder {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
}
.goods-info { flex: 1; display: flex; flex-direction: column; }
.goods-title {
  font-size: 14px;
  color: #333;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.goods-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.goods-seller { font-size: 12px; color: #999; }
.goods-price-row {
  margin-top: auto;
  display: flex;
  align-items: baseline;
}
.price-symbol { font-size: 12px; color: #ff4400; font-weight: 600; }
.price-num { font-size: 18px; color: #ff4400; font-weight: 700; }

.price-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  font-size: 14px;
  color: #333;
}
.price-row.total {
  border-top: 1px solid #f0f0f0;
  margin-top: 8px;
  padding-top: 12px;
}
.price-text { color: #333; }
.price-total { font-size: 20px; color: #ff4400; font-weight: 700; }

.bottom-placeholder { height: 20px; }

.bottom-bar {
  position: sticky;
  bottom: 0;
  left: auto;
  right: auto;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  box-shadow: 0 -2px 10px rgba(0,0,0,0.06);
  z-index: 30;
}
.bar-left { display: flex; align-items: baseline; }
.total-label { font-size: 14px; color: #333; }
.bar-price-symbol { font-size: 13px; color: #ff4400; font-weight: 600; margin-left: 4px; }
.bar-price { font-size: 22px; color: #ff4400; font-weight: 700; }
.submit-btn {
  background: linear-gradient(135deg, #ff6b00, #ff8c00);
  border: none;
  border-radius: 22px;
  height: 44px;
  padding: 0 36px;
  font-size: 16px;
  font-weight: 600;
}
.submit-btn:hover {
  background: linear-gradient(135deg, #ff5500, #ff7700) !important;
}
</style>
