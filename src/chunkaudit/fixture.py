"""The committed fixture: PDFs, the facts planted in them, and a manifest that pins the bytes.

The fixture is committed rather than regenerated on every run so that a reviewer audits the same
files the README describes. Two checks guard it, for two different failures. ``verify_manifest``
compares the committed bytes against the SHA-256 in the manifest: a cheap tamper and corruption
check that needs no regeneration and holds in any environment. ``check_against_policy`` regenerates
from the seed and compares content, the planted facts and the extracted text, which is what every
number depends on; a PyMuPDF build that recompresses identical text to different bytes is reported
but is not a failure, because it moves no number. CI runs both on every push.

Files:
    data/fixtures/D01.pdf ...   one PDF per document
    data/fixtures/facts.json    every fact with its kind, question, answer and required spans, plus
                           each document's layout and page count
    data/fixtures/manifest.json seed, generator parameters and the SHA-256 of every file above
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Policy
from .corpus import Corpus, Fact, corpus_from_policy
from .extract import MODES, extract_pdf
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


@dataclass
class ReproCheck:
    """Outcome of regenerating the fixture and comparing it with the committed copy.

    ``problems`` are content differences (a changed fact, or extracted text that moved): these fail
    the check, because they would move a published number. ``byte_only`` names PDFs whose compressed
    bytes differ while every mode's extracted text is identical: a PyMuPDF build difference that
    changes no number, reported but not a failure.
    """

    problems: list[str]
    byte_only: list[str]

    @property
    def ok(self) -> bool:
        return not self.problems


def check_against_policy(policy: Policy, fixture_dir: Path, scratch: Path) -> ReproCheck:
    """Regenerate into ``scratch`` and compare content with the committed fixture.

    The reproducible invariant is the corpus and the text a reader (and the audit) sees, not the
    compressed PDF bytes. A third-party renderer does not promise byte-identical output across its
    own versions and does not need to, because what every number depends on is the extracted text.
    So this compares facts.json and the text extracted in all three modes, and treats a bytes-only
    difference (identical text, different compression) as information rather than a failure. The
    extracted text was verified identical under PyMuPDF 1.28.2 (Python 3.10) and 2.1 (Python 3.11+).
    """
    write_fixture(policy, scratch)
    problems: list[str] = []
    byte_only: list[str] = []

    committed_facts = fixture_dir / "facts.json"
    if not committed_facts.exists():
        problems.append("missing facts.json")
    elif json.loads(committed_facts.read_text(encoding="utf-8")) != json.loads(
        (scratch / "facts.json").read_text(encoding="utf-8")
    ):
        problems.append("facts.json content differs")

    for fresh_pdf in sorted(scratch.glob("*.pdf")):
        name = fresh_pdf.name
        committed_pdf = fixture_dir / name
        if not committed_pdf.exists():
            problems.append(f"missing {name}")
            continue
        try:
            committed_text = {m: extract_pdf(committed_pdf, m).text for m in MODES}
        except Exception:
            # A committed PDF that cannot even be opened is itself a content problem.
            problems.append(f"unreadable {name}")
            continue
        fresh_text = {m: extract_pdf(fresh_pdf, m).text for m in MODES}
        if committed_text != fresh_text:
            problems.append(f"text differs {name}")
        elif sha256(committed_pdf) != sha256(fresh_pdf):
            byte_only.append(name)

    return ReproCheck(problems=problems, byte_only=byte_only)


def corpus_for(policy: Policy) -> Corpus:
    return corpus_from_policy(policy)
