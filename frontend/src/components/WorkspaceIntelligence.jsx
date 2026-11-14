import { useCallback, useEffect, useState } from 'react'
import { C } from '../App'

const button = {
  background: 'transparent', border: '1px solid #394152', color: C.text,
  padding: '5px 8px', borderRadius: 4, cursor: 'pointer', fontSize: 11,
  fontFamily: 'inherit',
}

export default function WorkspaceIntelligence({ onClose, onOpenFile, onAsk }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    fetch('/api/workspace/intelligence')
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    const onKey = event => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const open = path => { onOpenFile(path); onClose() }
  const index = data?.index || {}
  const architecture = data?.architecture || {}
  const inventory = data?.inventory || {}

  return (
    <div onClick={onClose} style={{ position:'fixed', inset:0, zIndex:1200,
      background:'rgba(5,8,13,.72)', display:'flex', justifyContent:'flex-end' }}>
      <aside onClick={event => event.stopPropagation()} style={{ width:430, maxWidth:'100vw',
        height:'100%', background:'#0f1218', borderLeft:`1px solid ${C.borderLight}`,
        display:'flex', flexDirection:'column', boxShadow:'-16px 0 44px #0007' }}>
        <header style={{ padding:'18px 18px 14px', borderBottom:`1px solid ${C.border}` }}>
          <div style={{ display:'flex', alignItems:'center', gap:9 }}>
            <span style={{ color:C.accent, fontSize:17 }}>✦</span>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:14, fontWeight:650 }}>Agent Workspace</div>
              <div style={{ fontSize:11, color:C.textMuted, marginTop:2 }}>
                {data?.name || 'Reading workspace intelligence'}
              </div>
            </div>
            <button onClick={load} title="Refresh workspace intelligence" style={button}>Refresh</button>
            <button onClick={onClose} aria-label="Close" style={{ ...button, border:'none', fontSize:17, padding:'2px 5px' }}>×</button>
          </div>
        </header>

        <div style={{ padding:18, overflow:'auto', display:'flex', flexDirection:'column', gap:18 }}>
          {loading && <div style={{ color:C.textMuted, fontSize:12 }}>Building a live map of this workspace…</div>}
          {!loading && !data && <div style={{ color:C.errorText, fontSize:12 }}>Couldn’t load workspace intelligence.</div>}
          {data && <>
            <section>
              <Label>AGENT ACCESS</Label>
              <div style={{ padding:12, border:`1px solid ${C.accent}38`, background:`${C.accent}0c`, borderRadius:7 }}>
                <div style={{ display:'flex', alignItems:'center', gap:7, color:C.accent, fontSize:12, fontWeight:600 }}>
                  <span style={{ width:7, height:7, borderRadius:'50%', background:C.success, boxShadow:`0 0 10px ${C.success}` }} />
                  Workspace-scoped access is active
                </div>
                <div style={{ color:'#aeb7c5', fontSize:11, lineHeight:1.55, marginTop:7 }}>
                  The agent can inspect, search, plan, edit, and verify across the folder you opened. It stays scoped to that folder.
                </div>
              </div>
            </section>

            <section>
              <Label>CODEBASE AT A GLANCE</Label>
              <div style={{ display:'grid', gridTemplateColumns:'repeat(3, 1fr)', gap:8 }}>
                <Metric value={inventory.files ?? 0} label="files" />
                <Metric value={inventory.directories ?? 0} label="folders" />
                <Metric value={index.status === 'ready' ? 'Ready' : index.status || 'Idle'} label="semantic index" accent={index.status === 'ready'} />
              </div>
              {(inventory.languages || []).length > 0 && <div style={{ display:'flex', flexWrap:'wrap', gap:5, marginTop:9 }}>
                {inventory.languages.map(language => <span key={language.name} style={{ fontSize:10, color:'#aab6ca', background:'#18202d', border:'1px solid #283348', borderRadius:12, padding:'3px 7px' }}>{language.name} · {language.files}</span>)}
              </div>}
            </section>

            <section>
              <Label>WORKFLOW MAP</Label>
              <WorkflowRow step="1" title="Understand" text="Maps files, imports, symbols, git context, and saved project decisions." />
              <WorkflowRow step="2" title="Plan" text="Shows the files and approach for coordinated changes before it edits." />
              <WorkflowRow step="3" title="Execute & verify" text="Applies reviewed changes, runs code/tests, and records checkpoints." last />
            </section>

            <section>
              <Label>LIKELY ENTRY POINTS</Label>
              {(architecture.entry_points || []).length === 0 ? <Empty text="The code graph is still learning this project, or no conventional entry point was found." /> : architecture.entry_points.map(entry => <FileRow key={entry.file_path} path={entry.file_path} detail={entry.reason} onOpen={open} />)}
            </section>

            <section>
              <Label>HIGH-IMPACT MODULES</Label>
              {(architecture.core_modules || []).length === 0 ? <Empty text="No dependency hotspots are available yet." /> : architecture.core_modules.slice(0, 5).map(module => <FileRow key={module.file_path} path={module.file_path} detail={`Imported by ${module.imported_by_count} module${module.imported_by_count === 1 ? '' : 's'}`} onOpen={open} />)}
            </section>

            <section style={{ display:'flex', gap:8 }}>
              <button onClick={() => { onAsk('Give me a concise walkthrough of this codebase: its entry points, data flow, main modules, and the safest first improvement.'); onClose() }} style={{ ...button, flex:1, color:C.accent, borderColor:`${C.accent}66` }}>Explain this codebase</button>
              <button onClick={() => { onAsk(`Review the ${data.todo_count || 0} TODOs in this workspace and propose the highest-value next task.`); onClose() }} style={{ ...button, flex:1 }}>Plan next task</button>
            </section>
          </>}
        </div>
      </aside>
    </div>
  )
}

