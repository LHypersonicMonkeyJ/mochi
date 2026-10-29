import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from backend.ai.conversation import GOODBYE, GREETING, SORRY, Conversation
from backend.ai.openai_client import Brain
from backend.ai.personality import SentenceSplitter, clean_for_speech, split_mood
from backend.ai.wake_word import Session
from backend.communication import Robot
from backend.tests.fake_robot import FakeRobot

RATE, BLOCK = 16000, 320
rng = np.random.default_rng(1)


# --- Stand-ins ---

class FakeSTT:
    def __init__(self, text="hello robot"):
        self.texts = list(text) if isinstance(text, list) else None  # one per utterance, if a list
        self.text = text
        self.heard: list[np.ndarray] = []

    def transcribe(self, audio):
        self.heard.append(audio)
        if self.texts is not None:
            return self.texts.pop(0) if self.texts else ""
        return self.text


class FakeBrain:
    def __init__(self, reply="[happy] Hello there, my friend! It is lovely to meet you today.", fail=False):
        self.reply_text, self.fail, self.asked = reply, fail, []

    def forget(self):
        self.forgotten = getattr(self, "forgotten", 0) + 1

    def reply(self, text):
        self.asked.append(text)
        if self.fail:
            raise RuntimeError("no network")
        for i in range(0, len(self.reply_text), 3):  # stream in small pieces
            yield self.reply_text[i:i + 3]


class FakeTTS:
    def __init__(self):
        self.said: list[str] = []

    def synthesize(self, text):
        self.said.append(text)
        return np.full(int(0.2 * RATE), 1000, dtype=np.int16)


def mic_script(speech_from, speech_to, also_during=None):
    """Mic source for the fake robot: room noise, speech between two block numbers,
    and optionally speech again later (as if the mic heard the robot)."""
    def source(seq):
        loud = speech_from <= seq < speech_to or (also_during and also_during[0] <= seq < also_during[1])
        level = 0.1 if loud else 0.005
        return (rng.standard_normal(BLOCK) * 32768 * level).astype(np.int16)
    return source


def expressions(fake):
    return [line.split()[1] for line in fake.received if line.startswith("expr ")]


@pytest.fixture
def setup():
    fake = FakeRobot()
    robot = Robot(fake, timeout=2.0)
    yield fake, robot
    robot.close()


def run_conversation(conv, max_turns=1, timeout=8.0):
    stop = threading.Event()
    t = threading.Thread(target=conv.run, kwargs={"max_turns": max_turns, "stop": stop})
    t.start()
    t.join(timeout)
    stop.set()
    t.join(2)


# --- Conversation ---

def test_one_turn(setup):
    fake, robot = setup
    fake.mic_source = mic_script(50, 100)  # 1 s of noise, then 1 s of speech
    stt, brain, tts = FakeSTT(), FakeBrain(), FakeTTS()
    logs = []
    conv = Conversation(robot, stt, brain, tts, log=logs.append)
    run_conversation(conv)

    assert len(conv.turns) == 1
    turn = conv.turns[0]
    assert turn.heard == "hello robot" and brain.asked == ["hello robot"]
    assert turn.mood == "happy"
    assert tts.said == ["Hello there, my friend!", "It is lovely to meet you today."]
    assert 0.9 <= turn.speech_s <= 2.2
    assert 0 < turn.first_word_s <= turn.total_s
    # The face: idle, listening, thinking, the reply's mood, back to idle.
    assert expressions(fake) == ["neutral", "listening", "thinking", "happy", "neutral", "neutral"]
    assert any(line.startswith("pcm ") and line not in ("pcm end", "pcm stop") for line in fake.received)
    assert fake.received[-2:] == ["mic off", "expr neutral"]  # shutdown: mic off, face back to idle
    assert any(line.startswith("you: hello robot") for line in logs)


def test_mic_is_ignored_while_the_robot_speaks(setup):
    fake, robot = setup
    # Speech again from block 110 to 400: that is the robot hearing itself while it talks.
    fake.mic_source = mic_script(50, 100, also_during=(110, 400))
    tts = FakeTTS()
    tts.synthesize = lambda text: (tts.said.append(text), np.full(int(2.0 * RATE), 1000, np.int16))[1]
    conv = Conversation(robot, FakeSTT(), FakeBrain("[happy] Hello there, this is a long answer."), tts,
                        log=lambda _m: None)
    run_conversation(conv, max_turns=1)
    assert expressions(fake).count("listening") == 1


def test_no_words_means_no_reply(setup):
    fake, robot = setup
    fake.mic_source = mic_script(50, 80)
    brain = FakeBrain()
    conv = Conversation(robot, FakeSTT(text=""), brain, FakeTTS(), log=lambda _m: None)
    stop = threading.Event()
    t = threading.Thread(target=conv.run, kwargs={"stop": stop})
    t.start()
    time.sleep(3)
    stop.set()
    t.join(3)
    assert brain.asked == [] and conv.turns == []
    assert "listening" in expressions(fake) and "thinking" not in expressions(fake)
    assert expressions(fake)[-1] == "neutral"


def test_ai_failure_apologises(setup):
    fake, robot = setup
    fake.mic_source = mic_script(50, 100)
    tts = FakeTTS()
    conv = Conversation(robot, FakeSTT(), FakeBrain(fail=True), tts, log=lambda _m: None)
    run_conversation(conv)
    assert conv.turns[0].error == "no network"
    assert tts.said == [SORRY]
    assert "sad" in expressions(fake)


