<template>
  <div class="publish-page">
    <!-- 顶部导航 -->
    <div class="top-nav">
      <el-icon class="back-btn" @click="$router.back()"><ArrowLeft /></el-icon>
      <span class="nav-title">{{ isEdit ? '编辑宝贝' : '发布宝贝' }}</span>
      <span></span>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="publish-form">
      <!-- 图片上传 -->
      <div class="form-section">
        <div class="section-label">
          <span class="required">*</span> 宝贝图片（最多6张）
        </div>
        <div class="upload-grid">
          <div
            v-for="(file, idx) in fileList"
            :key="idx"
            class="upload-item"
          >
            <img :src="file.url" class="upload-img" @click="onPreview(file)" />
            <div class="remove-btn" @click="onRemove(file)">
              <el-icon :size="14" color="#fff"><Close /></el-icon>
            </div>
          </div>
          <el-upload
            v-if="fileList.length < 6"
            :show-file-list="false"
            :http-request="doUpload"
            accept="image/*"
            class="upload-add"
          >
            <div class="upload-add-inner">
              <el-icon :size="28" color="#ccc"><Plus /></el-icon>
              <span class="upload-text">添加图片</span>
            </div>
          </el-upload>
        </div>
      </div>

      <!-- 标题 -->
      <div class="form-section">
        <el-form-item label="标题" prop="title" class="form-item">
          <el-input
            v-model="form.title"
            maxlength="30"
            show-word-limit
            placeholder="宝贝标题（30字以内）"
            class="simple-input"
          />
        </el-form-item>
      </div>

      <!-- 描述 -->
      <div class="form-section">
        <el-form-item label="宝贝描述" prop="description" class="form-item">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="5"
            maxlength="500"
            show-word-limit
            placeholder="描述宝贝情况、入手渠道、转手原因等"
            class="simple-textarea"
          />
        </el-form-item>
      </div>

      <!-- 交易信息 -->
      <div class="form-section">
        <div class="info-row">
          <span class="info-label">价格</span>
          <div class="price-input-wrap">
            <span class="price-prefix">¥</span>
            <el-input
              v-model.number="form.price"
              type="number"
              placeholder="0.00"
              class="price-input"
            />
          </div>
        </div>
        <div class="divider"></div>
        <div class="info-row">
          <span class="info-label">分类</span>
          <el-select v-model="form.category" placeholder="请选择分类" class="info-select" filterable allow-create>
            <el-option v-for="c in categoryList" :key="c" :label="c" :value="c" />
          </el-select>
        </div>
        <div class="divider"></div>
        <div class="info-row">
          <span class="info-label">成色</span>
          <el-select v-model="form.condition" placeholder="请选择成色" class="info-select">
            <el-option v-for="c in conditions" :key="c" :label="c" :value="c" />
          </el-select>
        </div>
        <div class="divider"></div>
        <div class="info-row">
          <span class="info-label">联系方式</span>
          <el-input
            v-model="form.contact"
            placeholder="微信号/QQ/手机号（不填默认私聊）"
            class="info-input"
          />
        </div>
      </div>

      <div class="bottom-placeholder"></div>
    </el-form>

    <!-- 底部发布按钮 -->
    <div class="bottom-bar">
      <el-button
        type="primary"
        class="publish-submit-btn"
        :loading="submitting"
        @click="submit"
      >
        {{ isEdit ? '保存修改' : '立即发布' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Plus, Close } from '@element-plus/icons-vue'
import { createGoods, updateGoods, getGoods, uploadImage, categories } from '@/api/goods'

const route = useRoute()
const router = useRouter()
const formRef = ref()
const submitting = ref(false)
const categoryList = ref([])
const conditions = ['全新', '九成新', '八成新', '七成新', '五成新', '其他']

const isEdit = computed(() => !!route.query.id)
const fileList = ref([])

const form = reactive({
  title: '', category: '', price: null, condition: '九成新',
  contact: '', description: '', image_urls: []
})
const rules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  price: [{ required: true, message: '请输入价格', trigger: 'blur' }],
  description: [{ required: true, message: '请输入描述', trigger: 'blur' }]
}

async function doUpload({ file, onSuccess, onError }) {
  try {
    const res = await uploadImage(file)
    fileList.value.push({ name: res.data.url, url: res.data.url })
    form.image_urls.push(res.data.url)
    onSuccess && onSuccess(res)
  } catch (e) {
    onError && onError(e)
  }
}
function onRemove(file) {
  form.image_urls = form.image_urls.filter((u) => u !== file.url && u !== file.name)
  fileList.value = fileList.value.filter(f => f.url !== file.url)
}
function onPreview(file) {
  window.open(file.url || file.name, '_blank')
}

