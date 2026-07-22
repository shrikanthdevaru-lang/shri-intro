"""
config.py — Centralised settings and environment loading for FlowDictate.

All tuneable knobs live here. Other modules import from this file only;
they never touch os.environ directly.
"""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# ── locate the project root (same directory as this file) ──────────────────
_ROOT = Path(__file__).parent.resolve()
_ENV_FILE = _ROOT / ".env"

# Load .env if it exists (silently ignore if absent)
load_dotenv(_ENV_FILE, override=False)


# ─────────────────────────────────────────────────────────────────────────────
# API keys
# ─────────────────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")


# ─────────────────────────────────────────────────────────────────────────────
# Hotkey
# ─────────────────────────────────────────────────────────────────────────────
# Value must match a pynput Key attribute name, e.g. "right_cmd", "f13"
HOTKEY: str = os.environ.get("HOTKEY", "right_cmd")


# ─────────────────────────────────────────────────────────────────────────────
# Transcription
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_MODE: str = os.environ.get("DEFAULT_MODE", "cloud").lower()  # "cloud" | "local"
WHISPER_CLOUD_MODEL: str = "whisper-1"
WHISPER_LOCAL_MODEL: str = os.environ.get("WHISPER_LOCAL_MODEL", "turbo")

# Audio capture
SAMPLE_RATE: int = 16_000   # Hz
CHANNELS: int = 1            # mono
DTYPE: str = "float32"

# Temp directory for audio snippets (deleted immediately after transcription)
TEMP_DIR: Path = Path("/tmp/flowdictate")
TEMP_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# LLM cleanup
# ─────────────────────────────────────────────────────────────────────────────
CLEANUP_ENABLED: bool = os.environ.get("CLEANUP_ENABLED", "true").lower() == "true"
CLEANUP_MODEL: str = "claude-haiku-4-5"
CLEANUP_TIMEOUT_SECONDS: float = 8.0  # fall back to raw transcript if exceeded

SYSTEM_PROMPT_TEMPLATE: str = """\
You are a dictation cleanup assistant. The user just dictated the following text using voice.

Your job:
1. Remove filler words (um, uh, like, you know, so, basically, literally)
2. Fix punctuation and capitalisation
3. Fix grammar while preserving the speaker's voice
4. Do NOT add content that wasn't spoken
5. Adjust formatting based on context: {context}

Return ONLY the cleaned text. No explanation, no preamble.\
"""

# Per-app context instructions injected into the system prompt
APP_CONTEXT_RULES: dict[str, str] = {
    # Messaging — casual
    "messages":  "Casual conversation; use short, natural sentences. Contractions are fine.",
    "whatsapp":  "Casual conversation; use short, natural sentences. Contractions are fine.",
    "telegram":  "Casual conversation; use short, natural sentences. Contractions are fine.",
    # Email / documents — professional
    "mail":      "Professional email or document; use full paragraphs with formal grammar.",
    "outlook":   "Professional email or document; use full paragraphs with formal grammar.",
    "word":      "Professional document; use full paragraphs with formal grammar.",
    "pages":     "Professional document; use full paragraphs with formal grammar.",
    # Dev tools — minimal cleanup, preserve terms
    "code":          "Technical context (code editor). Preserve all technical terms, variable names, "
                     "and acronyms exactly as spoken. Minimal punctuation fixes only.",
    "cursor":        "Technical context (AI code editor). Preserve all technical terms exactly. "
                     "Minimal cleanup only.",
    "xcode":         "Technical context (Xcode IDE). Preserve all technical terms. Minimal cleanup.",
    "terminal":      "Terminal / command-line context. Preserve commands and flags verbatim.",
    "iterm":         "Terminal context. Preserve commands and flags verbatim.",
    "iterm2":        "Terminal context. Preserve commands and flags verbatim.",
    # Notes / knowledge management — markdown prose
    "notes":     "Personal notes app. Clean prose with markdown formatting where appropriate.",
    "notion":    "Notion document. Clean prose with markdown headings and bullets where helpful.",
    "obsidian":  "Obsidian markdown vault. Use clean markdown formatting with appropriate headings.",
}

DEFAULT_CONTEXT_RULE: str = (
    "Neutral context. Produce clean, readable prose with proper punctuation."
)


# ─────────────────────────────────────────────────────────────────────────────
# History
# ─────────────────────────────────────────────────────────────────────────────
HISTORY_SIZE: int = int(os.environ.get("HISTORY_SIZE", "10"))


# ─────────────────────────────────────────────────────────────────────────────
# Database (custom vocabulary)
# ─────────────────────────────────────────────────────────────────────────────
DB_PATH: Path = _ROOT / "flowdictate.db"


# ─────────────────────────────────────────────────────────────────────────────
# UI / overlay
# ─────────────────────────────────────────────────────────────────────────────
OVERLAY_WIDTH: int = 220
OVERLAY_HEIGHT: int = 60
OVERLAY_BOTTOM_MARGIN: int = 60   # pixels from bottom of screen
OVERLAY_BG_COLOR: str = "#1a1a2e"
OVERLAY_ACCENT_COLOR: str = "#e94560"
OVERLAY_TEXT_COLOR: str = "#ffffff"
OVERLAY_FONT_FAMILY: str = "SF Pro Display"
OVERLAY_FONT_SIZE: int = 13


# ─────────────────────────────────────────────────────────────────────────────
# Logging (metadata only — never log transcript content)
# ─────────────────────────────────────────────────────────────────────────────
LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
