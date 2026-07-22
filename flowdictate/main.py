"""
main.py — FlowDictate entry point.

Launches:
  • rumps menu bar app (macOS status bar)
  • Tkinter hidden root window (owns overlay + dictionary UI)
  • pynput global hotkey listener
  • Background thread pool for recording / transcription / cleanup

Architecture:
  ┌─────────────┐   press/release   ┌──────────────┐
  │ HotkeyListener│ ──────────────► │  on_press /  │
  │  (daemon)   │                   │  on_release  │
  └─────────────┘                   └──────┬───────┘
                                           │ submit to
                                     ThreadPoolExecutor
                                           │
                               ┌───────────▼──────────────┐
                               │  _run_pipeline()          │
                               │  1. AudioRecorder.stop()  │
                               │  2. Transcriber           │
                               │  3. TextCleaner           │
                               │  4. TextInjector          │
                               └───────────────────────────┘

The rumps menu bar app runs its own CFRunLoop.
The Tkinter root runs via periodic `update()` calls from a background thread
(Tk is not thread-safe; we drive it from a single dedicated thread).
"""

from __future__ import annotations

import collections
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Deque

import rumps

import config
from cleaner import TextCleaner
from context import get_frontmost_app
from dictionary import DictionaryManagerWindow, VocabularyDB
from hotkey import HotkeyListener
from injector import TextInjector
from recorder import AudioRecorder, MicrophoneError, RecordingTooShortError
from transcriber import Transcriber, TranscriptionError

# ── logging setup (metadata only) ────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format=config.LOG_FORMAT,
)
logger = logging.getLogger("flowdictate.main")


# ─────────────────────────────────────────────────────────────────────────────
# Tkinter thread (overlay + dictionary windows)
# ─────────────────────────────────────────────────────────────────────────────

def _start_tk_thread():
    """
    Initialise Tkinter in a dedicated thread and keep it alive by calling
    root.update() every 50 ms.  Tkinter is not thread-safe, so ALL tk widget
    creation must happen in this thread via root.after().
    """
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()                  # hide the root window
    root.title("FlowDictate")

    # Make the hidden root completely invisible / non-interactive
    root.attributes("-alpha", 0)
    root.resizable(False, False)

    # Store on a global so other threads can schedule work with root.after()
    FlowDictateApp._tk_root = root

    from overlay import RecordingOverlay
    FlowDictateApp._overlay = RecordingOverlay(root)

    # Signal that Tk is ready
    FlowDictateApp._tk_ready.set()

    # Drive the event loop
    while not FlowDictateApp._tk_stop.is_set():
        try:
            root.update()
        except Exception:
            break
        time.sleep(0.05)

    try:
        root.destroy()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Preferences window (Tkinter)
# ─────────────────────────────────────────────────────────────────────────────

