import { useState, useEffect, useRef, useCallback } from 'react'
import { C } from '../App'
import DiffViewer from './DiffViewer'
import TemplatesPicker from './TemplatesPicker'
import SaveAsModal from './SaveAsModal'
import AttachmentPill from './AttachmentPill'
import PlanView from './PlanView'
import MultiFileResults from './MultiFileResults'
import WorkingState from './WorkingState'
import AgentTurnCard from './AgentTurnCard'

// ── Parse text into plain-text + fenced code blocks ──────────────────────────
function parseBlocks(text) {
  const parts = []
  const re    = /```(\w*)\n?([\s\S]*?)```/g
  let last = 0, m
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push({ type:'text', content:text.slice(last, m.index) })
    parts.push({ type:'code', lang:m[1]||'text', content:m[2].trimEnd() })
    last = m.index + m[0].length
  }
  if (last < text.length) {
    const remainder = text.slice(last)
    // Safety net: an unterminated opening fence (model forgot to close it)
    const dangling = remainder.match(/```(\w*)\n?([\s\S]+)$/)
    if (dangling && dangling[2].trim().length > 10) {
      const before = remainder.slice(0, dangling.index)
      if (before.trim()) parts.push({ type:'text', content:before })
      parts.push({ type:'code', lang:dangling[1]||'text', content:dangling[2].trimEnd() })
    } else {
      parts.push({ type:'text', content:remainder })
    }
  }
  return parts
}

// ── Animated typing dots ──────────────────────────────────────────────────────
function Dots() {
  return (
    <>
      <style>{`@keyframes blink{0%,80%,100%{opacity:.15}40%{opacity:1}}`}</style>
      <span style={{ display:'inline-flex', gap:4 }}>
        {[0,1,2].map(i => (
          <span key={i} style={{
            width:5, height:5, borderRadius:'50%', background:'#666',
            display:'inline-block',
            animation:`blink 1.2s ${i*0.2}s infinite ease-in-out`,
          }}/>
        ))}
      </span>
    </>
  )
}

// ── Review badge (Milestone A + D) ────────────────────────────────────────────
function ReviewBadge({ review }) {
  if (!review) return null
  const { ok, verified, issues = [], revised, security, performance, agents_run = [] } = review

  const secRisk    = security?.risk
  const secHigh     = secRisk === 'high'
  const overallOk   = ok && !secHigh
  const color   = overallOk ? '#73c991' : secHigh ? '#f48771' : '#e2c08d'
  const icon    = overallOk ? '✓' : secHigh ? '⛔' : '⚠'
  const label   = secHigh
    ? `Security: ${security.findings.length} issue${security.findings.length!==1?'s':''}`
    : revised
    ? 'Auto-fixed'
    : verified
    ? (ok ? 'Verified' : `${issues.length} issue${issues.length!==1?'s':''}`)
    : 'Checked'

  const tooltipParts = [
    ...issues,
    ...(security?.findings ?? []).map(f => `[security] ${f.label}`),
    ...(performance?.findings ?? []).map(f => `[performance] ${f.label}`),
  ]

  return (
    <div style={{ marginTop:5, display:'flex', flexWrap:'wrap', gap:5 }}>
      <div style={{
        display:'inline-flex', alignItems:'center', gap:5, fontSize:10,
        color, padding:'2px 7px', borderRadius:10,
        background:`${color}15`, border:`1px solid ${color}44`,
      }}>
        <span>{icon}</span>
        <span>{label}</span>
        {tooltipParts.length > 0 && (
          <span title={tooltipParts.join('\n')} style={{ cursor:'help', opacity:0.7 }}>ⓘ</span>
        )}
      </div>
      {/* Milestone D: show which specialist agents ran */}
      {agents_run.length > 1 && (
        <span style={{ fontSize:9, color:'#555', display:'inline-flex', alignItems:'center' }}>
          {agents_run.join(' → ')}
        </span>
      )}
      {/* Milestone G: Trust Score */}
      {review.trust && (
        <span
          title={Object.entries(review.trust.checks)
            .filter(([, v]) => v !== null)
            .map(([k, v]) => `${v ? '✓' : '✗'} ${k}`)
            .join('\n')}
          style={{
            fontSize:9, fontWeight:600, padding:'1px 7px', borderRadius:8, cursor:'help',
            color: review.trust.score >= 80 ? '#73c991' : review.trust.score >= 50 ? '#e2c08d' : '#f48771',
            background: 'transparent',
          }}
        >
          🛡 {review.trust.score}%
        </span>
      )}
    </div>
  )
}

// ── Context badge (Phases 3+4, Milestone E) ───────────────────────────────────
function ContextBadge({ summary }) {
  const [open, setOpen] = useState(false)
  const webSources = summary?.web_sources ?? []
  const ragHitsCheck = summary?.rag_hits ?? []
  if (!summary?.current_file && webSources.length === 0 && ragHitsCheck.length === 0) return null

  const imports  = summary.imports   ?? []
  const tabs     = summary.open_tabs ?? []
  const symbols  = summary.symbols   ?? {}
  const ragHits  = summary.rag_hits  ?? []
  const fnCount  = symbols.functions?.length ?? 0
  const clsCount = symbols.classes?.length   ?? 0
  const total    = (summary.current_file ? 1 : 0) + imports.length + tabs.length
                    + ragHits.length + webSources.length

  return (
    <div style={{ margin:'4px 0 2px', fontSize:10 }}>
      <button onClick={() => setOpen(v => !v)} style={{
        background:`${C.accent}18`, border:`1px solid ${C.accent}44`,
        color:C.accent, borderRadius:3, padding:'2px 8px',
        cursor:'pointer', fontSize:10, fontFamily:'inherit',
        display:'inline-flex', alignItems:'center', gap:5,
      }}>
        📎 Context: {total} source{total!==1?'s':''}
        {ragHits.length > 0 && <span style={{color:'#c586c0'}}>· {ragHits.length} RAG</span>}
        {webSources.length > 0 && <span style={{color:'#4ec9b0'}}>· {webSources.length} web</span>}
        {(fnCount+clsCount) > 0 && (
          <span style={{color:'#dcdcaa'}}>· {fnCount}fn{clsCount>0?` ${clsCount}cls`:''}</span>
        )}
        <span style={{opacity:0.5}}>{open?'▾':'▸'}</span>
      </button>
      {open && (
        <div style={{ marginTop:4, background:'#1a1a1a', border:'1px solid #2a2a2a',
                      borderRadius:4, padding:'7px 10px', fontSize:10, lineHeight:1.9 }}>
          {summary.current_file && <Row icon="📄" label={summary.current_file} note="current" />}
          {imports.map(p  => <Row key={p} icon="🔗" label={p} note="import" />)}
          {tabs.map(p     => <Row key={p} icon="📑" label={p} note="tab" />)}
          {fnCount  > 0  && <Row icon="⚙" label={`${fnCount} fn`}  note={symbols.functions.slice(0,6).join(', ')} />}
          {clsCount > 0  && <Row icon="◻" label={`${clsCount} class`} note={symbols.classes.join(', ')} />}
          {ragHits.length > 0 && (
            <div style={{ borderTop:'1px solid #2a2a2a', marginTop:5, paddingTop:5 }}>
              <div style={{ color:'#555', marginBottom:3 }}>🔍 RAG — semantic matches</div>
              {ragHits.map((h,i) => (
                <Row key={i}
                  icon={h.type==='function'?'ƒ':h.type==='class'?'◻':'◦'}
                  label={h.name||h.path}
                  note={`${h.path} · ${(h.score*100).toFixed(0)}%`}
                  labelColor="#c586c0" />
              ))}
            </div>
          )}
          {/* Milestone E: web sources */}
          {webSources.length > 0 && (
            <div style={{ borderTop:'1px solid #2a2a2a', marginTop:5, paddingTop:5 }}>
              <div style={{ color:'#555', marginBottom:3 }}>🌐 Web research</div>
              {webSources.map((s,i) => (
                <div key={i} style={{ display:'flex', gap:6, color:'#4ec9b0' }}>
                  <span>↗</span>
                  <a href={s.url} target="_blank" rel="noreferrer"
                     style={{ color:'#4ec9b0', textDecoration:'none', wordBreak:'break-all' }}>
                    {s.title || s.url}
                  </a>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Row({ icon, label, note, labelColor }) {
  return (
    <div style={{ display:'flex', gap:6, alignItems:'baseline', color:'#555' }}>
      <span style={{ flexShrink:0 }}>{icon}</span>
      <span style={{ color:labelColor||'#888', wordBreak:'break-all' }}>{label}</span>
      {note && <span style={{ color:'#555', flexShrink:0 }}>· {note}</span>}
    </div>
  )
}

// ── Regression test result note (Milestone C) ─────────────────────────────────
function RegressionNote({ regression }) {
  if (!regression) return null
  const { success, summary, test_path } = regression
  const color = success ? '#73c991' : '#f48771'
  return (
    <div style={{
      alignSelf:'flex-start', maxWidth:'96%', fontSize:11,
      display:'flex', alignItems:'center', gap:6,
      padding:'5px 10px', borderRadius:4,
      background:`${color}12`, border:`1px solid ${color}33`, color,
    }}>
      <span>{success ? '✓' : '✗'}</span>
      <span>Ran <code style={{opacity:0.8}}>{test_path}</code> — {summary}</span>
    </div>
  )
}

// ── Explainability — on-demand "why" (Milestone E) ────────────────────────────
function ExplainButton({ request, original, proposed, language }) {
  const [explanation, setExplanation] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchExplain = async () => {
    if (explanation !== null) { setExplanation(null); return }   // toggle closed
    setLoading(true)
    try {
      const r = await fetch('/api/explain', {
        method: 'POST', headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({ request: request || '', original, proposed, language }),
      })
      const d = await r.json()
      setExplanation(d.explanation || 'No explanation available.')
    } catch {
      setExplanation('Could not fetch explanation.')
    }
    setLoading(false)
  }

  return (
    <>
      <button
        onClick={fetchExplain}
        style={{
          background:'#c586c018', border:'1px solid #c586c055',
          color:'#c586c0', padding:'3px 10px', borderRadius:3,
          fontSize:10, cursor:'pointer', fontFamily:'inherit',
        }}
        onMouseEnter={e => e.currentTarget.style.background='#c586c030'}
        onMouseLeave={e => e.currentTarget.style.background='#c586c018'}
      >
        {loading ? '…' : explanation !== null ? '❓ Hide' : '❓ Why?'}
      </button>
      {explanation !== null && (
        <div style={{
          width:'100%', marginTop:4, fontSize:11, color:'#bbb', lineHeight:1.6,
          background:'#c586c00c', border:'1px solid #c586c033',
          borderRadius:4, padding:'7px 10px',
        }}>
          {explanation}
        </div>
      )}
    </>
  )
}

// ── Single chat bubble ────────────────────────────────────────────────────────
function Bubble({ msg, activeFile, onApply, onSaveAs }) {
  const isUser  = msg.role === 'user'
  const isError = msg.role === 'error'
  const blocks  = parseBlocks(msg.content)

  return (
    <div style={{ alignSelf:isUser?'flex-end':'flex-start', maxWidth:'96%' }}>
      {!isUser && (
        <div style={{ fontSize:10, color:'#555', marginBottom:3, paddingLeft:2 }}>
          {isError ? '⚠ Error' : 'Assistant'}
        </div>
      )}
      <div style={{
        background: isUser ? `${C.accent}14` : isError ? '#3a1a1a' : C.bgTab,
        border:`1px solid ${isUser?`${C.accent}40`:isError?'#6b2c2c':C.borderLight}`,
        borderRadius: isUser ? '14px 14px 3px 14px' : '3px 14px 14px 14px',
        padding:'9px 12px',
      }}>
        {blocks.map((b,i) =>
          b.type === 'text' ? (
            <div key={i} style={{ fontSize:12, lineHeight:1.7,
              color:isError?'#f48771':C.text, whiteSpace:'pre-wrap', wordBreak:'break-word' }}>
              {b.content.trim()}
            </div>
          ) : (
            <div key={i} style={{ marginTop:6, marginBottom:4 }}>
              {b.lang && (
                <div style={{ fontSize:9, color:'#555', textTransform:'uppercase',
                              letterSpacing:1, fontWeight:600, marginBottom:4 }}>
                  {b.lang}
                </div>
              )}
              <pre style={{
                background:'#181818', border:'1px solid #333', borderRadius:4,
                padding:'8px 10px', margin:0, overflow:'auto', maxHeight:280,
                fontSize:11, lineHeight:1.6, color:'#d4d4d4',
                fontFamily:"'Cascadia Code','Fira Code',Consolas,monospace",
                whiteSpace:'pre',
              }}>
                {/* If this message has a fixed_code from the quality pipeline, use it */}
                {msg.fixedCode && b.type === 'code' ? msg.fixedCode : b.content}
              </pre>
              <div style={{ display:'flex', gap:6, marginTop:5, flexWrap:'wrap' }}>
                {activeFile && (
                  <button
                    onClick={() => onApply(
                      msg.fixedCode || b.content,
                      b.lang,
                      activeFile.content ?? ''
                    )}
                    style={{
                      background:`${C.accent}18`, border:`1px solid ${C.accent}55`,
                      color:C.accent, padding:'3px 10px', borderRadius:3,
                      fontSize:10, cursor:'pointer', fontFamily:'inherit',
                    }}
                    onMouseEnter={e => e.currentTarget.style.background=`${C.accent}30`}
                    onMouseLeave={e => e.currentTarget.style.background=`${C.accent}18`}
                  >
                    ↳ Apply to {activeFile.path.split('/').pop()}
                  </button>
                )}
                {/* Milestone C: Save as new file — closes the "create file" gap */}
                <button
                  onClick={() => onSaveAs(msg.fixedCode || b.content, b.lang)}
                  style={{
                    background:'#073a1818', border:'1px solid #73c99155',
                    color:'#73c991', padding:'3px 10px', borderRadius:3,
                    fontSize:10, cursor:'pointer', fontFamily:'inherit',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background='#073a1840'}
                  onMouseLeave={e => e.currentTarget.style.background='#073a1818'}
                >
                  💾 Save as new file
                </button>
                {/* Milestone E: explain why this approach was chosen */}
                {activeFile && (
                  <ExplainButton
                    request={msg.requestText}
                    original={activeFile.content ?? ''}
                    proposed={msg.fixedCode || b.content}
                    language={b.lang}
                  />
                )}
              </div>
            </div>
          )
        )}
        {/* Milestone A: review badge */}
        {!isUser && msg.review && <ReviewBadge review={msg.review} />}
      </div>
    </div>
  )
}

// ── Main ChatPanel ────────────────────────────────────────────────────────────
export default function ChatPanel({ activeFile, openFiles = [], onApplyCode, onCreateFile, pendingPrompt }) {
  const [messages,      setMessages]      = useState([])
  const [streaming,     setStreaming]      = useState(false)
  const [reviewing,     setReviewing]      = useState(null)  // step string while reviewing
  const [streamBuf,     setStreamBuf]      = useState('')
  const [models,        setModels]         = useState([])
  const [model,         setModel]          = useState('qwen3:8b')
  const modelRef = useRef(model)           // Milestone G: avoid stale closure in ws.onmessage
  useEffect(() => { modelRef.current = model }, [model])
  const [connected,     setConnected]      = useState(false)
  const [ollamaOk,      setOllamaOk]       = useState(false)
  const [input,         setInput]          = useState('')
  const [applyModal,    setApplyModal]     = useState(null)
  const [saveAsModal,   setSaveAsModal]    = useState(null)
  const [bestModel,     setBestModel]      = useState(null)   // Milestone G
  const [suggestion,    setSuggestion]     = useState(null)   // Milestone G: improvement suggestion
  const [attachments,   setAttachments]    = useState([])    // Sprint 1
  const [uploading,     setUploading]      = useState(false) // Sprint 1
  const [dragOver,      setDragOver]       = useState(false) // Sprint 1
  const fileInputRef = useRef(null)                          // Sprint 1
  // Sprint 3: planner + multi-file
  const [fileProgress,     setFileProgress]     = useState(null)
  const [showTemplates, setShowTemplates]  = useState(false)

  const wsRef     = useRef(null)
  const streamRef = useRef('')
  const msgEndRef = useRef(null)
  const inputRef  = useRef(null)

  // Sprint 5: consume pendingPrompt bridge from App.jsx (e.g. TODO resolver)
  const lastPendingTsRef = useRef(0)
  useEffect(() => {
    if (!pendingPrompt || pendingPrompt.ts === lastPendingTsRef.current) return
    lastPendingTsRef.current = pendingPrompt.ts
    setInput(pendingPrompt.text)
    setTimeout(() => inputRef.current?.focus(), 50)
  }, [pendingPrompt])
  const lastUserMessageRef = useRef('')   // Milestone E: for explainability requests
  const genStartRef = useRef(0)           // Milestone G: timing for model benchmarking

  // ── Fetch model list + Milestone G: best model indicator ──────────────────
  useEffect(() => {
    fetch('/api/models').then(r => r.json()).then(d => {
      if (d.models?.length) {
        setModels(d.models)
        const pick =
          d.models.find(m => m.includes('qwen3:8b')) ??
          d.models.find(m => m.includes('qwen3')) ??
          d.models.find(m => m.includes('qwen2.5:1.5b')) ??
          d.models.find(m => m.includes('qwen')) ?? d.models[0]
        if (pick) setModel(pick)
      }
    }).catch(() => {})

    // Milestone G: fetch empirically best model for edit tasks
    fetch('/api/benchmark/best?task_type=edit')
      .then(r => r.json())
      .then(d => { if (d.best?.model) setBestModel(d.best.model) })
      .catch(() => {})

    // Milestone G: check for a pending improvement suggestion
    fetch('/api/preferences/suggestion')
      .then(r => r.json())
      .then(d => { if (d.suggestion) setSuggestion(d.suggestion) })
      .catch(() => {})
  }, [])

  // ── WebSocket ─────────────────────────────────────────────────────────────
  // ── Sprint 1: file upload handler ────────────────────────────────────────
  const ACCEPTED_EXTS = new Set([
    '.png','.jpg','.jpeg','.webp','.gif','.bmp',
    '.pdf','.docx','.doc','.csv','.json','.txt','.md',
  ])

  const uploadFile = useCallback(async (file) => {
    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!ACCEPTED_EXTS.has(ext)) {
      alert(`Unsupported file type: ${ext}.\nSupported: images, PDF, DOCX, CSV, JSON, TXT, MD`)
      return
    }
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const r    = await fetch('/api/upload', { method:'POST', body: form })
      const data = await r.json()
      if (data.ok) {
        setAttachments(prev => [...prev, {
          ...data.attachment,
          server_path: data.server_path,
        }])
      }
    } catch (e) {
      console.error('Upload failed:', e)
    }
    setUploading(false)
  }, [])

  // Paste image handler (Ctrl+V with image in clipboard)
  useEffect(() => {
    const h = async (e) => {
      const item = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith('image/'))
      if (!item) return
      e.preventDefault()
      const file = item.getAsFile()
      if (file) await uploadFile(file)
    }
    document.addEventListener('paste', h)
    return () => document.removeEventListener('paste', h)
  }, [uploadFile])

  const handleDrop = useCallback(async (e) => {
    e.preventDefault()
    setDragOver(false)
    const files = [...e.dataTransfer.files]
    for (const f of files) await uploadFile(f)
  }, [uploadFile])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    const ws = new WebSocket(`ws://${location.host}/ws/chat`)
    wsRef.current = ws
    ws.onopen  = () => setConnected(true)
    ws.onclose = () => { setConnected(false); setTimeout(connect, 3000) }
    ws.onerror = () => setConnected(false)

    ws.onmessage = e => {
      try {
        const data = JSON.parse(e.data)
        switch (data.type) {
          case 'connected':
            setOllamaOk(data.ollama)
            break
          case 'context':
            setMessages(prev => [...prev,
              { id:Date.now(), role:'context', summary:data.summary }])
            break
          case 'clarify':
            setStreaming(false); streamRef.current = ''; setStreamBuf('')
            setMessages(prev => [...prev,
              { id:Date.now(), role:'assistant', content:data.message }])
            break
          case 'token':
            streamRef.current += data.content
            setStreamBuf(streamRef.current)
            break
          case 'done': {
            const final = streamRef.current
            streamRef.current = ''; setStreamBuf(''); setStreaming(false)
            if (final.trim())
              setMessages(prev => [...prev,
                { id:Date.now(), role:'assistant', content:final,
                  requestText: lastUserMessageRef.current,
                  model: modelRef.current,
                  genStartTime: genStartRef.current }])   // Milestone G: for benchmarking
            break
          }
          // Sprint 3: autonomous planner events
          case 'plan_start':
            setFileProgress(null)
            setReviewing({ agent: 'planner', message: data.message || 'Planning which files to change…' })
            break

          case 'plan_done': {
            setReviewing(null)
            // Insert plan card into messages
            setMessages(prev => [...prev, {
              id: Date.now(), role: 'plan',
              plan: data.plan, fileCount: data.file_count,
            }])
            break
          }

          case 'file_start': {
            setFileProgress({ file: data.file, index: data.index, total: data.total, editMode: data.edit_mode })
            const modeLabel = data.edit_mode === 'targeted' ? 'targeted edit' : 'full rewrite'
            setReviewing({ agent: 'coder',
              message: `Writing ${data.file} (${modeLabel}, ${data.index}/${data.total})…` })
            streamRef.current = ''; setStreamBuf('')
            break
          }

          case 'file_done':
            setReviewing(null)
            streamRef.current = ''; setStreamBuf('')
            break

          case 'all_done': {
            setReviewing(null)
            setFileProgress(null)
            setStreaming(false)
            streamRef.current = ''; setStreamBuf('')
            if (data.results?.length) {
              setMessages(prev => [...prev, {
                id:                 Date.now(),
                role:               'multi_file',
                results:            data.results,
                featureRequest:     data.feature_request     || '',
                consistencySummary: data.consistency_summary || '',
              }])
            }
            break
          }

          // Sprint 6: live inter-agent transparency — the actual reasoning
          // each agent produced, shown as an expandable card in the stream
          case 'agent_turn':
            setMessages(prev => [...prev, {
              id: Date.now() + Math.random(), role: 'agent_turn',
              agent: data.agent, file: data.file,
              summary: data.summary, content: data.content,
            }])
            break

          // Sprint 5: project memory confirmation
          case 'memory_stored':
            setMessages(prev => [...prev, {
              id: Date.now(), role: 'memory', message: data.message,
            }])
            break

          // Sprint 5: TDD cycle progress + result
          case 'tdd_step':
            setReviewing({ agent: 'coder', message: `🧪 ${data.message}` })
            break

          case 'tdd_done':
            setReviewing(null)
            setMessages(prev => [...prev, {
              id: Date.now(), role: 'tdd_result',
              testPath: data.test_path, implPath: data.impl_path,
              testCode: data.test_code, implCode: data.impl_code,
              passed: data.passed, attempts: data.attempts,
            }])
            break

          // Milestone D: show the planned agent pipeline before it runs
          case 'pipeline_plan':
            if (data.agents?.length > 1) {
              setReviewing({ agent: null, message: `Running ${data.agents.join(' → ')} (${data.estimate})…` })
            }
            break

          // Sprint 2: vibe coding mode — show what's being built
          case 'vibe_plan':
            setReviewing({ agent: 'coder', message:
              data.reference
                ? `✨ Vibe coding: ${data.component} (${data.reference} style)…`
                : `✨ Vibe coding: building ${data.component}…`
            })
            break
          // Milestone A: quality pipeline messages
          case 'reviewing':
            setReviewing({ agent: data.step, message: data.message || data.step })
            break
          // VS Code-style ReAct agent — live streaming
          case 'react_start':
            setReviewing({ agent: 'react', message: data.message || 'Agent started…' })
            setFileProgress(null)
            break
          case 'agent_thought':
            setReviewing({ agent: 'react', message: data.thought || 'Thinking…' })
            // also log as transient thought card
            setMessages(prev => [...prev, {
              id: Date.now() + Math.random(), role: 'agent_thought',
              thought: data.thought, iteration: data.iteration,
            }])
            break
          case 'tool_call':
            setReviewing({ agent: 'tool', message: `Running ${data.tool}…` })
            setMessages(prev => [...prev, {
              id: Date.now() + Math.random(), role: 'tool_call',
              tool: data.tool, args: data.args, thought: data.thought, callId: data.id,
            }])
            break
          case 'tool_result':
            setReviewing(null)
            setMessages(prev => [...prev, {
              id: Date.now() + Math.random(), role: 'tool_result',
              tool: data.tool, result: data.result, success: data.success, callId: data.id,
            }])
            break
          case 'react_done': {
            setReviewing(null)
            setFileProgress(null)
            setStreaming(false)
            streamRef.current = ''; setStreamBuf('')
            const answer = data.answer || ''
            if (answer.trim())
              setMessages(prev => [...prev, {
                id: Date.now(), role: 'assistant', content: answer,
                requestText: lastUserMessageRef.current,
                model: data.model || modelRef.current,
                filesChanged: data.files_changed || [],
              }])
            // if files changed, refresh explorer + current file
            if (data.files_changed?.length) {
              setTimeout(() => {
                // trigger a custom event that App.jsx can listen to for file tree refresh
                window.dispatchEvent(new CustomEvent('react-files-changed', { detail: data.files_changed }))
              }, 100)
            }
            break
          }
          case 'react_files_changed':
            // legacy compat — files were written, inform user
            setMessages(prev => [...prev, {
              id: Date.now(), role: 'tool_result',
              tool: 'write_file', result: `Files updated: ${(data.files||[]).join(', ')}`, success: true,
            }])
            break
          // Reliability fix: model's response got auto-reformatted into a proper code block
          case 'reformatted':
            setMessages(prev => {
              const copy = [...prev]
              for (let i = copy.length - 1; i >= 0; i--) {
                if (copy[i].role === 'assistant') {
                  copy[i] = { ...copy[i], content: data.full }
                  break
                }
              }
              return copy
            })
            break
          case 'format_warning':
            setReviewing(null)
            setMessages(prev => [...prev,
              { id:Date.now(), role:'error', content:data.message }])
            break
          case 'review_done': {
            setReviewing(null)
            // Attach review result to the last assistant message
            const { fixed_code, ...reviewData } = data
            setMessages(prev => {
              const copy = [...prev]
              for (let i = copy.length - 1; i >= 0; i--) {
                if (copy[i].role === 'assistant') {
                  copy[i] = {
                    ...copy[i],
                    review:    reviewData,
                    fixedCode: fixed_code ?? null,
                  }
                  break
                }
              }
              return copy
            })
            break
          }
          case 'error':
            streamRef.current = ''; setStreamBuf(''); setStreaming(false); setReviewing(null)
            setMessages(prev => [...prev,
              { id:Date.now(), role:'error', content:data.message }])
            break
        }
      } catch {}
    }
  }, [])

  useEffect(() => { connect(); return () => wsRef.current?.close() }, [connect])
  useEffect(() => { msgEndRef.current?.scrollIntoView({ behavior:'smooth' }) }, [messages, streamBuf, reviewing])

  // ── Send ──────────────────────────────────────────────────────────────────
  const send = useCallback((overrideInput) => {
    const text = (overrideInput ?? input).trim()
    if ((!text && attachments.length === 0) || streaming || wsRef.current?.readyState !== WebSocket.OPEN) return

    // Build display message — include attachment names for the chat log
    const displayContent = [
      text,
      ...attachments.map(a => `📎 ${a.name}`),
    ].filter(Boolean).join('\n')

    setMessages(prev => [...prev, { id:Date.now(), role:'user', content:displayContent }])
    if (!overrideInput) setInput('')
    setStreaming(true)
    streamRef.current = ''; setStreamBuf('')
    lastUserMessageRef.current = text || attachments.map(a => a.name).join(', ')
    genStartRef.current = Date.now()

    const history = messages
      .filter(m => m.role==='user' || m.role==='assistant')
      .map(m => ({ role:m.role, content:m.content }))

    const openTabPaths = openFiles.map(f => f.path).filter(p => p !== activeFile?.path)

    // Sprint 1: include attachments (strip base64 — server already has files)
    const attachmentPayload = attachments.map(a => ({
      type:        a.type,
      name:        a.name,
      text:        a.text       || '',
      description: a.description || '',
      server_path: a.server_path || '',
    }))

    wsRef.current.send(JSON.stringify({
      type:'chat', message:text, model,
      include_file: !!activeFile,          // Sprint 3: always include if a file is open
      file_path:    activeFile?.path    ?? '',
      file_content: activeFile?.content ?? '',
      language:     activeFile?.language ?? '',
      open_tabs:    openTabPaths,
      history,
      attachments: attachmentPayload,
    }))

    setAttachments([])   // clear after send
    inputRef.current?.focus()
  }, [input, attachments, streaming, model, activeFile, messages, openFiles])

  const onKeyDown = e => {
    if (e.key==='Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const canSend = connected && !streaming && (!!input.trim() || attachments.length > 0)

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div
      style={{ width:310, background:C.bgSide, flexShrink:0,
               display:'flex', flexDirection:'column',
               borderLeft:`1px solid ${C.border}`,
               outline: dragOver ? '2px dashed #7F77DD' : 'none',
               transition:'outline 0.1s',
      }}
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >

      {/* Header */}
      <div style={{ height:35, flexShrink:0, display:'flex', alignItems:'center',
                    padding:'0 12px', gap:8, borderBottom:`1px solid ${C.border}`,
                    userSelect:'none' }}>
        <span style={{ fontSize:11, fontWeight:600, letterSpacing:1.1, color:'#bbb' }}>
          AI ASSISTANT
        </span>
        <div style={{ flex:1 }} />
        {/* Milestone A: Templates button */}
        <button
          onClick={() => setShowTemplates(true)}
          title="Quick templates (Ctrl+K)"
          style={{ background:'none', border:`1px solid #3a3a3a`, color:C.textMuted,
                   fontSize:10, padding:'3px 8px', borderRadius:3,
                   cursor:'pointer', fontFamily:'inherit' }}
        >
          ⌘ Templates
        </button>
        <span title={!connected?'Disconnected':!ollamaOk?'Ollama not detected':'Connected'}
          style={{ width:7, height:7, borderRadius:'50%', flexShrink:0,
                   background:!connected?'#555':ollamaOk?'#73c991':'#e2c08d' }} />
      </div>

      {/* Model + include-file */}
      <div style={{ padding:'8px 12px', borderBottom:`1px solid ${C.border}`,
                    flexShrink:0, display:'flex', flexDirection:'column', gap:7 }}>
        <select value={model} onChange={e => setModel(e.target.value)} style={{
          width:'100%', background:'#2d2d2d', border:'1px solid #444',
          color:C.text, padding:'5px 8px', borderRadius:3,
          fontSize:11, fontFamily:'inherit', outline:'none', cursor:'pointer',
        }}>
          {models.length===0 && <option value={model}>{model}</option>}
          {models.map(m => (
            <option key={m} value={m}>
              {m === bestModel ? `⭐ ${m} (best for edits)` : m}
            </option>
          ))}
        </select>

        {activeFile && (
          <div style={{ fontSize:10, color:'#555', display:'flex', alignItems:'center', gap:5 }}>
            <span style={{ color:C.accent, fontSize:9 }}>●</span>
            <span>
              Active: <em style={{ fontStyle:'normal', color:C.textMuted }}>
                {activeFile.path.split('/').pop()}
              </em> — agent has full workspace tools (read, grep, run, write)
            </span>
          </div>
        )}
      </div>

      {/* Messages */}
      <div style={{ flex:1, overflow:'auto', padding:'10px 10px 4px',
                    display:'flex', flexDirection:'column', gap:8 }}>
        {messages.length===0 && !streaming && (
          <div style={{ textAlign:'center', padding:'24px 12px',
                        color:'#3a3a3a', fontSize:12, lineHeight:1.7 }}>
            <div style={{ fontSize:26, marginBottom:10, opacity:0.3 }}>⚡</div>
            {connected
              ? ollamaOk
                ? <>
              <span style={{ color:C.accent }}>Agent mode</span> — describe what to build/fix; the agent will explore, edit files, run tests, and self-correct like VS Code.<br/>
              Use <span style={{color:C.accent, cursor:'pointer'}}
                         onClick={() => setShowTemplates(true)}>⌘ Templates</span> for quick prompts.{' '}
              📎 Attach images, PDFs, or DOCX to chat.<br/>
              <span style={{color:'#7F77DD'}}>✨ Vibe:</span> paste a screenshot or describe a UI to build it.
            </>
                : <>Run <code style={{background:'#2a2a2a',padding:'1px 4px',
                                      borderRadius:2,color:'#e2c08d'}}>ollama serve</code></>
              : 'Connecting…'}
          </div>
        )}

        {messages.map(msg => {
          if (msg.role === 'context')
            return <ContextBadge key={msg.id} summary={msg.summary} />
          if (msg.role === 'regression')
            return <RegressionNote key={msg.id} regression={msg.regression} />
          // Sprint 3: plan card
          if (msg.role === 'plan')
            return <PlanView key={msg.id} plan={msg.plan} fileCount={msg.fileCount} />
          // Sprint 3+4: multi-file diff with atomic apply + consistency warnings
          if (msg.role === 'multi_file')
            return (
              <MultiFileResults
                key={msg.id}
                results={msg.results}
                featureRequest={msg.featureRequest}
                consistencySummary={msg.consistencySummary}
                onRefreshEditor={() => {
                  if (activeFile) {
                    fetch('/api/file?path=' + encodeURIComponent(activeFile.path))
                      .then(r => r.json())
                      .then(d => {
                        if (d.content !== undefined)
                          onApplyCode(activeFile.path, d.content)
                      }).catch(() => {})
                  }
                }}
              />
            )
          // Sprint 6: live agent transparency — expandable reasoning card
          if (msg.role === 'agent_turn')
            return (
              <AgentTurnCard key={msg.id}
                agent={msg.agent} file={msg.file}
                summary={msg.summary} content={msg.content} />
            )
          // Sprint 5: project memory confirmation pill
          if (msg.role === 'memory')
            return (
              <div key={msg.id} style={{
                alignSelf:'flex-start', fontSize:11, color:'#73c991',
                padding:'5px 10px', borderRadius:4,
                background:'#73c99110', border:'1px solid #73c99133',
              }}>
                {msg.message}
              </div>
            )
          // Sprint 5: TDD cycle result card
          if (msg.role === 'tdd_result')
            return (
              <div key={msg.id} style={{
                alignSelf:'flex-start', maxWidth:'97%', fontSize:12,
                border:`1px solid ${msg.passed ? '#73c99144' : '#e2c08d44'}`,
                borderRadius:6, overflow:'hidden',
                background: msg.passed ? '#1e2a1e' : '#1e1e1e',
              }}>
                <div style={{
                  padding:'8px 12px', background: msg.passed ? '#73c99110' : '#e2c08d10',
                  borderBottom:'1px solid #2a2a2a', display:'flex', alignItems:'center', gap:8,
                }}>
                  <span>{msg.passed ? '✅' : '⚠️'}</span>
                  <span style={{ fontWeight:500, color: msg.passed ? '#73c991' : '#e2c08d' }}>
                    TDD cycle — {msg.passed ? 'tests passing' : `still failing after ${msg.attempts} attempts`}
                  </span>
                </div>
                <div style={{ padding:'8px 12px', display:'flex', flexDirection:'column', gap:6 }}>
                  <div style={{ fontSize:11, color:'#888' }}>
                    🧪 <code>{msg.testPath}</code> + ✏️ <code>{msg.implPath}</code>
                  </div>
                  <div style={{ display:'flex', gap:6 }}>
                    <button onClick={() => setApplyModal({
                      code: msg.testCode, lang: activeFile?.language || 'python',
                      originalContent: '',
                    })} style={{
                      background:`${C.accent}18`, border:`1px solid ${C.accent}44`, color:C.accent,
                      padding:'3px 10px', borderRadius:3, cursor:'pointer', fontSize:10, fontFamily:'inherit',
                    }}>Review test file</button>
                    <button onClick={() => setApplyModal({
                      code: msg.implCode, lang: activeFile?.language || 'python',
                      originalContent: '',
                    })} style={{
                      background:'#73c99118', border:'1px solid #73c99144', color:'#73c991',
                      padding:'3px 10px', borderRadius:3, cursor:'pointer', fontSize:10, fontFamily:'inherit',
                    }}>Review implementation</button>
                  </div>
                </div>
              </div>
            )
          // VS Code-style ReAct: thought
          if (msg.role === 'agent_thought')
            return (
              <div key={msg.id} style={{
                alignSelf:'flex-start', maxWidth:'96%', fontSize:11,
                color:'#858585', fontStyle:'italic',
                padding:'4px 8px', borderLeft:'2px solid #3a3a3a',
                background:'#1a1a1a', borderRadius:2,
              }}>
                <span style={{ color:'#569cd6', fontWeight:600, fontStyle:'normal' }}>💭 Thought</span>
                <span style={{ marginLeft:6 }}>{msg.thought}</span>
                {msg.iteration && <span style={{ color:'#555', marginLeft:8 }}>· step {msg.iteration}</span>}
              </div>
            )
          // Tool call card
          if (msg.role === 'tool_call')
            return (
              <div key={msg.id} style={{
                alignSelf:'flex-start', maxWidth:'96%', fontSize:11,
                background:'#0f1a2a', border:'1px solid #1e3a5f', borderRadius:4,
                padding:'7px 10px', fontFamily:"'Cascadia Code',monospace",
              }}>
                <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:4 }}>
                  <span style={{ color:'#4fc1ff', fontWeight:600 }}>🔧 {msg.tool}</span>
                  {msg.thought && <span style={{ color:'#888', fontFamily:'inherit', fontSize:10, fontStyle:'italic' }}>— {msg.thought}</span>}
                </div>
                <div style={{ color:'#858585', fontSize:10, whiteSpace:'pre-wrap', wordBreak:'break-all', background:'#0a0a0a', padding:'6px 8px', borderRadius:3, border:'1px solid #1e1e1e' }}>
                  {Object.entries(msg.args || {}).map(([k,v]) => `${k}: ${String(v).slice(0,800)}`).join('\n') || '(no args)'}
                </div>
              </div>
            )
          // Tool result card
          if (msg.role === 'tool_result')
            return (
              <div key={msg.id} style={{
                alignSelf:'flex-start', maxWidth:'96%', fontSize:11,
                background: msg.success ? '#0f1f0f' : '#1f0f0f',
                border: `1px solid ${msg.success ? '#73c99133' : '#f4877133'}`,
                borderRadius:4, padding:'7px 10px',
              }}>
                <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:4 }}>
                  <span style={{ color: msg.success ? '#73c991' : '#f48771', fontWeight:600, fontSize:10 }}>
                    {msg.success ? '✓' : '✗'} {msg.tool} {msg.success ? 'result' : 'failed'}
                  </span>
                  <span style={{ color:'#555', fontSize:9 }}>#{msg.callId}</span>
                </div>
                <pre style={{
                  margin:0, whiteSpace:'pre-wrap', wordBreak:'break-all',
                  maxHeight:220, overflow:'auto',
                  fontSize:10, lineHeight:1.5, color:'#bbb',
                  background:'#0a0a0a', padding:'6px 8px', borderRadius:3, border:'1px solid #1e1e1e',
                  fontFamily:"'Cascadia Code','Fira Code',monospace",
                }}>
                  {String(msg.result || '').slice(0,4000)}
                </pre>
              </div>
            )
          return (
            <Bubble key={msg.id} msg={msg} activeFile={activeFile}
              onApply={(code, lang, orig) =>
                setApplyModal({
                  code, lang, originalContent: orig ?? '',
                  review:     msg.review || null,
                  model:      msg.model || model,
                  taskType:   msg.review?.intent || 'edit',
                  durationMs: msg.genStartTime ? Date.now() - msg.genStartTime : 0,
                })}
              onSaveAs={(code, lang) => {
                const base = activeFile?.path?.split('/').slice(0, -1).join('/') ?? ''
                const stem = activeFile?.path?.split('/').pop()?.replace(/\.\w+$/, '') ?? 'new_file'
                const ext  = lang === 'python' ? '.py' : lang === 'javascript' ? '.js' :
                             lang === 'typescript' ? '.ts' : ''
                const suggested = base ? `${base}/test_${stem}${ext}` : `test_${stem}${ext}`
                setSaveAsModal({ code, lang, suggestedPath: suggested })
              }} />
          )
        })}

        {/* Streaming bubble */}
        {/* Sprint 3+6: per-file progress indicator with edit-mode badge */}
        {fileProgress && streaming && (
          <div style={{
            alignSelf:'flex-start', fontSize:10, color:'#4fc1ff',
            display:'flex', alignItems:'center', gap:7,
            padding:'4px 8px', borderRadius:4,
            background:'#4fc1ff10', border:'1px solid #4fc1ff30',
          }}>
            <span>📄</span>
            <span>
              Writing{' '}
              <code style={{ color:'#fff', fontFamily:"'Cascadia Code',monospace" }}>
                {fileProgress.file.split('/').pop()}
              </code>
              {' '}({fileProgress.index}/{fileProgress.total})
            </span>
            {fileProgress.editMode && (
              <span style={{
                fontSize:9, padding:'1px 6px', borderRadius:8,
                background: fileProgress.editMode === 'targeted' ? '#73c99118' : '#e2c08d18',
                color:      fileProgress.editMode === 'targeted' ? '#73c991' : '#e2c08d',
                border: `1px solid ${fileProgress.editMode === 'targeted' ? '#73c99144' : '#e2c08d44'}`,
              }}>
                {fileProgress.editMode === 'targeted' ? '✎ targeted' : '⟳ full rewrite'}
              </span>
            )}
          </div>
        )}

        {streaming && (
          <div style={{ alignSelf:'flex-start', maxWidth:'96%' }}>
            <div style={{ fontSize:10, color:'#555', marginBottom:3, paddingLeft:2 }}>Assistant</div>
            <div style={{ background:'#2a2a2a', border:'1px solid #3a3a3a',
                          borderRadius:'2px 12px 12px 12px',
                          padding:'8px 11px', fontSize:12, lineHeight:1.7,
                          color:C.text, whiteSpace:'pre-wrap', wordBreak:'break-word',
                          minHeight:36, minWidth:60 }}>
              {streamBuf || <Dots />}
            </div>
          </div>
        )}

        {/* Sprint 6: live working-state indicator with pulsing signal dot */}
        {reviewing && (
          <WorkingState agent={reviewing.agent} message={reviewing.message} />
        )}

        <div ref={msgEndRef} />
      </div>

      {/* Milestone G: Autonomous improvement suggestion card */}
      {suggestion && (
        <div style={{
          margin:'0 10px 8px', padding:'9px 12px',
          background:'#c586c012', border:'1px solid #c586c044', borderRadius:5,
          fontSize:11, flexShrink:0,
        }}>
          <div style={{ color:'#c586c0', fontWeight:500, marginBottom:5 }}>
            💡 Learning suggestion
          </div>
          <div style={{ color:'#bbb', lineHeight:1.6, marginBottom:8 }}>
            I've noticed you consistently prefer to <strong style={{ color:'#fff' }}>
              {suggestion.label}
            </strong>. Want me to always remember this for{' '}
            <code style={{ background:'#2a2a2a', padding:'0 4px', borderRadius:2 }}>
              {suggestion.language}
            </code>?
          </div>
          <div style={{ display:'flex', gap:6 }}>
            <button
              onClick={() => {
                fetch('/api/preferences/suggestion/seen', {
                  method:'POST', headers:{'Content-Type':'application/json'},
                  body: JSON.stringify({ signal: suggestion.signal, language: suggestion.language }),
                }).catch(() => {})
                setSuggestion(null)
              }}
              style={{
                background:'#c586c022', border:'1px solid #c586c055',
                color:'#c586c0', padding:'3px 10px', borderRadius:3,
                cursor:'pointer', fontSize:10, fontFamily:'inherit',
              }}
            >
              Got it ✓
            </button>
            <button
              onClick={() => {
                fetch('/api/preferences/suggestion/seen', {
                  method:'POST', headers:{'Content-Type':'application/json'},
                  body: JSON.stringify({ signal: suggestion.signal, language: suggestion.language }),
                }).catch(() => {})
                setSuggestion(null)
              }}
              style={{
                background:'transparent', border:'1px solid #3a3a3a',
                color:'#555', padding:'3px 10px', borderRadius:3,
                cursor:'pointer', fontSize:10, fontFamily:'inherit',
              }}
            >
              Skip
            </button>
          </div>
        </div>
      )}

      {/* Input */}
      <div style={{ padding:'10px 10px 12px', borderTop:`1px solid ${C.border}`, flexShrink:0 }}>

        {/* Sprint 1: attachment pills row */}
        {attachments.length > 0 && (
          <div style={{ display:'flex', flexWrap:'wrap', gap:5, marginBottom:7 }}>
            {attachments.map((att, i) => (
              <AttachmentPill
                key={i} attachment={att}
                onRemove={() => setAttachments(prev => prev.filter((_, j) => j !== i))}
              />
            ))}
          </div>
        )}

        {/* Sprint 1: uploading indicator */}
        {uploading && (
          <div style={{ fontSize:10, color:'#7F77DD', marginBottom:6, display:'flex', gap:5, alignItems:'center' }}>
            <Dots />
            <span>Reading file…</span>
          </div>
        )}

        {/* Sprint 1: drag-drop hint when dragging over */}
        {dragOver && (
          <div style={{
            position:'absolute', inset:0, zIndex:10,
            background:'#7F77DD18', border:'2px dashed #7F77DD',
            borderRadius:4, display:'flex', alignItems:'center',
            justifyContent:'center', pointerEvents:'none',
          }}>
            <span style={{ fontSize:14, color:'#7F77DD', fontWeight:500 }}>
              Drop file to attach
            </span>
          </div>
        )}

        <div style={{ display:'flex', gap:6, alignItems:'flex-end' }}>

          {/* Sprint 1: hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            style={{ display:'none' }}
            accept=".png,.jpg,.jpeg,.webp,.gif,.bmp,.pdf,.docx,.doc,.csv,.json,.txt,.md"
            multiple
            onChange={async e => {
              for (const f of e.target.files) await uploadFile(f)
              e.target.value = ''
            }}
          />

          {/* Sprint 1: paperclip button */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={!connected || streaming || uploading}
            title="Attach file (or paste/drag an image)"
            style={{
              background:'none', border:`1px solid #3a3a3a`,
              color: uploading ? '#555' : C.textMuted,
              padding:'7px 9px', borderRadius:4, fontSize:14,
              cursor: connected && !streaming && !uploading ? 'pointer' : 'default',
              flexShrink:0, lineHeight:1,
            }}
          >
            📎
          </button>

          <textarea ref={inputRef} value={input}
            onChange={e => setInput(e.target.value)} onKeyDown={onKeyDown}
            disabled={!connected||streaming}
            placeholder={!connected?'Connecting…':streaming?'Waiting…':
              attachments.length > 0 ? 'Describe the file or ask a question…' :
              'Ask… or paste/drag a file  (Enter ↵)'}
            rows={2}
            style={{ flex:1, background:'#222', border:'1px solid #3a3a3a',
                     color:C.text, padding:'7px 10px', borderRadius:4, fontSize:12,
                     fontFamily:'inherit', outline:'none', resize:'none', lineHeight:1.5,
                     opacity:(!connected||streaming)?0.45:1 }}
            onFocus={e => e.target.style.borderColor='#555'}
            onBlur={e  => e.target.style.borderColor='#3a3a3a'} />
          <button onClick={() => send()} disabled={!canSend} style={{
            background:canSend?C.accent:'#2a2a2a',
            border:'none', color:canSend?'#fff':'#444',
            padding:'10px 12px', borderRadius:4, fontSize:16, flexShrink:0,
            cursor:canSend?'pointer':'default', transition:'background 0.1s',
          }}>↑</button>
        </div>
        {connected && !ollamaOk && (
          <div style={{ fontSize:10, color:'#e2c08d', marginTop:6 }}>
            ⚠ Run <code style={{background:'#2a2a2a',padding:'0 4px',borderRadius:2}}>
              ollama serve</code>
          </div>
        )}
      </div>

      {/* Diff viewer */}
      {applyModal && activeFile && (
        <DiffViewer
          path={activeFile.path}
          originalContent={applyModal.originalContent}
          proposedContent={applyModal.code}
          language={applyModal.lang || activeFile.language || ''}
          review={applyModal.review}
          onApply={async () => {
            const lang = applyModal.lang || activeFile.language || ''
            // Milestone C+G: record acceptance signal + feed model benchmarking
            const outcome = applyModal.review?.revised ? 'revised' : 'accept'
            fetch('/api/preferences/record', {
              method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify({
                proposed: applyModal.code, language: lang, outcome,
                model: applyModal.model || '', task_type: applyModal.taskType || 'edit',
                duration_ms: applyModal.durationMs || 0,
              }),
            }).catch(() => {})

            const result = await onApplyCode(activeFile.path, applyModal.code)
            if (result?.regression) {
              setMessages(prev => [...prev,
                { id: Date.now(), role:'regression', regression: result.regression }])
            }
            setApplyModal(null)
            // Milestone G: check if a new improvement suggestion is ready
            fetch('/api/preferences/suggestion')
              .then(r => r.json())
              .then(d => { if (d.suggestion) setSuggestion(d.suggestion) })
              .catch(() => {})
          }}
          onClose={() => {
            // Milestone C+G: record rejection signal + feed model benchmarking
            const lang = applyModal.lang || activeFile.language || ''
            fetch('/api/preferences/record', {
              method:'POST', headers:{'Content-Type':'application/json'},
              body: JSON.stringify({
                proposed: applyModal.code, language: lang, outcome:'reject',
                model: applyModal.model || '', task_type: applyModal.taskType || 'edit',
                duration_ms: applyModal.durationMs || 0,
              }),
            }).catch(() => {})
            setApplyModal(null)
          }}
        />
      )}

      {/* Milestone C: Save as new file modal */}
      {saveAsModal && (
        <SaveAsModal
          suggestedPath={saveAsModal.suggestedPath}
          code={saveAsModal.code}
          lang={saveAsModal.lang}
          onCreate={async (path, code) => { await onCreateFile(path, code) }}
          onClose={() => setSaveAsModal(null)}
        />
      )}

      {/* Milestone A: Templates picker */}
      {showTemplates && (
        <TemplatesPicker
          onSelect={prompt => { setInput(prompt); setTimeout(() => inputRef.current?.focus(), 50) }}
          onClose={() => setShowTemplates(false)}
        />
      )}
    </div>
  )
}
