from datetime import date

from copilot.facts.compute import compute_facts
from tests.fixtures import (FIXTURE_CONDITIONS, FIXTURE_ENCOUNTERS, FIXTURE_MEDS,
                            FIXTURE_OBS, FIXTURE_PATIENT)

TODAY = date(2026, 8, 1)


def facts(**overrides):
    args = dict(patient=FIXTURE_PATIENT, encounters=FIXTURE_ENCOUNTERS,
                conditions=FIXTURE_CONDITIONS, medications=FIXTURE_MEDS,
                observations=FIXTURE_OBS, today=TODAY)
    args.update(overrides)
    return compute_facts(**args)


def test_briefing_end_to_end():
    f = facts()
    assert f["patient"]["age"] == 62
    assert f["last_visit"]["date"] == "2026-04-10"          # the procedure is not a visit
    assert [m["display"] for m in f["medications"]["new_since_last_visit"]] == ["spironolactone"]
    assert "lisinopril" not in {m["display"] for m in f["medications"]["active"]}
    assert f["medications"]["stopped_since_last_visit"] is None    # unknown, not "none"
    assert [c["code"] for c in f["new_conditions"]] == ["49436004"]
    assert [e["id"] for e in f["events_since_last_visit"]] == ["er1"]
    hba1c = next(l for l in f["labs"] if l["concept"] == "hba1c")
    assert hba1c["change"] == 0.8


def test_no_previous_visit_degrades_gracefully():
    f = facts(encounters=[])
    assert f["last_visit"] is None
    assert f["new_conditions"] == [] and f["events_since_last_visit"] == []
    assert all(l["change"] is None for l in f["labs"])
    assert any("No previous clinic visit" in x for x in f["limitations"])