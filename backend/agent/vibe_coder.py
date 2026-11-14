"""
agent/vibe_coder.py — Mini IDE Sprint 2

Handles vibe coding requests — natural language / design → code.

Two modes:
  1. Image-to-code: user attaches a screenshot/design → vision model (llama3.2-vision:11b) describes
     it → structured spec → coder generates component
  2. Text-to-code: user describes a UI or aesthetic in plain English →
     spec is extracted → coder generates component

Also handles "make it feel like X" mood requests by extracting a
design system from the reference and mapping it to CSS/Tailwind.
"""
from __future__ import annotations

import re
from pathlib import Path


# ── Vibe / design intent detection ───────────────────────────────────────────
_VIBE_TRIGGERS = re.compile(
    r"\b(feel like|vibe|aesthetic|style like|look like|inspired by|"
    r"make it|give it a|theme|dark mode|light mode|minimal|modern|"
    r"replicate|recreate|copy the (ui|ux|design|style|layout))\b",
    re.IGNORECASE,
)

_UI_BUILD_TRIGGERS = re.compile(
    r"\b(build|create|make|design|generate|write)\b.{0,40}"
    r"\b(ui|component|page|screen|form|modal|sidebar|navbar|dashboard|"
    r"button|card|table|chart|layout|interface)\b",
    re.IGNORECASE,
)

_SCREENSHOT_REPLICATE = re.compile(
    r"\b(replicate|recreate|copy|clone|build|implement)\b.{0,30}"
    r"\b(this|the|it|ui|design|screenshot|image|layout)\b",
    re.IGNORECASE,
)

# Known design references and their characteristics
_DESIGN_REFERENCES: dict[str, dict] = {
    "notion":    {"bg": "#ffffff", "text": "#37352f", "radius": "3px",   "density": "comfortable", "style": "minimal, clean, document-first"},
    "linear":    {"bg": "#111111", "text": "#e2e2e2", "radius": "6px",   "density": "compact",     "style": "dark, minimal, sharp edges, purple accents"},
    "vercel":    {"bg": "#000000", "text": "#ededed", "radius": "8px",   "density": "airy",        "style": "ultra-minimal, black/white, generous whitespace"},
    "figma":     {"bg": "#2c2c2c", "text": "#ffffff", "radius": "4px",   "density": "compact",     "style": "dark, tool-like, purple/grey"},
    "github":    {"bg": "#0d1117", "text": "#c9d1d9", "radius": "6px",   "density": "comfortable", "style": "dark developer, subtle borders, blue accents"},
    "stripe":    {"bg": "#ffffff", "text": "#425466", "radius": "8px",   "density": "comfortable", "style": "clean, professional, indigo accents, soft shadows"},
    "discord":   {"bg": "#313338", "text": "#dbdee1", "radius": "8px",   "density": "compact",     "style": "dark, blurple accents, rounded, social"},
    "tailwind":  {"bg": "#0f172a", "text": "#e2e8f0", "radius": "8px",   "density": "comfortable", "style": "dark slate, utility-first, sky blue accents"},
    "shadcn":    {"bg": "#ffffff", "text": "#09090b", "radius": "8px",   "density": "comfortable", "style": "clean, zinc greys, minimal, accessible"},
    "vs code":   {"bg": "#1e1e1e", "text": "#d4d4d4", "radius": "2px",   "density": "dense",       "style": "dark, editor-like, blue accents, no shadows"},
}


def is_vibe_request(message: str) -> bool:
    """Return True if the message is asking for UI/vibe work."""
    return bool(
        _VIBE_TRIGGERS.search(message) or
        _UI_BUILD_TRIGGERS.search(message) or
        _SCREENSHOT_REPLICATE.search(message)
    )


def detect_design_reference(message: str) -> dict | None:
    """
    Check if the user mentions a known design reference.
    Returns the design system dict or None.
    """
    lower = message.lower()
    for name, system in _DESIGN_REFERENCES.items():
        if name in lower:
            return {"name": name, **system}
    return None


