"""Experiment 2: what overlap recovers, and what it costs.

Question the README asks: the usual fix for a boundary loss is overlap, so how many orphans does
overlap recover at the default size, and how many more chunks does the index carry for it? Run
for the fixed and recursive strategies, which are the two that take a token overlap.
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

OVERLAPS = (0, 32, 64, 128, 256)
STRATEGIES = ("fixed", "recursive")


def main() -> None:
    require_fixture()
    policy = load_policy()
    size = policy.chunking.default_size
    extracted = extract_dir(DEFAULT_FIXTURE_DIR, policy.extraction_mode)
    rows = []
    results = []
    baseline: dict[str, dict] = {}
    for strategy in STRATEGIES:
        for overlap in OVERLAPS:
            r = run_audit(
                strategy=strategy,
                size=size,
                overlap=overlap,
                extraction_mode=policy.extraction_mode,
                extracted=extracted,
            )
            d = r.to_dict()
            if overlap == 0:
                baseline[strategy] = d
            base = baseline[strategy]
            d["recovered"] = base["orphaned"] - d["orphaned"]
            d["chunk_growth_ratio"] = round(d["chunk_count"] / base["chunk_count"], 2)
            results.append(d)
            rows.append(
                [
                    strategy,
                    overlap,
                    d["chunk_count"],
                    d["chunk_growth_ratio"],
                    d["orphaned"],
                    d["recovered"],
                ]
            )
    print_table(["strategy", "overlap", "chunks", "growth", "orphaned", "recovered"], rows)
    write_result(
        "exp02_overlap_sweep",
        {
            "question": "what overlap recovers and what it costs",
            "size": size,
            "extraction_mode": policy.extraction_mode,
            "overlaps": list(OVERLAPS),
            "results": results,
        },
    )


if __name__ == "__main__":
    main()
