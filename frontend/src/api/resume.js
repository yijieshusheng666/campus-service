import request from './request'

export const uploadResume = (file) => {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/api/v1/resumes/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 300000
  })
}
export const myResumes = () => request.get('/api/v1/resumes/mine')
export const deleteResume = (id) => request.delete(`/api/v1/resumes/${id}`)
export const generateAdvice = (id, jobRequirement) =>
  request.post(`/api/v1/resumes/${id}/advice`, { job_requirement: jobRequirement || null }, { timeout: 300000 })
export const reparseResume = (id) => request.post(`/api/v1/resumes/${id}/reparse`)