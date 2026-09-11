import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'
import { me as fetchMe } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  const isAuthenticated = computed(() => !!token.value)

  function setAuth(newToken, newUser, newRefreshToken) {
    token.value = newToken
    user.value = newUser
    if (newRefreshToken) refreshToken.value = newRefreshToken
    localStorage.setItem('token', newToken)
    if (newRefreshToken) localStorage.setItem('refresh_token', newRefreshToken)
    localStorage.setItem('user', JSON.stringify(newUser))
  }

  // 刷新成功后只换令牌、不动 user（避免覆盖 loadMe 拉到的新资料）
  function setTokens(newToken, newRefreshToken) {
    token.value = newToken
    refreshToken.value = newRefreshToken
    localStorage.setItem('token', newToken)
    localStorage.setItem('refresh_token', newRefreshToken)
  }

  function updateUser(newUserData) {
    user.value = { ...user.value, ...newUserData }
    localStorage.setItem('user', JSON.stringify(user.value))
  }

  function logout() {
    // 尽力通知服务端吊销 refresh token（拦不住就算了——本地清掉是底线）。
    // 刻意用裸 axios：走 request.js 的话，吊销请求自身 401 会触发拦截器再次 logout。
    if (refreshToken.value) {
      axios.post('/api/v1/auth/logout', { refresh_token: refreshToken.value }).catch(() => {})
    }
    token.value = ''
    refreshToken.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
  }

  async function loadMe() {
    if (!token.value) return
    try {
      const res = await fetchMe()
      user.value = res.data
      localStorage.setItem('user', JSON.stringify(res.data))
    } catch (e) {
      // 401 已在拦截器处理（含刷新重试）
    }
  }

  return {
    token, refreshToken, user, isAuthenticated,
    setAuth, setTokens, updateUser, logout, loadMe,
  }
})
