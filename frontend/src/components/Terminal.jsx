import { useState, useEffect, useRef, useCallback } from 'react'
import { C } from '../App'

// Languages that have a runner configured on the backend
const RUNNABLE = new Set(['python','javascript','typescript','shell','bat','go'])

// Line type → display colour
const LINE_COLOR = {
  cmd:      '#858585',   // $ prompt line
  stdout:   '#cccccc',
  stderr:   '#f48771',
  step:     '#569cd6',   // agent thinking
  fix:      '#dcdcaa',   // fix applied
  success:  '#73c991',
  error:    '#f48771',
  diagnosis:'#c586c0',   // Milestone F: self-diagnosis / strategy switch
}

// A single terminal output line
function Line({ line }) {
  const color = LINE_COLOR[line.kind] ?? '#cccccc'
  const prefix =
    line.kind === 'step'    ? '  ' :
    line.kind === 'fix'     ? '  ' :
    line.kind === 'success' ? '  ' :
    line.kind === 'error'   ? '  ' :
    line.kind === 'stderr'  ? '  ' : ''

  return (
    <div style={{
      color,
      fontFamily:"'Cascadia Code','Fira Code',Consolas,monospace",
      fontSize:12, lineHeight:1.65, whiteSpace:'pre-wrap', wordBreak:'break-all',
    }}>
      {prefix}{line.text}
    </div>
  )
}

// Small animated spinner
function Spinner() {
  const frames = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']
  const [f, setF] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setF(n => (n+1) % frames.length), 80)
    return () => clearInterval(t)
  }, [])
  return <span style={{ color:'#569cd6', fontSize:11 }}>{frames[f]}</span>
}

