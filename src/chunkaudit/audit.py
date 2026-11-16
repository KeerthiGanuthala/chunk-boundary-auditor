"""The containment audit: for every planted fact, did all of its spans land in one chunk?

This is the module the repository exists for. The question it asks of each fact is deliberately
narrow and deliberately strict:

    A fact is CONTAINED when at least one chunk holds every span the fact needs.
    A fact is ORPHANED when every span survived extraction but no single chunk holds all of them.
    A fact is BROKEN when at least one span cannot be found in the extracted text at all, so no
    chunking strategy could ever have contained it. That loss belongs to extraction, not chunking.

Containment is a necessary condition for retrieval, not a sufficient one: a chunk that holds the
spans can still lose to a better-scoring neighbour. ADR-002 explains why the audit stops at
containment, and why a fact answerable only by stitching two chunks together is counted as lost.

Matching is on whitespace-normalised text, because PDF extraction wraps lines and the chunkers cut
on tokens. Order of spans inside a chunk is not required: a reader can resolve a pronoun that
appears before its antecedent on the same screen, and refusing that would overcount orphans.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from statistics import mean

from .chunkers import Chunk
from .corpus import FACT_KINDS, Fact

OUTCOMES = ("contained", "orphaned", "broken")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WS.sub(" ", text).strip()


@dataclass(frozen=True)
class FactOutcome:
    fact: Fact
    outcome: str
    containing_chunks: tuple[int, ...] = ()
    missing_spans: tuple[str, ...] = ()


@dataclass
class AuditResult:
    strategy: str
    extraction_mode: str
    size: int
    overlap: int
    outcomes: list[FactOutcome]
    chunk_count: int
    mean_chunk_tokens: float
    max_chunk_tokens: int
    by_kind: dict[str, Counter] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    def count(self, outcome: str) -> int:
        return sum(1 for o in self.outcomes if o.outcome == outcome)

    @property
    def orphaned(self) -> int:
        return self.count("orphaned")

    @property
    def broken(self) -> int:
        return self.count("broken")

    @property
    def contained(self) -> int:
        return self.count("contained")

    def share(self, outcome: str) -> float:
        return self.count(outcome) / self.total if self.total else 0.0

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "extraction_mode": self.extraction_mode,
            "size": self.size,
            "overlap": self.overlap,
            "facts_total": self.total,
            "contained": self.contained,
            "orphaned": self.orphaned,
            "broken": self.broken,
            "chunk_count": self.chunk_count,
            "mean_chunk_tokens": round(self.mean_chunk_tokens, 1),
            "max_chunk_tokens": self.max_chunk_tokens,
            "by_kind": {kind: {o: self.by_kind[kind][o] for o in OUTCOMES} for kind in FACT_KINDS},
            "lost_fact_ids": sorted(
                o.fact.fact_id for o in self.outcomes if o.outcome != "contained"
            ),
        }


def audit_fact(fact: Fact, extracted_text: str, chunks: list[Chunk]) -> FactOutcome:
    spans = tuple(normalize(s) for s in fact.spans)
    full = normalize(extracted_text)
    missing = tuple(s for s in spans if s not in full)
    if missing:
        return FactOutcome(fact, "broken", missing_spans=missing)
    holders = tuple(c.index for c in chunks if all(s in normalize(c.text) for s in spans))
    if holders:
        return FactOutcome(fact, "contained", containing_chunks=holders)
    return FactOutcome(fact, "orphaned")


def audit(
    facts: list[Fact],
    extracted: dict[str, str],
    chunks: dict[str, list[Chunk]],
    *,
    strategy: str,
    extraction_mode: str,
    size: int,
    overlap: int,
) -> AuditResult:
    """Audit every fact against its document's chunks.

    ``extracted`` maps doc_id to the full extracted text; ``chunks`` maps doc_id to that document's
    chunks. A fact whose document has no extraction is a caller error, not a silent zero.
    """
    outcomes: list[FactOutcome] = []
    for fact in facts:
        if fact.doc_id not in extracted:
            raise KeyError(
                f"fact {fact.fact_id} refers to document {fact.doc_id} with no extraction"
            )
        outcomes.append(audit_fact(fact, extracted[fact.doc_id], chunks.get(fact.doc_id, [])))
    all_chunks = [c for cs in chunks.values() for c in cs]
    by_kind: dict[str, Counter] = {kind: Counter() for kind in FACT_KINDS}
    for o in outcomes:
        by_kind[o.fact.kind][o.outcome] += 1
    return AuditResult(
        strategy=strategy,
        extraction_mode=extraction_mode,
        size=size,
        overlap=overlap,
        outcomes=outcomes,
        chunk_count=len(all_chunks),
        mean_chunk_tokens=mean(c.tokens for c in all_chunks) if all_chunks else 0.0,
        max_chunk_tokens=max((c.tokens for c in all_chunks), default=0),
        by_kind=by_kind,
    )
