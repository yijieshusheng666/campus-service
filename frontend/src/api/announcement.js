import request from './request'

export const listAnnouncements = (params) => request.get('/api/v1/announcements', { params })
export const getAnnouncement = (id) => request.get(`/api/v1/announcements/${id}`)
export const manageAnnouncements = () => request.get('/api/v1/announcements/manage')
export const createAnnouncement = (data) => request.post('/api/v1/announcements', data)
export const updateAnnouncement = (id, data) => request.put(`/api/v1/announcements/${id}`, data)
export const deleteAnnouncement = (id) => request.delete(`/api/v1/announcements/${id}`)
