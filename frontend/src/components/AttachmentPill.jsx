import { C } from '../App'

const TYPE_ICON = {
  image:   '🖼️',
  pdf:     '📄',
  docx:    '📝',
  csv:     '📊',
  json:    '📋',
  text:    '📃',
  error:   '⚠️',
}

const TYPE_COLOR = {
  image:   '#7F77DD',
  pdf:     '#D85A30',
  docx:    '#378ADD',
  csv:     '#1D9E75',
  json:    '#BA7517',
  text:    '#888',
  error:   '#f48771',
}

export default function AttachmentPill({ attachment, onRemove }) {
  const { type = 'file', name = 'file' } = attachment
  const icon  = TYPE_ICON[type]  || '📎'
  const color = TYPE_COLOR[type] || '#888'

  return (
    <div style={{
      display:'inline-flex', alignItems:'center', gap:5,
      padding:'3px 8px 3px 7px', borderRadius:12,
      background:`${color}18`, border:`1px solid ${color}44`,
      fontSize:11, maxWidth:200,
    }}>
      <span style={{ flexShrink:0 }}>{icon}</span>
      <span style={{
        color: C.text, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
      }}>
        {name}
      </span>
      {type === 'image' && attachment.description && (
        <span style={{ color:color, fontSize:9, flexShrink:0 }}>✓ read</span>
      )}
      {onRemove && (
        <button
          onClick={onRemove}
          style={{
            background:'none', border:'none', color:'#666',
            cursor:'pointer', fontSize:13, padding:'0 0 0 2px',
            lineHeight:1, flexShrink:0,
          }}
          title="Remove attachment"
        >
          ×
        </button>
      )}
    </div>
  )
}
