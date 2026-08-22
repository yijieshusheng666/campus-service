<template>
  <div class="xianyu-page">
    <!-- 顶部搜索栏 -->
    <div class="top-bar">
      <div class="search-wrap">
        <el-input
          v-model="query.keyword"
          placeholder="搜索你想要的宝贝"
          clearable
          class="search-input"
          @keyup.enter="search"
          @clear="search"
        >
          <template #prefix><el-icon class="search-icon"><Search /></el-icon></template>
        </el-input>
        <el-button type="primary" class="publish-btn" @click="$router.push('/goods-publish')">
          <el-icon><Plus /></el-icon>
          卖闲置
        </el-button>
      </div>
      <!-- 分类标签栏 -->
      <div class="category-bar">
        <span
          class="cat-tag"
          :class="{ active: !query.category }"
          @click="selectCategory('')"
        >全部</span>
        <span
          v-for="c in categoryList"
          :key="c"
          class="cat-tag"
          :class="{ active: query.category === c }"
          @click="selectCategory(c)"
        >{{ c }}</span>
      </div>
      <!-- 排序栏 -->
      <div class="sort-bar">
        <span
          class="sort-item"
          :class="{ active: query.sort === 'latest' }"
          @click="setSort('latest')"
        >最新</span>
        <span
          class="sort-item"
          :class="{ active: query.sort === 'price_asc' }"
          @click="setSort('price_asc')"
        >价格↑</span>
        <span
          class="sort-item"
          :class="{ active: query.sort === 'price_desc' }"
          @click="setSort('price_desc')"
        >价格↓</span>
      </div>
    </div>

    <!-- 商品瀑布流 -->
    <div class="goods-waterfall" v-loading="loading">
      <div
        v-for="g in list"
        :key="g.id"
        class="goods-item"
        @click="$router.push(`/goods/${g.id}`)"
      >
        <div class="goods-cover-wrap">
          <img
            v-if="g.images?.length"
            :src="g.images[0].url"
            class="goods-cover"
            loading="lazy"
          />
          <div v-else class="goods-cover-placeholder">
            <el-icon :size="48" color="#ccc"><Picture /></el-icon>
          </div>
          <span v-if="g.condition" class="condition-tag">{{ g.condition }}</span>
        </div>
        <div class="goods-info">
          <div class="goods-title">{{ g.title }}</div>
          <div class="goods-price-row">
            <span class="price-symbol">¥</span>
            <span class="price-num">{{ g.price }}</span>
          </div>
          <div class="goods-meta">
            <span class="seller-name">{{ g.seller_name }}</span>
            <span class="goods-cat">{{ g.category }}</span>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-if="!loading && !list.length" description="暂无相关宝贝" :image-size="120" />

    <div v-if="total > query.page_size" class="load-more">
      <el-button v-if="query.page * query.page_size < total" @click="loadMore" :loading="loading">加载更多</el-button>
      <span v-else class="no-more">没有更多了</span>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Search, Plus, Picture } from '@element-plus/icons-vue'
import { listGoods, categories } from '@/api/goods'

const list = ref([])
const total = ref(0)
const loading = ref(false)
const categoryList = ref([])
const query = reactive({ page: 1, page_size: 10, keyword: '', category: '', sort: 'latest' })

async function load() {
  loading.value = true
  try {
    const res = await listGoods(query)
    list.value = res.data.items
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loading.value) return
  query.page += 1
  loading.value = true
  try {
    const res = await listGoods(query)
    list.value.push(...res.data.items)
    total.value = res.data.total
  } finally {
    loading.value = false
  }
}

function search() {
  query.page = 1
  load()
}
function selectCategory(cat) {
  query.category = cat
  search()
}
function setSort(sort) {
  query.sort = sort
  search()
}

onMounted(async () => {
  load()
  try {
    const res = await categories()
    categoryList.value = res.data
  } catch (e) {}
})
</script>

<style scoped>
.xianyu-page {
  min-height: 100%;
  background: #f5f5f5;
  padding-bottom: 40px;
}

/* ===== 顶部栏 ===== */
.top-bar {
  background: #fff;
  padding: 12px 16px 0;
  position: sticky;
  top: 0;
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.search-wrap {
  display: flex;
  gap: 10px;
  align-items: center;
}
.search-input {
  flex: 1;
}
.search-input :deep(.el-input__wrapper) {
  background: #f5f5f5;
  border-radius: 20px;
  box-shadow: none;
}
.search-icon {
  color: #999;
}
.publish-btn {
  background: linear-gradient(135deg, #ff6b00, #ff8c00);
  border: none;
  border-radius: 20px;
  padding: 0 18px;
  height: 36px;
  font-weight: 500;
}
.publish-btn:hover {
  background: linear-gradient(135deg, #ff5500, #ff7700) !important;
}

.category-bar {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 12px 0 8px;
  scrollbar-width: none;
}
.category-bar::-webkit-scrollbar { display: none; }
.cat-tag {
  flex-shrink: 0;
  padding: 6px 14px;
  font-size: 14px;
  color: #666;
  background: #f5f5f5;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s;
}
.cat-tag.active {
  color: #ff6b00;
  background: #fff3e8;
  font-weight: 600;
}

.sort-bar {
  display: flex;
  gap: 20px;
  padding: 8px 0 10px;
  border-top: 1px solid #f0f0f0;
}
.sort-item {
  font-size: 13px;
  color: #999;
  cursor: pointer;
  padding: 2px 0;
}
.sort-item.active {
  color: #333;
  font-weight: 600;
  position: relative;
}
.sort-item.active::after {
  content: '';
  position: absolute;
  bottom: -10px;
  left: 50%;
  transform: translateX(-50%);
  width: 20px;
  height: 3px;
  background: #ff6b00;
  border-radius: 2px;
}

/* ===== 瀑布流 ===== */
.goods-waterfall {
  padding: 10px 8px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
@media (min-width: 640px) {
  .goods-waterfall { grid-template-columns: repeat(3, 1fr); gap: 12px; padding: 12px; }
}
@media (min-width: 900px) {
  .goods-waterfall { grid-template-columns: repeat(4, 1fr); gap: 14px; }
}
@media (min-width: 1200px) {
  .goods-waterfall { grid-template-columns: repeat(5, 1fr); gap: 16px; }
}
.goods-item {
  background: #fff;
  border-radius: 10px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.15s;
}
.goods-item:active {
  transform: scale(0.98);
}
.goods-cover-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 1;
  background: #f8f8f8;
  overflow: hidden;
}
.goods-cover {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.goods-cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.condition-tag {
  position: absolute;
  left: 6px;
  bottom: 6px;
  background: rgba(0,0,0,0.55);
  color: #fff;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
}
.goods-info {
  padding: 8px 10px 10px;
}
.goods-title {
  font-size: 14px;
  color: #333;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 39px;
  word-break: break-all;
}
.goods-price-row {
  margin-top: 6px;
  display: flex;
  align-items: baseline;
}
.price-symbol {
  font-size: 13px;
  color: #ff4400;
  font-weight: 600;
}
.price-num {
  font-size: 20px;
  color: #ff4400;
  font-weight: 700;
  margin-left: 1px;
}
.goods-meta {
  margin-top: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #999;
}
.seller-name {
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.goods-cat {
  color: #bbb;
  font-size: 11px;
}

.load-more {
  text-align: center;
  padding: 20px 0;
}
.no-more {
  font-size: 13px;
  color: #ccc;
}
</style>
