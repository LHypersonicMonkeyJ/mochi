"""Whether the robot is awake, and what each heard sentence means for that.

The robot sleeps until someone says its name ("Hey Mochi!"). Awake, it answers
everything, until a goodbye ("Bye bye Mochi!") or a stretch of silence puts it
back to sleep. Sentences are transcribed on the PC for free; only questions
asked while awake go to the AI.
"""

from __future__ import annotations

import re
import time
from typing import Callable, Iterable

DEFAULT_NAME = "Mochi"
DEFAULT_IDLE_TIMEOUT_S = 120.0

# Ways speech recognition writes names it doesn't know well.
NAME_VARIANTS = {
    "mochi": ("mochi", "mochie", "mochee", "mochy", "motchi", "mocchi", "moochi", "moochie", "mouchi"),
}

GREETING_WORDS = {"hey", "hi", "hello", "hiya", "ok", "okay", "yo", "oh", "there", "good", "morning",
                  "afternoon", "evening", "dear"}
GOODBYE_PHRASES = ("bye", "goodbye", "good bye", "good night", "goodnight", "see you", "see ya",
                   "go to sleep", "sleep")

# What classify() returns.
IGNORE = "ignore"        # asleep, and not called
WAKE = "wake"            # called by name and nothing else: greet
WAKE_AND_ASK = "ask+"    # called by name with a question: wake and answer it
ASK = "ask"              # awake: answer it
GOODBYE = "goodbye"      # told to go to sleep


def _words(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).split()


class Session:
    def __init__(self, name: str = DEFAULT_NAME, idle_timeout_s: float = DEFAULT_IDLE_TIMEOUT_S,
                 aliases: Iterable[str] = (), clock: Callable[[], float] = time.monotonic):
        self.name = name
        key = name.lower()
        self.names = tuple(dict.fromkeys([key, *NAME_VARIANTS.get(key, ()), *(a.lower() for a in aliases)]))
        self.idle_timeout_s = idle_timeout_s
        self._clock = clock
        self.awake = False
        self._last_activity = clock()

    # --- What was said ---

    def _name_at(self, words: list[str]) -> int | None:
        for i, w in enumerate(words):
            if w in self.names:
                return i
        return None

    def classify(self, text: str) -> str:
        words = _words(text)
        at = self._name_at(words)
        if at is None:
            return ASK if self.awake else IGNORE
        joined = " " + " ".join(words) + " "
        if any(f" {p} " in joined for p in GOODBYE_PHRASES):
            return GOODBYE if self.awake else IGNORE
        rest = [w for i, w in enumerate(words) if i != at and w not in GREETING_WORDS]
        if self.awake:
            return ASK if rest else WAKE
        return WAKE_AND_ASK if rest else WAKE

    # --- State ---

    def wake(self):
        self.awake = True
        self.touch()

    def sleep(self):
        self.awake = False

    def touch(self):
        """Someone spoke or the robot answered: restart the nap countdown."""
        self._last_activity = self._clock()

    def should_nap(self) -> bool:
        return self.awake and self._clock() - self._last_activity > self.idle_timeout_s
