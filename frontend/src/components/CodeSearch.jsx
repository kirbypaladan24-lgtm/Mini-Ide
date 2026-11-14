import { useState, useEffect, useRef, useCallback } from 'react'
import { C } from '../App'

const TYPE_ICON = { function: 'ƒ', class: '◻', file: '📄' }

export default function CodeSearch({ onClose, onOpenFile }) {
  const [query,   setQuery]   = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const inputRef = useRef(null)
  const debounceRef = useRef(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const search = useCallback((q) => {
    if (!q.trim()) { setResults([]); return }
    setLoading(true)
    fetch('/api/search?q=' + encodeURIComponent(q) + '&k=10')
      .then(r => r.json())
      .then(d => setResults(d.results ?? []))
      .catch(() => setResults([]))
      .finally(() => setLoading(false))
  }, [])

  const onChange = (e) => {
    const v = e.target.value
    setQuery(v)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => search(v), 300)
  }

  return (
    <div style={{
      position:'fixed', inset:0, zIndex:1100, background:'rgba(0,0,0,0.55)',
      display:'flex', alignItems:'flex-start', justifyContent:'center', paddingTop:'8vh',
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background:'#252526', border:`1px solid ${C.borderLight}`, borderRadius:6,
        width:560, maxWidth:'94vw', maxHeight:'70vh',
        display:'flex', flexDirection:'column', overflow:'hidden',
        boxShadow:'0 8px 32px rgba(0,0,0,0.5)',
      }}>
        <div style={{
          padding:'10px 12px', borderBottom:`1px solid ${C.border}`,
          display:'flex', alignItems:'center', gap:8,
        }}>
          <span style={{ fontSize:14 }}>🔍</span>
          <input
            ref={inputRef} value={query} onChange={onChange}
            placeholder="Search codebase semantically… (e.g. 'rate limiting', 'database connection')"
            style={{
              flex:1, background:'transparent', border:'none', color:C.text,
              fontSize:13, outline:'none', fontFamily:'inherit',
            }}
          />
          {loading && <span style={{ fontSize:11, color:'#555' }}>…</span>}
          <span style={{ fontSize:10, color:'#555' }}>Esc</span>
        </div>

        <div style={{ flex:1, overflow:'auto' }}>
          {!query && (
            <div style={{ padding:'24px 16px', textAlign:'center', color:'#3a3a3a', fontSize:12 }}>
              Search by meaning, not just text — try "error handling" or "user auth"
            </div>
          )}
          {query && !loading && results.length === 0 && (
            <div style={{ padding:'24px 16px', textAlign:'center', color:'#555', fontSize:12 }}>
              No matches found for "{query}"
            </div>
          )}
          {results.map((r, i) => (
            <div
              key={i}
              onClick={() => { onOpenFile(r.path, r.line); onClose() }}
              style={{
                padding:'9px 14px', borderBottom:'1px solid #2a2a2a',
                cursor:'pointer', display:'flex', alignItems:'center', gap:10,
              }}
              onMouseEnter={e => e.currentTarget.style.background = '#2a2a2a'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
            >
              <span style={{ fontSize:13, color:'#c586c0', flexShrink:0, width:16, textAlign:'center' }}>
                {TYPE_ICON[r.type] || '◦'}
              </span>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:12, color:C.text }}>
                  {r.name || r.path.split('/').pop()}
                </div>
                <div style={{ fontSize:10, color:'#666', marginTop:1 }}>
                  {r.path}{r.line ? `:${r.line}` : ''}
                </div>
              </div>
              <span style={{
                fontSize:9, color:'#555', flexShrink:0,
                padding:'1px 6px', borderRadius:8, background:'#2a2a2a',
              }}>
                {Math.round((r.score || 0) * 100)}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
