from __future__ import annotations

from collections import defaultdict
from datetime import date


def medication_facts(medications: list[dict], last_visit: date | None) -> dict:
    by_drug: dict[str, list[dict]] = defaultdict(list)
    for m in medications:
        if m["rxnorm"]:
            by_drug[m["rxnorm"]].append(m)

    active, new = [], []
    for rx, requests in by_drug.items():
        requests.sort(key=lambda m: m["authored_at"])
        if not any(m["status"] == "active" for m in requests):
            continue
        current = requests[-1]
        item = {
            "rxnorm": rx,
            "display": current["display"],
            "first_prescribed": requests[0]["authored_at"].date().isoformat(),
            "fhir_id": current["id"],
        }
        active.append(item)
        # new = never prescribed at or before the last visit (refills don't count)
        if last_visit and not any(m["authored_at"].date() <= last_visit for m in requests):
            new.append(item)

    return {
        "active": sorted(active, key=lambda m: m["display"]),
        "new_since_last_visit": new,
        "stopped_since_last_visit": None,   # unknown: stop dates aren't recorded
    }