import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import MainLayout from '@/layout/MainLayout.vue'

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
        component: () => import('@/views/goods/GoodsDetail.vue')
      },
      {
        path: 'goods-publish',
        name: 'GoodsPublish',
        component: () => import('@/views/goods/GoodsPublish.vue'),
        meta: { requiresAuth: true }
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
        meta: { requiresAuth: true }
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
        meta: { requiresAuth: true }
      },
      {
        path: 'interviews/:id/report',
        name: 'InterviewReport',
        component: () => import('@/views/interview/InterviewReport.vue'),
        meta: { requiresAuth: true }
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/Settings.vue'),
        meta: { requiresAuth: true }
      }
    ]
  },
  {
    path: '/resume/edit/:id',
    name: 'ResumeEditor',
    component: () => import('@/views/resume/ResumeEditor.vue'),
    meta: { requiresAuth: true, fullscreen: true }
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
})

export default router