async function submit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    if (!form.price || form.price <= 0) {
      ElMessage.warning('请输入正确的价格')
      submitting.value = false
      return
    }
    if (isEdit.value) {
      await updateGoods(route.query.id, { ...form })
      ElMessage.success('修改成功')
    } else {
      await createGoods(form)
      ElMessage.success('发布成功')
    }
    router.push('/my-goods')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  categories().then((res) => (categoryList.value = res.data)).catch(() => {})
  if (isEdit.value) {
    const res = await getGoods(route.query.id)
    Object.assign(form, {
      title: res.data.title,
      category: res.data.category,
      price: Number(res.data.price),
      condition: res.data.condition,
      contact: res.data.contact,
      description: res.data.description,
      image_urls: (res.data.images || []).map((i) => i.url)
    })
    fileList.value = form.image_urls.map((u) => ({ name: u, url: u }))
  }
})
</script>

<style scoped>
.publish-page {
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

.publish-form {
  padding: 0;
}
.form-section {
  background: #fff;
  padding: 14px 16px;
  margin-bottom: 10px;
}
.section-label {
  font-size: 15px;
  color: #333;
  font-weight: 500;
  margin-bottom: 12px;
}
.required {
  color: #ff4400;
  margin-right: 2px;
}
.form-item {
  margin-bottom: 0 !important;
}
.form-item :deep(.el-form-item__label) {
  font-size: 15px;
  font-weight: 500;
  color: #333;
  padding-bottom: 8px;
}
.simple-input :deep(.el-input__wrapper) {
  box-shadow: none;
  background: #f8f8f8;
  border-radius: 8px;
  padding: 8px 12px;
}
.simple-textarea :deep(.el-textarea__inner) {
  box-shadow: none;
  background: #f8f8f8;
  border-radius: 8px;
  padding: 10px 12px;
  border: none;
}

/* 图片上传 */
.upload-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.upload-item {
  position: relative;
  aspect-ratio: 1;
  border-radius: 8px;
  overflow: hidden;
}
.upload-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.remove-btn {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  background: rgba(0,0,0,0.5);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.upload-add {
  aspect-ratio: 1;
}
.upload-add :deep(.el-upload) {
  width: 100%;
  height: 100%;
}
.upload-add-inner {
  width: 100%;
  height: 100%;
  border: 1px dashed #ddd;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: #fafafa;
  cursor: pointer;
}
.upload-text {
  font-size: 12px;
  color: #999;
}

/* 信息行 */
.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
}
.info-label {
  font-size: 15px;
  color: #333;
  flex-shrink: 0;
  margin-right: 16px;
}
.divider {
  height: 1px;
  background: #f0f0f0;
}
.price-input-wrap {
  display: flex;
  align-items: center;
  background: #f8f8f8;
  border-radius: 8px;
  padding: 0 12px;
}
.price-prefix {
  font-size: 20px;
  color: #ff4400;
  font-weight: 700;
  margin-right: 4px;
}
.price-input {
  width: 120px;
}
.price-input :deep(.el-input__wrapper) {
  box-shadow: none;
  background: transparent;
  padding: 8px 0;
}
.price-input :deep(.el-input__inner) {
  font-size: 20px;
  font-weight: 700;
  color: #ff4400;
  text-align: right;
}
.info-select {
  width: 180px;
}
.info-select :deep(.el-input__wrapper) {
  box-shadow: none;
  background: #f8f8f8;
  border-radius: 8px;
}
.info-input {
  flex: 1;
  max-width: 240px;
}
.info-input :deep(.el-input__wrapper) {
  box-shadow: none;
  background: #f8f8f8;
  border-radius: 8px;
}

.bottom-placeholder {
  height: 20px;
}

/* 底部发布按钮 */
.bottom-bar {
  position: sticky;
  bottom: 0;
  left: auto;
  right: auto;
  background: #fff;
  padding: 10px 16px;
  box-shadow: 0 -2px 10px rgba(0,0,0,0.06);
  z-index: 30;
}
.publish-submit-btn {
  width: 100%;
  height: 44px;
  background: linear-gradient(135deg, #ff6b00, #ff8c00);
  border: none;
  border-radius: 22px;
  font-size: 16px;
  font-weight: 600;
}
.publish-submit-btn:hover {
  background: linear-gradient(135deg, #ff5500, #ff7700) !important;
}
</style>
