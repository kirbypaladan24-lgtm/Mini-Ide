import { useState, useEffect, useCallback } from 'react'
import { C } from '../App'

const MARKER_COLOR = { FIXME:'#f48771', HACK:'#e2c08d', XXX:'#e2c08d', TODO:'#569cd6' }

export default function TodoResolver({ onClose, onResolve }) {
  const [todos,   setTodos]   = useState([])
  const [summary, setSummary] = useState('')
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/api/todos').then(r => r.json())
      .then(d => { setTodos(d.todos ?? []); setSummary(d.summary || '') })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div style={{
      position:'fixed', inset:0, zIndex:1000, background:'rgba(0,0,0,0.72)',
      display:'flex', alignItems:'center', justifyContent:'center',
    }}>
      <div style={{
        background:'#1e1e1e', border:`1px solid ${C.borderLight}`, borderRadius:6,
        width:560, maxWidth:'95vw', maxHeight:'78vh',
        display:'flex', flexDirection:'column', overflow:'hidden',
      }}>
        <div style={{
          padding:'12px 16px', borderBottom:`1px solid ${C.border}`,
          display:'flex', alignItems:'center', gap:10, flexShrink:0,
        }}>
          <span style={{ fontSize:13, fontWeight:500 }}>✓ TODOs</span>
          {!loading && <span style={{ fontSize:11, color:'#666' }}>{summary}</span>}
          <div style={{ flex:1 }} />
          <button onClick={load} style={{ background:'none', border:'none', color:C.textMuted, cursor:'pointer', fontSize:14 }}>↻</button>
          <button onClick={onClose} style={{ background:'none', border:'none', color:C.textMuted, cursor:'pointer', fontSize:18, lineHeight:1 }}>×</button>
        </div>

        <div style={{ flex:1, overflow:'auto' }}>
          {loading && <div style={{ padding:28, textAlign:'center', color:'#555', fontSize:12 }}>Scanning…</div>}
          {!loading && todos.length === 0 && (
            <div style={{ padding:36, textAlign:'center', color:'#3a3a3a', fontSize:12, lineHeight:1.8 }}>
              <div style={{ fontSize:22, marginBottom:8, opacity:0.3 }}>✓</div>
              No TODOs found in the workspace.
            </div>
          )}
          {todos.map((t, i) => {
            const color = MARKER_COLOR[t.marker] || '#888'
            return (
              <div key={i} style={{ padding:'9px 14px', borderBottom:'1px solid #2a2a2a' }}>
                <div style={{ display:'flex', alignItems:'baseline', gap:8 }}>
                  <span style={{
                    fontSize:9, fontWeight:600, color, padding:'1px 6px',
                    borderRadius:6, background:`${color}18`, border:`1px solid ${color}44`,
                    flexShrink:0,
                  }}>{t.marker}</span>
                  <span style={{ fontSize:12, color:C.text, flex:1 }}>{t.text}</span>
                </div>
                <div style={{ fontSize:10, color:'#555', marginTop:4, marginLeft:2 }}>
                  {t.file_path}:{t.line}
                </div>
                <button
                  onClick={() => onResolve(t)}
                  style={{
                    marginTop:6, background:'#0e639c18', border:'1px solid #0e639c44',
                    color:'#4fc1ff', padding:'3px 10px', borderRadius:3,
                    cursor:'pointer', fontSize:10, fontFamily:'inherit',
                  }}
                >
                  Resolve with AI →
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
