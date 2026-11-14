import MonacoEditor from '@monaco-editor/react'
import { useRef } from 'react'

// Monaco editor options — tuned for a comfortable coding experience
const EDITOR_OPTIONS = {
  fontSize:                  14,
  fontFamily:                "'Cascadia Code', 'Fira Code', 'JetBrains Mono', Consolas, 'Courier New', monospace",
  fontLigatures:             true,
  lineHeight:                22,
  letterSpacing:             0.3,
  lineNumbers:               'on',
  glyphMargin:               true,           // space for breakpoints (Phase 3)
  folding:                   true,
  foldingHighlight:          true,
  minimap:                   { enabled: true, scale: 1 },
  scrollBeyondLastLine:      false,
  wordWrap:                  'off',
  automaticLayout:           true,           // resize with container
  bracketPairColorization:   { enabled: true },
  renderWhitespace:          'selection',
  smoothScrolling:           true,
  cursorBlinking:            'smooth',
  cursorSmoothCaretAnimation:'on',
  tabSize:                   4,
  insertSpaces:              true,
  formatOnPaste:             true,
  formatOnType:              false,
  padding:                   { top: 10, bottom: 10 },
  suggest:                   { preview: true },
  inlineSuggest:             { enabled: true },
  scrollbar: {
    verticalScrollbarSize:   8,
    horizontalScrollbarSize: 8,
  },
}

export default function Editor({ file, onContentChange, onSave }) {
  const editorRef = useRef(null)

  const handleMount = (editor, monaco) => {
    editorRef.current = editor

    // ── Ctrl+S / Cmd+S → save ─────────────────────────────────────────────
    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS,
      () => onSave(file.path)
    )

    // ── Ctrl+Shift+F → format (monaco built-in) ───────────────────────────
    editor.addCommand(
      monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyF,
      () => editor.getAction('editor.action.formatDocument')?.run()
    )

    // Auto-focus on open
    editor.focus()
  }

  /*
   * key={`${file.path}-${file.version ?? 0}`} forces a full remount when:
   *   1. The user switches files (path changes)
   *   2. AI applies new code via the chat panel (version increments)
   * This keeps defaultValue in sync without needing a controlled component.
   * Phase 6 will upgrade to Monaco models for cursor-position persistence.
   */
  return (
    <MonacoEditor
      key={`${file.path}-${file.version ?? 0}`}
      height="100%"
      theme="vs-dark"
      language={file.language}
      defaultValue={file.content}
      onChange={value => onContentChange(file.path, value ?? '')}
      onMount={handleMount}
      options={EDITOR_OPTIONS}
      loading={
        <div style={{
          height:'100%', display:'flex', alignItems:'center',
          justifyContent:'center', color:'#555', fontSize:12,
          fontFamily:'inherit', background:'#1e1e1e',
        }}>
          Loading editor…
        </div>
      }
    />
  )
}
