"""The HTML report: structure the screenshot tool depends on, and the badge that must be visible."""

import re

import pytest

from chunkaudit.cli import main
from chunkaudit.html import CLASSES_USED, STYLE, render
from chunkaudit.pipeline import run_audit
from chunkaudit.report import EXIT_OK


@pytest.fixture
def results(small_fixture_dir):
    return [
        run_audit(strategy=s, size=256, fixture_dir=small_fixture_dir)
        for s in ("fixed", "paragraph")
    ]


def test_the_report_has_the_three_named_headings(results):
    page = render(results, 0, [], "policy.toml")
    for heading in ("verdict", "strategies", "lost"):
        assert f'<h2 id="{heading}">' in page


def test_a_passing_run_renders_a_pass_badge(results):
    assert 'class="badge badge-pass">PASS' in render(results, 0, [], "policy.toml")


def test_a_failing_run_renders_a_fail_badge_and_the_reasons(results):
    page = render(results, 1, ["too many orphans"], "policy.toml")
    assert 'class="badge badge-fail">FAIL' in page
    assert "<li>too many orphans</li>" in page


def test_the_best_strategy_row_is_marked(results):
    page = render(results, 0, [], "policy.toml")
    assert page.count('<tr class="best">') == 1


def test_every_css_class_used_in_the_markup_has_a_rule_in_the_stylesheet(results):
    """Pins the collision that once rendered a verdict badge green on green: no rule, no colour."""
    page = render(results, 0, ["x"], "policy.toml")
    used = set(re.findall(r'class="([^"]+)"', page))
    used = {c for group in used for c in group.split()}
    assert used <= set(CLASSES_USED)
    for cls in CLASSES_USED:
        assert re.search(rf"\.{re.escape(cls)}\b", STYLE), cls


def test_the_badge_colours_are_not_the_page_background():
    assert "#ffffff" in STYLE.split("body")[1].split("}")[0]
    assert "#1a7f37" in STYLE and "#cf222e" in STYLE


def test_lost_fact_ids_are_listed_once_and_sorted(results):
    page = render(results, 0, [], "policy.toml")
    ids = re.findall(r"D\d\d-[a-z_]+-\d+", page.split('<h2 id="lost">')[1])
    assert ids == sorted(set(ids))


def test_a_report_with_no_results_is_refused():
    with pytest.raises(ValueError):
        render([], 0, [], "policy.toml")


def test_the_report_escapes_policy_names(results):
    page = render(results, 0, [], "<b>policy</b>")
    assert "&lt;b&gt;policy&lt;/b&gt;" in page


def test_the_cli_writes_the_html_report(tmp_path):
    out = tmp_path / "r" / "audit.html"
    assert main(["audit", "--strategy", "fixed", "--html", str(out)]) == EXIT_OK
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
