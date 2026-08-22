import request from './request'

export const updateProfile = (data) => request.put('/api/v1/users/me', data)
export const changePassword = (data) => request.post('/api/v1/users/me/change-password', data)
