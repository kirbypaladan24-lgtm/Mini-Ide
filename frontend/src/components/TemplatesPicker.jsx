import { useState, useEffect, useRef } from 'react'
import { C } from '../App'

const TEMPLATES = [
  { icon:'✨', label:'Build a UI component',     prompt:'Build a React component: ' },
  { icon:'🖼️', label:'Screenshot → code',        prompt:'Replicate this UI in React. Build every element visible in the attached screenshot.' },
  { icon:'🎨', label:'Style like Linear',         prompt:'Make this UI feel like Linear — dark, minimal, compact, with purple accents.' },
  { icon:'⬛', label:'Style like Vercel',         prompt:'Make this UI feel like Vercel — ultra-minimal, black and white, generous whitespace.' },
  { icon:'📝', label:'Style like Notion',         prompt:'Make this UI feel like Notion — clean, document-first, subtle borders, comfortable spacing.' },
  { icon:'📝', label:'Add docstrings',            prompt:'Add comprehensive docstrings to all functions and classes in this file.' },
  { icon:'⚡', label:'Convert to async',          prompt:'Convert all blocking functions to async/await where appropriate.' },
  { icon:'🔷', label:'Add type hints',            prompt:'Add complete type hints to all function parameters and return values.' },
  { icon:'🧪', label:'Write unit tests',          prompt:'Write comprehensive unit tests for all functions in this file using pytest.' },
  { icon:'❓', label:'Explain this file',         prompt:'Explain what this file does, how it works, and what each major function is responsible for.' },
  { icon:'🔒', label:'Find security issues',      prompt:'Analyze this file for security vulnerabilities, injection risks, and unsafe patterns. Suggest fixes.' },
  { icon:'🚀', label:'Optimize performance',      prompt:'Identify and fix performance bottlenecks — O(n²) loops, unnecessary copies, redundant calls.' },
  { icon:'🔧', label:'Split long functions',      prompt:'Refactor by breaking up any functions longer than 30 lines into smaller, focused functions.' },
  { icon:'🛡️', label:'Add error handling',        prompt:'Add comprehensive try/except error handling and input validation throughout this file.' },
  { icon:'📦', label:'Convert to dataclass',      prompt:'Replace plain dicts and tuples with proper dataclasses or Pydantic models where appropriate.' },
  { icon:'🌐', label:'Add logging',               prompt:'Add structured logging statements (using the logging module) throughout this file.' },
  { icon:'♻️', label:'Remove dead code',           prompt:'Identify and remove any unused variables, functions, and imports from this file.' },
]

export default function TemplatesPicker({ onSelect, onClose }) {
  const [query, setQuery]       = useState('')
  const [focused, setFocused]   = useState(0)
  const inputRef                = useRef(null)

  const filtered = TEMPLATES.filter(t =>
    !query || t.label.toLowerCase().includes(query.toLowerCase())
  )

  // Keyboard navigation
  useEffect(() => {
    const h = (e) => {
      if (e.key === 'Escape')    { onClose(); return }
      if (e.key === 'ArrowDown') { setFocused(f => Math.min(f+1, filtered.length-1)); e.preventDefault() }
      if (e.key === 'ArrowUp')   { setFocused(f => Math.max(f-1, 0)); e.preventDefault() }
      if (e.key === 'Enter')     { if (filtered[focused]) onSelect(filtered[focused].prompt); onClose() }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [filtered, focused, onClose, onSelect])

  // Focus search input on open
  useEffect(() => { inputRef.current?.focus() }, [])

  // Reset focused index when filter changes
  useEffect(() => { setFocused(0) }, [query])

  const pick = (t) => { onSelect(t.prompt); onClose() }

  return (
    <div style={{
      position:'fixed', inset:0, zIndex:1100,
      background:'rgba(0,0,0,0.55)',
      display:'flex', alignItems:'flex-start', justifyContent:'center',
      paddingTop:'10vh',
    }}
    onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background:'#252526', border:`1px solid ${C.borderLight}`,
          borderRadius:6, width:480, maxWidth:'94vw',
          boxShadow:'0 8px 32px rgba(0,0,0,0.5)',
          display:'flex', flexDirection:'column', overflow:'hidden',
        }}
      >
        {/* Search bar */}
        <div style={{
          padding:'10px 12px', borderBottom:`1px solid ${C.border}`,
          display:'flex', alignItems:'center', gap:8,
        }}>
          <span style={{ fontSize:14, opacity:0.5 }}>⌘</span>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search templates…"
            style={{
              flex:1, background:'transparent', border:'none',
              color:C.text, fontSize:13, outline:'none', fontFamily:'inherit',
            }}
          />
          <span style={{ fontSize:10, color:'#555', flexShrink:0 }}>Esc to close</span>
        </div>

        {/* Template list */}
        <div style={{ maxHeight:340, overflow:'auto' }}>
          {filtered.length === 0 && (
            <div style={{ padding:'20px 14px', color:'#555', fontSize:12, textAlign:'center' }}>
              No templates match "{query}"
            </div>
          )}
          {filtered.map((t, i) => (
            <div
              key={t.label}
              onClick={() => pick(t)}
              onMouseEnter={() => setFocused(i)}
              style={{
                display:'flex', alignItems:'center', gap:10,
                padding:'9px 14px', cursor:'pointer',
                background: i === focused ? '#094771' : 'transparent',
                transition:'background 0.08s',
              }}
            >
              <span style={{ fontSize:15, flexShrink:0 }}>{t.icon}</span>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:12, color: i===focused ? '#fff' : C.text, fontWeight:500 }}>
                  {t.label}
                </div>
                <div style={{ fontSize:10, color: i===focused ? '#99c4e8' : C.textMuted,
                              marginTop:2, overflow:'hidden', textOverflow:'ellipsis',
                              whiteSpace:'nowrap', maxWidth:360 }}>
                  {t.prompt}
                </div>
              </div>
              {i === focused && (
                <span style={{ fontSize:10, color:'#99c4e8', flexShrink:0 }}>↵ insert</span>
              )}
            </div>
          ))}
        </div>

        {/* Footer hint */}
        <div style={{
          padding:'7px 14px', borderTop:`1px solid ${C.border}`,
          display:'flex', gap:12, fontSize:10, color:'#555',
        }}>
          <span>↑↓ navigate</span>
          <span>↵ insert into chat</span>
          <span>Esc close</span>
        </div>
      </div>
    </div>
  )
}
