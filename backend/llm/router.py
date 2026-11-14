"""
llm/router.py — Mini IDE Phase 2
Maps task type + file language → the right model and system prompt.
Phase 3 will add: intent classification via Qwen 0.5B, token budget.
"""
from pathlib import Path

# ── Default model assignments ─────────────────────────────────────────────────
# These can be overridden at request time via the UI model selector.
# Updated 2026-08-27 to match locally available Ollama models.
MODELS = {
    "intent": "qwen2.5:1.5b",                              # 986 MB — fast classifier
    "code":   "deepseek-coder:6.7b",                       # 3.8 GB — code specialist (still available)
    "chat":   "qwen3:8b",                                  # 5.2 GB — best general chat/edit
    "reason": "artifish/llama3.2-uncensored:latest",       # 2.2 GB — reasoning / critic
}

# ── Per-language expert prefix ────────────────────────────────────────────────
_LANG_EXPERT: dict[str, str] = {
    "python":     "You are an expert Python developer.",
    "javascript": "You are an expert JavaScript and React developer.",
    "typescript": "You are an expert TypeScript developer.",
    "rust":       "You are an expert Rust systems programmer.",
    "go":         "You are an expert Go developer.",
    "sql":        "You are a SQL and database design expert.",
    "css":        "You are an expert in CSS and web styling.",
    "html":       "You are an expert in HTML and web development.",
    "json":       "You are an expert in data formats and JSON schemas.",
    "markdown":   "You are an expert technical writer.",
    "shell":      "You are an expert in shell scripting and Unix tools.",
    "yaml":       "You are an expert in configuration and DevOps tooling.",
}

# ── System prompts ────────────────────────────────────────────────────────────
_CHAT_BASE = (
    "You are an expert AI assistant embedded in Mini IDE, a locally-running code editor. "
    "Help the developer understand, write, improve, and debug code. "
    "Be concise and direct. "
    "When showing code, always use fenced code blocks with the correct language tag."
)

_EDIT_BASE = (
    "You are an expert AI code editor embedded in Mini IDE. "
    "The user has shared the full content of a file. "
    "When the user asks you to make changes:\n"
    "  1. Put any explanation BEFORE the code block.\n"
    "  2. Output the COMPLETE updated file inside a SINGLE fenced code block.\n"
    "  3. Do NOT truncate, summarise, or abbreviate any part of the file.\n"
    "  4. Preserve the original indentation style and formatting conventions.\n"
    "  5. Make only the changes the user requests — nothing else.\n\n"
    "FORMAT EXAMPLE — your code MUST look exactly like this:\n"
    "Here's the updated function with error handling added.\n\n"
    "```python\n"
    "def example():\n"
    "    return 42\n"
    "```\n\n"
    "CRITICAL: Always wrap code in triple backticks with the language name "
    "right after the opening backticks (e.g. ```python), and ALWAYS close "
    "the block with a matching ``` on its own line. Never leave a code "
    "block unclosed. Never output code without fencing."
)


def get_system_prompt(task: str = "chat", language: str = "") -> str:
    """Return the system prompt for the given task + language combination."""
    lang_hint = _LANG_EXPERT.get(language.lower(), "")
    base      = _EDIT_BASE if task == "edit" else _CHAT_BASE
    return f"{lang_hint}\n\n{base}".strip() if lang_hint else base


# ── Message assembly ──────────────────────────────────────────────────────────
MAX_HISTORY_TURNS = 20   # cap conversation history to avoid blowing context
MAX_FILE_CHARS    = 50_000  # ~12k tokens — safe upper bound for all 5 models


def build_messages(
    system_prompt: str,
    history: list[dict],        # [{"role": "user"|"assistant", "content": "..."}]
    user_message: str,
    file_path:    str  = "",
    file_content: str  = "",
    include_file: bool = False,
) -> list[dict]:
    """
    Assemble the full messages list for Ollama's /api/chat.

    If include_file is True, the current file is injected as a synthetic
    user→assistant exchange before the conversation history, so the model
    always has fresh context on the file regardless of how old the history is.
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # Inject file as context (trimmed to avoid context overflow)
    if include_file and file_content and file_path:
        ext      = Path(file_path).suffix.lstrip(".") or "text"
        snippet  = file_content[:MAX_FILE_CHARS]
        trimmed  = len(file_content) > MAX_FILE_CHARS
        note     = "\n\n[File truncated — showing first 50,000 characters]" if trimmed else ""
        file_msg = (
            f"Here is the current file `{file_path}`:\n\n"
            f"```{ext}\n{snippet}{note}\n```"
        )
        messages.append({"role": "user",      "content": file_msg})
        messages.append({"role": "assistant", "content": "I can see the file. What would you like to do?"})

    # Append capped conversation history
    for turn in history[-MAX_HISTORY_TURNS:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    # Current user turn
    messages.append({"role": "user", "content": user_message})

    return messages


# ── Phase 3: context-aware message builder ────────────────────────────────────
def build_messages_with_context(
    system_prompt: str,
    context_string: str,     # from WorkspaceContext.to_prompt_string()
    history: list[dict],
    user_message: str,
) -> list[dict]:
    """
    Build the messages list using the full workspace context (Phase 3+).
    Replaces build_messages() when a WorkspaceContext is available.
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    if context_string.strip():
        messages.append({
            "role":    "user",
            "content": f"Here is my workspace context:\n\n{context_string}",
        })
        messages.append({
            "role":    "assistant",
            "content": "I can see your workspace. What would you like to do?",
        })

    for turn in history[-MAX_HISTORY_TURNS:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_message})
    return messages
