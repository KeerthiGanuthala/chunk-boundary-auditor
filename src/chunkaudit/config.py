"""Policy loading and validation.

The policy file is the only place a threshold or a size is allowed to live. This module exists so
that every other module receives a validated, typed ``Policy`` rather than a dict, and so that a bad
policy is refused at the boundary with a message naming the key, instead of surfacing as a
``KeyError`` three modules later.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):  # pragma: no cover
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "policy.toml"

KNOWN_STRATEGIES = ("fixed", "recursive", "sentence_window", "page_aware", "paragraph")
KNOWN_EXTRACTION_MODES = ("raw", "sorted", "blocks")


class PolicyError(ValueError):
    """Raised when the policy file is missing, malformed, or asks for something impossible."""


@dataclass(frozen=True)
class FixturePolicy:
    seed: int
    documents: int
    pages_min: int
    pages_max: int
    two_column_share: float
    reversed_stream_share: float
    facts_single: int
    facts_cross_sentence: int
    facts_cross_paragraph: int
    facts_cross_page: int
    facts_table: int


@dataclass(frozen=True)
class ChunkingPolicy:
    default_size: int
    default_overlap: int
    strategies: tuple[str, ...]
    sentence_overlap: int


@dataclass(frozen=True)
class Thresholds:
    max_orphan_share: float
    max_extraction_loss_share: float


@dataclass(frozen=True)
class Policy:
    fixture: FixturePolicy
    extraction_mode: str
    chunking: ChunkingPolicy
    thresholds: Thresholds
    source: Path = field(default=DEFAULT_POLICY_PATH, compare=False)


def _require(section: dict, key: str, kind: type, where: str):
    if key not in section:
        raise PolicyError(f"policy [{where}] is missing '{key}'")
    value = section[key]
    if kind is float and isinstance(value, int) and not isinstance(value, bool):
        value = float(value)
    if not isinstance(value, kind) or isinstance(value, bool):
        raise PolicyError(f"policy [{where}].{key} must be {kind.__name__}, got {value!r}")
    return value


def load_policy(path: Path | str | None = None) -> Policy:
    """Read and validate a policy file. Raises ``PolicyError`` with the offending key named."""
    source = Path(path) if path is not None else DEFAULT_POLICY_PATH
    if not source.exists():
        raise PolicyError(f"policy file not found: {source}")
    try:
        raw = tomllib.loads(source.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(f"policy file is not valid TOML: {exc}") from exc

    for section in ("fixture", "extraction", "chunking", "thresholds"):
        if section not in raw or not isinstance(raw[section], dict):
            raise PolicyError(f"policy is missing the [{section}] table")

    fx = raw["fixture"]
    fixture = FixturePolicy(
        seed=_require(fx, "seed", int, "fixture"),
        documents=_require(fx, "documents", int, "fixture"),
        pages_min=_require(fx, "pages_min", int, "fixture"),
        pages_max=_require(fx, "pages_max", int, "fixture"),
        two_column_share=_require(fx, "two_column_share", float, "fixture"),
        reversed_stream_share=_require(fx, "reversed_stream_share", float, "fixture"),
        facts_single=_require(fx, "facts_single", int, "fixture"),
        facts_cross_sentence=_require(fx, "facts_cross_sentence", int, "fixture"),
        facts_cross_paragraph=_require(fx, "facts_cross_paragraph", int, "fixture"),
        facts_cross_page=_require(fx, "facts_cross_page", int, "fixture"),
        facts_table=_require(fx, "facts_table", int, "fixture"),
    )
    if fixture.documents < 1:
        raise PolicyError("policy [fixture].documents must be at least 1")
    if fixture.pages_min < 2 or fixture.pages_max < fixture.pages_min:
        raise PolicyError("policy [fixture] needs pages_min >= 2 and pages_max >= pages_min")
    for name in ("two_column_share", "reversed_stream_share"):
        if not 0.0 <= getattr(fixture, name) <= 1.0:
            raise PolicyError(f"policy [fixture].{name} must be between 0 and 1")
    if fixture.facts_cross_page > fixture.pages_min - 1:
        raise PolicyError(
            "policy [fixture].facts_cross_page cannot exceed pages_min - 1: "
            "each cross-page fact needs its own page boundary"
        )

    ex = raw["extraction"]
    mode = _require(ex, "mode", str, "extraction")
    if mode not in KNOWN_EXTRACTION_MODES:
        raise PolicyError(
            f"policy [extraction].mode must be one of {KNOWN_EXTRACTION_MODES}, got {mode!r}"
        )

    ch = raw["chunking"]
    strategies = _require(ch, "strategies", list, "chunking")
    unknown = [s for s in strategies if s not in KNOWN_STRATEGIES]
    if unknown or not strategies:
        raise PolicyError(
            f"policy [chunking].strategies must be a non-empty subset of {KNOWN_STRATEGIES}, "
            f"unknown: {unknown}"
        )
    chunking = ChunkingPolicy(
        default_size=_require(ch, "default_size", int, "chunking"),
        default_overlap=_require(ch, "default_overlap", int, "chunking"),
        strategies=tuple(strategies),
        sentence_overlap=_require(ch, "sentence_overlap", int, "chunking"),
    )
    if chunking.default_size < 8:
        raise PolicyError("policy [chunking].default_size must be at least 8 tokens")
    if not 0 <= chunking.default_overlap < chunking.default_size:
        raise PolicyError("policy [chunking].default_overlap must be in [0, default_size)")
    if chunking.sentence_overlap < 0:
        raise PolicyError("policy [chunking].sentence_overlap cannot be negative")

    th = raw["thresholds"]
    thresholds = Thresholds(
        max_orphan_share=_require(th, "max_orphan_share", float, "thresholds"),
        max_extraction_loss_share=_require(th, "max_extraction_loss_share", float, "thresholds"),
    )
    for name in ("max_orphan_share", "max_extraction_loss_share"):
        if not 0.0 <= getattr(thresholds, name) <= 1.0:
            raise PolicyError(f"policy [thresholds].{name} must be between 0 and 1")

    return Policy(
        fixture=fixture,
        extraction_mode=mode,
        chunking=chunking,
        thresholds=thresholds,
        source=source,
    )
