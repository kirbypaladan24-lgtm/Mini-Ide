import { C } from '../App'

// NOTE: these two colors are intentionally hardcoded literals, not C.accent /
// C.success references. AGENT_META is built at module load time, and since
// this file is reached via App.jsx -> ChatPanel.jsx -> WorkingState.jsx while
// App.jsx is still mid-initialization, reading C's exported values here (before
// App.jsx finishes evaluating its own `export const C = {...}` line) throws
// "Cannot access 'C' before initialization". Reading C.* inside a component's
// render body (further below) is safe since that only runs after the full
// module graph has loaded.
const AGENT_META = {
  planner:     { icon: '🧭', color: '#22d3d8',  label: 'Planner' },
  coder:       { icon: '✏️', color: '#4fc1ff',  label: 'Coder' },
  critic:      { icon: '🔍', color: '#c586c0',  label: 'Critic' },
  security:    { icon: '🛡',  color: '#f48771',  label: 'Security' },
  performance: { icon: '⚡', color: '#e2c08d',  label: 'Performance' },
  web:         { icon: '🌐', color: '#4ec9b0',  label: 'Web research' },
  verify:      { icon: '✓',  color: '#73c991',  label: 'Verifier' },
}

/**
 * A persistent, live status bar shown while any agent is actively working.
 * Distinct from AgentTurnCard (which shows completed, expandable results) —
 * this is specifically the "something is happening right now" signal.
 */
export default function WorkingState({ agent, message }) {
  if (!message) return null
  const meta = AGENT_META[agent] || { icon: '🔄', color: C.accent, label: 'Working' }

  return (
    <div style={{
      alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 8,
      padding: '6px 12px', borderRadius: 6,
      background: `${meta.color}12`,
      border: `1px solid ${meta.color}35`,
    }}>
      <style>{`
        @keyframes signal-pulse {
          0%   { box-shadow: 0 0 0 0 ${meta.color}66; }
          70%  { box-shadow: 0 0 0 6px ${meta.color}00; }
          100% { box-shadow: 0 0 0 0 ${meta.color}00; }
        }
      `}</style>
      <span style={{
        width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
        background: meta.color,
        animation: 'signal-pulse 1.6s infinite',
      }} />
      <span style={{ fontSize: 11, color: meta.color, fontWeight: 600, flexShrink: 0 }}>
        {meta.icon} {meta.label}
      </span>
      <span style={{ fontSize: 11, color: C.textMuted }}>{message}</span>
    </div>
  )
}

export { AGENT_META }
