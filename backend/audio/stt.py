"""Speech recognition on this PC with faster-whisper.

The model downloads from Hugging Face on first use (base.en about 150 MB,
small.en about 500 MB) into the usual Hugging Face cache.
"""

from __future__ import annotations

import os

import numpy as np

RATE = 16000


class SpeechToText:
    def __init__(self, model: str = "base.en", threads: int | None = None, hotwords: str | None = None):
        from faster_whisper import WhisperModel

        self.model_name = model
        self.hotwords = hotwords  # e.g. the robot's name, so it is recognised more often
        self._model = WhisperModel(model, device="cpu", compute_type="int8",
                                   cpu_threads=threads or os.cpu_count() or 4)

    def transcribe(self, audio: np.ndarray) -> str:
        """16 kHz int16 mono in, text out ("" if nothing was said)."""
        x = audio.astype(np.float32) / 32768
        segments, _info = self._model.transcribe(
            x, language="en", beam_size=1, condition_on_previous_text=False, vad_filter=False,
            hotwords=self.hotwords)
        parts = [s.text.strip() for s in segments if s.no_speech_prob < 0.6]
        return " ".join(p for p in parts if p).strip()
