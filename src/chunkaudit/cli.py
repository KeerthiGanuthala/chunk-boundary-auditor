"""Command line entry point: ``chunkaudit generate | audit | extract | explain``.

    generate   render the fixture from the policy seed; --check compares against the committed one
    audit      the headline table: every policy strategy at the policy size and extraction mode
    extract    print one document's extracted text in a given mode (for seeing the interleaving)
    explain    print every span of one fact and which chunks hold it, for one strategy

Exit codes are documented in ``report.py`` and in the README.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import __version__
from .audit import normalize
from .chunkers import STRATEGIES, chunk, effective_overlap
from .config import KNOWN_EXTRACTION_MODES, PolicyError, load_policy
from .extract import extract_dir, extract_pdf
from .fixture import (
    DEFAULT_FIXTURE_DIR,
    FixtureError,
    check_against_policy,
    load_facts,
    verify_manifest,
    write_fixture,
)
from .html import write_report
from .pipeline import run_audit
from .report import EXIT_ERROR, EXIT_FIXTURE, EXIT_OK, table, verdict, write_json


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chunkaudit", description=__doc__.split("\n")[0])
    p.add_argument("--version", action="version", version=f"chunkaudit {__version__}")
    p.add_argument("--policy", type=Path, default=None, help="policy TOML (default: config/)")
    p.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURE_DIR, help="fixture dir")
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="render the fixture from the policy seed")
    g.add_argument("--check", action="store_true", help="compare with committed fixture, no write")

    a = sub.add_parser("audit", help="audit every policy strategy and print the table")
    a.add_argument("--strategy", choices=sorted(STRATEGIES), action="append", default=None)
    a.add_argument("--size", type=int, default=None, help="chunk size in tokens")
    a.add_argument(
        "--overlap",
        type=int,
        default=None,
        help="token overlap for fixed, recursive and page_aware; sentence packing uses the "
        "policy's sentence_overlap and paragraph packing takes none",
    )
    a.add_argument("--mode", choices=KNOWN_EXTRACTION_MODES, default=None)
    a.add_argument("--json", type=Path, default=None, help="write results to this JSON file")
    a.add_argument("--html", type=Path, default=None, help="write a self-contained HTML report")
    a.add_argument("--no-verdict", action="store_true", help="always exit 0 after a run")

    e = sub.add_parser("extract", help="print extracted text for one document")
    e.add_argument("doc_id")
    e.add_argument("--mode", choices=KNOWN_EXTRACTION_MODES, default=None)
    e.add_argument("--page", type=int, default=None, help="1-based page, default all")

    x = sub.add_parser("explain", help="show where one fact's spans landed")
    x.add_argument("fact_id")
    x.add_argument("--strategy", choices=sorted(STRATEGIES), default="fixed")
    x.add_argument("--size", type=int, default=None)
    x.add_argument("--overlap", type=int, default=None)
    x.add_argument("--mode", choices=KNOWN_EXTRACTION_MODES, default=None)
    return p


def cmd_generate(args, policy) -> int:
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            problems = check_against_policy(policy, args.fixtures, Path(tmp))
        if problems:
            print("fixture differs from what the policy generates:")
            for pr in problems:
                print(f"  {pr}")
            print("run `chunkaudit generate` to refresh it, then commit the result")
            return EXIT_FIXTURE
        print(f"fixture matches policy seed {policy.fixture.seed}")
        return EXIT_OK
    manifest = write_fixture(policy, args.fixtures)
    print(f"wrote {len(manifest['files'])} files to {args.fixtures} (seed {policy.fixture.seed})")
    return EXIT_OK


def _guard_fixture(fixture_dir: Path) -> list[str]:
    return verify_manifest(fixture_dir)


def cmd_audit(args, policy) -> int:
    problems = _guard_fixture(args.fixtures)
    if problems:
        print("fixture does not match its manifest: " + "; ".join(problems))
        return EXIT_FIXTURE
    strategies = args.strategy or list(policy.chunking.strategies)
    size = args.size if args.size is not None else policy.chunking.default_size
    overlap = args.overlap if args.overlap is not None else policy.chunking.default_overlap
    mode = args.mode or policy.extraction_mode
    if size < 1 or overlap < 0 or overlap >= size:
        print(f"size must be >= 1 and 0 <= overlap < size (got size={size}, overlap={overlap})")
        return EXIT_ERROR
    extracted = extract_dir(args.fixtures, mode)
    results = [
        run_audit(
            strategy=s,
            size=size,
            overlap=effective_overlap(s, overlap, policy.chunking.sentence_overlap),
            extraction_mode=mode,
            fixture_dir=args.fixtures,
            extracted=extracted,
        )
        for s in strategies
    ]
    print(table(results))
    if args.json:
        write_json(results, args.json, {"policy": str(policy.source)})
    code, reasons = verdict(results, policy)
    if args.html:
        write_report(args.html, results, code, reasons, policy.source.name)
    if args.no_verdict:
        return EXIT_OK
    for r in reasons:
        print(f"FAIL: {r}")
    if code == EXIT_OK:
        print("PASS: thresholds hold for the best strategy")
    return code


def cmd_extract(args, policy) -> int:
    path = args.fixtures / f"{args.doc_id}.pdf"
    if not path.exists():
        print(f"no such document: {path}")
        return EXIT_ERROR
    ex = extract_pdf(path, args.mode or policy.extraction_mode)
    if args.page is None:
        print(ex.text)
    elif 1 <= args.page <= len(ex.pages):
        print(ex.pages[args.page - 1])
    else:
        print(f"page must be between 1 and {len(ex.pages)}")
        return EXIT_ERROR
    return EXIT_OK


def cmd_explain(args, policy) -> int:
    facts, _ = load_facts(args.fixtures)
    matches = [f for f in facts if f.fact_id == args.fact_id]
    if not matches:
        print(f"no such fact: {args.fact_id}")
        return EXIT_ERROR
    fact = matches[0]
    mode = args.mode or policy.extraction_mode
    size = args.size if args.size is not None else policy.chunking.default_size
    overlap = args.overlap if args.overlap is not None else policy.chunking.default_overlap
    overlap = effective_overlap(args.strategy, overlap, policy.chunking.sentence_overlap)
    ex = extract_pdf(args.fixtures / f"{fact.doc_id}.pdf", mode)
    chunks = chunk(args.strategy, ex.pages, size, overlap)
    full = normalize(ex.text)
    print(f"{fact.fact_id} [{fact.kind}] {fact.question} -> {fact.answer}")
    print(f"strategy={args.strategy} size={size} overlap={overlap} mode={mode}")
    for i, span in enumerate(fact.spans, start=1):
        ns = normalize(span)
        holders = [c.index for c in chunks if ns in normalize(c.text)]
        state = "in extraction" if ns in full else "LOST IN EXTRACTION"
        print(f"  span {i}: {state}; chunks {holders}: {span}")
    all_in = [c.index for c in chunks if all(normalize(s) in normalize(c.text) for s in fact.spans)]
    print(f"  chunks holding every span: {all_in or 'none'}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        policy = load_policy(args.policy)
    except PolicyError as exc:
        print(f"policy error: {exc}")
        return EXIT_ERROR
    try:
        if args.command == "generate":
            return cmd_generate(args, policy)
        if args.command == "audit":
            return cmd_audit(args, policy)
        if args.command == "extract":
            return cmd_extract(args, policy)
        return cmd_explain(args, policy)
    except FixtureError as exc:
        print(f"fixture error: {exc}")
        return EXIT_FIXTURE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
