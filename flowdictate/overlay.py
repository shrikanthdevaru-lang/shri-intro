"""
overlay.py — Floating recording / transcribing indicator (Tkinter).

A small pill-shaped transparent window that appears at the bottom-centre of
the screen.  It has two states:

  • RECORDING   — animated waveform bars + "Recording…" label
  • PROCESSING  — spinning arc + "Transcribing…" label

The window runs entirely on the Tkinter main-thread via `after()` calls so it
never needs its own thread; callers simply invoke show()/hide() from any thread
and the UI updates are scheduled safely.
"""

from __future__ import annotations

import math
import threading
import tkinter as tk
from enum import Enum, auto
from typing import Callable

import config


class OverlayState(Enum):
    RECORDING = auto()
    PROCESSING = auto()


# Animation constants
_WAVE_BARS = 7
_WAVE_PERIOD = 80        # ms per animation frame
_SPIN_PERIOD = 30        # ms per spinner frame
_FADE_STEPS = 12
_FADE_INTERVAL = 18      # ms per opacity step


class RecordingOverlay:
    """
    Thread-safe floating overlay widget.

    Usage (from any thread):
        overlay.show(OverlayState.RECORDING)
        overlay.hide()
    """

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._window: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._label_var: tk.StringVar | None = None
        self._state: OverlayState = OverlayState.RECORDING
        self._anim_job: str | None = None    # after() handle
        self._fade_job: str | None = None
        self._anim_frame: int = 0
        self._spin_angle: float = 0.0
        self._alpha: float = 0.0
        self._lock = threading.Lock()

    # ── public API (thread-safe) ──────────────────────────────────────────

    def show(self, state: OverlayState = OverlayState.RECORDING) -> None:
        """Show (or update) the overlay on the Tk thread."""
        self._state = state
        self._root.after(0, self._show_on_main)

    def hide(self) -> None:
        """Start a fade-out and destroy the overlay."""
        self._root.after(0, self._start_fade_out)

    # ── internal — must run on Tk main thread ────────────────────────────

    def _show_on_main(self) -> None:
        if self._window is None or not tk.Toplevel.winfo_exists(self._window):
            self._create_window()
        else:
            self._update_state()
        self._start_fade_in()

    def _create_window(self) -> None:
        win = tk.Toplevel(self._root)
        self._window = win

        win.overrideredirect(True)           # no title bar / chrome
        win.attributes("-topmost", True)     # always on top
        win.attributes("-alpha", 0.0)        # start transparent
        win.configure(bg=config.OVERLAY_BG_COLOR)

        # Position: bottom-centre
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = (sw - config.OVERLAY_WIDTH) // 2
        y = sh - config.OVERLAY_HEIGHT - config.OVERLAY_BOTTOM_MARGIN
        win.geometry(f"{config.OVERLAY_WIDTH}x{config.OVERLAY_HEIGHT}+{x}+{y}")

        # Try rounded corners via platform-specific approach
        try:
            # macOS: use wm_attributes for round corners where available
            win.attributes("-modified", False)
        except Exception:
            pass

        # Canvas for animation
        canvas = tk.Canvas(
            win,
            width=config.OVERLAY_WIDTH,
            height=config.OVERLAY_HEIGHT,
            bg=config.OVERLAY_BG_COLOR,
            highlightthickness=0,
        )
        canvas.pack()
        self._canvas = canvas

        # Rounded background rect (simulated pill shape)
        r = config.OVERLAY_HEIGHT // 2
        self._draw_pill(canvas, r)

        # Status label
        self._label_var = tk.StringVar()
        canvas.create_text(
            config.OVERLAY_WIDTH // 2,
            config.OVERLAY_HEIGHT - 10,
            text="",
            fill=config.OVERLAY_TEXT_COLOR,
            font=(config.OVERLAY_FONT_FAMILY, 10),
            tags="status_label",
        )

        self._update_state()

    def _draw_pill(self, canvas: tk.Canvas, radius: int) -> None:
        """Draw the pill-shaped background on the canvas."""
        w, h = config.OVERLAY_WIDTH, config.OVERLAY_HEIGHT
        canvas.create_oval(0, 0, radius * 2, h, fill=config.OVERLAY_BG_COLOR,
                           outline="", tags="bg")
        canvas.create_oval(w - radius * 2, 0, w, h, fill=config.OVERLAY_BG_COLOR,
                           outline="", tags="bg")
        canvas.create_rectangle(radius, 0, w - radius, h,
                                fill=config.OVERLAY_BG_COLOR, outline="", tags="bg")
        # Subtle border
        canvas.create_arc(1, 1, radius * 2 - 1, h - 1,
                          start=90, extent=180, outline="#444466",
                          style="arc", tags="border")
        canvas.create_arc(w - radius * 2 + 1, 1, w - 1, h - 1,
                          start=270, extent=180, outline="#444466",
                          style="arc", tags="border")
        canvas.create_line(radius, 1, w - radius, 1, fill="#444466", tags="border")
        canvas.create_line(radius, h - 1, w - radius, h - 1,
                           fill="#444466", tags="border")

    def _update_state(self) -> None:
        if self._canvas is None:
            return
        # Cancel running animation
        if self._anim_job:
            self._root.after_cancel(self._anim_job)
            self._anim_job = None

        self._canvas.delete("anim")
        self._anim_frame = 0
        self._spin_angle = 0.0

        if self._state == OverlayState.RECORDING:
            self._canvas.itemconfigure("status_label",
                                       text="● Recording…")
            self._schedule_wave()
        else:
            self._canvas.itemconfigure("status_label",
                                       text="◌ Transcribing…")
            self._schedule_spinner()

    # ── waveform animation ────────────────────────────────────────────────

    def _schedule_wave(self) -> None:
        self._draw_wave()
        self._anim_job = self._root.after(_WAVE_PERIOD, self._schedule_wave)

    def _draw_wave(self) -> None:
        if self._canvas is None:
            return
        self._canvas.delete("anim")
        cx = config.OVERLAY_WIDTH // 2
        cy = (config.OVERLAY_HEIGHT - 18) // 2
        bar_w = 4
        spacing = 8
        total = _WAVE_BARS * spacing
        start_x = cx - total // 2

        t = self._anim_frame * 0.25
        for i in range(_WAVE_BARS):
            phase = i * (2 * math.pi / _WAVE_BARS)
            amp = 0.4 + 0.6 * abs(math.sin(t + phase))
            max_h = 20
            bh = max(4, int(amp * max_h))
            x = start_x + i * spacing
            y0 = cy - bh // 2
            y1 = cy + bh // 2
            # Colour interpolation: accent → lighter
            intensity = int(200 + 55 * amp)
            r = min(255, int(0xe9 * amp + 0x60 * (1 - amp)))
            g = min(255, int(0x45 * amp))
            b = min(255, int(0x60 * (1 - amp) + intensity * 0.1))
            colour = f"#{r:02x}{g:02x}{b:02x}"
            self._canvas.create_rectangle(
                x, y0, x + bar_w, y1,
                fill=colour, outline="", tags="anim"
            )
        self._anim_frame += 1

    # ── spinner animation ─────────────────────────────────────────────────

    def _schedule_spinner(self) -> None:
        self._draw_spinner()
        self._anim_job = self._root.after(_SPIN_PERIOD, self._schedule_spinner)

    def _draw_spinner(self) -> None:
        if self._canvas is None:
            return
        self._canvas.delete("anim")
        cx = config.OVERLAY_WIDTH // 2
        cy = (config.OVERLAY_HEIGHT - 18) // 2
        r = 10
        start = self._spin_angle
        self._canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=start, extent=270,
            outline=config.OVERLAY_ACCENT_COLOR,
            width=3, style="arc", tags="anim"
        )
        self._spin_angle = (self._spin_angle + 12) % 360

    # ── fade in / out ─────────────────────────────────────────────────────

    def _start_fade_in(self) -> None:
        if self._fade_job:
            self._root.after_cancel(self._fade_job)
            self._fade_job = None
        self._alpha = float(
            self._window.attributes("-alpha") if self._window else 0.0
        )
        self._fade_step(direction=1)

    def _start_fade_out(self) -> None:
        if self._window is None:
            return
        if self._fade_job:
            self._root.after_cancel(self._fade_job)
            self._fade_job = None
        self._alpha = float(self._window.attributes("-alpha"))
        self._fade_step(direction=-1)

    def _fade_step(self, direction: int) -> None:
        if self._window is None:
            return
        step = direction / _FADE_STEPS
        self._alpha = max(0.0, min(1.0, self._alpha + step))
        self._window.attributes("-alpha", self._alpha)

        if direction == 1 and self._alpha < 0.92:
            self._fade_job = self._root.after(
                _FADE_INTERVAL, lambda: self._fade_step(direction)
            )
        elif direction == -1 and self._alpha > 0.0:
            self._fade_job = self._root.after(
                _FADE_INTERVAL, lambda: self._fade_step(direction)
            )
        elif direction == -1 and self._alpha <= 0.0:
            # Fully hidden — cancel animation and destroy
            if self._anim_job:
                self._root.after_cancel(self._anim_job)
                self._anim_job = None
            if self._window:
                self._window.destroy()
                self._window = None
                self._canvas = None
