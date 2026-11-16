"""Experiment 1: which facts die as the chunk gets smaller.

Question the README asks: is the loss a property of the strategy or of the size? Every strategy
is run at six sizes with no overlap, on the recommended extraction mode, and the orphan count is
recorded per fact kind.
"""

from __future__ import annotations

from common import (
    DEFAULT_FIXTURE_DIR,
    extract_dir,
    load_policy,
    print_table,
    require_fixture,
    run_audit,
    write_result,
)

SIZES = (128, 256, 384, 512, 768, 1024)


def main() -> None:
    require_fixture()
    policy = load_policy()
    extracted = extract_dir(DEFAULT_FIXTURE_DIR, policy.extraction_mode)
    rows = []
    results = []
    for size in SIZES:
        for strategy in policy.chunking.strategies:
            r = run_audit(
                strategy=strategy,
                size=size,
                extraction_mode=policy.extraction_mode,
                extracted=extracted,
            )
            results.append(r.to_dict())
            rows.append(
                [size, strategy, r.chunk_count, f"{r.mean_chunk_tokens:.0f}", r.orphaned, r.broken]
                + [
                    r.by_kind[k]["orphaned"]
                    for k in ("single", "cross_sentence", "cross_paragraph", "cross_page", "table")
                ]
            )
    print_table(
        [
            "size",
            "strategy",
            "chunks",
            "mean",
            "orphaned",
            "broken",
            "single",
            "x_sent",
            "x_para",
            "x_page",
            "table",
        ],
        rows,
    )
    best_per_size = {}
    for size in SIZES:
        at_size = [r for r in results if r["size"] == size]
        best = min(at_size, key=lambda r: (r["orphaned"], r["strategy"]))
        best_per_size[str(size)] = {"strategy": best["strategy"], "orphaned": best["orphaned"]}
    write_result(
        "exp01_size_sweep",
        {
            "question": "which facts die as the chunk gets smaller",
            "extraction_mode": policy.extraction_mode,
            "sizes": list(SIZES),
            "results": results,
            "best_per_size": best_per_size,
        },
    )


if __name__ == "__main__":
    main()
