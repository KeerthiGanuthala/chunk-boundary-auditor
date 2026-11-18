"""The committed fixture, its manifest, and the pipeline that the CLI and experiments share."""

import json

import pymupdf
import pytest

from chunkaudit.fixture import (
    FixtureError,
    check_against_policy,
    load_facts,
    sha256,
    verify_manifest,
    write_fixture,
)
from chunkaudit.pipeline import run_audit


def test_write_fixture_produces_one_pdf_per_document_plus_facts_and_manifest(
    small_corpus, small_fixture_dir
):
    names = sorted(p.name for p in small_fixture_dir.iterdir())
    expected = sorted(
        [f"{d.doc_id}.pdf" for d in small_corpus.documents] + ["facts.json", "manifest.json"]
    )
    assert names == expected


def test_the_manifest_hashes_every_pdf_and_the_facts_file(small_fixture_dir):
    manifest = json.loads((small_fixture_dir / "manifest.json").read_text())
    assert "facts.json" in manifest["files"]
    for name, digest in manifest["files"].items():
        assert sha256(small_fixture_dir / name) == digest


def test_verify_manifest_passes_on_a_fresh_fixture(small_fixture_dir):
    assert verify_manifest(small_fixture_dir) == []


def test_verify_manifest_reports_a_missing_manifest(tmp_path):
    assert verify_manifest(tmp_path) == [f"missing {tmp_path / 'manifest.json'}"]


def test_verify_manifest_reports_a_modified_pdf(small_policy, tmp_path):
    write_fixture(small_policy, tmp_path)
    pdf = tmp_path / "D01.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"\n%tamper")
    assert verify_manifest(tmp_path) == ["hash mismatch D01.pdf"]


def test_verify_manifest_reports_a_missing_pdf(small_policy, tmp_path):
    write_fixture(small_policy, tmp_path)
    (tmp_path / "D02.pdf").unlink()
    assert verify_manifest(tmp_path) == ["missing D02.pdf"]


def test_verify_manifest_reports_an_unlisted_pdf(small_policy, tmp_path):
    write_fixture(small_policy, tmp_path)
    (tmp_path / "D99.pdf").write_bytes(b"%PDF-1.4 stray")
    assert verify_manifest(tmp_path) == ["unlisted file D99.pdf"]


def test_regenerating_writes_identical_bytes(small_policy, tmp_path):
    a = write_fixture(small_policy, tmp_path / "a")
    b = write_fixture(small_policy, tmp_path / "b")
    assert a["files"] == b["files"]


def test_regenerating_removes_stale_pdfs(small_policy, tmp_path):
    (tmp_path / "old.pdf").write_bytes(b"%PDF stale")
    write_fixture(small_policy, tmp_path)
    assert not (tmp_path / "old.pdf").exists()


def test_check_against_policy_is_clean_for_a_matching_fixture(
    small_policy, small_fixture_dir, tmp_path
):
    result = check_against_policy(small_policy, small_fixture_dir, tmp_path)
    assert result.problems == []
    assert result.byte_only == []
    assert result.ok


def test_check_against_policy_names_a_missing_or_unreadable_file(small_policy, tmp_path):
    committed = tmp_path / "committed"
    write_fixture(small_policy, committed)
    (committed / "D01.pdf").write_bytes(b"%PDF not a real pdf")
    (committed / "D03.pdf").unlink()
    result = check_against_policy(small_policy, committed, tmp_path / "scratch")
    assert result.problems == ["unreadable D01.pdf", "missing D03.pdf"]
    assert not result.ok


def test_check_against_policy_flags_a_real_text_change(small_policy, tmp_path):
    """A committed PDF whose extracted text moved is a content problem: a number would move."""
    committed = tmp_path / "committed"
    write_fixture(small_policy, committed)
    doc = pymupdf.open(committed / "D02.pdf")
    doc[0].insert_text((70, 70), "An extra planted sentence that was never in the corpus.")
    doc.save(committed / "_tmp.pdf", garbage=0, deflate=True, no_new_id=True)
    doc.close()
    (committed / "_tmp.pdf").replace(committed / "D02.pdf")
    result = check_against_policy(small_policy, committed, tmp_path / "scratch")
    assert "text differs D02.pdf" in result.problems
    assert not result.ok


