"""
cleaner.py — LLM-powered dictation cleanup via Anthropic Claude.

Sends raw transcribed text to claude-haiku-4-5 with a context-aware system
prompt.  Times out after CLEANUP_TIMEOUT_SECONDS and returns the raw text if
the API is unavailable or too slow.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import config
from context import get_context_rule

logger = logging.getLogger(__name__)


class TextCleaner:
    """
    Post-process raw Whisper transcript with Claude haiku.

    Args:
        app_name: lowercase frontmost app name for context selection.
    """

    def __init__(self, app_name: str = "") -> None:
        self.app_name = app_name

    def clean(self, raw_text: str) -> str:
        """
        Return cleaned text.  Falls back to raw_text on any error or timeout.
        Never raises.
        """
        if not config.CLEANUP_ENABLED:
            return raw_text

        if not raw_text.strip():
            return raw_text

        if not config.ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set — skipping LLM cleanup")
            return raw_text

        try:
            return self._call_claude(raw_text)
        except CleanupTimeoutError:
            logger.warning(
                "LLM cleanup timed out (>%.1fs) — returning raw transcript",
                config.CLEANUP_TIMEOUT_SECONDS,
            )
            return raw_text
        except Exception as exc:
            logger.error("LLM cleanup error (%s) — returning raw transcript", exc)
            return raw_text

    # ── private ───────────────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        context_rule = get_context_rule(self.app_name)
        return config.SYSTEM_PROMPT_TEMPLATE.format(context=context_rule)

    def _call_claude(self, raw_text: str) -> str:
        import anthropic
        import signal

        # Use SIGALRM-based timeout on POSIX systems (macOS)
        def _timeout_handler(signum, frame):
            raise CleanupTimeoutError("Claude API call exceeded timeout")

        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(int(config.CLEANUP_TIMEOUT_SECONDS) + 1)

        t0 = time.perf_counter()
        try:
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=config.CLEANUP_MODEL,
                max_tokens=1024,
                system=self._build_system_prompt(),
                messages=[
                    {"role": "user", "content": raw_text},
                ],
            )
            cleaned = response.content[0].text.strip()
        finally:
            signal.alarm(0)   # cancel alarm

        latency = time.perf_counter() - t0
        raw_words = len(raw_text.split())
        clean_words = len(cleaned.split())
        logger.info(
            "LLM cleanup — raw_words=%d, clean_words=%d, latency=%.2fs",
            raw_words,
            clean_words,
            latency,
        )
        return cleaned


# ── exceptions ────────────────────────────────────────────────────────────────

class CleanupTimeoutError(TimeoutError):
    """Raised when the Claude API call exceeds CLEANUP_TIMEOUT_SECONDS."""
