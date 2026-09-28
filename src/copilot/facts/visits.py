from __future__ import annotations

from datetime import date

# Matches on display text because the encounter type code isn't stored yet.
# TODO: store type_code in the loader and match on codes, like everything else.
VISIT_TYPES = {
    "Encounter for check up (procedure)",
    "General examination of patient (procedure)",
    "Encounter for problem (procedure)",
    "Encounter for symptom (procedure)",
    "Follow-up encounter (procedure)",
    "Consultation for treatment (procedure)",
    "Well child visit (procedure)",
    "Asthma follow-up (regime/therapy)",
}
VISIT_CLASSES = {"AMB", "VR"}            # in person or virtual
EVENT_CLASSES = {"EMER", "IMP"}           # emergency, inpatient
URGENT_CARE = "Urgent care clinic (environment)"


def last_visit(encounters: list[dict], before: date | None = None) -> dict | None:
    visits = [e for e in encounters
              if e["start_at"] and e["class"] in VISIT_CLASSES and e["type"] in VISIT_TYPES]
    if before is not None:
        visits = [e for e in visits if e["start_at"].date() < before]
    return max(visits, key=lambda e: e["start_at"]) if visits else None


def events_since(encounters: list[dict], since: date | None) -> list[dict]:
    if since is None:
        return []
    events = [e for e in encounters
              if e["start_at"] and e["start_at"].date() > since
              and (e["class"] in EVENT_CLASSES or e["type"] == URGENT_CARE)]
    return [{"id": e["id"], "class": e["class"], "type": e["type"],
             "date": e["start_at"].date().isoformat()}
            for e in sorted(events, key=lambda e: e["start_at"])]