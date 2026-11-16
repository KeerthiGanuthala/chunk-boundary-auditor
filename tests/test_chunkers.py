"""Chunker properties: size bounds, coverage, overlap, and what each strategy promises."""

import pytest

from chunkaudit import tokens as tk
from chunkaudit.audit import normalize
from chunkaudit.chunkers import (
    _SENTENCE_RE,
    PAGE_JOIN,
    STRATEGIES,
    _split_recursive,
    chunk,
    fixed,
    page_aware,
    paragraph,
    recursive,
    sentence_window,
    unwrap,
)

PAGES = [
    "The Varlen K2 unit was commissioned at the Ostbro site in 1987. Its rated output is 412 MW. "
    "Operators replaced the inlet filters during the spring outage.\n\n"
    "Unit | mass | design pressure\nOstsen K3 | 8076 kg | 262 bar\nRilost V8 | 6406 kg | 91 bar",
    "A review in 2024 found the logbooks complete and legible. The schedule slipped by 33 weeks "
    "after a late delivery. Spare parts for the assembly are held at the Quanex depot.",
    "Noise surveys were repeated at 18 points along the fence line. The crew logged 29 hours of "
    "maintenance in the summer window.",
]
FULL = PAGE_JOIN.join(PAGES)


@pytest.mark.parametrize("name", sorted(STRATEGIES))
@pytest.mark.parametrize("size", [16, 32, 64, 512])
def test_no_chunk_exceeds_the_requested_size(name, size):
    for c in chunk(name, PAGES, size):
        assert c.tokens <= size, (name, size, c.text)


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_the_chunks_concatenate_back_to_the_whole_text_when_there_is_no_overlap(name):
    """Fixed windows may cut inside a word (a token splitter does), so compare characters."""
    covered = "".join(normalize(c.text) for c in chunk(name, PAGES, 32)).replace(" ", "")
    assert covered == normalize(FULL).replace(" ", "")


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_chunk_indices_are_consecutive_from_zero(name):
    chunks = chunk(name, PAGES, 32)
    assert [c.index for c in chunks] == list(range(len(chunks)))


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_reported_token_count_matches_the_tokenizer(name):
    for c in chunk(name, PAGES, 32):
        assert c.tokens == tk.count(c.text)


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_a_size_larger_than_the_text_yields_one_chunk_per_unit_at_most(name):
    chunks = chunk(name, PAGES, 10_000)
    assert 1 <= len(chunks) <= len(PAGES)


def test_an_unknown_strategy_is_refused():
    with pytest.raises(ValueError, match="unknown strategy"):
        chunk("semantic", PAGES, 32)


def test_fixed_refuses_a_zero_size():
    with pytest.raises(ValueError):
        fixed(PAGES, 0)


def test_fixed_refuses_overlap_at_or_above_size():
    with pytest.raises(ValueError):
        fixed(PAGES, 16, 16)


def test_fixed_windows_are_exactly_size_tokens_except_the_last():
    chunks = fixed(PAGES, 16)
    assert all(c.tokens == 16 for c in chunks[:-1])
    assert 1 <= chunks[-1].tokens <= 16


def test_fixed_overlap_repeats_the_tail_of_the_previous_window():
    chunks = fixed(PAGES, 16, 4)
    for a, b in zip(chunks, chunks[1:], strict=False):
        tail = tk.tokenize(a.text)[-4:]
        tail_text = normalize(a.text[tail[0].start :])
        assert normalize(b.text).startswith(tail_text.split(" ")[0])


def test_fixed_overlap_increases_the_chunk_count():
    assert len(fixed(PAGES, 16, 8)) > len(fixed(PAGES, 16, 0))


def test_fixed_cuts_between_tokens_never_inside_a_word():
    for c in fixed(PAGES, 7):
        assert not c.text.startswith(" ") and not c.text.endswith(" ")


def test_fixed_ignores_page_boundaries():
    chunks = fixed(PAGES, 1000)
    assert len(chunks) == 1


def test_page_aware_never_crosses_a_page_boundary():
    for c in page_aware(PAGES, 1000):
        assert sum(normalize(c.text) in normalize(p) for p in PAGES) == 1


def test_page_aware_with_a_large_size_returns_each_page_whole():
    assert [normalize(c.text) for c in page_aware(PAGES, 1000)] == [normalize(p) for p in PAGES]


def test_page_aware_skips_blank_pages():
    assert len(page_aware(["", "   ", "one page"], 100)) == 1


def test_page_aware_produces_at_least_one_chunk_per_non_empty_page():
    assert len(page_aware(PAGES, 1000)) == len(PAGES)


def test_sentence_window_never_cuts_inside_a_sentence():
    for c in sentence_window(PAGES, 40):
        assert c.text.rstrip().endswith((".", "bar", "MW")) or c.text.endswith("pressure")


def test_sentence_window_packs_several_sentences_when_they_fit():
    chunks = sentence_window(PAGES, 64)
    assert any(c.text.count(". ") >= 1 for c in chunks)


def test_sentence_window_overlap_repeats_the_last_sentence_when_it_fits():
    chunks = sentence_window(PAGES, 80, overlap_sentences=1)
    assert len(chunks) > 1
    units = [normalize(s) for s in _SENTENCE_RE.split(FULL) if s and s.strip()]
    for a, b in zip(chunks, chunks[1:], strict=False):
        last = next(u for u in units if normalize(a.text).endswith(u))
        assert normalize(b.text).startswith(last)


