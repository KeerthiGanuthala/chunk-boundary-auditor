"""Containment: the three outcomes and the rules that decide them."""

import pytest

from chunkaudit.audit import FactOutcome, audit, audit_fact, normalize
from chunkaudit.chunkers import Chunk
from chunkaudit.corpus import FACT_KINDS, Fact

FIRST = "The Varlen K2 unit was commissioned at the Ostbro site in 1987."
SECOND = "Its rated output is 412 MW."
FACT = Fact("D01-cross_sentence-0", "D01", "cross_sentence", "q", "412 MW", (FIRST, SECOND))
SINGLE = Fact(
    "D02-single-0", "D02", "single", "q", "1", ("The Ostsen K3 unit has a mass of 1 kg.",)
)


def _chunks(*texts):
    return [Chunk(i, t, 1) for i, t in enumerate(texts)]


def test_normalize_collapses_whitespace_and_strips():
    assert normalize("  a\n b\t\tc ") == "a b c"


def test_a_fact_whose_spans_share_a_chunk_is_contained():
    out = audit_fact(FACT, FIRST + " " + SECOND, _chunks(FIRST + " " + SECOND))
    assert out.outcome == "contained"
    assert out.containing_chunks == (0,)


def test_a_fact_whose_spans_fall_in_different_chunks_is_orphaned():
    out = audit_fact(FACT, FIRST + " " + SECOND, _chunks(FIRST, SECOND))
    assert out.outcome == "orphaned"
    assert out.containing_chunks == ()


def test_a_fact_with_a_span_missing_from_the_extraction_is_broken_not_orphaned():
    broken_first = FIRST.replace("Ostbro site", "Ostbro Noise surveys site")
    out = audit_fact(FACT, broken_first + " " + SECOND, _chunks(broken_first, SECOND))
    assert out.outcome == "broken"
    assert out.missing_spans == (FIRST,)


def test_broken_takes_precedence_over_orphaned():
    out = audit_fact(FACT, SECOND, _chunks(SECOND))
    assert out.outcome == "broken"


def test_span_matching_ignores_line_wrapping():
    wrapped = FIRST.replace("at the", "at\nthe")
    out = audit_fact(FACT, wrapped + "\n" + SECOND, _chunks(wrapped + "\n" + SECOND))
    assert out.outcome == "contained"


def test_span_order_inside_a_chunk_does_not_matter():
    out = audit_fact(FACT, SECOND + " " + FIRST, _chunks(SECOND + " " + FIRST))
    assert out.outcome == "contained"


def test_a_footer_between_the_spans_does_not_break_containment():
    text = FIRST + "\nAsset register D01 | page 1 of 3\n" + SECOND
    assert audit_fact(FACT, text, _chunks(text)).outcome == "contained"


def test_every_chunk_holding_all_spans_is_reported():
    both = FIRST + " " + SECOND
    out = audit_fact(FACT, both, _chunks(both, "filler", both))
    assert out.containing_chunks == (0, 2)


def test_a_single_span_fact_only_needs_itself():
    out = audit_fact(SINGLE, SINGLE.spans[0], _chunks(SINGLE.spans[0]))
    assert out.outcome == "contained"


def test_a_partial_span_does_not_count():
    out = audit_fact(SINGLE, SINGLE.spans[0], _chunks(SINGLE.spans[0][:-6]))
    assert out.outcome == "orphaned"


def test_a_fact_with_no_chunks_at_all_is_orphaned():
    assert audit_fact(FACT, FIRST + " " + SECOND, []).outcome == "orphaned"


def _result(outcomes_by_doc):
    facts, extracted, chunks = [], {}, {}
    for doc_id, (text, chunk_texts, fact_list) in outcomes_by_doc.items():
        facts.extend(fact_list)
        extracted[doc_id] = text
        chunks[doc_id] = _chunks(*chunk_texts)
    return audit(
        facts, extracted, chunks, strategy="fixed", extraction_mode="blocks", size=8, overlap=0
    )


def test_audit_counts_each_outcome_once():
    r = _result(
        {
            "D01": (FIRST + " " + SECOND, [FIRST + " " + SECOND], [FACT]),
            "D02": (
                FIRST + " " + SECOND,
                [FIRST, SECOND],
                [Fact("D02-cross_sentence-0", "D02", "cross_sentence", "q", "a", (FIRST, SECOND))],
            ),
            "D03": (
                SECOND,
                [SECOND],
                [Fact("D03-cp-0", "D03", "cross_page", "q", "a", (FIRST, SECOND))],
            ),
        }
    )
    assert (r.contained, r.orphaned, r.broken, r.total) == (1, 1, 1, 3)


def test_audit_shares_divide_by_the_total():
    r = _result({"D01": (FIRST + " " + SECOND, [FIRST, SECOND], [FACT])})
    assert r.share("orphaned") == 1.0
    assert r.share("contained") == 0.0


def test_audit_share_of_an_empty_audit_is_zero():
    r = _result({})
    assert r.share("orphaned") == 0.0 and r.total == 0


def test_audit_breaks_down_by_fact_kind():
    r = _result(
        {
            "D01": (FIRST + " " + SECOND, [FIRST, SECOND], [FACT]),
            "D02": (SINGLE.spans[0], [SINGLE.spans[0]], [SINGLE]),
        }
    )
    assert r.by_kind["cross_sentence"]["orphaned"] == 1
    assert r.by_kind["single"]["contained"] == 1
    assert set(r.by_kind) == set(FACT_KINDS)


def test_audit_records_chunk_statistics():
    r = _result({"D01": (FIRST + " " + SECOND, [FIRST, SECOND, "x"], [FACT])})
    assert r.chunk_count == 3
    assert r.mean_chunk_tokens == 1.0
    assert r.max_chunk_tokens == 1


def test_audit_of_a_fact_whose_document_was_not_extracted_is_an_error():
    with pytest.raises(KeyError, match="D01"):
        audit([FACT], {}, {}, strategy="fixed", extraction_mode="blocks", size=8, overlap=0)


def test_to_dict_lists_lost_fact_ids_sorted():
    r = _result(
        {
            "D02": (FIRST + " " + SECOND, [FIRST, SECOND], [FACT]),
            "D01": (
                SECOND,
                [SECOND],
                [Fact("D01-cp-0", "D01", "cross_page", "q", "a", (FIRST, SECOND))],
            ),
        }
    )
    assert r.to_dict()["lost_fact_ids"] == ["D01-cp-0", "D01-cross_sentence-0"]


def test_to_dict_carries_the_run_parameters():
    r = _result({"D01": (FIRST + " " + SECOND, [FIRST + " " + SECOND], [FACT])})
    d = r.to_dict()
    assert (d["strategy"], d["extraction_mode"], d["size"], d["overlap"]) == (
        "fixed",
        "blocks",
        8,
        0,
    )
    assert d["facts_total"] == 1 and d["contained"] == 1


def test_fact_outcome_is_immutable():
    out = FactOutcome(FACT, "contained")
    with pytest.raises(AttributeError):
        out.outcome = "orphaned"  # type: ignore[misc]
