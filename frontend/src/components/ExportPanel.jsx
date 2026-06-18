import React, { useEffect, useState } from 'react'
import { getFolders, downloadFolders, syncToInbox } from '../api/client'
import { Download, Folder, Send, X } from 'lucide-react'

export default function ExportPanel() {

  const [folders, setFolders] = useState([])
  const [selected, setSelected] = useState([])
  const [loading, setLoading] = useState(true)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState('')

  // ── Sync-to-inbox state (new, additive) ──
  const [showSyncForm, setShowSyncForm] = useState(false)
  const [destEmail, setDestEmail] = useState('')
  const [destPassword, setDestPassword] = useState('')
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)
  const [syncError, setSyncError] = useState('')

  useEffect(() => {
    loadFolders()
  }, [])

  async function loadFolders() {
    try {
      setLoading(true)

      const response = await getFolders()

      const allFolders =
        response.data.folders || []

      const visibleFolders =
        allFolders.filter(
          f =>
            !f.startsWith('[Gmail]') &&
            f !== 'INBOX'
        )

      setFolders(visibleFolders)
    }
    catch (err) {
      setError('Could not load folders.')
    }
    finally {
      setLoading(false)
    }
  }

  function toggleFolder(folder) {

    if (selected.includes(folder)) {
      setSelected(
        selected.filter(f => f !== folder)
      )
    }
    else {
      setSelected(
        [...selected, folder]
      )
    }
  }

  async function handleDownload() {

    if (selected.length === 0)
      return

    try {

      setDownloading(true)

      await downloadFolders(selected)

    }
    catch (err) {

      setError('Download failed.')

    }
    finally {

      setDownloading(false)

    }
  }

  // ── Sync-to-inbox handlers (new, additive) ──

  function openSyncForm() {
    setSyncResult(null)
    setSyncError('')
    setShowSyncForm(true)
  }

  function closeSyncForm() {
    setShowSyncForm(false)
  }

  async function handleSync() {

    if (selected.length === 0 || !destEmail || !destPassword)
      return

    try {

      setSyncing(true)
      setSyncError('')
      setSyncResult(null)

      const response = await syncToInbox(
        selected,
        { email: destEmail, password: destPassword }
      )

      setSyncResult(response.data)

    }
    catch (err) {

      const detail =
        err?.response?.data?.detail || 'Sync failed.'

      setSyncError(detail)

    }
    finally {

      setSyncing(false)

    }
  }

  return (
    <div
      style={{
        padding: '20px',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-sm)',
        background: 'var(--surface)',
      }}
    >

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '16px',
        }}
      >
        <Folder size={18} />

        <h2
          style={{
            margin: 0,
            fontSize: '16px',
          }}
        >
          Export Labels ({folders.length})
        </h2>
      </div>

      {loading && (
        <p style={{ color: 'var(--text-muted)' }}>
          Loading folders...
        </p>
      )}

      {error && (
        <p style={{ color: '#ef4444' }}>
          {error}
        </p>
      )}

      {!loading && folders.length === 0 && (
        <p style={{ color: 'var(--text-muted)' }}>
          No folders found.
        </p>
      )}

      {!loading && folders.length > 0 && (
        <>
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
              marginBottom: '20px',
              maxHeight: '420px',
              overflowY: 'auto',
              paddingRight: '8px',
            }}
          >
            {folders.map(folder => (
              <label
                key={folder}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  cursor: 'pointer',
                  fontSize: '14px',
                }}
              >
                <input
                  type="checkbox"
                  checked={selected.includes(folder)}
                  onChange={() => toggleFolder(folder)}
                />

                {folder}
              </label>
            ))}
          </div>

          {/* ── Existing: Download Selected (unchanged) ── */}
          <button
            onClick={handleDownload}
            disabled={
              selected.length === 0 || downloading
            }
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              width: '100%',
              padding: '10px 18px',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              background:
                selected.length === 0 || downloading
                  ? 'var(--surface-2)'
                  : 'var(--accent)',
              color:
                selected.length === 0 || downloading
                  ? 'var(--text-dim)'
                  : '#fff',
              cursor:
                selected.length === 0 || downloading
                  ? 'not-allowed'
                  : 'pointer',
              fontWeight: '600',
              marginBottom: '10px',
            }}
          >
            <Download size={16} />

            {downloading
              ? 'Downloading...'
              : 'Download Selected'}
          </button>

          {/* ── New: Sync to another inbox ── */}
          <button
            onClick={openSyncForm}
            disabled={selected.length === 0}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              width: '100%',
              padding: '10px 18px',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              background: 'transparent',
              color:
                selected.length === 0
                  ? 'var(--text-dim)'
                  : 'var(--text)',
              cursor:
                selected.length === 0
                  ? 'not-allowed'
                  : 'pointer',
              fontWeight: '600',
            }}
          >
            <Send size={16} />
            Sync to another inbox
          </button>

          {selected.length === 0 && (
            <p style={{
              fontSize: '12px',
              color: 'var(--text-dim)',
              marginTop: '8px',
              marginBottom: 0,
            }}>
              Select at least one folder to download or sync.
            </p>
          )}
        </>
      )}

      {/* ── Sync credentials form (new, additive) ── */}
      {showSyncForm && (
        <div
          style={{
            marginTop: '16px',
            padding: '16px',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--surface-2)',
          }}
        >
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '12px',
          }}>
            <p style={{ margin: 0, fontSize: '14px', fontWeight: '600' }}>
              Destination mailbox
            </p>
            <button
              onClick={closeSyncForm}
              style={{
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                color: 'var(--text-muted)',
                display: 'flex',
              }}
              aria-label="Close"
            >
              <X size={16} />
            </button>
          </div>

          <p style={{
            fontSize: '12px',
            color: 'var(--text-muted)',
            marginTop: 0,
            marginBottom: '12px',
          }}>
            Works with any IMAP provider — Gmail, Outlook, Yahoo, etc.
            Use an app password, not your regular login password.
            Nothing is saved after this sync.
          </p>

          <input
            type="email"
            placeholder="destination@example.com"
            value={destEmail}
            onChange={e => setDestEmail(e.target.value)}
            style={{
              width: '100%',
              padding: '8px 10px',
              marginBottom: '8px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text)',
              fontSize: '13px',
            }}
          />

          <input
            type="password"
            placeholder="App password"
            value={destPassword}
            onChange={e => setDestPassword(e.target.value)}
            style={{
              width: '100%',
              padding: '8px 10px',
              marginBottom: '12px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border)',
              background: 'var(--surface)',
              color: 'var(--text)',
              fontSize: '13px',
            }}
          />

          <button
            onClick={handleSync}
            disabled={
              syncing || !destEmail || !destPassword
            }
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              width: '100%',
              padding: '9px 16px',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              background:
                syncing || !destEmail || !destPassword
                  ? 'var(--surface-2)'
                  : 'var(--accent)',
              color:
                syncing || !destEmail || !destPassword
                  ? 'var(--text-dim)'
                  : '#fff',
              cursor:
                syncing || !destEmail || !destPassword
                  ? 'not-allowed'
                  : 'pointer',
              fontWeight: '600',
            }}
          >
            <Send size={14} />
            {syncing ? 'Syncing...' : `Sync ${selected.length} folder(s)`}
          </button>

          {syncError && (
            <p style={{
              color: '#ef4444',
              fontSize: '13px',
              marginTop: '10px',
              marginBottom: 0,
            }}>
              {syncError}
            </p>
          )}

          {syncResult && (
            <p style={{
              color: syncResult.failed.length > 0 ? '#f59e0b' : '#22c55e',
              fontSize: '13px',
              marginTop: '10px',
              marginBottom: 0,
            }}>
              Synced {syncResult.synced} email(s) to {destEmail}'s inbox.
              {syncResult.failed.length > 0 &&
                ` ${syncResult.failed.length} failed.`}
            </p>
          )}
        </div>
      )}

    </div>
  )
}