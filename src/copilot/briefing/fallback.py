"""Sentences written by code, no model.

The same sentence patterns the prompt asks MedGemma for. Used two ways:
  complete_briefing  the draft is correct but left something out -> add just those sentences
  facts_only_text    the draft got something wrong twice -> the whole briefing from the template

Tests prove both always pass the verifier.
"""
from .narrator_input import clean
from .verify import missing_items, split_sentences


def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def _value(p: dict) -> str:
    sep = "" if p["unit"] == "%" else " "
    return f"{_fmt(p['value'])}{sep}{p['unit']} ({p['date']})"


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def last_visit_sentence(ni: dict) -> str:
    lv = ni["last_visit"]
    return f"The last visit was on {lv['date']}." if lv else "No previous clinic visit on record."


def lab_sentence(lab: dict) -> str:
    if not lab["previous"]:
        return f"{lab['lab']} was {_value(lab['latest'])}, the first result."
    verb = {"up": "rose", "down": "fell"}.get(lab["direction"], "went")
    return f"{lab['lab']} {verb} from {_value(lab['previous'])} to {_value(lab['latest'])}."


def medication_sentence(m: dict) -> str:
    return f"{_cap(m['name'])} was started on {m['started']}."


def condition_sentence(c: dict) -> str:
    return f"{c['name']} was recorded on {c['onset']}."


def event_sentence(ev: dict) -> str:
    return f"Hospital or urgent care visit: {ev['type']} on {ev['date']}."


def sentence_for(key: tuple, ni: dict) -> str:
    kind, i = key
    if kind == "last_visit":
        return last_visit_sentence(ni)
    if kind == "lab":
        return lab_sentence(ni["labs_with_new_results"][i])
    if kind == "medication":
        return medication_sentence(ni["new_medications"][i])
    if kind == "condition":
        return condition_sentence(ni["new_conditions"][i])
    return event_sentence(ni["events_since_last_visit"][i])


def complete_briefing(text: str, ni: dict) -> tuple[str, list[str]]:
    """Add a template sentence for each item the draft left out. Returns (text, added)."""
    missing = missing_items(text, ni)
    head = [sentence_for(k, ni) for k, _ in missing if k[0] == "last_visit"]
    tail = [sentence_for(k, ni) for k, _ in missing if k[0] != "last_visit"]
    lines = head + split_sentences(text) + tail
    return "\n".join(lines), head + tail


def facts_only_text(ni: dict) -> str:
    lines = [last_visit_sentence(ni)]
    lines += [lab_sentence(l) for l in ni["labs_with_new_results"]]
    lines += [medication_sentence(m) for m in ni["new_medications"]]
    lines += [condition_sentence(c) for c in ni["new_conditions"]]
    lines += [event_sentence(e) for e in ni["events_since_last_visit"]]
    if not ni["labs_with_new_results"] and ni["last_visit"]:
        lines.append("No new lab results since the last visit.")
    return "\n".join(lines)


def context_lines(facts: dict) -> list[str]:
    """What the patient has and takes right now. Written by code from the facts, never by
    the model: when these lists were in the model's input it listed them and skipped the
    new medication. The doctor still reads them as part of the briefing."""
    meds = facts["medications"]
    new = {m["display"] for m in meds["new_since_last_visit"] or []}
    lines = []
    if meds["active"]:
        names = [m["display"] + (" (new since last visit)" if m["display"] in new else "")
                 for m in sorted(meds["active"], key=lambda m: m["display"])]
        lines.append("Current medications: " + ", ".join(names) + ".")
    if facts["problems"]:
        lines.append("Known problems: " + ", ".join(clean(p["display"]) for p in facts["problems"]) + ".")
    return lines
