<template>
  <div class="detail-page">
    <!-- 顶部返回栏 -->
    <div class="top-nav">
      <el-icon class="back-btn" @click="$router.back()"><ArrowLeft /></el-icon>
      <span class="nav-title">宝贝详情</span>
      <span></span>
    </div>

    <div v-if="goods" class="detail-content">
      <!-- 图片轮播 -->
      <div class="img-swiper">
        <el-carousel
          v-if="goods.images?.length"
          :autoplay="false"
          indicator-position="outside"
          height="375px"
        >
          <el-carousel-item v-for="(img, i) in goods.images" :key="i">
            <img :src="img.url" class="swiper-img" @click="previewImg(i)" />
          </el-carousel-item>
        </el-carousel>
        <div v-else class="swiper-placeholder">
          <el-icon :size="60" color="#ddd"><Picture /></el-icon>
        </div>
        <div v-if="goods.images?.length" class="img-count">
          {{ currentImgIndex + 1 }}/{{ goods.images.length }}
        </div>
      </div>

      <!-- 价格区域 -->
      <div class="price-section">
        <div class="price-main">
          <span class="price-symbol">¥</span>
          <span class="price-value">{{ goods.price }}</span>
        </div>
        <div class="price-tags">
          <el-tag size="small" type="warning" effect="plain">{{ goods.condition }}</el-tag>
          <el-tag size="small" type="info" effect="plain">{{ goods.category }}</el-tag>
        </div>
        <h2 class="goods-title">{{ goods.title }}</h2>
      </div>

      <!-- 卖家信息 -->
      <div class="seller-card">
        <div class="seller-avatar">
          <el-icon :size="28" color="#ff6b00"><User /></el-icon>
        </div>
        <div class="seller-info">
          <div class="seller-name">{{ goods.seller_name }}</div>
          <div class="seller-meta">校园卖家</div>
        </div>
        <el-button v-if="!isOwner" type="warning" size="small" plain class="chat-btn" @click="handleChat">
          <el-icon><ChatDotRound /></el-icon>
          聊一聊
        </el-button>
      </div>

      <!-- 商品描述 -->
      <div class="desc-section">
        <h4 class="section-title">宝贝描述</h4>
        <p class="desc-text" style="white-space: pre-wrap">{{ goods.description }}</p>
      </div>

      <!-- 发布信息 -->
      <div class="info-section">
        <div class="info-item">
          <span class="info-label">联系方式</span>
          <span class="info-value">{{ goods.contact || '私聊联系' }}</span>
        </div>
        <div class="info-item">
          <span class="info-label">发布时间</span>
          <span class="info-value">{{ formatTime(goods.created_at) }}</span>
        </div>
      </div>

      <div class="bottom-placeholder"></div>
    </div>

    <!-- 底部操作栏 -->
    <div v-if="goods" class="bottom-bar">
      <div class="bar-left">
        <div
          class="bar-action"
          :class="{ active: goods.is_favorited }"
          @click="toggleFav"
        >
          <el-icon :size="22">
            <StarFilled v-if="goods.is_favorited" />
            <Star v-else />
          </el-icon>
          <span class="bar-text">{{ goods.is_favorited ? '已收藏' : '收藏' }}</span>
        </div>
        <div class="bar-action" v-if="isOwner" @click="$router.push({ path: '/goods-publish', query: { id: goods.id } })">
          <el-icon :size="22"><Edit /></el-icon>
          <span class="bar-text">编辑</span>
        </div>
      </div>
      <div class="bar-right">
        <el-button v-if="!isOwner && isOnSale" type="warning" class="want-btn" @click="handleWant">
          我想要
        </el-button>
        <el-button v-else-if="!isOwner" type="info" disabled class="want-btn sold-btn">
          {{ goods.status === 'sold' ? '已售出' : '已下架' }}
        </el-button>
        <el-button v-if="isOwner" type="danger" plain class="del-btn" @click="onDelete">
          删除
        </el-button>
      </div>
    </div>

    <!-- 图片预览 -->
    <el-image-viewer
      v-if="imgViewerVisible"
      :url-list="goods?.images?.map(i => i.url) || []"
      :initial-index="currentImgIndex"
      @close="imgViewerVisible = false"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Picture, User, ChatDotRound, Star, StarFilled, Edit } from '@element-plus/icons-vue'
import { getGoods, deleteGoods, addFavorite, removeFavorite } from '@/api/goods'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const goods = ref(null)
const loading = ref(false)
const imgViewerVisible = ref(false)
const currentImgIndex = ref(0)

const isOwner = computed(() => goods.value && auth.user && goods.value.seller_id === auth.user.id || goods.value?.seller_name === auth.user?.username)
const isOnSale = computed(() => goods.value?.status === 'on_sale')

function formatTime(timeStr) {
  if (!timeStr) return ''
  const d = new Date(timeStr)
  return `${d.getMonth()+1}月${d.getDate()}日`
}

function previewImg(idx) {
  currentImgIndex.value = idx
  imgViewerVisible.value = true
}

