"""A stand-in for the robot that speaks protocol v0, for tests without hardware.

It is a Transport: Robot writes command lines to it and reads reply lines
from it. Knobs let tests drop replies, stream the mic with gaps, send
periodic telemetry and reboot.
"""

import base64
import json
import queue
import threading
import time

import numpy as np

EXPRESSIONS = {"neutral", "happy", "sad", "angry", "surprised", "sleepy", "listening", "thinking"}
CAPACITY = 32768
RATE = 16000


class FakeRobot:
    def __init__(self, telemetry_period: float | None = None):
        self._out: queue.Queue[bytes] = queue.Queue()
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self.received: list[str] = []      # every command line, in order
        self.drop_replies: set[str] = set()  # commands to swallow without replying
        self.reply_delay = 0.0
        self.volume = 50
        self.uptime_start = time.monotonic()

        # pcm buffer that drains in real time
        self._buffered = 0.0
        self._buffer_time = time.monotonic()
        self.max_buffered = 0
        self.dropped_total = 0

        # mic stream
        self.mic_skip: set[int] = set()  # sequence numbers to leave out
        self.mic_source = None  # optional fn(seq) -> 320 int16 samples; default: the seq number
        self._mic_on = threading.Event()
        self._mic_seq = 0
        threading.Thread(target=self._mic_loop, daemon=True).start()

        if telemetry_period:
            threading.Thread(target=self._telemetry_loop, args=(telemetry_period,), daemon=True).start()

    # --- Transport ---

    def write(self, data: bytes) -> int:
        for line in data.decode().splitlines():
            self._command(line.strip())
        return len(data)

    def readline(self) -> bytes:
        if self._closed.is_set():
            raise OSError("port closed")
        try:
            return self._out.get(timeout=0.05)
        except queue.Empty:
            return b""

    def close(self):
        self._closed.set()

    # --- Test helpers ---

    def emit(self, msg: dict | str):
        """Sends a line as the robot: a dict becomes JSON, a str is a log line."""
        text = msg if isinstance(msg, str) else json.dumps(msg, separators=(",", ":"))
        self._out.put(text.encode() + b"\n")

    def reboot(self):
        self._mic_on.clear()
        self._buffered = 0
        self.emit("ESP-ROM:esp32s3-20210327")  # garbage-ish boot log
        self.emit({"type": "boot", "reset_reason": 1, "idf": "fake", "lcd": True, "audio": True, "mic": True})

    def telemetry(self) -> dict:
        return {"type": "telemetry", "uptime_ms": int((time.monotonic() - self.uptime_start) * 1000),
                "audio_ms": int(self._level() * 1000 / RATE), "dropouts": 0, "mic_peak": 0.0, "mic_overruns": 0}

    # --- Robot behaviour ---

    def _level(self) -> float:
        now = time.monotonic()
        self._buffered = max(0.0, self._buffered - (now - self._buffer_time) * RATE)
        self._buffer_time = now
        return self._buffered

    def _reply(self, name: str, msg: dict):
        if name in self.drop_replies:
            return
        if self.reply_delay:
            time.sleep(self.reply_delay)
        self.emit(msg)

    def _command(self, line: str):
        self.received.append(line)
        name, _, args = line.partition(" ")
        ack = {"type": "ack", "cmd": name}
        with self._lock:
            if name == "ping":
                self._reply(name, {"type": "pong", "uptime_ms": 1})
            elif name == "status":
                self._reply(name, self.telemetry())
            elif name == "expr":
                if args in EXPRESSIONS:
                    self._reply(name, {**ack, "name": args})
                else:
                    self._reply(name, {"type": "error", "msg": "usage: expr <...>"})
            elif name in ("look", "blink", "eyes", "talk", "beep", "rate", "bright", "servo", "relax"):
                self._reply(name, ack)
            elif name == "vol":
                if args:
                    self.volume = int(args)
                self._reply(name, {**ack, "percent": self.volume})
            elif name == "mic":
                if args == "on":
                    self._mic_on.set()
                elif args == "off":
                    self._mic_on.clear()
                self._reply(name, {**ack, "on": self._mic_on.is_set(), "gain_db": 18})
            elif name == "pcm":
                dropped = 0
                if args == "stop":
                    self._buffered = 0
                elif args != "end":
                    n = len(base64.b64decode(args)) // 2
                    level = self._level()
                    fit = min(n, int(CAPACITY - level))
                    dropped = n - fit
                    self.dropped_total += dropped
                    self._buffered = level + fit
                    self.max_buffered = max(self.max_buffered, int(self._buffered))
                self._reply(name, {"type": "pcm", "buffered": int(self._level()), "capacity": CAPACITY,
                                   "dropped": dropped})
            elif name == "reboot":
                self._reply(name, ack)
                self.reboot()
            else:
                self._reply(name, {"type": "error", "msg": "unknown command", "cmd": name})

    def _mic_loop(self):
        block = np.zeros(320, dtype="<i2")
        while not self._closed.is_set():
            if not self._mic_on.wait(0.05):
                continue
            seq = self._mic_seq
            self._mic_seq += 1
            if seq not in self.mic_skip:
                if self.mic_source:
                    block[:] = self.mic_source(seq)
                else:
                    block[:] = seq  # each block carries its own number, so tests can check order
                self.emit({"type": "mic", "seq": seq, "data": base64.b64encode(block.tobytes()).decode()})
            time.sleep(0.02)

    def _telemetry_loop(self, period: float):
        while not self._closed.is_set():
            self.emit(self.telemetry())
            time.sleep(period)
