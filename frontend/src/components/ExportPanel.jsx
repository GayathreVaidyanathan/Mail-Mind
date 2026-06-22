import React, { useEffect, useState } from 'react'
import { getFolders, downloadFolders, syncToInbox, uploadEmails, checkDestinationFolders } from '../api/client'
import { Download, Folder, Send, X, Star, Inbox, Settings, Upload, FileArchive } from 'lucide-react'

// ── Helpers ───────────────────────────────────────────────────────

function groupFolders(folders) {
  const inbox  = folders.filter(f => f.type === 'inbox')
  const system = folders.filter(f => f.type === 'system' && f.special_use !== '\\flagged')
  const custom = folders.filter(f => f.type === 'custom')
  // Starred folder — may exist as a real folder (Gmail) or not at all
  const starredFolder = folders.find(f => f.special_use === '\\flagged') || null
  return { inbox, system, custom, starredFolder }
}

function SectionLabel({ icon: Icon, label }) {
  return (
    <p style={{
      display:    'flex',
      alignItems: 'center',
      gap:        '6px',
      margin:     '12px 0 6px',
      fontSize:   '11px',
      fontWeight: '600',
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      color: 'var(--text-dim)',
    }}>
      <Icon size={11} />
      {label}
    </p>
  )
}

function FolderCheckbox({ folder, selected, onToggle }) {
  return (
    <label style={{
      display:    'flex',
      alignItems: 'center',
      gap:        '8px',
      cursor:     'pointer',
      fontSize:   '14px',
      padding:    '2px 0',
    }}>
      <input
        type="checkbox"
        checked={selected}
        onChange={() => onToggle(folder.name)}
      />
      {folder.label}
    </label>
  )
}

// ── Main component ────────────────────────────────────────────────

