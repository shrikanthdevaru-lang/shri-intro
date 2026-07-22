"""
context.py — Detect the frontmost application on macOS.

Uses pyobjc / NSWorkspace, which requires no special permissions.
Falls back gracefully if pyobjc is unavailable (useful in CI / non-macOS).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    from AppKit import NSWorkspace  # type: ignore
    _OBJC_AVAILABLE = True
except ImportError:
    _OBJC_AVAILABLE = False
    logger.warning("pyobjc not available — app context detection disabled.")


def get_frontmost_app() -> str:
    """
    Return the lowercase display name of the currently active application.

    Examples: "code", "messages", "mail", "terminal"

    Returns an empty string if detection fails.
    """
    if not _OBJC_AVAILABLE:
        return ""
    try:
        workspace = NSWorkspace.sharedWorkspace()
        active_app = workspace.frontmostApplication()
        if active_app is None:
            return ""
        name: str = active_app.localizedName() or ""
        return name.lower().strip()
    except Exception as exc:  # pragma: no cover
        logger.debug("App context detection failed: %s", exc)
        return ""


def get_context_rule(app_name: str) -> str:
    """
    Map an app name to a context instruction string for the LLM prompt.

    Args:
        app_name: Lowercase app name (from get_frontmost_app()).

    Returns:
        A context instruction string.
    """
    from config import APP_CONTEXT_RULES, DEFAULT_CONTEXT_RULE

    for key, rule in APP_CONTEXT_RULES.items():
        if key in app_name:
            return rule
    return DEFAULT_CONTEXT_RULE
