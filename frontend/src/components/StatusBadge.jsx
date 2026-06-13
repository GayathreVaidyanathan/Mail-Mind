import React from 'react';
const CATEGORY_CONFIG = {
  personal_work:        { label: 'Personal/Work',        color: '#a78bfa' },
  academic_info:        { label: 'Academic/Info',         color: '#34d399' },
  account_notification: { label: 'Account Notification',  color: '#0ea5e9' },
  promotional:          { label: 'Promotional',           color: '#f59e0b' },
  spam:                 { label: 'Spam',                  color: '#ef4444' },
}

const TRUST_CONFIG = {
  trusted:    { color: '#22c55e', bg: '#22c55e18' },
  suspicious: { color: '#f59e0b', bg: '#f59e0b18' },
  dangerous:  { color: '#ef4444', bg: '#ef444418' },
}

export function CategoryBadge({ category }) {
  const cfg = CATEGORY_CONFIG[category] || { label: category, color: '#94a3b8' }
  return (
    <span style={{
      display:       'inline-flex',
      alignItems:    'center',
      padding:       '2px 10px',
      borderRadius:  '999px',
      fontSize:      '12px',
      fontWeight:    '500',
      color:         cfg.color,
      background:    cfg.color + '18',
      border:        `1px solid ${cfg.color}30`,
    }}>
      {cfg.label}
    </span>
  )
}

export function TrustBadge({ level, score }) {
  const cfg = TRUST_CONFIG[level] || { color: '#94a3b8', bg: '#94a3b818' }
  return (
    <span style={{
      display:       'inline-flex',
      alignItems:    'center',
      gap:           '4px',
      padding:       '2px 10px',
      borderRadius:  '999px',
      fontSize:      '12px',
      fontWeight:    '500',
      color:         cfg.color,
      background:    cfg.bg,
      border:        `1px solid ${cfg.color}30`,
      fontFamily:    'var(--mono)',
    }}>
      {level} · {score}
    </span>
  )
}

export function LabelChip({ text }) {
  if (!text) return null
  return (
    <span style={{
      display:      'inline-flex',
      alignItems:   'center',
      padding:      '2px 8px',
      borderRadius: 'var(--radius-sm)',
      fontSize:     '11px',
      fontWeight:   '500',
      color:        'var(--text-muted)',
      background:   'var(--surface-2)',
      border:       '1px solid var(--border)',
    }}>
      🏷 {text}
    </span>
  )
}
