import request from './request'

export const listGoods = (params) => request.get('/api/v1/goods', { params })
export const getGoods = (id) => request.get(`/api/v1/goods/${id}`)
export const createGoods = (data) => request.post('/api/v1/goods', data)
export const updateGoods = (id, data) => request.put(`/api/v1/goods/${id}`, data)
export const deleteGoods = (id) => request.delete(`/api/v1/goods/${id}`)
export const myGoods = () => request.get('/api/v1/goods/mine')
export const categories = () => request.get('/api/v1/goods/categories')
export const uploadImage = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/api/v1/goods/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

export const addFavorite = (id) => request.post(`/api/v1/favorites/${id}`)
export const removeFavorite = (id) => request.delete(`/api/v1/favorites/${id}`)
export const myFavorites = () => request.get('/api/v1/favorites')