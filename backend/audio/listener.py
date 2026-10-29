"""Finds where someone starts and stops talking in the mic stream.

Works on 20 ms blocks of 16 kHz int16 audio. Loudness is compared with an
adaptive noise floor: speech starts when blocks stay well above the floor,
and ends after a stretch of quiet. Pure code, no threads.

    listener = Listener()
    for block in blocks:
        event = listener.feed(block)
        if event == START: ...
        elif isinstance(event, np.ndarray): utterance = event
"""

from __future__ import annotations

import collections

import numpy as np

RATE = 16000
BLOCK_S = 0.02

START = "start"   # feed() returns this when speech begins


def block_dbfs(block: np.ndarray) -> float:
    x = block.astype(np.float32) / 32768
    return float(10 * np.log10(np.mean(x * x) + 1e-12))


class Listener:
    def __init__(self, start_db: float = 12, keep_db: float = 6, start_s: float = 0.06,
                 end_silence_s: float = 0.7, preroll_s: float = 0.3, min_speech_s: float = 0.3,
                 max_speech_s: float = 15, min_level_db: float = -55):
        self.start_db = start_db          # above the floor to start
        self.keep_db = keep_db            # above the floor to count as still talking
        self.start_blocks = max(1, round(start_s / BLOCK_S))
        self.end_blocks = round(end_silence_s / BLOCK_S)
        self.min_blocks = round(min_speech_s / BLOCK_S)
        self.max_blocks = round(max_speech_s / BLOCK_S)
        self.min_level_db = min_level_db  # never start below this, however quiet the room
        self.steady_db = 6.0              # level spread below which a max-length "utterance" is noise
        self._preroll: collections.deque[np.ndarray] = collections.deque(maxlen=round(preroll_s / BLOCK_S))
        self.floor_db: float | None = None
        self.reset()

    def reset(self):
        """Forgets any speech in progress (the noise floor is kept)."""
        self._loud_run = 0
        self._quiet_run = 0
        self._speech: list[np.ndarray] | None = None
        self._levels: list[float] = []
        self._voiced = 0
        self._preroll.clear()

    @property
    def in_speech(self) -> bool:
        return self._speech is not None

    def feed(self, block: np.ndarray):
        """Returns START, a finished utterance (int16 array), or None."""
        db = block_dbfs(block)
        self._track_floor(db)
        loud = db > max(self.floor_db + self.start_db, self.min_level_db)
        voiced = db > max(self.floor_db + self.keep_db, self.min_level_db)

        if self._speech is None:
            self._preroll.append(block)
            self._loud_run = self._loud_run + 1 if loud else 0
            if self._loud_run >= self.start_blocks:
                self._speech = list(self._preroll)
                self._voiced = self._loud_run
                self._quiet_run = 0
                self._preroll.clear()
                return START
            return None

        self._speech.append(block)
        self._levels.append(db)
        if voiced:
            self._voiced += 1
            self._quiet_run = 0
        else:
            self._quiet_run += 1
        if self._quiet_run >= self.end_blocks or len(self._speech) >= self.max_blocks:
            speech, levels, voiced_blocks = self._speech, self._levels, self._voiced
            hit_max = len(speech) >= self.max_blocks
            self.reset()
            if voiced_blocks < self.min_blocks:
                return None  # a click or a cough, not speech
            if hit_max and np.percentile(levels, 90) - np.percentile(levels, 10) < self.steady_db:
                # Talking rises and falls; this stayed level, so the room got
                # louder (a fan, say). Learn it as the new floor instead.
                self.floor_db = float(np.median(levels))
                return None
            return np.concatenate(speech)
        return None

    def _track_floor(self, db: float):
        # Falls quickly to quiet blocks, rises slowly (about 1 dB per second),
        # so speech barely moves it but a louder room is learned in a while.
        if self.floor_db is None:
            self.floor_db = db
        elif db < self.floor_db:
            self.floor_db = 0.7 * self.floor_db + 0.3 * db
        elif self._speech is None:
            self.floor_db += min(db - self.floor_db, 0.02)
