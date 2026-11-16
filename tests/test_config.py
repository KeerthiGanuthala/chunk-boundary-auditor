"""The policy file is refused at the boundary, with the offending key named."""

import pytest

from chunkaudit.config import (
    DEFAULT_POLICY_PATH,
    KNOWN_EXTRACTION_MODES,
    KNOWN_STRATEGIES,
    PolicyError,
    load_policy,
)

from .conftest import write_policy


def test_the_committed_policy_loads():
    policy = load_policy(DEFAULT_POLICY_PATH)
    assert policy.fixture.seed == 20251116
    assert policy.source == DEFAULT_POLICY_PATH


def test_loading_with_no_argument_uses_the_committed_policy():
    assert load_policy().fixture.seed == load_policy(DEFAULT_POLICY_PATH).fixture.seed


def test_the_small_policy_loads(small_policy):
    assert small_policy.fixture.documents == 4
    assert small_policy.chunking.strategies == KNOWN_STRATEGIES


def test_a_missing_file_is_a_policy_error(tmp_path):
    with pytest.raises(PolicyError, match="not found"):
        load_policy(tmp_path / "nope.toml")


def test_invalid_toml_is_a_policy_error(tmp_path):
    path = tmp_path / "p.toml"
    path.write_text("[fixture\nseed = 1", encoding="utf-8")
    with pytest.raises(PolicyError, match="not valid TOML"):
        load_policy(path)


@pytest.mark.parametrize("section", ["fixture", "extraction", "chunking", "thresholds"])
def test_each_missing_table_is_named(tmp_path, section):
    path = write_policy(tmp_path / "p.toml")
    text = path.read_text(encoding="utf-8").replace(f"[{section}]", f"[{section}_gone]")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(PolicyError, match=rf"\[{section}\]"):
        load_policy(path)


def test_a_missing_key_is_named(tmp_path):
    path = write_policy(tmp_path / "p.toml")
    text = path.read_text(encoding="utf-8").replace("seed = 7\n", "")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(PolicyError, match="missing 'seed'"):
        load_policy(path)


def test_a_wrongly_typed_key_is_named(tmp_path):
    path = write_policy(tmp_path / "p.toml", documents='"four"')
    with pytest.raises(PolicyError, match="documents must be int"):
        load_policy(path)


def test_a_boolean_is_not_accepted_as_an_int(tmp_path):
    path = write_policy(tmp_path / "p.toml", documents="true")
    with pytest.raises(PolicyError, match="documents must be int"):
        load_policy(path)


def test_an_int_is_accepted_where_a_float_is_expected(tmp_path):
    path = write_policy(tmp_path / "p.toml", two_column_share="1")
    assert load_policy(path).fixture.two_column_share == 1.0


def test_zero_documents_is_refused(tmp_path):
    path = write_policy(tmp_path / "p.toml", documents="0")
    with pytest.raises(PolicyError, match="documents"):
        load_policy(path)


def test_fewer_than_two_pages_is_refused_because_cross_page_facts_need_a_boundary(tmp_path):
    path = write_policy(tmp_path / "p.toml", pages_min="1", pages_max="1")
    with pytest.raises(PolicyError, match="pages_min"):
        load_policy(path)


def test_pages_max_below_pages_min_is_refused(tmp_path):
    path = write_policy(tmp_path / "p.toml", pages_min="3", pages_max="2")
    with pytest.raises(PolicyError, match="pages_max"):
        load_policy(path)


@pytest.mark.parametrize("key", ["two_column_share", "reversed_stream_share"])
def test_shares_outside_the_unit_interval_are_refused(tmp_path, key):
    path = write_policy(tmp_path / "p.toml", **{key: "1.5"})
    with pytest.raises(PolicyError, match=key):
        load_policy(path)


def test_more_cross_page_facts_than_page_boundaries_is_refused(tmp_path):
    path = write_policy(tmp_path / "p.toml", facts_cross_page="3")
    with pytest.raises(PolicyError, match="facts_cross_page"):
        load_policy(path)


def test_an_unknown_extraction_mode_is_refused(tmp_path):
    path = write_policy(tmp_path / "p.toml", mode="words")
    with pytest.raises(PolicyError, match="mode"):
        load_policy(path)


@pytest.mark.parametrize("mode", KNOWN_EXTRACTION_MODES)
def test_each_known_extraction_mode_is_accepted(tmp_path, mode):
    path = write_policy(tmp_path / "p.toml", mode=mode)
    assert load_policy(path).extraction_mode == mode


def test_an_unknown_strategy_is_refused(tmp_path):
    path = write_policy(tmp_path / "p.toml", strategies='["fixed", "semantic"]')
    with pytest.raises(PolicyError, match="semantic"):
        load_policy(path)


def test_an_empty_strategy_list_is_refused(tmp_path):
    path = write_policy(tmp_path / "p.toml", strategies="[]")
    with pytest.raises(PolicyError, match="non-empty"):
        load_policy(path)


def test_a_tiny_chunk_size_is_refused(tmp_path):
    path = write_policy(tmp_path / "p.toml", default_size="4")
    with pytest.raises(PolicyError, match="default_size"):
        load_policy(path)


def test_overlap_at_or_above_size_is_refused(tmp_path):
    path = write_policy(tmp_path / "p.toml", default_overlap="256")
    with pytest.raises(PolicyError, match="default_overlap"):
        load_policy(path)


def test_negative_sentence_overlap_is_refused(tmp_path):
    path = write_policy(tmp_path / "p.toml", sentence_overlap="-1")
    with pytest.raises(PolicyError, match="sentence_overlap"):
        load_policy(path)


@pytest.mark.parametrize("key", ["max_orphan_share", "max_extraction_loss_share"])
def test_thresholds_outside_the_unit_interval_are_refused(tmp_path, key):
    path = write_policy(tmp_path / "p.toml", **{key: "2"})
    with pytest.raises(PolicyError, match=key):
        load_policy(path)


def test_the_policy_is_immutable():
    policy = load_policy(DEFAULT_POLICY_PATH)
    with pytest.raises(AttributeError):
        policy.fixture.seed = 1  # type: ignore[misc]
