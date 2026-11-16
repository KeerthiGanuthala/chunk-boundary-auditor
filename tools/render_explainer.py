"""Render the animated explainer video from the measured numbers.

An HTML animation with eight scenes is filled from docs/metrics.json and the experiment JSON, so
every figure shown on screen is the one the receipts check. Playwright records the page; ffmpeg
transcodes it to an H.264 MP4 at 1280x720. No external asset, no font download, no narration
track: captions carry the argument, and a voice track can be laid over the MP4 later without
changing a frame.

Writes docs/video/explainer.mp4 and docs/video/explainer.json (scene list with timings).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "video"
METRICS = ROOT / "docs" / "metrics.json"
EXPERIMENTS = ROOT / "docs" / "experiments"
W, H = 1280, 720

SCENES = [
    ("title", 5.0),
    ("problem", 13.0),
    ("method", 12.0),
    ("extraction", 13.0),
    ("strategies", 12.0),
    ("overlap", 13.0),
    ("receipts", 8.0),
    ("outro", 5.0),
]


def load() -> dict:
    m = json.loads(METRICS.read_text(encoding="utf-8"))["metrics"]
    e3 = json.loads((EXPERIMENTS / "exp03_strategy_compare.json").read_text())
    e2 = json.loads((EXPERIMENTS / "exp02_overlap_sweep.json").read_text())
    labels = {
        "sentence_window": "sentence packing",
        "fixed": "fixed windows",
        "recursive": "recursive",
        "paragraph": "paragraph packing",
        "page_aware": "page-aware",
    }
    strategies = sorted(e3["results"], key=lambda r: r["orphaned"])
    bars = [{"label": labels[r["strategy"]], "value": r["orphaned"]} for r in strategies]
    rec = [
        {"overlap": r["overlap"], "orphaned": r["orphaned"]}
        for r in e2["results"]
        if r["strategy"] == "recursive"
    ]
    return {"m": m, "bars": bars, "recursive": rec}


def page_html(data: dict) -> str:
    m = data["m"]
    scenes_json = json.dumps([{"id": s, "seconds": t} for s, t in SCENES])
    bars_json = json.dumps(data["bars"])
    rec_json = json.dumps(data["recursive"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
html,body {{ margin:0; background:#0b1118; color:#e6edf3; width:{W}px; height:{H}px; overflow:hidden;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
.scene {{ position:absolute; inset:0; opacity:0; transition: opacity .6s ease; padding:64px 80px;
  box-sizing:border-box; }}
.scene.on {{ opacity:1; }}
h1 {{ font-size:56px; margin:0 0 12px 0; letter-spacing:-1px; }}
h2 {{ font-size:34px; margin:0 0 18px 0; }}
.cap {{ font-size:24px; color:#9fb0c3; max-width:1000px; line-height:1.35; }}
.big {{ font-size:84px; font-weight:700; color:#ffb454; font-family: ui-monospace, Menlo, monospace; }}
.mono {{ font-family: ui-monospace, Menlo, Consolas, monospace; }}
.chunk {{ position:absolute; border:2px solid #2e3f52; background:#16202b; border-radius:8px;
  padding:14px 16px; font-size:19px; color:#d7dee6; width:300px; height:96px; box-sizing:border-box; }}
.chunk .lbl {{ font-size:13px; color:#7d8fa3; font-family:ui-monospace, Menlo, monospace; display:block; margin-bottom:6px; }}
.cut {{ position:absolute; width:4px; background:#ff6b6b; opacity:0; }}
.arc {{ position:absolute; opacity:0; }}
.pipe {{ display:flex; gap:12px; align-items:center; margin-top:40px; }}
.node {{ background:#16202b; border:2px solid #2e3f52; border-radius:10px; padding:14px 12px; font-size:19px;
  opacity:0; transform:translateY(12px); transition: all .5s ease; min-width:120px; max-width:190px; text-align:center; }}
.node small {{ display:block; color:#7d8fa3; font-size:14px; margin-top:4px; }}
.node.on {{ opacity:1; transform:none; }}
.arrow {{ color:#7d8fa3; font-size:28px; opacity:0; transition: opacity .4s; }} .arrow.on {{ opacity:1; }}
.col {{ position:absolute; top:220px; width:380px; font-size:17px; line-height:1.5; color:#d7dee6; }}
.col div {{ white-space:nowrap; }}
.interleaved {{ position:absolute; top:220px; left:600px; width:620px; font-size:17px; line-height:1.5;
  color:#d7dee6; }}
.interleaved div {{ opacity:0; transition: opacity .25s; white-space:nowrap; }}
.interleaved div.on {{ opacity:1; }}
.bar {{ display:flex; align-items:center; gap:16px; margin:14px 0; font-size:22px; }}
.bar .name {{ width:260px; text-align:right; color:#9fb0c3; }}
.bar .fill {{ height:34px; background:#3b82f6; border-radius:6px; width:0; transition: width 1.1s ease; }}
.bar .fill.best {{ background:#ffb454; }}
.bar .val {{ font-family: ui-monospace, Menlo, monospace; color:#e6edf3; }}
svg text {{ font-family: ui-monospace, Menlo, monospace; fill:#9fb0c3; font-size:16px; }}
.rec {{ margin-top:12px; font-size:22px; color:#9fb0c3; }}
.receipt {{ font-size:30px; margin:12px 0; opacity:0; transform:translateX(-10px); transition: all .5s; }}
.receipt.on {{ opacity:1; transform:none; }}
.receipt b {{ color:#ffb454; font-family: ui-monospace, Menlo, monospace; }}
.footer {{ position:absolute; bottom:28px; left:80px; font-size:16px; color:#56657a; }}
</style></head><body>

<div class="scene" id="title">
  <div style="margin-top:170px">
  <h1>chunk-boundary-auditor</h1>
  <div class="cap" style="font-size:30px">Which facts did your chunker make unretrievable?<br>Measured, not assumed.</div>
  </div>
</div>

<div class="scene" id="problem">
  <h2>A chunker's output cannot show the fact it split</h2>
  <div class="cap">The fact is in the document. After chunking, it is in no chunk. You can read every chunk and never find the gap.</div>
  <div class="chunk" style="left:80px; top:340px"><span class="lbl">chunk 0</span>The Varlen K2 unit was commissioned in 1987.</div>
  <div class="chunk" style="left:420px; top:340px"><span class="lbl">chunk 1</span>Its rated output is 412 MW.</div>
  <div class="chunk" style="left:760px; top:340px"><span class="lbl">chunk 2</span>Operators replaced the inlet filters in spring.</div>
  <svg class="arc" id="arc" style="left:80px; top:260px" width="700" height="100">
    <path d="M 150 80 C 220 -10, 420 -10, 490 80" fill="none" stroke="#ffb454" stroke-width="4"/>
    <text x="500" y="40" style="fill:#ffb454; font-size:18px">one fact, two sentences, two chunks</text>
  </svg>
  <div class="cut" id="cut" style="left:400px; top:320px; height:140px"></div>
  <div class="cap" id="problem2" style="position:absolute; top:490px; opacity:0; transition: opacity .6s">A retriever returns chunks. Neither chunk answers "what is the rated output of the Varlen K2?"</div>
</div>

<div class="scene" id="method">
  <h2>So plant the facts on purpose, and count the ones no chunk holds</h2>
  <div class="cap">{m["facts_total"]} facts planted in {m["documents_total"]} seeded PDFs, each recorded with the exact spans a reader needs. Five kinds: one sentence, across a sentence, a paragraph, a page, and in a table.</div>
  <div class="pipe">
    <div class="node">seed<small>one integer</small></div><div class="arrow">&#8594;</div>
    <div class="node">PDFs<small>single, two-column, reversed stream</small></div><div class="arrow">&#8594;</div>
    <div class="node">extract<small>raw, sorted, blocks</small></div><div class="arrow">&#8594;</div>
    <div class="node">chunk<small>five strategies</small></div><div class="arrow">&#8594;</div>
    <div class="node">audit<small>contained, orphaned, broken</small></div>
  </div>
  <div class="cap" style="margin-top:46px">Offline, deterministic, no model, no key. One command reproduces every number.</div>
</div>

<div class="scene" id="extraction">
  <h2>Extraction loses facts before the chunker can</h2>
  <div class="cap">On a two-column page, PyMuPDF's sort=True orders lines by position across both columns. Every sentence that wraps gets another column's line spliced into it.</div>
  <div class="cap" style="position:absolute; top:190px; left:80px; font-size:15px">the page, as laid out</div>
  <div class="cap" style="position:absolute; top:190px; left:600px; font-size:15px">what sort=True hands the chunker</div>
  <div class="col" style="left:80px" id="colL">
    <div>The Varlen K2 unit was</div><div>commissioned at the Ostbro</div><div>site in 1987. Its rated</div><div>output is 412 MW.</div>
  </div>
  <div class="col" style="left:340px" id="colR" >
    <div>Noise surveys were</div><div>repeated at 18 points</div><div>along the fence line.</div><div>The crew logged 29 hours.</div>
  </div>
  <div class="interleaved" id="inter">
    <div>The Varlen K2 unit was Noise surveys were</div>
    <div>commissioned at the Ostbro repeated at 18 points</div>
    <div>site in 1987. Its rated along the fence line.</div>
    <div>output is 412 MW. The crew logged 29 hours.</div>
  </div>
  <div style="position:absolute; top:400px; left:80px">
    <div class="big" id="brokenCounter">0</div>
    <div class="cap">of {m["facts_total"]} facts broken before any chunker runs ({m["sorted_broken_pct"]} percent). Block clustering breaks {m["blocks_broken"]}.</div>
  </div>
</div>

<div class="scene" id="strategies">
  <h2>Five strategies at {m["policy_size"]} tokens: facts no chunk holds</h2>
  <div id="bars"></div>
  <div class="cap" style="margin-top:20px">The best still orphans {m["sentence_window_orphaned"]}. Page-aware loses all {m["page_aware_cross_page_orphaned"]} cross-page facts by construction.</div>
</div>

<div class="scene" id="overlap">
  <h2>Overlap is the usual fix. It made the recursive splitter worse first.</h2>
  <svg id="chart" width="1100" height="330"></svg>
  <div class="rec">32 tokens of overlap: <b style="color:#ff6b6b">{m["recursive_overlap_32_extra_lost"]} more fact lost</b> than no overlap at all. 64 tokens: {m["recursive_overlap_64_extra_lost"]} more. Zero only at {m["recursive_overlap_to_zero"]} tokens, with the index {m["recursive_overlap_zero_growth_pct"]} percent larger.</div>
</div>

<div class="scene" id="receipts">
  <h2>Every number is re-measured, and the prose is checked against it</h2>
  <div class="receipt"><b>{m["tests_total"]}</b> tests, <b>{m["coverage_line_pct"]}%</b> line coverage, three Pythons in CI</div>
  <div class="receipt"><b>{m["experiment_count"]}</b> experiments write JSON; tables and banner are rendered from it</div>
  <div class="receipt">a checker matches <b>anchor phrases</b>, not digits: a stale sentence fails the build</div>
  <div class="receipt">a fresh clone, no network, <b>make verify</b></div>
</div>

<div class="scene" id="outro">
  <div style="margin-top:200px">
  <h1 style="font-size:44px">github.com/KeerthiGanuthala/chunk-boundary-auditor</h1>
  <div class="cap">Measure the loss before you blame the model.</div>
  </div>
</div>

<div class="footer">chunk-boundary-auditor explainer. All figures from docs/metrics.json.</div>

<script>
const scenes = {scenes_json};
const bars = {bars_json};
const rec = {rec_json};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const q = s => document.querySelector(s);
function show(id) {{ document.querySelectorAll('.scene').forEach(s => s.classList.remove('on')); q('#' + id).classList.add('on'); }}

async function problem() {{
  await sleep(2500); q('#arc').style.transition = 'opacity .6s'; q('#arc').style.opacity = 1;
  await sleep(2500); q('#cut').style.transition = 'opacity .4s'; q('#cut').style.opacity = 1;
  await sleep(2000); q('#problem2').style.opacity = 1;
}}
async function method() {{
  await sleep(2500);
  const nodes = document.querySelectorAll('#method .node, #method .arrow');
  for (const n of nodes) {{ n.classList.add('on'); await sleep(420); }}
}}
async function extraction() {{
  await sleep(3200);
  const lines = document.querySelectorAll('#inter div');
  for (const l of lines) {{ l.classList.add('on'); await sleep(500); }}
  await sleep(600);
  const target = {m["sorted_broken"]}; const el = q('#brokenCounter');
  const start = performance.now(); const dur = 2200;
  while (true) {{ const t = Math.min(1, (performance.now() - start) / dur); el.textContent = Math.round(target * (1 - Math.pow(1 - t, 3))); if (t >= 1) break; await sleep(30); }}
}}
async function strategies() {{
  const host = q('#bars'); const max = Math.max(...bars.map(b => b.value));
  bars.forEach((b, i) => {{
    const row = document.createElement('div'); row.className = 'bar';
    row.innerHTML = '<div class="name">' + b.label + '</div><div class="fill' + (i === 0 ? ' best' : '') + '"></div><div class="val">' + b.value + '</div>';
    host.appendChild(row);
  }});
  await sleep(1200);
  const fills = document.querySelectorAll('#bars .fill');
  bars.forEach((b, i) => {{ setTimeout(() => {{ fills[i].style.width = (60 + 640 * b.value / max) + 'px'; }}, i * 500); }});
}}
async function overlap() {{
  const svg = q('#chart'); const left = 90, right = 1000, top = 30, bottom = 280;
  const xs = rec.map(r => r.overlap); const maxX = Math.max(...xs); const maxY = Math.max(...rec.map(r => r.orphaned)) + 4;
  const X = v => left + (right - left) * v / maxX; const Y = v => bottom - (bottom - top) * v / maxY;
  let s = '<line x1="' + left + '" y1="' + bottom + '" x2="' + right + '" y2="' + bottom + '" stroke="#2e3f52" stroke-width="2"/>';
  s += '<line x1="' + left + '" y1="' + top + '" x2="' + left + '" y2="' + bottom + '" stroke="#2e3f52" stroke-width="2"/>';
  s += '<text x="' + (left + 380) + '" y="' + (bottom + 44) + '">overlap in tokens</text>';
  s += '<text x="8" y="' + (top + 10) + '">facts orphaned</text>';
  xs.forEach(x => {{ s += '<text x="' + (X(x) - 10) + '" y="' + (bottom + 20) + '">' + x + '</text>'; }});
  const pts = rec.map(r => X(r.overlap) + ',' + Y(r.orphaned)).join(' ');
  s += '<polyline id="line" points="' + pts + '" fill="none" stroke="#3b82f6" stroke-width="4" stroke-dasharray="2000" stroke-dashoffset="2000"/>';
  rec.forEach((r, i) => {{ const bad = i > 0 && r.orphaned > rec[0].orphaned; s += '<circle id="pt' + i + '" cx="' + X(r.overlap) + '" cy="' + Y(r.orphaned) + '" r="9" fill="' + (bad ? '#ff6b6b' : '#3b82f6') + '" opacity="0"/>'; s += '<text id="tx' + i + '" x="' + (X(r.overlap) + 14) + '" y="' + (Y(r.orphaned) - 12) + '" style="fill:' + (bad ? '#ff6b6b' : '#e6edf3') + '; font-size:20px" opacity="0">' + r.orphaned + '</text>'; }});
  svg.innerHTML = s;
  await sleep(1800);
  const line = q('#line'); line.style.transition = 'stroke-dashoffset 3s ease'; line.style.strokeDashoffset = 0;
  for (let i = 0; i < rec.length; i++) {{ await sleep(620); q('#pt' + i).setAttribute('opacity', 1); q('#tx' + i).setAttribute('opacity', 1); }}
}}
async function receipts() {{
  await sleep(1200);
  for (const r of document.querySelectorAll('#receipts .receipt')) {{ r.classList.add('on'); await sleep(1300); }}
}}
const actions = {{ problem, method, extraction, strategies, overlap, receipts }};
async function run() {{
  await sleep(400);
  for (const s of scenes) {{
    show(s.id);
    const started = performance.now();
    if (actions[s.id]) actions[s.id]();
    const remaining = s.seconds * 1000 - (performance.now() - started);
    await sleep(Math.max(0, remaining));
  }}
  await sleep(300);
  document.title = 'done';
}}
run();
</script></body></html>
"""


def main() -> int:
    from playwright.sync_api import sync_playwright

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = load()
    page_path = OUT_DIR / "explainer.html"
    page_path.write_text(page_html(data), encoding="utf-8")
    frames = OUT_DIR / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(frames),
            record_video_size={"width": W, "height": H},
        )
        page = context.new_page()
        page.goto(page_path.resolve().as_uri())
        page.wait_for_function("document.title === 'done'", timeout=240_000)
        video = page.video.path()
        context.close()
        browser.close()
    webm = OUT_DIR / "explainer.webm"
    shutil.move(video, webm)
    shutil.rmtree(frames, ignore_errors=True)
    mp4 = OUT_DIR / "explainer.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(webm),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(mp4),
        ],
        check=True,
    )
    webm.unlink()
    page_path.unlink()
    (OUT_DIR / "explainer.json").write_text(
        json.dumps(
            {
                "note": "animated explainer rendered from docs/metrics.json; captions only, no narration",
                "resolution": [W, H],
                "scenes": [{"id": s, "seconds": t} for s, t in SCENES],
                "total_seconds": sum(t for _, t in SCENES),
                "mp4_bytes": mp4.stat().st_size,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {mp4.relative_to(ROOT)} ({mp4.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
