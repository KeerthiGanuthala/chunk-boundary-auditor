"""Text extraction from the fixture PDFs, in the three orders PyMuPDF can hand you.

This module exists because the first place a fact dies is usually here, before any chunker runs,
and a chunking experiment that starts from extracted text cannot see that. Three modes:

    raw     ``page.get_text("text")``: content stream order. Correct when the producer wrote
            the page in reading order, wrong when it did not, and you cannot tell from the page.
    sorted  ``page.get_text("text", sort=True)``: the fix most tutorials recommend for raw. It
            orders lines by position, which on a two-column page interleaves the columns line by
            line and cuts every sentence that wraps.
    blocks  ``page.get_text("blocks")`` clustered into columns by horizontal position, then read
            column by column, top to bottom. The audit recommends this one, and measures why.

The page footer is kept in every mode on purpose. Real extractions carry footers, and a cross-page
fact has to survive one landing between its two sentences.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pymupdf

MODES = ("raw", "sorted", "blocks")
# Blocks whose left edges differ by more than this many points start a new column.
COLUMN_GAP_PT = 40.0


@dataclass(frozen=True)
class Extracted:
    doc_id: str
    mode: str
    pages: tuple[str, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(self.pages)


def _blocks_in_columns(page: pymupdf.Page) -> str:
    blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
    if not blocks:
        return ""
    # Cluster by left edge: sort the distinct x0 values and cut where the gap is wide.
    xs = sorted({round(b[0], 1) for b in blocks})
    cuts: list[float] = []
    for a, b in zip(xs, xs[1:], strict=False):
        if b - a > COLUMN_GAP_PT:
            cuts.append((a + b) / 2)

    def column_of(x: float) -> int:
        return sum(1 for c in cuts if x > c)

    ordered = sorted(blocks, key=lambda b: (column_of(b[0]), round(b[1], 1), round(b[0], 1)))
    return "\n\n".join(b[4].strip() for b in ordered)


def extract_pdf(path: Path, mode: str) -> Extracted:
    if mode not in MODES:
        raise ValueError(f"unknown extraction mode {mode!r}, expected one of {MODES}")
    pdf = pymupdf.open(path)
    pages: list[str] = []
    try:
        for page in pdf:
            if mode == "raw":
                pages.append(page.get_text("text"))
            elif mode == "sorted":
                pages.append(page.get_text("text", sort=True))
            else:
                pages.append(_blocks_in_columns(page))
    finally:
        pdf.close()
    return Extracted(doc_id=path.stem, mode=mode, pages=tuple(pages))


def extract_dir(fixture_dir: Path, mode: str) -> dict[str, Extracted]:
    """Extract every ``*.pdf`` in a directory, keyed by document id (the file stem)."""
    out: dict[str, Extracted] = {}
    for path in sorted(fixture_dir.glob("*.pdf")):
        out[path.stem] = extract_pdf(path, mode)
    return out