# ── Prompt builders ────────────────────────────────────────────────────────────
def build_ui_system_prompt(
    ui_description:   str,
    existing_stack:   str = "React/JSX",
    design_reference: dict | None = None,
    convention_note:  str = "",
) -> str:
    """
    Build a system prompt for a UI generation task.

    Args:
        ui_description:   What the vision model described OR what the user typed
        existing_stack:   The project's frontend stack
        design_reference: Optional known design system to match
        convention_note:  Convention note from the convention detector
    """
    style_note = ""
    if design_reference:
        style_note = (
            f"\n\nDESIGN REFERENCE — match the {design_reference['name'].title()} aesthetic:\n"
            f"- Background: {design_reference['bg']}\n"
            f"- Text color: {design_reference['text']}\n"
            f"- Border radius: {design_reference['radius']}\n"
            f"- Density: {design_reference['density']}\n"
            f"- Overall style: {design_reference['style']}\n"
            f"Use inline styles that match this design system exactly."
        )

    conv_note = f"\n\n{convention_note}" if convention_note else ""

    return (
        f"You are an expert {existing_stack} developer specializing in UI implementation. "
        f"Your task is to convert a UI description into clean, working {existing_stack} code.\n\n"
        f"RULES:\n"
        f"1. Output the COMPLETE component in a single fenced code block.\n"
        f"2. Use inline styles only — no external CSS files, no Tailwind classes.\n"
        f"3. Every piece of the described UI must be implemented — do not skip elements.\n"
        f"4. Use realistic placeholder content (not 'Lorem ipsum' — use real-looking names/data).\n"
        f"5. Make it fully functional (useState for interactive elements).\n"
        f"6. Default export the main component.\n"
        f"7. Match the described layout, colors, and spacing as closely as possible."
        f"{style_note}"
        f"{conv_note}"
    )


def build_ui_user_message(
    ui_description:   str,
    user_request:     str,
    component_name:   str = "Component",
) -> str:
    """Build the user message for a UI generation request."""
    return (
        f"Build this {component_name} in React/JSX.\n\n"
        f"UI Description:\n{ui_description}\n\n"
        f"User's request: {user_request}\n\n"
        f"Generate the complete React component now."
    )


def build_mood_prompt(reference_name: str, current_css_vars: str = "") -> str:
    """
    Build a prompt for converting the project's theme to match a reference.
    """
    ref = _DESIGN_REFERENCES.get(reference_name.lower(), {})
    if not ref:
        return ""

    current_section = (
        f"\nExisting CSS variables to update:\n```css\n{current_css_vars}\n```\n"
        if current_css_vars else ""
    )

    return (
        f"Update this project's visual theme to match the {reference_name.title()} aesthetic.\n"
        f"{current_section}\n"
        f"Target design system:\n"
        f"- Background: {ref.get('bg', 'auto')}\n"
        f"- Text: {ref.get('text', 'auto')}\n"
        f"- Border radius: {ref.get('radius', 'auto')}\n"
        f"- Density: {ref.get('density', 'auto')}\n"
        f"- Style: {ref.get('style', 'auto')}\n\n"
        f"Generate updated CSS variables and any necessary style changes."
    )


def extract_component_name(user_message: str) -> str:
    """
    Try to extract a reasonable component name from the user's message.
    Falls back to 'Component'.
    """
    # "build a sidebar" → "Sidebar"
    # "create a user profile card" → "UserProfileCard"
    patterns = [
        r"\b(?:build|create|make|design|generate|write)\s+(?:a|an|the)?\s+([\w\s]+?)(?:\s+component|$|\s+with|\s+that|\s+for|\s+in)",
    ]
    for pattern in patterns:
        m = re.search(pattern, user_message, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            # Convert to PascalCase
            words  = re.findall(r"[A-Za-z]+", raw)
            result = "".join(w.capitalize() for w in words if w)
            if result and len(result) < 40:
                return result
    return "Component"


def suggest_file_path(component_name: str, workspace: Path) -> str:
    """Suggest where the new component file should be saved."""
    components_dir = workspace / "frontend" / "src" / "components"
    if components_dir.exists():
        return f"frontend/src/components/{component_name}.jsx"
    src_dir = workspace / "src" / "components"
    if src_dir.exists():
        return f"src/components/{component_name}.jsx"
    return f"{component_name}.jsx"
