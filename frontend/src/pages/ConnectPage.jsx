import React from 'react';
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { connect } from '../api/client'
import { Mail, Lock, Zap, AlertCircle } from 'lucide-react'

export default function ConnectPage() {
  const navigate  = useNavigate()
  const [email,    setEmail]    = useState('')
  const [password, setPassword] = useState('')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')

  async function handleConnect() {
    if (!email || !password) {
      setError('Please enter both email and app password.')
      return
    }
    setLoading(true)
    setError('')
    try {
      await connect(email, password)
      navigate('/dashboard')
    } catch (err) {
      setError(err.response?.data?.detail || 'Connection failed. Check your credentials.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight:      '100vh',
      display:        'flex',
      alignItems:     'center',
      justifyContent: 'center',
      padding:        '24px',
      background:     'radial-gradient(ellipse at 50% 0%, #0ea5e915 0%, var(--bg) 70%)',
    }}>
      <div style={{ width: '100%', maxWidth: '420px' }}>

        {/* ── Logo + title ── */}
        <div style={{ textAlign: 'center', marginBottom: '40px' }}>
          <div style={{
            display:        'inline-flex',
            alignItems:     'center',
            justifyContent: 'center',
            width:          '52px',
            height:         '52px',
            borderRadius:   '14px',
            background:     'var(--accent-dim)',
            border:         '1px solid var(--accent)30',
            marginBottom:   '16px',
          }}>
            <Zap size={24} color="var(--accent)" />
          </div>
          <h1 style={{ fontSize: '24px', fontWeight: '700', color: 'var(--text)', marginBottom: '6px' }}>
            MailMind
          </h1>
          <p style={{ fontSize: '14px', color: 'var(--text-muted)' }}>
            AI-powered email pipeline · Powered by Ollama
          </p>
        </div>

        {/* ── Card ── */}
        <div style={{
          background:   'var(--surface)',
          border:       '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding:      '32px',
          boxShadow:    'var(--shadow)',
        }}>
          <h2 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '24px', color: 'var(--text)' }}>
            Connect your inbox
          </h2>

          {/* Email */}
          <Field label="Email address" icon={<Mail size={14} />}>
            <input
              type="email"
              placeholder="you@gmail.com"
              value={email}
              onChange={e => setEmail(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleConnect()}
              style={inputStyle}
            />
          </Field>

          {/* App password */}
          <Field label="App password" icon={<Lock size={14} />} hint="Not your real password — generate one in your account security settings.">
            <input
              type="password"
              placeholder="xxxx xxxx xxxx xxxx"
              value={password}
              onChange={e => setPassword(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleConnect()}
              style={inputStyle}
            />
          </Field>

          {/* Error */}
          {error && (
            <div style={{
              display:      'flex',
              alignItems:   'center',
              gap:          '8px',
              padding:      '10px 14px',
              borderRadius: 'var(--radius-sm)',
              background:   '#ef444418',
              border:       '1px solid #ef444430',
              color:        '#ef4444',
              fontSize:     '13px',
              marginBottom: '16px',
            }}>
              <AlertCircle size={14} />
              {error}
            </div>
          )}

          {/* Button */}
          <button
            onClick={handleConnect}
            disabled={loading}
            style={{
              width:        '100%',
              padding:      '11px',
              borderRadius: 'var(--radius-sm)',
              border:       'none',
              background:   loading ? 'var(--surface-2)' : 'var(--accent)',
              color:        loading ? 'var(--text-dim)' : '#fff',
              fontSize:     '14px',
              fontWeight:   '600',
              cursor:       loading ? 'not-allowed' : 'pointer',
              transition:   'background 0.2s',
              fontFamily:   'var(--sans)',
            }}
          >
            {loading ? 'Connecting...' : 'Connect inbox →'}
          </button>
        </div>

        {/* ── Hint ── */}
        <p style={{ textAlign: 'center', fontSize: '12px', color: 'var(--text-dim)', marginTop: '20px' }}>
          Works with Gmail, Outlook, Yahoo, iCloud and more
        </p>

      </div>
    </div>
  )
}

function Field({ label, icon, hint, children }) {
  return (
    <div style={{ marginBottom: '16px' }}>
      <label style={{
        display:      'flex',
        alignItems:   'center',
        gap:          '6px',
        fontSize:     '12px',
        fontWeight:   '500',
        color:        'var(--text-muted)',
        marginBottom: '6px',
      }}>
        <span style={{ color: 'var(--text-dim)' }}>{icon}</span>
        {label}
      </label>
      {children}
      {hint && (
        <p style={{ fontSize: '11px', color: 'var(--text-dim)', marginTop: '4px' }}>
          {hint}
        </p>
      )}
    </div>
  )
}

const inputStyle = {
  width:        '100%',
  padding:      '10px 12px',
  borderRadius: 'var(--radius-sm)',
  border:       '1px solid var(--border)',
  background:   'var(--bg)',
  color:        'var(--text)',
  fontSize:     '14px',
  fontFamily:   'var(--sans)',
  outline:      'none',
  transition:   'border-color 0.2s',
}
