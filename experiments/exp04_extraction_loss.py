"""Experiment 4: how many facts die before any chunker runs.

Question the README asks: the chunker gets blamed for every lost fact, so how many were already
gone when the PDF extractor handed over the text? The best strategy from experiment 3 is run on
all three extraction orders, and the broken count is split by document layout so the loss can
be attributed to the layout that causes it.
"""

from __future__ import annotations

from collections import Counter

from common import (
    DEFAULT_FIXTURE_DIR,
    extract_dir,
    load_facts,
    load_policy,
    print_table,
    require_fixture,
    run_audit,
    write_result,
)

MODES = ("raw", "sorted", "blocks")
LAYOUTS = ("single", "two_column", "two_column_reversed")


def main() -> None:
    require_fixture()
    policy = load_policy()
    size = policy.chunking.default_size
    facts, docs = load_facts(DEFAULT_FIXTURE_DIR)
    layout_of = {d["doc_id"]: d["layout"] for d in docs}
    facts_per_layout = Counter(layout_of[f.doc_id] for f in facts)
    # Judge extraction with the strategy that loses the fewest facts on the recommended mode, so
    # the comparison between modes is not confounded by a weak chunker.
    strategies = policy.chunking.strategies
    on_blocks = extract_dir(DEFAULT_FIXTURE_DIR, "blocks")
    judged = min(
        (
            run_audit(strategy=s, size=size, extraction_mode="blocks", extracted=on_blocks)
            for s in strategies
        ),
        key=lambda r: (r.orphaned, r.strategy),
    ).strategy
    rows = []
    results = []
    for mode in MODES:
        extracted = on_blocks if mode == "blocks" else extract_dir(DEFAULT_FIXTURE_DIR, mode)
        r = run_audit(strategy=judged, size=size, extraction_mode=mode, extracted=extracted)
        by_layout = {layout: Counter() for layout in LAYOUTS}
        for o in r.outcomes:
            by_layout[layout_of[o.fact.doc_id]][o.outcome] += 1
        d = r.to_dict()
        d["by_layout"] = {
            layout: {
                "facts": facts_per_layout[layout],
                "orphaned": by_layout[layout]["orphaned"],
                "broken": by_layout[layout]["broken"],
            }
            for layout in LAYOUTS
        }
        results.append(d)
        rows.append(
            [mode, r.orphaned, r.broken]
            + [f"{by_layout[lay]['orphaned']}+{by_layout[lay]['broken']}" for lay in LAYOUTS]
        )
    print_table(["mode", "orphaned", "broken", *LAYOUTS], rows)
    print("layout columns read orphaned+broken")
    write_result(
        "exp04_extraction_loss",
        {
            "question": "how many facts die before any chunker runs",
            "size": size,
            "strategy": judged,
            "facts_per_layout": dict(facts_per_layout),
            "results": results,
        },
    )


if __name__ == "__main__":
    main()
