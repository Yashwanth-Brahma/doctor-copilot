from datetime import date

from copilot.facts.conditions import new_since, problem_list
from tests.fixtures import FIXTURE_CONDITIONS

CODES = {p["code"] for p in problem_list(FIXTURE_CONDITIONS)}


def test_only_most_advanced_ckd_stage():
    assert "433144002" in CODES
    assert not {"431855005", "431856006"} & CODES


def test_diabetes_supersedes_prediabetes():
    assert "44054006" in CODES and "714628002" not in CODES


def test_social_findings_hidden():
    assert "266948004" not in CODES


def test_regression_untagged_disorder_is_kept():
    # found in real data: Gout, Opioid abuse and diabetic retinopathy have no "(disorder)" tag
    assert "90560007" in CODES


def test_transplant_status_most_recent_wins():
    assert "161665007" in CODES and "698306007" not in CODES


def test_resolved_condition_hidden():
    assert "10509002" not in CODES


def test_new_conditions_since_last_visit():
    new = new_since(problem_list(FIXTURE_CONDITIONS), date(2026, 4, 10))
    assert [p["code"] for p in new] == ["49436004"]