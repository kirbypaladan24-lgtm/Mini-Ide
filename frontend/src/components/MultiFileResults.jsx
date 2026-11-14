import { useState } from 'react'
import DiffViewer from './DiffViewer'
import { C } from '../App'

function ConsistencyWarnings({ warnings }) {
  if (!warnings?.length) return null
  return (
    <div style={{ padding:'5px 10px', background:'#e2c08d08', borderTop:'1px solid #e2c08d22' }}>
      {warnings.map((w, i) => (
        <div key={i} style={{ fontSize:10, color:'#e2c08d', display:'flex', gap:5, lineHeight:1.5 }}>
          <span style={{ flexShrink:0 }}>⚠</span><span>{w}</span>
        </div>
      ))}
    </div>
  )
}

function FileResult({ result, index, total, applied, skipped, onApply, onSkip }) {
  const [showDiff, setShowDiff] = useState(false)
  const { file, code, original, language, review, success, consistency_warnings = [], edit_mode_used } = result
  const isNew   = !original
  const hasWarn = consistency_warnings.length > 0
  const isTargeted = edit_mode_used === 'targeted'

  const borderColor = applied ? '#73c99155' : skipped ? '#33333366' :
                      hasWarn ? '#e2c08d44' : '#3a3a3a'

  return (
    <div style={{
      border:`1px solid ${borderColor}`, borderRadius:6, overflow:'hidden',
      opacity: skipped ? 0.45 : 1, background: applied ? '#1e2a1e' : '#1a1a1a',
    }}>
      <div style={{
        padding:'7px 12px', borderBottom:'1px solid #252525',
        display:'flex', alignItems:'center', gap:8,
      }}>
        <span style={{ fontSize:11, flexShrink:0 }}>{isNew ? '✨' : '✏️'}</span>
        <code style={{
          color:C.text, fontSize:11, flex:1, overflow:'hidden',
          textOverflow:'ellipsis', whiteSpace:'nowrap',
          fontFamily:"'Cascadia Code','Fira Code',monospace",
        }}>{file}</code>
        {!isNew && (
          <span style={{
            fontSize:9, padding:'1px 6px', borderRadius:8, flexShrink:0,
            background: isTargeted ? '#73c99118' : '#e2c08d18',
            color:      isTargeted ? '#73c991' : '#e2c08d',
            border: `1px solid ${isTargeted ? '#73c99144' : '#e2c08d44'}`,
          }}>
            {isTargeted ? '✎ targeted' : '⟳ full rewrite'}
          </span>
        )}
        <span style={{ fontSize:9, color:'#555', flexShrink:0 }}>{index}/{total}</span>
        {hasWarn && !applied && <span style={{ fontSize:9, color:'#e2c08d' }}>⚠</span>}
        {review?.verified && !applied && <span style={{ fontSize:9, color:'#73c991' }}>✓</span>}
        {applied && <span style={{ fontSize:10, color:'#73c991', fontWeight:500 }}>✓ Applied</span>}
        {skipped && <span style={{ fontSize:10, color:'#555' }}>– Skipped</span>}
      </div>

      {!applied && !skipped && success && (
        <div style={{ padding:'7px 12px', display:'flex', gap:6, alignItems:'center' }}>
          <button onClick={() => setShowDiff(v => !v)} style={{
            background:'#2a2a2a', border:'1px solid #3a3a3a', color:C.textMuted,
            padding:'3px 10px', borderRadius:3, cursor:'pointer', fontSize:10, fontFamily:'inherit',
          }}>{showDiff ? 'Hide diff' : 'View diff'}</button>
          <button onClick={onApply} style={{
            background:'#0e639c', border:'none', color:'#fff',
            padding:'3px 12px', borderRadius:3, cursor:'pointer', fontSize:10, fontFamily:'inherit',
          }}>Apply</button>
          <button onClick={onSkip} style={{
            background:'transparent', border:'1px solid #3a3a3a', color:'#666',
            padding:'3px 10px', borderRadius:3, cursor:'pointer', fontSize:10, fontFamily:'inherit',
          }}>Skip</button>
        </div>
      )}

      {!success && !applied && (
        <div style={{ padding:'8px 12px', fontSize:11, color:'#f48771' }}>
          Generation failed for this file.
        </div>
      )}

      <ConsistencyWarnings warnings={consistency_warnings} />

      {showDiff && !applied && !skipped && (
        <div style={{ borderTop:'1px solid #252525' }}>
          <DiffViewer
            path={file} originalContent={original} proposedContent={code}
            language={language}
            onApply={() => { onApply(); setShowDiff(false) }}
            onClose={() => { onSkip(); setShowDiff(false) }}
          />
        </div>
      )}
    </div>
  )
}

