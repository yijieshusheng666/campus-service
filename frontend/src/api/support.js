import request from './request'

export const getSupportHistory = () =>
  request.get('/api/v1/support/history')

export const clearSupportHistory = () =>
  request.post('/api/v1/support/clear')