class PreferencesWindow:
    """Simple Tkinter preferences dialog."""

    def __init__(self, app: "FlowDictateApp") -> None:
        self._app = app
        self._win = None

    def open(self) -> None:
        root = FlowDictateApp._tk_root
        if root is None:
            return
        root.after(0, self._create)

    def _create(self) -> None:
        import tkinter as tk

        if self._win and tk.Toplevel.winfo_exists(self._win):
            self._win.lift()
            return

        BG = "#1a1a2e"
        CARD = "#16213e"
        ACCENT = "#e94560"
        FG = "#ffffff"
        MUTED = "#a0a0b8"
        FONT = ("SF Pro Display", 13)
        FONT_SM = ("SF Pro Display", 11)

        win = tk.Toplevel(FlowDictateApp._tk_root)
        self._win = win
        win.title("FlowDictate — Preferences")
        win.geometry("400x380")
        win.resizable(False, False)
        win.configure(bg=BG)

        # Header
        tk.Label(win, text="⚙️  Preferences", bg=BG, fg=FG,
                 font=("SF Pro Display", 16, "bold"), pady=16).pack()

        # ── Hotkey ──────────────────────────────────────────────────────
        row = tk.Frame(win, bg=BG, padx=24, pady=6)
        row.pack(fill="x")
        tk.Label(row, text="Hotkey key name:", bg=BG, fg=MUTED, font=FONT_SM,
                 width=20, anchor="w").pack(side="left")
        hotkey_var = tk.StringVar(value=config.HOTKEY)
        tk.Entry(row, textvariable=hotkey_var, bg=CARD, fg=FG,
                 insertbackground=FG, font=FONT, relief="flat", bd=6,
                 width=16).pack(side="left")

        # ── Mode ────────────────────────────────────────────────────────
        row2 = tk.Frame(win, bg=BG, padx=24, pady=6)
        row2.pack(fill="x")
        tk.Label(row2, text="Transcription mode:", bg=BG, fg=MUTED,
                 font=FONT_SM, width=20, anchor="w").pack(side="left")
        mode_var = tk.StringVar(value=self._app._mode)
        mode_menu = tk.OptionMenu(row2, mode_var, "cloud", "local")
        mode_menu.configure(bg=CARD, fg=FG, activebackground=ACCENT,
                            activeforeground=FG, relief="flat", font=FONT)
        mode_menu.pack(side="left")

        # ── Cleanup toggle ────────────────────────────────────────────
        row3 = tk.Frame(win, bg=BG, padx=24, pady=6)
        row3.pack(fill="x")
        tk.Label(row3, text="LLM cleanup:", bg=BG, fg=MUTED, font=FONT_SM,
                 width=20, anchor="w").pack(side="left")
        cleanup_var = tk.BooleanVar(value=config.CLEANUP_ENABLED)
        tk.Checkbutton(row3, variable=cleanup_var, bg=BG, fg=FG,
                       selectcolor=CARD, activebackground=BG,
                       activeforeground=FG).pack(side="left")

        # ── Local model size ──────────────────────────────────────────
        row4 = tk.Frame(win, bg=BG, padx=24, pady=6)
        row4.pack(fill="x")
        tk.Label(row4, text="Local model size:", bg=BG, fg=MUTED,
                 font=FONT_SM, width=20, anchor="w").pack(side="left")
        model_var = tk.StringVar(value=config.WHISPER_LOCAL_MODEL)
        model_menu = tk.OptionMenu(row4, model_var,
                                   "tiny", "base", "small", "medium",
                                   "large-v3", "turbo")
        model_menu.configure(bg=CARD, fg=FG, activebackground=ACCENT,
                             activeforeground=FG, relief="flat", font=FONT)
        model_menu.pack(side="left")

        # ── Save button ────────────────────────────────────────────────
        def save():
            config.HOTKEY = hotkey_var.get().strip()
            self._app._mode = mode_var.get()
            config.CLEANUP_ENABLED = cleanup_var.get()
            config.WHISPER_LOCAL_MODEL = model_var.get()
            self._app._update_mode_menu()
            win.destroy()

        tk.Button(win, text="Save & Close", command=save,
                  bg=ACCENT, fg=FG, font=("SF Pro Display", 12, "bold"),
                  relief="flat", padx=16, pady=8, cursor="hand2").pack(pady=20)

        # Info note
        tk.Label(
            win,
            text="Note: hotkey changes take effect after restarting FlowDictate.",
            bg=BG, fg=MUTED, font=("SF Pro Display", 10),
            wraplength=350,
        ).pack(pady=(0, 12))


# ─────────────────────────────────────────────────────────────────────────────
# History window (Tkinter)
# ─────────────────────────────────────────────────────────────────────────────

