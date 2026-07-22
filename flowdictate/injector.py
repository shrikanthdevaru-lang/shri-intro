"""
injector.py — Paste cleaned text at the system cursor position.

Strategy:
  1. Save the current clipboard contents.
  2. Copy the cleaned text to the clipboard.
  3. Simulate Cmd+V via pynput keyboard controller.
  4. After a short delay, restore the previous clipboard contents (privacy).

All operations run on the calling thread; the caller is responsible for
not blocking the main loop (run this in an executor).
"""

from __future__ import annotations

import logging
import threading
import time

import pyperclip
from pynput.keyboard import Controller, Key

logger = logging.getLogger(__name__)

_PASTE_DELAY: float = 0.08   # seconds between copy and Cmd+V
_CLEAR_DELAY: float = 2.0    # seconds before restoring previous clipboard


class TextInjector:
    """Injects text at the current cursor position using clipboard paste."""

    def __init__(self) -> None:
        self._keyboard = Controller()

    def inject(self, text: str) -> None:
        """
        Paste *text* at the current cursor position.

        Saves and restores the previous clipboard contents for privacy.
        """
        if not text:
            return

        # Save previous clipboard
        try:
            previous_clipboard = pyperclip.paste()
        except Exception:
            previous_clipboard = ""

        try:
            # Place text on clipboard
            pyperclip.copy(text)
            time.sleep(_PASTE_DELAY)

            # Simulate Cmd+V
            self._keyboard.press(Key.cmd)
            self._keyboard.press("v")
            self._keyboard.release("v")
            self._keyboard.release(Key.cmd)

            logger.info(
                "Text injected — chars=%d, words=%d",
                len(text),
                len(text.split()),
            )
        except Exception as exc:
            logger.error("Text injection failed: %s", exc)
            raise InjectionError(str(exc)) from exc
        finally:
            # Restore previous clipboard asynchronously (privacy)
            def _restore():
                time.sleep(_CLEAR_DELAY)
                try:
                    pyperclip.copy(previous_clipboard)
                except Exception:
                    pass

            threading.Thread(target=_restore, daemon=True).start()


# ── exceptions ────────────────────────────────────────────────────────────────

class InjectionError(RuntimeError):
    """Raised when text cannot be injected."""
