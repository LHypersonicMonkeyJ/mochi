from backend.audio.stt import has_words


def test_has_words():
    assert has_words("Hey Mochi!")
    assert has_words("I'm 3")
    assert not has_words("")
    assert not has_words(".")
    assert not has_words(" ... ?! ")
    assert not has_words("42")