class HistoryWindow:
    """Shows the last N transcriptions; clicking one re-pastes it."""

    def __init__(self, app: "FlowDictateApp") -> None:
        self._app = app
        self._win = None

    def open(self) -> None:
        root = FlowDictateApp._tk_root
        if root is None:
            return
        root.after(0, self._create)

    def _create(self) -> None:
        import tkinter as tk

        if self._win and tk.Toplevel.winfo_exists(self._win):
            self._win.lift()
            return

        BG = "#1a1a2e"
        CARD = "#16213e"
        ACCENT = "#e94560"
        FG = "#ffffff"
        MUTED = "#a0a0b8"
        FONT = ("SF Pro Display", 12)
        FONT_SM = ("SF Pro Display", 10)

        win = tk.Toplevel(FlowDictateApp._tk_root)
        self._win = win
        win.title("FlowDictate — History")
        win.geometry("500x460")
        win.resizable(True, True)
        win.configure(bg=BG)

        tk.Label(win, text="📋  Transcription History", bg=BG, fg=FG,
                 font=("SF Pro Display", 15, "bold"), pady=14).pack()
        tk.Label(win, text="Click an item to re-paste it at your cursor",
                 bg=BG, fg=MUTED, font=FONT_SM).pack(pady=(0, 8))

        frame = tk.Frame(win, bg=BG, padx=16)
        frame.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")

        listbox = tk.Listbox(
            frame,
            bg=CARD, fg=FG, selectbackground=ACCENT, selectforeground=FG,
            font=FONT, relief="flat", bd=0, activestyle="none",
            yscrollcommand=scrollbar.set,
        )
        scrollbar.config(command=listbox.yview)
        listbox.pack(fill="both", expand=True)

        history = list(self._app._history)
        for i, item in enumerate(reversed(history), start=1):
            preview = item[:80].replace("\n", " ")
            listbox.insert(tk.END, f"  {i:2d}. {preview}")

        def on_select(event):
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            text = list(reversed(history))[idx]
            injector = TextInjector()
            threading.Thread(
                target=injector.inject, args=(text,), daemon=True
            ).start()
            win.destroy()

        listbox.bind("<Double-1>", on_select)
        listbox.bind("<Return>", on_select)

        tk.Button(win, text="Close", command=win.destroy,
                  bg="#2a2a4e", fg=FG, font=FONT_SM,
                  relief="flat", padx=12, pady=6).pack(pady=10)


# ─────────────────────────────────────────────────────────────────────────────
# Main rumps App
# ─────────────────────────────────────────────────────────────────────────────