export default function MultiFileResults({ results, featureRequest, consistencySummary, onRefreshEditor }) {
  const [states,   setStates]   = useState({})
  const [applying, setApplying] = useState(false)
  const [feedback, setFeedback] = useState('')

  if (!results?.length) return null
  const pending = results.filter(r => r.success && !states[r.file])
  const anyWarn = results.some(r => r.consistency_warnings?.length > 0)
  const markState = (file, s) => setStates(prev => ({ ...prev, [file]: s }))

  const applyAll = async () => {
    const toApply = results.filter(r => r.success && !states[r.file])
    if (!toApply.length) return
    setApplying(true); setFeedback('')
    try {
      const r = await fetch('/api/apply-multi', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          feature_request: featureRequest || 'AI changes',
          files: toApply.map(f => ({ path:f.file, content:f.code, original:f.original, language:f.language })),
        }),
      })
      const d = await r.json()
      if (d.ok) {
        toApply.forEach(f => markState(f.file, 'applied'))
        setFeedback(`✓ Applied ${toApply.length} file${toApply.length !== 1 ? 's' : ''}`)
        onRefreshEditor?.()
      } else if (d.rolled_back) {
        setFeedback('✗ Apply failed — all changes rolled back automatically.')
      }
    } catch (e) { setFeedback(`Error: ${e.message}`) }
    setApplying(false)
  }

  const applySingle = async (result) => {
    try {
      const r = await fetch('/api/apply-multi', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
          feature_request: featureRequest || 'AI changes',
          files: [{ path:result.file, content:result.code, original:result.original, language:result.language }],
        }),
      })
      const d = await r.json()
      if (d.ok) { markState(result.file, 'applied'); onRefreshEditor?.() }
    } catch {}
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:8, width:'100%', maxWidth:'97%' }}>
      <div style={{
        padding:'8px 12px', borderRadius:6, background:'#1a1e2e',
        border:'1px solid #2a3a5a', display:'flex', alignItems:'center', gap:8, flexWrap:'wrap', fontSize:11,
      }}>
        <span style={{ color:'#4fc1ff', fontWeight:500 }}>🗂 {results.length} file{results.length !== 1 ? 's' : ''} ready</span>
        {(anyWarn || consistencySummary) && (
          <span style={{ fontSize:10, color:'#e2c08d' }}>{consistencySummary || '⚠ check warnings before applying'}</span>
        )}
        <div style={{ flex:1 }} />
        {pending.length > 0 && (
          <button onClick={applyAll} disabled={applying} style={{
            background:applying ? '#2a2a2a' : '#0e639c', border:'none',
            color:applying ? '#555' : '#fff', padding:'4px 14px', borderRadius:3,
            cursor:applying ? 'default' : 'pointer', fontSize:10, fontFamily:'inherit', fontWeight:500,
          }}>{applying ? 'Applying…' : `Apply All (${pending.length})`}</button>
        )}
      </div>

      {feedback && (
        <div style={{
          fontSize:11, padding:'4px 10px', borderRadius:4,
          color:feedback.startsWith('✓') ? '#73c991' : '#f48771',
          background:feedback.startsWith('✓') ? '#73c99112' : '#f4877112',
          border:`1px solid ${feedback.startsWith('✓') ? '#73c99133' : '#f4877133'}`,
        }}>{feedback}</div>
      )}

      {results.map((r, i) => (
        <FileResult key={r.file} result={r} index={i+1} total={results.length}
          applied={states[r.file] === 'applied'} skipped={states[r.file] === 'skipped'}
          onApply={() => applySingle(r)} onSkip={() => markState(r.file, 'skipped')} />
      ))}
    </div>
  )
}
