<template>
  <div class="fav-page">
    <!-- 顶部栏 -->
    <div class="page-header">
      <el-icon class="back-btn" @click="$router.back()"><ArrowLeft /></el-icon>
      <span class="header-title">我的收藏</span>
      <span></span>
    </div>

    <!-- 收藏列表 -->
    <div class="fav-list" v-loading="loading">
      <div
        v-for="item in list"
        :key="item.id"
        class="fav-card"
        @click="$router.push(`/goods/${item.id}`)"
      >
        <div class="card-img-wrap">
          <img
            v-if="item.images?.length"
            :src="item.images[0].url"
            class="card-img"
          />
          <div v-else class="card-img-placeholder">
            <el-icon :size="32" color="#ccc"><Picture /></el-icon>
          </div>
        </div>
        <div class="card-info">
          <div class="card-title">{{ item.title }}</div>
          <div class="card-desc" v-if="item.description">{{ item.description.slice(0, 40) }}{{ item.description.length > 40 ? '...' : '' }}</div>
          <div class="card-bottom">
            <div class="card-price">
              <span class="price-symbol">¥</span>
              <span class="price-num">{{ item.price }}</span>
            </div>
            <el-button size="small" text type="danger" @click.stop="unfav(item)">
              取消收藏
            </el-button>
          </div>
          <div class="seller-info">
            <el-icon :size="14" color="#999"><User /></el-icon>
            <span>{{ item.seller_name }}</span>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-if="!loading && !list.length" description="还没有收藏宝贝" :image-size="100" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Picture, User } from '@element-plus/icons-vue'
import { myFavorites, removeFavorite } from '@/api/goods'

const list = ref([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await myFavorites()
    list.value = res.data
  } finally {
    loading.value = false
  }
}
async function unfav(row) {
  await removeFavorite(row.id)
  ElMessage.success('已取消收藏')
  load()
}
onMounted(load)
</script>

<style scoped>
.fav-page {
  min-height: 100%;
  background: #f5f5f5;
}

.page-header {
  position: sticky;
  top: 0;
  z-index: 10;
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
.header-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

.fav-list {
  padding: 10px;
}
.fav-card {
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 10px;
  display: flex;
  cursor: pointer;
}
.card-img-wrap {
  width: 110px;
  height: 110px;
  flex-shrink: 0;
  background: #f8f8f8;
}
.card-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.card-img-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.card-info {
  flex: 1;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
}
.card-title {
  font-size: 14px;
  color: #333;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-desc {
  font-size: 12px;
  color: #999;
  margin-top: 6px;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-bottom {
  margin-top: auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-price {
  display: flex;
  align-items: baseline;
}
.price-symbol {
  font-size: 12px;
  color: #ff4400;
  font-weight: 600;
}
.price-num {
  font-size: 18px;
  color: #ff4400;
  font-weight: 700;
}
.seller-info {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
</style>
