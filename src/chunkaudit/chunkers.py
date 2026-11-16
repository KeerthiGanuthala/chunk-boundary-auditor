"""The five chunking strategies under audit.

They are reimplemented here in a few dozen lines each rather than imported from a framework, for
one reason: the audit must be able to say exactly where a boundary fell and why, and a framework
splitter changes its boundary rules between versions. ADR-002 records the decision. The shapes
are the ones every RAG pipeline reaches for:

    fixed            a window of N tokens, optionally overlapping the previous window
    recursive        split on paragraph, then line, then sentence, then word, merging pieces back
                     up to N tokens (the shape of LangChain's RecursiveCharacterTextSplitter)
    sentence_window  whole sentences packed up to N tokens, never cutting inside a sentence
    page_aware       fixed windows that never cross a page boundary
    paragraph        whole paragraphs packed up to N tokens, a long paragraph split by fixed windows

All strategies take the extracted pages, so a page boundary is visible to the ones that want it and
invisible to the ones that do not.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from . import tokens as tk

PAGE_JOIN = "\n\n"
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n")
_RECURSIVE_SEPARATORS = ("\n\n", "\n", ". ", " ")


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    tokens: int


def _window_text(text: str, toks: list[tk.Token], start: int, end: int) -> str:
    return text[toks[start].start : toks[end - 1].end]


def fixed(pages: Sequence[str], size: int, overlap: int = 0) -> list[Chunk]:
    text = PAGE_JOIN.join(pages)
    return _fixed_on_text(text, size, overlap)


def _fixed_on_text(text: str, size: int, overlap: int, start_index: int = 0) -> list[Chunk]:
    if size < 1 or not 0 <= overlap < size:
        raise ValueError("fixed chunking needs size >= 1 and 0 <= overlap < size")
    toks = tk.tokenize(text)
    out: list[Chunk] = []
    step = size - overlap
    i = 0
    while i < len(toks):
        j = min(i + size, len(toks))
        out.append(Chunk(start_index + len(out), _window_text(text, toks, i, j), j - i))
        if j == len(toks):
            break
        i += step
    return out


def page_aware(pages: Sequence[str], size: int, overlap: int = 0) -> list[Chunk]:
    out: list[Chunk] = []
    for page in pages:
        if page.strip():
            out.extend(_fixed_on_text(page, size, overlap, start_index=len(out)))
    return out


def _pack(units: list[str], size: int, overlap_units: int, joiner: str) -> list[Chunk]:
    """Pack whole units into chunks of at most ``size`` tokens; a unit larger than size is split.

    ``overlap_units`` trailing units of a chunk are carried into the next one, unless the carry
    plus the next unit would already exceed ``size``, in which case the carry is dropped so the
    packer always makes progress.
    """
    out: list[Chunk] = []
    current: list[str] = []

    def emit(parts: list[str]) -> None:
        text = joiner.join(parts)
        out.append(Chunk(len(out), text, tk.count(text)))

    def fits(parts: list[str]) -> bool:
        return tk.count(joiner.join(parts)) <= size

    for unit in units:
        if tk.count(unit) > size:
            if current:
                emit(current)
                current = []
            for piece in _fixed_on_text(unit, size, 0):
                out.append(Chunk(len(out), piece.text, piece.tokens))
            continue
        if current and not fits([*current, unit]):
            emit(current)
            carry = current[len(current) - overlap_units :] if overlap_units > 0 else []
            current = carry if carry and fits([*carry, unit]) else []
        current.append(unit)
    if current:
        emit(current)
    return out


def sentence_window(pages: Sequence[str], size: int, overlap_sentences: int = 0) -> list[Chunk]:
    text = PAGE_JOIN.join(pages)
    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s and s.strip()]
    return _pack(sentences, size, overlap_sentences, " ")


def paragraph(pages: Sequence[str], size: int, overlap: int = 0) -> list[Chunk]:
    text = PAGE_JOIN.join(pages)
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return _pack(paras, size, 0, "\n\n")


def _split_recursive(text: str, size: int, separators: tuple[str, ...]) -> list[str]:
    """Return pieces of at most ``size`` tokens, split on the coarsest separator that works."""
    if tk.count(text) <= size:
        return [text]
    if not separators:
        return [c.text for c in _fixed_on_text(text, size, 0)]
    sep, rest = separators[0], separators[1:]
    parts = [p for p in text.split(sep) if p.strip()]
    if len(parts) <= 1:
        return _split_recursive(text, size, rest)
    out: list[str] = []
    for part in parts:
        piece = part + (sep.rstrip() if sep == ". " else "")
        if tk.count(piece) <= size:
            out.append(piece)
        else:
            out.extend(_split_recursive(piece, size, rest))
    return out


def recursive(pages: Sequence[str], size: int, overlap: int = 0) -> list[Chunk]:
    """Split with the separator hierarchy, then merge adjacent pieces back up to ``size`` tokens.

    Overlap is applied the way the framework splitter does it: the trailing pieces of a chunk are
    carried into the next one while they fit within ``overlap`` tokens.
    """
    text = PAGE_JOIN.join(pages)
    pieces = _split_recursive(text, size, _RECURSIVE_SEPARATORS)
    out: list[Chunk] = []
    current: list[str] = []
    for piece in pieces:
        candidate = " ".join([*current, piece])
        if current and tk.count(candidate) > size:
            merged = " ".join(current)
            out.append(Chunk(len(out), merged, tk.count(merged)))
            carry: list[str] = []
            if overlap:
                budget = 0
                for prev in reversed(current):
                    n = tk.count(prev)
                    if budget + n > overlap:
                        break
                    carry.insert(0, prev)
                    budget += n
            current = [*carry, piece]
        else:
            current.append(piece)
    if current:
        merged = " ".join(current)
        out.append(Chunk(len(out), merged, tk.count(merged)))
    return out


Strategy = Callable[[Sequence[str], int, int], list[Chunk]]

STRATEGIES: dict[str, Strategy] = {
    "fixed": fixed,
    "recursive": recursive,
    "sentence_window": sentence_window,
    "page_aware": page_aware,
    "paragraph": paragraph,
}


def chunk(strategy: str, pages: Sequence[str], size: int, overlap: int = 0) -> list[Chunk]:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}, expected one of {tuple(STRATEGIES)}")
    return STRATEGIES[strategy](pages, size, overlap)
