"""Glue: fixture in, audit result out, for the CLI and the experiments alike.

The experiments and the CLI must measure exactly the same thing, so both call ``run_audit`` here
rather than wiring extraction, chunking and auditing together in two places that can drift apart.
"""

from __future__ import annotations

from pathlib import Path

from .audit import AuditResult, audit
from .chunkers import chunk
from .extract import Extracted, extract_dir
from .fixture import DEFAULT_FIXTURE_DIR, load_facts


def run_audit(
    *,
    strategy: str,
    size: int,
    overlap: int = 0,
    extraction_mode: str = "blocks",
    fixture_dir: Path = DEFAULT_FIXTURE_DIR,
    extracted: dict[str, Extracted] | None = None,
) -> AuditResult:
    """Extract (or reuse an extraction), chunk every document, audit every fact."""
    facts, _docs = load_facts(fixture_dir)
    if extracted is None:
        extracted = extract_dir(fixture_dir, extraction_mode)
    texts = {doc_id: ex.text for doc_id, ex in extracted.items()}
    chunks = {doc_id: chunk(strategy, ex.pages, size, overlap) for doc_id, ex in extracted.items()}
    return audit(
        facts,
        texts,
        chunks,
        strategy=strategy,
        extraction_mode=extraction_mode,
        size=size,
        overlap=overlap,
    )
