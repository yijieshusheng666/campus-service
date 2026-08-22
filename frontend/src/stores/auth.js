import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { me as fetchMe } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  const isAuthenticated = computed(() => !!token.value)

  function setAuth(newToken, newUser) {
    token.value = newToken
    user.value = newUser
    localStorage.setItem('token', newToken)
    localStorage.setItem('user', JSON.stringify(newUser))
  }

  function updateUser(newUserData) {
    user.value = { ...user.value, ...newUserData }
    localStorage.setItem('user', JSON.stringify(user.value))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  async function loadMe() {
    if (!token.value) return
    try {
      const res = await fetchMe()
      user.value = res.data
      localStorage.setItem('user', JSON.stringify(res.data))
    } catch (e) {
      // 401 已在拦截器处理
    }
  }

  return { token, user, isAuthenticated, setAuth, updateUser, logout, loadMe }
})