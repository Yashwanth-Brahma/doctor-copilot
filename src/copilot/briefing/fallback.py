"""Sentences written by code, no model.

The same sentence patterns the prompt asks MedGemma for. Used two ways:
  complete_briefing  the draft is correct but left something out -> add just those sentences
  facts_only_text    the draft got something wrong twice -> the whole briefing from the template

Tests prove both always pass the verifier.
"""
from .narrator_input import LAB_NAMES, clean, unit
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


def has_changes(ni: dict) -> bool:
    return any(ni[k] for k in ("labs_with_new_results", "new_medications",
                               "new_conditions", "events_since_last_visit"))


def no_changes_text(ni: dict) -> str:
    """Nothing to narrate, so no model call: code says so directly."""
    if ni["last_visit"] is None:
        return "No previous clinic visit on record, so there is nothing to compare."
    return (f"The last visit was on {ni['last_visit']['date']}.\n"
            "No new lab results, medications, conditions or hospital visits since then.")


def _range_word(flag: bool | None) -> str:
    return {True: "out of range", False: "in range", None: "no reference range"}[flag]


def context_lines(facts: dict) -> list[str]:
    """What the patient has and takes right now, written by code from the facts, never by the
    model (when these lists were in the model's input it listed them and skipped the new
    medication). Empty lists are said out loud: "no medications" must not look like missing data."""
    meds = facts["medications"]
    new = {m["display"] for m in meds["new_since_last_visit"] or []}
    lines = []
    if meds["active"]:
        names = [m["display"] + (" (new since last visit)" if m["display"] in new else "")
                 for m in sorted(meds["active"], key=lambda m: m["display"])]
        lines.append("Current medications: " + ", ".join(names) + ".")
    else:
        lines.append("No active medications on record.")

    # Onset year shown so a condition the record never closed (e.g. "Sepsis" from 2007)
    # can be judged by the doctor instead of silently hidden.
    if facts["problems"]:
        lines.append("Known problems: " + ", ".join(
            f"{clean(p['display'])} (since {p['onset'][:4]})" if p.get("onset") else clean(p["display"])
            for p in facts["problems"]) + ".")
    else:
        lines.append("No known problems on record.")

    # Latest values of labs that have NO new result (the new ones are in the narrative already).
    older = [l for l in facts["labs"] if l["new_since_last_visit"] is not True and l["latest"]]
    if older:
        lines.append("Other latest results: " + "; ".join(_latest_result(l) for l in older) + ".")
    return lines


def _latest_result(lab: dict) -> str:
    """'HbA1c 6.01% (2026-08-12, out of range)'"""
    p = lab["latest"]
    u = unit(p["unit"])
    sep = "" if u == "%" else " "
    name = LAB_NAMES.get(lab["concept"], lab["concept"])
    return f"{name} {_fmt(p['value'])}{sep}{u} ({p['date']}, {_range_word(lab['latest_out_of_range'])})"
