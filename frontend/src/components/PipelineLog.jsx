import React from 'react';
export default function PipelineLog({ logs }) {
  if (!logs.length) return null
  return (
    <div style={{
      background:   'var(--surface)',
      border:       '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding:      '14px 18px',
      fontFamily:   'var(--mono)',
      fontSize:     '12px',
      color:        'var(--text-dim)',
      lineHeight:   '1.8',
      maxHeight:    '120px',
      overflowY:    'auto',
    }}>
      {logs.map((log, i) => (
        <div key={i} style={{ color: i === logs.length - 1 ? 'var(--accent)' : 'var(--text-dim)' }}>
          <span style={{ color: 'var(--text-dim)', marginRight: '8px' }}>›</span>
          {log}
        </div>
      ))}
    </div>
  )
}
