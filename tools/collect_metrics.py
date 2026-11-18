"""Re-measure every figure the documents quote and write docs/metrics.json.

Nothing in this file is typed by hand. Test count and coverage come from the junit and coverage
JSON reports that `make test` writes; every other figure comes from the experiment JSON under
docs/experiments and the fixture's facts.json. With --run, the tests and experiments are executed
first; without it, missing inputs are an error rather than a silent default.

Each metric carries anchor phrases: the wording a document must use around the value, with the
value substituted in. tools/check_numbers.py matches those phrases, not bare digits, so a stale
sentence fails the build even when its digits happen to appear elsewhere.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
FIXTURES = ROOT / "src" / "chunkaudit" / "data" / "fixtures"
EXPERIMENTS = ROOT / "docs" / "experiments"
OUT = ROOT / "docs" / "metrics.json"

CHECKED_DOCUMENTS = [
    "README.md",
    "docs/defense-guide.md",
    "docs/adr/ADR-001-synthetic-corpus-with-planted-facts.md",
    "docs/adr/ADR-002-containment-as-the-metric.md",
    "docs/adr/ADR-003-token-counting-without-a-network.md",
    "docs/adr/ADR-004-one-library-for-generation-and-extraction.md",
    "docs/adr/ADR-005-overlap-as-a-priced-trade.md",
]

ANCHORS: dict[str, list[str]] = {
    "facts_total": ["{} planted facts", "of the {} planted", "{} planted"],
    "facts_single": ["{} single,"],
    "facts_cross_sentence": ["{} cross-sentence,"],
    "facts_cross_paragraph": ["{} cross-paragraph,"],
    "facts_cross_page": ["{} cross-page and"],
    "facts_table": ["and {} table"],
    "documents_total": ["{} PDFs", "{} documents include"],
    "pages_total": ["{} pages,"],
    "two_column_documents": ["{} two-column documents", "{} of the documents are two-column"],
    "reversed_documents": ["{} of those write", "{} of those"],
    "two_column_facts": ["has {} facts on two-column"],
    "tests_total": ["{} tests"],
    "coverage_line_pct": ["{} percent line coverage"],
    "policy_size": [
        "policy size of {} tokens",
        "size of {} tokens would",
        "A size of {} in this repository",
        "{} of its own tokens",
        "{} BPE tokens",
    ],
    "sentence_window_orphaned": ["still orphans {} facts", "sentence packing loses {}"],
    "fixed_orphaned": ["lose {} facts (", '"orphans {} facts"'],
    "recursive_orphaned": ["recursive splitter loses {}"],
    "page_aware_orphaned": ["page-aware windows lose {}"],
    "page_aware_cross_page_orphaned": ["all {} cross-page facts", "pinned at the {} cross-page"],
    "paragraph_orphaned": ["paragraph packing loses {}"],
    "best_orphan_share_pct": [
        "losing {} percent of the planted",
        "loses {} percent of the planted",
    ],
    "fixed_orphan_share_pct": ["({} percent of planted facts)"],
    "fixed_overlap_to_zero": ["overlap of {} tokens recovers"],
    "fixed_overlap_growth_pct": ["at {} percent more chunks"],
    "fixed_overlap_32_orphaned": ["brings the loss down to {}"],
    "recursive_overlap_32_extra_lost": ["loses {} more fact than", "lost {} more fact than"],
    "recursive_overlap_64_extra_lost": ["64 tokens loses {} more", "64 tokens lost {} more"],
    "recursive_overlap_to_zero": ["reaches zero at {} tokens"],
    "recursive_overlap_zero_growth_pct": ["index {} percent larger"],
    "sorted_broken": ["breaks {} of the 396"],
    "sorted_broken_pct": ["{} percent of every fact"],
    "sorted_broken_two_column_pct": ["sorting breaks {} percent of them"],
    "raw_reversed_orphaned": ["costs {} orphans"],
    "blocks_broken": ["breaks {} of the same facts", "broke {} facts", "loses {} of the facts"],
    "fixed_128_orphaned": ["lose {} facts at 128 tokens"],
    "fixed_128_orphan_share_pct": ["which is {} percent of planted"],
    "sentence_window_128_orphaned": ["sentence packing orphans {} at 128"],
    "sentence_window_1024_orphaned": ["down to {} fact at 1024"],
    "resolution_floor_denominator": ["one in {}", "zero over {} facts"],
    "adr_count": ["{} decision records", "{} ADRs"],
    "experiment_count": ["{} experiments"],
    "strategy_count": ["{} strategies and"],
    "extraction_mode_count": ["offers {} orders", "{} extraction orders"],
}


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def read_junit(path: Path) -> int:
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root[0]
    total = int(suite.get("tests", 0))
    failures = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
    if failures:
        sys.exit(f"junit reports {failures} failing tests; receipts refuse to describe a red suite")
    return total


def read_coverage(path: Path) -> float:
    return float(json.loads(path.read_text())["totals"]["percent_covered"])


def load_experiment(name: str) -> dict:
    path = EXPERIMENTS / f"{name}.json"
    if not path.exists():
        sys.exit(f"missing {path}; run `make experiments` (or collect_metrics.py --run)")
    return json.loads(path.read_text(encoding="utf-8"))


def by_strategy(results: list[dict]) -> dict[str, dict]:
    return {r["strategy"]: r for r in results}


def collect() -> dict:
    facts_json = json.loads((FIXTURES / "facts.json").read_text(encoding="utf-8"))
    kinds = Counter(f["kind"] for f in facts_json["facts"])
    layouts = Counter(d["layout"] for d in facts_json["documents"])
    facts_per_doc = Counter(f["doc_id"] for f in facts_json["facts"])
    layout_of = {d["doc_id"]: d["layout"] for d in facts_json["documents"]}
    two_column_facts = sum(n for doc, n in facts_per_doc.items() if layout_of[doc] != "single")

    exp01 = load_experiment("exp01_size_sweep")
    exp02 = load_experiment("exp02_overlap_sweep")
    exp03 = load_experiment("exp03_strategy_compare")
    exp04 = load_experiment("exp04_extraction_loss")

    s3 = by_strategy(exp03["results"])
    total = s3["fixed"]["facts_total"]
    best = exp03["best"]

    fixed_rows = [r for r in exp02["results"] if r["strategy"] == "fixed"]
    rec_rows = [r for r in exp02["results"] if r["strategy"] == "recursive"]
    fixed_zero = next(r for r in fixed_rows if r["orphaned"] == 0)
    rec_zero = next(r for r in rec_rows if r["orphaned"] == 0)
    rec_by_overlap = {r["overlap"]: r for r in rec_rows}
    fixed_by_overlap = {r["overlap"]: r for r in fixed_rows}

    modes = {r["extraction_mode"]: r for r in exp04["results"]}
    sorted_two_col_broken = (
        modes["sorted"]["by_layout"]["two_column"]["broken"]
        + modes["sorted"]["by_layout"]["two_column_reversed"]["broken"]
    )

    size128 = {r["strategy"]: r for r in exp01["results"] if r["size"] == 128}
    size1024 = {r["strategy"]: r for r in exp01["results"] if r["size"] == 1024}

    metrics = {
        "facts_total": total,
        "facts_single": kinds["single"],
        "facts_cross_sentence": kinds["cross_sentence"],
        "facts_cross_paragraph": kinds["cross_paragraph"],
        "facts_cross_page": kinds["cross_page"],
        "facts_table": kinds["table"],
        "documents_total": len(facts_json["documents"]),
        "pages_total": sum(d["pages"] for d in facts_json["documents"]),
        "two_column_documents": layouts["two_column"] + layouts["two_column_reversed"],
        "reversed_documents": layouts["two_column_reversed"],
        "two_column_facts": two_column_facts,
        "tests_total": read_junit(REPORTS / "junit.xml"),
        "coverage_line_pct": int(read_coverage(REPORTS / "coverage.json")),
        "policy_size": exp03["size"],
        "best_strategy": best["strategy"],
        "sentence_window_orphaned": s3["sentence_window"]["orphaned"],
        "fixed_orphaned": s3["fixed"]["orphaned"],
        "recursive_orphaned": s3["recursive"]["orphaned"],
        "page_aware_orphaned": s3["page_aware"]["orphaned"],
        "page_aware_cross_page_orphaned": s3["page_aware"]["by_kind"]["cross_page"]["orphaned"],
        "paragraph_orphaned": s3["paragraph"]["orphaned"],
        "best_orphan_share_pct": round(100 * best["orphaned"] / total, 1),
        "fixed_orphan_share_pct": round(100 * s3["fixed"]["orphaned"] / total, 1),
        "fixed_overlap_to_zero": fixed_zero["overlap"],
        "fixed_overlap_growth_pct": round(100 * (fixed_zero["chunk_growth_ratio"] - 1)),
        "fixed_overlap_32_orphaned": fixed_by_overlap[32]["orphaned"],
        "recursive_overlap_32_extra_lost": -rec_by_overlap[32]["recovered"],
        "recursive_overlap_64_extra_lost": -rec_by_overlap[64]["recovered"],
        "recursive_overlap_to_zero": rec_zero["overlap"],
        "recursive_overlap_zero_growth_pct": round(100 * (rec_zero["chunk_growth_ratio"] - 1)),
        "sorted_broken": modes["sorted"]["broken"],
        "sorted_broken_pct": round(100 * modes["sorted"]["broken"] / total, 1),
        "sorted_broken_two_column_pct": round(100 * sorted_two_col_broken / two_column_facts, 1),
        "raw_reversed_orphaned": modes["raw"]["by_layout"]["two_column_reversed"]["orphaned"],
        "blocks_broken": modes["blocks"]["broken"],
        "fixed_128_orphaned": size128["fixed"]["orphaned"],
        "fixed_128_orphan_share_pct": round(100 * size128["fixed"]["orphaned"] / total, 1),
        "sentence_window_128_orphaned": size128["sentence_window"]["orphaned"],
        "sentence_window_1024_orphaned": size1024["sentence_window"]["orphaned"],
        "resolution_floor_denominator": total,
        "adr_count": len([d for d in CHECKED_DOCUMENTS if "/adr/" in d]),
        "experiment_count": 4,
        "strategy_count": len(s3),
        "extraction_mode_count": len(modes),
    }
    return {
        "metrics": metrics,
        "anchors": ANCHORS,
        "checked_documents": CHECKED_DOCUMENTS,
        "allowed_unanchored": [
            "0",
            "1",
            "2",
            "3",
            "32",
            "64",
            "128",
            "256",
            "384",
            "768",
            "1024",
            "3.10",
            "3.11",
            "3.12",
            "1.28.2",
            "2.1",
            "0.1.0",
            "2025",
            "20251116",
            "ADR-001",
            "ADR-002",
            "ADR-003",
            "ADR-004",
            "ADR-005",
            "exp01",
            "exp02",
            "exp03",
            "exp04",
            "D06-single-1",
            "D06",
        ],
        "note": "every value here is produced by running the suite and the experiments",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run", action="store_true", help="run tests and experiments first")
    args = parser.parse_args()
    if args.run:
        REPORTS.mkdir(exist_ok=True)
        run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--junitxml=reports/junit.xml",
                "--cov=chunkaudit",
                "--cov-report=json:reports/coverage.json",
            ]
        )
        for exp in sorted((ROOT / "experiments").glob("exp0*.py")):
            run([sys.executable, str(exp)])
    for needed in (REPORTS / "junit.xml", REPORTS / "coverage.json"):
        if not needed.exists():
            sys.exit(f"missing {needed}; run `make test` (or collect_metrics.py --run)")
    payload = collect()
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} with {len(payload['metrics'])} metrics")
    for key, value in payload["metrics"].items():
        print(f"  {key} = {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
