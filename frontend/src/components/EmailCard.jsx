import React from 'react';
import { CategoryBadge, TrustBadge, LabelChip } from './StatusBadge'
import { Mail, User, Calendar, FileText, MessageSquare } from 'lucide-react'

export default function EmailCard({ msg, index }) {
  const {
    sender, subject, date, category,
    platform_label, topic_label,
    trust_level, trust_score,
    summary, draft, status,
  } = msg

  return (
    <div className="slide-in" style={{
      background:   'var(--surface)',
      border:       '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding:      '20px 24px',
      display:      'flex',
      flexDirection:'column',
      gap:          '14px',
      boxShadow:    'var(--shadow)',
    }}>

      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span style={{ color: 'var(--text-dim)', fontFamily: 'var(--mono)', fontSize: '11px' }}>
              #{String(index).padStart(2, '0')}
            </span>
            <CategoryBadge category={category} />
          </div>
          <h3 style={{
            fontSize: '15px', fontWeight: '600',
            color: 'var(--text)', whiteSpace: 'nowrap',
            overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {subject}
          </h3>
        </div>
        {trust_level && <TrustBadge level={trust_level} score={trust_score} />}
      </div>

      {/* ── Meta ── */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px' }}>
        <MetaRow icon={<User size={13} />} text={sender} mono />
        {date && <MetaRow icon={<Calendar size={13} />} text={date} />}
      </div>

      {/* ── Labels ── */}
      {(platform_label || topic_label) && (
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {platform_label && <LabelChip text={platform_label} />}
          {topic_label    && <LabelChip text={topic_label} />}
        </div>
      )}

      {/* ── Summary ── */}
      {summary && (
        <Section icon={<FileText size={13} />} label="Summary">
          <p style={{ color: 'var(--text-muted)', fontSize: '13px', lineHeight: '1.7', whiteSpace: 'pre-wrap' }}>
            {summary}
          </p>
        </Section>
      )}

      {/* ── Draft (personal/work emails) ── */}
      {draft && (
        <Section icon={<MessageSquare size={13} />} label="Draft Reply">
          <p style={{
            color: 'var(--text-muted)', fontSize: '13px',
            lineHeight: '1.7', whiteSpace: 'pre-wrap',
            borderLeft: '2px solid var(--accent)',
            paddingLeft: '12px',
          }}>
            {draft}
          </p>
        </Section>
      )}

      {/* ── Status ── */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: '10px' }}>
        <span style={{
          fontFamily: 'var(--mono)', fontSize: '11px',
          color: 'var(--text-dim)',
        }}>
          status → {status}
        </span>
      </div>

    </div>
  )
}

function MetaRow({ icon, text, mono }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
      <span style={{ color: 'var(--text-dim)' }}>{icon}</span>
      <span style={{
        fontSize: '12px', color: 'var(--text-muted)',
        fontFamily: mono ? 'var(--mono)' : 'var(--sans)',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        maxWidth: '320px',
      }}>
        {text}
      </span>
    </div>
  )
}

function Section({ icon, label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <span style={{ color: 'var(--text-dim)' }}>{icon}</span>
        <span style={{ fontSize: '11px', fontWeight: '600', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
          {label}
        </span>
      </div>
      {children}
    </div>
  )
}
