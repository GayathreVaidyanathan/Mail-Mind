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

  return es
}

// ── Export ───────────────────────────────────────────────────────

// Returns: { folders: [{ name, label, type, special_use }] }
// type: "inbox" | "system" | "custom"
// special_use: RFC 6154 attribute e.g. "\\sent", or ""
export const getFolders = () =>
  api.get('/export/folders')


// folders: list of raw IMAP folder names (the "name" field from getFolders)
// includeStarred: bool
// starredFolder: raw IMAP name of the starred folder if server exposes one (e.g. "[Gmail]/Starred"), else ""
export const downloadFolders = async (folders, includeStarred = false, starredFolder = '') => {

  const response = await api.post(
    '/export/download',
    {
      folders,
      include_starred: includeStarred,
      starred_folder:  starredFolder,
    },
    { responseType: 'blob' }
  )

  const blob = new Blob([response.data], { type: 'application/zip' })
  const url  = window.URL.createObjectURL(blob)

  let filename = 'mail_export.zip'
  const disposition = response.headers['content-disposition']
  if (disposition) {
    const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^"]+)"?/)
    if (match) filename = match[1]
  }

  const link = document.createElement('a')
  link.href     = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}


// destination: { email, password }
// includeStarred: bool
// starredFolder: raw IMAP name of the starred folder if server exposes one, else ""
export const syncToInbox = (folders, destination, includeStarred = false, starredFolder = '') =>
  api.post('/export/sync-to-inbox', {
    folders,
    destination,
    include_starred: includeStarred,
    starred_folder:  starredFolder,
  })


// file: a File object (.eml or .zip) from an <input type="file"> element
// destination: { email, password } — same shape as syncToInbox's destination
// destFolder: raw IMAP folder name on the DESTINATION mailbox to force
//   everything into. '' (default) = preserve original structure from the
//   zip (each subfolder maps to its own destination IMAP folder); ignored
//   for a standalone .eml upload, which always needs an explicit
//   destFolder or falls back to INBOX server-side.
// Returns: { imported: number, failed: [{ file, folder, error }] }
export const uploadEmails = (file, destination, destFolder = '') => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('dest_email', destination.email)
  formData.append('dest_password', destination.password)
  formData.append('dest_folder', destFolder)

  return api.post('/export/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}


// destination: { email, password }
// Connects to an arbitrary destination mailbox (independent of whatever
// mailbox is currently active) and returns its folder list, so the
// Upload UI can offer a dropdown of the DESTINATION's real folders.
// Returns: { folders: [{ name, label, type, special_use }] }
export const checkDestinationFolders = (destination) =>
  api.post('/export/check-destination-folders', { destination })