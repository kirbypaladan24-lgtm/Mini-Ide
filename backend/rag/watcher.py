"""
rag/watcher.py — Mini IDE Phase 4

Monitors the workspace directory for file changes using watchdog.
Changed files are placed in a queue; the background asyncio task
in main.py drains the queue and calls indexer.index_file().
"""
import queue
from pathlib import Path
from typing import Optional

try:
    from watchdog.observers import Observer
    from watchdog.events    import FileSystemEventHandler, FileSystemEvent
    WATCHDOG_OK = True
except ImportError:
    Observer    = None           # type: ignore
    WATCHDOG_OK = False

from rag.chunker import INDEXABLE_EXTS

# Shared queue — written by watchdog thread, read by asyncio task
change_queue: queue.Queue[str] = queue.Queue()

_observer: Optional[object] = None


class _Handler(FileSystemEventHandler if WATCHDOG_OK else object):  # type: ignore
    """Push changed file paths into change_queue."""

    def on_modified(self, event: "FileSystemEvent") -> None:         # type: ignore
        self._enqueue(event.src_path)

    def on_created(self, event: "FileSystemEvent") -> None:          # type: ignore
        self._enqueue(event.src_path)

    def on_moved(self, event: "FileSystemEvent") -> None:            # type: ignore
        self._enqueue(getattr(event, "dest_path", event.src_path))

    @staticmethod
    def _enqueue(path: str) -> None:
        p = Path(path)
        if p.is_file() and p.suffix.lower() in INDEXABLE_EXTS:
            change_queue.put_nowait(path)


def start_watcher(workspace: Path) -> None:
    """Start the watchdog Observer for the given workspace."""
    global _observer
    if not WATCHDOG_OK:
        return
    stop_watcher()          # stop any previous observer
    obs = Observer()
    obs.schedule(_Handler(), str(workspace), recursive=True)
    obs.start()
    _observer = obs


def stop_watcher() -> None:
    """Stop the current Observer if running."""
    global _observer
    if _observer is not None:
        try:
            _observer.stop()        # type: ignore[union-attr]
            _observer.join(timeout=2)
        except Exception:
            pass
        _observer = None


def drain_changes() -> list[str]:
    """Pop all pending paths from the change queue (non-blocking)."""
    paths: list[str] = []
    while True:
        try:
            paths.append(change_queue.get_nowait())
        except queue.Empty:
            break
    return paths
