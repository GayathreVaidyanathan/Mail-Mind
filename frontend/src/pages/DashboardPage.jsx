import React from 'react';
import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { disconnect, authStatus } from '../api/client'
import { runPipeline } from '../api/client'
import EmailCard from '../components/EmailCard'
import PipelineLog from '../components/PipelineLog'
import { LogOut, Play, Zap, CheckCircle, AlertCircle } from 'lucide-react'

export default function DashboardPage() {
  const navigate  = useNavigate()
  const [email,    setEmail]    = useState('')
  const [running,  setRunning]  = useState(false)
  const [emails,   setEmails]   = useState([])
  const [logs,     setLogs]     = useState([])
  const [total,    setTotal]    = useState(0)
  const [done,     setDone]     = useState(false)
  const [counts,   setCounts]   = useState(null)
  const [error,    setError]    = useState('')
  const esRef = useRef(null)

  // Check auth on mount
  useEffect(() => {
    authStatus()
      .then(r => {
        if (!r.data.connected) navigate('/')
        else setEmail(r.data.email || '')
      })
      .catch(() => navigate('/'))
  }, [])

  async function handleDisconnect() {
    await disconnect()
    navigate('/')
  }

  function handleRun() {
    setRunning(true)
    setEmails([])
    setLogs([])
    setTotal(0)
    setDone(false)
    setCounts(null)
    setError('')

    esRef.current = runPipeline(
      // onEvent
      (data) => {
        if (data.event === 'log') {
          setLogs(prev => [...prev, data.message])
        } else if (data.event === 'start') {
          setTotal(data.total)
          setLogs(prev => [...prev, `Found ${data.total} emails. Starting pipeline...`])
        } else if (data.event === 'email_start') {
          setLogs(prev => [...prev, `Processing ${data.index}/${data.total}: ${data.subject}`])
        } else if (data.event === 'email_done') {
          setEmails(prev => [...prev, { ...data.msg, _index: data.index }])
        }
      },
      // onError
      (err) => {
        setError('Pipeline error. Check that Ollama is running.')
        setRunning(false)
      },
      // onDone
      (data) => {
        if (data.event === 'error') {
          setError(data.detail)
        } else {
          setCounts(data.counts)
          setDone(true)
        }
        setRunning(false)
      }
    )
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>

      {/* ── Navbar ── */}
      <nav style={{
        display:        'flex',
        alignItems:     'center',
        justifyContent: 'space-between',
        padding:        '0 28px',
        height:         '56px',
        background:     'var(--surface)',
        borderBottom:   '1px solid var(--border)',
        position:       'sticky',
        top:            0,
        zIndex:         10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Zap size={18} color="var(--accent)" />
          <span style={{ fontWeight: '700', fontSize: '15px' }}>MailMind</span>
          {running && (
            <span className="pulse" style={{
              fontSize: '12px', color: 'var(--accent)',
              fontFamily: 'var(--mono)',
            }}>
              ● live
            </span>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontSize: '13px', color: 'var(--text-muted)', fontFamily: 'var(--mono)' }}>
            {email}
          </span>
          <button onClick={handleDisconnect} style={ghostBtn}>
            <LogOut size={14} />
            Disconnect
          </button>
        </div>
      </nav>

      {/* ── Main ── */}
      <main style={{ flex: 1, maxWidth: '860px', width: '100%', margin: '0 auto', padding: '32px 24px' }}>

        {/* ── Run bar ── */}
        <div style={{
          display:      'flex',
          alignItems:   'center',
          justifyContent:'space-between',
          marginBottom: '24px',
          gap:          '16px',
        }}>
          <div>
            <h1 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '2px' }}>
              Email Pipeline
            </h1>
            <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              {done
                ? `Processed ${total} emails`
                : running
                ? `Processing ${emails.length} of ${total || '?'}...`
                : 'Run the pipeline to process your unread emails'}
            </p>
          </div>
          <button
            onClick={handleRun}
            disabled={running}
            style={{
              display:      'flex',
              alignItems:   'center',
              gap:          '8px',
              padding:      '10px 20px',
              borderRadius: 'var(--radius-sm)',
              border:       'none',
              background:   running ? 'var(--surface-2)' : 'var(--accent)',
              color:        running ? 'var(--text-dim)' : '#fff',
              fontSize:     '14px',
              fontWeight:   '600',
              cursor:       running ? 'not-allowed' : 'pointer',
              transition:   'background 0.2s',
              fontFamily:   'var(--sans)',
              whiteSpace:   'nowrap',
            }}
          >
            <Play size={14} />
            {running ? 'Running...' : 'Run pipeline'}
          </button>
        </div>

        {/* ── Progress log ── */}
        {logs.length > 0 && <div style={{ marginBottom: '24px' }}><PipelineLog logs={logs} /></div>}

        {/* ── Error ── */}
        {error && (
          <div style={{
            display:      'flex',
            alignItems:   'center',
            gap:          '8px',
            padding:      '12px 16px',
            borderRadius: 'var(--radius-sm)',
            background:   '#ef444418',
            border:       '1px solid #ef444430',
            color:        '#ef4444',
            fontSize:     '13px',
            marginBottom: '24px',
          }}>
            <AlertCircle size={14} />
            {error}
          </div>
        )}

        {/* ── Done summary ── */}
        {done && counts && (
          <div style={{
            display:      'flex',
            alignItems:   'center',
            gap:          '10px',
            padding:      '12px 16px',
            borderRadius: 'var(--radius-sm)',
            background:   '#22c55e18',
            border:       '1px solid #22c55e30',
            color:        '#22c55e',
            fontSize:     '13px',
            marginBottom: '24px',
            flexWrap:     'wrap',
          }}>
            <CheckCircle size={14} />
            <span style={{ fontWeight: '600' }}>Pipeline complete —</span>
            {Object.entries(counts)
              .filter(([, n]) => n > 0)
              .map(([cat, n]) => (
                <span key={cat} style={{ color: 'var(--text-muted)' }}>
                  {cat.replace('_', ' ')}: <strong style={{ color: 'var(--text)' }}>{n}</strong>
                </span>
              ))}
          </div>
        )}

        {/* ── Email feed ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {emails.map((msg) => (
            <EmailCard key={msg.id} msg={msg} index={msg._index} />
          ))}
        </div>

        {/* ── Empty state ── */}
        {!running && !done && emails.length === 0 && (
          <div style={{
            textAlign:  'center',
            padding:    '80px 24px',
            color:      'var(--text-dim)',
          }}>
            <Zap size={32} color="var(--border)" style={{ marginBottom: '12px' }} />
            <p style={{ fontSize: '14px' }}>Hit "Run pipeline" to start processing your inbox</p>
          </div>
        )}

      </main>
    </div>
  )
}

const ghostBtn = {
  display:      'flex',
  alignItems:   'center',
  gap:          '6px',
  padding:      '7px 12px',
  borderRadius: 'var(--radius-sm)',
  border:       '1px solid var(--border)',
  background:   'transparent',
  color:        'var(--text-muted)',
  fontSize:     '13px',
  cursor:       'pointer',
  fontFamily:   'var(--sans)',
  transition:   'border-color 0.2s, color 0.2s',
}
