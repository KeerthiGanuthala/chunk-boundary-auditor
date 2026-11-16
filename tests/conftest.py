"""Shared fixtures: a small policy, a small corpus and a small rendered fixture directory.

The committed fixture (18 documents) is used by the CLI tests because that is what the README
describes. Everything else uses a reduced corpus so the suite stays fast on three Pythons.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chunkaudit.config import DEFAULT_POLICY_PATH, Policy, load_policy
from chunkaudit.corpus import Corpus, corpus_from_policy
from chunkaudit.fixture import DEFAULT_FIXTURE_DIR, write_fixture

SMALL_POLICY = """
[fixture]
seed = 7
documents = 4
pages_min = 3
pages_max = 3
two_column_share = 0.5
reversed_stream_share = 0.5
facts_single = 2
facts_cross_sentence = 2
facts_cross_paragraph = 2
facts_cross_page = 1
facts_table = 1

[extraction]
mode = "blocks"

[chunking]
default_size = 256
default_overlap = 0
strategies = ["fixed", "recursive", "sentence_window", "page_aware", "paragraph"]
sentence_overlap = 0

[thresholds]
max_orphan_share = 0.5
max_extraction_loss_share = 0.0
"""


@pytest.fixture(scope="session")
def small_policy_path(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("policy") / "policy.toml"
    path.write_text(SMALL_POLICY, encoding="utf-8")
    return path


@pytest.fixture(scope="session")
def small_policy(small_policy_path) -> Policy:
    return load_policy(small_policy_path)


@pytest.fixture(scope="session")
def small_corpus(small_policy) -> Corpus:
    return corpus_from_policy(small_policy)


@pytest.fixture(scope="session")
def small_fixture_dir(small_policy, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("fixture")
    write_fixture(small_policy, out)
    return out


@pytest.fixture(scope="session")
def default_policy() -> Policy:
    return load_policy(DEFAULT_POLICY_PATH)


@pytest.fixture(scope="session")
def committed_fixture_dir() -> Path:
    assert (DEFAULT_FIXTURE_DIR / "manifest.json").exists(), "committed fixture missing"
    return DEFAULT_FIXTURE_DIR


def _is_toml_literal(value: str) -> bool:
    """True for values that must be written bare: numbers, booleans, arrays, quoted strings."""
    if value.startswith(("[", '"')) or value in ("true", "false"):
        return True
    try:
        float(value)
    except ValueError:
        return False
    return True


def write_policy(path: Path, **overrides) -> Path:
    """Write the small policy with ``key = value`` lines replaced. Keys are TOML keys."""
    lines = []
    for line in SMALL_POLICY.strip().splitlines():
        key = line.split("=")[0].strip() if "=" in line else None
        if key in overrides:
            value = overrides.pop(key)
            if isinstance(value, str) and not _is_toml_literal(value):
                value = f'"{value}"'
            line = f"{key} = {value}"
        lines.append(line)
    assert not overrides, f"unknown policy keys {list(overrides)}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
