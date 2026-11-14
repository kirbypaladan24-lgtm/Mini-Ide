"""
tools/file_reader.py — Mini IDE Sprint 1

Extracts readable content from uploaded files so the AI can work with them.
All extraction is synchronous and CPU-bound (runs via asyncio.to_thread).

Supported:
  .pdf          → PyMuPDF text extraction, page by page
  .docx / .doc  → python-docx paragraphs + tables
  .csv          → markdown table (first 100 rows)
  .json         → pretty-printed, capped at 12k chars
  .png/.jpg/... → raw bytes for vision model (llama3.2-vision:11b)
  everything else → plain text, capped at 12k chars
"""
from __future__ import annotations

import base64
import csv
import json
from pathlib import Path

try:
    import fitz as _fitz     # PyMuPDF
    PDF_OK = True
except ImportError:
    _fitz  = None            # type: ignore
    PDF_OK = False

try:
    import docx as _docx     # python-docx
    DOCX_OK = True
except ImportError:
    _docx   = None           # type: ignore
    DOCX_OK = False

_MAX_CHARS = 12_000
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
_MIME_MAP   = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
    ".tiff": "image/tiff",
}


# ── Main dispatcher ───────────────────────────────────────────────────────────
def read_uploaded_file(path: Path) -> dict:
    """
    Read a file and return a dict describing its content.

    Return shape:
      {
        "type":      str,           # "image" | "pdf" | "docx" | "csv" | "json" | "text" | "error"
        "name":      str,           # original filename
        "text":      str,           # extracted text (empty for images)
        "base64":    str | None,    # base64 image data (images only)
        "mime":      str | None,    # MIME type (images only)
        "truncated": bool,
      }
    """
    ext  = path.suffix.lower()
    name = path.name

    if ext in _IMAGE_EXTS:
        try:
            raw = path.read_bytes()
            return {
                "type":      "image",
                "name":      name,
                "text":      "",
                "base64":    base64.b64encode(raw).decode(),
                "mime":      _MIME_MAP.get(ext, "image/png"),
                "truncated": False,
            }
        except Exception as e:
            return _err(name, f"Could not read image: {e}")

    if ext == ".pdf":
        text = read_pdf(path)
        return _ok("pdf", name, text)

    if ext in (".docx", ".doc"):
        text = read_docx(path)
        return _ok("docx", name, text)

    if ext == ".csv":
        text = read_csv_file(path)
        return _ok("csv", name, text)

    if ext == ".json":
        text = read_json_file(path)
        return _ok("json", name, text)

    # Plaintext fallback (includes .txt, .md, .py, .js, etc.)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        trunc = len(text) > _MAX_CHARS
        return _ok("text", name, text[:_MAX_CHARS], truncated=trunc)
    except Exception as e:
        return _err(name, f"Could not read file: {e}")


# ── Specific readers ──────────────────────────────────────────────────────────
def read_pdf(path: Path) -> str:
    if not PDF_OK:
        return "(PDF reading unavailable — run: pip install pymupdf)"
    try:
        doc    = _fitz.open(str(path))
        pages  = []
        total  = 0
        for i, page in enumerate(doc, 1):
            text = page.get_text()
            if total + len(text) > _MAX_CHARS:
                text = text[: _MAX_CHARS - total]
                pages.append(f"[Page {i}]\n{text}\n(truncated)")
                break
            pages.append(f"[Page {i}]\n{text}")
            total += len(text)
        doc.close()
        return "\n\n".join(pages)
    except Exception as e:
        return f"(PDF extraction error: {e})"


def read_docx(path: Path) -> str:
    if not DOCX_OK:
        return "(DOCX reading unavailable — run: pip install python-docx)"
    try:
        doc   = _docx.Document(str(path))
        parts: list[str] = []
        total = 0

        for para in doc.paragraphs:
            t = para.text.strip()
            if not t:
                continue
            if total + len(t) > _MAX_CHARS:
                break
            parts.append(t)
            total += len(t)

        for table in doc.tables:
            for row in table.rows:
                cells    = [c.text.strip() for c in row.cells]
                row_text = " | ".join(cells)
                if total + len(row_text) > _MAX_CHARS:
                    break
                parts.append(row_text)
                total += len(row_text)

        return "\n".join(parts)
    except Exception as e:
        return f"(DOCX extraction error: {e})"


def read_csv_file(path: Path, max_rows: int = 100) -> str:
    try:
        rows: list[str] = []
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader):
                if i > max_rows:
                    rows.append(f"… ({i} rows total, showing first {max_rows})")
                    break
                rows.append(" | ".join(row))
        return "\n".join(rows)
    except Exception as e:
        return f"(CSV extraction error: {e})"


def read_json_file(path: Path) -> str:
    try:
        raw  = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(raw)
        out  = json.dumps(data, indent=2)
        if len(out) > _MAX_CHARS:
            return out[:_MAX_CHARS] + "\n… (truncated)"
        return out
    except json.JSONDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")[:_MAX_CHARS]
    except Exception as e:
        return f"(JSON extraction error: {e})"


# ── Context formatter ─────────────────────────────────────────────────────────
def format_attachment_context(attachment: dict) -> str:
    """
    Format an extracted attachment as a labelled context block
    ready for injection into the LLM prompt.
    """
    atype = attachment.get("type", "file")
    name  = attachment.get("name", "file")
    text  = attachment.get("text", "")
    desc  = attachment.get("description", "")   # set by vision model for images

    labels = {
        "image": "Attached image",
        "pdf":   "Attached PDF",
        "docx":  "Attached document",
        "csv":   "Attached data (CSV)",
        "json":  "Attached JSON",
        "text":  "Attached file",
    }
    header = f"[{labels.get(atype, 'Attached file')}: {name}]"

    if atype == "image":
        body = f"Visual description:\n{desc}" if desc else "(image — vision model not available)"
    else:
        body = text or "(empty)"

    trunc = attachment.get("truncated", False)
    footer = "\n(content was truncated to fit context)" if trunc else ""
    return f"{header}\n{body}{footer}"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ok(atype: str, name: str, text: str, truncated: bool = False) -> dict:
    return {
        "type": atype, "name": name, "text": text,
        "base64": None, "mime": None,
        "truncated": truncated or len(text) >= _MAX_CHARS,
    }

def _err(name: str, msg: str) -> dict:
    return {
        "type": "error", "name": name, "text": msg,
        "base64": None, "mime": None, "truncated": False,
    }
