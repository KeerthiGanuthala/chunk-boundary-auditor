"""Record the terminal demo as a replay of captured output, not a screen recording.

Pipeline: run each command and capture its real stdout, stderr, exit code and wall time; write a
self-contained HTML player that types the command and reveals the captured output paced by that
command's measured duration; record the page with Playwright to webm; transcode with ffmpeg to an
MP4 and a two-pass palette GIF that autoplays inline on GitHub.

Every line of terminal text in the video is real captured output. The segments are ordered as the
argument, not as the feature list: the baseline table, then the extraction loss that exits 1,
then the war story, then overlap priced, then the receipts. A setup command warms the import so
the first segment does not pay for it.

Writes docs/video/demo.mp4, docs/video/demo.gif and docs/video/manifest.json.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "video"
PLAYER = OUT_DIR / "player.html"
WIDTH, HEIGHT = 1100, 460
MAX_SEGMENT_SECONDS = 6.0
MIN_SEGMENT_SECONDS = 1.6

COMMANDS = [
    ("chunkaudit audit", "the headline table: five strategies at the policy size"),
    ("chunkaudit audit --mode sorted --strategy sentence_window", "the extraction loss, exit 1"),
    (
        "chunkaudit explain D06-single-1 --strategy sentence_window --size 128",
        "one fact, span by span",
    ),
    ("python experiments/exp02_overlap_sweep.py", "overlap priced: recovered against growth"),
    ("python tools/check_numbers.py", "every published figure re-checked"),
]


def capture(cmd: str) -> dict:
    start = time.perf_counter()
    proc = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True)
    wall = time.perf_counter() - start
    out = proc.stdout + (("\n" + proc.stderr) if proc.stderr.strip() else "")
    return {
        "command": cmd,
        "exit_code": proc.returncode,
        "wall_seconds": round(wall, 3),
        "output": out,
    }


def player_html(segments: list[dict]) -> str:
    data = json.dumps(segments)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>chunk-boundary-auditor demo</title>
<style>
 body {{ margin:0; background:#0b1118; color:#d7dee6; font: 12.5px/1.4 ui-monospace, SFMono-Regular,
        Menlo, Consolas, monospace; }}
 #term {{ box-sizing:border-box; width:{WIDTH}px; height:{HEIGHT}px; padding:18px 22px;
         overflow:hidden; white-space:pre; }}
 .prompt {{ color:#7ee787; }} .cmd {{ color:#f0f3f6; }} .note {{ color:#7d8fa3; }}
 .exit0 {{ color:#7ee787; }} .exit1 {{ color:#ff7b72; }}
</style></head><body><div id="term"></div>
<script>
const segments = {data};
const term = document.getElementById('term');
const sleep = ms => new Promise(r => setTimeout(r, ms));
function esc(s) {{ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;'); }}
async function typeLine(cmd, note) {{
  term.innerHTML += '<span class="note"># ' + esc(note) + '</span>\\n';
  term.innerHTML += '<span class="prompt">$ </span><span class="cmd"></span>';
  const span = term.querySelectorAll('.cmd'); const el = span[span.length-1];
  for (const ch of cmd) {{ el.textContent += ch; await sleep(22); }}
  term.innerHTML += '\\n';
}}
async function run() {{
  await sleep(600);
  for (const seg of segments) {{
    term.innerHTML = '';
    await typeLine(seg.command, seg.note);
    const lines = seg.output.replace(/\\s+$/, '').split('\\n');
    const clamped = Math.min({MAX_SEGMENT_SECONDS}, seg.wall_seconds);
    const total = Math.max({MIN_SEGMENT_SECONDS}, clamped) * 1000;
    const per = Math.max(8, total / Math.max(lines.length, 1));
    for (const line of lines) {{ term.innerHTML += esc(line) + '\\n'; await sleep(per); }}
    const cls = seg.exit_code ? 'exit1' : 'exit0';
    term.innerHTML += '<span class="' + cls + '">exit ' + seg.exit_code + '</span>\\n';
    await sleep(1800);
  }}
  document.title = 'done';
}}
run();
</script></body></html>
"""


def main() -> int:
    from playwright.sync_api import sync_playwright

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found; the replay cannot be transcoded")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run("chunkaudit --version", shell=True, cwd=ROOT, capture_output=True)  # warm
    segments = []
    for cmd, note in COMMANDS:
        seg = capture(cmd)
        seg["note"] = note
        segments.append(seg)
        print(f"captured `{cmd}` exit {seg['exit_code']} in {seg['wall_seconds']}s")
    PLAYER.write_text(player_html(segments), encoding="utf-8")

    frames = OUT_DIR / "frames"
    if frames.exists():
        shutil.rmtree(frames)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            record_video_dir=str(frames),
            record_video_size={"width": WIDTH, "height": HEIGHT},
        )
        page = context.new_page()
        page.goto(PLAYER.resolve().as_uri())
        page.wait_for_function("document.title === 'done'", timeout=180_000)
        page.wait_for_timeout(500)
        video_path = page.video.path()
        context.close()
        browser.close()
    webm = OUT_DIR / "demo.webm"
    shutil.move(video_path, webm)
    shutil.rmtree(frames, ignore_errors=True)

    mp4 = OUT_DIR / "demo.mp4"
    gif = OUT_DIR / "demo.gif"
    palette = OUT_DIR / "palette.png"
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
            "-pix_fmt",
            "yuv420p",
            "-crf",
            "23",
            "-movflags",
            "+faststart",
            str(mp4),
        ],
        check=True,
    )
    scale = "fps=10,scale=900:-1:flags=lanczos"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(webm),
            "-vf",
            f"{scale},palettegen=max_colors=64",
            str(palette),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(webm),
            "-i",
            str(palette),
            "-lavfi",
            f"{scale} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5",
            str(gif),
        ],
        check=True,
    )
    palette.unlink()
    webm.unlink()
    PLAYER.unlink()
    manifest = {
        "note": "replay of captured stdout paced by measured wall time; not a screen recording",
        "viewport": [WIDTH, HEIGHT],
        "segments": [
            {k: v for k, v in s.items() if k != "output"}
            | {"output_lines": s["output"].count("\n")}
            for s in segments
        ],
        "files": {
            "mp4": str(mp4.relative_to(ROOT)),
            "gif": str(gif.relative_to(ROOT)),
            "gif_bytes": gif.stat().st_size,
            "mp4_bytes": mp4.stat().st_size,
        },
    }
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {gif.relative_to(ROOT)} ({gif.stat().st_size // 1024} KB) and {mp4.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
