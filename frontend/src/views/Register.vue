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

        <!-- 邮箱验证码：仅在后端开启 REQUIRE_EMAIL_VERIFY 时显示 -->
        <el-form-item v-if="policy.require_email_verify" label="邮箱验证码" prop="email_code">
          <div class="code-row">
            <el-input
              v-model="form.email_code"
              placeholder="6 位验证码"
              maxlength="6"
              prefix-icon="Key"
            />
            <el-button
              class="code-btn"
              :disabled="countdown > 0 || sending"
              :loading="sending"
              @click="onSendCode"
            >
              {{ countdown > 0 ? `${countdown}s 后重发` : '获取验证码' }}
            </el-button>
          </div>
          <div class="code-hint">
            验证码 {{ ttlMinutes }} 分钟内有效。收不到请检查垃圾邮件，或稍后重试。
          </div>
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
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getRegisterPolicy, register, sendEmailCode } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const formRef = ref()
const loading = ref(false)
const sending = ref(false)
const auth = useAuthStore()

// 后端策略：是否需要邮箱验证码（SMTP 没配好的部署仍是老流程，不受影响）
const policy = reactive({ require_email_verify: false, email_configured: true })
const ttlMinutes = ref(10)

const form = reactive({ username: '', email: '', password: '', email_code: '' })

const rules = computed(() => ({
  username: [{ required: true, min: 3, max: 50, message: '用户名需 3-50 位', trigger: 'blur' }],
  email: [{ required: true, type: 'email', message: '请输入正确的邮箱', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少 6 位', trigger: 'blur' }],
  email_code: policy.require_email_verify
    ? [{ required: true, len: 6, message: '请输入 6 位邮箱验证码', trigger: 'blur' }]
    : []
}))

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
  // 先单独校验邮箱，避免整表校验时把「密码没填」也一起报出来干扰焦点
  try {
    await formRef.value.validateField('email')
  } catch (e) {
    return
  }
  sending.value = true
  try {
    const res = await sendEmailCode(form.email)
    ElMessage.success(res.data.message || '验证码已发送')
    startCountdown(60)
  } catch (e) {
    // 429（发送过于频繁）与 503（SMTP 未配置）的具体文案由拦截器弹出
    const retryAfter = Number(e.response?.headers?.['retry-after'])
    if (e.response?.status === 429 && retryAfter > 0 && retryAfter <= 3600) {
      startCountdown(retryAfter)
    }
  } finally {
    sending.value = false
  }
}

async function submit() {
  await formRef.value.validate()
  loading.value = true
  try {
    const payload = { username: form.username, email: form.email, password: form.password }
    if (policy.require_email_verify) payload.email_code = form.email_code
    const res = await register(payload)
    auth.setAuth(res.data.access_token, res.data.user, res.data.refresh_token)
    ElMessage.success('注册成功')
    router.push('/goods')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const res = await getRegisterPolicy()
    Object.assign(policy, res.data)
  } catch (e) {
    // 拿不到策略就按「不需要验证码」处理：老流程，至少能注册
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
}
.auth-card { width: 420px; padding: 12px 8px; }
.title { text-align: center; margin-bottom: 20px; }
.submit { width: 100%; }
.foot { margin-top: 16px; text-align: center; font-size: 13px; color: #909399; }
.link { color: #409eff; }

.code-row { display: flex; gap: 10px; width: 100%; }
.code-btn { flex-shrink: 0; min-width: 108px; }
.code-hint { font-size: 12px; color: #a0a5b2; line-height: 1.5; margin-top: 4px; }

/* 移动端：验证码按钮与输入框等宽堆叠，避免 375px 屏幕下按钮被挤没 */
@media (max-width: 767px) {
  .auth-page { align-items: flex-start; padding: 16px; }
  .auth-card { width: 100%; }
  .code-row { flex-direction: column; gap: 8px; }
  .code-btn { width: 100%; }
}
</style>