async function load() {
  loading.value = true
  try {
    const res = await getGoods(route.params.id)
    goods.value = res.data
  } finally {
    loading.value = false
  }
}

async function toggleFav() {
  if (!auth.isAuthenticated) {
    router.push('/login')
    return
  }
  if (goods.value.is_favorited) {
    await removeFavorite(goods.value.id)
    goods.value.is_favorited = false
    ElMessage.success('已取消收藏')
  } else {
    await addFavorite(goods.value.id)
    goods.value.is_favorited = true
    ElMessage.success('已收藏')
  }
}

function handleWant() {
  if (!auth.isAuthenticated) {
    router.push('/login')
    return
  }
  router.push({ path: '/order-confirm', query: { goods_id: goods.value.id } })
}

function handleChat() {
  if (!auth.isAuthenticated) {
    router.push('/login')
    return
  }
  router.push({ name: 'Chat', params: { userId: goods.value.seller_id } })
}

async function onDelete() {
  await ElMessageBox.confirm('确定删除该商品？', '提示', { type: 'warning' })
  await deleteGoods(goods.value.id)
  ElMessage.success('已删除')
  router.push('/my-goods')
}

onMounted(load)
</script>

<style scoped>
.detail-page {
  min-height: 100%;
  background: #f5f5f5;
}

/* ===== 顶部导航 ===== */
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
.back-btn {
  font-size: 22px;
  cursor: pointer;
  color: #333;
}
.nav-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

/* ===== 图片轮播 ===== */
.img-swiper {
  position: relative;
  background: #fff;
}
.img-swiper :deep(.el-carousel__container) {
  height: 375px !important;
}
.img-swiper :deep(.el-carousel__indicators--outside) {
  margin-top: -30px;
  position: absolute;
  bottom: 10px;
}
.img-swiper :deep(.el-carousel__indicator .el-carousel__button) {
  background: rgba(255,255,255,0.6);
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.img-swiper :deep(.el-carousel__indicator.is-active .el-carousel__button) {
  background: #fff;
  width: 18px;
  border-radius: 3px;
}
.swiper-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  cursor: pointer;
}
.swiper-placeholder {
  height: 375px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8f8f8;
}
.img-count {
  position: absolute;
  right: 12px;
  bottom: 40px;
  background: rgba(0,0,0,0.5);
  color: #fff;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}

/* ===== 价格区域 ===== */
.price-section {
  background: #fff;
  padding: 14px 16px 16px;
  margin-bottom: 8px;
}
.price-main {
  display: flex;
  align-items: baseline;
}
.price-symbol {
  font-size: 16px;
  color: #ff4400;
  font-weight: 700;
}
.price-value {
  font-size: 28px;
  color: #ff4400;
  font-weight: 700;
  margin-left: 2px;
}
.price-tags {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.goods-title {
  font-size: 16px;
  font-weight: 500;
  color: #333;
  margin: 12px 0 0;
  line-height: 1.5;
}

/* ===== 卖家卡片 ===== */
.seller-card {
  background: #fff;
  padding: 14px 16px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.seller-avatar {
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: #fff3e8;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.seller-info {
  flex: 1;
}
.seller-name {
  font-size: 15px;
  font-weight: 500;
  color: #333;
}
.seller-meta {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}
.chat-btn {
  border-radius: 16px;
  border-color: #ff6b00;
  color: #ff6b00;
}
.chat-btn:hover {
  background: #fff3e8 !important;
  border-color: #ff6b00 !important;
  color: #ff6b00 !important;
}

/* ===== 描述区域 ===== */
.desc-section, .info-section {
  background: #fff;
  padding: 14px 16px;
  margin-bottom: 8px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
  margin: 0 0 10px;
}
.desc-text {
  font-size: 14px;
  color: #333;
  line-height: 1.7;
  margin: 0;
}

.info-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  font-size: 14px;
}
.info-label {
  color: #999;
}
.info-value {
  color: #333;
}

.bottom-placeholder {
  height: 20px;
}

/* ===== 底部操作栏 ===== */
.bottom-bar {
  position: sticky;
  bottom: 0;
  left: auto;
  right: auto;
  height: 56px;
  background: #fff;
  display: flex;
  align-items: center;
  padding: 0 12px;
  box-shadow: 0 -2px 10px rgba(0,0,0,0.06);
  z-index: 30;
  margin-top: auto;
}
.bar-left {
  display: flex;
  gap: 16px;
}
.bar-action {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  cursor: pointer;
  color: #666;
  min-width: 44px;
}
.bar-action.active {
  color: #ff6b00;
}
.bar-text {
  font-size: 11px;
}
.bar-right {
  flex: 1;
  margin-left: 16px;
  display: flex;
  gap: 10px;
}
.want-btn {
  flex: 1;
  height: 40px;
  background: linear-gradient(135deg, #ff6b00, #ff8c00);
  border: none;
  border-radius: 20px;
  font-size: 16px;
  font-weight: 600;
}
.want-btn:hover {
  background: linear-gradient(135deg, #ff5500, #ff7700) !important;
}
.del-btn {
  height: 40px;
  border-radius: 20px;
}
</style>
