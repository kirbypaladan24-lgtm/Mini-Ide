import { useState } from 'react'

// ── File-extension → accent colour (language colours from GitHub Linguist) ───
const EXT_COLOR = {
  py:   '#3572a5', pyw:  '#3572a5',
  js:   '#f1e05a', jsx:  '#61dafb', mjs: '#f1e05a',
  ts:   '#3178c6', tsx:  '#61dafb',
  json: '#cbcb41', jsonc:'#cbcb41',
  css:  '#563d7c', scss: '#c6538c', less:'#1d365d',
  html: '#e34c26', htm:  '#e34c26',
  md:   '#083fa1', mdx:  '#083fa1',
  yml:  '#cb171e', yaml: '#cb171e',
  toml: '#9c4121', ini:  '#9c4121', cfg: '#9c4121',
  sh:   '#89e051', bash: '#89e051', zsh: '#89e051',
  bat:  '#c1f12e', cmd:  '#c1f12e',
  rs:   '#dea584', go:   '#00add8',
  cpp:  '#f34b7d', cc:   '#f34b7d', cxx: '#f34b7d',
  c:    '#555555', h:    '#555555',
  java: '#b07219', kt:   '#A97BFF',
  sql:  '#e38c00',
  xml:  '#0060ac', svg:  '#0060ac',
  vue:  '#41b883', rb:   '#701516', php: '#4f5d95',
  env:  '#ecd53f', txt:  '#858585',
}

function extOf(name) {
  const parts = name.split('.')
  return parts.length > 1 ? parts.pop().toLowerCase() : ''
}

// Coloured badge showing the first 2 chars of the extension
function FileBadge({ name }) {
  const ext   = extOf(name)
  const color = EXT_COLOR[ext] ?? '#6a6a6a'
  const label = ext.slice(0, 2).toUpperCase() || '?'
  return (
    <span style={{
      display:'inline-flex', alignItems:'center', justifyContent:'center',
      width:17, height:13, borderRadius:2,
      background:color, flexShrink:0,
      fontSize:7, fontWeight:800, color:'rgba(0,0,0,0.75)',
      marginRight:5, letterSpacing:0,
    }}>
      {label}
    </span>
  )
}

// ── Single tree node (recursive) ──────────────────────────────────────────────
function TreeNode({ node, depth, activeFile, openFiles, onOpenFile, expanded, onToggle }) {
  const isDir    = node.type === 'directory'
  const isOpen   = expanded.has(node.path)
  const isActive = node.path === activeFile
  const modified = !isDir && openFiles.find(f => f.path === node.path)?.modified
  const indent   = 8 + depth * 14

  return (
    <>
      <div
        role={isDir ? 'button' : 'button'}
        tabIndex={0}
        onClick={() => isDir ? onToggle(node.path) : onOpenFile(node.path)}
        onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (isDir ? onToggle(node.path) : onOpenFile(node.path))}
        style={{
          display:'flex', alignItems:'center',
          height:22, paddingLeft:indent, paddingRight:8,
          cursor:'pointer', userSelect:'none', fontSize:13,
          borderLeft: isActive ? '2px solid #007acc' : '2px solid transparent',
          background:  isActive ? '#094771' : 'transparent',
          color:       isActive ? '#ffffff'  : '#cccccc',
          outline:'none',
        }}
        onMouseEnter={e => { if (!isActive) e.currentTarget.style.background = '#2a2d2e' }}
        onMouseLeave={e => { if (!isActive) e.currentTarget.style.background = 'transparent' }}
      >
        {/* Expand chevron — folders only */}
        <span style={{
          width:14, fontSize:9, color:'#858585',
          textAlign:'center', flexShrink:0, marginRight:2,
        }}>
          {isDir ? (isOpen ? '▾' : '▸') : ''}
        </span>

        {/* Icon */}
        {isDir ? (
          <span style={{ fontSize:13, marginRight:5, flexShrink:0 }}>
            {isOpen ? '📂' : '📁'}
          </span>
        ) : (
          <FileBadge name={node.name} />
        )}

        {/* Label */}
        <span style={{
          flex:1, overflow:'hidden', textOverflow:'ellipsis',
          whiteSpace:'nowrap', lineHeight:'22px',
        }}>
          {node.name}
        </span>

        {/* Modified dot */}
        {modified && (
          <span style={{
            width:6, height:6, borderRadius:'50%',
            background:'#e2c08d', flexShrink:0, marginLeft:4,
          }} />
        )}
      </div>

      {/* Render children when expanded */}
      {isDir && isOpen && node.children?.map(child => (
        <TreeNode
          key={child.path || child.name}
          node={child}
          depth={depth + 1}
          activeFile={activeFile}
          openFiles={openFiles}
          onOpenFile={onOpenFile}
          expanded={expanded}
          onToggle={onToggle}
        />
      ))}
    </>
  )
}

// ── Root FileTree component ───────────────────────────────────────────────────
export default function FileTree({ tree, activeFile, openFiles, onOpenFile }) {
  // Start with root expanded (empty-string path = root)
  const [expanded, setExpanded] = useState(() => new Set(['']))

  const toggle = (path) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })
  }

  if (!tree) return null

  return (
    <div>
      <TreeNode
        node={tree}
        depth={0}
        activeFile={activeFile}
        openFiles={openFiles}
        onOpenFile={onOpenFile}
        expanded={expanded}
        onToggle={toggle}
      />
    </div>
  )
}
