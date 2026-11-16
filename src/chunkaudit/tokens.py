"""Deterministic token counting with character offsets.

Chunk sizes are quoted in tokens everywhere in the RAG literature, and the usual way to count them
is a BPE tokenizer that downloads its vocabulary on first use. This repository refuses to touch the
network at runtime, so it counts tokens with a fixed rule instead: a word or a punctuation mark is
one token, and an alphabetic word longer than ``PIECE`` characters is split into ``PIECE``-sized
pieces to approximate subword tokenization. ADR-003 states the boundary: sizes in this repository
are comparable with each other and with nothing else.

The same function also returns offsets, so the fixed-window chunker can cut text between tokens
rather than between characters.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PIECE = 4
_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True)
class Token:
    start: int
    end: int


def tokenize(text: str) -> list[Token]:
    """Return token spans as character offsets into ``text``. Whitespace is never a token."""
    out: list[Token] = []
    for m in _TOKEN_RE.finditer(text):
        s, e = m.span()
        if e - s > PIECE and m.group().isalpha():
            for p in range(s, e, PIECE):
                out.append(Token(p, min(p + PIECE, e)))
        else:
            out.append(Token(s, e))
    return out


def count(text: str) -> int:
    return len(tokenize(text))
