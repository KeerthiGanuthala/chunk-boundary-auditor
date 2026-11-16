"""Render the README banner from its template and the measured metrics.

The banner shows numbers, and a number nobody re-measures goes stale. So the committed SVG is
generated from tools/banner_template.svg with values from docs/metrics.json, and CI fails when the
committed banner differs from a fresh render. The animation lives inside the SVG (CSS keyframes in
an internal style block), uses no script and no external asset, has intrinsic dimensions and an
opaque background, and switches itself off under prefers-reduced-motion.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "tools" / "banner_template.svg"
OUT = ROOT / "docs" / "assets" / "banner.svg"
METRICS = ROOT / "docs" / "metrics.json"


def render() -> str:
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))["metrics"]
    text = TEMPLATE.read_text(encoding="utf-8")
    # Plain substitution rather than str.format: the template's CSS is full of braces.
    for key, value in metrics.items():
        text = text.replace("{" + key + "}", str(value))
    leftover = [t for t in ("{sentence_window_orphaned}", "{facts_total}") if t in text]
    if leftover:
        raise KeyError(f"unfilled placeholders in banner template: {leftover}")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if the committed banner differs")
    args = parser.parse_args()
    svg = render()
    ET.fromstring(svg)  # the file must be well-formed XML or GitHub shows a broken image
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != svg:
            print("docs/assets/banner.svg is stale; run tools/render_banner.py and commit")
            return 1
        print("banner matches the measured metrics")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(svg.encode())} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
