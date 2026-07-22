"""
transcriber.py — Whisper transcription (cloud + local).

MODE A — Cloud:
    Calls OpenAI Whisper API (whisper-1).  Passes custom vocabulary as the
    ``prompt`` parameter for better proper-noun recognition.

MODE B — Local (privacy / offline):
    Uses faster-whisper with the configured model size and int8 quantisation.
    Loads the model lazily on first use (avoids startup delay).

Both modes are fully synchronous — run them on a background thread via the
executor in main.py.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)

# ── lazy-loaded local model ───────────────────────────────────────────────────
_local_model = None
_local_model_lock = None


def _get_local_model():
    """Return a cached faster-whisper WhisperModel, loading on first call."""
    global _local_model, _local_model_lock
    import threading
    if _local_model_lock is None:
        _local_model_lock = threading.Lock()

    with _local_model_lock:
        if _local_model is None:
            from faster_whisper import WhisperModel  # type: ignore
            logger.info(
                "Loading local Whisper model '%s' (int8, CPU)…",
                config.WHISPER_LOCAL_MODEL,
            )
            t0 = time.perf_counter()
            _local_model = WhisperModel(
                config.WHISPER_LOCAL_MODEL,
                device="cpu",
                compute_type="int8",
            )
            logger.info(
                "Local Whisper model loaded in %.1fs", time.perf_counter() - t0
            )
    return _local_model


# ─────────────────────────────────────────────────────────────────────────────
# Public interface
# ─────────────────────────────────────────────────────────────────────────────

class Transcriber:
    """
    Wraps cloud and local Whisper transcription.

    Args:
        mode: "cloud" or "local"
        vocabulary_prompt: comma-separated custom words fed to Whisper
    """

    def __init__(self, mode: str = "cloud", vocabulary_prompt: str = "") -> None:
        self.mode = mode.lower()
        self.vocabulary_prompt = vocabulary_prompt

    def transcribe(self, audio_path: Path) -> str:
        """
        Transcribe *audio_path* and return plain text.

        Raises:
            TranscriptionError: on unrecoverable failure.
        """
        t0 = time.perf_counter()
        try:
            if self.mode == "cloud":
                text = self._transcribe_cloud(audio_path)
            else:
                text = self._transcribe_local(audio_path)

            word_count = len(text.split())
            latency = time.perf_counter() - t0
            logger.info(
                "Transcription complete — mode=%s, words=%d, latency=%.2fs",
                self.mode,
                word_count,
                latency,
            )
            return text.strip()

        except Exception as exc:
            latency = time.perf_counter() - t0
            logger.error(
                "Transcription failed — mode=%s, latency=%.2fs, error=%s",
                self.mode,
                latency,
                type(exc).__name__,
            )
            raise TranscriptionError(str(exc)) from exc

    def transcribe_with_fallback(self, audio_path: Path) -> tuple[str, str]:
        """
        Try cloud transcription; fall back to local on any failure.

        Returns:
            (text, mode_used)  where mode_used is "cloud" or "local".
        """
        if self.mode == "local":
            return self._transcribe_local(audio_path).strip(), "local"

        # Try cloud first
        try:
            if not config.OPENAI_API_KEY:
                raise TranscriptionError("No OpenAI API key")
            if not _has_internet():
                raise TranscriptionError("No internet connection")
            text = self._transcribe_cloud(audio_path)
            return text.strip(), "cloud"
        except Exception as exc:
            logger.warning(
                "Cloud transcription failed (%s) — falling back to local", exc
            )
            try:
                text = self._transcribe_local(audio_path)
                return text.strip(), "local"
            except Exception as local_exc:
                raise TranscriptionError(
                    f"Both cloud and local transcription failed: {local_exc}"
                ) from local_exc

    # ── cloud ─────────────────────────────────────────────────────────────

    def _transcribe_cloud(self, audio_path: Path) -> str:
        import openai

        if not config.OPENAI_API_KEY:
            raise TranscriptionError(
                "OPENAI_API_KEY not set — add it to .env"
            )

        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        with audio_path.open("rb") as f:
            response = client.audio.transcriptions.create(
                model=config.WHISPER_CLOUD_MODEL,
                file=f,
                response_format="text",
                prompt=self.vocabulary_prompt or None,
            )
        # response is a plain str when response_format="text"
        return str(response)

    # ── local ─────────────────────────────────────────────────────────────

    def _transcribe_local(self, audio_path: Path) -> str:
        model = _get_local_model()
        segments, info = model.transcribe(
            str(audio_path),
            language=None,           # auto-detect
            vad_filter=True,
            initial_prompt=self.vocabulary_prompt or None,
        )
        logger.info(
            "Local transcription — detected language: %s (prob=%.2f)",
            info.language,
            info.language_probability,
        )
        text = " ".join(seg.text for seg in segments)
        return text


# ── helpers ───────────────────────────────────────────────────────────────────

def _has_internet(host: str = "8.8.8.8", port: int = 53, timeout: float = 2.0) -> bool:
    """Quick connectivity check via TCP connect to Google DNS."""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except OSError:
        return False


# ── exceptions ────────────────────────────────────────────────────────────────

class TranscriptionError(RuntimeError):
    """Raised when transcription cannot produce a result."""
