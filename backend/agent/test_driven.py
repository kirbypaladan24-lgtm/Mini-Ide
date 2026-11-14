"""
agent/test_driven.py — Mini IDE Sprint 5

TDD workflow: tests first (red), then implementation (green).

Triggered by: "TDD mode: ..." or "build this test-first" or the
Smart Template "Build this test-first".

Pipeline:
  1. Generate test file based on the request + existing test conventions
  2. Show test diff → user approves (handled by caller, not here)
  3. Generate implementation to satisfy the tests
  4. Run tests via the sandbox
  5. If tests fail, attempt one fix round (reuses agent.loop patterns)
"""
from __future__ import annotations

import re
from pathlib import Path

from llm.client      import stream_chat
from tools.sandbox    import run_sandboxed

_TDD_TEST_SYSTEM = """\
You are writing tests FIRST, before any implementation exists, following
test-driven development practice. The implementation does not exist yet —
write tests that describe the desired behavior precisely.

Rules:
1. Use pytest conventions (or jest if the project is JavaScript).
2. Cover the happy path AND at least one edge case AND one error case.
3. Use clear, descriptive test names (test_what_when_expected).
4. Output the COMPLETE test file in a single fenced code block.
5. Assume the implementation will be in a module — use a reasonable
   import statement based on the described feature.
"""

_TDD_IMPL_SYSTEM = """\
You are implementing code to make a specific set of failing tests pass.
This is the GREEN step of test-driven development.

Rules:
1. Read the tests carefully — they define the exact required behavior.
2. Implement the SIMPLEST code that makes all tests pass.
3. Do not add functionality beyond what the tests require.
4. Output the COMPLETE implementation file in a single fenced code block.
5. Match the import path the tests expect.
"""


def is_tdd_request(message: str) -> bool:
    """Detect explicit TDD-mode requests."""
    lower = message.lower()
    return bool(re.search(
        r"\b(tdd|test-first|test first|tests? first|write tests? before)\b", lower
    ))


def strip_tdd_prefix(message: str) -> str:
    """Remove the TDD trigger phrase to get the underlying feature request."""
    cleaned = re.sub(
        r"^\s*(tdd mode:?|test-first:?|build this test-first:?)\s*",
        "", message, flags=re.IGNORECASE,
    )
    return cleaned.strip() or message


async def generate_test_file(
    feature_request: str,
    language:         str,
    test_convention:  str,
    model:            str,
) -> str | None:
    """Generate the test file content (red step)."""
    user_msg = (
        f"Feature to test: {feature_request}\n\n"
        f"Existing test convention in this project: {test_convention or 'pytest, standard style'}\n\n"
        "Write the complete test file now."
    )
    messages = [
        {"role": "system", "content": _TDD_TEST_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]
    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.15, num_ctx=4096):
            full += token
    except Exception:
        return None
    return _extract_code(full)


async def generate_implementation(
    feature_request: str,
    test_content:    str,
    language:         str,
    model:            str,
) -> str | None:
    """Generate the implementation to satisfy the tests (green step)."""
    user_msg = (
        f"Feature: {feature_request}\n\n"
        f"Tests that must pass:\n```{language}\n{test_content}\n```\n\n"
        "Write the complete implementation now."
    )
    messages = [
        {"role": "system", "content": _TDD_IMPL_SYSTEM},
        {"role": "user",   "content": user_msg},
    ]
    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.15, num_ctx=4096):
            full += token
    except Exception:
        return None
    return _extract_code(full)


async def run_tdd_cycle(
    websocket,
    feature_request: str,
    language:         str,
    workspace:        Path,
    impl_path:        str,
    test_path:        str,
    test_convention:  str,
    model:            str,
    max_fix_attempts: int = 2,
) -> dict:
    """
    Full TDD cycle, emitting progress events over the websocket.
    Returns {"test_code": str, "impl_code": str, "passed": bool, "attempts": int}.
    """
    await websocket.send_json({"type": "tdd_step", "step": "red",
                               "message": "Writing tests first (red)…"})
    test_code = await generate_test_file(feature_request, language, test_convention, model)
    if not test_code:
        return {"ok": False, "error": "Could not generate tests."}

    await websocket.send_json({"type": "tdd_step", "step": "green",
                               "message": "Writing implementation (green)…"})
    impl_code = await generate_implementation(feature_request, test_code, language, model)
    if not impl_code:
        return {"ok": False, "test_code": test_code, "error": "Could not generate implementation."}

    # Write both temporarily to sandbox-test, then report — actual disk write
    # happens via the normal diff-approval flow in the caller.
    attempts = 0
    passed   = False
    last_stderr = ""

    for attempt in range(1, max_fix_attempts + 2):
        attempts = attempt
        # Write to disk temporarily under workspace for sandboxed execution
        impl_abs = (workspace / impl_path).resolve()
        test_abs = (workspace / test_path).resolve()
        impl_abs.parent.mkdir(parents=True, exist_ok=True)
        test_abs.parent.mkdir(parents=True, exist_ok=True)
        impl_abs.write_text(impl_code, encoding="utf-8")
        test_abs.write_text(test_code, encoding="utf-8")

        await websocket.send_json({"type": "tdd_step", "step": "run",
                                   "message": f"Running tests (attempt {attempt})…"})
        result = await run_sandboxed(test_path, workspace, language, timeout=20)
        passed = result["success"]
        last_stderr = result["stderr"]

        if passed or attempt > max_fix_attempts:
            break

        await websocket.send_json({"type": "tdd_step", "step": "fix",
                                   "message": "Tests failed — refining implementation…"})
        impl_code = await _fix_implementation(impl_code, test_code, last_stderr, language, model) or impl_code

    return {
        "ok":        True,
        "test_code": test_code,
        "impl_code": impl_code,
        "passed":    passed,
        "attempts":  attempts,
        "stderr":    last_stderr if not passed else "",
    }


async def _fix_implementation(
    impl_code: str, test_code: str, stderr: str, language: str, model: str,
) -> str | None:
    messages = [
        {"role": "system", "content": (
            "Fix this implementation so the tests pass. Output the complete "
            "corrected file in a single fenced code block."
        )},
        {"role": "user", "content": (
            f"Implementation:\n```{language}\n{impl_code}\n```\n\n"
            f"Tests:\n```{language}\n{test_code}\n```\n\n"
            f"Test failure output:\n```\n{stderr[:1500]}\n```"
        )},
    ]
    full = ""
    try:
        async for token in stream_chat(model, messages, temperature=0.1, num_ctx=4096):
            full += token
    except Exception:
        return None
    return _extract_code(full)


def _extract_code(text: str) -> str | None:
    m = re.search(r"```(?:\w+)?\n([\s\S]*?)```", text)
    return m.group(1) if m else None
