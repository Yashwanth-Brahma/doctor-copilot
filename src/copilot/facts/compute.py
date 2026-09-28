from __future__ import annotations

from datetime import date

from copilot.facts.conditions import new_since, problem_list
from copilot.facts.labs import lab_facts
from copilot.facts.meds import medication_facts
from copilot.facts.visits import events_since, last_visit


def _age(birth: date, today: date) -> int:
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def compute_facts(patient: dict, encounters: list[dict], conditions: list[dict],
                  medications: list[dict], observations: list[dict], today: date) -> dict:
    visit = last_visit(encounters, before=today)
    lv = visit["start_at"].date() if visit else None
    problems = problem_list(conditions)

    limitations = ["Medication stop dates are not recorded, so stopped medications are not reported."]
    if lv is None:
        limitations.append("No previous clinic visit on record, so there is nothing to compare against.")

    return {
        "as_of": today.isoformat(),
        "patient": {
            "id": patient["id"], "name": patient["name"],
            "age": _age(patient["birth_date"], today), "sex": patient["sex"],
        },
        "last_visit": ({"date": lv.isoformat(), "type": visit["type"], "encounter_id": visit["id"]}
                       if visit else None),
        "problems": problems,
        "new_conditions": new_since(problems, lv),
        "medications": medication_facts(medications, lv),
        "labs": lab_facts(observations, lv),
        "events_since_last_visit": events_since(encounters, lv),
        "limitations": limitations,
    }