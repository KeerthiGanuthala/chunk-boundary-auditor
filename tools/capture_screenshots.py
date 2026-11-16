"""Screenshot the real HTML report, framed by heading, with the badge's visibility checked.

Builds the report if it is missing (a screenshot of a stale report is worse than none), opens it in
Chromium through Playwright, and clips each shot from a named h2 to the next named h2. Framing by
heading rather than by pixel offset means a longer paragraph moves the frame instead of cropping
it, and a missing heading fails the run because the report has changed shape.

Before saving, the tool reads back the computed style of the verdict badge and fails if the badge
has no size or its text colour equals its background: a badge rendered green on green passed every
other check in an earlier project, and a screenshot tool is the only thing that can see pixels.

Writes docs/assets/report-<section>.png and docs/assets/screenshots.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "audit.html"
OUT_DIR = ROOT / "docs" / "assets"
MANIFEST = OUT_DIR / "screenshots.json"
SECTIONS = [("verdict", "strategies"), ("strategies", "lost")]
WIDTH = 1120


def build_report() -> None:
    REPORT.parent.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, "-m", "chunkaudit", "audit", "--html", str(REPORT), "--no-verdict"],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )


def main() -> int:
    from playwright.sync_api import sync_playwright

    build_report()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": 800})
        page.goto(REPORT.resolve().as_uri())
        badge = page.evaluate(
            """() => {
              const b = document.querySelector('.badge');
              if (!b) return null;
              const s = getComputedStyle(b);
              return {text: b.textContent, colour: s.color, background: s.backgroundColor,
                      visible: b.offsetWidth > 0 && b.offsetHeight > 0};
            }"""
        )
        if not badge or not badge["visible"] or badge["colour"] == badge["background"]:
            browser.close()
            sys.exit(f"verdict badge is missing or invisible: {badge}")
        for start, end in SECTIONS:
            offsets = page.evaluate(
                """([a, b]) => {
                  const top = document.getElementById(a);
                  const next = document.getElementById(b);
                  if (!top || !next) return null;
                  const y0 = top.getBoundingClientRect().top + window.scrollY;
                  const y1 = next.getBoundingClientRect().top + window.scrollY;
                  return {y0: y0 - 8, y1: y1 - 16};
                }""",
                [start, end],
            )
            if not offsets:
                browser.close()
                sys.exit(f"report no longer has headings {start!r} and {end!r}")
            path = OUT_DIR / f"report-{start}.png"
            page.screenshot(
                path=str(path),
                full_page=True,
                clip={
                    "x": 0,
                    "y": offsets["y0"],
                    "width": WIDTH,
                    "height": offsets["y1"] - offsets["y0"],
                },
            )
            entries.append(
                {
                    "image": str(path.relative_to(ROOT)),
                    "report": str(REPORT.relative_to(ROOT)),
                    "from_heading": start,
                    "to_heading": end,
                }
            )
            print(f"wrote {path.relative_to(ROOT)}")
        browser.close()
    MANIFEST.write_text(
        json.dumps({"badge": badge, "screenshots": entries}, indent=1) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
