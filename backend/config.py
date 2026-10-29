"""Settings, from the environment or a .env file in the repository root.

.env holds secrets such as the OpenAI API key and is ignored by git:

    OPENAI_API_KEY=sk-...
    AIBOT_OPENAI_MODEL=...      # optional
    AIBOT_OPENAI_REASONING=...  # optional, GPT-5 models only
    AIBOT_STT_MODEL=base.en     # optional
    AIBOT_VOICE=en_US-lessac-medium  # optional, any Piper voice, downloaded on first use
    AIBOT_NAME=Mochi            # optional, the name that wakes the robot
    AIBOT_IDLE_TIMEOUT_S=120    # optional, silence before it naps

Variables already set in the environment win over .env.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"
# GPT-5 models think before answering unless told not to, which adds delay.
# "none" keeps replies quick; set AIBOT_OPENAI_REASONING=low (etc.) for more thought.
DEFAULT_OPENAI_REASONING = "none"
DEFAULT_STT_MODEL = "base.en"


def load_env(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def setting(name: str, default: str | None = None) -> str | None:
    load_env()
    return os.environ.get(name) or default


def openai_key() -> str:
    key = setting("OPENAI_API_KEY")
    if not key:
        raise SystemExit(f"OPENAI_API_KEY is not set. Put it in {ENV_FILE} as OPENAI_API_KEY=sk-...")
    return key
