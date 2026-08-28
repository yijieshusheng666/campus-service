import request from './request'

export const listErrands = (role = 'all') =>
  request.get('/api/v1/errands', { params: { role } })
export const getErrand = (id) => request.get(`/api/v1/errands/${id}`)
export const publishErrand = (payload) => request.post('/api/v1/errands', payload)
export const acceptErrand = (id) => request.put(`/api/v1/errands/${id}/accept`)
export const updateErrandStatus = (id, status) =>
  request.put(`/api/v1/errands/${id}/status`, { status })
