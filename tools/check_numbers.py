"""Fail the build when a document quotes a figure the code no longer produces.

Reads docs/metrics.json (written by collect_metrics.py) and every checked document, then:

1. For every metric, every anchor phrase is turned into a pattern with a number slot. Any
   occurrence of that phrase in a checked document whose number differs from the measured value
   is STALE and fails the build. Phrases, not digits: "17 facts" going stale is caught even
   though "17" still appears somewhere as a chunk count.
2. A metric that no checked document quotes at all is reported as unused. That is not a failure,
   but a metric below six that is unused is reported as a receipts gap, because a small number
   is too likely to appear by coincidence for a digit match to prove anything.
3. The reverse check: every number in the README outside fenced code, inline code, HTML tags and
   link targets must equal some measured value or be on the allowed list. A number nothing
   re-measures is a number that will go stale silently.

Exit code 1 on any stale phrase, unanchored README number or missing checked document.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "docs" / "metrics.json"

NUMBER = r"(-?\d+(?:\.\d+)?)"


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\]\([^)]*\)", "]()", text)
    return text


def anchor_pattern(anchor: str) -> re.Pattern:
    parts = [re.escape(p) for p in anchor.split("{}")]
    body = NUMBER.join(parts)
    body = body.replace(r"\ ", r"\s+")
    return re.compile(body, flags=re.I)


def same(a: str, b: float | int | str) -> bool:
    try:
        return float(a) == float(b)
    except ValueError:
        return a == str(b)


def main() -> int:
    if not METRICS.exists():
        print(f"missing {METRICS}; run tools/collect_metrics.py first")
        return 1
    payload = json.loads(METRICS.read_text(encoding="utf-8"))
    metrics: dict = payload["metrics"]
    anchors: dict[str, list[str]] = payload["anchors"]
    allowed = set(payload.get("allowed_unanchored", []))
    docs: dict[str, str] = {}
    missing = 0
    for rel in payload["checked_documents"]:
        path = ROOT / rel
        if not path.exists():
            print(f"MISSING  {rel}")
            missing += 1
            continue
        docs[rel] = strip_code(path.read_text(encoding="utf-8"))

    stale = 0
    unused: list[str] = []
    gaps: list[str] = []
    for key, value in metrics.items():
        if isinstance(value, str):
            continue
        phrases = anchors.get(key, [])
        seen_correct = False
        for anchor in phrases:
            pat = anchor_pattern(anchor)
            for rel, text in docs.items():
                for m in pat.finditer(text):
                    if same(m.group(1), value):
                        seen_correct = True
                    else:
                        stale += 1
                        print(f"STALE    {rel}: '{m.group(0)}' but {key} = {value}")
        if not seen_correct:
            unused.append(key)
            if not phrases or (isinstance(value, int | float) and abs(value) < 6):
                gaps.append(key)

    numeric_values = {float(v) for v in metrics.values() if not isinstance(v, str)}
    readme = docs.get("README.md", "")
    unanchored: list[str] = []
    for m in re.finditer(r"(?<![\w.-])-?\d+(?:\.\d+)?(?![\w.-])", readme):
        token = m.group(0)
        if token in allowed or float(token) in numeric_values:
            continue
        line = readme.count("\n", 0, m.start()) + 1
        unanchored.append(f"{token} (README line {line})")

    for key in unused:
        print(f"UNUSED   {key} = {metrics[key]} is quoted by no checked document")
    for key in gaps:
        print(
            f"GAP      {key} = {metrics[key]} is small and unanchored; a digit match proves nothing"
        )
    for item in unanchored:
        print(f"LOOSE    README number {item} matches no measured value")

    checked = len([k for k, v in metrics.items() if not isinstance(v, str)])
    print(
        f"checked {checked} metrics across {len(docs)} documents: "
        f"{stale} stale, {len(unused)} unused, {len(unanchored)} loose"
    )
    return 1 if stale or unanchored or missing else 0


if __name__ == "__main__":
    sys.exit(main())
