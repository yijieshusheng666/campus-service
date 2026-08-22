<template>
  <div class="my-goods-page">
    <!-- 顶部栏 -->
    <div class="page-header">
      <el-icon class="back-btn" @click="$router.back()"><ArrowLeft /></el-icon>
      <span class="header-title">我发布的</span>
      <el-button type="primary" class="publish-btn" @click="$router.push('/goods-publish')">
        <el-icon><Plus /></el-icon>
        发布
      </el-button>
    </div>

    <!-- Tab 切换 -->
    <div class="tab-bar">
      <span
        class="tab-item"
        :class="{ active: activeTab === 'all' }"
        @click="activeTab = 'all'"
      >全部</span>
      <span
        class="tab-item"
        :class="{ active: activeTab === 'on_sale' }"
        @click="activeTab = 'on_sale'"
      >在售中</span>
    </div>

    <!-- 商品列表 -->
    <div class="goods-list" v-loading="loading">
      <div
        v-for="item in filteredList"
        :key="item.id"
        class="goods-card"
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
          <el-tag
            :type="statusType[item.status]"
            size="small"
            class="status-tag"
          >{{ statusMap[item.status] }}</el-tag>
        </div>
        <div class="card-info">
          <div class="card-title">{{ item.title }}</div>
          <div class="card-price">
            <span class="price-symbol">¥</span>
            <span class="price-num">{{ item.price }}</span>
          </div>
          <div class="card-meta">
            <span class="card-cat">{{ item.category }}</span>
            <span class="card-condition">{{ item.condition }}</span>
          </div>
          <div class="card-actions" @click.stop>
            <el-button size="small" text type="primary" @click="$router.push({ path: '/goods-publish', query: { id: item.id } })">
              编辑
            </el-button>
            <el-button size="small" text type="danger" @click="onDelete(item)">
              删除
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-if="!loading && !filteredList.length" description="还没有发布商品" :image-size="100" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Plus, Picture } from '@element-plus/icons-vue'
import { myGoods, deleteGoods } from '@/api/goods'

const list = ref([])
const loading = ref(false)
const activeTab = ref('all')
const statusMap = { on_sale: '在售', sold: '已售', off_shelf: '下架' }
const statusType = { on_sale: 'success', sold: 'info', off_shelf: 'warning' }

const filteredList = computed(() => {
  if (activeTab.value === 'all') return list.value
  return list.value.filter(item => item.status === activeTab.value)
})

async function load() {
  loading.value = true
  try {
    const res = await myGoods()
    list.value = res.data
  } finally {
    loading.value = false
  }
}
async function onDelete(row) {
  await ElMessageBox.confirm(`确定删除「${row.title}」？`, '提示', { type: 'warning' })
  await deleteGoods(row.id)
  ElMessage.success('已删除')
  load()
}
onMounted(load)
</script>

<style scoped>
.my-goods-page {
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
.publish-btn {
  background: linear-gradient(135deg, #ff6b00, #ff8c00);
  border: none;
  border-radius: 16px;
  padding: 0 14px;
  height: 30px;
  font-size: 13px;
}
.publish-btn:hover {
  background: linear-gradient(135deg, #ff5500, #ff7700) !important;
}

.tab-bar {
  display: flex;
  background: #fff;
  padding: 0 16px;
  gap: 24px;
  border-bottom: 1px solid #f0f0f0;
}
.tab-item {
  padding: 12px 0;
  font-size: 15px;
  color: #666;
  cursor: pointer;
  position: relative;
}
.tab-item.active {
  color: #333;
  font-weight: 600;
}
.tab-item.active::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 24px;
  height: 3px;
  background: #ff6b00;
  border-radius: 2px;
}

.goods-list {
  padding: 10px;
}
.goods-card {
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
  margin-bottom: 10px;
  display: flex;
  cursor: pointer;
}
.card-img-wrap {
  position: relative;
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
.status-tag {
  position: absolute;
  left: 4px;
  top: 4px;
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
.card-price {
  margin-top: auto;
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
.card-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
.card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  margin-top: 6px;
}
.card-actions :deep(.el-button) {
  padding: 4px 8px;
  font-size: 12px;
}
</style>
