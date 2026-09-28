from __future__ import annotations

from datetime import date

from copilot.ingest.concepts import LAB_CONCEPTS, code_rank

# Used only when an Observation carries no referenceRange.
# General adult ranges; they vary by lab, sex, and method.
# TODO: cite a source for each entry before relying on it.
FALLBACK_RANGES: dict[str, tuple[float | None, float | None]] = {
    "potassium":  (3.5, 5.1),    # mmol/L
    "creatinine": (0.6, 1.3),    # mg/dL
    "egfr":       (60, None),    # mL/min/1.73m2
    "hba1c":      (4.0, 5.6),    # % — was (None, 5.6): a one-sided range can never flag a low value
}
# TODO: cite a source for each entry before relying on it.

def daily_series(observations: list[dict], concept: str) -> list[dict]:
    """One reading per day for a concept. When two codes report on the same day,
    keep the preferred code (earlier in LAB_CONCEPTS); on a tie, keep the later reading."""
    best: dict[date, dict] = {}
    for o in observations:
        if o["concept"] != concept or o["value"] is None or o["effective_at"] is None:
            continue
        day = o["effective_at"].date()
        cur = best.get(day)
        if cur is None:
            best[day] = o
            continue
        rank_new, rank_cur = code_rank(concept, o["loinc"]), code_rank(concept, cur["loinc"])
        if rank_new < rank_cur or (rank_new == rank_cur and o["effective_at"] > cur["effective_at"]):
            best[day] = o
    return [best[d] for d in sorted(best)]


def out_of_range(o: dict, concept: str) -> bool | None:
    """True / False, or None when no reference range is known."""
    low, high = o.get("ref_low"), o.get("ref_high")
    if low is None and high is None:
        low, high = FALLBACK_RANGES.get(concept, (None, None))
    if low is None and high is None:
        return None
    v = float(o["value"])
    return (low is not None and v < low) or (high is not None and v > high)


def _point(o: dict) -> dict:
    """Every value carries its OWN date and source id — no shared or implied dates."""
    return {
        "value": round(float(o["value"]), 2),
        "unit": o["unit"],
        "date": o["effective_at"].date().isoformat(),
        "loinc": o["loinc"],                    # which test this came from
        "fhir_id": o["id"],
    }


def lab_facts(observations: list[dict], last_visit: date | None) -> list[dict]:
    """Compare each lab's latest value with what was known at the last clinic visit.

    latest               most recent measurement
    baseline             most recent measurement on or before the last visit
    new_since_last_visit True if the latest was measured after the last visit
    change / direction   only when there is something new AND a baseline
    """
    facts = []
    for concept in LAB_CONCEPTS:
        series = daily_series(observations, concept)
        if not series:
            continue
        latest = series[-1]
        fact = {
            "id": f"lab.{concept}",
            "concept": concept,
            "latest": _point(latest),
            "latest_out_of_range": out_of_range(latest, concept),
            "measurements": len(series),
            "new_since_last_visit": None,
            "baseline": None,
            "change": None,
            "direction": None,
        }
        if last_visit is not None:
            fact["new_since_last_visit"] = latest["effective_at"].date() > last_visit
            # compare like with like: same test code only
            known_at_visit = [o for o in series
                              if o["effective_at"].date() <= last_visit
                              and o["loinc"] == latest["loinc"]]
            if fact["new_since_last_visit"] and known_at_visit:
                base = known_at_visit[-1]
                change = round(float(latest["value"]) - float(base["value"]), 2)
                fact["baseline"] = _point(base)
                fact["change"] = change
                fact["direction"] = "up" if change > 0 else "down" if change < 0 else "same"
        facts.append(fact)
    return facts