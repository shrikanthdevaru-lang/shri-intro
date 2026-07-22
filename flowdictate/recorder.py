"""
recorder.py — Microphone capture via sounddevice.

Records audio while the hotkey is held, writes a temporary WAV file, and
returns the path for the transcriber to consume.  The temp file is deleted
immediately after transcription.

All recording happens on a background thread so it never blocks the event loop.
"""

from __future__ import annotations

import logging
import os
import queue
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd

import config

logger = logging.getLogger(__name__)


class AudioRecorder:
    """
    Non-blocking microphone recorder.

    Usage:
        recorder = AudioRecorder()
        recorder.start()      # begins capturing
        ...
        path = recorder.stop()  # stops capturing, returns WAV file path
    """

    def __init__(self) -> None:
        self._recording: bool = False
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._start_time: float = 0.0
        self._lock = threading.Lock()

    # ── public API ────────────────────────────────────────────────────────

    def start(self) -> None:
        """Begin recording from the default input device."""
        if self._recording:
            logger.warning("Recorder already running — ignoring start()")
            return

        with self._lock:
            self._frames = []
            self._recording = True
            self._start_time = time.perf_counter()

        try:
            self._stream = sd.InputStream(
                samplerate=config.SAMPLE_RATE,
                channels=config.CHANNELS,
                dtype=config.DTYPE,
                callback=self._audio_callback,
                blocksize=1024,
            )
            self._stream.start()
            logger.info(
                "Recording started — device: %s",
                sd.query_devices(kind="input")["name"],
            )
        except Exception as exc:
            self._recording = False
            raise MicrophoneError(f"Cannot open microphone: {exc}") from exc

    def stop(self) -> Path:
        """
        Stop recording and write a temporary WAV file.

        Returns:
            Path to the temporary WAV file (caller is responsible for deleting it).

        Raises:
            RecordingTooShortError: if less than 0.3 s of audio was captured.
        """
        if not self._recording:
            raise RuntimeError("Recorder is not running")

        with self._lock:
            self._recording = False

        duration = time.perf_counter() - self._start_time

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        with self._lock:
            frames = list(self._frames)

        if not frames:
            raise RecordingTooShortError("No audio captured")

        audio = np.concatenate(frames, axis=0)
        duration_actual = len(audio) / config.SAMPLE_RATE

        if duration_actual < 0.3:
            raise RecordingTooShortError(
                f"Recording too short ({duration_actual:.2f}s)"
            )

        path = self._write_wav(audio)
        logger.info(
            "Recording stopped — duration=%.2fs, samples=%d, file=%s",
            duration_actual,
            len(audio),
            path.name,
        )
        return path

    def is_recording(self) -> bool:
        return self._recording

    # ── private ───────────────────────────────────────────────────────────

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.debug("sounddevice status: %s", status)
        if self._recording:
            with self._lock:
                self._frames.append(indata.copy())

    @staticmethod
    def _write_wav(audio: np.ndarray) -> Path:
        """Write float32 audio to a 16-bit PCM WAV in TEMP_DIR."""
        config.TEMP_DIR.mkdir(parents=True, exist_ok=True)

        # Convert float32 → int16
        pcm = (audio * 32767).astype(np.int16)

        fd, tmp_path = tempfile.mkstemp(
            suffix=".wav",
            prefix="flowdictate_",
            dir=str(config.TEMP_DIR),
        )
        os.close(fd)

        with wave.open(tmp_path, "wb") as wf:
            wf.setnchannels(config.CHANNELS)
            wf.setsampwidth(2)                        # 16-bit = 2 bytes
            wf.setframerate(config.SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())

        return Path(tmp_path)


# ── custom exceptions ─────────────────────────────────────────────────────────

class MicrophoneError(RuntimeError):
    """Raised when the microphone cannot be opened."""


class RecordingTooShortError(ValueError):
    """Raised when the captured audio is too short to transcribe."""
