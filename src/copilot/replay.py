"""Rebuild a patient's record as it stood on an earlier day, for evaluation.

Synthea records end at each patient's last visit, so "since the last visit" is empty for almost
everyone today (95 of 101 patients). The realistic test is the briefing a doctor would have got
FOR that last visit: today = that visit's date, compared with the visit before it, with nothing
recorded afterwards visible.

Known gap: a medication's status is its final status, so a drug stopped after the replay day
still looks stopped. Condition resolution is rewound using abated_at.
"""
from datetime import date, datetime


def _day(ts: datetime | None) -> date | None:
    return ts.date() if ts else None


def records_as_of(records: dict, day: date) -> dict:
    """Drop everything recorded after `day`; conditions resolved after `day` count as active."""
    def on_or_before(ts):
        return ts is not None and _day(ts) <= day

    conditions = []
    for c in records["conditions"]:
        if not on_or_before(c["onset_at"]):
            continue
        if c["abated_at"] and _day(c["abated_at"]) > day:
            c = c | {"abated_at": None, "clinical_status": "active"}
        conditions.append(c)

    return {
        "patient": records["patient"],
        "encounters": [e for e in records["encounters"] if on_or_before(e["start_at"])],
        "conditions": conditions,
        "medications": [m for m in records["medications"] if on_or_before(m["authored_at"])],
        "observations": [o for o in records["observations"] if on_or_before(o["effective_at"])],
    }


def replay_day(records: dict, last_visit) -> date | None:
    """The date of the patient's most recent clinic visit: the visit we brief for."""
    v = last_visit(records["encounters"], before=None)
    return _day(v["start_at"]) if v else None