export default function Terminal({
  visible, workspace, activeFile, onToggle,
  autoRunPath, onAutoRunHandled,   // Milestone C: auto-run newly created test files
}) {
  const [lines,     setLines]     = useState([])
  const [running,   setRunning]   = useState(false)
  const [connected, setConnected] = useState(false)
  const [model,     setModel]     = useState('deepseek-coder:6.7b')

  const wsRef     = useRef(null)
  const bottomRef = useRef(null)

  // ── Connect to /ws/run ────────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    const ws = new WebSocket(`ws://${location.host}/ws/run`)
    wsRef.current = ws

    ws.onopen  = () => setConnected(true)
    ws.onclose = () => { setConnected(false); setTimeout(connect, 3000) }
    ws.onerror = () => setConnected(false)

    ws.onmessage = e => {
      try { handleMsg(JSON.parse(e.data)) } catch {}
    }
  }, []) // eslint-disable-line

  useEffect(() => {
    connect()
    return () => wsRef.current?.close()
  }, [connect])

  // ── Auto-scroll ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (visible) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines, visible])

  // ── Handle incoming WS events ─────────────────────────────────────────────
  const handleMsg = (data) => {
    switch (data.type) {
      case 'connected':
        break   // nothing to show

      case 'agent_step':
        push(data.thought, 'step')
        break

      case 'run_result': {
        const outLines = (data.stdout || '').trimEnd().split('\n').filter(Boolean)
        const errLines = (data.stderr || '').trimEnd().split('\n').filter(Boolean)
        outLines.forEach(l => push(l, 'stdout'))
        errLines.forEach(l => push(l, 'stderr'))
        if (data.sandboxed === 'docker') push('🐳 ran inside Docker sandbox', 'step')
        break
      }

      // Milestone F: self-diagnosis — loop detected, strategy switched
      case 'self_diagnosis':
        push(`🔄 ${data.message}`, 'diagnosis')
        break

      case 'agent_fix_applied':
        push(data.message, 'fix')
        break

      case 'agent_done':
        push(data.message, data.success ? 'success' : 'error')
        setRunning(false)
        break

      case 'error':
        push(data.message, 'error')
        setRunning(false)
        break
    }
  }

  const push = (text, kind) =>
    setLines(prev => [...prev, { id: Date.now() + Math.random(), text, kind }])

  // ── Run actions ───────────────────────────────────────────────────────────
  const runFile = (autoFix = false) => {
    if (!activeFile || !connected || running) return
    setRunning(true)
    const label = autoFix ? 'Run & Fix' : 'Run'
    push(`$ ${label}: ${activeFile.path}`, 'cmd')
    wsRef.current.send(JSON.stringify({
      type:         'run',
      file_path:    activeFile.path,
      language:     activeFile.language,
      auto_fix:     autoFix,
      model,
      max_attempts: 3,
    }))
  }

  const clear = () => setLines([])

  // Milestone C: auto-run when a new test file is created from chat
  useEffect(() => {
    if (!autoRunPath || !connected) return
    if (activeFile?.path !== autoRunPath) return
    push(`$ Auto-running new test file…`, 'cmd')
    runFile(false)
    onAutoRunHandled?.()
  }, [autoRunPath, connected, activeFile]) // eslint-disable-line

  const canRun = connected && !!activeFile
                 && RUNNABLE.has(activeFile?.language)
                 && !running

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{
      background: '#161616', flexShrink:0, overflow:'hidden',
      borderTop:`1px solid ${C.border}`,
      height: visible ? 200 : 30,
      display:'flex', flexDirection:'column',
      transition:'height 0.15s ease',
    }}>
      {/* ── Tab / toolbar ──────────────────────────────────────────────────── */}
      <div style={{
        height:30, flexShrink:0,
        background:'#2d2d2d', display:'flex', alignItems:'center',
        padding:'0 8px', gap:6,
        borderBottom: visible ? `1px solid ${C.border}` : 'none',
        userSelect:'none',
      }}>
        {/* Toggle */}
        <button
          onClick={onToggle}
          style={btnStyle(false)}
        >
          <span style={{ fontSize:8, opacity:0.6 }}>{visible ? '▾' : '▸'}</span>
          TERMINAL
        </button>

        <div style={{ width:1, height:14, background:'#3c3c3c', flexShrink:0 }} />

        {/* Run */}
        <button
          onClick={() => runFile(false)}
          disabled={!canRun}
          title={canRun ? `Run ${activeFile?.path.split('/').pop()}` : 'Open a runnable file first'}
          style={btnStyle(canRun, '#73c991')}
        >
          ▶ Run
        </button>

        {/* Run & Fix */}
        <button
          onClick={() => runFile(true)}
          disabled={!canRun}
          title="Run and auto-fix errors with AI"
          style={btnStyle(canRun, '#569cd6')}
        >
          ▶ Run & Fix
        </button>

        {/* Model picker for fix */}
        <select
          value={model}
          onChange={e => setModel(e.target.value)}
          title="Model used for auto-fix"
          style={{
            background:'#1e1e1e', border:`1px solid #3a3a3a`,
            color:'#858585', fontSize:10, padding:'2px 5px',
            borderRadius:3, fontFamily:'inherit', outline:'none',
            cursor:'pointer', maxWidth:130,
          }}
        >
          {[
            'deepseek-coder:6.7b',
            'qwen3:8b',
            'qwen3:4b',
            'qwen2.5:1.5b',
            'artifish/llama3.2-uncensored:latest',
          ].map(m => <option key={m} value={m}>{m}</option>)}
        </select>

        <div style={{ flex:1 }} />

        {/* Running indicator */}
        {running && (
          <span style={{ display:'flex', alignItems:'center', gap:4, fontSize:11, color:'#569cd6' }}>
            <Spinner /> running…
          </span>
        )}

        {/* Active file name */}
        {activeFile && RUNNABLE.has(activeFile.language) && (
          <span style={{ fontSize:10, color:'#555',
                         fontFamily:"Consolas,monospace", maxWidth:220,
                         overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {activeFile.path}
          </span>
        )}

        {/* Clear */}
        {lines.length > 0 && (
          <button
            onClick={clear}
            title="Clear output"
            style={{ ...btnStyle(true), marginLeft:4 }}
          >
            ✕
          </button>
        )}

        {/* Connection dot */}
        <span
          title={connected ? 'Connected to run server' : 'Disconnected'}
          style={{
            width:6, height:6, borderRadius:'50%', flexShrink:0,
            background: connected ? '#73c991' : '#555',
          }}
        />
      </div>

      {/* ── Output area ────────────────────────────────────────────────────── */}
      {visible && (
        <div style={{
          flex:1, overflow:'auto', padding:'8px 14px',
          display:'flex', flexDirection:'column', gap:1,
        }}>
          {lines.length === 0 ? (
            <div style={{
              color:'#3a3a3a', fontSize:12, marginTop:4,
              fontFamily:"'Cascadia Code',Consolas,monospace",
            }}>
              {canRun
                ? `$ ready — click ▶ Run or ▶ Run & Fix`
                : activeFile
                ? `$ ${activeFile.language} is not runnable in this IDE yet`
                : '$ open a file to run it'}
            </div>
          ) : (
            lines.map(line => <Line key={line.id} line={line} />)
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}

function btnStyle(active, hoverColor) {
  return {
    background:'none', border:'none',
    color: active ? '#cccccc' : '#444',
    cursor: active ? 'pointer' : 'default',
    display:'flex', alignItems:'center', gap:4,
    padding:'4px 7px', borderRadius:3,
    fontSize:11, fontFamily:'inherit',
    transition:'color 0.1s',
    ...(active && hoverColor
      ? { ':hover': { color: hoverColor } }   // note: inline :hover won't work — see note
      : {}),
  }
}