export default function ExportPanel() {

  const [folders,     setFolders]     = useState([])
  const [selected,    setSelected]    = useState([])   // raw IMAP folder names
  const [inclStarred, setInclStarred] = useState(false)
  const [loading,     setLoading]     = useState(true)
  const [downloading, setDownloading] = useState(false)
  const [error,       setError]       = useState('')

  // Sync form
  const [showSyncForm,  setShowSyncForm]  = useState(false)
  const [destEmail,     setDestEmail]     = useState('')
  const [destPassword,  setDestPassword]  = useState('')
  const [syncing,       setSyncing]       = useState(false)
  const [syncResult,    setSyncResult]    = useState(null)
  const [syncError,     setSyncError]     = useState('')

  // Upload form
  const [showUploadForm,   setShowUploadForm]   = useState(false)
  const [uploadFile,       setUploadFile]       = useState(null)
  const [preserveStructure,setPreserveStructure]= useState(true)
  const [uploadDestEmail,    setUploadDestEmail]    = useState('')
  const [uploadDestPassword, setUploadDestPassword] = useState('')
  const [uploadDestFolder, setUploadDestFolder] = useState('')
  const [destFolders,        setDestFolders]        = useState([])   // folders of the DESTINATION mailbox, fetched on demand
  const [checkingFolders,    setCheckingFolders]    = useState(false)
  const [checkFoldersError,  setCheckFoldersError] = useState('')
  const [uploading,        setUploading]        = useState(false)
  const [uploadResult,     setUploadResult]     = useState(null)
  const [uploadError,      setUploadError]      = useState('')

  useEffect(() => { loadFolders() }, [])

  async function loadFolders() {
    try {
      setLoading(true)
      const response = await getFolders()
      setFolders(response.data.folders || [])
    } catch (err) {
      setError('Could not load folders.')
    } finally {
      setLoading(false)
    }
  }

  function toggleFolder(name) {
    setSelected(prev =>
      prev.includes(name)
        ? prev.filter(f => f !== name)
        : [...prev, name]
    )
  }

  const { inbox, system, custom, starredFolder } = groupFolders(folders)

  const nothingSelected = selected.length === 0 && !inclStarred

  // The raw IMAP name of the starred folder (empty string = use flag-search fallback)
  const starredFolderName = starredFolder?.name || ''

  async function handleDownload() {
    if (nothingSelected) return
    try {
      setDownloading(true)
      setError('')
      await downloadFolders(selected, inclStarred, starredFolderName)
    } catch (err) {
      setError('Download failed.')
    } finally {
      setDownloading(false)
    }
  }

  function openSyncForm() {
    setSyncResult(null)
    setSyncError('')
    setShowSyncForm(true)
  }

  async function handleSync() {
    if (nothingSelected || !destEmail || !destPassword) return
    try {
      setSyncing(true)
      setSyncError('')
      setSyncResult(null)
      const response = await syncToInbox(
        selected,
        { email: destEmail, password: destPassword },
        inclStarred,
        starredFolderName,
      )
      setSyncResult(response.data)
    } catch (err) {
      setSyncError(err?.response?.data?.detail || 'Sync failed.')
    } finally {
      setSyncing(false)
    }
  }

  function openUploadForm() {
    setUploadResult(null)
    setUploadError('')
    setDestFolders([])
    setCheckFoldersError('')
    setUploadDestFolder('')
    setShowUploadForm(true)
  }

  function handleFileChange(e) {
    const file = e.target.files?.[0] || null
    setUploadFile(file)
    setUploadResult(null)
    setUploadError('')
  }

  const isZipUpload = uploadFile?.name?.toLowerCase().endsWith('.zip')

  async function handleCheckFolders() {
    if (!uploadDestEmail || !uploadDestPassword) return
    try {
      setCheckingFolders(true)
      setCheckFoldersError('')
      setDestFolders([])
      setUploadDestFolder('')
      const response = await checkDestinationFolders({
        email:    uploadDestEmail,
        password: uploadDestPassword,
      })
      setDestFolders(response.data.folders || [])
    } catch (err) {
      setCheckFoldersError(err?.response?.data?.detail || 'Could not connect to that mailbox.')
    } finally {
      setCheckingFolders(false)
    }
  }

  async function handleUpload() {
    if (!uploadFile || !uploadDestEmail || !uploadDestPassword) return
    // When not preserving structure, a destination folder is required
    if ((!preserveStructure || !isZipUpload) && !uploadDestFolder) return

    try {
      setUploading(true)
      setUploadError('')
      setUploadResult(null)

      const destFolder = (preserveStructure && isZipUpload) ? '' : uploadDestFolder

      const response = await uploadEmails(
        uploadFile,
        { email: uploadDestEmail, password: uploadDestPassword },
        destFolder,
      )
      setUploadResult(response.data)
    } catch (err) {
      setUploadError(err?.response?.data?.detail || 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div style={{
      padding:      '20px',
      border:       '1px solid var(--border)',
      borderRadius: 'var(--radius-sm)',
      background:   'var(--surface)',
    }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
        <Folder size={18} />
        <h2 style={{ margin: 0, fontSize: '16px' }}>
          Export Labels ({folders.length})
        </h2>
      </div>

      {loading && <p style={{ color: 'var(--text-muted)', marginTop: '12px' }}>Loading folders...</p>}
      {error   && <p style={{ color: '#ef4444',          marginTop: '12px' }}>{error}</p>}
      {!loading && folders.length === 0 && (
        <p style={{ color: 'var(--text-muted)', marginTop: '12px' }}>No folders found.</p>
      )}

      {!loading && folders.length > 0 && (
        <>
          {/* ── Folder list, grouped ── */}
          <div style={{
            maxHeight: '420px',
            overflowY: 'auto',
            paddingRight: '8px',
            marginBottom: '16px',
          }}>

            {/* Inbox */}
            {inbox.length > 0 && (
              <>
                <SectionLabel icon={Inbox} label="Inbox" />
                {inbox.map(f => (
                  <FolderCheckbox
                    key={f.name}
                    folder={f}
                    selected={selected.includes(f.name)}
                    onToggle={toggleFolder}
                  />
                ))}
              </>
            )}

            {/* System folders */}
            {system.length > 0 && (
              <>
                <SectionLabel icon={Settings} label="System" />
                {system.map(f => (
                  <FolderCheckbox
                    key={f.name}
                    folder={f}
                    selected={selected.includes(f.name)}
                    onToggle={toggleFolder}
                  />
                ))}
              </>
            )}

            {/* Custom labels */}
            {custom.length > 0 && (
              <>
                <SectionLabel icon={Folder} label="Labels" />
                {custom.map(f => (
                  <FolderCheckbox
                    key={f.name}
                    folder={f}
                    selected={selected.includes(f.name)}
                    onToggle={toggleFolder}
                  />
                ))}
              </>
            )}

            {/* Starred — always shown as a separate toggle */}
            <SectionLabel icon={Star} label="Starred" />
            <label style={{
              display:    'flex',
              alignItems: 'center',
              gap:        '8px',
              cursor:     'pointer',
              fontSize:   '14px',
              padding:    '2px 0',
            }}>
              <input
                type="checkbox"
                checked={inclStarred}
                onChange={e => setInclStarred(e.target.checked)}
              />
              ⭐ Starred emails
              {starredFolder && (
                <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                  (via {starredFolder.name})
                </span>
              )}
            </label>

          </div>

          {nothingSelected && (
            <p style={{
              fontSize: '12px',
              color: 'var(--text-dim)',
              marginBottom: '10px',
            }}>
              Select at least one folder or starred to download or sync.
            </p>
          )}

          {/* Download button */}
          <button
            onClick={handleDownload}
            disabled={nothingSelected || downloading}
            style={{
              display:        'flex',
              alignItems:     'center',
              justifyContent: 'center',
              gap:            '8px',
              width:          '100%',
              padding:        '10px 18px',
              border:         'none',
              borderRadius:   'var(--radius-sm)',
              background:     nothingSelected || downloading ? 'var(--surface-2)' : 'var(--accent)',
              color:          nothingSelected || downloading ? 'var(--text-dim)'  : '#fff',
              cursor:         nothingSelected || downloading ? 'not-allowed'      : 'pointer',
              fontWeight:     '600',
              marginBottom:   '10px',
            }}
          >
            <Download size={16} />
            {downloading ? 'Downloading...' : 'Download Selected'}
          </button>

          {/* Sync button */}
          <button
            onClick={openSyncForm}
            disabled={nothingSelected}
            style={{
              display:        'flex',
              alignItems:     'center',
              justifyContent: 'center',
              gap:            '8px',
              width:          '100%',
              padding:        '10px 18px',
              border:         '1px solid var(--border)',
              borderRadius:   'var(--radius-sm)',
              background:     'transparent',
              color:          nothingSelected ? 'var(--text-dim)' : 'var(--text)',
              cursor:         nothingSelected ? 'not-allowed'     : 'pointer',
              fontWeight:     '600',
              marginBottom:   '10px',
            }}
          >
            <Send size={16} />
            Sync to another inbox
          </button>

          {/* Upload button — no folder selection required, so never disabled by nothingSelected */}
          <button
            onClick={openUploadForm}
            style={{
              display:        'flex',
              alignItems:     'center',
              justifyContent: 'center',
              gap:            '8px',
              width:          '100%',
              padding:        '10px 18px',
              border:         '1px solid var(--border)',
              borderRadius:   'var(--radius-sm)',
              background:     'transparent',
              color:          'var(--text)',
              cursor:         'pointer',
              fontWeight:     '600',
            }}
          >
            <Upload size={16} />
            Upload local emails
          </button>

          {/* Sync form */}
          {showSyncForm && (
            <div style={{
              marginTop:    '16px',
              padding:      '16px',
              border:       '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              background:   'var(--surface-2)',
            }}>
              <div style={{
                display:        'flex',
                alignItems:     'center',
                justifyContent: 'space-between',
                marginBottom:   '8px',
              }}>
                <p style={{ margin: 0, fontSize: '14px', fontWeight: '600' }}>
                  Destination mailbox
                </p>
                <button
                  onClick={() => setShowSyncForm(false)}
                  style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex' }}
                  aria-label="Close"
                >
                  <X size={16} />
                </button>
              </div>

              <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '0 0 12px' }}>
                Works with any IMAP provider. Use an app password — credentials are not saved.
              </p>

              <input
                type="email"
                placeholder="destination@example.com"
                value={destEmail}
                onChange={e => setDestEmail(e.target.value)}
                style={inputStyle}
              />
              <input
                type="password"
                placeholder="App password"
                value={destPassword}
                onChange={e => setDestPassword(e.target.value)}
                style={{ ...inputStyle, marginBottom: '12px' }}
              />

              <button
                onClick={handleSync}
                disabled={syncing || !destEmail || !destPassword}
                style={{
                  display:        'flex',
                  alignItems:     'center',
                  justifyContent: 'center',
                  gap:            '8px',
                  width:          '100%',
                  padding:        '9px 16px',
                  border:         'none',
                  borderRadius:   'var(--radius-sm)',
                  background:     syncing || !destEmail || !destPassword ? 'var(--surface-2)' : 'var(--accent)',
                  color:          syncing || !destEmail || !destPassword ? 'var(--text-dim)'  : '#fff',
                  cursor:         syncing || !destEmail || !destPassword ? 'not-allowed'      : 'pointer',
                  fontWeight:     '600',
                }}
              >
                <Send size={14} />
                {syncing
                  ? 'Syncing...'
                  : `Sync ${selected.length} folder(s)${inclStarred ? ' + Starred' : ''}`}
              </button>

              {syncError && (
                <p style={{ color: '#ef4444', fontSize: '13px', marginTop: '10px', marginBottom: 0 }}>
                  {syncError}
                </p>
              )}

              {syncResult && (
                <p style={{
                  color:        syncResult.failed.length > 0 ? '#f59e0b' : '#22c55e',
                  fontSize:     '13px',
                  marginTop:    '10px',
                  marginBottom: 0,
                }}>
                  Synced {syncResult.synced} email(s) to {destEmail}.
                  {syncResult.failed.length > 0 && ` ${syncResult.failed.length} failed.`}
                </p>
              )}
            </div>
          )}

          {/* Upload form */}
          {showUploadForm && (
            <div style={{
              marginTop:    '16px',
              padding:      '16px',
              border:       '1px solid var(--border)',
              borderRadius: 'var(--radius-sm)',
              background:   'var(--surface-2)',
            }}>
              <div style={{
                display:        'flex',
                alignItems:     'center',
                justifyContent: 'space-between',
                marginBottom:   '8px',
              }}>
                <p style={{ margin: 0, fontSize: '14px', fontWeight: '600' }}>
                  Upload to a mailbox
                </p>
                <button
                  onClick={() => setShowUploadForm(false)}
                  style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--text-muted)', display: 'flex' }}
                  aria-label="Close"
                >
                  <X size={16} />
                </button>
              </div>

              <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '0 0 12px' }}>
                Upload a local .eml file, or a .zip from a previous download,
                into any mailbox — works with any IMAP provider. Use an app
                password — credentials are not saved.
              </p>

              {/* File picker */}
              <label style={{
                display:        'flex',
                alignItems:     'center',
                justifyContent: 'center',
                gap:            '8px',
                width:          '100%',
                padding:        '14px',
                marginBottom:   '12px',
                border:         '1px dashed var(--border)',
                borderRadius:   'var(--radius-sm)',
                background:     'var(--surface)',
                color:          uploadFile ? 'var(--text)' : 'var(--text-muted)',
                fontSize:       '13px',
                cursor:         'pointer',
                boxSizing:      'border-box',
              }}>
                <FileArchive size={15} />
                {uploadFile ? uploadFile.name : 'Choose .eml or .zip file'}
                <input
                  type="file"
                  accept=".eml,.zip"
                  onChange={handleFileChange}
                  style={{ display: 'none' }}
                />
              </label>

              {/* Structure choice — only meaningful for zip uploads */}
              {isZipUpload && (
                <div style={{ marginBottom: '12px' }}>
                  <label style={{
                    display:    'flex',
                    alignItems: 'center',
                    gap:        '8px',
                    cursor:     'pointer',
                    fontSize:   '13px',
                    padding:    '3px 0',
                  }}>
                    <input
                      type="radio"
                      name="upload-structure"
                      checked={preserveStructure}
                      onChange={() => setPreserveStructure(true)}
                    />
                    Preserve original folder structure
                  </label>
                  <label style={{
                    display:    'flex',
                    alignItems: 'center',
                    gap:        '8px',
                    cursor:     'pointer',
                    fontSize:   '13px',
                    padding:    '3px 0',
                  }}>
                    <input
                      type="radio"
                      name="upload-structure"
                      checked={!preserveStructure}
                      onChange={() => setPreserveStructure(false)}
                    />
                    Put everything in one folder
                  </label>
                </div>
              )}

              {/* Destination mailbox credentials — same pattern as Sync */}
              <p style={{ fontSize: '12px', fontWeight: '600', color: 'var(--text-muted)', margin: '4px 0 6px' }}>
                Destination mailbox
              </p>
              <input
                type="email"
                placeholder="destination@example.com"
                value={uploadDestEmail}
                onChange={e => {
                  setUploadDestEmail(e.target.value)
                  setDestFolders([])
                  setUploadDestFolder('')
                }}
                style={inputStyle}
              />
              <input
                type="password"
                placeholder="App password"
                value={uploadDestPassword}
                onChange={e => {
                  setUploadDestPassword(e.target.value)
                  setDestFolders([])
                  setUploadDestFolder('')
                }}
                style={{ ...inputStyle, marginBottom: '8px' }}
              />

              {/* Only need to actually know the destination's folders when
                  we're not preserving structure, or it's a standalone .eml */}
              {(!preserveStructure || !isZipUpload) && (
                <>
                  <button
                    onClick={handleCheckFolders}
                    disabled={checkingFolders || !uploadDestEmail || !uploadDestPassword}
                    style={{
                      display:        'flex',
                      alignItems:     'center',
                      justifyContent: 'center',
                      gap:            '8px',
                      width:          '100%',
                      padding:        '8px 14px',
                      marginBottom:   '10px',
                      border:         '1px solid var(--border)',
                      borderRadius:   'var(--radius-sm)',
                      background:     'transparent',
                      color:          (checkingFolders || !uploadDestEmail || !uploadDestPassword) ? 'var(--text-dim)' : 'var(--text)',
                      cursor:         (checkingFolders || !uploadDestEmail || !uploadDestPassword) ? 'not-allowed' : 'pointer',
                      fontWeight:     '600',
                      fontSize:       '13px',
                    }}
                  >
                    <Folder size={14} />
                    {checkingFolders ? 'Checking folders...' : 'Check folders'}
                  </button>

                  {checkFoldersError && (
                    <p style={{ color: '#ef4444', fontSize: '13px', marginTop: '0', marginBottom: '10px' }}>
                      {checkFoldersError}
                    </p>
                  )}

                  {destFolders.length > 0 && (
                    <select
                      value={uploadDestFolder}
                      onChange={e => setUploadDestFolder(e.target.value)}
                      style={{ ...inputStyle, marginBottom: '12px' }}
                    >
                      <option value="">Select destination folder...</option>
                      {destFolders.map(f => (
                        <option key={f.name} value={f.name}>{f.label}</option>
                      ))}
                    </select>
                  )}
                </>
              )}

              <button
                onClick={handleUpload}
                disabled={
                  uploading ||
                  !uploadFile ||
                  !uploadDestEmail ||
                  !uploadDestPassword ||
                  ((!preserveStructure || !isZipUpload) && !uploadDestFolder)
                }
                style={{
                  display:        'flex',
                  alignItems:     'center',
                  justifyContent: 'center',
                  gap:            '8px',
                  width:          '100%',
                  padding:        '9px 16px',
                  border:         'none',
                  borderRadius:   'var(--radius-sm)',
                  background:     uploading || !uploadFile ? 'var(--surface-2)' : 'var(--accent)',
                  color:          uploading || !uploadFile ? 'var(--text-dim)'  : '#fff',
                  cursor:         uploading || !uploadFile ? 'not-allowed'      : 'pointer',
                  fontWeight:     '600',
                }}
              >
                <Upload size={14} />
                {uploading ? 'Uploading...' : 'Upload'}
              </button>

              {uploadError && (
                <p style={{ color: '#ef4444', fontSize: '13px', marginTop: '10px', marginBottom: 0 }}>
                  {uploadError}
                </p>
              )}

              {uploadResult && (
                <p style={{
                  color:        uploadResult.failed.length > 0 ? '#f59e0b' : '#22c55e',
                  fontSize:     '13px',
                  marginTop:    '10px',
                  marginBottom: 0,
                }}>
                  Imported {uploadResult.imported} email(s).
                  {uploadResult.failed.length > 0 && ` ${uploadResult.failed.length} failed.`}
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}

const inputStyle = {
  width:        '100%',
  padding:      '8px 10px',
  marginBottom: '8px',
  borderRadius: 'var(--radius-sm)',
  border:       '1px solid var(--border)',
  background:   'var(--surface)',
  color:        'var(--text)',
  fontSize:     '13px',
  boxSizing:    'border-box',
}