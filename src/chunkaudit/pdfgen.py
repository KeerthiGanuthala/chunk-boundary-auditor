"""Render corpus documents to PDF with PyMuPDF, in the layouts that make extraction hard.

A chunker never sees the document; it sees what a PDF extractor returned. So the fixture has to be
a real PDF, with the two properties that cost real ingestion pipelines facts:

    two columns             text that reads down one column then the next, which position-sorted
                            extraction interleaves line by line
    reversed content stream the right column written into the file before the left one, which
                            makes raw stream order wrong even though the page looks identical

Every paragraph is inserted as its own text box so it becomes its own text block on extraction.
That is also how most document producers behave, and it is what lets the ``blocks`` extraction
mode cluster blocks into columns.

Determinism: the PDF metadata dates are pinned, the file identifier is not regenerated on save, and
PyMuPDF lays out text deterministically, so the same corpus produces byte-identical files. The
fixture manifest records the SHA-256 of every file and ``chunkaudit generate --check`` fails when
they drift.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

from .corpus import Corpus, Document

PAGE_W, PAGE_H = 612.0, 792.0
MARGIN = 54.0
TOP = 80.0
BOTTOM = PAGE_H - 54.0
GUTTER = 24.0
FONT = "helv"
FONT_SIZE = 9.0
PARA_GAP = 6.0
_FIXED_DATE = "D:20251116000000Z"


class LayoutError(RuntimeError):
    """A page's paragraphs do not fit. The corpus parameters, not the renderer, need changing."""


def _rects(layout: str) -> list[pymupdf.Rect]:
    if layout == "single":
        return [pymupdf.Rect(MARGIN, TOP, PAGE_W - MARGIN, BOTTOM)]
    col_w = (PAGE_W - 2 * MARGIN - GUTTER) / 2
    left = pymupdf.Rect(MARGIN, TOP, MARGIN + col_w, BOTTOM)
    right = pymupdf.Rect(MARGIN + col_w + GUTTER, TOP, PAGE_W - MARGIN, BOTTOM)
    return [left, right]


def _fill_column(page: pymupdf.Page, rect: pymupdf.Rect, paragraphs: list[str]) -> int:
    """Insert paragraphs top-down into ``rect``. Returns how many were placed."""
    y = rect.y0
    placed = 0
    for para in paragraphs:
        box = pymupdf.Rect(rect.x0, y, rect.x1, rect.y1)
        if box.height < FONT_SIZE * 2:
            break
        unused = page.insert_textbox(box, para, fontsize=FONT_SIZE, fontname=FONT, align=0)
        if unused < 0:
            break
        y = rect.y1 - unused + PARA_GAP
        placed += 1
    return placed


def _paragraph_heights(layout: str, paragraphs: list[str]) -> list[float]:
    """Height each paragraph takes in a column of this layout, measured on a scratch page."""
    scratch = pymupdf.open()
    page = scratch.new_page(width=PAGE_W, height=PAGE_H)
    rect = _rects(layout)[0]
    heights: list[float] = []
    for para in paragraphs:
        unused = page.insert_textbox(rect, para, fontsize=FONT_SIZE, fontname=FONT, align=0)
        if unused < 0:
            raise LayoutError("a single paragraph is taller than a column")
        heights.append(rect.height - unused + PARA_GAP)
    scratch.close()
    return heights


def _measure_split(layout: str, paragraphs: list[str]) -> int:
    """How many paragraphs go in the left column: the prefix that fills about half the text."""
    heights = _paragraph_heights(layout, paragraphs)
    half = sum(heights) / 2
    running = 0.0
    k = 0
    for h in heights:
        if running >= half:
            break
        running += h
        k += 1
    return max(1, min(k, len(paragraphs) - 1)) if len(paragraphs) > 1 else len(paragraphs)


def render_document(doc: Document) -> pymupdf.Document:
    pdf = pymupdf.open()
    total = len(doc.pages)
    for n, page_src in enumerate(doc.pages, start=1):
        page = pdf.new_page(width=PAGE_W, height=PAGE_H)
        if n == 1:
            page.insert_text((MARGIN, TOP - 28), doc.title, fontsize=14, fontname="hebo")
        rects = _rects(doc.layout)
        paras = page_src.paragraphs
        if doc.layout == "single":
            placed = _fill_column(page, rects[0], paras)
            if placed != len(paras):
                raise LayoutError(
                    f"{doc.doc_id} page {n}: {len(paras) - placed} paragraphs overflow"
                )
        else:
            k = _measure_split(doc.layout, paras)
            left, right = paras[:k], paras[k:]
            if doc.layout == "two_column_reversed":
                placed_r = _fill_column(page, rects[1], right)
                placed_l = _fill_column(page, rects[0], left)
            else:
                placed_l = _fill_column(page, rects[0], left)
                placed_r = _fill_column(page, rects[1], right)
            if placed_l != len(left) or placed_r != len(right):
                raise LayoutError(f"{doc.doc_id} page {n}: two-column overflow")
        footer = f"{doc.title} | page {n} of {total}"
        page.insert_text((MARGIN, PAGE_H - 36), footer, fontsize=8, fontname=FONT)
    pdf.set_metadata(
        {
            "title": doc.title,
            "author": "chunk-boundary-auditor fixture",
            "producer": "chunk-boundary-auditor",
            "creator": "chunk-boundary-auditor",
            "creationDate": _FIXED_DATE,
            "modDate": _FIXED_DATE,
        }
    )
    return pdf


def write_corpus(corpus: Corpus, out_dir: Path) -> list[Path]:
    """Render every document to ``out_dir/<doc_id>.pdf`` and return the paths written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for doc in corpus.documents:
        pdf = render_document(doc)
        path = out_dir / f"{doc.doc_id}.pdf"
        pdf.save(path, garbage=0, deflate=True, no_new_id=True)
        pdf.close()
        paths.append(path)
    return paths
