"""Render the README's architecture diagram from its Mermaid source to a committed SVG.

GitHub's own Mermaid renderer fails intermittently inside its lazily loaded display code, with
nothing to fix in the source, so the diagram is rendered here with the mermaid library through
Playwright and committed as docs/assets/architecture.svg, embedded in the README with an img tag.
The source stays in the README in a fence labelled ``mermaid-source`` so nothing tries to render it
live.

Three rules from past builds: htmlLabels off, so the SVG is well-formed XML and loads as an image;
explicit width and height copied from the viewBox, so a browser has an aspect ratio; and a painted
light background, so labels stay legible in a dark theme.

Requires: ``pip install playwright && playwright install chromium`` and a local copy of
mermaid.min.js, found via --mermaid or the MERMAID_JS environment variable, or installed with
``npm install mermaid`` next to this repository. No network is used at render time.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
OUT = ROOT / "docs" / "assets" / "architecture.svg"
MANIFEST = ROOT / "docs" / "assets" / "architecture.json"
FENCE = re.compile(r"```mermaid-source\n(.*?)```", re.S)


def find_mermaid(explicit: str | None) -> Path:
    candidates = [explicit, os.environ.get("MERMAID_JS")]
    candidates += [
        str(ROOT / "node_modules" / "mermaid" / "dist" / "mermaid.min.js"),
        str(ROOT.parent / "node_modules" / "mermaid" / "dist" / "mermaid.min.js"),
        "/tmp/mm/node_modules/mermaid/dist/mermaid.min.js",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return Path(c)
    sys.exit("mermaid.min.js not found; pass --mermaid or set MERMAID_JS")


def render(source: str, mermaid_js: Path) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.set_content("<!DOCTYPE html><html><body><div id='out'></div></body></html>")
        page.add_script_tag(path=str(mermaid_js))
        svg = page.evaluate(
            """async (src) => {
                mermaid.initialize({ startOnLoad: false, theme: 'neutral',
                    flowchart: { htmlLabels: false, useMaxWidth: false },
                    themeVariables: { fontFamily: 'Helvetica, Arial, sans-serif',
                                      fontSize: '14px' } });
                const { svg } = await mermaid.render('arch', src);
                return svg;
            }""",
            source,
        )
        browser.close()
    return svg


def finish(svg: str) -> str:
    """Explicit dimensions from the viewBox and an opaque background rectangle."""
    m = re.search(r'viewBox="([\d.\-]+) ([\d.\-]+) ([\d.\-]+) ([\d.\-]+)"', svg)
    if not m:
        sys.exit("rendered SVG has no viewBox")
    x, y, w, h = (float(v) for v in m.groups())
    svg = re.sub(r'\swidth="[^"]*"', "", svg, count=1)
    svg = re.sub(r'\sheight="[^"]*"', "", svg, count=1)
    svg = re.sub(r'\sstyle="max-width:[^"]*"', "", svg, count=1)
    svg = svg.replace("<svg ", f'<svg width="{w:.0f}" height="{h:.0f}" ', 1)
    bg = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#ffffff"/>'
    svg = re.sub(r"(<svg[^>]*>)", r"\1" + bg, svg, count=1)
    ET.fromstring(svg)
    return svg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--mermaid", default=None, help="path to mermaid.min.js")
    args = parser.parse_args()
    text = README.read_text(encoding="utf-8")
    m = FENCE.search(text)
    if not m:
        sys.exit("README has no ```mermaid-source fence")
    source = m.group(1)
    svg = finish(render(source, find_mermaid(args.mermaid)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(svg, encoding="utf-8")
    MANIFEST.write_text(
        json.dumps(
            {
                "source": "README.md ```mermaid-source fence",
                "output": str(OUT.relative_to(ROOT)),
                "bytes": len(svg.encode()),
                "htmlLabels": False,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT.relative_to(ROOT)} ({len(svg.encode())} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
