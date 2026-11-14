import { useState, useEffect, useCallback } from 'react'
import FileTree    from './components/FileTree'
import Editor      from './components/Editor'
import ChatPanel   from './components/ChatPanel'
import Terminal    from './components/Terminal'
import UndoHistory  from './components/UndoHistory'
import SkillManager     from './components/SkillManager'
import CheckpointBrowser from './components/CheckpointBrowser'
import AgentTrace        from './components/AgentTrace'
import SessionTimeline   from './components/SessionTimeline'
import CodeSearch        from './components/CodeSearch'
import TodoResolver       from './components/TodoResolver'
import ProjectMemoryPanel from './components/ProjectMemoryPanel'
import ToolsMenu          from './components/ToolsMenu'
import WorkspaceIntelligence from './components/WorkspaceIntelligence'

// ── VS Code dark+ colour tokens ───────────────────────────────────────────────
export const C = {
  // Deep cool-slate surfaces — not flat VS Code gray, has a blue undertone
  bg:          '#0a0c11',
  bgSide:      '#0f1218',
  bgTab:       '#141822',
  bgHeader:    '#0d0f15',
  bgHover:     '#1a1f29',
  bgSelected:  '#16233a',
  border:      '#1b1f2a',
  borderLight: '#272c3a',
  text:        '#e6e8ec',
  textMuted:   '#6b7280',
  textActive:  '#ffffff',
  // Signature "signal" accent — a live cyan-teal, distinct from generic
  // corporate blue and standing in for "the AI is active right now"
  accent:      '#22d3d8',
  accentHov:   '#4fe4e8',
  modified:    '#e2c08d',
  errorText:   '#f48771',
  success:     '#73c991',
}

