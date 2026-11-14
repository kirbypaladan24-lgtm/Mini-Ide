"""
Mini IDE — FastAPI backend
Phase 1: Workspace + file CRUD
Phase 2: Ollama WebSocket streaming + /api/models
Phase 3: Context engine (imports, tabs, AST) + confidence gate
Phase 4: FAISS RAG index + file watcher + /api/rag/*
"""
import sys, json, re, asyncio
from collections import Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import httpx

from tools.file_ops import list_directory, read_file, write_file, create_file, delete_file, rename_path
from llm.client     import stream_chat, list_models, check_connection
from llm.router     import MODELS, get_system_prompt, build_messages, build_messages_with_context
from context_engine.workspace_state import build_workspace_context
from rag.indexer    import index_workspace, index_file, get_status as rag_status
from rag.retriever  import semantic_search, format_rag_context
from rag.watcher    import start_watcher, stop_watcher, drain_changes
from agent.loop     import run_with_autofix
from agent.pipeline import run_pipeline as agent_run_pipeline
from agent.explain  import explain_change
from tools.file_reader       import read_uploaded_file, format_attachment_context
from tools.convention_detector import detect_conventions, build_prompt_note
from context_engine.codebase_summary import get_summary as get_codebase_summary, invalidate as invalidate_summary
from agent.workspace_planner         import plan_changes, is_pure_chat
from agent.multi_file_executor       import execute_plan
from agent.react_loop                import run_react_loop
from agent.vibe_coder                import (
    is_vibe_request, detect_design_reference, build_ui_system_prompt,
    build_ui_user_message, extract_component_name, suggest_file_path,
)
from llm.vision        import describe, read_error, analyze_ui, analyze_diagram,                                is_vision_available, pick_vision_strategy
from memory.model_benchmark import record_outcome as record_benchmark, get_best_model, get_all_stats as get_benchmark_stats
from memory.preference_learner import suggest_new_preference, mark_suggestion_seen
from web.agent       import should_use_web, run_web_research
from knowledge_graph.architecture import (
    get_entry_points, get_core_modules, diff_changed_symbols
)
from agent.journal  import get_recent as get_journal_recent, get_stats as get_journal_stats
from agent.test_runner import run_regression, suggest_test_path, find_test_file
from memory.checkpoint  import create_checkpoint, list_checkpoints, restore_checkpoint
from memory.session_journal    import (
    new_feature_id, record_file_change, get_today_features,
    get_checkpoint_ids_for_feature,
)
from tools.consistency_checker import check_consistency, summarize_warnings
from tools.dead_code            import find_dead_code, format_dead_code_summary
from tools.todo_scanner         import scan_todos, format_todo_summary
from agent.pr_generator         import generate_pr_description, get_branch_info
from agent.test_driven          import (
    is_tdd_request, strip_tdd_prefix, run_tdd_cycle,
)
from memory.project_memory      import (
    store as memory_store, list_all as memory_list_all, delete as memory_delete,
    build_context as memory_build_context, detect_remember_request,
)
from memory.preference_learner import (
    record_accept, record_reject, get_preference_context, get_stats as get_pref_stats
)
from skills.skill_manager import get_manager as get_skill_manager
from knowledge_graph.builder import build_graph
from knowledge_graph.query   import find_callers, impact_analysis, get_file_symbols
from knowledge_graph.git_layer import repo_summary, function_history
from tools.runner   import RUNNABLE_LANGUAGES
from tools.sandbox  import run_sandboxed, detect_docker
from tools.differ   import unified_diff, diff_stats
from tools.patch_engine import apply_patches
from memory.edit_history import record_edit, undo_edit, get_history

app = FastAPI(title="Mini IDE", version="4.0.0-phase4")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# ── Global state ──────────────────────────────────────────────────────────────
_workspace: Optional[Path] = None
_drain_task: Optional[asyncio.Task] = None

# ── Startup / shutdown ────────────────────────────────────────────────────────
@app.on_event("startup")
async def _startup():
    asyncio.create_task(_drain_watcher_loop())

@app.on_event("shutdown")
async def _shutdown():
    stop_watcher()

async def _drain_watcher_loop():
    """Background task: drain the watchdog change queue every 5 s."""
    while True:
        await asyncio.sleep(5)
        if _workspace is None:
            continue
        for raw_path in set(drain_changes()):
            try:
                p = Path(raw_path)
                if p.exists():
                    await index_file(p, _workspace)
            except Exception:
                pass

# ── Helpers ───────────────────────────────────────────────────────────────────
def require_workspace() -> Path:
    if _workspace is None:
        raise HTTPException(400, "No workspace set.")
    return _workspace

def safe_resolve(rel: str, ws: Path) -> Path:
    clean  = rel.replace("\\", "/").lstrip("/")
    target = (ws / clean).resolve()
    if not str(target).startswith(str(ws.resolve())):
        raise HTTPException(403, "Path traversal not allowed.")
    return target

def workspace_inventory(ws: Path) -> dict:
    """Return a compact, non-content inventory for the Agent Workspace view."""
    files = directories = total_bytes = 0
    languages: Counter[str] = Counter()
    ignored = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".rag_cache"}
    for item in ws.rglob("*"):
        try:
            if any(part in ignored for part in item.relative_to(ws).parts):
                continue
            if item.is_dir():
                directories += 1
            elif item.is_file():
                files += 1
                total_bytes += item.stat().st_size
                suffix = item.suffix.lower().lstrip(".")
                if suffix:
                    languages[suffix] += 1
        except (OSError, PermissionError):
            continue
    return {
        "files": files, "directories": directories, "bytes": total_bytes,
        "languages": [{"name": name, "files": count} for name, count in languages.most_common(6)],
    }

# ── Workspace ─────────────────────────────────────────────────────────────────
class WorkspacePayload(BaseModel):
    path: str

@app.get("/api/workspace")
def get_workspace():
    if _workspace is None: return {"workspace": None, "name": None}
    return {"workspace": str(_workspace), "name": _workspace.name}

