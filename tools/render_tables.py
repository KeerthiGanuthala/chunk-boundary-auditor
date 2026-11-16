"""Render the README's result tables from the experiment JSON, in place, and check them in CI.

A hand-typed table is the easiest place for a number to go wrong, because a typo in a cell is not
a stale phrase and no anchor guards it. So every result table in the README sits between a pair
of markers and is written by this script from docs/experiments/*.json:

    <!-- table:exp03 -->
    ...generated...
    <!-- /table -->

``--check`` renders into memory and fails if the README differs, so a README whose tables were
not regenerated after the experiments changed cannot pass ``make receipts``. The number checker
treats the generated regions like code: their digits come from the JSON, so there is nothing for
prose anchors to guard.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
EXPERIMENTS = ROOT / "docs" / "experiments"
BLOCK = re.compile(r"(<!-- table:(\w+) -->\n)(.*?)(<!-- /table -->)", re.S)
KINDS = ("single", "cross_sentence", "cross_paragraph", "cross_page", "table")
LABELS = {
    "fixed": "fixed windows",
    "recursive": "recursive (paragraph, line, sentence, word)",
    "sentence_window": "sentence packing",
    "page_aware": "page-aware fixed windows",
    "paragraph": "paragraph packing",
}
ORDER = ("sentence_window", "fixed", "recursive", "paragraph", "page_aware")


def load(name: str) -> dict:
    return json.loads((EXPERIMENTS / f"{name}.json").read_text(encoding="utf-8"))


def md_table(headers: list[str], rows: list[list[object]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def exp03() -> str:
    data = load("exp03_strategy_compare")
    by = {r["strategy"]: r for r in data["results"]}
    best = min(by.values(), key=lambda r: (r["orphaned"] + r["broken"], r["strategy"]))
    rows = []
    for s in ORDER:
        r = by[s]
        orphaned = f"**{r['orphaned']}**" if r is best else str(r["orphaned"])
        rows.append(
            [LABELS[s], r["chunk_count"], orphaned] + [r["by_kind"][k]["orphaned"] for k in KINDS]
        )
    return md_table(
        [
            "strategy",
            "chunks",
            "orphaned",
            "single",
            "cross-sentence",
            "cross-paragraph",
            "cross-page",
            "table",
        ],
        rows,
    )


def exp01() -> str:
    data = load("exp01_size_sweep")
    cols = ("fixed", "recursive", "sentence_window", "page_aware", "paragraph")
    rows = []
    for size in data["sizes"]:
        at = {r["strategy"]: r for r in data["results"] if r["size"] == size}
        rows.append([size] + [at[s]["orphaned"] for s in cols])
    return md_table(
        ["size (tokens)", "fixed", "recursive", "sentence packing", "page-aware", "paragraph"], rows
    )


def exp02() -> str:
    data = load("exp02_overlap_sweep")
    rows = [
        [
            r["strategy"],
            r["overlap"],
            r["chunk_count"],
            r["chunk_growth_ratio"],
            r["orphaned"],
            r["recovered"],
        ]
        for r in data["results"]
    ]
    return md_table(["strategy", "overlap", "chunks", "growth", "orphaned", "recovered"], rows)


def exp04() -> str:
    data = load("exp04_extraction_loss")
    what = {
        "raw": "content stream order, the library default",
        "sorted": "`sort=True`, the fix most tutorials recommend",
        "blocks": "text blocks clustered into columns by horizontal position",
    }
    rows = []
    for r in data["results"]:
        mode = r["extraction_mode"]
        rev = r["by_layout"]["two_column_reversed"]
        orphaned = f"{r['orphaned']}, of which {rev['orphaned']} on the reversed-stream documents"
        rows.append([f"`{mode}`", what[mode], r["broken"], orphaned])
    return md_table(
        [
            "extraction order",
            "what it is",
            "facts broken before chunking",
            "facts orphaned by the chunker",
        ],
        rows,
    )


RENDERERS = {"exp01": exp01, "exp02": exp02, "exp03": exp03, "exp04": exp04}


def render(text: str) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(2)
        if name not in RENDERERS:
            sys.exit(f"README table marker {name!r} has no renderer")
        return m.group(1) + RENDERERS[name]() + m.group(4)

    out, n = BLOCK.subn(sub, text)
    if n != len(RENDERERS):
        sys.exit(f"README has {n} table blocks, expected {len(RENDERERS)}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if the README tables are stale")
    args = parser.parse_args()
    current = README.read_text(encoding="utf-8")
    fresh = render(current)
    if args.check:
        if fresh != current:
            print("README tables are stale; run tools/render_tables.py and commit")
            return 1
        print("README tables match the experiment JSON")
        return 0
    README.write_text(fresh, encoding="utf-8")
    print("README tables rendered from docs/experiments")
    return 0


if __name__ == "__main__":
    sys.exit(main())
