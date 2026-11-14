# ⚡ Mini IDE

A locally-running AI code editor built on FastAPI + React + Monaco.

## Phase 1 — Core IDE Shell

Full feature plan: 6 phases from bare IDE shell → context engine → agent loop → AST diffs.

---

## Quick start (Windows)

Double-click `start.bat` — it opens two terminals and launches both servers.

Then open **http://localhost:5173** in your browser.

---

## Manual setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Ollama running locally (used from Phase 2)

### Backend
```
cd backend
pip install -r ../requirements.txt
python -m uvicorn main:app --reload --port 8000
```

### Frontend
```
cd frontend
npm install
npm run dev
```

---

## Phase 1 features

- Open any folder as your workspace via "Open Folder"
- File explorer with expand/collapse and colour-coded file badges
- Monaco Editor (same engine as VS Code) with full syntax highlighting
- Multiple tabs — click to switch, × to close
- Modified indicator (● dot) on unsaved tabs
- **Ctrl+S** to save to disk
- Terminal panel (collapsible, Phase 3 placeholder)
- AI chat panel (Phase 2 placeholder — models listed)
- Workspace sandboxing: file tools cannot escape the chosen folder

---

## Roadmap

| Phase | Feature |
|---|---|
| 1 ✅ | IDE shell — Monaco + file tree + tabs + save |
| 2 | LLM chat + streaming + diff → approve → write |
| 3 | Context engine: current file + imports + open tabs + error logs |
| 4 | Enhanced RAG: function-level FAISS chunks + symbol index |
| 5 | Agent loop: observe → re-evaluate → auto-fix on error |
| 6 | AST-aware patches + multi-file edits + undo stack |

---

## Architecture

```
UI (React + Monaco)
      ↓
Orchestrator          [Phase 2]
      ↓
Agent Loop            [Phase 5]
      ↓
LLM Models (Ollama)   [Phase 2]
      ↓
Tools Layer           [Phase 1 file ops; Phase 3+ code runner, AST]
      ↓
Memory System         [Phase 3]
      ↓
Knowledge Base (FAISS)[Phase 4]
```
