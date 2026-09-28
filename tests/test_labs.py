from datetime import date

from copilot.facts import labs
from copilot.facts.labs import lab_facts
from tests.fixtures import FIXTURE_OBS, obs

LAST_VISIT = date(2026, 4, 10)


def by_concept(facts):
    return {f["concept"]: f for f in facts}


def test_regression_never_compare_across_codes():
    # found in real data: serum and blood creatinine differ by up to 2x on the same day
    o = [obs("s1", "2160-0", "creatinine", 2.0, "2026-04-10"),
         obs("b1", "38483-4", "creatinine", 1.0, "2026-07-15")]
    f = by_concept(lab_facts(o, date(2026, 4, 10)))["creatinine"]
    assert f["latest"]["fhir_id"] == "b1"
    assert f["baseline"] is None and f["change"] is None     # no fake "halved"


def test_egfr_goes_down():
    f = by_concept(lab_facts(FIXTURE_OBS, LAST_VISIT))["egfr"]
    assert (f["baseline"]["value"], f["latest"]["value"]) == (46, 38)
    assert f["change"] == -8 and f["direction"] == "down"


def test_same_day_duplicate_prefers_serum():
    f = by_concept(lab_facts(FIXTURE_OBS, LAST_VISIT))["creatinine"]
    assert f["latest"]["value"] == 1.9 and f["latest"]["fhir_id"] == "c2s"
    assert f["measurements"] == 2


def test_first_ever_measurement_has_no_baseline():
    f = by_concept(lab_facts(FIXTURE_OBS, LAST_VISIT))["potassium"]
    assert f["new_since_last_visit"] is True
    assert f["baseline"] is None and f["change"] is None


def test_nothing_new_since_last_visit():
    f = by_concept(lab_facts(FIXTURE_OBS, date(2026, 7, 20)))["hba1c"]
    assert f["new_since_last_visit"] is False
    assert f["change"] is None


def test_no_previous_visit_means_no_comparison():
    f = by_concept(lab_facts(FIXTURE_OBS, None))["hba1c"]
    assert f["new_since_last_visit"] is None and f["change"] is None


def test_every_value_carries_its_own_date():
    for f in lab_facts(FIXTURE_OBS, LAST_VISIT):
        for p in (f["latest"], f["baseline"]):
            if p is not None:
                assert p["date"] and p["fhir_id"]


def test_regression_low_hba1c_is_flagged():
    # found in real data: HbA1c 3.84% showed as in-range under a one-sided fallback
    o = [obs("x", "4548-4", "hba1c", 3.84, "2026-07-15", "%")]
    assert by_concept(lab_facts(o, None))["hba1c"]["latest_out_of_range"] is True


def test_observation_range_beats_fallback():
    o = [obs("k9", "6298-4", "potassium", 5.2, "2026-07-15", "mmol/L", ref_low=3.5, ref_high=5.0)]
    assert by_concept(lab_facts(o, None))["potassium"]["latest_out_of_range"] is True


def test_no_range_means_unknown_not_normal(monkeypatch):
    monkeypatch.setattr(labs, "FALLBACK_RANGES", {})
    for f in lab_facts(FIXTURE_OBS, LAST_VISIT):
        assert f["latest_out_of_range"] is None


def test_hba1c_change_since_last_visit():
    f = by_concept(lab_facts(FIXTURE_OBS, LAST_VISIT))["hba1c"]
    assert f["new_since_last_visit"] is True
    assert f["latest"] == {"value": 8.2, "unit": "%", "date": "2026-07-15",
                           "loinc": "4548-4", "fhir_id": "a3"}
    assert f["baseline"]["value"] == 7.4 and f["baseline"]["date"] == "2026-04-10"
    assert f["change"] == 0.8 and f["direction"] == "up"