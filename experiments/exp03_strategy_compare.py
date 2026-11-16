"""Experiment 3: the five strategies at the policy size, on the recommended extraction mode.

This is the headline table. It is the same run `chunkaudit audit` prints, saved as JSON so the
README's figures are checked against it.
"""

from __future__ import annotations

from chunkaudit.chunkers import effective_overlap
from common import (
    DEFAULT_FIXTURE_DIR,
    extract_dir,
    load_policy,
    print_table,
    require_fixture,
    run_audit,
    write_result,
)

KINDS = ("single", "cross_sentence", "cross_paragraph", "cross_page", "table")


def main() -> None:
    require_fixture()
    policy = load_policy()
    size = policy.chunking.default_size
    extracted = extract_dir(DEFAULT_FIXTURE_DIR, policy.extraction_mode)
    results = []
    rows = []
    for strategy in policy.chunking.strategies:
        r = run_audit(
            strategy=strategy,
            size=size,
            overlap=effective_overlap(
                strategy, policy.chunking.default_overlap, policy.chunking.sentence_overlap
            ),
            extraction_mode=policy.extraction_mode,
            extracted=extracted,
        )
        results.append(r.to_dict())
        rows.append(
            [
                strategy,
                r.chunk_count,
                f"{r.mean_chunk_tokens:.0f}",
                r.contained,
                r.orphaned,
                r.broken,
            ]
            + [r.by_kind[k]["orphaned"] for k in KINDS]
        )
    print_table(
        ["strategy", "chunks", "mean", "contained", "orphaned", "broken", *KINDS],
        rows,
    )
    best = min(results, key=lambda r: (r["orphaned"] + r["broken"], r["strategy"]))
    worst = max(results, key=lambda r: (r["orphaned"] + r["broken"], r["strategy"]))
    write_result(
        "exp03_strategy_compare",
        {
            "question": "which strategy loses the fewest facts at the policy size",
            "size": size,
            "overlap": policy.chunking.default_overlap,
            "extraction_mode": policy.extraction_mode,
            "results": results,
            "best": {"strategy": best["strategy"], "orphaned": best["orphaned"]},
            "worst": {"strategy": worst["strategy"], "orphaned": worst["orphaned"]},
        },
    )


if __name__ == "__main__":
    main()
