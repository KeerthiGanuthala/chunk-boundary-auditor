"""Rendering: determinism, layouts, and the two bugs the first fixture had."""

import hashlib

import pymupdf
import pytest

from chunkaudit import pdfgen
from chunkaudit.corpus import Document, Page


def _render_bytes(doc):
    pdf = pdfgen.render_document(doc)
    data = pdf.tobytes(garbage=0, deflate=True, no_new_id=True)
    pdf.close()
    return data


def test_rendering_the_same_document_twice_gives_identical_bytes(small_corpus):
    d = small_corpus.documents[0]
    assert hashlib.sha256(_render_bytes(d)).digest() == hashlib.sha256(_render_bytes(d)).digest()


def test_page_count_matches_the_corpus(small_corpus):
    for d in small_corpus.documents:
        pdf = pdfgen.render_document(d)
        assert pdf.page_count == len(d.pages)
        pdf.close()


def test_metadata_dates_are_pinned_so_the_bytes_do_not_depend_on_the_clock(small_corpus):
    pdf = pdfgen.render_document(small_corpus.documents[0])
    assert pdf.metadata["creationDate"] == pdf.metadata["modDate"] == "D:20251116000000Z"
    pdf.close()


def test_the_title_is_on_the_first_page_only(small_corpus):
    d = small_corpus.documents[0]
    pdf = pdfgen.render_document(d)
    assert d.title in pdf[0].get_text()
    body_second = pdf[1].get_text().replace(f"{d.title} | page 2", "")
    assert d.title not in body_second
    pdf.close()


def test_every_page_carries_a_footer_with_its_number(small_corpus):
    d = small_corpus.documents[0]
    pdf = pdfgen.render_document(d)
    for n, page in enumerate(pdf, start=1):
        assert f"page {n} of {len(d.pages)}" in page.get_text()
    pdf.close()


def test_single_column_layout_has_one_text_column():
    rects = pdfgen._rects("single")
    assert len(rects) == 1
    assert rects[0].width > 400


def test_two_column_layout_has_two_non_overlapping_columns():
    left, right = pdfgen._rects("two_column")
    assert left.x1 < right.x0
    assert abs(left.width - right.width) < 0.01


def test_two_column_pages_put_text_in_both_columns(small_corpus):
    """Pinned bug: the first fixture's two-column pages had an empty right column.

    The left column was filled until it overflowed and it never did, because a page's worth of
    paragraphs fits in one column. Every "two-column" document was really single-column text,
    so the sorted-mode interleaving the extraction experiment exists to measure never happened.
    The split now balances the column heights instead of filling the left one first.
    """
    two_col = [d for d in small_corpus.documents if d.layout != "single"]
    assert two_col
    for d in two_col:
        pdf = pdfgen.render_document(d)
        for page in pdf:
            xs = {round(b[0]) for b in page.get_text("blocks") if b[6] == 0}
            left, _ = pdfgen._rects("two_column")
            assert any(x > left.x1 for x in xs), (d.doc_id, page.number)
        pdf.close()


def test_reversed_layout_writes_the_right_column_first_in_the_content_stream(small_corpus):
    """Raw extraction order is the content stream order, which is the whole point of the layout."""
    d = next(d for d in small_corpus.documents if d.layout == "two_column_reversed")
    pdf = pdfgen.render_document(d)
    page = pdf[0]
    body_blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[1] > pdfgen.TOP - 1]
    body_blocks = [b for b in body_blocks if b[1] < pdfgen.BOTTOM]
    left_edge = pdfgen._rects("two_column")[0].x1
    first_body_x = body_blocks[0][0]
    assert first_body_x > left_edge
    pdf.close()


def test_normal_two_column_layout_writes_the_left_column_first(small_corpus):
    d = next(d for d in small_corpus.documents if d.layout == "two_column")
    pdf = pdfgen.render_document(d)
    page = pdf[0]
    body_blocks = [
        b for b in page.get_text("blocks") if b[6] == 0 and pdfgen.TOP - 1 < b[1] < pdfgen.BOTTOM
    ]
    assert body_blocks[0][0] < pdfgen._rects("two_column")[0].x1
    pdf.close()


def test_a_page_that_cannot_fit_its_paragraphs_raises_a_layout_error():
    """Pinned bug: the committed seed first produced a page one paragraph too tall.

    The renderer silently dropped the overflow, and a dropped paragraph with a planted fact in it
    would have been counted as lost to extraction. It now raises, naming the page, so the corpus
    parameters get fixed instead of the number.
    """
    huge = " ".join([f"Filler sentence number {i} for the overflow test." for i in range(400)])
    doc = Document(
        doc_id="OVR",
        title="overflow",
        layout="single",
        pages=[Page([huge, huge]), Page(["short"])],
        facts=[],
    )
    with pytest.raises(pdfgen.LayoutError, match="OVR page 1"):
        pdfgen.render_document(doc)


def test_a_two_column_page_that_cannot_fit_its_paragraphs_raises():
    huge = " ".join([f"Filler sentence number {i} for the overflow test." for i in range(300)])
    doc = Document(
        doc_id="OVR2",
        title="overflow",
        layout="two_column",
        pages=[Page([huge, huge, huge]), Page(["short"])],
        facts=[],
    )
    with pytest.raises(pdfgen.LayoutError):
        pdfgen.render_document(doc)


def test_a_paragraph_taller_than_a_column_is_refused_when_measuring():
    huge = " ".join([f"Filler sentence number {i} for the overflow test." for i in range(900)])
    with pytest.raises(pdfgen.LayoutError, match="taller than a column"):
        pdfgen._paragraph_heights("two_column", [huge])


def test_measure_split_keeps_at_least_one_paragraph_on_each_side():
    paras = ["Short paragraph one.", "Short paragraph two."]
    assert pdfgen._measure_split("two_column", paras) == 1


def test_measure_split_of_a_single_paragraph_puts_it_on_the_left():
    assert pdfgen._measure_split("two_column", ["Only one paragraph."]) == 1


def test_write_corpus_names_files_by_document_id(small_corpus, tmp_path):
    paths = pdfgen.write_corpus(small_corpus, tmp_path)
    assert [p.name for p in paths] == [f"{d.doc_id}.pdf" for d in small_corpus.documents]
    for p in paths:
        pdf = pymupdf.open(p)
        assert pdf.page_count >= 3
        pdf.close()
