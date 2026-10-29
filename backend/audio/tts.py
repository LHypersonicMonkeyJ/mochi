"""Speech synthesis on this PC with Piper, at the robot's 16 kHz.

Uses the same voice as firmware/tools/say.py, from firmware/tools/voices/,
downloading it there (about 60 MB) if it is missing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

RATE = 16000
VOICES = Path(__file__).resolve().parents[2] / "firmware" / "tools" / "voices"
DEFAULT_VOICE = "en_US-lessac-medium"


def resample(audio: np.ndarray, rate: int) -> np.ndarray:
    if rate == RATE or len(audio) == 0:
        return audio.astype(np.int16)
    x = audio.astype(np.float32)
    if rate > RATE:
        # Moving-average low-pass before downsampling, to limit aliasing.
        k = int(round(rate / RATE)) + 1
        x = np.convolve(x, np.ones(k) / k, mode="same")
    n_out = int(len(x) * RATE / rate)
    t = np.arange(n_out) * rate / RATE
    return np.clip(np.interp(t, np.arange(len(x)), x), -32768, 32767).astype(np.int16)


class TextToSpeech:
    def __init__(self, voice: str = DEFAULT_VOICE):
        from piper import PiperVoice

        model = VOICES / f"{voice}.onnx"
        if not model.exists():
            print(f"downloading voice {voice} into {VOICES} ...", file=sys.stderr)
            VOICES.mkdir(parents=True, exist_ok=True)
            subprocess.run([sys.executable, "-m", "piper.download_voices", "--data-dir", str(VOICES), voice],
                           check=True)
        self._voice = PiperVoice.load(str(model))

    def synthesize(self, text: str) -> np.ndarray:
        """Text in, 16 kHz int16 mono out."""
        chunks = list(self._voice.synthesize(text))
        if not chunks:
            return np.zeros(0, dtype=np.int16)
        audio = np.concatenate([c.audio_int16_array for c in chunks])
        return resample(audio, chunks[0].sample_rate)
