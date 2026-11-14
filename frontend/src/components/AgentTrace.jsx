import { useState, useEffect, useCallback } from 'react'
import { C } from '../App'

const AGENT_COLOR = {
  verify:      '#569cd6',
  autofix:     '#e2c08d',
  critic:      '#c586c0',
  security:    '#f48771',
  performance: '#73c991',
}

function fmtTime(iso) {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour:'2-digit', minute:'2-digit', second:'2-digit' })
  } catch { return iso }
}

function StepChip({ step }) {
  const [open, setOpen] = useState(false)
  const color = AGENT_COLOR[step.agent] || '#888'
  const hasDetail = (step.notes?.length || 0) + (step.findings?.length || 0) > 0

  return (
    <div style={{ marginBottom:4 }}>
      <div
        onClick={() => hasDetail && setOpen(v => !v)}
        style={{
          display:'flex', alignItems:'center', gap:8, padding:'5px 9px',
          borderRadius:4, background:`${color}12`, border:`1px solid ${color}33`,
          cursor: hasDetail ? 'pointer' : 'default',
        }}
      >
        <span style={{ width:7, height:7, borderRadius:'50%', background:color, flexShrink:0 }} />
        <span style={{ fontSize:11, color, fontWeight:600, flexShrink:0 }}>{step.agent}</span>
        <span style={{ fontSize:10, color:'#666', flex:1 }}>{step.reason}</span>
        {step.model && (
          <span style={{ fontSize:9, color:'#555', flexShrink:0 }}>{step.model.split(':')[0]}</span>
        )}
        <span style={{ fontSize:10, color:'#555', flexShrink:0 }}>{step.duration_ms}ms</span>
        {hasDetail && <span style={{ fontSize:9, color:'#555' }}>{open ? '▾' : '▸'}</span>}
      </div>
      {open && hasDetail && (
        <div style={{ marginLeft:18, marginTop:3, fontSize:10, color:'#777', lineHeight:1.7 }}>
          {step.notes?.map((n, i) => <div key={`n${i}`}>· {n}</div>)}
          {step.findings?.map((f, i) => (
            <div key={`f${i}`} style={{ color:'#e2c08d' }}>⚠ {f}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function TaskRow({ task }) {
  const [open, setOpen] = useState(false)
  const outcomeColor = task.outcome === 'applied' ? '#73c991' :
                       task.outcome === 'flagged' ? '#e2c08d' : '#666'

  return (
    <div style={{ borderBottom:'1px solid #2a2a2a', padding:'10px 14px' }}>
      <div onClick={() => setOpen(v => !v)} style={{ display:'flex', alignItems:'center', gap:8, cursor:'pointer' }}>
        <span style={{ fontSize:9, color:'#555', flexShrink:0 }}>{open ? '▾' : '▸'}</span>
        <span style={{ fontSize:12, color:C.text, flex:1, overflow:'hidden',
                       textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
          {task.request}
        </span>
        <span style={{
          fontSize:9, fontWeight:600, padding:'1px 7px', borderRadius:8,
          background:`${outcomeColor}22`, color:outcomeColor, flexShrink:0,
        }}>
          {task.outcome}
        </span>
        <span style={{ fontSize:10, color:'#555', flexShrink:0 }}>{task.total_ms}ms</span>
      </div>
      <div style={{ fontSize:10, color:'#555', marginTop:3, marginLeft:17 }}>
        {fmtTime(task.ts)} {task.file_path && `· ${task.file_path}`}
        {' · '}{task.agents_run.join(' → ')}
      </div>
      {open && (
        <div style={{ marginTop:8, marginLeft:17 }}>
          {task.steps.map((s, i) => <StepChip key={i} step={s} />)}
        </div>
      )}
    </div>
  )
}

export default function AgentTrace({ onClose }) {
  const [entries,  setEntries]  = useState([])
  const [stats,    setStats]    = useState(null)
  const [ragStats, setRagStats] = useState(null)
  const [loading,  setLoading]  = useState(true)
  const [showStats, setShowStats] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/api/journal?limit=40')
      .then(r => r.json())
      .then(d => {
        setEntries(d.entries ?? [])
        setStats(d.stats)
        setRagStats(d.rag_stats)
      })
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
    <div style={{ position:'fixed', inset:0, zIndex:1000, background:'rgba(0,0,0,0.72)',
                  display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div style={{ background:'#1e1e1e', border:`1px solid ${C.borderLight}`,
                    borderRadius:6, width:600, maxWidth:'95vw', maxHeight:'82vh',
                    display:'flex', flexDirection:'column', overflow:'hidden' }}>

        <div style={{ padding:'12px 16px', borderBottom:`1px solid ${C.border}`,
                      display:'flex', alignItems:'center', gap:10, flexShrink:0 }}>
          <span style={{ fontSize:13, fontWeight:500 }}>📜 Agent Log</span>
          {stats && (
            <span
              onClick={() => setShowStats(v => !v)}
              style={{ fontSize:11, color:'#666', cursor:'pointer' }}
              title="Click for observability breakdown"
            >
              {stats.total_tasks} tasks · avg {stats.avg_ms}ms
              {ragStats && ragStats.queries > 0 && ` · RAG ${ragStats.hit_rate}% hit rate`}
              {' '}<span style={{ opacity:0.5 }}>{showStats ? '▾' : '▸'}</span>
            </span>
          )}
          <div style={{ flex:1 }} />
          <button onClick={load} style={{ background:'none', border:'none',
            color:C.textMuted, cursor:'pointer', fontSize:14 }}>↻</button>
          <button onClick={onClose} style={{ background:'none', border:'none',
            color:C.textMuted, cursor:'pointer', fontSize:18, lineHeight:1 }}>×</button>
        </div>

        {/* Milestone F: observability breakdown */}
        {showStats && stats && (
          <div style={{ padding:'10px 16px', borderBottom:`1px solid ${C.border}`,
                        background:'#181818', flexShrink:0, fontSize:11 }}>
            {Object.keys(stats.agent_counts ?? {}).length > 0 && (
              <div style={{ marginBottom:8 }}>
                <div style={{ color:'#555', marginBottom:4 }}>Agent run counts (last 200 steps)</div>
                <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
                  {Object.entries(stats.agent_counts).map(([agent, count]) => (
                    <span key={agent} style={{
                      background:`${AGENT_COLOR[agent]||'#888'}18`,
                      border:`1px solid ${AGENT_COLOR[agent]||'#888'}44`,
                      color: AGENT_COLOR[agent] || '#888',
                      padding:'2px 8px', borderRadius:10,
                    }}>
                      {agent}: {count}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {(stats.model_stats ?? []).length > 0 && (
              <div>
                <div style={{ color:'#555', marginBottom:4 }}>Model success rate</div>
                {stats.model_stats.map(m => (
                  <div key={m.model} style={{ display:'flex', alignItems:'center', gap:8, marginBottom:3 }}>
                    <span style={{ color:'#ccc', minWidth:140 }}>{m.model}</span>
                    <div style={{ flex:1, height:5, background:'#2a2a2a', borderRadius:3, overflow:'hidden' }}>
                      <div style={{ width:`${m.success_rate}%`, height:'100%',
                                    background: m.success_rate >= 70 ? '#73c991' : m.success_rate >= 40 ? '#e2c08d' : '#f48771' }} />
                    </div>
                    <span style={{ color:'#666', minWidth:80, textAlign:'right' }}>
                      {m.success_rate}% ({m.runs} runs)
                    </span>
                  </div>
                ))}
              </div>
            )}
            {ragStats && (
              <div style={{ marginTop:8, color:'#666' }}>
                🔍 RAG: {ragStats.queries} searches, {ragStats.hits} returned results
                {ragStats.queries > 0 && ` (${ragStats.hit_rate}% hit rate)`}
              </div>
            )}
          </div>
        )}

        <div style={{ flex:1, overflow:'auto' }}>
          {loading && (
            <div style={{ padding:28, textAlign:'center', color:'#555', fontSize:12 }}>Loading…</div>
          )}
          {!loading && entries.length === 0 && (
            <div style={{ padding:28, textAlign:'center', color:'#3a3a3a', fontSize:12, lineHeight:1.7 }}>
              <div style={{ fontSize:22, marginBottom:8, opacity:0.3 }}>📜</div>
              No agent tasks recorded yet.<br/>
              Apply an AI suggestion with "Include file" to see the pipeline in action.
            </div>
          )}
          {entries.map(task => <TaskRow key={task.id} task={task} />)}
        </div>
      </div>
    </div>
  )
}
