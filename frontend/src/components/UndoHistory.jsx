import { useState, useEffect, useCallback } from 'react'
import { C } from '../App'

function fmtTime(isoStr) {
  try {
    const d = new Date(isoStr)
    return d.toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }) +
           ' ' + d.toLocaleDateString([], { month:'short', day:'numeric' })
  } catch { return isoStr?.slice(0, 16) ?? '' }
}

function SizeDelta({ origSize, updSize }) {
  const delta = updSize - origSize
  const color = delta > 0 ? '#73c991' : delta < 0 ? '#f48771' : '#666'
  return (
    <span style={{ fontSize:10, color, fontFamily:'Consolas,monospace' }}>
      {delta > 0 ? '+' : ''}{delta} b
    </span>
  )
}

export default function UndoHistory({ workspace, onReverted, onClose }) {
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [reverting, setReverting] = useState(null)   // edit id being reverted

  const load = useCallback(() => {
    setLoading(true)
    fetch('/api/history')
      .then(r => r.json())
      .then(d => setHistory(d.history ?? []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  // Escape key
  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const revert = async (editId, filePath) => {
    setReverting(editId)
    try {
      const r = await fetch(`/api/undo/${editId}`, { method:'POST' })
      if (r.ok) {
        onReverted(filePath)   // tell App to reload this file from disk
        load()                 // refresh list
      }
    } catch {}
    setReverting(null)
  }

  const sourceLabel = s =>
    s === 'auto_fix' ? '⚡ auto-fix' :
    s === 'ai'       ? '🤖 AI chat'  :
    s === 'patch'    ? '🔧 patch'    : s

  return (
    <div style={{ position:'fixed', inset:0, zIndex:1000, background:'rgba(0,0,0,0.72)',
                  display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div style={{ background:'#252526', border:`1px solid ${C.borderLight}`,
                    borderRadius:6, width:660, maxWidth:'95vw', maxHeight:'80vh',
                    display:'flex', flexDirection:'column', overflow:'hidden' }}>

        {/* Header */}
        <div style={{ padding:'12px 16px', borderBottom:`1px solid ${C.border}`,
                      display:'flex', alignItems:'center', gap:10, flexShrink:0 }}>
          <span style={{ fontSize:13, fontWeight:500 }}>⏪ Edit History</span>
          <div style={{ flex:1 }} />
          <span style={{ fontSize:11, color:'#555' }}>
            {history.length} edit{history.length !== 1 ? 's' : ''} recorded
          </span>
          <button onClick={onClose} style={{ background:'none', border:'none',
            color:C.textMuted, cursor:'pointer', fontSize:18, lineHeight:1,
            padding:'0 4px' }}>×</button>
        </div>

        {/* List */}
        <div style={{ flex:1, overflow:'auto' }}>
          {loading && (
            <div style={{ padding:24, textAlign:'center', color:'#555', fontSize:12 }}>
              Loading…
            </div>
          )}
          {!loading && history.length === 0 && (
            <div style={{ padding:28, textAlign:'center', color:'#3a3a3a', fontSize:12,
                          lineHeight:1.7 }}>
              <div style={{ fontSize:24, marginBottom:8, opacity:0.3 }}>⏪</div>
              No AI edits recorded yet.
              <br />
              Apply a suggestion from the chat panel to start building history.
            </div>
          )}
          {history.map((edit, i) => (
            <div key={edit.id} style={{
              display:'flex', alignItems:'center', gap:10,
              padding:'9px 16px',
              borderBottom:`1px solid #2a2a2a`,
              opacity: edit.reverted ? 0.4 : 1,
              background: i % 2 === 0 ? 'transparent' : '#1e1e1e22',
            }}>
              {/* File path */}
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:12, color: edit.reverted ? '#666' : C.text,
                              overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                              textDecoration: edit.reverted ? 'line-through' : 'none' }}>
                  {edit.file_path}
                </div>
                <div style={{ fontSize:10, color:'#555', marginTop:2,
                              display:'flex', gap:8, alignItems:'center' }}>
                  <span>{fmtTime(edit.ts)}</span>
                  <span style={{ color:'#444' }}>·</span>
                  <span>{sourceLabel(edit.source)}</span>
                  {edit.description && (
                    <>
                      <span style={{ color:'#444' }}>·</span>
                      <span style={{ color:'#666', overflow:'hidden',
                                     textOverflow:'ellipsis', maxWidth:180 }}>
                        {edit.description}
                      </span>
                    </>
                  )}
                </div>
              </div>

              {/* Size delta */}
              <SizeDelta origSize={edit.orig_size} updSize={edit.upd_size} />

              {/* Status / revert */}
              {edit.reverted ? (
                <span style={{ fontSize:10, color:'#555', flexShrink:0 }}>reverted</span>
              ) : (
                <button
                  onClick={() => revert(edit.id, edit.file_path)}
                  disabled={reverting === edit.id}
                  title="Revert this edit"
                  style={{
                    background:'#2a2a2a', border:`1px solid #3a3a3a`,
                    color: reverting === edit.id ? '#555' : '#cccccc',
                    padding:'3px 10px', borderRadius:3, cursor:'pointer',
                    fontSize:11, fontFamily:'inherit', flexShrink:0,
                  }}
                >
                  {reverting === edit.id ? '…' : '↩ Revert'}
                </button>
              )}
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{ padding:'10px 16px', borderTop:`1px solid ${C.border}`,
                      display:'flex', justifyContent:'space-between',
                      alignItems:'center', flexShrink:0 }}>
          <span style={{ fontSize:10, color:'#555' }}>
            Reverts restore the file to its state before the AI edit.
          </span>
          <button onClick={onClose} style={{ background:C.accent, border:'none',
            color:'#fff', padding:'5px 14px', borderRadius:3, cursor:'pointer',
            fontSize:12, fontFamily:'inherit' }}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
