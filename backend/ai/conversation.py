"""The listen → think → speak loop, with the face following along.

    idle (neutral) → you start talking → listening → you stop → thinking
    → reply starts → its mood → reply ends → neutral

With a session, the robot sleeps (sleepy face) until called by name, answers
everything while awake, and goes back to sleep on a goodbye or after a
stretch of silence. Sentences heard while asleep are dropped after
transcription, and hellos and goodbyes are answered locally, so neither
costs anything.

Speech recognition, the AI and the voice are passed in, so tests can use
stand-ins: stt.transcribe(audio) -> str, brain.reply(text) -> iterator of
text pieces, tts.synthesize(text) -> int16 audio.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from backend.audio.listener import START, Listener
from backend.communication import RATE, RobotError

from .personality import SentenceSplitter, clean_for_speech, split_mood
from . import wake_word
from .wake_word import Session

SORRY = "Sorry, my brain isn't answering right now."
GREETING = "Hi! I'm listening."
GOODBYE = "Bye bye! Say hey {name} when you need me."


@dataclass
class Turn:
    heard: str = ""
    mood: str | None = None
    reply: list[str] = field(default_factory=list)
    speech_s: float = 0.0       # how long you spoke
    stt_s: float = 0.0          # end of your speech → text
    first_word_s: float = 0.0   # end of your speech → robot starts talking
    total_s: float = 0.0        # end of your speech → robot finished
    error: str | None = None


class Conversation:
    def __init__(self, robot, stt, brain, tts, listener: Listener | None = None,
                 echo_tail_s: float = 0.3, log: Callable[[str], None] = print,
                 session: Session | None = None):
        self.robot, self.stt, self.brain, self.tts = robot, stt, brain, tts
        self.session = session  # None: always awake, answer everything
        self.listener = listener or Listener()
        self.echo_tail_s = echo_tail_s
        self.log = log
        self.turns: list[Turn] = []
        self.ignored: list[str] = []  # heard while asleep, not addressed to the robot
        self._mic: queue.Queue[np.ndarray] = queue.Queue()
        self._mute_until = 0.0

    # --- Loop ---

    def run(self, max_turns: int | None = None, stop: threading.Event | None = None):
        stop = stop or threading.Event()
        self.robot.expr(self._idle_face())
        self.robot.eyes_auto(True)
        self.robot.mic_on(lambda block, _seq: self._mic.put(block))  # reader thread: just queue it
        self.log("listening... (Ctrl-C to stop)")
        try:
            while not stop.is_set() and (max_turns is None or len(self.turns) < max_turns):
                if self.session and self.session.should_nap() and not self.listener.in_speech:
                    self.session.sleep()
                    self.log(f"(no one has spoken for {self.session.idle_timeout_s:g} s: napping)")
                    self.robot.expr("sleepy")
                try:
                    block = self._mic.get(timeout=0.1)
                except queue.Empty:
                    continue
                if time.monotonic() < self._mute_until:
                    continue  # the tail of the robot's own voice
                event = self.listener.feed(block)
                if event is START:
                    if self._awake():
                        self.robot.expr("listening")  # asleep, it keeps the sleepy face
                        if self.session:
                            self.session.touch()
                elif event is not None:
                    try:
                        turn = self.turn(event)
                        if turn:
                            self.turns.append(turn)
                    except RobotError as exc:
                        self.log(f"robot error: {exc}")
                    self._resume()
        finally:
            for step in (self.robot.mic_off, lambda: self.robot.expr("neutral")):  # neutral for whoever's next
                try:
                    step()
                except RobotError:
                    pass

    def _resume(self):
        """Back to listening, ignoring whatever the mic heard meanwhile (mostly the robot)."""
        while not self._mic.empty():
            self._mic.get_nowait()
        self.listener.reset()
        self._mute_until = time.monotonic() + self.echo_tail_s
        self.robot.expr(self._idle_face())

    def _awake(self) -> bool:
        return self.session is None or self.session.awake

    def _idle_face(self) -> str:
        return "neutral" if self._awake() else "sleepy"

    def _say_local(self, turn: "Turn", text: str, t0: float, mood: str = "happy"):
        """A built-in line: spoken without asking the AI, so it is instant and free."""
        turn.first_word_s = time.monotonic() - t0
        turn.mood = mood
        turn.reply.append(text)
        samples = self.tts.synthesize(text)
        self.robot.expr(mood)
        self.robot.play(samples)

    # --- One turn ---

    def turn(self, audio: np.ndarray) -> Turn | None:
        t0 = time.monotonic()
        turn = Turn(speech_s=len(audio) / RATE)
        turn.heard = self.stt.transcribe(audio)  # the face stays on "listening"
        turn.stt_s = time.monotonic() - t0
        if not turn.heard:
            self.log(f"(heard {turn.speech_s:.1f} s of sound but no words)")
            return None
        if self.session:
            kind = self.session.classify(turn.heard)
            if kind == wake_word.IGNORE:
                self.ignored.append(turn.heard)
                self.log(f"(asleep, not for me: {turn.heard})")
                return None
            self.log(f"you: {turn.heard}")
            if kind in (wake_word.WAKE, wake_word.WAKE_AND_ASK) and not self.session.awake:
                self.session.wake()
                self.brain.forget()  # each session starts a fresh conversation
                self.log("(awake)")
            if kind == wake_word.GOODBYE:
                self._say_local(turn, GOODBYE.format(name=self.session.name), t0)
                self.session.sleep()
                self.log(f"robot [happy]: {turn.reply[0]}  (going to sleep)")
                return self._finish(turn, t0)
            if kind == wake_word.WAKE:
                self._say_local(turn, GREETING, t0)
                self.log(f"robot [happy]: {GREETING}")
                return self._finish(turn, t0)
        else:
            self.log(f"you: {turn.heard}")
        self.robot.expr("thinking")

        pieces: queue.Queue[tuple] = queue.Queue()
        threading.Thread(target=self._think, args=(turn.heard, pieces), daemon=True).start()

        mood = None
        while True:
            kind, *rest = pieces.get()
            if kind == "mood":
                mood = rest[0]
            elif kind == "say":
                text, samples = rest
                if not turn.reply:  # about to speak: show the mood now
                    turn.first_word_s = time.monotonic() - t0
                    turn.mood = mood
                    self.robot.expr(mood or "neutral")
                turn.reply.append(text)
                self.robot.play(samples)
            elif kind == "error":
                turn.error = rest[0]
                self.log(f"AI error: {turn.error}")
                if not turn.reply:
                    self.robot.expr("sad")
                    turn.reply.append(SORRY)
                    self.robot.play(self.tts.synthesize(SORRY))
            elif kind == "done":
                break
        self.log(f"robot [{turn.mood or 'neutral'}]: {' '.join(turn.reply)}")
        turn = self._finish(turn, t0)
        self.log(f"  timing: you spoke {turn.speech_s:.1f} s; text after {turn.stt_s:.1f} s, "
                 f"first word after {turn.first_word_s:.1f} s, done after {turn.total_s:.1f} s")
        return turn

    def _finish(self, turn: "Turn", t0: float) -> "Turn":
        turn.total_s = time.monotonic() - t0
        if self.session:
            self.session.touch()
        return turn

    def _think(self, text: str, out: queue.Queue):
        """Worker: streams the reply and turns each sentence into audio while the
        previous one plays."""
        def say(sentence: str):
            sentence = clean_for_speech(sentence)
            if sentence:
                out.put(("say", sentence, self.tts.synthesize(sentence)))

        try:
            splitter = SentenceSplitter()
            head, mood_known = "", False
            for delta in self.brain.reply(text):
                if not mood_known:
                    head += delta
                    stripped = head.lstrip()
                    if not stripped or (stripped.startswith("[") and "]" not in stripped and len(stripped) < 20):
                        continue  # the mood tag may still be arriving
                    mood, delta = split_mood(head)
                    out.put(("mood", mood))
                    mood_known = True
                for sentence in splitter.feed(delta):
                    say(sentence)
            if not mood_known:
                mood, rest = split_mood(head)
                out.put(("mood", mood))
                splitter.feed(rest)
            for sentence in splitter.flush():
                say(sentence)
        except Exception as exc:  # noqa: BLE001 - reported to the loop, which apologises
            out.put(("error", str(exc)))
        finally:
            out.put(("done",))
