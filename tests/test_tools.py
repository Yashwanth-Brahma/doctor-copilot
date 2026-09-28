from datetime import datetime

from copilot.tools import get_lab_series, resolve_lab


def o(id, day, value, loinc="2160-0", concept="creatinine", unit="mg/dL"):
    return {"id": id, "concept": concept, "loinc": loinc, "value": value, "unit": unit,
            "effective_at": datetime.fromisoformat(f"{day}T09:00:00+00:00"),
            "ref_low": None, "ref_high": None}


RECORDS = {"observations": [
    o("c1", "2025-10-01", 1.3),
    o("c2", "2026-01-10", 2.4, loinc="38483-4"),      # whole-blood code: must not join the trend
    o("c3", "2026-04-01", 1.55),
    o("c4", "2026-09-21", 1.9),
    o("e1", "2026-09-21", 38, loinc="33914-3", concept="egfr", unit="mL/min/{1.73_m2}"),
]}


def test_resolve_lab_aliases():
    assert resolve_lab("A1c") == resolve_lab("HbA1c") == resolve_lab("hba1c") == "hba1c"
    assert resolve_lab("eGFR") == "egfr"
    assert resolve_lab("cholesterol") is None


def test_lab_series_oldest_first_with_sources():
    s = get_lab_series(RECORDS, "creatinine")
    assert [p["date"] for p in s["points"]] == ["2025-10-01", "2026-04-01", "2026-09-21"]
    assert [p["source"] for p in s["points"]] == ["c1", "c3", "c4"]
    assert [p["out_of_range"] for p in s["points"]] == [False, True, True]


def test_lab_series_never_mixes_codes():
    s = get_lab_series(RECORDS, "creatinine")
    assert 2.4 not in [p["value"] for p in s["points"]]
    assert "different test code" in s["note"]


def test_lab_series_since_and_units():
    s = get_lab_series(RECORDS, "egfr", since="2026-01-01")
    assert s["unit"] == "mL/min/1.73m²" and len(s["points"]) == 1


def test_unknown_lab_lists_what_exists():
    s = get_lab_series(RECORDS, "cholesterol")
    assert "error" in s and "HbA1c" in s["available"]


def test_regression_last_visit_has_a_source_to_cite(monkeypatch):
    # "Has he been to the hospital since the last visit?" was withheld: the answer mentioned
    # the visit date, but the tool gave no source id for it, so nothing real could be cited.
    import copilot.tools as tools_module
    from copilot.qa.check import check_answer
    from tests.test_verify import FACTS
    monkeypatch.setattr(tools_module, "compute_facts", lambda *a, **k: FACTS)
    records = {"patient": {}, "encounters": [], "conditions": [], "medications": [], "observations": []}
    changes = tools_module.get_changes_since_last_visit(records, None)
    assert changes["last_visit"]["source"] == "demo-ravi-kumar-enc-2"
    answer = "There are no hospital visits since the last visit on 2026-04-01 [demo-ravi-kumar-enc-2]."
    assert check_answer(answer, [changes], "Has he been to the hospital since the last visit?") == []