def test_reply_without_mood_tag(setup):
    fake, robot = setup
    fake.mic_source = mic_script(50, 100)
    tts = FakeTTS()
    conv = Conversation(robot, FakeSTT(), FakeBrain("Just a plain answer here."), tts, log=lambda _m: None)
    run_conversation(conv)
    assert conv.turns[0].mood is None
    assert tts.said == ["Just a plain answer here."]


def run_for(conv, seconds):
    stop = threading.Event()
    t = threading.Thread(target=conv.run, kwargs={"stop": stop})
    t.start()
    time.sleep(seconds)
    stop.set()
    t.join(3)


def three_utterances():
    """Speech at about 1 s, 4 s and 7 s."""
    def source(seq):
        loud = any(a <= seq < a + 40 for a in (50, 200, 350))
        return (rng.standard_normal(BLOCK) * 32768 * (0.1 if loud else 0.005)).astype(np.int16)
    return source


def test_session_asleep_wake_ask_goodbye(setup):
    fake, robot = setup
    fake.mic_source = three_utterances()
    stt = FakeSTT(["What's for dinner?", "Hey Mochi!", "Tell me a joke"])
    brain, tts = FakeBrain(), FakeTTS()
    session = Session("Mochi")
    conv = Conversation(robot, stt, brain, tts, log=lambda _m: None, session=session)
    run_for(conv, 9.5)
    assert conv.ignored == ["What's for dinner?"]   # asleep: not sent anywhere
    assert brain.asked == ["Tell me a joke"]        # the greeting was answered locally
    assert tts.said[0] == GREETING and brain.forgotten == 1
    assert session.awake
    faces = expressions(fake)
    # Asleep (sleepy, no listening face), woken (happy greeting), then a normal turn.
    assert faces[:3] == ["sleepy", "sleepy", "happy"]  # start, after the ignored sentence, the greeting
    assert faces.index("listening") > faces.index("happy")


def test_goodbye_puts_it_to_sleep_without_the_ai(setup):
    fake, robot = setup
    fake.mic_source = three_utterances()
    stt = FakeSTT(["Hey Mochi, how are you?", "Bye bye Mochi!", "Are you there?"])
    brain, tts = FakeBrain(), FakeTTS()
    session = Session("Mochi")
    conv = Conversation(robot, stt, brain, tts, log=lambda _m: None, session=session)
    run_for(conv, 9.5)
    assert brain.asked == ["Hey Mochi, how are you?"]
    assert GOODBYE.format(name="Mochi") in tts.said
    assert conv.ignored == ["Are you there?"]  # asleep again
    assert not session.awake
    assert expressions(fake)[-2:] == ["sleepy", "neutral"]  # asleep, then neutral when the program ends


def test_naps_after_silence(setup):
    fake, robot = setup
    fake.mic_source = mic_script(50, 90)
    session = Session("Mochi", idle_timeout_s=1.0)
    conv = Conversation(robot, FakeSTT("Hey Mochi"), FakeBrain(), FakeTTS(), log=lambda _m: None,
                        session=session)
    run_for(conv, 6)
    assert not session.awake
    faces = expressions(fake)
    assert faces.count("sleepy") >= 2  # at start, and again after the nap


# --- Reply shaping ---

def test_split_mood():
    assert split_mood("[happy] Hi!") == ("happy", "Hi!")
    assert split_mood("  [Sad]Oh no.") == ("sad", "Oh no.")
    assert split_mood("[thinking] Hmm.") == (None, "Hmm.")  # not a reply mood
    assert split_mood("No tag.") == (None, "No tag.")


def test_sentence_splitter_streams_whole_sentences():
    s = SentenceSplitter()
    out = []
    for piece in ["Hi. I am a", "ibot! How are ", "you today? Fine", "."]:
        out += s.feed(piece)
    out += s.flush()
    assert out == ["Hi. I am aibot!", "How are you today?", "Fine."]


def test_clean_for_speech():
    assert clean_for_speech("**Bold** and `code` # here") == "Bold and code here"


# --- OpenAI client (with a stand-in for the OpenAI library) ---

class FakeResponses:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        n = len(self.calls)
        return iter([SimpleNamespace(type="response.created"),
                     SimpleNamespace(type="response.output_text.delta", delta="[happy] Re"),
                     SimpleNamespace(type="response.output_text.delta", delta=f"ply {n}."),
                     SimpleNamespace(type="response.completed")])


def test_brain_streams_and_keeps_history():
    responses = FakeResponses()
    brain = Brain("test-model", client=SimpleNamespace(responses=responses), history_turns=2)
    assert "".join(brain.reply("one")) == "[happy] Reply 1."
    assert "".join(brain.reply("two")) == "[happy] Reply 2."
    second = responses.calls[1]
    assert second["model"] == "test-model" and second["stream"] is True and "reasoning" not in second
    assert [m["content"] for m in second["input"]] == ["one", "[happy] Reply 1.", "two"]
    for text in ("three", "four"):
        list(brain.reply(text))
    assert [m["content"] for m in brain.history] == ["three", "[happy] Reply 3.", "four", "[happy] Reply 4."]


def test_brain_passes_reasoning_effort():
    responses = FakeResponses()
    brain = Brain("gpt-5-test", client=SimpleNamespace(responses=responses), reasoning_effort="none")
    list(brain.reply("hi"))
    assert responses.calls[0]["reasoning"] == {"effort": "none"}


def test_brain_raises_on_error_event():
    class Failing:
        def create(self, **kwargs):
            return iter([SimpleNamespace(type="error", message="rate limited")])
    brain = Brain("m", client=SimpleNamespace(responses=Failing()))
    with pytest.raises(RuntimeError, match="rate limited"):
        list(brain.reply("hi"))
