import { C } from '../App'

const RISK_COLOR = { low:'#73c991', moderate:'#e2c08d', destructive:'#f48771' }
const RISK_ICON  = { low:'◦', moderate:'◈', destructive:'⚠' }

export default function PlanView({ plan, fileCount }) {
  if (!plan) return null
  const { understanding, approach, files_to_change = [], confidence } = plan
  const pct   = Math.round((confidence ?? 0.8) * 100)
  const color  = pct >= 80 ? '#73c991' : pct >= 60 ? '#e2c08d' : '#f48771'

  return (
    <div style={{
      alignSelf:'flex-start', maxWidth:'97%',
      background:'#1e2a1e', border:'1px solid #73c99133',
      borderRadius:6, overflow:'hidden', fontSize:12,
    }}>
      {/* Header */}
      <div style={{
        padding:'8px 12px', background:'#73c99110',
        borderBottom:'1px solid #73c99122',
        display:'flex', alignItems:'center', gap:8,
      }}>
        <span style={{ fontSize:14 }}>📋</span>
        <span style={{ fontWeight:500, color:'#73c991' }}>
          Plan — {fileCount} file{fileCount !== 1 ? 's' : ''} to change
        </span>
        <div style={{ flex:1 }} />
        <span style={{ fontSize:10, color, padding:'1px 6px',
                       background:`${color}18`, borderRadius:8,
                       border:`1px solid ${color}44` }}>
          {pct}% confident
        </span>
      </div>

      <div style={{ padding:'10px 12px' }}>
        {understanding && (
          <div style={{ color:'#bbb', marginBottom:6, lineHeight:1.6 }}>
            {understanding}
          </div>
        )}
        {approach && (
          <div style={{ color:'#888', marginBottom:10, lineHeight:1.6, fontSize:11 }}>
            Approach: {approach}
          </div>
        )}

        {/* Files list */}
        <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
          {files_to_change.map((f, i) => {
            const riskColor = RISK_COLOR[f.risk] || '#888'
            const riskIcon  = RISK_ICON[f.risk]  || '◦'
            return (
              <div key={i} style={{
                padding:'6px 8px', borderRadius:4,
                background:'#0a0a0a', border:`1px solid #2a2a2a`,
              }}>
                <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                  <span style={{ color:riskColor, fontSize:10 }}>{riskIcon}</span>
                  <code style={{
                    color: C.text, fontSize:11, flex:1,
                    fontFamily:"'Cascadia Code','Fira Code',monospace",
                  }}>
                    {f.file}
                  </code>
                  <span style={{
                    fontSize:9, color:riskColor,
                    padding:'1px 5px', borderRadius:6,
                    background:`${riskColor}15`, border:`1px solid ${riskColor}33`,
                    flexShrink:0,
                  }}>
                    {f.risk}
                  </span>
                </div>
                <div style={{ fontSize:10, color:'#666', marginTop:3, paddingLeft:16 }}>
                  {f.changes || f.reason}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
