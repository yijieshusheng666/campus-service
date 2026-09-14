import request from './request'
import { useAuthStore } from '@/stores/auth'

export const myInterviews = () => request.get('/api/v1/interviews')
export const getInterview = (id) => request.get(`/api/v1/interviews/${id}`)
export const deleteInterview = (id) => request.delete(`/api/v1/interviews/${id}`)
export const finishInterview = (id) =>
  request.post(`/api/v1/interviews/${id}/finish`, {}, { timeout: 300000 })

/**
 * SSE 流式 POST（axios 不支持流式读取，用原生 fetch）。
 * onEvent(event, data) 依次回调 start/delta/done/error。
 */
export async function ssePost(url, body, onEvent) {
  const auth = useAuthStore()
  let resp
  try {
    resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {})
      },
      body: JSON.stringify(body)
    })
  } catch (e) {
    onEvent('error', { detail: '网络错误，请重试' })
    return
  }
  if (!resp.ok) {
    const detail = (await resp.json().catch(() => ({})))?.detail || `请求失败(${resp.status})`
    onEvent('error', { detail })
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      let event = 'message'
      let data = ''
      for (const line of raw.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) data += line.slice(6)
      }
      if (data) {
        try { onEvent(event, JSON.parse(data)) } catch { onEvent(event, { raw: data }) }
      }
    }
  }
}

export const createInterviewSse = (payload, onEvent) => ssePost('/api/v1/interviews', payload, onEvent)
export const chatInterviewSse = (id, content, onEvent) =>
  ssePost(`/api/v1/interviews/${id}/chat`, { content }, onEvent)
