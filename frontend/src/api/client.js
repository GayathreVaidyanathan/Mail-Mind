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

// ── Export ───────────────────────────────────────────────────────

export const getFolders = () =>
  api.get('/export/folders')


export const downloadFolders = async (folders) => {

  const response = await api.post(
    '/export/download',
    { folders },
    {
      responseType: 'blob',
    }
  )

  const blob = new Blob(
    [response.data],
    {
      type: 'application/zip',
    }
  )

  const url = window.URL.createObjectURL(blob)

  let filename = 'mail_export.zip'

  const disposition =
    response.headers['content-disposition']

  if (disposition) {

    const match = disposition.match(
      /filename\*?=(?:UTF-8'')?"?([^"]+)"?/
    )

    if (match) {
      filename = match[1]
    }
  }

  const link = document.createElement('a')

  link.href = url
  link.download = filename

  document.body.appendChild(link)

  link.click()

  link.remove()

  window.URL.revokeObjectURL(url)
}

// Syncs the selected folders directly into another mailbox's INBOX
// over IMAP (no file download, no SMTP — raw IMAP-to-IMAP copy).
// destination = { email, password }
export const syncToInbox = (folders, destination) =>
  api.post('/export/sync-to-inbox', { folders, destination })