class FlowDictateApp(rumps.App):
    # Class-level Tk handles (set by _start_tk_thread)
    _tk_root = None
    _overlay = None
    _tk_ready: threading.Event = threading.Event()
    _tk_stop: threading.Event = threading.Event()

    def __init__(self) -> None:
        super().__init__(
            "FlowDictate",
            title="🎙",
            quit_button=None,
        )

        # ── state ────────────────────────────────────────────────────────
        self._mode: str = config.DEFAULT_MODE
        self._recorder = AudioRecorder()
        self._injector = TextInjector()
        self._vocab_db = VocabularyDB()
        self._history: Deque[str] = collections.deque(maxlen=config.HISTORY_SIZE)
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fd-worker")
        self._pipeline_running = threading.Lock()   # ensures one pipeline at a time
        self._current_app: str = ""

        # ── menu setup ────────────────────────────────────────────────────
        self._status_item = rumps.MenuItem("FlowDictate — Ready")
        self._status_item.set_callback(None)

        self._mode_item = rumps.MenuItem(
            self._mode_label(), callback=self._toggle_mode
        )

        self._dict_item = rumps.MenuItem(
            "Edit Dictionary…", callback=self._open_dictionary
        )
        self._history_item = rumps.MenuItem(
            "History", callback=self._open_history
        )
        self._prefs_item = rumps.MenuItem(
            "Preferences…", callback=self._open_preferences
        )
        self._quit_item = rumps.MenuItem("Quit", callback=self._quit)

        self.menu = [
            self._status_item,
            None,   # separator
            self._mode_item,
            self._dict_item,
            self._history_item,
            None,
            self._prefs_item,
            self._quit_item,
        ]

        # ── subwindow controllers ─────────────────────────────────────────
        self._dict_window: DictionaryManagerWindow | None = None
        self._prefs_window: PreferencesWindow | None = None
        self._history_window: HistoryWindow | None = None

        # ── hotkey listener ────────────────────────────────────────────────
        self._hotkey = HotkeyListener(
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
        )

        # ── validate API keys on startup ───────────────────────────────────
        self._check_api_keys()

    # ── hotkey callbacks ──────────────────────────────────────────────────

    def _on_hotkey_press(self) -> None:
        """Start recording immediately when hotkey is pressed."""
        if not self._pipeline_running.acquire(blocking=False):
            logger.info("Pipeline already running — ignoring hotkey press")
            return

        try:
            # Capture frontmost app before we show the overlay
            self._current_app = get_frontmost_app()
            logger.debug("Frontmost app: %s", self._current_app)

            self._recorder.start()
            self._set_status("🔴 Recording…")
            self._show_overlay_recording()
        except MicrophoneError as exc:
            self._pipeline_running.release()
            self._set_status("⚠️ Mic Error")
            rumps.notification(
                "FlowDictate",
                "Microphone error",
                "Check System Settings → Privacy → Microphone.",
                sound=False,
            )
            logger.error("Microphone error: %s", exc)

    def _on_hotkey_release(self) -> None:
        """Stop recording and kick off the transcription pipeline."""
        if not self._recorder.is_recording():
            # Release was spurious or we errored on press
            try:
                self._pipeline_running.release()
            except RuntimeError:
                pass
            return

        # Submit pipeline to thread pool (non-blocking)
        self._executor.submit(self._run_pipeline)

    # ── main pipeline (runs on worker thread) ─────────────────────────────

    def _run_pipeline(self) -> None:
        audio_path: Path | None = None
        try:
            # 1. Stop recording
            try:
                audio_path = self._recorder.stop()
            except RecordingTooShortError:
                logger.info("Recording too short — discarding")
                self._set_status("FlowDictate — Ready")
                self._hide_overlay()
                return

            # 2. Show "Transcribing" state
            self._show_overlay_processing()
            self._set_status("⏳ Transcribing…")

            # 3. Transcribe
            vocab_prompt = self._vocab_db.prompt_string()
            transcriber = Transcriber(
                mode=self._mode,
                vocabulary_prompt=vocab_prompt,
            )
            try:
                raw_text, mode_used = transcriber.transcribe_with_fallback(audio_path)
            except TranscriptionError as exc:
                logger.error("Transcription failed: %s", exc)
                self._set_status("⚠️ Transcription failed")
                self._hide_overlay()
                rumps.notification(
                    "FlowDictate", "Transcription failed",
                    str(exc), sound=False
                )
                return

            if not raw_text.strip():
                logger.info("Empty transcript — nothing to inject")
                self._set_status("FlowDictate — Ready")
                self._hide_overlay()
                return

            # 4. LLM cleanup
            self._set_status("✨ Cleaning up…")
            cleaner = TextCleaner(app_name=self._current_app)
            cleaned_text = cleaner.clean(raw_text)

            # 5. Hide overlay, inject text
            self._hide_overlay()
            self._injector.inject(cleaned_text)

            # 6. Update history
            self._history.append(cleaned_text)
            self._set_status("FlowDictate — Ready")

            logger.info(
                "Pipeline complete — raw_words=%d, final_words=%d, mode=%s",
                len(raw_text.split()),
                len(cleaned_text.split()),
                mode_used,
            )

        except Exception as exc:
            logger.exception("Unexpected pipeline error: %s", exc)
            self._set_status("⚠️ Error — see logs")
            self._hide_overlay()
        finally:
            # Always delete temp audio file
            if audio_path and audio_path.exists():
                try:
                    audio_path.unlink()
                    logger.debug("Temp audio deleted: %s", audio_path.name)
                except OSError:
                    pass
            # Release the pipeline lock
            try:
                self._pipeline_running.release()
            except RuntimeError:
                pass

    # ── overlay helpers (schedule on Tk thread) ───────────────────────────

    def _show_overlay_recording(self) -> None:
        if self._overlay and self._tk_root:
            from overlay import OverlayState
            self._overlay.show(OverlayState.RECORDING)

    def _show_overlay_processing(self) -> None:
        if self._overlay and self._tk_root:
            from overlay import OverlayState
            self._overlay.show(OverlayState.PROCESSING)

    def _hide_overlay(self) -> None:
        if self._overlay:
            self._overlay.hide()

    # ── menu bar helpers ──────────────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        self._status_item.title = text

    def _mode_label(self) -> str:
        cloud_check = " ✓" if self._mode == "cloud" else ""
        local_check = " ✓" if self._mode == "local" else ""
        return f"Mode: Cloud{cloud_check} / Local{local_check}"

    def _update_mode_menu(self) -> None:
        self._mode_item.title = self._mode_label()

    # ── menu callbacks ────────────────────────────────────────────────────

    def _toggle_mode(self, sender) -> None:
        self._mode = "local" if self._mode == "cloud" else "cloud"
        self._update_mode_menu()
        label = "Cloud (OpenAI Whisper)" if self._mode == "cloud" else "Local (faster-whisper)"
        rumps.notification(
            "FlowDictate", f"Switched to {label}", "", sound=False
        )

    def _open_dictionary(self, sender) -> None:
        if FlowDictateApp._tk_root is None:
            return
        if self._dict_window is None:
            self._dict_window = DictionaryManagerWindow(self._vocab_db)
        FlowDictateApp._tk_root.after(0, self._dict_window.open)

    def _open_history(self, sender) -> None:
        if FlowDictateApp._tk_root is None:
            return
        if self._history_window is None:
            self._history_window = HistoryWindow(self)
        else:
            self._history_window = HistoryWindow(self)   # recreate with fresh data
        FlowDictateApp._tk_root.after(0, self._history_window.open)

    def _open_preferences(self, sender) -> None:
        if FlowDictateApp._tk_root is None:
            return
        self._prefs_window = PreferencesWindow(self)
        FlowDictateApp._tk_root.after(0, self._prefs_window.open)

    def _quit(self, sender) -> None:
        logger.info("Quitting FlowDictate…")
        self._hotkey.stop()
        FlowDictateApp._tk_stop.set()
        self._executor.shutdown(wait=False)
        rumps.quit_application()

    # ── startup validation ────────────────────────────────────────────────

    def _check_api_keys(self) -> None:
        missing: list[str] = []
        if not config.OPENAI_API_KEY and self._mode == "cloud":
            missing.append("OPENAI_API_KEY")
        if not config.ANTHROPIC_API_KEY and config.CLEANUP_ENABLED:
            missing.append("ANTHROPIC_API_KEY")
        if missing:
            keys = ", ".join(missing)
            rumps.notification(
                "FlowDictate",
                "API key(s) missing",
                f"Add {keys} to your .env file.",
                sound=False,
            )
            logger.warning("Missing API keys: %s", keys)

    # ── rumps lifecycle ───────────────────────────────────────────────────

    @rumps.clicked("FlowDictate — Ready")
    def _noop(self, sender):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # 1. Start Tkinter in its own thread (overlay + dialogs)
    tk_thread = threading.Thread(target=_start_tk_thread, daemon=True, name="tk-main")
    tk_thread.start()

    # Wait until Tk is ready (max 3 s)
    if not FlowDictateApp._tk_ready.wait(timeout=3.0):
        logger.warning("Tkinter did not initialise in time — overlays may not work")

    # 2. Build and start the menu bar app
    app = FlowDictateApp()

    # 3. Start global hotkey listener
    app._hotkey.start()

    logger.info(
        "FlowDictate started — mode=%s, hotkey=%s, cleanup=%s",
        config.DEFAULT_MODE,
        config.HOTKEY,
        config.CLEANUP_ENABLED,
    )

    # 4. Run rumps event loop (blocks until Quit)
    app.run()


if __name__ == "__main__":
    main()
