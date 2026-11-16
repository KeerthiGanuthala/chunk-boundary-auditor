"""The table, the verdict and the four exit codes, exercised through the real CLI."""

import json

import pytest

from chunkaudit.cli import main
from chunkaudit.config import load_policy
from chunkaudit.fixture import DEFAULT_FIXTURE_DIR
from chunkaudit.pipeline import run_audit
from chunkaudit.report import (
    EXIT_ERROR,
    EXIT_FIXTURE,
    EXIT_OK,
    EXIT_THRESHOLD,
    table,
    verdict,
    write_json,
)

from .conftest import write_policy


@pytest.fixture
def results(small_fixture_dir):
    return [
        run_audit(strategy=s, size=256, fixture_dir=small_fixture_dir)
        for s in ("fixed", "sentence_window")
    ]


def test_the_table_has_a_header_a_rule_and_one_row_per_result(results):
    lines = table(results).splitlines()
    assert lines[0].startswith("strategy")
    assert set(lines[1].strip()) == {"-", " "}
    assert lines[2].startswith("fixed") and lines[3].startswith("sentence_window")


def test_the_table_explains_the_per_kind_columns(results):
    assert "orphaned+broken" in table(results)


def test_the_table_shows_contained_over_total(results):
    assert f"{results[0].contained}/{results[0].total}" in table(results)


def test_verdict_passes_when_the_best_strategy_is_under_the_thresholds(results, small_policy):
    code, reasons = verdict(results, small_policy)
    assert code == EXIT_OK and reasons == []


def test_verdict_fails_on_orphans_above_the_threshold(small_fixture_dir, tmp_path):
    tiny = run_audit(strategy="fixed", size=8, fixture_dir=small_fixture_dir)
    policy = load_policy(write_policy(tmp_path / "p.toml", max_orphan_share="0.0"))
    code, reasons = verdict([tiny], policy)
    assert code == EXIT_THRESHOLD
    assert any("orphans" in r for r in reasons)


def test_verdict_fails_on_extraction_loss_above_the_threshold(small_fixture_dir, small_policy):
    r = run_audit(
        strategy="fixed", size=256, extraction_mode="sorted", fixture_dir=small_fixture_dir
    )
    code, reasons = verdict([r], small_policy)
    assert code == EXIT_THRESHOLD
    assert any("extraction mode sorted broke" in x for x in reasons)


def test_verdict_with_no_results_is_an_error(small_policy):
    assert verdict([], small_policy)[0] == EXIT_ERROR


def test_verdict_judges_the_best_strategy_not_the_worst(small_fixture_dir, tmp_path):
    tiny = run_audit(strategy="fixed", size=8, fixture_dir=small_fixture_dir)
    huge = run_audit(strategy="fixed", size=100_000, fixture_dir=small_fixture_dir)
    policy = load_policy(write_policy(tmp_path / "p.toml", max_orphan_share="0.0"))
    assert verdict([tiny, huge], policy)[0] == EXIT_OK


def test_write_json_includes_results_and_extra_keys(results, tmp_path):
    out = tmp_path / "r" / "out.json"
    write_json(results, out, {"note": "x"})
    payload = json.loads(out.read_text())
    assert len(payload["results"]) == 2 and payload["note"] == "x"


# CLI


def test_cli_version_prints_and_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "chunkaudit" in capsys.readouterr().out


def test_cli_generate_check_passes_on_the_committed_fixture(capsys):
    assert main(["generate", "--check"]) == EXIT_OK
    assert "matches policy seed 20251116" in capsys.readouterr().out


def test_cli_generate_check_exits_3_when_the_fixture_differs(small_policy_path, tmp_path, capsys):
    (tmp_path / "manifest.json").write_text("{}")
    code = main(
        ["--policy", str(small_policy_path), "--fixtures", str(tmp_path), "generate", "--check"]
    )
    assert code == EXIT_FIXTURE
    assert "differs from what the policy generates" in capsys.readouterr().out


def test_cli_generate_writes_a_fixture(small_policy_path, tmp_path, capsys):
    code = main(["--policy", str(small_policy_path), "--fixtures", str(tmp_path), "generate"])
    assert code == EXIT_OK
    assert (tmp_path / "manifest.json").exists()
    assert "wrote 5 files" in capsys.readouterr().out


