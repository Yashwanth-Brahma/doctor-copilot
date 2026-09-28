"""The patient tools. One module, two ways in:
  - the FastAPI briefing endpoint calls these functions directly
  - the Q&A agent calls them through the MCP server (mcp_server.py), and the UI shows each call

Every tool is a pure function of (records, today): no database here, so it's all testable.
Every value carries `source` (the FHIR record id) so an answer can cite where it came from.
"""
from datetime import date

from .briefing.narrator_input import LAB_NAMES, clean, unit
from .briefing.verify import LAB_ALIASES
from .facts.compute import compute_facts
from .facts.labs import daily_series, out_of_range


def _facts(records: dict, today: date) -> dict:
    return compute_facts(records["patient"], records["encounters"], records["conditions"],
                         records["medications"], records["observations"], today=today)


def _point(p: dict | None) -> dict | None:
    if p is None:
        return None
    return {"value": p["value"], "unit": unit(p["unit"]), "date": p["date"], "source": p["fhir_id"]}


def _last_visit(f: dict) -> dict | None:
    """The last visit carries its encounter id as `source`, like every other value: without it
    the agent had nothing to cite for the visit date, and a correct answer was withheld."""
    lv = f["last_visit"]
    return lv and {"date": lv["date"], "type": clean(lv["type"]), "source": lv["encounter_id"]}


def resolve_lab(name: str) -> str | None:
    """'A1c', 'HbA1c', 'hba1c', 'glycated hemoglobin' -> 'hba1c'."""
    n = name.strip().lower()
    for concept, display in LAB_NAMES.items():
        if n in {concept, display.lower(), *LAB_ALIASES.get(display, [])}:
            return concept
    return None


def get_patient_summary(records: dict, today: date) -> dict:
    """Who the patient is: problems, active medications, latest value of each lab."""
    f = _facts(records, today)
    return {
        "patient": {k: f["patient"][k] for k in ("name", "age", "sex")},
        "last_visit": _last_visit(f),
        "problems": [{"name": clean(p["display"]), "onset": p["onset"], "source": p["id"]}
                     for p in f["problems"]],
        "active_medications": [{"name": m["display"], "first_prescribed": m["first_prescribed"],
                                "source": m["fhir_id"]} for m in f["medications"]["active"]],
        "latest_labs": [{"lab": LAB_NAMES[l["concept"]], **_point(l["latest"]),
                         "out_of_range": l["latest_out_of_range"]} for l in f["labs"]],
        "limitations": f["limitations"],
    }


def get_changes_since_last_visit(records: dict, today: date) -> dict:
    """What's new since the last clinic visit: labs, medications, conditions, hospital events."""
    f = _facts(records, today)
    meds = f["medications"]
    return {
        "last_visit": _last_visit(f),
        "labs": [{"lab": LAB_NAMES[l["concept"]], "previous": _point(l["baseline"]),
                  "latest": _point(l["latest"]), "change": l["change"],
                  "direction": l["direction"], "latest_out_of_range": l["latest_out_of_range"]}
                 for l in f["labs"] if l["new_since_last_visit"] is True],
        "new_medications": [{"name": m["display"], "started": m["first_prescribed"],
                             "source": m["fhir_id"]} for m in meds["new_since_last_visit"] or []],
        "stopped_medications": meds["stopped_since_last_visit"],   # None = unknown, not "none"
        "new_conditions": [{"name": clean(c["display"]), "onset": c["onset"], "source": c["id"]}
                           for c in f["new_conditions"]],
        "events": [{"type": clean(e["type"]), "date": e["date"], "source": e["id"]}
                   for e in f["events_since_last_visit"]],
        "limitations": f["limitations"],
    }


def get_lab_series(records: dict, lab: str, since: str | None = None) -> dict:
    """Every result for one lab, oldest first. Only the latest result's test code is kept,
    so serum and whole-blood values are never mixed in one trend."""
    concept = resolve_lab(lab)
    if concept is None:
        return {"error": f"unknown lab '{lab}'", "available": list(LAB_NAMES.values())}
    series = daily_series(records["observations"], concept)
    if not series:
        return {"lab": LAB_NAMES[concept], "points": [], "note": "no results on record"}
    code = series[-1]["loinc"]
    kept = [o for o in series if o["loinc"] == code]
    if since:
        kept = [o for o in kept if o["effective_at"].date().isoformat() >= since]
    out = {
        "lab": LAB_NAMES[concept],
        "unit": unit(series[-1]["unit"]),
        "points": [{"date": o["effective_at"].date().isoformat(),
                    "value": round(float(o["value"]), 2),
                    "out_of_range": out_of_range(o, concept), "source": o["id"]} for o in kept],
    }
    dropped = len(series) - len([o for o in series if o["loinc"] == code])
    if dropped:
        out["note"] = f"{dropped} result(s) from a different test code left out so values compare like with like"
    return out
