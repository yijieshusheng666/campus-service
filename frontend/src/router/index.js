import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import MainLayout from '@/layout/MainLayout.vue'

// meta.hideSupportBall —— 隐藏右下角的智能客服悬浮球。
// 约定：页面底部若有「sticky 操作栏」或「输入+发送区」，就一定要加这个标记，
// 否则固定定位的悬浮球（56px，right/bottom 各 24px）会压住那里的按钮。
// 聊天页的发送按钮、商品详情的「立即购买」都栽过这个坑。
const routes = [
  {
    path: '/',
    component: MainLayout,
    children: [
      { path: '', redirect: '/goods' },
      {
        path: 'goods',
        name: 'GoodsList',
        component: () => import('@/views/goods/GoodsList.vue')
      },
      {
        path: 'goods/:id',
        name: 'GoodsDetail',
        component: () => import('@/views/goods/GoodsDetail.vue'),
        // 底部有 sticky 操作栏（立即购买 / 聊一聊），悬浮客服球会压在按钮上
        meta: { hideSupportBall: true }
      },
      {
        path: 'goods-publish',
        name: 'GoodsPublish',
        component: () => import('@/views/goods/GoodsPublish.vue'),
        meta: { requiresAuth: true, hideSupportBall: true }
      },
      {
        path: 'my-goods',
        name: 'MyGoods',
        component: () => import('@/views/goods/MyGoods.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'favorites',
        name: 'Favorites',
        component: () => import('@/views/goods/Favorites.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'order-confirm',
        name: 'OrderConfirm',
        component: () => import('@/views/goods/OrderConfirm.vue'),
        meta: { requiresAuth: true, hideSupportBall: true }
      },
      {
        path: 'my-orders',
        name: 'MyOrders',
        component: () => import('@/views/goods/MyOrders.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'resume',
        name: 'ResumeManage',
        component: () => import('@/views/resume/ResumeManage.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'interviews',
        name: 'InterviewList',
        component: () => import('@/views/interview/InterviewList.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'interviews/:id',
        name: 'InterviewChat',
        component: () => import('@/views/interview/InterviewChat.vue'),
        // 底部是答题输入区，悬浮球会压住发送按钮
        meta: { requiresAuth: true, hideSupportBall: true }
      },
      {
        path: 'interviews/:id/report',
        name: 'InterviewReport',
        component: () => import('@/views/interview/InterviewReport.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'errands',
        name: 'ErrandList',
        component: () => import('@/views/errand/ErrandList.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'errands/publish',
        name: 'ErrandPublish',
        component: () => import('@/views/errand/ErrandPublish.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'errands/:id',
        name: 'ErrandDetail',
        component: () => import('@/views/errand/ErrandDetail.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'chat/:userId?',
        name: 'Chat',
        component: () => import('@/views/chat/Chat.vue'),
        // 发送按钮在右下角，与悬浮客服球位置正面冲突（会挡住发送）
        meta: { requiresAuth: true, hideSupportBall: true }
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/Settings.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'admin',
        name: 'AdminCenter',
        component: () => import('@/views/admin/AdminCenter.vue'),
        meta: { requiresAuth: true, requiresAdmin: true }
      }
    ]
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue')
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  // 管理员页面：已登录但不是管理员，退回商品集市。
  // 这只是体验层的拦截（避免普通用户撞进一个全是 403 的页面）——
  // 真正的权限边界在后端 get_current_admin，它会对非管理员返回 403；
  // 就算有人改前端把守卫绕过去，也拿不到任何数据。
  if (to.meta.requiresAdmin && !auth.user?.is_admin) {
    return { path: '/goods' }
  }
})

export default router