def test_cli_audit_prints_the_table_and_passes(capsys):
    assert main(["audit"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "PASS" in out and "sentence_window" in out


def test_cli_audit_exits_1_when_a_threshold_is_exceeded(tmp_path, capsys):
    policy = write_policy(tmp_path / "p.toml", max_orphan_share="0.0")
    policy_text = (
        policy.read_text()
        .replace("seed = 7", "seed = 20251116")
        .replace("documents = 4", "documents = 18")
    )
    policy_text = policy_text.replace("pages_max = 3", "pages_max = 5")
    policy_text = policy_text.replace("facts_single = 2", "facts_single = 6")
    policy.write_text(policy_text)
    code = main(["--policy", str(policy), "audit", "--strategy", "fixed", "--size", "64"])
    assert code == EXIT_THRESHOLD
    assert "FAIL" in capsys.readouterr().out


def test_cli_audit_exits_1_in_sorted_mode_because_extraction_loses_facts(capsys):
    code = main(["audit", "--mode", "sorted", "--strategy", "fixed"])
    assert code == EXIT_THRESHOLD
    assert "extraction mode sorted broke" in capsys.readouterr().out


def test_cli_audit_no_verdict_always_exits_zero():
    assert main(["audit", "--mode", "sorted", "--strategy", "fixed", "--no-verdict"]) == EXIT_OK


def test_cli_audit_exits_3_on_a_tampered_fixture(small_policy, small_policy_path, tmp_path, capsys):
    from chunkaudit.fixture import write_fixture

    write_fixture(small_policy, tmp_path)
    (tmp_path / "D01.pdf").write_bytes(b"%PDF tampered")
    code = main(["--policy", str(small_policy_path), "--fixtures", str(tmp_path), "audit"])
    assert code == EXIT_FIXTURE
    assert "hash mismatch D01.pdf" in capsys.readouterr().out


def test_cli_audit_exits_2_on_an_impossible_overlap(capsys):
    assert main(["audit", "--size", "32", "--overlap", "32"]) == EXIT_ERROR
    assert "overlap" in capsys.readouterr().out


def test_cli_audit_writes_json_when_asked(tmp_path):
    out = tmp_path / "audit.json"
    assert main(["audit", "--strategy", "fixed", "--json", str(out)]) == EXIT_OK
    payload = json.loads(out.read_text())
    assert payload["results"][0]["strategy"] == "fixed"
    assert payload["results"][0]["facts_total"] == 396


def test_cli_exits_2_on_a_bad_policy(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("[fixture]\nseed = 1\n")
    assert main(["--policy", str(bad), "audit"]) == EXIT_ERROR
    assert "policy error" in capsys.readouterr().out


def test_cli_extract_prints_a_page(capsys):
    assert main(["extract", "D01", "--page", "1"]) == EXIT_OK
    assert "page 1 of" in capsys.readouterr().out


def test_cli_extract_prints_the_whole_document_by_default(capsys):
    assert main(["extract", "D01"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "page 1 of" in out and "page 2 of" in out


def test_cli_extract_rejects_a_page_out_of_range(capsys):
    assert main(["extract", "D01", "--page", "99"]) == EXIT_ERROR
    assert "page must be between" in capsys.readouterr().out


def test_cli_extract_rejects_an_unknown_document(capsys):
    assert main(["extract", "D99"]) == EXIT_ERROR
    assert "no such document" in capsys.readouterr().out


def test_cli_explain_shows_where_each_span_landed(capsys):
    assert (
        main(["explain", "D01-cross_sentence-0", "--strategy", "fixed", "--size", "64"]) == EXIT_OK
    )
    out = capsys.readouterr().out
    assert "span 1" in out and "span 2" in out and "chunks holding every span" in out


def test_cli_explain_reports_a_span_lost_in_extraction(capsys):
    facts = json.loads((DEFAULT_FIXTURE_DIR / "facts.json").read_text(encoding="utf-8"))
    two_col = {d["doc_id"] for d in facts["documents"] if d["layout"] != "single"}
    fact_id = next(
        f["fact_id"]
        for f in facts["facts"]
        if f["doc_id"] in two_col and f["kind"] == "cross_sentence"
    )
    assert main(["explain", fact_id, "--mode", "sorted"]) == EXIT_OK
    out = capsys.readouterr().out
    assert "LOST IN EXTRACTION" in out or "in extraction" in out


def test_cli_explain_rejects_an_unknown_fact(capsys):
    assert main(["explain", "nope"]) == EXIT_ERROR
    assert "no such fact" in capsys.readouterr().out


def test_cli_audit_exits_3_when_facts_json_is_missing(small_policy_path, tmp_path, capsys):
    from chunkaudit.fixture import write_fixture

    write_fixture(load_policy(small_policy_path), tmp_path)
    (tmp_path / "facts.json").unlink()
    code = main(["--policy", str(small_policy_path), "--fixtures", str(tmp_path), "audit"])
    assert code == EXIT_FIXTURE


def test_cli_explain_exits_3_when_the_fixture_is_absent(small_policy_path, tmp_path, capsys):
    code = main(["--policy", str(small_policy_path), "--fixtures", str(tmp_path), "explain", "x"])
    assert code == EXIT_FIXTURE
    assert "fixture error" in capsys.readouterr().out


def test_module_entry_point_runs(capsys):
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "chunkaudit", "--version"], capture_output=True, text=True
    )
    assert proc.returncode == 0 and "chunkaudit" in proc.stdout


def test_cli_overlap_flag_does_not_reach_sentence_packing_or_paragraph_packing(tmp_path):
    out = tmp_path / "o.json"
    code = main(["audit", "--overlap", "64", "--no-verdict", "--json", str(out)])
    assert code == EXIT_OK
    by = {r["strategy"]: r for r in json.loads(out.read_text())["results"]}
    assert by["fixed"]["overlap"] == 64 and by["page_aware"]["overlap"] == 64
    assert by["sentence_window"]["overlap"] == 0 and by["paragraph"]["overlap"] == 0
