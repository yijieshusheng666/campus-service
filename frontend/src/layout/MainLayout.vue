<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <!-- Logo区域 -->
      <div class="logo-area">
        <div class="logo-icon">
          <el-icon :size="24" color="#fff"><School /></el-icon>
        </div>
        <div class="logo-text">
          <h2>校园综合服务平台</h2>
          <p>Campus Service</p>
        </div>
      </div>

      <!-- 导航菜单 -->
      <el-menu
        :default-active="activeMenu"
        :default-openeds="['trade', 'errand', 'career']"
        router
        class="side-menu"
        background-color="transparent"
        text-color="#5a6070"
        active-text-color="#ff6b00"
      >
        <el-sub-menu index="trade">
          <template #title>
            <el-icon class="menu-icon"><Goods /></el-icon>
            <span>二手交易</span>
          </template>
          <el-menu-item index="/goods">
            <span class="menu-dot"></span>
            <span>商品集市</span>
          </el-menu-item>
          <el-menu-item v-if="auth.isAuthenticated" index="/goods-publish">
            <span class="menu-dot"></span>
            <span>发布商品</span>
          </el-menu-item>
          <el-menu-item v-if="auth.isAuthenticated" index="/my-goods">
            <span class="menu-dot"></span>
            <span>我的商品</span>
          </el-menu-item>
          <el-menu-item v-if="auth.isAuthenticated" index="/my-orders">
            <span class="menu-dot"></span>
            <span>我的订单</span>
          </el-menu-item>
          <el-menu-item v-if="auth.isAuthenticated" index="/favorites">
            <span class="menu-dot"></span>
            <span>我的收藏</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="errand">
          <template #title>
            <el-icon class="menu-icon"><Van /></el-icon>
            <span>校园跑腿</span>
          </template>
          <el-menu-item v-if="auth.isAuthenticated" index="/errands">
            <span class="menu-dot"></span>
            <span>跑腿大厅</span>
          </el-menu-item>
          <el-menu-item v-if="auth.isAuthenticated" index="/errands/publish">
            <span class="menu-dot"></span>
            <span>发布跑腿需求</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu index="career">
          <template #title>
            <el-icon class="menu-icon"><Briefcase /></el-icon>
            <span>AI求职</span>
          </template>
          <el-menu-item v-if="auth.isAuthenticated" index="/resume">
            <span class="menu-dot"></span>
            <span>我的简历</span>
          </el-menu-item>
          <el-menu-item v-if="auth.isAuthenticated" index="/interviews">
            <span class="menu-dot"></span>
            <span>AI 模拟面试</span>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>

      <!-- 底部用户信息 -->
      <div class="side-footer">
        <template v-if="auth.isAuthenticated">
          <div class="user-card" @click="goToSettings">
            <div class="user-avatar">
              <el-icon :size="20" color="#fff"><User /></el-icon>
            </div>
            <div class="user-info">
              <span class="user-name">{{ auth.user?.nickname || auth.user?.username }}</span>
              <span class="user-tip">账号设置</span>
            </div>
            <div class="user-actions">
              <el-icon class="action-icon" title="设置" @click.stop="goToSettings"><Setting /></el-icon>
              <el-icon class="action-icon logout" title="退出登录" @click.stop="onCommand('logout')"><SwitchButton /></el-icon>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="login-entry">
            <el-button type="primary" class="login-btn" @click="$router.push('/login')">
              立即登录
            </el-button>
            <p class="register-tip" @click="$router.push('/register')">没有账号？去注册</p>
          </div>
        </template>
      </div>
    </el-aside>

    <el-container class="right-container">
      <el-header class="header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/goods' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentBreadcrumb">{{ currentBreadcrumb }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <span class="header-right">
          <el-badge
            v-if="auth.isAuthenticated"
            :value="unreadTotal > 99 ? '99+' : unreadTotal"
            :hidden="unreadTotal === 0"
            class="msg-badge"
          >
            <el-icon :size="20" class="msg-icon" title="我的私信" @click="$router.push({ name: 'Chat' })">
              <ChatDotRound />
            </el-icon>
          </el-badge>
          <span class="welcome-text">欢迎使用校园综合服务平台 👋</span>
        </span>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { getConversations } from '@/api/message'
import {
  School, Goods, Briefcase, User, SwitchButton, Setting, Van, ChatDotRound
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const showUserMenu = ref(false)

// 顶栏未读徽标：30s 轮询会话列表（轻量聚合接口）
const unreadTotal = ref(0)
let unreadTimer = null
async function refreshUnread() {
  if (!auth.isAuthenticated) {
    unreadTotal.value = 0
    return
  }
  try {
    const res = await getConversations()
    unreadTotal.value = res.data.reduce((sum, c) => sum + c.unread, 0)
  } catch (e) {
    /* 401 已由拦截器处理 */
  }
}
onMounted(() => {
  refreshUnread()
  unreadTimer = setInterval(refreshUnread, 30000)
})
onUnmounted(() => clearInterval(unreadTimer))

const activeMenu = computed(() => route.path)

const breadcrumbMap = {
  '/goods': '商品集市',
  '/goods-publish': '发布商品',
  '/my-goods': '我的商品',
  '/my-orders': '我的订单',
  '/favorites': '我的收藏',
  '/resume': '我的简历',
  '/interviews': 'AI 模拟面试',
  '/errands': '跑腿大厅',
  '/errands/publish': '发布跑腿需求',
  '/chat': '我的私信',
  '/settings': '账号设置'
}
const currentBreadcrumb = computed(() => {
  const path = route.path
  if (path.startsWith('/goods/')) return '商品详情'
  if (path.startsWith('/resume/edit/')) return '简历编辑'
  if (path.startsWith('/interviews/') && path.endsWith('/report')) return '面试评估报告'
  if (path.startsWith('/interviews/')) return '面试对话'
  if (path.startsWith('/errands/')) return '需求详情'
  return breadcrumbMap[path] || ''
})

function onCommand(cmd) {
  if (cmd === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定退出',
      cancelButtonText: '取消',
      type: 'warning',
      confirmButtonClass: 'el-button--danger'
    }).then(() => {
      auth.logout()
      ElMessage.success('已退出登录')
      router.push('/goods')
    }).catch(() => {})
  }
}
function goToSettings() {
  router.push('/settings')
}
</script>