def test_check_against_policy_tolerates_a_bytes_only_difference(small_policy, tmp_path):
    """The regression this fix exists for: different compressed bytes, identical extracted text.

    This is what a different PyMuPDF build produces. The committed PyMuPDF 2.1 (Python 3.11+) and
    the 1.28.2 that Python 3.10 resolves to write the same text to different bytes; the check must
    pass on that difference, because it moves no number, and only report it.
    """
    committed = tmp_path / "committed"
    write_fixture(small_policy, committed)
    original = (committed / "D01.pdf").read_bytes()
    # Re-save with the streams left uncompressed: different bytes, byte for byte the same text.
    doc = pymupdf.open(committed / "D01.pdf")
    doc.save(committed / "_tmp.pdf", garbage=4, deflate=False, clean=True)
    doc.close()
    (committed / "_tmp.pdf").replace(committed / "D01.pdf")
    assert (committed / "D01.pdf").read_bytes() != original  # precondition: bytes really differ
    result = check_against_policy(small_policy, committed, tmp_path / "scratch")
    assert result.problems == []
    assert result.byte_only == ["D01.pdf"]
    assert result.ok


def test_load_facts_round_trips_the_corpus(small_corpus, small_fixture_dir):
    facts, docs = load_facts(small_fixture_dir)
    assert facts == small_corpus.facts
    assert [d["doc_id"] for d in docs] == [d.doc_id for d in small_corpus.documents]


def test_load_facts_records_layout_and_page_count(small_corpus, small_fixture_dir):
    _, docs = load_facts(small_fixture_dir)
    for meta, d in zip(docs, small_corpus.documents, strict=True):
        assert meta["layout"] == d.layout and meta["pages"] == len(d.pages)


def test_load_facts_without_a_fixture_is_a_fixture_error(tmp_path):
    with pytest.raises(FixtureError, match="generate"):
        load_facts(tmp_path)


def test_the_committed_fixture_matches_its_manifest(committed_fixture_dir):
    assert verify_manifest(committed_fixture_dir) == []


def test_the_committed_fixture_matches_the_committed_policy(
    default_policy, committed_fixture_dir, tmp_path
):
    assert check_against_policy(default_policy, committed_fixture_dir, tmp_path).problems == []


def test_run_audit_audits_every_fact_in_the_fixture(small_corpus, small_fixture_dir):
    r = run_audit(strategy="fixed", size=256, fixture_dir=small_fixture_dir)
    assert r.total == len(small_corpus.facts)
    assert r.contained + r.orphaned + r.broken == r.total


def test_run_audit_is_deterministic(small_fixture_dir):
    a = run_audit(strategy="recursive", size=128, fixture_dir=small_fixture_dir)
    b = run_audit(strategy="recursive", size=128, fixture_dir=small_fixture_dir)
    assert a.to_dict() == b.to_dict()


def test_run_audit_reuses_a_supplied_extraction(small_fixture_dir):
    from chunkaudit.extract import extract_dir

    ex = extract_dir(small_fixture_dir, "sorted")
    r = run_audit(
        strategy="fixed",
        size=256,
        extraction_mode="sorted",
        fixture_dir=small_fixture_dir,
        extracted=ex,
    )
    assert r.extraction_mode == "sorted"
    assert r.broken > 0


def test_blocks_mode_breaks_nothing_on_the_small_fixture(small_fixture_dir):
    r = run_audit(
        strategy="fixed", size=256, extraction_mode="blocks", fixture_dir=small_fixture_dir
    )
    assert r.broken == 0


def test_a_huge_chunk_size_contains_every_fact_that_extraction_kept(small_fixture_dir):
    r = run_audit(
        strategy="fixed", size=100_000, extraction_mode="blocks", fixture_dir=small_fixture_dir
    )
    assert r.orphaned == 0 and r.broken == 0


def test_a_tiny_chunk_size_orphans_every_pair_fact(small_fixture_dir):
    r = run_audit(strategy="fixed", size=8, extraction_mode="blocks", fixture_dir=small_fixture_dir)
    pair_kinds = ("cross_sentence", "cross_paragraph", "cross_page", "table")
    for kind in pair_kinds:
        assert r.by_kind[kind]["contained"] == 0, kind
