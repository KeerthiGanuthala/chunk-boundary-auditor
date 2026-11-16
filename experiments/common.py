"""Shared plumbing for the experiments: where JSON goes, how a table prints, what gets recorded.

Every experiment writes one JSON file to docs/experiments/ and prints one table. The JSON is what
tools/collect_metrics.py reads, so an experiment that prints a number it does not also write is a
number nothing can check.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "experiments"
sys.path.insert(0, str(ROOT / "src"))

from chunkaudit.config import load_policy  # noqa: E402
from chunkaudit.extract import extract_dir  # noqa: E402
from chunkaudit.fixture import DEFAULT_FIXTURE_DIR, load_facts, verify_manifest  # noqa: E402
from chunkaudit.pipeline import run_audit  # noqa: E402

__all__ = [
    "DEFAULT_FIXTURE_DIR",
    "OUT_DIR",
    "extract_dir",
    "load_facts",
    "load_policy",
    "print_table",
    "require_fixture",
    "run_audit",
    "write_result",
]


def require_fixture() -> None:
    problems = verify_manifest(DEFAULT_FIXTURE_DIR)
    if problems:
        sys.exit("fixture does not match its manifest: " + "; ".join(problems))


def write_result(name: str, payload: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return path


def print_table(headers: list[str], rows: list[list[object]]) -> None:
    cells = [[str(c) for c in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in cells)) for i, h in enumerate(headers)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in cells:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)))
