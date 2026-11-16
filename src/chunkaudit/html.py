"""A self-contained HTML report of an audit run, for reading and for the evidence screenshots.

One file, no external assets, headings that the screenshot tool frames by name. The verdict badge
is a plain element with a dedicated class, and a test asserts that every class used here has a
rule in the stylesheet, because a badge rendered green on green is invisible to every check in
the pipeline except a screenshot.
"""

from __future__ import annotations

import html as _html
from pathlib import Path

from .audit import AuditResult
from .corpus import FACT_KINDS

STYLE = """
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
       margin: 32px auto; max-width: 1060px; color: #1b1f23; background: #ffffff;
       line-height: 1.45; }
h1 { font-size: 24px; margin: 0 0 4px 0; }
h2 { font-size: 18px; margin: 28px 0 8px 0; border-bottom: 1px solid #d0d7de; padding-bottom: 4px; }
p.sub { color: #57606a; margin: 0 0 16px 0; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border: 1px solid #d0d7de; padding: 5px 8px; text-align: right; }
th:first-child, td:first-child { text-align: left; }
th { background: #f6f8fa; }
tr.best td { background: #eef9f0; }
.badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-weight: 600;
         font-size: 14px; color: #ffffff; }
.badge-pass { background: #1a7f37; }
.badge-fail { background: #cf222e; }
.reasons { margin: 8px 0 0 0; padding-left: 20px; }
.lost { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px;
        color: #57606a; }
"""

CLASSES_USED = ("sub", "best", "badge", "badge-pass", "badge-fail", "reasons", "lost")


def _esc(value: object) -> str:
    return _html.escape(str(value))


def render(results: list[AuditResult], code: int, reasons: list[str], policy_path: str) -> str:
    if not results:
        raise ValueError("cannot render a report with no results")
    best = min(results, key=lambda r: (r.orphaned + r.broken, r.strategy))
    badge_class = "badge badge-pass" if code == 0 else "badge badge-fail"
    badge_text = "PASS" if code == 0 else "FAIL"
    size, mode, total = results[0].size, results[0].extraction_mode, results[0].total
    rows = []
    for r in results:
        cls = ' class="best"' if r is best else ""
        kind_cells = "".join(
            f"<td>{r.by_kind[k]['orphaned']}+{r.by_kind[k]['broken']}</td>" for k in FACT_KINDS
        )
        rows.append(
            f"<tr{cls}><td>{_esc(r.strategy)}</td><td>{r.chunk_count}</td>"
            f"<td>{r.mean_chunk_tokens:.0f}</td><td>{r.contained}</td><td>{r.orphaned}</td>"
            f"<td>{r.broken}</td>{kind_cells}</tr>"
        )
    kind_heads = "".join(f"<th>{k}</th>" for k in FACT_KINDS)
    reason_items = "".join(f"<li>{_esc(x)}</li>" for x in reasons)
    lost = sorted({o.fact.fact_id for r in results for o in r.outcomes if o.outcome != "contained"})
    lost_html = (
        '<p class="lost">' + ", ".join(_esc(x) for x in lost) + "</p>"
        if lost
        else "<p>No fact was lost by any strategy in this run.</p>"
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>chunk-boundary-auditor report</title>
<style>{STYLE}</style>
</head>
<body>
<h1>chunk-boundary-auditor</h1>
<p class="sub">{len(results)} strategies at {size} tokens, extraction mode {_esc(mode)},
{total} planted facts, policy {_esc(policy_path)}</p>

<h2 id="verdict">Verdict</h2>
<p><span class="{badge_class}">{badge_text}</span>
best strategy <strong>{_esc(best.strategy)}</strong> orphans {best.orphaned} of {total} facts
and extraction broke {best.broken}.</p>
<ul class="reasons">{reason_items}</ul>

<h2 id="strategies">Facts lost per strategy</h2>
<table>
<thead><tr><th>strategy</th><th>chunks</th><th>mean tokens</th><th>contained</th>
<th>orphaned</th><th>broken</th>{kind_heads}</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
<p class="sub">Per-kind cells read orphaned+broken. A fact is broken when extraction lost one of
its spans, so no chunking strategy could have contained it.</p>

<h2 id="lost">Facts lost by at least one strategy</h2>
{lost_html}
</body>
</html>
"""


def write_report(path: Path, *args) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(*args), encoding="utf-8")
