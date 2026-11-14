import { useState, useEffect, useCallback } from 'react'
import { C } from '../App'

const CAT_COLOR = {
  architecture: '#569cd6', convention: '#c586c0', decision: '#73c991',
  preference: '#e2c08d', warning: '#f48771',
}

export default function ProjectMemoryPanel({ onClose }) {
  const [memories, setMemories] = useState([])
  const [loading,  setLoading]  = useState(true)
  const [newText,  setNewText]  = useState('')
  const [category, setCategory] = useState('decision')

  const load = useCallback(() => {
    setLoading(true)
    fetch('/api/memory').then(r => r.json())
      .then(d => setMemories(d.memories ?? []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const add = async () => {
    if (!newText.trim()) return
    await fetch('/api/memory', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ text: newText.trim(), category }),
    })
    setNewText('')
    load()
  }

  const remove = async (id) => {
    await fetch(`/api/memory/${id}`, { method:'DELETE' })
    load()
  }

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
          <span style={{ fontSize:13, fontWeight:500 }}>🧠 Project Memory</span>
          <span style={{ fontSize:11, color:'#666' }}>
            Persists across sessions — always included in AI context
          </span>
          <div style={{ flex:1 }} />
          <button onClick={onClose} style={{ background:'none', border:'none', color:C.textMuted, cursor:'pointer', fontSize:18, lineHeight:1 }}>×</button>
        </div>

        <div style={{ flex:1, overflow:'auto' }}>
          {loading && <div style={{ padding:28, textAlign:'center', color:'#555', fontSize:12 }}>Loading…</div>}
          {!loading && memories.length === 0 && (
            <div style={{ padding:36, textAlign:'center', color:'#3a3a3a', fontSize:12, lineHeight:1.8 }}>
              <div style={{ fontSize:22, marginBottom:8, opacity:0.3 }}>🧠</div>
              No memories yet.<br/>
              Say "remember that we always use X" in chat, or add one below.
            </div>
          )}
          {memories.map(m => {
            const color = CAT_COLOR[m.category] || '#888'
            return (
              <div key={m.id} style={{
                padding:'9px 14px', borderBottom:'1px solid #2a2a2a',
                display:'flex', alignItems:'flex-start', gap:10,
              }}>
                <span style={{
                  fontSize:9, fontWeight:600, color, padding:'1px 6px', borderRadius:6,
                  background:`${color}18`, border:`1px solid ${color}44`, flexShrink:0, marginTop:1,
                }}>{m.category}</span>
                <span style={{ fontSize:12, color:C.text, flex:1, lineHeight:1.5 }}>{m.text}</span>
                <button onClick={() => remove(m.id)} style={{
                  background:'none', border:'none', color:'#555', cursor:'pointer',
                  fontSize:14, flexShrink:0, lineHeight:1,
                }}>×</button>
              </div>
            )
          })}
        </div>

        <div style={{ padding:'10px 14px', borderTop:`1px solid ${C.border}`, flexShrink:0 }}>
          <div style={{ display:'flex', gap:6 }}>
            <select value={category} onChange={e => setCategory(e.target.value)} style={{
              background:'#2d2d2d', border:'1px solid #444', color:C.text,
              padding:'6px 8px', borderRadius:3, fontSize:11, fontFamily:'inherit', outline:'none',
            }}>
              <option value="decision">decision</option>
              <option value="architecture">architecture</option>
              <option value="convention">convention</option>
              <option value="preference">preference</option>
              <option value="warning">warning</option>
            </select>
            <input
              value={newText} onChange={e => setNewText(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && add()}
              placeholder="e.g. This project uses SQLite, not PostgreSQL"
              style={{
                flex:1, background:'#2d2d2d', border:'1px solid #444', color:C.text,
                padding:'6px 10px', borderRadius:3, fontSize:11, fontFamily:'inherit', outline:'none',
              }}
            />
            <button onClick={add} disabled={!newText.trim()} style={{
              background:C.accent, border:'none', color:'#fff', padding:'6px 14px',
              borderRadius:3, cursor:'pointer', fontSize:11, fontFamily:'inherit',
              opacity: newText.trim() ? 1 : 0.5,
            }}>Add</button>
          </div>
        </div>
      </div>
    </div>
  )
}
