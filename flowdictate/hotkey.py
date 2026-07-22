"""
hotkey.py — Global hotkey listener using pynput.

Listens for the configured key (default: right_cmd).
- on press  → calls on_press_callback()
- on release → calls on_release_callback()

Runs in a dedicated daemon thread so it works system-wide, even when the
app is not in focus.  pynput uses the Quartz event tap on macOS, which
requires Accessibility permission (granted once in System Settings).
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

import config

logger = logging.getLogger(__name__)


def _resolve_key(hotkey_name: str) -> Key | KeyCode | None:
    """
    Convert a hotkey name string to a pynput Key or KeyCode.

    Examples:
        "right_cmd"  → Key.right_cmd
        "f13"        → Key.f13
        "a"          → KeyCode.from_char('a')
    """
    # Try pynput named keys first
    try:
        return getattr(Key, hotkey_name)
    except AttributeError:
        pass
    # Try single-character key
    if len(hotkey_name) == 1:
        return KeyCode.from_char(hotkey_name)
    logger.error("Unknown hotkey name: '%s' — falling back to Key.right_cmd", hotkey_name)
    return Key.right_cmd


class HotkeyListener:
    """
    Listens globally for hold-to-record hotkey events.

    Args:
        on_press:   called once when the key is first pressed.
        on_release: called when the key is released.
    """

    def __init__(
        self,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._target_key = _resolve_key(config.HOTKEY)
        self._pressed = False
        self._listener: keyboard.Listener | None = None
        self._thread: threading.Thread | None = None

    # ── public API ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the global listener in a background daemon thread."""
        self._listener = keyboard.Listener(
            on_press=self._handle_press,
            on_release=self._handle_release,
        )
        self._listener.daemon = True
        self._listener.start()
        logger.info("Hotkey listener started — key=%s", config.HOTKEY)

    def stop(self) -> None:
        """Stop the global listener."""
        if self._listener:
            self._listener.stop()
            self._listener = None
        logger.info("Hotkey listener stopped")

    # ── pynput callbacks ──────────────────────────────────────────────────

    def _handle_press(self, key: Key | KeyCode | None) -> None:
        if self._key_matches(key) and not self._pressed:
            self._pressed = True
            logger.debug("Hotkey pressed")
            try:
                self._on_press()
            except Exception as exc:
                logger.exception("on_press callback raised: %s", exc)

    def _handle_release(self, key: Key | KeyCode | None) -> None:
        if self._key_matches(key) and self._pressed:
            self._pressed = False
            logger.debug("Hotkey released")
            try:
                self._on_release()
            except Exception as exc:
                logger.exception("on_release callback raised: %s", exc)

    def _key_matches(self, key: Key | KeyCode | None) -> bool:
        if key is None:
            return False
        return key == self._target_key

    @property
    def is_active(self) -> bool:
        return self._listener is not None and self._listener.running
