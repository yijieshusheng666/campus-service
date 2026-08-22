<template>
  <div class="auth-page">
    <el-card class="auth-card">
      <h2 class="title">注册账号</h2>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="3-50 个字符" prefix-icon="User" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入邮箱" prefix-icon="Message" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" prefix-icon="Lock" />
        </el-form-item>
      </el-form>
      <el-button type="primary" class="submit" :loading="loading" @click="submit">注 册</el-button>
      <div class="foot">
        <span>已有账号？</span>
        <router-link to="/login" class="link">直接登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { register } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const formRef = ref()
const loading = ref(false)
const auth = useAuthStore()

const form = reactive({ username: '', email: '', password: '' })
const rules = {
  username: [{ required: true, min: 3, max: 50, message: '用户名需 3-50 位', trigger: 'blur' }],
  email: [{ required: true, type: 'email', message: '请输入正确的邮箱', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少 6 位', trigger: 'blur' }]
}

async function submit() {
  await formRef.value.validate()
  loading.value = true
  try {
    const res = await register(form)
    auth.setAuth(res.data.access_token, res.data.user)
    ElMessage.success('注册成功')
    router.push('/goods')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2d3d, #3a5a80);
}
.auth-card { width: 420px; padding: 12px 8px; }
.title { text-align: center; margin-bottom: 20px; }
.submit { width: 100%; }
.foot { margin-top: 16px; text-align: center; font-size: 13px; color: #909399; }
.link { color: #409eff; }
</style>