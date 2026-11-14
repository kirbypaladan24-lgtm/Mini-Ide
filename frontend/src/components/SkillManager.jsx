import { useState, useEffect, useCallback } from 'react'
import { C } from '../App'

function Badge({ children, color = '#555' }) {
  return (
    <span style={{
      fontSize:9, fontWeight:600, letterSpacing:0.5, padding:'1px 6px',
      borderRadius:8, background:`${color}22`, color,
      border:`1px solid ${color}44`,
    }}>
      {children}
    </span>
  )
}

function SkillRow({ skill, onToggle, onUninstall, active }) {
  const isBuiltin = skill.path?.includes('builtin') ?? !skill.path?.includes('installed')
  return (
    <div style={{
      padding:'10px 14px', borderBottom:`1px solid #2a2a2a`,
      display:'flex', alignItems:'flex-start', gap:10,
      opacity: skill.enabled ? 1 : 0.45,
    }}>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:3 }}>
          <span style={{ fontSize:12, fontWeight:500,
                         color: skill.enabled ? C.text : C.textMuted }}>
            {skill.name}
          </span>
          {isBuiltin  && <Badge color="#569cd6">built-in</Badge>}
          {!isBuiltin && <Badge color="#c586c0">installed</Badge>}
          {active     && <Badge color="#73c991">active</Badge>}
          <span style={{ fontSize:10, color:'#555' }}>v{skill.version}</span>
        </div>
        <div style={{ fontSize:11, color:'#666', lineHeight:1.5 }}>
          {skill.description}
        </div>
        {skill.triggers?.imports?.length > 0 && (
          <div style={{ fontSize:10, color:'#555', marginTop:3 }}>
            Triggers on: {skill.triggers.imports.slice(0,4).join(', ')}
            {skill.triggers.imports.length > 4 ? '…' : ''}
          </div>
        )}
        {skill.triggers?.file_patterns?.length > 0 && (
          <div style={{ fontSize:10, color:'#555' }}>
            Files: {skill.triggers.file_patterns.join(', ')}
          </div>
        )}
      </div>
      <div style={{ display:'flex', flexDirection:'column', gap:4, flexShrink:0 }}>
        <button
          onClick={() => onToggle(skill.name, skill.enabled)}
          style={{
            background: skill.enabled ? '#073a18' : '#2a2a2a',
            border:`1px solid ${skill.enabled ? '#73c99155' : '#3a3a3a'}`,
            color: skill.enabled ? '#73c991' : '#666',
            padding:'3px 10px', borderRadius:3,
            cursor:'pointer', fontSize:10, fontFamily:'inherit',
          }}
        >
          {skill.enabled ? 'Enabled' : 'Disabled'}
        </button>
        {!isBuiltin && (
          <button onClick={() => onUninstall(skill.name)} style={{
            background:'transparent', border:'1px solid #4a1a1a',
            color:'#f48771', padding:'3px 10px', borderRadius:3,
            cursor:'pointer', fontSize:10, fontFamily:'inherit',
          }}>
            Remove
          </button>
        )}
      </div>
    </div>
  )
}

