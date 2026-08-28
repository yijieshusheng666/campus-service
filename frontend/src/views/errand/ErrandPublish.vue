<template>
  <div class="page">
    <div class="page-header">
      <h2>发布代拿需求</h2>
      <el-button @click="$router.back()">返回</el-button>
    </div>

    <el-card>
      <el-form :model="form" label-width="90px" class="form">
        <el-form-item label="取件地址" required>
          <el-input v-model="form.pickup_location" placeholder="如：菜鸟驿站3号店" maxlength="200" />
        </el-form-item>
        <el-form-item label="快递信息" required>
          <el-input v-model="form.package_info" placeholder="如：顺丰 SF1234567890" maxlength="200" />
        </el-form-item>
        <el-form-item label="送达地址" required>
          <el-input v-model="form.dropoff_location" placeholder="如：梧桐苑5栋302" maxlength="200" />
        </el-form-item>
        <el-form-item label="报酬" required>
          <div class="reward-input">
            <el-input-number v-model="form.reward" :min="0.5" :max="9999" :precision="2" :step="0.5" />
            <span class="unit">元</span>
          </div>
        </el-form-item>
        <el-form-item label="期望送达">
          <el-date-picker v-model="form.deadline" type="datetime" placeholder="可选" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="如：放门口即可" maxlength="500" />
        </el-form-item>
        <el-form-item label="联系方式">
          <el-input v-model="form.contact" placeholder="默认使用用户名" maxlength="100" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" :disabled="!valid" @click="submit">发布</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { publishErrand } from '@/api/errand'

const router = useRouter()
const submitting = ref(false)
const form = reactive({
  pickup_location: '',
  package_info: '',
  dropoff_location: '',
  reward: 2,
  deadline: null,
  remark: '',
  contact: ''
})

const valid = computed(
  () => form.pickup_location.trim() && form.package_info.trim() && form.dropoff_location.trim()
)

const submit = async () => {
  submitting.value = true
  try {
    const res = await publishErrand({
      ...form,
      pickup_location: form.pickup_location.trim(),
      package_info: form.package_info.trim(),
      dropoff_location: form.dropoff_location.trim(),
      deadline: form.deadline || null,
      remark: form.remark.trim() || null,
      contact: form.contact.trim() || null
    })
    ElMessage.success('发布成功')
    router.push({ name: 'ErrandDetail', params: { id: res.data.id } })
  } catch { /* 拦截器已提示 */ } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.page { max-width: 640px; margin: 0 auto; padding: 20px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 18px; }
.reward-input { display: flex; align-items: center; gap: 8px; }
.unit { color: var(--el-text-color-regular); }
</style>