<style scoped>
.layout { height: 100vh; overflow: hidden; }

/* ===== 侧边栏 ===== */
.aside {
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
  border-right: 1px solid #eef0f4;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
}

/* Logo */
.logo-area {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 18px 22px;
  border-bottom: 1px solid #f0f2f5;
}
.logo-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #ff6b00, #ff9500);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 10px rgba(255, 107, 0, 0.25);
  flex-shrink: 0;
}
.logo-text h2 {
  font-size: 15px;
  font-weight: 700;
  color: #1d2129;
  line-height: 1.3;
  margin: 0;
}
.logo-text p {
  font-size: 11px;
  color: #a0a5b2;
  margin-top: 2px;
  font-weight: 400;
  letter-spacing: 0.5px;
}

/* 菜单 */
.side-menu {
  flex: 1;
  border-right: none !important;
  padding: 10px 8px;
}
.side-menu :deep(.el-sub-menu__title) {
  height: 44px;
  line-height: 44px;
  border-radius: 8px;
  margin-bottom: 2px;
  font-weight: 500;
  font-size: 14px;
  color: #1d2129 !important;
  transition: all 0.2s;
}
.side-menu :deep(.el-sub-menu__title:hover) {
  background: #fff5ec !important;
  color: #ff6b00 !important;
}
.side-menu :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
  color: #ff6b00 !important;
  background: #fff5ec !important;
}
.side-menu :deep(.el-sub-menu .el-menu) {
  background: transparent !important;
}
.side-menu :deep(.el-menu-item) {
  height: 38px;
  line-height: 38px;
  border-radius: 8px;
  margin: 2px 0;
  font-size: 13px;
  display: flex;
  align-items: center;
  padding-left: 46px !important;
  transition: all 0.2s;
}
.side-menu :deep(.el-menu-item:hover) {
  background: #f5f6f8 !important;
  color: #ff6b00 !important;
}
.side-menu :deep(.el-menu-item.is-active) {
  background: linear-gradient(135deg, #fff0e0, #ffe8d1) !important;
  color: #ff6b00 !important;
  font-weight: 600;
}
.side-menu :deep(.el-menu-item.is-active)::before {
  content: '';
  position: absolute;
  left: 8px;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 16px;
  background: linear-gradient(180deg, #ff6b00, #ff9500);
  border-radius: 2px;
}
.menu-icon {
  font-size: 18px;
  margin-right: 10px;
}
.menu-dot {
  display: none;
}

/* 底部 */
.side-footer {
  padding: 12px;
  border-top: 1px solid #f0f2f5;
}
.user-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.2s;
}
.user-card:hover {
  background: #f5f6f8;
}
.user-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea, #764ba2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.user-info {
  flex: 1;
  min-width: 0;
}
.user-name {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: #1d2129;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.user-tip {
  display: block;
  font-size: 11px;
  color: #ff6b00;
  margin-top: 2px;
}
.user-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.action-icon {
  font-size: 17px;
  color: #a0a5b2;
  padding: 6px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}
.action-icon:hover {
  background: #f0f2f5;
  color: #4e5969;
}
.action-icon.logout:hover {
  color: #f56c6c;
  background: #fef0f0;
}

.login-entry {
  padding: 6px 4px;
}
.login-btn {
  width: 100%;
  height: 40px;
  border-radius: 20px;
  background: linear-gradient(135deg, #ff6b00, #ff9500);
  border: none;
  font-size: 14px;
  font-weight: 600;
  box-shadow: 0 4px 12px rgba(255, 107, 0, 0.3);
}
.login-btn:hover {
  background: linear-gradient(135deg, #ff5500, #ff8800) !important;
}
.register-tip {
  text-align: center;
  font-size: 12px;
  color: #a0a5b2;
  margin-top: 8px;
  cursor: pointer;
  transition: color 0.2s;
}
.register-tip:hover {
  color: #ff6b00;
}

/* ===== 右侧区域 ===== */
.right-container { height: 100%; overflow: hidden; }

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #eef0f4;
  flex-shrink: 0;
  padding: 0 24px;
}
.header-left {
  display: flex;
  align-items: center;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 14px;
}
.msg-badge {
  display: flex;
  align-items: center;
}
.msg-icon {
  color: #86909c;
  cursor: pointer;
  transition: color 0.2s;
}
.msg-icon:hover {
  color: #ff6b00;
}
.welcome-text {
  font-size: 13px;
  color: #86909c;
}

.main {
  background: #f5f7fa;
  padding: 0;
  overflow-y: auto;
  flex: 1;
}
</style>
