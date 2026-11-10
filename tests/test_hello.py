import pytest

from wmata_board.hello import HELLO_EMOJI, HELLO_SHOW_S, Hello, hello_age_s, hello_showing, parse_hello


def test_emoji_set_is_fixed_and_ordered():
    assert HELLO_EMOJI == ("💗", "👋", "😘", "🥳", "😴", "☕", "🐀")


def test_parse_a_plain_hello():
    h = parse_hello({"emoji": "💗", "text": "  see   you  soon "}, 1000.5)
    assert h == Hello(id=1000500, emoji="💗", text="see you soon", at=1000.5)


def test_text_is_optional_and_may_be_empty():
    assert parse_hello({"emoji": "👋"}, 5.0).text == ""
    assert parse_hello({"emoji": "👋", "text": None}, 5.0).text == ""
    assert parse_hello({"emoji": "👋", "text": "   "}, 5.0).text == ""


def test_text_length_counts_after_collapsing_whitespace():
    assert parse_hello({"emoji": "☕", "text": "a" * 40}, 5.0).text == "a" * 40
    assert parse_hello({"emoji": "☕", "text": "a  " + "b" * 38}, 5.0).text == "a " + "b" * 38
    with pytest.raises(ValueError, match="40"):
        parse_hello({"emoji": "☕", "text": "a" * 41}, 5.0)


@pytest.mark.parametrize("body, match", [
    ("hi", "object"),
    ([], "object"),
    ({}, "emoji"),
    ({"emoji": "🙂"}, "emoji"),
    ({"emoji": 5}, "emoji"),
    ({"emoji": ["💗"]}, "emoji"),
    ({"emoji": "💗", "text": 5}, "text"),
    ({"emoji": "💗", "text": ["x"]}, "text"),
])
def test_bad_bodies_say_what_is_wrong(body, match):
    with pytest.raises(ValueError, match=match):
        parse_hello(body, 1.0)


def test_ids_are_unique_even_within_a_millisecond():
    first = parse_hello({"emoji": "💗"}, 10.0)
    again = parse_hello({"emoji": "💗"}, 10.0, previous=first)
    earlier = parse_hello({"emoji": "💗"}, 9.0, previous=first)   # a clock that stepped back
    later = parse_hello({"emoji": "💗"}, 11.0, previous=first)
    assert again.id == first.id + 1
    assert earlier.id == first.id + 1
    assert later.id == 11000


def test_a_hello_shows_for_sixty_seconds():
    h = Hello(1, "💗", "", at=100.0)
    assert HELLO_SHOW_S == 60
    assert hello_showing(h, 100.0) and hello_showing(h, 159.9)
    assert not hello_showing(h, 160.0)
    assert not hello_showing(None, 100.0)


def test_age_is_seconds_since_sent_never_negative():
    h = Hello(1, "💗", "", at=100.0)
    assert hello_age_s(h, 112.5) == 12.5
    assert hello_age_s(h, 90.0) == 0.0
