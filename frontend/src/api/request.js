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

// ---- 401 自动刷新（single-flight）----
// 并发多个请求同时 401 时，只发一次 /auth/refresh，其余等同一个 Promise，
// 否则第二个请求拿着已被轮换作废的旧 refresh 去换，会触发后端「重放检测」，
// 把用户所有端的登录全部吊销 —— 这是双令牌 + 轮换方案最容易踩的前端坑。
let refreshing = null

function doRefresh() {
  const auth = useAuthStore()
  if (!auth.refreshToken) return Promise.resolve(false)
  if (!refreshing) {
    refreshing = axios
      .post('/api/v1/auth/refresh', { refresh_token: auth.refreshToken })
      .then((res) => {
        auth.setTokens(res.data.access_token, res.data.refresh_token)
        return true
      })
      .catch(() => {
        auth.logout()
        return false
      })
      .finally(() => { refreshing = null })
  }
  return refreshing
}

service.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status
    const detail =
      error.response?.data?.detail ||
      (typeof error.response?.data === 'object'
        ? JSON.stringify(error.response.data)
        : error.response?.data) ||
      error.message ||
      '请求失败'

    if (status === 401) {
      const config = error.config || {}
      const auth = useAuthStore()
      // 401 且还没重试过 → 先尝试用 refresh 换新令牌，成功则重放原请求
      if (!config._retry && auth.refreshToken && (await doRefresh())) {
        config._retry = true
        config.headers = config.headers || {}
        config.headers.Authorization = `Bearer ${auth.token}`
        return service(config)
      }
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