def test_sentence_window_splits_a_sentence_longer_than_size_with_fixed_windows():
    long_sentence = " ".join(["word"] * 50) + "."
    chunks = sentence_window([long_sentence], 10)
    assert len(chunks) == 6 and all(c.tokens <= 10 for c in chunks)


def test_sentence_window_overlap_is_dropped_when_it_would_not_fit():
    sentences = ["alpha beta gamma delta.", "epsilon zeta eta theta.", "iota kappa lambda mu."]
    chunks = sentence_window(["\n\n".join(sentences)], 9, overlap_sentences=1)
    assert [c.text for c in chunks] == sentences


def test_paragraph_keeps_whole_paragraphs_when_they_fit():
    chunks = paragraph(PAGES, 1000)
    texts = [c.text for c in chunks]
    assert len(texts) == 1
    assert "\n\n" in texts[0]


def test_paragraph_never_merges_across_a_size_boundary():
    for c in paragraph(PAGES, 30):
        assert c.tokens <= 30


def test_paragraph_splits_a_paragraph_larger_than_size():
    big = " ".join(["word"] * 100)
    chunks = paragraph([big], 25)
    assert len(chunks) == 4


def test_recursive_prefers_paragraph_breaks_over_sentence_breaks():
    chunks = recursive(PAGES, 40)
    assert any(c.text.endswith("outage.") for c in chunks)


def test_recursive_pieces_fall_back_to_sentences_when_a_paragraph_is_too_big():
    pieces = _split_recursive(PAGES[1], 20, ("\n\n", "\n", ". ", " "))
    assert len(pieces) == 3
    assert all(p.endswith(".") for p in pieces)


def test_recursive_falls_back_to_words_then_fixed_windows_for_a_single_long_token_run():
    text = " ".join(["w"] * 30)
    pieces = _split_recursive(text, 8, (". ",))
    assert all(tk.count(p) <= 8 for p in pieces)
    assert len(pieces) == 4


def test_recursive_with_no_separator_left_uses_fixed_windows():
    pieces = _split_recursive("abcdefghijklmnopqrstuvwxyz" * 3, 3, ())
    assert all(tk.count(p) <= 3 for p in pieces)


def test_recursive_overlap_carries_trailing_pieces_into_the_next_chunk():
    plain = recursive(PAGES, 40, overlap=0)
    lapped = recursive(PAGES, 40, overlap=20)
    assert len(lapped) >= len(plain)
    shared = 0
    for a, b in zip(lapped, lapped[1:], strict=False):
        last_piece = normalize(a.text).rsplit(". ", 1)[-1]
        if last_piece in normalize(b.text):
            shared += 1
    assert shared >= 1


def test_recursive_does_not_double_the_full_stop_at_a_paragraph_end():
    """Pinned bug: splitting on ". " and re-appending "." gave "outage.." on the last sentence.

    The doubled stop changed the token count of every paragraph-final piece and, worse, made the
    span of any fact ending a paragraph unmatchable, which showed up as a cross_paragraph orphan
    rate for recursive that no other strategy had.
    """
    for c in recursive(PAGES, 40):
        assert ".." not in c.text


def test_recursive_merges_small_pieces_back_up_to_size():
    chunks = recursive(PAGES, 1000)
    assert len(chunks) == 1


def test_strategy_table_lists_the_five_shapes():
    assert set(STRATEGIES) == {"fixed", "recursive", "sentence_window", "page_aware", "paragraph"}


def test_empty_input_gives_no_chunks():
    for name in STRATEGIES:
        assert chunk(name, ["", ""], 32) == []


def test_unwrap_turns_a_lone_newline_into_a_space_and_keeps_blank_lines():
    assert unwrap("a\nb\n\nc") == "a b\n\nc"


def test_sentence_window_keeps_a_sentence_wrapped_across_pdf_lines_whole():
    """Pinned bug: a one-sentence fact was orphaned by the strategy that never cuts a sentence.

    Fact D06-single-1 in the committed fixture sat on a line wrap: "... USD. The" newline
    "Tovqua M3 unit has a nominal voltage of 684 V." The sentence splitter treated every newline
    as a sentence end, so "The" ended one unit and the rest of the sentence started another, and
    the two could land in different chunks. Extracted PDF text wraps every line, so this was not
    a corner case: it was every sentence that happened to wrap at a chunk boundary.
    """
    wrapped = (
        "Its unit price is 54425 USD. The\nTovqua M3 unit has a nominal voltage of 684 V. "
        "Operators\nreplaced the filters."
    )
    chunks = sentence_window([wrapped], 20)
    assert any("The Tovqua M3 unit has a nominal voltage of 684 V." in c.text for c in chunks)


def test_sentence_window_treats_a_table_block_as_one_unit_after_unwrapping():
    """The price of unwrapping: a table's lines are no longer separate units."""
    table = "Unit | mass\nOstsen K3 | 8076 kg\nRilost V8 | 6406 kg"
    chunks = sentence_window([table], 512)
    assert len(chunks) == 1 and "Ostsen K3 | 8076 kg Rilost V8" in chunks[0].text
