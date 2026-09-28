from datetime import date, datetime

from copilot.replay import records_as_of


def ts(day):
    return datetime.fromisoformat(f"{day}T09:00:00+00:00")


RECORDS = {
    "patient": {"id": "p1"},
    "encounters": [{"id": "e1", "start_at": ts("2026-01-10")}, {"id": "e2", "start_at": ts("2026-06-01")},
                   {"id": "e3", "start_at": ts("2026-08-01")}],
    "conditions": [
        {"id": "c1", "onset_at": ts("2025-01-01"), "abated_at": ts("2026-07-01"), "clinical_status": "resolved"},
        {"id": "c2", "onset_at": ts("2026-07-15"), "abated_at": None, "clinical_status": "active"},
    ],
    "medications": [{"id": "m1", "authored_at": ts("2026-05-20")}, {"id": "m2", "authored_at": ts("2026-06-02")}],
    "observations": [{"id": "o1", "effective_at": ts("2026-06-01")}, {"id": "o2", "effective_at": ts("2026-06-02")}],
}


def test_nothing_after_the_replay_day_is_visible():
    r = records_as_of(RECORDS, date(2026, 6, 1))
    assert [e["id"] for e in r["encounters"]] == ["e1", "e2"]
    assert [m["id"] for m in r["medications"]] == ["m1"]
    assert [o["id"] for o in r["observations"]] == ["o1"]        # same-day result is kept


def test_condition_resolved_later_was_active_then():
    r = records_as_of(RECORDS, date(2026, 6, 1))
    assert [c["id"] for c in r["conditions"]] == ["c1"]
    assert r["conditions"][0]["clinical_status"] == "active" and r["conditions"][0]["abated_at"] is None
    assert RECORDS["conditions"][0]["clinical_status"] == "resolved"   # original untouched
