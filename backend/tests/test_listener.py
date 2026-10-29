import numpy as np

from backend.audio.listener import START, Listener

RATE, BLOCK = 16000, 320
rng = np.random.default_rng(0)


def noise(seconds, dbfs=-45):
    return (rng.standard_normal(int(seconds * RATE)) * 32768 * 10 ** (dbfs / 20)).astype(np.int16)


def speech(seconds, dbfs=-20):
    """Voice-like: a 150 Hz tone with a 4 Hz syllable rhythm, over the room noise."""
    t = np.arange(int(seconds * RATE)) / RATE
    env = 0.6 + 0.4 * np.sin(2 * np.pi * 4 * t)
    tone = np.sin(2 * np.pi * 150 * t) * env * 32768 * 10 ** (dbfs / 20) * np.sqrt(2)
    return (tone + noise(seconds)).clip(-32768, 32767).astype(np.int16)


def run(audio):
    listener = Listener()
    events = []
    for i in range(0, len(audio) - BLOCK + 1, BLOCK):
        ev = listener.feed(audio[i:i + BLOCK])
        if ev is not None:
            events.append((round(i / RATE, 2), ev))
    return listener, events


def test_one_utterance():
    _, events = run(np.concatenate([noise(1.5), speech(1.0), noise(1.5)]))
    assert len(events) == 2
    (t_start, start), (t_end, utterance) = events
    assert start is START and 1.5 <= t_start <= 1.7
    # pre-roll (0.3 s) + speech (1 s) + the quiet that ends it (0.7 s)
    assert 1.8 <= len(utterance) / RATE <= 2.2
    assert 2.1 <= t_end <= 3.4


def test_quiet_room_and_short_click_are_ignored():
    click = speech(0.04, dbfs=-10)
    _, events = run(np.concatenate([noise(1.5), click, noise(1.5)]))
    assert events == []


def test_two_utterances():
    audio = np.concatenate([noise(1.0), speech(0.8), noise(1.2), speech(0.6), noise(1.0)])
    _, events = run(audio)
    assert [e is START for _, e in events] == [True, False, True, False]


def test_long_speech_is_cut_at_the_maximum():
    listener = Listener(max_speech_s=2)
    audio = np.concatenate([noise(1.0), speech(5.0)])
    ends = [ev for i in range(0, len(audio) - BLOCK + 1, BLOCK)
            if isinstance(ev := listener.feed(audio[i:i + BLOCK]), np.ndarray)]
    assert ends and abs(len(ends[0]) / RATE - 2.0) < 0.05


def test_floor_adapts_to_a_louder_room():
    listener, events = run(np.concatenate([noise(1.0, -60), noise(20, -40)]))
    # A sudden louder room looks like speech starting, but it is never handed
    # over as an utterance, and the new level is learned.
    assert [e for _, e in events if e is not START] == []
    assert len(events) == 1
    assert listener.floor_db > -45
    _, after = run(np.concatenate([noise(1.0, -40), speech(1.0, -10), noise(1.5, -40)]))
    assert [e is START for _, e in after] == [True, False]  # speech still heard over the louder room


def test_reset_drops_speech_in_progress():
    listener = Listener()
    audio = np.concatenate([noise(1.0), speech(0.5)])
    for i in range(0, len(audio) - BLOCK + 1, BLOCK):
        listener.feed(audio[i:i + BLOCK])
    assert listener.in_speech
    listener.reset()
    assert not listener.in_speech