@app.post("/api/workspace/set")
async def set_workspace(payload: WorkspacePayload):
    global _workspace
    p = Path(payload.path.strip()).resolve()
    if not p.exists():  raise HTTPException(404, f"Not found: {payload.path}")
    if not p.is_dir():  raise HTTPException(400, f"Not a directory: {payload.path}")
    _workspace = p
    # Phase 4: start file watcher + kick off background indexing
    start_watcher(p)
    asyncio.create_task(index_workspace(p))
    # Milestone B: build knowledge graph in background
    asyncio.create_task(asyncio.to_thread(build_graph, p))
    # Sprint 2: detect coding conventions in background
    asyncio.create_task(asyncio.to_thread(_refresh_conventions, p))
    # Sprint 3: prime the codebase summary cache in background
    asyncio.create_task(asyncio.to_thread(get_codebase_summary, p))
    return {"workspace": str(_workspace), "name": _workspace.name}

# ── File tree ─────────────────────────────────────────────────────────────────
@app.get("/api/files")
def get_file_tree():
    ws = require_workspace()
    return list_directory(ws, ws)

# ── File CRUD ─────────────────────────────────────────────────────────────────
@app.get("/api/file")
def read_file_api(path: str = Query(...)):
    ws = require_workspace(); t = safe_resolve(path, ws)
    if not t.exists():  raise HTTPException(404, f"Not found: {path}")
    if t.is_dir():      raise HTTPException(400, "Path is a directory.")
    content, enc = read_file(t)
    return {"path":path,"name":t.name,"content":content,"encoding":enc,
            "language":detect_language(t),"size":t.stat().st_size}

class WritePayload(BaseModel):
    path: str
    content: str
    source: str = ""       # if set, edit is recorded in history
    description: str = ""  # human-readable change description
    language: str = ""     # used for preference learning + regression check

@app.post("/api/file/write")
async def write_file_api(payload: WritePayload):
    ws     = require_workspace()
    target = safe_resolve(payload.path, ws)
    regression_result = None

    # Record to edit history + checkpoint for AI-sourced writes (not manual Ctrl+S)
    if payload.source and target.exists():
        try:
            original, _ = read_file(target)
            record_edit(
                file_path   = payload.path,
                original    = original,
                updated     = payload.content,
                source      = payload.source,
                description = payload.description or f"AI edit via {payload.source}",
                workspace   = str(ws),
            )
            # Milestone C: checkpoint snapshot (separate from undo stack)
            create_checkpoint(payload.path, original, ws, label=payload.description)
        except Exception:
            pass

    write_file(target, payload.content)

    # Milestone C+G: regression check for AI writes (preference recording now
    # happens exclusively via /api/preferences/record to avoid double-counting
    # signals — that endpoint is always called alongside Apply/Cancel)
    if payload.source == "ai":
        lang = payload.language or detect_language(target)
        try:
            regression_result = await run_regression(payload.path, lang, ws)
        except Exception:
            regression_result = None

    return {
        "ok":         True,
        "path":       payload.path,
        "regression": regression_result,
    }

class CreatePayload(BaseModel):
    path: str; is_dir: bool = False

@app.post("/api/file/create")
def create_file_api(payload: CreatePayload):
    ws = require_workspace(); t = safe_resolve(payload.path, ws)
    if t.exists(): raise HTTPException(409, "Already exists.")
    create_file(t, payload.is_dir); return {"ok":True,"path":payload.path}

@app.delete("/api/file")
def delete_file_api(path: str = Query(...)):
    ws = require_workspace(); t = safe_resolve(path, ws)
    if not t.exists(): raise HTTPException(404, "Not found.")
    delete_file(t); return {"ok":True,"path":path}

class RenamePayload(BaseModel):
    old_path: str; new_path: str

@app.post("/api/file/rename")
def rename_api(payload: RenamePayload):
    ws = require_workspace()
    old = safe_resolve(payload.old_path, ws); new = safe_resolve(payload.new_path, ws)
    if not old.exists(): raise HTTPException(404, "Source not found.")
    if new.exists():     raise HTTPException(409, "Destination exists.")
    rename_path(old, new); return {"ok":True}

# ── LLM models ────────────────────────────────────────────────────────────────
@app.get("/api/models")
async def get_models():
    try:    return {"models": await list_models(), "ok": True}
    except Exception as e: return {"models":[],"ok":False,"error":str(e)}



# ── Checkpoint endpoints (Milestone C) ────────────────────────────────────────
@app.get("/api/checkpoints")
def get_checkpoints(path: str = Query(...)):
    ws = require_workspace()
    return {"checkpoints": list_checkpoints(path, ws)}

class RestorePayload(BaseModel):
    path: str
    checkpoint_id: str

@app.post("/api/checkpoints/restore")
def restore_checkpoint_api(payload: RestorePayload):
    ws = require_workspace()
    content = restore_checkpoint(payload.path, payload.checkpoint_id, ws)
    if content is None:
        raise HTTPException(404, "Checkpoint not found.")
    target = safe_resolve(payload.path, ws)
    # Snapshot current state before restoring, so this is itself undoable
    try:
        current, _ = read_file(target) if target.exists() else ("", "")
        create_checkpoint(payload.path, current, ws, label="before restore")
    except Exception:
        pass
    write_file(target, content)
    return {"ok": True, "path": payload.path, "content": content}


# ── Preference learning endpoints (Milestone C) ───────────────────────────────
class PreferencePayload(BaseModel):
    proposed:    str
    language:    str
    outcome:     str   # "accept" | "revised" | "reject"
    model:       str = ""
    task_type:   str = ""
    duration_ms: int = 0

@app.post("/api/preferences/record")
def record_preference(payload: PreferencePayload):
    if payload.outcome == "reject":
        record_reject(payload.proposed, payload.language)
    else:
        record_accept(payload.proposed, payload.language)

    # Milestone G: feed the same outcome into model benchmarking
    if payload.model and payload.task_type:
        record_benchmark(payload.model, payload.task_type, payload.outcome, payload.duration_ms)

    return {"ok": True}

@app.get("/api/preferences")
def get_preferences():
    return {"stats": get_pref_stats()}


# ── Model benchmarking + suggestion endpoints (Milestone G) ──────────────────
@app.get("/api/benchmark/best")
def benchmark_best(task_type: str = Query(...)):
    return {"best": get_best_model(task_type)}

@app.get("/api/benchmark/stats")
def benchmark_stats():
    return {"stats": get_benchmark_stats()}

@app.get("/api/preferences/suggestion")
def get_preference_suggestion():
    return {"suggestion": suggest_new_preference()}

class SuggestionSeenPayload(BaseModel):
    signal:   str
    language: str

