import { useState, useEffect } from 'react'
import { C } from '../App'

function parseDiff(text) {
  if (!text.trim()) return []
  return text.split('\n').map((raw, i) => {
    if (raw.startsWith('+++') || raw.startsWith('---'))
      return { id:i, type:'header',  text:raw }
    if (raw.startsWith('@@'))
      return { id:i, type:'hunk',    text:raw }
    if (raw.startsWith('+'))
      return { id:i, type:'add',     text:raw.slice(1) }
    if (raw.startsWith('-'))
      return { id:i, type:'remove',  text:raw.slice(1) }
    if (raw.startsWith('\\'))
      return { id:i, type:'meta',    text:raw }
    return   { id:i, type:'context', text:raw.slice(1) }
  })
}

const BG  = { add:'rgba(115,201,145,0.13)', remove:'rgba(244,135,113,0.13)',
              hunk:'rgba(86,156,214,0.07)', header:'transparent',
              context:'transparent', meta:'transparent' }
const FG  = { add:'#73c991', remove:'#f48771', hunk:'#569cd6',
              header:'#555', context:'#888', meta:'#555' }
const PFX = { add:'+', remove:'-', hunk:'', header:'', context:' ', meta:'' }

export default function DiffViewer({ path, originalContent, proposedContent, language, review, onApply, onClose }) {
  const [lines,   setLines]   = useState(null)
  const [stats,   setStats]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)
  const [impact,  setImpact]  = useState(null)   // Milestone E

  useEffect(() => {
    if (proposedContent == null) return
    setLoading(true); setError(null)
    fetch('/api/diff', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, content: proposedContent, original: originalContent ?? '' }),
    })
    .then(r => r.json())
    .then(d => {
      if (d.error) { setError(d.error); return }
      setLines(parseDiff(d.diff))
      setStats(d.stats)
    })
    .catch(e => setError(String(e)))
    .finally(() => setLoading(false))
  }, [path, originalContent, proposedContent])

  // Milestone E: impact analysis — who calls the functions that changed?
  useEffect(() => {
    if (proposedContent == null || !originalContent) { setImpact(null); return }
    fetch('/api/graph/diff-impact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        path, original: originalContent, proposed: proposedContent,
        language: language || 'python',
      }),
    })
      .then(r => r.json())
      .then(d => setImpact(d.impacts?.length > 0 ? d : null))
      .catch(() => setImpact(null))
  }, [path, originalContent, proposedContent, language])

  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  const filename = path?.split('/').pop() ?? path
  const noChange = !loading && !error && lines?.length === 0
  const canApply = !loading && !error && !noChange

  return (
    <div style={{ position:'fixed', inset:0, zIndex:1000, background:'rgba(0,0,0,0.75)',
                  display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div style={{ background:'#1e1e1e', border:'1px solid #454545', borderRadius:6,
                    width:740, maxWidth:'96vw', maxHeight:'86vh',
                    display:'flex', flexDirection:'column', overflow:'hidden' }}>

        {/* Header */}
        <div style={{ padding:'11px 16px', borderBottom:`1px solid ${C.border}`,
                      display:'flex', alignItems:'center', gap:10, flexShrink:0 }}>
          <span style={{ fontSize:13, fontWeight:500 }}>
            Diff —{' '}
            <code style={{ background:'#2d2d2d', padding:'1px 6px', borderRadius:3, fontSize:12 }}>
              {filename}
            </code>
          </span>
          {stats && (
            <span style={{ fontSize:11, display:'flex', gap:8 }}>
              <span style={{ color:'#73c991' }}>+{stats.added}</span>
              <span style={{ color:'#f48771' }}>−{stats.removed}</span>
              {stats.net !== 0 && (
                <span style={{ color:'#858585' }}>({stats.net > 0 ? '+':''}{stats.net} lines)</span>
              )}
            </span>
          )}
          {/* Milestone G: Trust Score badge */}
          {review?.trust && (
            <span
              title={Object.entries(review.trust.checks)
                .filter(([, v]) => v !== null)
                .map(([k, v]) => `${v ? '✓' : '✗'} ${k}`)
                .join('\n')}
              style={{
                fontSize:10, fontWeight:600, padding:'2px 8px', borderRadius:10,
                cursor:'help',
                background: review.trust.score >= 80 ? '#73c99118' :
                            review.trust.score >= 50 ? '#e2c08d18' : '#f4877118',
                color:      review.trust.score >= 80 ? '#73c991' :
                            review.trust.score >= 50 ? '#e2c08d' : '#f48771',
                border: `1px solid ${
                  review.trust.score >= 80 ? '#73c99144' :
                  review.trust.score >= 50 ? '#e2c08d44' : '#f4877144'}`,
              }}
            >
              🛡 Trust: {review.trust.score}%
            </span>
          )}
          <div style={{ flex:1 }} />
          <span style={{ fontSize:10, color:'#555' }}>Saved to undo history on apply</span>
        </div>

        {/* Milestone E: impact analysis warning */}
        {impact && (
          <div style={{
            padding:'8px 16px', background:'#e2c08d12', borderBottom:'1px solid #e2c08d33',
            flexShrink:0,
          }}>
            {impact.impacts.map((imp, i) => (
              <div key={i} style={{ fontSize:11, color:'#e2c08d', display:'flex',
                                    alignItems:'baseline', gap:6, marginBottom: i < impact.impacts.length-1 ? 4 : 0 }}>
                <span>⚠</span>
                <span>{imp.summary}</span>
              </div>
            ))}
          </div>
        )}

        {/* Diff body */}
        <div style={{ flex:1, overflow:'auto',
                      fontFamily:"'Cascadia Code','Fira Code',Consolas,monospace",
                      fontSize:11, lineHeight:'18px' }}>
          {loading && (
            <div style={{ padding:28, textAlign:'center', color:'#555' }}>Generating diff…</div>
          )}
          {error && (
            <div style={{ padding:16, color:'#f48771' }}>⚠ {error}</div>
          )}
          {noChange && (
            <div style={{ padding:28, textAlign:'center', color:'#555' }}>
              No changes — content is identical.
            </div>
          )}
          {lines && lines.map(line => (
            <div key={line.id} style={{
              display:'flex', background: BG[line.type],
              borderLeft: line.type === 'add'    ? '2px solid #73c99155'
                        : line.type === 'remove' ? '2px solid #f4877155'
                        :                          '2px solid transparent',
            }}>
              <span style={{ width:18, flexShrink:0, textAlign:'center',
                             color:FG[line.type], userSelect:'none', paddingTop:1 }}>
                {PFX[line.type]}
              </span>
              <span style={{ flex:1, color:FG[line.type], padding:'0 10px',
                             whiteSpace:'pre', overflow:'hidden', textOverflow:'ellipsis' }}>
                {line.text}
              </span>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div style={{ padding:'11px 16px', borderTop:`1px solid ${C.border}`,
                      display:'flex', justifyContent:'flex-end', gap:8, flexShrink:0 }}>
          <button onClick={onClose} style={{ background:'transparent', border:'1px solid #555',
            color:C.text, padding:'6px 14px', borderRadius:3, cursor:'pointer',
            fontSize:12, fontFamily:'inherit' }}>
            Cancel
          </button>
          <button onClick={onApply} disabled={!canApply} style={{
            background: canApply ? C.accent : '#333',
            border:'none', color: canApply ? '#fff' : '#555',
            padding:'6px 16px', borderRadius:3,
            cursor: canApply ? 'pointer' : 'default',
            fontSize:12, fontFamily:'inherit', transition:'background 0.1s',
          }}>
            Apply Changes
          </button>
        </div>
      </div>
    </div>
  )
}
