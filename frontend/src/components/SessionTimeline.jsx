import { useState, useEffect, useCallback } from 'react'
import { C } from '../App'

function fmtTime(iso) {
  try { return new Date(iso).toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }) }
  catch { return iso }
}

function FileRow({ file, onRollback, rolling }) {
  return (
    <div style={{
      display:'flex', alignItems:'center', gap:8,
      padding:'5px 14px 5px 28px', borderBottom:'1px solid #1e1e1e',
    }}>
      <span style={{ fontSize:10, color:'#444' }}>├</span>
      <code style={{
        fontSize:10, color:C.textMuted, flex:1,
        overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
        fontFamily:"'Cascadia Code','Fira Code',monospace",
      }}>{file.file_path}</code>
      <span style={{ fontSize:9, color:'#555', flexShrink:0 }}>
        <span style={{ color:'#73c991' }}>+{file.lines_added}</span>
        {' '}<span style={{ color:'#f48771' }}>−{file.lines_removed}</span>
      </span>
      {file.checkpoint_id && (
        <button
          onClick={() => onRollback(file)}
          disabled={rolling === file.file_path}
          title="Restore this file to before this change"
          style={{
            background:'none', border:'1px solid #2a2a2a', color:'#666',
            padding:'1px 7px', borderRadius:3, cursor:'pointer',
            fontSize:9, fontFamily:'inherit', flexShrink:0,
          }}
        >
          {rolling === file.file_path ? '…' : '↩'}
        </button>
      )}
    </div>
  )
}

function FeatureGroup({ feature, rolling, onRollbackFeature, onRollbackFile }) {
  const [open, setOpen] = useState(true)
  const fileCount = feature.files.length

  return (
    <div style={{ borderBottom:'1px solid #222' }}>
      <div
        onClick={() => setOpen(v => !v)}
        style={{ display:'flex', alignItems:'center', gap:8, padding:'9px 14px', cursor:'pointer' }}
      >
        <span style={{ fontSize:10, color:'#555' }}>{open ? '▾' : '▸'}</span>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{
            fontSize:12, color:C.text, fontWeight:500,
            overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
          }}>
            {feature.request || 'AI changes'}
          </div>
          <div style={{ fontSize:10, color:'#555', marginTop:1 }}>
            {fmtTime(feature.ts)} · {fileCount} file{fileCount !== 1 ? 's' : ''}
          </div>
        </div>
        <button
          onClick={e => { e.stopPropagation(); onRollbackFeature(feature.feature_id) }}
          disabled={rolling === feature.feature_id}
          style={{
            background:'#3a1a1a', border:'1px solid #6b2c2c', color:'#f48771',
            padding:'3px 9px', borderRadius:3, cursor:'pointer',
            fontSize:9, fontFamily:'inherit', flexShrink:0,
          }}
        >
          {rolling === feature.feature_id ? '…' : '↩ Rollback all'}
        </button>
      </div>
      {open && feature.files.map((f, i) => (
        <FileRow key={i} file={f} rolling={rolling}
          onRollback={onRollbackFile} />
      ))}
    </div>
  )
}

export default function SessionTimeline({ onClose, onFileRestored }) {
  const [features, setFeatures] = useState([])
  const [loading,  setLoading]  = useState(true)
  const [rolling,  setRolling]  = useState(null)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/api/session').then(r => r.json())
      .then(d => setFeatures(d.features ?? []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const rollbackFeature = async (featureId) => {
    setRolling(featureId)
    try {
      const r = await fetch('/api/session/rollback-feature', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ feature_id: featureId }),
      })
      const d = await r.json()
      if (d.ok) { onFileRestored?.(); load() }
    } catch {}
    setRolling(null)
  }

  const rollbackFile = async (file) => {
    if (!file.checkpoint_id) return
    setRolling(file.file_path)
    try {
      const r = await fetch('/api/checkpoints/restore', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ path: file.file_path, checkpoint_id: file.checkpoint_id }),
      })
      if (r.ok) { onFileRestored?.(); load() }
    } catch {}
    setRolling(null)
  }

  const totalFiles = features.reduce((n, f) => n + f.files.length, 0)

  return (
    <div style={{
      position:'fixed', inset:0, zIndex:1000, background:'rgba(0,0,0,0.72)',
      display:'flex', alignItems:'center', justifyContent:'center',
    }}>
      <div style={{
        background:'#1e1e1e', border:`1px solid ${C.borderLight}`,
        borderRadius:6, width:560, maxWidth:'95vw', maxHeight:'80vh',
        display:'flex', flexDirection:'column', overflow:'hidden',
      }}>
        <div style={{
          padding:'12px 16px', borderBottom:`1px solid ${C.border}`,
          display:'flex', alignItems:'center', gap:10, flexShrink:0,
        }}>
          <span style={{ fontSize:13, fontWeight:500 }}>📅 Today's changes</span>
          {!loading && (
            <span style={{ fontSize:11, color:'#666' }}>
              {features.length} request{features.length !== 1 ? 's' : ''} · {totalFiles} file{totalFiles !== 1 ? 's' : ''}
            </span>
          )}
          <div style={{ flex:1 }} />
          <button onClick={load} style={{ background:'none', border:'none', color:C.textMuted, cursor:'pointer', fontSize:14 }}>↻</button>
          <button onClick={onClose} style={{ background:'none', border:'none', color:C.textMuted, cursor:'pointer', fontSize:18, lineHeight:1 }}>×</button>
        </div>

        <div style={{ flex:1, overflow:'auto' }}>
          {loading && (
            <div style={{ padding:28, textAlign:'center', color:'#555', fontSize:12 }}>Loading…</div>
          )}
          {!loading && features.length === 0 && (
            <div style={{ padding:36, textAlign:'center', color:'#3a3a3a', fontSize:12, lineHeight:1.8 }}>
              <div style={{ fontSize:24, marginBottom:8, opacity:0.3 }}>📅</div>
              No AI changes recorded today.<br/>
              Applied suggestions will appear here grouped by request.
            </div>
          )}
          {features.map(f => (
            <FeatureGroup key={f.feature_id} feature={f} rolling={rolling}
              onRollbackFeature={rollbackFeature}
              onRollbackFile={rollbackFile} />
          ))}
        </div>

        <div style={{ padding:'9px 16px', borderTop:`1px solid ${C.border}`, flexShrink:0 }}>
          <span style={{ fontSize:10, color:'#555' }}>
            ↩ restores a single file. "Rollback all" restores every file touched by that request.
          </span>
        </div>
      </div>
    </div>
  )
}
