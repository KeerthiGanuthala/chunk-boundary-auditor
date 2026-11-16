"""Properties of the deterministic tokenizer."""

import pytest

from chunkaudit import tokens as tk


def test_a_short_word_is_one_token():
    assert tk.count("unit") == 1


def test_punctuation_is_its_own_token():
    assert tk.count("unit.") == 2


def test_whitespace_is_never_a_token():
    assert tk.count("   \n\t  ") == 0


def test_a_long_word_is_split_into_four_character_pieces():
    assert tk.count("commissioned") == 3


def test_a_long_number_is_not_split_because_only_alphabetic_words_are_pieced():
    assert tk.count("1234567890") == 1


def test_offsets_cover_exactly_the_non_whitespace_characters():
    text = "Its rated output is 412 MW."
    toks = tk.tokenize(text)
    covered = "".join(text[t.start : t.end] for t in toks)
    assert covered == text.replace(" ", "")


def test_offsets_are_strictly_increasing():
    toks = tk.tokenize("The Varlen K2 unit was commissioned at the Ostbro site in 1987.")
    for a, b in zip(toks, toks[1:], strict=False):
        assert a.end <= b.start


def test_piece_boundaries_lie_inside_the_word():
    text = "commissioned"
    toks = tk.tokenize(text)
    assert [text[t.start : t.end] for t in toks] == ["comm", "issi", "oned"]


@pytest.mark.parametrize("text", ["", "a", "a b", "a.b", "a\nb", "a  b"])
def test_count_equals_length_of_tokenize(text):
    assert tk.count(text) == len(tk.tokenize(text))


def test_the_same_text_counts_the_same_twice():
    text = "Spare parts for the assembly are held at the Quanex depot."
    assert tk.count(text) == tk.count(text)


def test_counting_is_additive_across_a_space_join():
    a, b = "Its rated output is 412 MW.", "Operators replaced the inlet filters."
    assert tk.count(a + " " + b) == tk.count(a) + tk.count(b)


def test_a_table_separator_bar_is_one_token():
    assert tk.count("Unit | mass") == 3