@app.post("/api/preferences/suggestion/seen")
def mark_preference_suggestion_seen(payload: SuggestionSeenPayload):
    mark_suggestion_seen(payload.signal, payload.language)
    return {"ok": True}





# ── File upload + vision endpoints (Sprint 1) ─────────────────────────────────
import shutil as _shutil
import uuid   as _uuid

_UPLOADS_DIR = Path(__file__).parent / ".uploads"
_UPLOADS_DIR.mkdir(exist_ok=True)


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Accept any file upload from the chat panel.
    Saves to .uploads/, extracts text (or image data), returns attachment dict.
    """
    ext      = Path(file.filename or "file").suffix.lower()
    uid      = _uuid.uuid4().hex[:10]
    dest     = _UPLOADS_DIR / f"{uid}{ext}"

    try:
        with dest.open("wb") as f_out:
            _shutil.copyfileobj(file.file, f_out)
    finally:
        await file.close()

    # Run extraction in a thread (CPU-bound)
    attachment = await asyncio.to_thread(read_uploaded_file, dest)

    # For images: trigger vision model immediately so description is ready
    if attachment.get("type") == "image":
        b64   = attachment.get("base64", "")
        if b64:
            vision_ok = await is_vision_available()
            if vision_ok:
                strategy = await pick_vision_strategy("")   # default: general describe
                if strategy == "ui":
                    desc = await analyze_ui(b64)
                elif strategy == "error":
                    desc = await read_error(b64)
                elif strategy == "diagram":
                    desc = await analyze_diagram(b64)
                else:
                    desc = await describe(b64)
                attachment["description"] = desc
            else:
                attachment["description"] = ""
        attachment.pop("base64", None)   # don't send raw bytes back to frontend

    return {
        "ok":         True,
        "attachment": attachment,
        "server_path": str(dest),
    }


@app.post("/api/upload/describe")
async def describe_image_with_context(payload: dict):
    """
    Re-describe an already-uploaded image with a specific user question.
    Called when the user types a message alongside an attached image.
    """
    server_path = payload.get("server_path", "")
    question    = payload.get("question", "")

    if not server_path:
        raise HTTPException(400, "server_path is required")

    p = Path(server_path)
    if not p.exists() or not p.is_relative_to(_UPLOADS_DIR):
        raise HTTPException(404, "Upload not found")

    vision_ok = await is_vision_available()
    if not vision_ok:
        return {"description": "(vision model not available)"}

    strategy = await pick_vision_strategy(question)
    if strategy == "error":
        desc = await read_error(p)
    elif strategy == "ui":
        desc = await analyze_ui(p)
    elif strategy == "diagram":
        desc = await analyze_diagram(p)
    else:
        desc = await describe(p, question=question)

    return {"description": desc}


@app.get("/api/vision/status")
async def vision_status():
    available = await is_vision_available()
    return {"available": available, "model": "llama3.2-vision:11b"}


# ── Explainability + Architecture endpoints (Milestone E) ────────────────────
class ExplainPayload(BaseModel):
    request:  str
    original: str
    proposed: str
    language: str
    model:    str = "qwen3:8b"

@app.post("/api/explain")
async def explain_api(payload: ExplainPayload):
    explanation = await explain_change(
        payload.request, payload.original, payload.proposed,
        payload.language, payload.model,
    )
    return {"explanation": explanation}


class DiffImpactPayload(BaseModel):
    path:     str
    original: str
    proposed: str
    language: str = "python"

@app.post("/api/graph/diff-impact")
def diff_impact_api(payload: DiffImpactPayload):
    """
    Detect which symbols actually changed between original and proposed,
    then run impact analysis on each — surfaces caller counts before
    the user applies the edit.
    """
    ws = _workspace
    if not ws:
        return {"changed_symbols": [], "impacts": []}

    changed = diff_changed_symbols(payload.original, payload.proposed, payload.language)
    impacts = []
    for symbol in changed[:5]:   # cap to avoid excessive graph queries
        result = impact_analysis(symbol, ws)
        if result["callers"] or result["inheritors"]:
            impacts.append(result)

    return {"changed_symbols": changed, "impacts": impacts}


@app.get("/api/graph/architecture")
def graph_architecture():
    ws = _workspace
    if not ws:
        return {"entry_points": [], "core_modules": []}
    return {
        "entry_points":  get_entry_points(ws),
        "core_modules":  get_core_modules(ws),
    }


@app.get("/api/workspace/intelligence")
def workspace_intelligence():
    """A single, fast status surface for the agentic workspace UI."""
    ws = require_workspace()
    try:
        todo_count = len(scan_todos(ws))
    except Exception:
        todo_count = 0
    return {
        "workspace": str(ws),
        "name": ws.name,
        "inventory": workspace_inventory(ws),
        "architecture": {
            "entry_points": get_entry_points(ws),
            "core_modules": get_core_modules(ws),
        },
        "git": repo_summary(ws),
        "index": rag_status(),
        "todo_count": todo_count,
        "capabilities": [
            "Read and search every file in this workspace",
            "Trace imports, callers, and likely entry points",
            "Plan coordinated multi-file changes before editing",
            "Run workspace files and verify changes with tests",
            "Remember project decisions across sessions",
        ],
    }


# ── Agent journal + observability endpoints (Milestone D + F) ────────────────
@app.get("/api/journal")
def get_journal(limit: int = 40):
    from rag.retriever import get_search_stats
    return {
        "entries":   get_journal_recent(limit),
        "stats":     get_journal_stats(),
        "rag_stats": get_search_stats(),
    }

@app.get("/api/sandbox/status")
def sandbox_status():
    return {"docker_available": detect_docker()}


# ── Test generation endpoint (Milestone C) ────────────────────────────────────
@app.get("/api/tests/find")
def find_test_for_file(path: str = Query(...)):
    """Check if a test file already exists for the given source file."""
    ws = require_workspace()
    existing = find_test_file(path, ws)
    suggested = suggest_test_path(path, ws)
    return {"existing": existing, "suggested": suggested}




# ── Dev workflow + knowledge endpoints (Sprint 5) ─────────────────────────────
@app.get("/api/dead-code")
def dead_code_api():
    ws = require_workspace()
    dead = find_dead_code(ws)
    return {"dead_code": dead, "summary": format_dead_code_summary(dead)}


@app.get("/api/todos")
def todos_api():
    ws = require_workspace()
    todos = scan_todos(ws)
    return {"todos": todos, "summary": format_todo_summary(todos)}


@app.get("/api/git/branch-info")
def git_branch_info():
    ws = require_workspace()
    return get_branch_info(ws)


class PRDescriptionPayload(BaseModel):
    base_branch: str = ""
    model:       str = "qwen3:8b"

@app.post("/api/git/pr-description")
async def pr_description_api(payload: PRDescriptionPayload):
    ws = require_workspace()
    return await generate_pr_description(ws, payload.base_branch, payload.model)


# ── Project memory endpoints (Sprint 5) ───────────────────────────────────────
class MemoryStorePayload(BaseModel):
    text:     str
    category: str = "decision"

@app.post("/api/memory")
def memory_store_api(payload: MemoryStorePayload):
    entry_id = memory_store(payload.text, payload.category)
    return {"ok": True, "id": entry_id}

@app.get("/api/memory")
def memory_list_api():
    return {"memories": memory_list_all()}

@app.delete("/api/memory/{entry_id}")
def memory_delete_api(entry_id: str):
    ok = memory_delete(entry_id)
    return {"ok": ok}


# ── Code search endpoint (Sprint 5 — uses existing RAG index) ────────────────
@app.get("/api/search")
async def code_search_api(q: str = Query(...), k: int = Query(8)):
    if not q.strip():
        return {"results": []}
    hits = await semantic_search(q, k=k)
    return {
        "results": [
            {
                "path":  h.get("file_path", ""),
                "name":  h.get("name", ""),
                "type":  h.get("chunk_type", ""),
                "score": h.get("score", 0),
                "line":  h.get("start_line", 0),
            }
            for h in hits
        ]
    }


# ── Session + atomic apply endpoints (Sprint 4) ───────────────────────────────
@app.get("/api/session")
def get_session():
    return {"features": get_today_features()}


class ApplyMultiPayload(BaseModel):
    feature_request: str = ""
    files: list[dict]


@app.post("/api/apply-multi")
async def apply_multi(payload: ApplyMultiPayload):
    ws = require_workspace()
    feature_id  = new_feature_id()
    checkpoints: dict[str, str] = {}
    results     = []

    for f in payload.files:
        target   = safe_resolve(f["path"], ws)
        original = f.get("original", "")
        if target.exists() and original:
            try:
                cp = create_checkpoint(f["path"], original, ws,
                                       label=(payload.feature_request or "AI edit")[:60])
                checkpoints[f["path"]] = cp["id"]
            except Exception:
                checkpoints[f["path"]] = ""

    write_failed = False
    for f in payload.files:
        target  = safe_resolve(f["path"], ws)
        content = f.get("content", "")
        lang    = f.get("language", "")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            write_file(target, content)
            record_file_change(
                feature_id    = feature_id,
                request       = payload.feature_request or "AI edit",
                file_path     = f["path"],
                original      = f.get("original", ""),
                updated       = content,
                checkpoint_id = checkpoints.get(f["path"], ""),
                language      = lang,
                description   = f"AI edit — {(payload.feature_request or f['path'])[:60]}",
            )
            results.append({"path": f["path"], "ok": True})
        except Exception as e:
            write_failed = True
            results.append({"path": f["path"], "ok": False, "error": str(e)})

    if write_failed:
        for f in payload.files:
            cp_id = checkpoints.get(f["path"])
            if cp_id:
                try:
                    content = restore_checkpoint(f["path"], cp_id, ws)
                    if content is not None:
                        write_file(safe_resolve(f["path"], ws), content)
                except Exception:
                    pass
        return {"ok": False, "rolled_back": True, "results": results}

    return {"ok": True, "feature_id": feature_id, "results": results}


@app.post("/api/session/rollback-feature")
async def rollback_feature(payload: dict):
    feature_id = payload.get("feature_id", "")
    if not feature_id:
        raise HTTPException(400, "feature_id required")
    ws    = require_workspace()
    pairs = get_checkpoint_ids_for_feature(feature_id)
    rolled = []
    for file_path, cp_id in pairs:
        if not cp_id:
            continue
        content = restore_checkpoint(file_path, cp_id, ws)
        if content is not None:
            try:
                write_file(safe_resolve(file_path, ws), content)
                rolled.append(file_path)
            except Exception:
                pass
    return {"ok": True, "rolled_back": rolled}


# ── Skills endpoints (Milestone B) ───────────────────────────────────────────
@app.get("/api/skills")
def list_skills():
    return {"skills": get_skill_manager().list_skills()}

@app.post("/api/skills/{name}/enable")
def enable_skill(name: str):
    ok = get_skill_manager().enable(name)
    return {"ok": ok, "name": name}

@app.post("/api/skills/{name}/disable")
def disable_skill(name: str):
    ok = get_skill_manager().disable(name)
    return {"ok": ok, "name": name}

@app.get("/api/skills/marketplace")
async def skill_marketplace(q: str = ""):
    from skills.marketplace import search_skills
    results = await search_skills(q)
    return {"results": results}

@app.post("/api/skills/install")
async def install_skill(payload: dict):
    from skills.installer import install_from_url
    url = payload.get("url", "")
    if not url:
        raise HTTPException(400, "url is required")
    return await install_from_url(url)

@app.delete("/api/skills/{name}")
async def uninstall_skill(name: str):
    from skills.installer import uninstall
    return await uninstall(name)

@app.get("/api/skills/active")
def get_active_skills(path: str = Query(""), language: str = Query("")):
    ws = _workspace
    if not ws or not path:
        return {"skills": []}
    from tools.ast_parser import parse_symbols
    abs_p = (ws / path).resolve()
    syms = parse_symbols(abs_p, language) if abs_p.exists() else {}
    imports = syms.get("imports", [])
    mgr = get_skill_manager()
    return {"skills": mgr.active_names(path, imports)}


# ── Knowledge graph endpoints (Milestone B) ────────────────────────────────────
@app.get("/api/graph/callers")
def graph_callers(symbol: str = Query(...)):
    ws = _workspace
    if not ws:
        return {"callers": []}
    return {"callers": find_callers(symbol, ws)}

@app.get("/api/graph/impact")
def graph_impact(symbol: str = Query(...)):
    ws = _workspace
    if not ws:
        return impact_analysis(symbol, None) if False else {"symbol": symbol, "summary": "No workspace set."}
    return impact_analysis(symbol, ws)

@app.get("/api/graph/symbols")
def graph_symbols(path: str = Query(...)):
    ws = _workspace
    if not ws:
        return {"symbols": []}
    return {"symbols": get_file_symbols(path, ws)}

@app.get("/api/graph/git")
def graph_git():
    ws = _workspace
    if not ws:
        return {}
    return repo_summary(ws)

@app.get("/api/graph/history")
def graph_history(
    func: str  = Query(...),
    path: str  = Query(...),
    line: int  = Query(1),
):
    ws = _workspace
    if not ws:
        return {"history": []}
    return {"history": function_history(func, path, line, ws)}

# ── RAG endpoints (Phase 4) ───────────────────────────────────────────────────
@app.get("/api/rag/status")
def get_rag_status():
    return rag_status()

@app.get("/api/rag/search")
async def rag_search(q: str = Query(...), k: int = 5):
    """Direct semantic search endpoint (useful for debugging / future UI)."""
    results = await semantic_search(q, k=k)
    return {"results": results, "count": len(results)}

@app.post("/api/rag/reindex")
async def rag_reindex():
    """Force a full re-index of the current workspace."""
    ws = require_workspace()
    asyncio.create_task(index_workspace(ws))
    return {"ok": True, "message": "Re-indexing started in background."}

# ── Intent classifier (confidence gate) ──────────────────────────────────────
_INTENT_PROMPT = ('Classify this code editor request. Reply ONLY with valid JSON:\n'
                  '{{"intent":"explain|chat|edit|create|delete|refactor",'
                  '"risk":"safe|moderate|destructive","confidence":0.0}}\n\nRequest: "{msg}"')
_DESTRUCTIVE   = {"delete","refactor"}
_CONF_THRESH   = 0.68

async def classify_intent(message: str) -> dict:
    prompt   = _INTENT_PROMPT.format(msg=message[:500])
    messages = [
        {"role":"system","content":"You are a JSON-only intent classifier."},
        {"role":"user",  "content":prompt},
    ]
    full = ""
    try:
        async for tok in stream_chat(MODELS["intent"], messages, temperature=0.0, num_ctx=512):
            full += tok
            if len(full) > 300: break
        m = re.search(r"\{.*?\}", full, re.DOTALL)
        if m:
            d = json.loads(m.group())
            return {"intent":str(d.get("intent","chat")),
                    "risk":str(d.get("risk","safe")),
                    "confidence":float(d.get("confidence",0.5))}
    except Exception:
        pass
    return {"intent":"chat","risk":"safe","confidence":1.0}


# ── Quality pipeline helper (Milestone A, hardened) ──────────────────────────
def _extract_code_block(text: str) -> str | None:
    """
    Extract the content of the first fenced code block.
    Falls back to treating an UNTERMINATED opening fence (no closing ```)
    as a code block running to the end of the text — handles models that
    forget to close the fence or get cut off mid-stream.
    """
    import re as _re
    m = _re.search(r"```(?:\w+)?\n([\s\S]*?)```", text)
    if m:
        return m.group(1)
    # Fallback: dangling open fence with no closing backticks
    m2 = _re.search(r"```(?:\w+)?\n([\s\S]+)$", text)
    if m2 and len(m2.group(1).strip()) > 10:
        return m2.group(1)
    return None


async def _ensure_fenced_response(
    raw_response: str,
    language:     str,
    model:        str,
) -> str | None:
    """
    If the model's response has no detectable code block, ask it to
    reformat its own previous answer into a single fenced code block.
    One quick low-temperature call — returns the reformatted full text,
    or None if the reformat attempt also fails.
    """
    ext = language[:2] if language else ""
    messages = [
        {"role": "system", "content": (
            "Reformat the following text. If it contains code, wrap the "
            "COMPLETE code in a single fenced code block using triple "
            "backticks with the language name, like ```" + (ext or "python") + "\n"
            "...code...\n```. Keep any explanation before the block. "
            "Do not add new content or remove any code — just fix the formatting."
        )},
        {"role": "user", "content": raw_response[:6000]},
    ]
    buf = ""
    try:
        async for tok in stream_chat(model, messages, temperature=0.0, num_ctx=4096):
            buf += tok
    except Exception:
        return None

    return buf if _extract_code_block(buf) else None


async def _quality_pipeline(
    websocket,
    code:         str,
    language:     str,
    request:      str,
    original:     str,
    coder_model:  str,
    risk:         str = "safe",
    file_path:    str = "",
) -> tuple[str, dict]:
    """
    Milestone D: delegates to the router-driven agent pipeline.
    Kept as a thin wrapper so the ws_chat call site stays unchanged.
    """
    return await agent_run_pipeline(
        websocket    = websocket,
        code         = code,
        language     = language,
        request      = request,
        original     = original,
        coder_model  = coder_model,
        risk         = risk,
        file_path    = file_path,
    )


# ── Convention cache (Sprint 2) ───────────────────────────────────────────────
_conventions: dict = {}


def _refresh_conventions(workspace: Path) -> None:
    """Run convention detection and cache the result."""
    global _conventions
    try:
        _conventions = detect_conventions(workspace)
    except Exception:
        pass


# ── WebSocket chat (Phase 4) ──────────────────────────────────────────────────
@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    try:
        ollama_ok = await check_connection()
        await websocket.send_json({"type":"connected","ollama":ollama_ok,
                                   "rag": rag_status()})
        while True:
            raw = await websocket.receive_text()
            try:   msg = json.loads(raw)
            except: await websocket.send_json({"type":"error","message":"Invalid JSON."}); continue

            if msg.get("type") != "chat": continue

            user_message   = msg.get("message","").strip()
            model          = msg.get("model","qwen3:8b")
            file_path      = msg.get("file_path","")
            file_content   = msg.get("file_content","")
            include_file   = bool(msg.get("include_file",False))
            language       = msg.get("language","")
            history        = msg.get("history",[])
            open_tab_paths = msg.get("open_tabs",[])
            attachments    = msg.get("attachments", [])   # Sprint 1: [{type, name, text, description, server_path}]

            if not user_message and not attachments: continue

            # Sprint 1: build attachment context string and inject into user message
            attachment_context = ""
            if attachments:
                parts = []
                for att in attachments:
                    ctx = format_attachment_context(att)
                    if ctx:
                        parts.append(ctx)
                if parts:
                    attachment_context = "\n\n".join(parts)
                    # Re-describe images with the actual user question if needed
                    for att in attachments:
                        if att.get("type") == "image" and att.get("server_path") and user_message:
                            try:
                                vision_ok = await is_vision_available()
                                if vision_ok:
                                    strategy = await pick_vision_strategy(user_message)
                                    p = Path(att["server_path"])
                                    if strategy == "error":
                                        desc = await read_error(p)
                                    elif strategy == "ui":
                                        desc = await analyze_ui(p)
                                    elif strategy == "diagram":
                                        desc = await analyze_diagram(p)
                                    else:
                                        desc = await describe(p, question=user_message)
                                    att["description"] = desc
                                    # Rebuild context with updated description
                                    parts2 = [format_attachment_context(a) for a in attachments]
                                    attachment_context = "\n\n".join(p2 for p2 in parts2 if p2)
                            except Exception:
                                pass

                # Append attachment context to user message for the LLM
                if attachment_context and user_message:
                    user_message = user_message + "\n\n" + attachment_context
                elif attachment_context:
                    user_message = attachment_context

            if not user_message: continue

            # ── Confidence gate ───────────────────────────────────────────────
            classification = {"intent": "chat", "risk": "safe", "confidence": 1.0}
            if include_file and file_content:
                classification = await classify_intent(user_message)
                cl = classification
                if cl["risk"] == "destructive" and cl["confidence"] < _CONF_THRESH:
                    await websocket.send_json({
                        "type":"clarify",
                        "message":(f"I want to be sure I understand — it looks like you want to "
                                   f"**{cl['intent']}** something. Could you be more specific "
                                   f"about exactly what you want changed?"),
                        "intent":cl["intent"],"confidence":cl["confidence"],
                    }); continue

            # ── Context engine (Phase 3) ──────────────────────────────────────
            context_string  = ""
            context_summary = {}
            excluded_paths: set[str] = set()

            if include_file and file_content and _workspace:
                try:
                    ctx = build_workspace_context(
                        workspace=_workspace, file_path=file_path,
                        file_content=file_content, language=language,
                        open_tab_paths=open_tab_paths, model=model,
                    )
                    context_string  = ctx.to_prompt_string()
                    context_summary = ctx.summary()
                    excluded_paths  = {file_path} | set(open_tab_paths)
                except Exception:
                    context_string = f"```{language}\n{file_content}\n```"

            # ── RAG search (Phase 4) ──────────────────────────────────────────
            rag_hits: list[dict] = []
            rag_section = ""
            try:
                rag_hits = await semantic_search(user_message, k=4,
                                                 exclude_paths=excluded_paths)
                if rag_hits:
                    rag_section = "\n\n---\n\n" + format_rag_context(rag_hits)
            except Exception:
                pass

            # ── Web research (Milestone E) — selective, not on every message ──
            web_section = ""
            web_sources: list[dict] = []
            if should_use_web(user_message):
                await websocket.send_json({
                    "type": "reviewing", "step": "web",
                    "message": "Searching the web…",
                })
                try:
                    web_result = await run_web_research(user_message, model=model)
                    if web_result["used"]:
                        web_section = "\n\n---\n\n" + web_result["context"]
                        web_sources = web_result["sources"]
                except Exception:
                    pass

            # Merge context + RAG + web (priority order: file > RAG > web)
            full_context = context_string + rag_section + web_section

            # ── Tell frontend what was included ───────────────────────────────
            await websocket.send_json({
                "type": "context",
                "summary": {
                    **context_summary,
                    "rag_hits": [
                        {"path": r["file_path"], "name": r.get("name",""),
                         "type": r.get("chunk_type",""), "score": r.get("score",0)}
                        for r in rag_hits
                    ],
                    "rag_status": rag_status()["status"],
                    "web_sources": web_sources,
                },
            })

            # ── Sprint 5: "remember that..." explicit project memory ───────────
            _remember_fact = detect_remember_request(user_message)
            if _remember_fact:
                memory_store(_remember_fact, category="preference")
                await websocket.send_json({
                    "type":    "memory_stored",
                    "message": f"📌 Remembered: {_remember_fact}",
                })
                await websocket.send_json({"type": "done", "full": f"Got it — I'll remember: {_remember_fact}"})
                continue

            # ── Sprint 5: TDD mode ──────────────────────────────────────────────
            if is_tdd_request(user_message) and _workspace and language:
                _feature_request = strip_tdd_prefix(user_message)
                _test_conv_note  = build_prompt_note(_conventions, language) if _conventions else ""

                from agent.test_runner import suggest_test_path
                _impl_path = file_path or "new_feature.py"
                _test_path = suggest_test_path(_impl_path, _workspace)

                _tdd_result = await run_tdd_cycle(
                    websocket        = websocket,
                    feature_request  = _feature_request,
                    language         = language,
                    workspace        = _workspace,
                    impl_path        = _impl_path,
                    test_path        = _test_path,
                    test_convention  = _test_conv_note,
                    model            = model,
                )

                if not _tdd_result.get("ok"):
                    await websocket.send_json({"type": "error",
                        "message": _tdd_result.get("error", "TDD generation failed.")})
                    continue

                await websocket.send_json({
                    "type":      "tdd_done",
                    "test_path": _test_path,
                    "impl_path": _impl_path,
                    "test_code": _tdd_result["test_code"],
                    "impl_code": _tdd_result["impl_code"],
                    "passed":    _tdd_result["passed"],
                    "attempts":  _tdd_result["attempts"],
                })
                continue

            # ── VS Code-style ReAct agent (replaces old planner→executor) ────
            # True agentic loop: Thought → Tool → Observation → repeat until done
            # Falls back to classic chat if request is pure question or not edit-like.
            _use_react = (
                _workspace is not None
                and not is_pure_chat(user_message)
                and classification.get("intent", "chat") in ("edit", "refactor", "fix", "create", "chat")
                and not is_vibe_request(user_message)
            )
            # Only use ReAct for requests that look like they need workspace exploration/edits.
            # Pure chat with no workspace edit intent still goes to streaming fallback.
            _is_edit_intent = classification.get("intent", "chat") in ("edit", "refactor", "fix", "create")
            _should_react = _use_react and _is_edit_intent

            if _should_react:
                # Build workspace snapshot for initial context
                try:
                    _summary = await asyncio.to_thread(get_codebase_summary, _workspace)
                    _mem_ctx = memory_build_context()
                    if _mem_ctx:
                        _summary = _mem_ctx + "\n\n" + _summary
                except Exception:
                    _summary = ""

                # Merge RAG + web context already fetched, but ReAct has tools to fetch more
                _initial_context = _summary
                if web_section or rag_section:
                    _initial_context = (_initial_context + "\n\n" + web_section + rag_section).strip()

                # Run the VS Code-like ReAct loop — streams tool calls live
                try:
                    _react_result = await run_react_loop(
                        websocket        = websocket,
                        request          = user_message,
                        workspace        = _workspace,
                        model            = model,
                        history          = history,
                        codebase_summary = _initial_context,
                        max_iterations   = 14,
                        language         = language,
                        file_path        = file_path,
                        file_content     = file_content,
                    )
                    # Invalidate summary cache if any files were touched
                    if _react_result.get("files_changed"):
                        invalidate_summary()
                        # Also record to session journal for observability
                        try:
                            from memory.session_journal import record_file_change as _rec
                            from memory.checkpoint import create_checkpoint as _cc
                            fid = new_feature_id()
                            for fpath in _react_result["files_changed"]:
                                try:
                                    # create checkpoint for undo
                                    abs_p = (_workspace / fpath).resolve()
                                    if abs_p.exists():
                                        content, _ = read_file(abs_p)
                                        _cc(fpath, content, _workspace, label=user_message[:60])
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    # Also emit a legacy all_done for frontends that expect it (no-op if no files)
                    if _react_result.get("files_changed"):
                        await websocket.send_json({
                            "type": "react_files_changed",
                            "files": _react_result["files_changed"],
                            "iterations": _react_result.get("iterations", 0),
                        })
                except Exception as _react_err:
                    await websocket.send_json({
                        "type": "agent_thought",
                        "thought": f"ReAct loop error: {_react_err} — falling back to chat",
                    })
                    # Fall through to chat fallback below
                    _should_react = False

                if _should_react:
                    continue  # ReAct handled the request, skip chat fallback

            # Legacy fallback: if ReAct not triggered but planner would have run,
            # keep single planner pass for backward compat (optional, not used now)
            _use_planner = False

            # ── Build messages and stream (single-file / chat fallback) ───────
            task   = "edit" if include_file else "chat"
            syspmt = get_system_prompt(task, language)

            # Milestone B: prepend active skill context to system prompt
            if file_path and _workspace:
                from tools.ast_parser import parse_symbols as _ps
                _abs  = (_workspace / file_path).resolve()
                _syms = _ps(_abs, language) if _abs.exists() else {}
                _skill_prefix = get_skill_manager().build_system_prompt_prefix(
                    file_path, _syms.get("imports", [])
                )
                if _skill_prefix:
                    syspmt = _skill_prefix + "\n\n" + syspmt

            # Milestone C: prepend learned developer preferences
            if language:
                _pref_ctx = get_preference_context(language)
                if _pref_ctx:
                    syspmt = syspmt + "\n\n" + _pref_ctx

            # Sprint 2: inject auto-detected convention note
            if _conventions and language:
                _conv_note = build_prompt_note(_conventions, language)
                if _conv_note:
                    syspmt = syspmt + "\n\n" + _conv_note

            # Sprint 5: inject long-term project memory
            _mem_ctx_chat = memory_build_context()
            if _mem_ctx_chat:
                syspmt = syspmt + "\n\n" + _mem_ctx_chat

            # Sprint 2: vibe coding — detect and route design/UI requests
            _vibe_syspmt = syspmt
            if is_vibe_request(user_message) and _workspace:
                _design_ref    = detect_design_reference(user_message)
                _comp_name     = extract_component_name(user_message)
                _conv_note_vibe = build_prompt_note(_conventions, language) if _conventions else ""

                # If there's an image attachment, its description is already in user_message.
                # Build a rich UI generation system prompt instead of the default edit prompt.
                _vibe_syspmt = build_ui_system_prompt(
                    ui_description   = user_message,
                    existing_stack   = "React/JSX" if language in ("javascript","jsx","typescript","tsx") else language,
                    design_reference = _design_ref,
                    convention_note  = _conv_note_vibe,
                )
                # Suggest a save path so the user sees "Save as new file" pointing to the right place
                _suggested_path = suggest_file_path(_comp_name, _workspace)
                await websocket.send_json({
                    "type":         "vibe_plan",
                    "component":    _comp_name,
                    "suggested_path": _suggested_path,
                    "has_reference": _design_ref is not None,
                    "reference":    _design_ref.get("name") if _design_ref else None,
                })
                syspmt      = _vibe_syspmt
                user_message = build_ui_user_message(user_message, user_message, _comp_name)

            msgs   = (build_messages_with_context(syspmt, full_context, history, user_message)
                      if full_context else
                      build_messages(syspmt, history, user_message))

            full_response = ""
            try:
                async for token in stream_chat(model, msgs):
                    full_response += token
                    await websocket.send_json({"type":"token","content":token})
                await websocket.send_json({"type":"done","full":full_response})

                # Milestone A+D: post-generation quality pipeline
                if include_file and task == "edit":
                    code_block = _extract_code_block(full_response)

                    # Reliability fix: model didn't fence its code properly —
                    # ask it to reformat its own answer before giving up.
                    if not code_block:
                        await websocket.send_json({
                            "type": "reviewing", "step": "reformat",
                            "message": "Response wasn't formatted as code — reformatting…",
                        })
                        reformatted = await _ensure_fenced_response(full_response, language, model)
                        if reformatted:
                            code_block = _extract_code_block(reformatted)
                            full_response = reformatted
                            await websocket.send_json({
                                "type": "reformatted", "full": full_response,
                            })

                    if code_block:
                        _risk = classification.get("risk", "safe")
                        final_code, review = await _quality_pipeline(
                            websocket   = websocket,
                            code        = code_block,
                            language    = language,
                            request     = user_message,
                            original    = file_content,
                            coder_model = model,
                            risk        = _risk,
                            file_path   = file_path,
                        )
                        await websocket.send_json({
                            "type":        "review_done",
                            "ok":          review.get("ok", True),
                            "verified":    review.get("verified", False),
                            "issues":      review.get("issues", []),
                            "warnings":    review.get("warnings", []),
                            "revised":     review.get("revised", False),
                            "security":    review.get("security"),
                            "performance": review.get("performance"),
                            "agents_run":  review.get("agents_run", []),
                            "trust":       review.get("trust"),
                            "intent":      classification.get("intent", "chat"),
                            "fixed_code":  final_code if review.get("revised") else None,
                        })
                    else:
                        # Reformat also failed — let the user know plainly
                        await websocket.send_json({
                            "type": "format_warning",
                            "message": (
                                "I couldn't detect a clean code block in this response. "
                                "Try rephrasing your request, or switch to qwen3:8b "
                                "which follows formatting instructions more reliably."
                            ),
                        })

            except httpx.ConnectError:
                await websocket.send_json({"type":"error",
                    "message":"Cannot connect to Ollama. Run: ollama serve"})
            except httpx.HTTPStatusError as e:
                await websocket.send_json({"type":"error",
                    "message":f"Ollama {e.response.status_code} — run: ollama pull {model}"})
            except Exception as e:
                await websocket.send_json({"type":"error","message":f"Error: {e}"})

    except (WebSocketDisconnect, RuntimeError):
        pass



# ── Diff endpoint (Phase 6) ───────────────────────────────────────────────────
class DiffPayload(BaseModel):
    path:     str
    content:  str   # proposed new content
    original: str = ""  # if empty, read from disk

@app.post("/api/diff")
def generate_diff(payload: DiffPayload):
    """Generate a unified diff between original and proposed content."""
    ws = require_workspace()
    original = payload.original
    if not original:
        target = safe_resolve(payload.path, ws)
        if target.exists() and target.is_file():
            original, _ = read_file(target)
    result_diff  = unified_diff(original, payload.content, payload.path)
    stats        = diff_stats(original, payload.content)
    return {"diff": result_diff, "stats": stats, "path": payload.path}

# ── Multi-file patch (Phase 6) ────────────────────────────────────────────────
class PatchPayload(BaseModel):
    patches:     list[dict]
    description: str = ""

@app.post("/api/patch")
def apply_patch(payload: PatchPayload):
    """Apply a list of structured patches atomically."""
    ws  = require_workspace()
    res = apply_patches(payload.patches, ws)
    if res["ok"] and payload.description:
        for rel in res.get("applied", []):
            try:
                target = (ws / rel).resolve()
                if target.exists():
                    content, _ = read_file(target)
                    record_edit(rel, "", content, "patch", payload.description, str(ws))
            except Exception:
                pass
    return res

# ── Edit history (Phase 6) ────────────────────────────────────────────────────
@app.get("/api/history")
def edit_history(limit: int = 60):
    ws = _workspace
    return {"history": get_history(workspace=str(ws) if ws else "", limit=limit)}

@app.post("/api/undo/{edit_id}")
def undo_edit_endpoint(edit_id: int):
    """Revert a specific AI edit to its original content."""
    ws     = require_workspace()
    result = undo_edit(edit_id)
    if not result:
        raise HTTPException(404, "Edit not found or already reverted.")
    target = safe_resolve(result["file_path"], ws)
    write_file(target, result["content"])
    return {"ok": True, "file_path": result["file_path"]}


# ── WebSocket /ws/run — code execution + auto-fix (Phase 5) ──────────────────
@app.websocket("/ws/run")
async def ws_run(websocket: WebSocket):
    await websocket.accept()
    try:
        await websocket.send_json({
            "type":      "connected",
            "runnable":  list(RUNNABLE_LANGUAGES),
        })
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type":"error","message":"Invalid JSON."})
                continue

            if msg.get("type") != "run":
                continue

            file_path    = msg.get("file_path", "")
            language     = msg.get("language",  "")
            auto_fix     = bool(msg.get("auto_fix", False))
            model        = msg.get("model", "deepseek-coder:6.7b")
            max_attempts = int(msg.get("max_attempts", 3))

            if not file_path or _workspace is None:
                await websocket.send_json({
                    "type":"error","message":"No file or workspace set."
                })
                continue

            if language not in RUNNABLE_LANGUAGES:
                await websocket.send_json({
                    "type":"error",
                    "message":f"Cannot run {language} files. "
                              f"Supported: {', '.join(sorted(RUNNABLE_LANGUAGES))}"
                })
                continue

            if auto_fix:
                # Full ReAct loop
                async for event in run_with_autofix(
                    file_path, language, _workspace, model, max_attempts
                ):
                    await websocket.send_json(event)
            else:
                # Simple single run
                await websocket.send_json({
                    "type": "agent_step", "step": 1,
                    "action": "run",
                    "thought": f"Running `{file_path}`…",
                })
                result = await run_sandboxed(file_path, _workspace, language)
                await websocket.send_json({
                    "type": "run_result",
                    **result,
                    "attempt": 1,
                })
                await websocket.send_json({
                    "type":    "agent_done",
                    "success": result["success"],
                    "message": "✓ Done." if result["success"] else "✗ Error.",
                })

    except (WebSocketDisconnect, RuntimeError):
        pass

# ── Language detection ────────────────────────────────────────────────────────
_LANG = {".py":"python",".pyw":"python",".js":"javascript",".jsx":"javascript",
         ".mjs":"javascript",".ts":"typescript",".tsx":"typescript",
         ".json":"json",".jsonc":"json",".html":"html",".htm":"html",
         ".css":"css",".scss":"scss",".less":"less",".md":"markdown",
         ".mdx":"markdown",".yml":"yaml",".yaml":"yaml",".toml":"ini",
         ".ini":"ini",".cfg":"ini",".sh":"shell",".bash":"shell",".zsh":"shell",
         ".bat":"bat",".cmd":"bat",".rs":"rust",".go":"go",".cpp":"cpp",
         ".cc":"cpp",".cxx":"cpp",".c":"c",".h":"c",".java":"java",
         ".kt":"kotlin",".sql":"sql",".txt":"plaintext",".env":"ini",
         ".xml":"xml",".svg":"xml",".vue":"html",".rb":"ruby",".php":"php"}

def detect_language(p: Path) -> str:
    n = p.name.lower()
    if n in ("dockerfile","makefile"): return n
    return _LANG.get(p.suffix.lower(),"plaintext")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
