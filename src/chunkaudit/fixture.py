"""The committed fixture: PDFs, the facts planted in them, and a manifest that pins both.

The fixture is committed rather than regenerated on every run so that a reviewer audits the same
bytes the README describes, and so that a PyMuPDF upgrade that changes layout is caught as a
manifest mismatch rather than silently moving every number. ``chunkaudit generate --check``
regenerates into a temporary directory and compares hashes; CI runs it on every push.

Files:
    data/fixtures/D01.pdf ...   one PDF per document
    data/fixtures/facts.json    every fact with its kind, question, answer and required spans, plus
                           each document's layout and page count
    data/fixtures/manifest.json seed, generator parameters and the SHA-256 of every file above
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .config import Policy
from .corpus import Corpus, Fact, corpus_from_policy
from .pdfgen import write_corpus

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parent / "data" / "fixtures"


class FixtureError(RuntimeError):
    """The fixture on disk does not match what the policy would generate."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_fixture(policy: Policy, out_dir: Path) -> dict:
    """Generate the corpus, render the PDFs, write facts.json and manifest.json. Return manifest."""
    corpus = corpus_from_policy(policy)
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.pdf"):
        stale.unlink()
    pdfs = write_corpus(corpus, out_dir)
    facts_payload = {
        "seed": corpus.seed,
        "documents": [
            {
                "doc_id": d.doc_id,
                "title": d.title,
                "layout": d.layout,
                "pages": len(d.pages),
                "paragraphs": sum(len(p.paragraphs) for p in d.pages),
            }
            for d in corpus.documents
        ],
        "facts": [asdict(f) for f in corpus.facts],
    }
    facts_path = out_dir / "facts.json"
    facts_path.write_text(json.dumps(facts_payload, indent=1) + "\n", encoding="utf-8")
    manifest = {
        "seed": policy.fixture.seed,
        "generator": asdict(policy.fixture),
        "files": {p.name: sha256(p) for p in [*pdfs, facts_path]},
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def load_facts(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> tuple[list[Fact], list[dict]]:
    path = fixture_dir / "facts.json"
    if not path.exists():
        raise FixtureError(f"missing {path}; run `chunkaudit generate` first")
    payload = json.loads(path.read_text(encoding="utf-8"))
    facts = [Fact(**{**f, "spans": tuple(f["spans"])}) for f in payload["facts"]]
    return facts, payload["documents"]


def verify_manifest(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> list[str]:
    """Return a list of problems (empty when the fixture matches its manifest)."""
    path = fixture_dir / "manifest.json"
    if not path.exists():
        return [f"missing {path}"]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []
    for name, digest in manifest["files"].items():
        file = fixture_dir / name
        if not file.exists():
            problems.append(f"missing {name}")
        elif sha256(file) != digest:
            problems.append(f"hash mismatch {name}")
    extra = {p.name for p in fixture_dir.glob("*.pdf")} - set(manifest["files"])
    for name in sorted(extra):
        problems.append(f"unlisted file {name}")
    return problems


def check_against_policy(policy: Policy, fixture_dir: Path, scratch: Path) -> list[str]:
    """Regenerate into ``scratch`` and report every file whose bytes differ from ``fixture_dir``."""
    fresh = write_fixture(policy, scratch)
    problems: list[str] = []
    for name, digest in fresh["files"].items():
        committed = fixture_dir / name
        if not committed.exists():
            problems.append(f"missing {name}")
        elif sha256(committed) != digest:
            problems.append(f"differs {name}")
    return problems


def corpus_for(policy: Policy) -> Corpus:
    return corpus_from_policy(policy)
