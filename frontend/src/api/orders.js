import request from './request'

export const createOrder = (data) => request.post('/api/v1/orders', data)
export const myOrders = (role = 'buyer') => request.get('/api/v1/orders', { params: { role } })
export const updateOrderStatus = (id, status) => request.put(`/api/v1/orders/${id}/status`, { status })
