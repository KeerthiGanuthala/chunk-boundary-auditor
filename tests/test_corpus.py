"""Properties of the seeded corpus: determinism, fact placement, and the spans facts require."""

import random
from collections import Counter

import pytest

from chunkaudit.corpus import (
    FACT_KINDS,
    _Namer,
    corpus_from_policy,
    generate_corpus,
    generate_document,
)


def _gen(seed=7, **over):
    params = dict(
        documents=3,
        pages_min=3,
        pages_max=4,
        two_column_share=0.5,
        reversed_stream_share=0.5,
        facts_single=2,
        facts_cross_sentence=2,
        facts_cross_paragraph=2,
        facts_cross_page=1,
        facts_table=1,
    )
    params.update(over)
    return generate_corpus(seed, **params)


def test_the_same_seed_gives_the_same_corpus():
    a, b = _gen(), _gen()
    assert [d.text() for d in a.documents] == [d.text() for d in b.documents]
    assert a.facts == b.facts


def test_a_different_seed_gives_a_different_corpus():
    assert _gen(1).documents[0].text() != _gen(2).documents[0].text()


def test_document_count_matches_the_request():
    assert len(_gen(documents=5).documents) == 5


def test_page_counts_stay_inside_the_requested_range():
    for d in _gen(documents=12, pages_min=2, pages_max=5).documents:
        assert 2 <= len(d.pages) <= 5


def test_every_fact_kind_is_planted_the_requested_number_of_times_per_document():
    for d in _gen().documents:
        kinds = Counter(f.kind for f in d.facts)
        assert kinds == {
            "single": 2,
            "cross_sentence": 2,
            "cross_paragraph": 2,
            "cross_page": 1,
            "table": 1,
        }


def test_fact_ids_are_unique_across_the_corpus():
    ids = [f.fact_id for f in _gen(documents=6).facts]
    assert len(ids) == len(set(ids))


def test_entity_names_are_unique_across_the_corpus():
    names = [f.question.split("of the ")[1].rsplit(" unit", 1)[0] for f in _gen(documents=6).facts]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("kind", FACT_KINDS)
def test_every_span_of_every_fact_appears_in_its_document_text(kind):
    corpus = _gen(documents=6)
    for d in corpus.documents:
        text = d.text()
        for f in d.facts:
            if f.kind == kind:
                for span in f.spans:
                    assert span in text, (f.fact_id, span)


def test_single_facts_have_one_span_and_pair_facts_have_two():
    for f in _gen().facts:
        expected = 1 if f.kind == "single" else 2
        assert len(f.spans) == expected


def test_the_answer_appears_in_the_last_span_of_the_fact():
    for f in _gen().facts:
        assert f.answer in f.spans[-1]


def test_the_entity_is_named_only_in_the_first_span_of_a_pair_fact():
    """The second sentence starts with a pronoun, so alone it names nothing."""
    for f in _gen().facts:
        if f.kind in ("cross_sentence", "cross_paragraph", "cross_page"):
            assert f.spans[1].startswith("Its ")


def test_a_cross_page_fact_ends_one_page_and_starts_the_next():
    for d in _gen(documents=6).documents:
        for f in d.facts:
            if f.kind == "cross_page":
                first, second = f.spans
                page_of_first = next(
                    i for i, p in enumerate(d.pages) if any(first in q for q in p.paragraphs)
                )
                assert d.pages[page_of_first].paragraphs[-1].endswith(first)
                assert d.pages[page_of_first + 1].paragraphs[0].startswith(second)


def test_a_cross_paragraph_fact_straddles_adjacent_paragraphs_on_one_page():
    """Pinned bug: a table could be spliced between the two halves of a cross_paragraph fact.

    Tables were inserted at any paragraph index, so one in twelve or so landed in the gap the
    fact straddles, turning a cross-paragraph fact into a cross-table one without the fact's
    kind saying so. The generator now records every glued gap and keeps tables out of it.
    """
    for d in _gen(documents=6).documents:
        for f in d.facts:
            if f.kind == "cross_paragraph":
                first, second = f.spans
                found = False
                for p in d.pages:
                    paras = p.paragraphs
                    for a, b in zip(paras, paras[1:], strict=False):
                        if a.endswith(first) and b.startswith(second):
                            found = True
                assert found, f.fact_id


def test_a_cross_sentence_fact_is_two_adjacent_sentences_in_one_paragraph():
    for d in _gen(documents=6).documents:
        for f in d.facts:
            if f.kind == "cross_sentence":
                joined = f.spans[0] + " " + f.spans[1]
                assert any(joined in q for p in d.pages for q in p.paragraphs), f.fact_id


def test_a_table_fact_requires_the_header_line_and_the_row_line():
    for f in _gen().facts:
        if f.kind == "table":
            header, row = f.spans
            assert header.startswith("Unit | ")
            assert row.count(" | ") == header.count(" | ")


def test_table_paragraphs_never_start_a_page_so_cross_page_spans_stay_first():
    for d in _gen(documents=8).documents:
        for p in d.pages:
            assert not p.paragraphs[0].startswith("Unit | ")


def test_layout_mix_follows_the_shares():
    corpus = _gen(documents=8, two_column_share=0.5, reversed_stream_share=0.5)
    layouts = Counter(d.layout for d in corpus.documents)
    assert layouts == {"single": 4, "two_column": 2, "two_column_reversed": 2}


def test_a_zero_two_column_share_gives_only_single_column_documents():
    corpus = _gen(documents=5, two_column_share=0.0)
    assert {d.layout for d in corpus.documents} == {"single"}


def test_filler_sentences_carry_numbers_so_a_fact_cannot_be_found_by_looking_for_digits():
    corpus = _gen()
    text = corpus.documents[0].text()
    fact_sentences = {s for f in corpus.facts for s in f.spans}
    numeric_non_fact = [
        s
        for p in corpus.documents[0].pages
        for q in p.paragraphs
        for s in q.split(". ")
        if any(c.isdigit() for c in s) and s not in fact_sentences and "Unit |" not in q
    ]
    assert numeric_non_fact, text[:200]


def test_more_cross_page_facts_than_boundaries_is_refused_at_generation():
    rng = random.Random(1)
    with pytest.raises(ValueError, match="cross-page"):
        generate_document(
            rng,
            _Namer(rng),
            "X",
            pages=2,
            layout="single",
            facts_single=0,
            facts_cross_sentence=0,
            facts_cross_paragraph=0,
            facts_cross_page=2,
            facts_table=0,
        )


def test_corpus_from_policy_matches_generate_corpus(small_policy):
    fx = small_policy.fixture
    direct = generate_corpus(
        fx.seed,
        documents=fx.documents,
        pages_min=fx.pages_min,
        pages_max=fx.pages_max,
        two_column_share=fx.two_column_share,
        reversed_stream_share=fx.reversed_stream_share,
        facts_single=fx.facts_single,
        facts_cross_sentence=fx.facts_cross_sentence,
        facts_cross_paragraph=fx.facts_cross_paragraph,
        facts_cross_page=fx.facts_cross_page,
        facts_table=fx.facts_table,
    )
    assert corpus_from_policy(small_policy).facts == direct.facts


def test_document_text_joins_pages_and_paragraphs_with_blank_lines(small_corpus):
    d = small_corpus.documents[0]
    assert d.text().count("\n\n") == sum(len(p.paragraphs) for p in d.pages) - 1


def test_the_committed_policy_plants_396_facts(default_policy):
    assert len(corpus_from_policy(default_policy).facts) == 396
