import { useState } from 'react'
import { C } from '../App'
import { AGENT_META } from './WorkingState'

/**
 * Shows one agent's completed turn: a one-line summary always visible,
 * and a chevron button that expands to reveal the full reasoning/content -
 * "what the planner actually decided", "what the critic actually said",
 * "what the coder actually changed and why", etc.
 */
export default function AgentTurnCard({ agent, file, summary, content }) {
  const [open, setOpen] = useState(false)
  const meta = AGENT_META[agent] || { icon: '🔄', color: C.accent, label: agent }
  const hasContent = content && content.trim().length > 0

  return (
    <div style={{
      alignSelf: 'flex-start', maxWidth: '97%', width: '100%',
      borderRadius: 6, overflow: 'hidden',
      border: `1px solid ${meta.color}2a`,
      background: `${meta.color}08`,
    }}>
      <button
        onClick={() => hasContent && setOpen(v => !v)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', gap: 8,
          padding: '7px 10px', background: 'none', border: 'none',
          cursor: hasContent ? 'pointer' : 'default', textAlign: 'left',
          fontFamily: 'inherit',
        }}
      >
        <span style={{ fontSize: 12, flexShrink: 0 }}>{meta.icon}</span>
        <span style={{ fontSize: 11, fontWeight: 600, color: meta.color, flexShrink: 0 }}>
          {meta.label}
        </span>
        {file && (
          <code style={{
            fontSize: 10, color: C.textMuted, flexShrink: 0,
            fontFamily: "'Cascadia Code','Fira Code',monospace",
          }}>
            {file.split('/').pop()}
          </code>
        )}
        <span style={{
          fontSize: 11, color: C.textMuted, flex: 1, overflow: 'hidden',
          textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {summary}
        </span>
        {hasContent && (
          <span style={{
            fontSize: 12, color: meta.color, flexShrink: 0,
            transform: open ? 'rotate(90deg)' : 'none',
            transition: 'transform 0.15s ease',
          }}>
            ›
          </span>
        )}
      </button>

      {open && hasContent && (
        <div style={{
          padding: '2px 12px 10px 32px', fontSize: 11.5, color: C.text,
          lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
          borderTop: `1px solid ${meta.color}1a`, marginTop: 2, paddingTop: 8,
        }}>
          {content}
        </div>
      )}
    </div>
  )
}
