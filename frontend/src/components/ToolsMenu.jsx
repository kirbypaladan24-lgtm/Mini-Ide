import { useState, useEffect, useRef } from 'react'
import { C } from '../App'

/**
 * Replaces a row of 8 individual titlebar buttons with one entry point.
 * Grouped by function so the menu reads as a coherent toolset rather
 * than a flat list: history/undo tools, observability tools, knowledge tools.
 */
export default function ToolsMenu({ items }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const onKey   = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const groups = items.reduce((acc, item) => {
    (acc[item.group] ??= []).push(item)
    return acc
  }, {})

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          background: open ? '#3a3a3a' : 'transparent',
          border: '1px solid #555', color: C.text,
          padding: '5px 12px', borderRadius: 3, cursor: 'pointer',
          fontSize: 12, fontFamily: 'inherit', display: 'flex',
          alignItems: 'center', gap: 5,
        }}
      >
        <span>⋯</span> Tools
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: '110%', right: 0, zIndex: 200,
          background: C.bgTab, border: `1px solid ${C.borderLight}`,
          borderRadius: 6, minWidth: 200, overflow: 'hidden',
          boxShadow: '0 8px 24px rgba(0,0,0,0.45)',
          padding: '6px 0',
        }}>
          {Object.entries(groups).map(([group, groupItems], gi) => (
            <div key={group}>
              {gi > 0 && <div style={{ height: 1, background: C.border, margin: '6px 0' }} />}
              <div style={{
                fontSize: 9, fontWeight: 600, letterSpacing: 0.6, color: '#555',
                padding: '2px 12px', textTransform: 'uppercase',
              }}>
                {group}
              </div>
              {groupItems.map(item => (
                <button
                  key={item.label}
                  onClick={() => { item.onClick(); setOpen(false) }}
                  style={{
                    width: '100%', display: 'flex', alignItems: 'center', gap: 8,
                    padding: '7px 12px', background: 'none', border: 'none',
                    color: C.text, cursor: 'pointer', fontSize: 12,
                    fontFamily: 'inherit', textAlign: 'left',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = C.bgHover}
                  onMouseLeave={e => e.currentTarget.style.background = 'none'}
                >
                  <span style={{ width: 16, textAlign: 'center' }}>{item.icon}</span>
                  {item.label}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
