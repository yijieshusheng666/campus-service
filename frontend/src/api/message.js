import request from './request'

export const getConversations = () => request.get('/api/v1/messages/conversations')
export const getMessages = (userId, params = {}) =>
  request.get(`/api/v1/messages/${userId}`, { params })
export const markRead = (userId) => request.put(`/api/v1/messages/${userId}/read`)
