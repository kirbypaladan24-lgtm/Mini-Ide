import { useState, useEffect, useCallback } from 'react'
import { C } from '../App'

function fmtTime(iso) {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour:'2-digit', minute:'2-digit', second:'2-digit' }) +
           ' · ' + d.toLocaleDateString([], { month:'short', day:'numeric' })
  } catch { return iso }
}

export default function CheckpointBrowser({ activeFile, onRestored, onClose }) {
  const [checkpoints, setCheckpoints] = useState([])
  const [loading,     setLoading]     = useState(true)
  const [restoring,   setRestoring]   = useState(null)

  const load = useCallback(() => {
    if (!activeFile) { setLoading(false); return }
    setLoading(true)
    fetch('/api/checkpoints?path=' + encodeURIComponent(activeFile.path))
      .then(r => r.json())
      .then(d => setCheckpoints(d.checkpoints ?? []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [activeFile])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const restore = async (id) => {
    setRestoring(id)
    try {
      const r = await fetch('/api/checkpoints/restore', {
        method: 'POST', headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({ path: activeFile.path, checkpoint_id: id }),
      })
      if (r.ok) {
        const d = await r.json()
        onRestored(activeFile.path, d.content)
        load()
      }
    } catch {}
    setRestoring(null)
  }

  return (
    <div style={{ position:'fixed', inset:0, zIndex:1000, background:'rgba(0,0,0,0.72)',
                  display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div style={{ background:'#252526', border:`1px solid ${C.borderLight}`,
                    borderRadius:6, width:540, maxWidth:'94vw', maxHeight:'78vh',
                    display:'flex', flexDirection:'column', overflow:'hidden' }}>

        <div style={{ padding:'12px 16px', borderBottom:`1px solid ${C.border}`,
                      display:'flex', alignItems:'center', gap:10, flexShrink:0 }}>
          <span style={{ fontSize:13, fontWeight:500 }}>🕐 Checkpoints</span>
          {activeFile && (
            <code style={{ background:'#2d2d2d', padding:'1px 6px', borderRadius:3, fontSize:11 }}>
              {activeFile.path.split('/').pop()}
            </code>
          )}
          <div style={{ flex:1 }} />
          <button onClick={onClose} style={{ background:'none', border:'none',
            color:C.textMuted, cursor:'pointer', fontSize:18, lineHeight:1 }}>×</button>
        </div>

        <div style={{ flex:1, overflow:'auto' }}>
          {!activeFile && (
            <div style={{ padding:28, textAlign:'center', color:'#555', fontSize:12 }}>
              Open a file to see its checkpoint timeline.
            </div>
          )}
          {activeFile && loading && (
            <div style={{ padding:28, textAlign:'center', color:'#555', fontSize:12 }}>Loading…</div>
          )}
          {activeFile && !loading && checkpoints.length === 0 && (
            <div style={{ padding:28, textAlign:'center', color:'#3a3a3a', fontSize:12, lineHeight:1.7 }}>
              <div style={{ fontSize:22, marginBottom:8, opacity:0.3 }}>🕐</div>
              No checkpoints yet for this file.<br/>
              Every AI edit automatically creates one.
            </div>
          )}
          {checkpoints.map(cp => (
            <div key={cp.id} style={{
              display:'flex', alignItems:'center', gap:10, padding:'9px 16px',
              borderBottom:'1px solid #2a2a2a',
            }}>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:12, color:C.text }}>{fmtTime(cp.ts)}</div>
                <div style={{ fontSize:10, color:'#555', marginTop:2 }}>
                  {cp.label || 'snapshot'} · {cp.size} bytes
                </div>
              </div>
              <button
                onClick={() => restore(cp.id)}
                disabled={restoring === cp.id}
                style={{
                  background:'#2a2a2a', border:'1px solid #3a3a3a',
                  color: restoring===cp.id ? '#555' : '#cccccc',
                  padding:'3px 10px', borderRadius:3, cursor:'pointer',
                  fontSize:11, fontFamily:'inherit', flexShrink:0,
                }}
              >
                {restoring === cp.id ? '…' : '↩ Restore'}
              </button>
            </div>
          ))}
        </div>

        <div style={{ padding:'9px 16px', borderTop:`1px solid ${C.border}`, flexShrink:0 }}>
          <span style={{ fontSize:10, color:'#555' }}>
            Checkpoints are full file snapshots, separate from the AI undo stack.
          </span>
        </div>
      </div>
    </div>
  )
}