export default function App() {
  // ── State ──────────────────────────────────────────────────────────────────
  const [workspace,    setWorkspace]    = useState(null)
  const [tree,         setTree]         = useState(null)
  const [openFiles,    setOpenFiles]    = useState([])
  const [activeTab,    setActiveTab]    = useState(null)
  const [termOpen,     setTermOpen]     = useState(true)
  const [modal,        setModal]        = useState(false)
  const [folderInput,  setFolderInput]  = useState('')
  const [modalErr,     setModalErr]     = useState('')
  const [modalLoading, setModalLoading] = useState(false)
  const [ragStatus,    setRagStatus]    = useState({ status: 'idle', total: 0, done: 0 })
  const [showHistory,  setShowHistory]  = useState(false)
  const [showSkills,   setShowSkills]   = useState(false)
  const [showCheckpoints, setShowCheckpoints] = useState(false)
  const [showAgentLog, setShowAgentLog] = useState(false)
  const [showSession,    setShowSession]    = useState(false)
  const [showCodeSearch, setShowCodeSearch] = useState(false)
  const [showTodos,      setShowTodos]      = useState(false)
  const [showMemory,     setShowMemory]     = useState(false)
  const [showWorkspaceIntel, setShowWorkspaceIntel] = useState(false)
  const [pendingPrompt,  setPendingPrompt]  = useState(null) // Sprint 5: bridge to ChatPanel input
  const [autoRunPath,  setAutoRunPath]  = useState(null)

  // ── Bootstrap ─────────────────────────────────────────────────────────────
  useEffect(() => {
    fetch('/api/workspace')
      .then(r => r.json())
      .then(d => { if (d.workspace) { setWorkspace(d); loadTree() } })
      .catch(() => {})
  }, []) // eslint-disable-line

  // ── RAG index status polling (Phase 4) ────────────────────────────────────
  useEffect(() => {
    if (!workspace) return
    const poll = setInterval(() => {
      fetch('/api/rag/status').then(r => r.json()).then(d => {
        setRagStatus(d)
        if (d.status === 'ready' || d.status === 'error' || d.status === 'idle')
          clearInterval(poll)
      }).catch(() => {})
    }, 1500)
    return () => clearInterval(poll)
  }, [workspace])

  // ── File tree ─────────────────────────────────────────────────────────────
  const loadTree = useCallback(async () => {
    try {
      const r = await fetch('/api/files')
      if (r.ok) setTree(await r.json())
    } catch {}
  }, [])

  // VS Code-style agent: refresh tree + open files when agent writes files
  useEffect(() => {
    const h = (e) => {
      loadTree()
      // reload open tabs that were changed
      const changed = e.detail || []
      changed.forEach(path => {
        fetch('/api/file?path=' + encodeURIComponent(path))
          .then(r => r.json())
          .then(d => {
            if (d.content !== undefined) {
              setOpenFiles(prev => prev.map(f => f.path === path ? { ...f, content: d.content, modified: false, version: (f.version ?? 0) + 1 } : f))
            }
          }).catch(() => {})
      })
    }
    window.addEventListener('react-files-changed', h)
    return () => window.removeEventListener('react-files-changed', h)
  }, [loadTree])

  // ── Open folder ───────────────────────────────────────────────────────────
  const handleOpenWorkspace = async () => {
    const path = folderInput.trim()
    if (!path) { setModalErr('Please enter a folder path.'); return }
    setModalErr(''); setModalLoading(true)
    try {
      const r = await fetch('/api/workspace/set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path }),
      })
      const d = await r.json()
      if (!r.ok) { setModalErr(d.detail || 'Failed.'); return }
      setWorkspace(d); setModal(false); setFolderInput('')
      setOpenFiles([]); setActiveTab(null)
      setRagStatus({ status: 'idle', total: 0, done: 0 })
      loadTree()
    } catch (e) { setModalErr(String(e)) }
    finally { setModalLoading(false) }
  }

  // ── Open file into tab ────────────────────────────────────────────────────
  const handleOpenFile = useCallback(async (path) => {
    if (openFiles.find(f => f.path === path)) { setActiveTab(path); return }
    try {
      const r = await fetch('/api/file?path=' + encodeURIComponent(path))
      if (!r.ok) return
      const d = await r.json()
      setOpenFiles(prev => [...prev,
        { path, content: d.content, language: d.language, modified: false, version: 0 }])
      setActiveTab(path)
    } catch {}
  }, [openFiles])

  // ── Close tab ─────────────────────────────────────────────────────────────
  const handleCloseTab = (path, e) => {
    e?.stopPropagation()
    const idx  = openFiles.findIndex(f => f.path === path)
    const next = openFiles.filter(f => f.path !== path)
    setOpenFiles(next)
    if (activeTab === path)
      setActiveTab(next[Math.min(idx, next.length - 1)]?.path ?? null)
  }

  // ── Track edits ───────────────────────────────────────────────────────────
  const handleContentChange = (path, content) => {
    setOpenFiles(prev => prev.map(f => f.path === path ? { ...f, content, modified: true } : f))
  }

  // ── Ctrl+S save (no history — manual saves aren't recorded) ──────────────
  const handleSave = useCallback(async (path) => {
    const file = openFiles.find(f => f.path === path)
    if (!file?.modified) return
    try {
      await fetch('/api/file/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, content: file.content }),
      })
      setOpenFiles(prev => prev.map(f => f.path === path ? { ...f, modified: false } : f))
    } catch {}
  }, [openFiles])

  // ── Apply AI code (Phase 2+6, Milestone C) — records history + returns regression info
  const handleApplyCode = useCallback(async (path, newContent) => {
    const file = openFiles.find(f => f.path === path)
    setOpenFiles(prev => prev.map(f =>
      f.path === path
        ? { ...f, content: newContent, modified: false, version: (f.version ?? 0) + 1 }
        : f
    ))
    try {
      const r = await fetch('/api/file/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path, content: newContent,
          source: 'ai', description: 'Applied from AI chat',
          language: file?.language ?? '',
        }),
      })
      return await r.json()   // { ok, path, regression }
    } catch {
      return null
    }
  }, [openFiles])

  // ── Create a brand-new file from AI chat (Milestone C) ────────────────────
  const handleCreateFile = useCallback(async (path, content) => {
    const r1 = await fetch('/api/file/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, is_dir: false }),
    })
    if (!r1.ok) {
      const d = await r1.json().catch(() => ({}))
      throw new Error(d.detail || 'Could not create file.')
    }
    const r2 = await fetch('/api/file/write', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, content, source: 'ai', description: 'Created from AI chat' }),
    })
    const result = await r2.json().catch(() => ({}))

    // Open it as a new tab
    const fr = await fetch('/api/file?path=' + encodeURIComponent(path))
    if (fr.ok) {
      const d = await fr.json()
      setOpenFiles(prev => [...prev,
        { path, content: d.content, language: d.language, modified: false, version: 0 }])
      setActiveTab(path)
    }

    // If it looks like a test file, auto-trigger a run in the Terminal
    if (/test_|\.test\.|__tests__/.test(path)) {
      setAutoRunPath(path)
    }
    return result
  }, [])

  // ── Revert file after undo (Phase 6) ─────────────────────────────────────
  const handleRevertFile = useCallback(async (filePath) => {
    try {
      const r = await fetch('/api/file?path=' + encodeURIComponent(filePath))
      if (!r.ok) return
      const d = await r.json()
      setOpenFiles(prev => prev.map(f =>
        f.path === filePath
          ? { ...f, content: d.content, modified: false, version: (f.version ?? 0) + 1 }
          : f
      ))
    } catch {}
  }, [])

  // ── Escape closes modal ───────────────────────────────────────────────────
  useEffect(() => {
    if (!modal) return
    const h = e => { if (e.key === 'Escape') { setModal(false); setModalErr('') } }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [modal])

  const activeFile = openFiles.find(f => f.path === activeTab) ?? null

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display:'flex', flexDirection:'column', height:'100vh',
                  background:C.bg, color:C.text, overflow:'hidden' }}>

      {/* ── Title bar ──────────────────────────────────────────────────────── */}
      <div style={{ height:38, background:C.bgHeader, flexShrink:0,
                    display:'flex', alignItems:'center', padding:'0 12px', gap:10,
                    borderBottom:`1px solid ${C.border}`, userSelect:'none' }}>
        <span style={{ fontSize:14, fontWeight:600 }}>⚡</span>
        <span style={{ fontSize:13, fontWeight:500 }}>Mini IDE</span>
        {workspace && (
          <span style={{ fontSize:12, color:C.textMuted }}>— {workspace.name}</span>
        )}
        {/* RAG status pill */}
        {workspace && ragStatus.status !== 'idle' && (
          <span style={{
            fontSize:9, fontWeight:600, letterSpacing:0.6,
            padding:'2px 7px', borderRadius:10, marginLeft:2,
            background: ragStatus.status==='ready' ? '#73c99122' :
                        ragStatus.status==='error'  ? '#f4877122' : '#e2c08d22',
            color:      ragStatus.status==='ready' ? '#73c991' :
                        ragStatus.status==='error'  ? '#f48771' : '#e2c08d',
            border:     ragStatus.status==='ready' ? '1px solid #73c99144' :
                        ragStatus.status==='error'  ? '1px solid #f4877144' : '1px solid #e2c08d44',
          }}>
            {ragStatus.status==='ready'    ? `⚡ RAG ${ragStatus.done} chunks`  :
             ragStatus.status==='indexing' ? `↻ Indexing ${ragStatus.done}/${ragStatus.total}` :
                                             '⚠ RAG error'}
          </span>
        )}
        {workspace && (
          <button onClick={() => setShowWorkspaceIntel(true)} style={{
            background:`${C.accent}12`, border:`1px solid ${C.accent}55`, color:C.accent,
            padding:'4px 9px', borderRadius:4, cursor:'pointer', fontSize:11, fontFamily:'inherit',
          }}>✦ Agent Workspace</button>
        )}
        <div style={{ flex:1 }} />
        {workspace && (
          <ToolsMenu items={[
            { group: 'Agent', icon: '✦', label: 'Agent Workspace', onClick: () => setShowWorkspaceIntel(true) },
            { group: 'History',      icon: '⏪', label: 'History',     onClick: () => setShowHistory(true) },
            ...(activeFile ? [
              { group: 'History',    icon: '🕐', label: 'Checkpoints', onClick: () => setShowCheckpoints(true) },
            ] : []),
            { group: 'Observability', icon: '📜', label: 'Agent Log',   onClick: () => setShowAgentLog(true) },
            { group: 'Observability', icon: '📅', label: 'Session',     onClick: () => setShowSession(true) },
            { group: 'Knowledge',    icon: '🧩', label: 'Skills',      onClick: () => setShowSkills(true) },
            { group: 'Knowledge',    icon: '🔍', label: 'Search',      onClick: () => setShowCodeSearch(true) },
            { group: 'Knowledge',    icon: '✓',  label: 'TODOs',       onClick: () => setShowTodos(true) },
            { group: 'Knowledge',    icon: '🧠', label: 'Memory',      onClick: () => setShowMemory(true) },
          ]} />
        )}
        <Btn primary onClick={() => setModal(true)}>
          {workspace ? `📁 ${workspace.name}` : '📁 Open Folder'}
        </Btn>
      </div>

      {/* ── Main row ───────────────────────────────────────────────────────── */}
      <div style={{ flex:1, display:'flex', overflow:'hidden' }}>

        {/* Sidebar */}
        <div style={{ width:250, background:C.bgSide, flexShrink:0,
                      display:'flex', flexDirection:'column', overflow:'hidden',
                      borderRight:`1px solid ${C.border}` }}>
          <div style={{ height:35, flexShrink:0, display:'flex', alignItems:'center',
                        justifyContent:'space-between', padding:'0 14px',
                        borderBottom:`1px solid ${C.border}` }}>
            <span style={{ fontSize:11, fontWeight:600, letterSpacing:1.1, color:'#bbb' }}>
              EXPLORER
            </span>
            <button onClick={loadTree} title="Refresh"
              style={{ background:'none', border:'none', color:C.textMuted,
                       cursor:'pointer', fontSize:15, padding:'2px 4px', lineHeight:1 }}>
              ↻
            </button>
          </div>
          <div style={{ flex:1, overflow:'auto', paddingBottom:8 }}>
            {tree ? (
              <FileTree tree={tree} activeFile={activeTab}
                        openFiles={openFiles} onOpenFile={handleOpenFile} />
            ) : (
              <div style={{ padding:'24px 16px', fontSize:12,
                            color:C.textMuted, lineHeight:1.7 }}>
                {workspace ? 'Loading…' : 'Click "Open Folder" to start.'}
              </div>
            )}
          </div>
        </div>

        {/* Editor column */}
        <div style={{ flex:1, display:'flex', flexDirection:'column',
                      overflow:'hidden', minWidth:0 }}>
          {/* Tab bar */}
          <div style={{ height:35, background:C.bgTab, flexShrink:0,
                        display:'flex', overflowX:'auto', overflowY:'hidden',
                        borderBottom:`1px solid ${C.border}` }}>
            {openFiles.map(f => {
              const name   = f.path.split('/').pop() || f.path
              const active = f.path === activeTab
              return (
                <div key={f.path} onClick={() => setActiveTab(f.path)}
                  style={{
                    display:'flex', alignItems:'center', gap:5, flexShrink:0,
                    padding:'0 14px', fontSize:12, cursor:'pointer',
                    whiteSpace:'nowrap', userSelect:'none',
                    background:  active ? C.bg : 'transparent',
                    color:       active ? C.textActive : C.textMuted,
                    borderRight: `1px solid ${C.border}`,
                    borderTop:   active ? `1px solid ${C.accent}` : '1px solid transparent',
                  }}>
                  {f.modified && <span style={{ color:C.modified, fontSize:9 }}>●</span>}
                  <span>{name}</span>
                  <span onClick={e => handleCloseTab(f.path, e)}
                    style={{ marginLeft:3, opacity:0.5, fontSize:16,
                             lineHeight:1, padding:'0 1px', cursor:'pointer' }}>
                    ×
                  </span>
                </div>
              )
            })}
          </div>

          {/* Monaco */}
          <div style={{ flex:1, overflow:'hidden' }}>
            {activeFile ? (
              <Editor file={activeFile}
                      onContentChange={handleContentChange}
                      onSave={handleSave} />
            ) : (
              <div style={{ height:'100%', display:'flex', flexDirection:'column',
                            alignItems:'center', justifyContent:'center',
                            gap:10, color:C.textMuted, userSelect:'none' }}>
                <div style={{ fontSize:40, opacity:0.12 }}>⚡</div>
                <div style={{ fontSize:13, opacity:0.5 }}>
                  {workspace ? 'Select a file from the explorer' : 'Open a folder to start'}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Chat panel */}
        <ChatPanel activeFile={activeFile} openFiles={openFiles}
                   onApplyCode={handleApplyCode}
                   onCreateFile={handleCreateFile}
                   pendingPrompt={pendingPrompt} />
      </div>

      {/* Terminal */}
      <Terminal visible={termOpen} workspace={workspace}
                activeFile={activeFile}
                autoRunPath={autoRunPath}
                onAutoRunHandled={() => setAutoRunPath(null)}
                onToggle={() => setTermOpen(v => !v)} />

      {/* Open folder modal */}
      {modal && (
        <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.65)',
                      display:'flex', alignItems:'center', justifyContent:'center', zIndex:999 }}>
          <div style={{ background:'#252526', border:`1px solid ${C.borderLight}`,
                        borderRadius:6, padding:24, width:460, maxWidth:'90vw' }}>
            <div style={{ fontSize:14, fontWeight:500, marginBottom:12 }}>Open Folder</div>
            <input autoFocus value={folderInput}
              onChange={e => setFolderInput(e.target.value)}
              onKeyDown={e => e.key==='Enter' && !modalLoading && handleOpenWorkspace()}
              placeholder="C:\Users\user\my-project"
              style={{ width:'100%', background:'#3c3c3c', border:'1px solid #555',
                       color:C.text, padding:'8px 10px', borderRadius:3,
                       fontSize:13, outline:'none', fontFamily:'inherit' }} />
            {modalErr && (
              <div style={{ color:C.errorText, fontSize:12, marginTop:6 }}>{modalErr}</div>
            )}
            <div style={{ display:'flex', justifyContent:'flex-end', gap:8, marginTop:16 }}>
              <Btn onClick={() => { setModal(false); setModalErr('') }}>Cancel</Btn>
              <Btn primary disabled={modalLoading} onClick={handleOpenWorkspace}>
                {modalLoading ? 'Opening…' : 'Open'}
              </Btn>
            </div>
          </div>
        </div>
      )}

      {/* Milestone B: Skill manager modal */}
      {showSkills && (
        <SkillManager
          activeFile={activeFile}
          onClose={() => setShowSkills(false)}
        />
      )}

      {/* Milestone C: Checkpoint browser */}
      {showCheckpoints && (
        <CheckpointBrowser
          activeFile={activeFile}
          onRestored={(path, content) => {
            setOpenFiles(prev => prev.map(f =>
              f.path === path
                ? { ...f, content, modified:false, version:(f.version??0)+1 }
                : f
            ))
          }}
          onClose={() => setShowCheckpoints(false)}
        />
      )}

      {/* Milestone D: Agent log viewer */}
      {showAgentLog && <AgentTrace onClose={() => setShowAgentLog(false)} />}

      {/* Sprint 4: Session timeline */}
      {showSession && (
        <SessionTimeline
          onClose={() => setShowSession(false)}
          onFileRestored={() => {
            if (activeTab) {
              fetch('/api/file?path=' + encodeURIComponent(activeTab))
                .then(r => r.json())
                .then(d => {
                  if (d.content !== undefined) {
                    setOpenFiles(prev => prev.map(f =>
                      f.path === activeTab
                        ? { ...f, content: d.content, modified: false, version: (f.version ?? 0) + 1 }
                        : f
                    ))
                  }
                }).catch(() => {})
            }
          }}
        />
      )}

      {/* Sprint 5: Code search */}
      {showCodeSearch && (
        <CodeSearch
          onClose={() => setShowCodeSearch(false)}
          onOpenFile={async (path, line) => {
            const r = await fetch('/api/file?path=' + encodeURIComponent(path))
            if (r.ok) {
              const d = await r.json()
              setOpenFiles(prev => {
                const exists = prev.find(f => f.path === path)
                if (exists) return prev
                return [...prev, { path, content: d.content, language: d.language, modified:false, version:0 }]
              })
              setActiveTab(path)
            }
          }}
        />
      )}

      {/* Sprint 5: TODO resolver */}
      {showTodos && (
        <TodoResolver
          onClose={() => setShowTodos(false)}
          onResolve={(todo) => {
            setShowTodos(false)
            // Open the file containing the TODO so the user has context
            fetch('/api/file?path=' + encodeURIComponent(todo.file_path))
              .then(r => r.json())
              .then(d => {
                setOpenFiles(prev => {
                  const exists = prev.find(f => f.path === todo.file_path)
                  if (exists) return prev
                  return [...prev, { path: todo.file_path, content: d.content, language: d.language, modified:false, version:0 }]
                })
                setActiveTab(todo.file_path)
                // Tell the AI exactly what to resolve, with line context
                setPendingPrompt({
                  text: `Resolve this ${todo.marker} on line ${todo.line}: "${todo.text}"\n\nContext:\n${todo.context}`,
                  ts: Date.now(),
                })
              }).catch(() => {})
          }}
        />
      )}

      {/* Sprint 5: Project memory */}
      {showMemory && <ProjectMemoryPanel onClose={() => setShowMemory(false)} />}

      {showWorkspaceIntel && (
        <WorkspaceIntelligence
          onClose={() => setShowWorkspaceIntel(false)}
          onOpenFile={handleOpenFile}
          onAsk={text => setPendingPrompt({ text, ts: Date.now() })}
        />
      )}

      {/* Edit history modal (Phase 6) */}
      {showHistory && (
        <UndoHistory
          workspace={workspace?.workspace ?? ''}
          onReverted={(path) => { handleRevertFile(path); setShowHistory(false) }}
          onClose={() => setShowHistory(false)}
        />
      )}
    </div>
  )
}

// ── Reusable button ───────────────────────────────────────────────────────────
function Btn({ children, onClick, primary, disabled }) {
  const [hov, setHov] = useState(false)
  return (
    <button onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        background: primary ? (hov ? C.accentHov : C.accent) : (hov ? '#3a3a3a' : 'transparent'),
        border:     primary ? 'none' : '1px solid #555',
        color:      primary ? '#fff' : C.text,
        padding: '5px 14px', borderRadius:3,
        cursor: disabled ? 'not-allowed' : 'pointer',
        fontSize:12, fontFamily:'inherit',
        opacity: disabled ? 0.5 : 1,
        transition:'background 0.1s',
      }}>
      {children}
    </button>
  )
}
