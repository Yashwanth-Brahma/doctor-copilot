"""What the narrator is allowed to see.

The facts object carries names, record ids and LOINC codes the model doesn't need.
We send only what it must describe: fewer things in the prompt = fewer things to mix up,
and no patient identifiers leave our code.
"""
import re

LAB_NAMES = {
    "hba1c": "HbA1c",
    "egfr": "eGFR",
    "creatinine": "Creatinine",
    "glucose": "Glucose",
    "potassium": "Potassium",
}

# FHIR/UCUM units -> how a clinician writes them
UNIT_DISPLAY = {"mL/min/{1.73_m2}": "mL/min/1.73m²"}

_TAG = re.compile(r"\s*\([a-z/ ]+\)\s*$")  # "(disorder)", "(procedure)", "(regime/therapy)"


def clean(display: str | None) -> str | None:
    return None if display is None else _TAG.sub("", display).strip()


def unit(u: str) -> str:
    return UNIT_DISPLAY.get(u, u)


def _point(p: dict | None) -> dict | None:
    if p is None:
        return None
    return {"value": p["value"], "unit": unit(p["unit"]), "date": p["date"]}


def narrator_input(facts: dict) -> dict:
    new_labs = []
    for lab in facts["labs"]:
        name = LAB_NAMES.get(lab["concept"], lab["concept"])
        if lab["new_since_last_visit"] is True:
            new_labs.append({
                "lab": name,
                "previous": _point(lab["baseline"]),
                "latest": _point(lab["latest"]),
                "change": lab["change"],
                "direction": lab["direction"],
                "latest_out_of_range": lab["latest_out_of_range"],
            })

    lv = facts["last_visit"]
    meds = facts["medications"]
    # Only what the briefing must say, in the order it should say it. Current medications,
    # the problem list and older labs are left out on purpose: the UI shows them from facts,
    # and when they were in here MedGemma listed them instead of the new medication.
    return {
        "as_of": facts["as_of"],
        "last_visit": None if lv is None else {"date": lv["date"], "type": clean(lv["type"])},
        "labs_with_new_results": new_labs,
        "new_medications": [
            {"name": m["display"], "started": m["first_prescribed"]}
            for m in meds["new_since_last_visit"] or []
        ],
        "new_conditions": [
            {"name": clean(c["display"]), "onset": c["onset"]} for c in facts["new_conditions"]
        ],
        "events_since_last_visit": [
            {"type": clean(e.get("type")), "date": e["date"]}
            for e in facts["events_since_last_visit"]
        ],
    }