function Label({ children }) { return <div style={{ color:'#71809a', fontSize:10, fontWeight:700, letterSpacing:1.05, marginBottom:8 }}>{children}</div> }
function Metric({ value, label, accent }) { return <div style={{ padding:'10px 8px', background:'#151b25', border:'1px solid #222d3e', borderRadius:6 }}><div style={{ color:accent ? C.success : C.text, fontSize:15, fontWeight:650, overflow:'hidden', textOverflow:'ellipsis' }}>{value}</div><div style={{ color:C.textMuted, fontSize:9, marginTop:4 }}>{label}</div></div> }
function WorkflowRow({ step, title, text, last }) { return <div style={{ position:'relative', display:'flex', gap:10, paddingBottom:last ? 0 : 12 }}><span style={{ width:20, height:20, borderRadius:'50%', display:'inline-flex', alignItems:'center', justifyContent:'center', flexShrink:0, background:`${C.accent}18`, color:C.accent, fontSize:10, border:`1px solid ${C.accent}44` }}>{step}</span>{!last && <span style={{ position:'absolute', left:9, top:21, height:12, width:1, background:'#344055' }} /> }<div><div style={{ color:C.text, fontSize:12, fontWeight:600 }}>{title}</div><div style={{ color:C.textMuted, fontSize:10, lineHeight:1.45, marginTop:2 }}>{text}</div></div></div> }
function FileRow({ path, detail, onOpen }) { return <button onClick={() => onOpen(path)} style={{ width:'100%', textAlign:'left', border:'none', borderTop:'1px solid #202837', background:'transparent', color:C.text, cursor:'pointer', padding:'8px 3px', fontFamily:'inherit' }}><div style={{ fontSize:11, color:'#b8c7dc', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>◫ {path}</div><div style={{ fontSize:10, color:C.textMuted, marginLeft:15, marginTop:2 }}>{detail}</div></button> }
function Empty({ text }) { return <div style={{ padding:'9px 10px', color:C.textMuted, background:'#141922', borderRadius:5, fontSize:10, lineHeight:1.5 }}>{text}</div> }
