"""Tables, JSON and the exit code.

The exit code is the tool's one-word answer and the distinction it draws matters:

    0  the audit ran and the policy thresholds hold
    1  the audit ran and the answer is no: a threshold was exceeded
    2  the tool could not answer: bad arguments, unreadable fixture, policy error
    3  the fixture does not match its manifest, so any number it produced would describe
       bytes nobody committed

Code 1 is a finding. Code 2 and 3 are failures to find. A CI job should treat them differently.
"""

from __future__ import annotations

import json
from pathlib import Path

from .audit import AuditResult
from .config import Policy
from .corpus import FACT_KINDS

EXIT_OK = 0
EXIT_THRESHOLD = 1
EXIT_ERROR = 2
EXIT_FIXTURE = 3


def _row(cells: list[str], widths: list[int]) -> str:
    return "  ".join(c.ljust(w) for c, w in zip(cells, widths, strict=True))


def table(results: list[AuditResult]) -> str:
    """One line per strategy, with the breakdown by fact kind. Plain text, fixed width."""
    headers = ["strategy", "mode", "size", "chunks", "mean", "contained", "orphaned", "broken"]
    headers += [f"{k}" for k in FACT_KINDS]
    rows: list[list[str]] = []
    for r in results:
        row = [
            r.strategy,
            r.extraction_mode,
            str(r.size),
            str(r.chunk_count),
            f"{r.mean_chunk_tokens:.0f}",
            f"{r.contained}/{r.total}",
            str(r.orphaned),
            str(r.broken),
        ]
        for kind in FACT_KINDS:
            c = r.by_kind[kind]
            row.append(f"{c['orphaned']}+{c['broken']}")
        rows.append(row)
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    lines = [_row(headers, widths), _row(["-" * w for w in widths], widths)]
    lines += [_row(r, widths) for r in rows]
    lines.append("")
    lines.append(
        "per-kind columns read orphaned+broken; a fact is broken when extraction lost a span"
    )
    return "\n".join(lines)


def verdict(results: list[AuditResult], policy: Policy) -> tuple[int, list[str]]:
    """Apply the policy thresholds to the best strategy. Returns (exit code, reasons)."""
    if not results:
        return EXIT_ERROR, ["no audit results"]
    reasons: list[str] = []
    best = min(results, key=lambda r: (r.orphaned + r.broken, r.strategy))
    orphan_share = best.orphaned / best.total if best.total else 0.0
    broken_share = best.broken / best.total if best.total else 0.0
    th = policy.thresholds
    if orphan_share > th.max_orphan_share:
        reasons.append(
            f"best strategy {best.strategy} orphans {best.orphaned} of {best.total} facts "
            f"({orphan_share:.1%}), above max_orphan_share {th.max_orphan_share:.1%}"
        )
    if broken_share > th.max_extraction_loss_share:
        reasons.append(
            f"extraction mode {best.extraction_mode} broke {best.broken} of {best.total} facts "
            f"({broken_share:.1%}), above max_extraction_loss_share "
            f"{th.max_extraction_loss_share:.1%}"
        )
    return (EXIT_THRESHOLD if reasons else EXIT_OK), reasons


def write_json(results: list[AuditResult], path: Path, extra: dict | None = None) -> None:
    payload = {"results": [r.to_dict() for r in results]}
    if extra:
        payload.update(extra)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
