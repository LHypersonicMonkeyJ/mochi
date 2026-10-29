from backend.ai.wake_word import ASK, GOODBYE, IGNORE, WAKE, WAKE_AND_ASK, Session


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_asleep_only_the_name_counts():
    s = Session("Mochi")
    assert s.classify("What's for dinner?") == IGNORE
    assert s.classify("You") == IGNORE
    assert s.classify("Bye bye Mochi") == IGNORE  # already asleep
    for text in ["Hey Mochi!", "Hi, Mochi.", "Mochi?", "Okay Mochie", "hello moochi"]:
        assert s.classify(text) == WAKE, text
    assert s.classify("Hey Mochi, what's the weather like?") == WAKE_AND_ASK


def test_awake_everything_is_a_question_until_goodbye():
    s = Session("Mochi")
    s.wake()
    assert s.classify("What's the weather like?") == ASK
    assert s.classify("Mochi, tell me a joke") == ASK
    assert s.classify("Hey Mochi") == WAKE  # a greeting while awake: just say hi
    for text in ["Bye bye Mochi!", "Goodbye, Mochi.", "Good night Mochi", "See you Mochi", "Mochi go to sleep"]:
        assert s.classify(text) == GOODBYE, text
    assert s.classify("How do I say bye in French?") == ASK  # no name, so not a goodbye


def test_nap_after_silence():
    clock = Clock()
    s = Session("Mochi", idle_timeout_s=120, clock=clock)
    assert not s.should_nap()  # asleep already
    s.wake()
    clock.t += 100
    assert not s.should_nap()
    s.touch()
    clock.t += 100
    assert not s.should_nap()  # the countdown restarted
    clock.t += 30
    assert s.should_nap()


def test_other_names_and_aliases():
    s = Session("Sparky", aliases=["sparkey"])
    assert s.names == ("sparky", "sparkey")
    assert s.classify("hey sparkey") == WAKE
    assert s.classify("hey mochi") == IGNORE
