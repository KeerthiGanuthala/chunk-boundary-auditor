"""Extraction: the three orders, and the one that cuts sentences in half."""

import pytest

from chunkaudit.audit import normalize
from chunkaudit.extract import MODES, extract_dir, extract_pdf


def _doc(small_corpus, layout):
    return next(d for d in small_corpus.documents if d.layout == layout)


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_returns_one_string_per_page(small_corpus, small_fixture_dir, mode):
    d = small_corpus.documents[0]
    ex = extract_pdf(small_fixture_dir / f"{d.doc_id}.pdf", mode)
    assert len(ex.pages) == len(d.pages)
    assert ex.doc_id == d.doc_id
    assert ex.mode == mode


def test_an_unknown_mode_is_refused(small_fixture_dir):
    with pytest.raises(ValueError, match="unknown extraction mode"):
        extract_pdf(small_fixture_dir / "D01.pdf", "words")


def test_text_joins_pages_with_a_blank_line(small_fixture_dir):
    ex = extract_pdf(small_fixture_dir / "D01.pdf", "blocks")
    assert ex.text == "\n\n".join(ex.pages)


@pytest.mark.parametrize("mode", MODES)
def test_single_column_documents_survive_every_mode(small_corpus, small_fixture_dir, mode):
    d = _doc(small_corpus, "single")
    full = normalize(extract_pdf(small_fixture_dir / f"{d.doc_id}.pdf", mode).text)
    for f in d.facts:
        for span in f.spans:
            assert normalize(span) in full, (mode, f.fact_id)


def test_blocks_mode_keeps_every_span_of_every_two_column_document(small_corpus, small_fixture_dir):
    for layout in ("two_column", "two_column_reversed"):
        d = _doc(small_corpus, layout)
        full = normalize(extract_pdf(small_fixture_dir / f"{d.doc_id}.pdf", "blocks").text)
        for f in d.facts:
            for span in f.spans:
                assert normalize(span) in full, (layout, f.fact_id)


def test_raw_mode_keeps_every_span_even_when_the_stream_is_reversed(
    small_corpus, small_fixture_dir
):
    """Reversed stream order scrambles paragraph order, not the paragraphs themselves."""
    d = _doc(small_corpus, "two_column_reversed")
    full = normalize(extract_pdf(small_fixture_dir / f"{d.doc_id}.pdf", "raw").text)
    for f in d.facts:
        for span in f.spans:
            assert normalize(span) in full


def test_raw_mode_reads_the_right_column_first_on_a_reversed_document(
    small_corpus, small_fixture_dir
):
    d = _doc(small_corpus, "two_column_reversed")
    raw = extract_pdf(small_fixture_dir / f"{d.doc_id}.pdf", "raw").pages[0]
    blocks = extract_pdf(small_fixture_dir / f"{d.doc_id}.pdf", "blocks").pages[0]
    first_para_raw = normalize(raw.split("\n\n")[0].split("\n", 2)[-1])[:40]
    assert first_para_raw not in normalize(blocks)[: len(first_para_raw) + 80]


def test_sorted_mode_interleaves_columns_and_cuts_sentences(small_corpus, small_fixture_dir):
    """The headline extraction loss: sort=True orders lines by position across both columns."""
    d = _doc(small_corpus, "two_column")
    full = normalize(extract_pdf(small_fixture_dir / f"{d.doc_id}.pdf", "sorted").text)
    lost = [f.fact_id for f in d.facts if any(normalize(s) not in full for s in f.spans)]
    assert lost, "sorted mode should have broken at least one span on a two-column document"


def test_sorted_mode_does_not_lose_spans_on_single_column_documents(
    small_corpus, small_fixture_dir
):
    d = _doc(small_corpus, "single")
    full = normalize(extract_pdf(small_fixture_dir / f"{d.doc_id}.pdf", "sorted").text)
    assert all(normalize(s) in full for f in d.facts for s in f.spans)


def test_blocks_mode_orders_a_two_column_page_left_column_then_right(
    small_corpus, small_fixture_dir
):
    d = _doc(small_corpus, "two_column")
    ex = extract_pdf(small_fixture_dir / f"{d.doc_id}.pdf", "blocks")
    page_text = normalize(ex.pages[0])
    paras = [normalize(p) for p in d.pages[0].paragraphs]
    positions = [page_text.find(p) for p in paras]
    assert all(pos >= 0 for pos in positions)
    assert positions == sorted(positions)


def test_blocks_mode_keeps_the_footer_so_cross_page_facts_face_a_real_gap(small_fixture_dir):
    ex = extract_pdf(small_fixture_dir / "D01.pdf", "blocks")
    assert "page 1 of" in ex.pages[0]


def test_extract_dir_keys_by_document_id(small_corpus, small_fixture_dir):
    out = extract_dir(small_fixture_dir, "blocks")
    assert set(out) == {d.doc_id for d in small_corpus.documents}


def test_blocks_mode_on_an_empty_page_returns_an_empty_string(tmp_path):
    import pymupdf

    pdf = pymupdf.open()
    pdf.new_page()
    path = tmp_path / "empty.pdf"
    pdf.save(path)
    pdf.close()
    assert extract_pdf(path, "blocks").pages == ("",)
