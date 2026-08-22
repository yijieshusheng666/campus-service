import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

const service = axios.create({
  baseURL: '',
  timeout: 60000
})

service.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

service.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status
    const detail =
      error.response?.data?.detail ||
      (typeof error.response?.data === 'object'
        ? JSON.stringify(error.response.data)
        : error.response?.data) ||
      error.message ||
      '请求失败'

    if (status === 401) {
      const auth = useAuthStore()
      auth.logout()
      if (router.currentRoute.value.name !== 'Login') {
        router.push({ name: 'Login' })
        ElMessage.warning('登录已过期，请重新登录')
      }
    } else {
      ElMessage.error(detail)
    }
    return Promise.reject(error)
  }
)

export default service