export default function SkillManager({ activeFile, onClose }) {
  const [tab,          setTab]          = useState('installed') // installed | marketplace
  const [skills,       setSkills]       = useState([])
  const [activeSkills, setActiveSkills] = useState([])
  const [mktResults,   setMktResults]   = useState([])
  const [mktQuery,     setMktQuery]     = useState('')
  const [mktLoading,   setMktLoading]   = useState(false)
  const [installUrl,   setInstallUrl]   = useState('')
  const [installing,   setInstalling]   = useState(false)
  const [feedback,     setFeedback]     = useState('')

  const loadSkills = useCallback(() => {
    fetch('/api/skills').then(r => r.json()).then(d => setSkills(d.skills ?? []))
    if (activeFile) {
      const params = new URLSearchParams({ path: activeFile.path, language: activeFile.language })
      fetch(`/api/skills/active?${params}`)
        .then(r => r.json()).then(d => setActiveSkills(d.skills ?? []))
    }
  }, [activeFile])

  useEffect(() => { loadSkills() }, [loadSkills])

  const toggle = async (name, enabled) => {
    const action = enabled ? 'disable' : 'enable'
    await fetch(`/api/skills/${name}/${action}`, { method:'POST' })
    loadSkills()
  }

  const uninstall = async (name) => {
    await fetch(`/api/skills/${name}`, { method:'DELETE' })
    setFeedback(`Removed ${name}`)
    loadSkills()
  }

  const searchMarketplace = async () => {
    setMktLoading(true)
    const r = await fetch(`/api/skills/marketplace?q=${encodeURIComponent(mktQuery)}`)
    const d = await r.json()
    setMktResults(d.results ?? [])
    setMktLoading(false)
  }

  const installFromUrl = async (url) => {
    setInstalling(true); setFeedback('')
    const r = await fetch('/api/skills/install', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ url }),
    })
    const d = await r.json()
    setInstalling(false)
    if (d.ok) { setFeedback(`✓ Installed: ${d.name}`); setInstallUrl(''); loadSkills() }
    else       { setFeedback(`✗ ${d.error}`) }
  }

  // Close on Escape
  useEffect(() => {
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  return (
    <div style={{ position:'fixed', inset:0, zIndex:1000, background:'rgba(0,0,0,0.7)',
                  display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div style={{ background:'#1e1e1e', border:`1px solid ${C.borderLight}`,
                    borderRadius:6, width:600, maxWidth:'95vw', maxHeight:'85vh',
                    display:'flex', flexDirection:'column', overflow:'hidden' }}>

        {/* Header */}
        <div style={{ padding:'12px 16px', borderBottom:`1px solid ${C.border}`,
                      display:'flex', alignItems:'center', gap:10, flexShrink:0 }}>
          <span style={{ fontSize:14 }}>🧩</span>
          <span style={{ fontSize:13, fontWeight:500 }}>Skill Manager</span>
          {activeSkills.length > 0 && (
            <div style={{ display:'flex', gap:4 }}>
              {activeSkills.map(n => <Badge key={n} color="#73c991">{n} active</Badge>)}
            </div>
          )}
          <div style={{ flex:1 }} />
          <button onClick={onClose} style={{ background:'none', border:'none',
            color:C.textMuted, cursor:'pointer', fontSize:18, lineHeight:1 }}>×</button>
        </div>

        {/* Tabs */}
        <div style={{ display:'flex', borderBottom:`1px solid ${C.border}`,
                      background:'#252526', flexShrink:0 }}>
          {['installed', 'marketplace'].map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              background:'none', border:'none', padding:'8px 16px',
              color: tab===t ? C.textActive : C.textMuted,
              borderBottom: tab===t ? '2px solid #007acc' : '2px solid transparent',
              cursor:'pointer', fontSize:12, fontFamily:'inherit', fontWeight: tab===t ? 500 : 400,
            }}>
              {t === 'installed' ? `Installed (${skills.length})` : 'Marketplace'}
            </button>
          ))}
        </div>

        {/* Body */}
        <div style={{ flex:1, overflow:'auto' }}>

          {tab === 'installed' && (
            <>
              {skills.length === 0 ? (
                <div style={{ padding:28, textAlign:'center', color:'#555', fontSize:12 }}>
                  No skills loaded. Check that PyYAML is installed: pip install PyYAML
                </div>
              ) : skills.map(s => (
                <SkillRow
                  key={s.name} skill={s}
                  active={activeSkills.includes(s.name)}
                  onToggle={toggle} onUninstall={uninstall}
                />
              ))}

              {/* Install from URL */}
              <div style={{ padding:'12px 14px', borderTop:`1px solid #2a2a2a` }}>
                <div style={{ fontSize:11, color:'#666', marginBottom:6 }}>
                  Install from raw GitHub URL (.skill.yaml)
                </div>
                <div style={{ display:'flex', gap:6 }}>
                  <input value={installUrl} onChange={e => setInstallUrl(e.target.value)}
                    placeholder="https://raw.githubusercontent.com/…/skill.yaml"
                    style={{ flex:1, background:'#2d2d2d', border:`1px solid #444`,
                             color:C.text, padding:'6px 10px', borderRadius:3,
                             fontSize:11, fontFamily:'inherit', outline:'none' }} />
                  <button
                    onClick={() => installFromUrl(installUrl)}
                    disabled={!installUrl.trim() || installing}
                    style={{ background:C.accent, border:'none', color:'#fff',
                             padding:'6px 12px', borderRadius:3, cursor:'pointer',
                             fontSize:11, fontFamily:'inherit',
                             opacity:(!installUrl.trim()||installing)?0.5:1 }}>
                    {installing ? '…' : 'Install'}
                  </button>
                </div>
                {feedback && (
                  <div style={{ fontSize:11, color: feedback.startsWith('✓')?'#73c991':'#f48771',
                                marginTop:5 }}>
                    {feedback}
                  </div>
                )}
              </div>
            </>
          )}

          {tab === 'marketplace' && (
            <div style={{ padding:12 }}>
              <div style={{ display:'flex', gap:6, marginBottom:12 }}>
                <input value={mktQuery} onChange={e => setMktQuery(e.target.value)}
                  onKeyDown={e => e.key==='Enter' && searchMarketplace()}
                  placeholder="Search community skills…"
                  style={{ flex:1, background:'#2d2d2d', border:`1px solid #444`,
                           color:C.text, padding:'6px 10px', borderRadius:3,
                           fontSize:11, fontFamily:'inherit', outline:'none' }} />
                <button onClick={searchMarketplace} disabled={mktLoading} style={{
                  background:C.accent, border:'none', color:'#fff',
                  padding:'6px 14px', borderRadius:3, cursor:'pointer',
                  fontSize:11, fontFamily:'inherit', opacity:mktLoading?0.5:1 }}>
                  {mktLoading ? '…' : 'Search'}
                </button>
              </div>

              {mktResults.length === 0 && !mktLoading && (
                <div style={{ textAlign:'center', color:'#555', fontSize:12, padding:20 }}>
                  Search GitHub for community skill files.<br/>
                  Requires an internet connection.
                </div>
              )}

              {mktResults.map((r, i) => (
                <div key={i} style={{ padding:'10px 0', borderBottom:'1px solid #2a2a2a',
                                      display:'flex', alignItems:'center', gap:10 }}>
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:12, color:C.text, fontWeight:500 }}>{r.name}</div>
                    <div style={{ fontSize:10, color:'#666' }}>{r.repo}</div>
                  </div>
                  <button onClick={() => installFromUrl(r.raw_url)} style={{
                    background:'#073a18', border:'1px solid #73c99155',
                    color:'#73c991', padding:'4px 10px', borderRadius:3,
                    cursor:'pointer', fontSize:10, fontFamily:'inherit' }}>
                    Install
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
