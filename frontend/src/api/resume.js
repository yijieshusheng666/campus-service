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
export const getResume = (id) => request.get(`/api/v1/resumes/${id}`)
export const updateResume = (id, editedData) => request.put(`/api/v1/resumes/${id}`, { edited_data: editedData })
export const deleteResume = (id) => request.delete(`/api/v1/resumes/${id}`)
export const improveResume = (id, jobRequirement) =>
  request.post(`/api/v1/resumes/${id}/improve`, { job_requirement: jobRequirement || null }, { timeout: 300000 })