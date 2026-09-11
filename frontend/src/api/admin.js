import request from './request'

// 管理后台接口。全部挂在 /api/v1/admin 下，后端靠 get_current_admin 统一鉴权：
// 未登录返回 401（拦截器会跳登录页），已登录但非管理员返回 403。

export const getStats = () => request.get('/api/v1/admin/stats')

export const listUsers = (params) => request.get('/api/v1/admin/users', { params })
export const setUserActive = (id, isActive) =>
  request.put(`/api/v1/admin/users/${id}/status`, { is_active: isActive })

export const listGoods = (params) => request.get('/api/v1/admin/goods', { params })
export const setGoodsStatus = (id, status) =>
  request.put(`/api/v1/admin/goods/${id}/status`, { status })
export const deleteGoods = (id) => request.delete(`/api/v1/admin/goods/${id}`)

export const listOrders = (params) => request.get('/api/v1/admin/orders', { params })

export const listErrands = (params) => request.get('/api/v1/admin/errands', { params })
export const deleteErrand = (id) => request.delete(`/api/v1/admin/errands/${id}`)

export const listMessages = (params) => request.get('/api/v1/admin/messages', { params })
