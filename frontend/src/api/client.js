import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// ── Auth ──────────────────────────────────────────────────────────
export const connect = (email, password) =>
  api.post('/auth/connect', { email, password })

export const disconnect = () =>
  api.post('/auth/disconnect')

export const authStatus = () =>
  api.get('/auth/status')

// ── Pipeline ──────────────────────────────────────────────────────
export const pipelineStatus = () =>
  api.get('/pipeline/status')

// SSE — returns an EventSource, not an axios call
export const runPipeline = (onEvent, onError, onDone) => {
  const es = new EventSource('/api/pipeline/run')

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)

      if (data.event === 'done' || data.event === 'error') {
        onDone(data)
        es.close()
      } else {
        onEvent(data)
      }
    } catch (err) {
      console.error('SSE parse error:', err)
    }
  }

  es.onerror = (err) => {
    onError(err)
    es.close()
  }

  return es  // caller can call es.close() to cancel
}