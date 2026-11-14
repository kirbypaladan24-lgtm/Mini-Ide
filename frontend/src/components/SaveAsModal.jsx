import { useState, useEffect, useRef } from 'react'
import { C } from '../App'

export default function SaveAsModal({ suggestedPath, code, lang, onCreate, onClose }) {
  const [path, setPath]       = useState(suggestedPath)
  const [error, setError]     = useState('')
  const [creating, setCreating] = useState(false)
  const inputRef = useRef(null)

  useEffect(() => { inputRef.current?.focus(); inputRef.current?.select() }, [])

  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const submit = async () => {
    const clean = path.trim()
    if (!clean) { setError('Enter a file path.'); return }
    setCreating(true); setError('')
    try {
      await onCreate(clean, code)
      onClose()
    } catch (e) {
      setError(String(e?.message || e))
      setCreating(false)
    }
  }

  const isTestFile = /test_|\.test\.|__tests__/.test(path)

  return (
    <div style={{ position:'fixed', inset:0, zIndex:1100, background:'rgba(0,0,0,0.65)',
                  display:'flex', alignItems:'center', justifyContent:'center' }}
         onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background:'#252526', border:`1px solid ${C.borderLight}`, borderRadius:6,
        padding:20, width:460, maxWidth:'92vw',
      }}>
        <div style={{ fontSize:13, fontWeight:500, marginBottom:4 }}>💾 Save as new file</div>
        <div style={{ fontSize:11, color:'#666', marginBottom:12 }}>
          {lang ? `${lang} · ` : ''}{code.split('\n').length} lines
        </div>

        <input
          ref={inputRef}
          value={path}
          onChange={e => setPath(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !creating && submit()}
          placeholder="path/to/file.py"
          style={{
            width:'100%', background:'#3c3c3c', border:'1px solid #555',
            color:C.text, padding:'8px 10px', borderRadius:3,
            fontSize:13, outline:'none', fontFamily:'inherit',
          }}
        />

        {isTestFile && (
          <div style={{ fontSize:11, color:'#73c991', marginTop:8 }}>
            🧪 Looks like a test file — it will run automatically after creation.
          </div>
        )}
        {error && (
          <div style={{ fontSize:12, color:C.errorText, marginTop:8 }}>{error}</div>
        )}

        <div style={{ display:'flex', justifyContent:'flex-end', gap:8, marginTop:16 }}>
          <button onClick={onClose} style={{
            background:'transparent', border:'1px solid #555', color:C.text,
            padding:'6px 14px', borderRadius:3, cursor:'pointer',
            fontSize:12, fontFamily:'inherit',
          }}>Cancel</button>
          <button onClick={submit} disabled={creating} style={{
            background:C.accent, border:'none', color:'#fff',
            padding:'6px 16px', borderRadius:3,
            cursor: creating ? 'default' : 'pointer',
            fontSize:12, fontFamily:'inherit', opacity: creating ? 0.6 : 1,
          }}>
            {creating ? 'Creating…' : 'Create File'}
          </button>
        </div>
      </div>
    </div>
  )
}
