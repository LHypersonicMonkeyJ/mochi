"""Talk with the robot.

    python3 -m backend.chat /dev/ttyACM0
    python3 -m backend.chat /dev/ttyACM0 --stt-model small.en   # more accurate, slower
    python3 -m backend.chat /dev/ttyACM0 --always-answer        # never sleeps
    python3 -m backend.chat /dev/ttyACM0 --voice en_US-amy-medium  # another Piper voice

The robot sleeps (sleepy face) until you say "Hey Mochi". Then it answers
everything until you say "Bye bye Mochi", or nobody speaks for 2 minutes.
While it sleeps nothing is sent to the AI, so nothing costs anything.

Needs OPENAI_API_KEY in .env at the repository root (see backend/config.py).
Close robot_cli.py and idf.py monitor first; only one program can hold the port.
"""

import argparse
import logging
import time

from backend import config
from backend.ai.conversation import Conversation
from backend.ai.openai_client import Brain
from backend.ai.personality import build_instructions
from backend.ai.wake_word import DEFAULT_IDLE_TIMEOUT_S, DEFAULT_NAME, Session
from backend.audio.stt import SpeechToText
from backend.audio.tts import DEFAULT_VOICE, TextToSpeech
from backend.communication import Robot


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port", help="serial device, e.g. /dev/ttyACM0")
    ap.add_argument("--model", help=f"OpenAI model (default {config.DEFAULT_OPENAI_MODEL}, "
                                    "or AIBOT_OPENAI_MODEL in .env)")
    ap.add_argument("--stt-model", help=f"faster-whisper model (default {config.DEFAULT_STT_MODEL})")
    ap.add_argument("--voice", help=f"Piper voice (default {DEFAULT_VOICE}, or AIBOT_VOICE in .env); "
                                    "downloaded on first use")
    ap.add_argument("--always-answer", action="store_true", help="never sleep: answer everything")
    ap.add_argument("--logs", action="store_true", help="show firmware log lines")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.logs else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    model = args.model or config.setting("AIBOT_OPENAI_MODEL", config.DEFAULT_OPENAI_MODEL)
    stt_model = args.stt_model or config.setting("AIBOT_STT_MODEL", config.DEFAULT_STT_MODEL)
    voice = args.voice or config.setting("AIBOT_VOICE", DEFAULT_VOICE)
    name = config.setting("AIBOT_NAME", DEFAULT_NAME)
    reasoning = (config.setting("AIBOT_OPENAI_REASONING", config.DEFAULT_OPENAI_REASONING)
                 if model.startswith("gpt-5") else None)
    brain = Brain(model, api_key=config.openai_key(), reasoning_effort=reasoning,
                  instructions=build_instructions(model, stt_model, voice, name))

    t0 = time.monotonic()
    print(f"loading speech recognition ({stt_model}) and voice ({voice}) ...", end=" ", flush=True)
    stt = SpeechToText(stt_model, hotwords=name)
    tts = TextToSpeech(voice)
    print(f"{time.monotonic() - t0:.1f} s. AI model: {model}")

    session = None
    if not args.always_answer:
        session = Session(name, float(config.setting("AIBOT_IDLE_TIMEOUT_S", str(DEFAULT_IDLE_TIMEOUT_S))))
        print(f'asleep: say "Hey {name}" to wake it, "Bye bye {name}" to end '
              f"(it also naps after {session.idle_timeout_s:g} s of silence)")

    with Robot.open(args.port) as robot:
        try:
            Conversation(robot, stt, brain, tts, session=session).run()
        except KeyboardInterrupt:
            print("\nbye")


if __name__ == "__main__":
    main()
