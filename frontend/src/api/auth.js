import request from './request'

export const register = (data) => request.post('/api/v1/auth/register', data)
export const login = (data) => request.post('/api/v1/auth/login', data)
export const me = () => request.get('/api/v1/auth/me')
// 注册策略：是否需要邮箱验证码（由后端配置决定，前端不自作判断，避免两边不一致）
export const getRegisterPolicy = () => request.get('/api/v1/auth/register-policy')
export const sendEmailCode = (email, purpose = 'register') =>
  request.post('/api/v1/auth/email/send-code', { email, purpose })

// 找回密码：申请验证码 → 用验证码 + 新密码重置
export const forgotPassword = (email) =>
  request.post('/api/v1/auth/password/forgot', { email })
export const resetPassword = (data) =>
  request.post('/api/v1/auth/password/reset', data)
