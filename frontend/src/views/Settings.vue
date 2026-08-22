<template>
  <div class="settings-page">
    <!-- 页面头部 -->
    <div class="page-header">
      <h2 class="page-title">账号设置</h2>
      <p class="page-desc">管理您的个人信息和账号安全</p>
    </div>

    <div class="settings-content">
      <!-- 个人资料卡片 -->
      <el-card class="settings-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon :size="18" color="#ff6b00"><User /></el-icon>
            <span>个人资料</span>
          </div>
        </template>
        <el-form
          ref="profileFormRef"
          :model="profileForm"
          :rules="profileRules"
          label-width="90px"
          label-position="left"
        >
          <el-form-item label="用户名">
            <el-input v-model="profileForm.username" disabled class="readonly-input">
              <template #append>不可修改</template>
            </el-input>
          </el-form-item>
          <el-form-item label="邮箱">
            <el-input v-model="profileForm.email" disabled class="readonly-input">
              <template #append>不可修改</template>
            </el-input>
          </el-form-item>
          <el-form-item label="昵称" prop="nickname">
            <el-input v-model="profileForm.nickname" placeholder="请输入昵称（显示在平台上的名字）" maxlength="20" show-word-limit />
          </el-form-item>
          <el-form-item label="手机号" prop="phone">
            <el-input v-model="profileForm.phone" placeholder="请输入手机号（选填，方便买家联系）" maxlength="11" />
          </el-form-item>
          <el-form-item label="注册时间">
            <span class="readonly-text">{{ formatDate(profileForm.created_at) }}</span>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" class="save-btn" :loading="savingProfile" @click="saveProfile">
              保存修改
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 修改密码卡片 -->
      <el-card class="settings-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon :size="18" color="#ff6b00"><Lock /></el-icon>
            <span>修改密码</span>
          </div>
        </template>
        <el-form
          ref="passwordFormRef"
          :model="passwordForm"
          :rules="passwordRules"
          label-width="90px"
          label-position="left"
        >
          <el-form-item label="原密码" prop="old_password">
            <el-input v-model="passwordForm.old_password" type="password" placeholder="请输入当前密码" show-password />
          </el-form-item>
          <el-form-item label="新密码" prop="new_password">
            <el-input v-model="passwordForm.new_password" type="password" placeholder="新密码至少6位" show-password />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirm_password">
            <el-input v-model="passwordForm.confirm_password" type="password" placeholder="再次输入新密码" show-password />
          </el-form-item>
          <el-form-item>
            <el-button type="warning" class="save-btn" :loading="savingPassword" @click="savePassword">
              修改密码
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 账号安全卡片 -->
      <el-card class="settings-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon :size="18" color="#ff6b00"><WarningFilled /></el-icon>
            <span>账号操作</span>
          </div>
        </template>
        <div class="danger-zone">
          <div class="danger-item">
            <div>
              <div class="danger-title">退出登录</div>
              <div class="danger-desc">退出当前账号，返回首页</div>
            </div>
            <el-button type="danger" plain @click="handleLogout">退出登录</el-button>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, Lock, WarningFilled } from '@element-plus/icons-vue'
import { updateProfile, changePassword } from '@/api/users'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const profileFormRef = ref()
const passwordFormRef = ref()
const savingProfile = ref(false)
const savingPassword = ref(false)

const profileForm = reactive({
  username: '',
  email: '',
  nickname: '',
  phone: '',
  created_at: ''
})

const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

const profileRules = {
  nickname: [{ max: 20, message: '昵称不能超过20个字符', trigger: 'blur' }],
  phone: [{ pattern: /^1[3-9]\d{9}$/, message: '请输入正确的手机号', trigger: 'blur' }]
}

const validateConfirm = (rule, value, callback) => {
  if (value !== passwordForm.new_password) {
    callback(new Error('两次输入的密码不一致'))
  } else {
    callback()
  }
}

const passwordRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' }
  ]
}

function formatDate(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

function loadData() {
  const u = auth.user
  if (u) {
    profileForm.username = u.username
    profileForm.email = u.email
    profileForm.nickname = u.nickname || ''
    profileForm.phone = u.phone || ''
    profileForm.created_at = u.created_at
  }
}

async function saveProfile() {
  if (!profileFormRef.value) return
  try {
    await profileFormRef.value.validate()
  } catch (e) { return }
  savingProfile.value = true
  try {
    const res = await updateProfile({
      nickname: profileForm.nickname.trim() || null,
      phone: profileForm.phone.trim() || null
    })
    auth.updateUser(res.data)
    ElMessage.success('个人资料已保存')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    savingProfile.value = false
  }
}

async function savePassword() {
  if (!passwordFormRef.value) return
  try {
    await passwordFormRef.value.validate()
  } catch (e) { return }
  savingPassword.value = true
  try {
    await changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password
    })
    ElMessage.success('密码修改成功，请重新登录')
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm_password = ''
    setTimeout(() => {
      auth.logout()
      router.push('/login')
    }, 1500)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '修改失败')
  } finally {
    savingPassword.value = false
  }
}

function handleLogout() {
  ElMessageBox.confirm('确定要退出登录吗？', '提示', {
    confirmButtonText: '确定退出',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    auth.logout()
    ElMessage.success('已退出登录')
    router.push('/goods')
  }).catch(() => {})
}

onMounted(loadData)
</script>

<style scoped>
.settings-page {
  padding: 20px;
  min-height: 100%;
  background: #f5f7fa;
}
.page-header {
  margin-bottom: 20px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #1d2129;
  margin: 0;
}
.page-desc {
  font-size: 13px;
  color: #86909c;
  margin: 6px 0 0;
}

.settings-content {
  max-width: 680px;
}
.settings-card {
  margin-bottom: 20px;
  border-radius: 12px;
  border: none;
}
.settings-card :deep(.el-card__header) {
  padding: 14px 20px;
  border-bottom: 1px solid #f0f2f5;
}
.settings-card :deep(.el-card__body) {
  padding: 24px;
}
.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #1d2129;
}
.readonly-input :deep(.el-input__wrapper) {
  background: #f7f8fa;
}
.readonly-input :deep(.el-input-group__append) {
  background: #f0f2f5;
  color: #a0a5b2;
  border-color: #e4e7ed;
}
.readonly-text {
  color: #86909c;
  font-size: 14px;
}
.save-btn {
  width: 140px;
  border-radius: 8px;
  font-weight: 500;
}

/* 危险区域 */
.danger-zone {
  border-radius: 8px;
}
.danger-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
}
.danger-title {
  font-size: 14px;
  font-weight: 500;
  color: #1d2129;
}
.danger-desc {
  font-size: 12px;
  color: #86909c;
  margin-top: 4px;
}
</style>
