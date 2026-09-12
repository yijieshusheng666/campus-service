<template>
  <div class="auth-page">
    <el-card class="auth-card">
      <h2 class="title">找回密码</h2>
      <p class="subtitle">验证邮箱后设置新密码</p>

      <el-alert
        v-if="!emailConfigured"
        type="warning"
        :closable="false"
        show-icon
        class="alert"
        title="邮件服务尚未配置"
        description="当前无法发送验证码，请联系平台管理员。"
      />

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="注册邮箱" prop="email">
          <el-input v-model="form.email" placeholder="请输入注册时使用的邮箱" prefix-icon="Message" />
        </el-form-item>

        <el-form-item label="邮箱验证码" prop="code">
          <div class="code-row">
            <el-input v-model="form.code" placeholder="6 位验证码" maxlength="6" prefix-icon="Key" />
            <el-button
              class="code-btn"
              :disabled="countdown > 0 || sending || !emailConfigured"
              :loading="sending"
              @click="onSendCode"
            >
              {{ countdown > 0 ? `${countdown}s 后重发` : '获取验证码' }}
            </el-button>
          </div>
          <div class="hint">验证码 10 分钟内有效。收不到请检查垃圾邮件，或稍后重试。</div>
        </el-form-item>

        <el-form-item label="新密码" prop="new_password">
          <el-input
            v-model="form.new_password"
            type="password"
            show-password
            placeholder="至少 6 位"
            prefix-icon="Lock"
          />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input
            v-model="form.confirm"
            type="password"
            show-password
            placeholder="再输入一次新密码"
            prefix-icon="Lock"
            @keyup.enter="submit"
          />
        </el-form-item>
      </el-form>

      <el-button type="primary" class="submit" :loading="loading" @click="submit">重置密码</el-button>

      <div class="foot">
        <router-link to="/login" class="link">返回登录</router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { forgotPassword, getRegisterPolicy, resetPassword } from '@/api/auth'

const router = useRouter()
const formRef = ref()
const loading = ref(false)
const sending = ref(false)
const emailConfigured = ref(true)

const form = reactive({ email: '', code: '', new_password: '', confirm: '' })

const rules = {
  email: [{ required: true, type: 'email', message: '请输入正确的邮箱', trigger: 'blur' }],
  code: [{ required: true, len: 6, message: '请输入 6 位邮箱验证码', trigger: 'blur' }],
  new_password: [{ required: true, min: 6, message: '新密码至少 6 位', trigger: 'blur' }],
  confirm: [
    { required: true, message: '请再输入一次新密码', trigger: 'blur' },
    {
      // 前端一致性校验只为减少打错字的概率；真正的规则（长度等）仍由后端把关
      validator: (rule, value, callback) =>
        value === form.new_password ? callback() : callback(new Error('两次输入的密码不一致')),
      trigger: 'blur'
    }
  ]
}

// ---- 验证码倒计时 ----
const countdown = ref(0)
let timer = null
function startCountdown(seconds = 60) {
  countdown.value = seconds
  clearInterval(timer)
  timer = setInterval(() => {
    countdown.value -= 1
    if (countdown.value <= 0) clearInterval(timer)
  }, 1000)
}

async function onSendCode() {
  try {
    await formRef.value.validateField('email')
  } catch (e) {
    return
  }
  sending.value = true
  try {
    const res = await forgotPassword(form.email)
    // 后端对「邮箱是否存在」返回同一句话，这是刻意的（防用户枚举），
    // 所以前端也只能给中性提示，不能提示「该邮箱未注册」
    ElMessage.success(res.data.message || '如果该邮箱已注册，验证码已发送')
    startCountdown(60)
  } catch (e) {
    const retryAfter = Number(e.response?.headers?.['retry-after'])
    if (e.response?.status === 429 && retryAfter > 0 && retryAfter <= 3600) {
      startCountdown(retryAfter)
    } else if (e.response?.status === 503) {
      emailConfigured.value = false
    }
  } finally {
    sending.value = false
  }
}

async function submit() {
  await formRef.value.validate()
  loading.value = true
  try {
    const res = await resetPassword({
      email: form.email,
      code: form.code,
      new_password: form.new_password
    })
    ElMessage.success(res.data.message || '密码已重置，请用新密码登录')
    // 重置成功后所有设备都被强制下线（后端吊销了全部 refresh token），
    // 所以这里直接回登录页，让用户用新密码重新登录
    router.push({ name: 'Login' })
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const res = await getRegisterPolicy()
    emailConfigured.value = res.data.email_configured
  } catch (e) {
    /* 拿不到策略就不显示警告条，用户点了自然会看到 503 提示 */
  }
})

onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.auth-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2d3d, #3a5a80);
  overflow-y: auto;
}
.auth-card { width: 420px; padding: 12px 8px; }
.title { text-align: center; margin-bottom: 4px; }
.subtitle { text-align: center; font-size: 13px; color: #909399; margin-bottom: 16px; }
.alert { margin-bottom: 12px; }
.submit { width: 100%; }
.foot { margin-top: 16px; text-align: center; font-size: 13px; color: #909399; }
.link { color: #409eff; }

.code-row { display: flex; gap: 10px; width: 100%; }
.code-btn { flex-shrink: 0; min-width: 108px; }
.hint { font-size: 12px; color: #a0a5b2; line-height: 1.5; margin-top: 4px; }

@media (max-width: 767px) {
  .auth-page { align-items: flex-start; padding: 16px; }
  .auth-card { width: 100%; }
  .code-row { flex-direction: column; gap: 8px; }
  .code-btn { width: 100%; }
}
</style>
