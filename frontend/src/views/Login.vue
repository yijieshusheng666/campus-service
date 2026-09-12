<template>
  <div class="auth-page">
    <el-card class="auth-card">
      <h2 class="title">校园综合服务平台</h2>
      <p class="subtitle">登录 · 二手交易 & AI 岗位匹配</p>
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="用户名 / 邮箱" prop="identifier">
          <el-input v-model="form.identifier" placeholder="请输入用户名或邮箱" prefix-icon="User" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" prefix-icon="Lock" @keyup.enter="submit" />
        </el-form-item>
      </el-form>
      <el-button type="primary" class="submit" :loading="loading" @click="submit">登 录</el-button>
      <div class="foot">
        <span>还没有账号？</span>
        <router-link to="/register" class="link">立即注册</router-link>
        <span class="divider">|</span>
        <router-link to="/forgot-password" class="link">忘记密码？</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const formRef = ref()
const loading = ref(false)
const auth = useAuthStore()

const form = reactive({ identifier: '', password: '' })
const rules = {
  identifier: [{ required: true, message: '请输入用户名或邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function submit() {
  await formRef.value.validate()
  loading.value = true
  try {
    const res = await login(form)
    auth.setAuth(res.data.access_token, res.data.user, res.data.refresh_token)
    ElMessage.success('登录成功')
    router.push(route.query.redirect || '/goods')
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
.auth-card { width: 380px; padding: 12px 8px; }
.title { text-align: center; margin-bottom: 4px; }
.subtitle { text-align: center; color: #909399; font-size: 13px; margin-bottom: 20px; }
.submit { width: 100%; }
.foot { margin-top: 16px; text-align: center; font-size: 13px; color: #909399; }
.link { color: #409eff; }
.divider { margin: 0 8px; color: #dcdfe6; }
</style>