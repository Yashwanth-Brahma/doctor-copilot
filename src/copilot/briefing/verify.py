"""Check a written briefing against the narrator input, one sentence at a time.

Grounding is per sentence, not per document: a number has to belong to the thing the
sentence is about. "eGFR was 38 on 2026-09-21" fails if 2026-09-21 is HbA1c's date,
even though that date exists somewhere in the facts. That is the exact MedGemma bug.

verify(text, ni) returns a list of violations. Empty list = pass.
"""
import re
from dataclasses import dataclass, field

LAB_ALIASES = {
    "HbA1c": ["hba1c", "a1c", "hemoglobin a1c", "haemoglobin a1c", "glycated hemoglobin"],
    "eGFR": ["egfr", "gfr", "glomerular filtration rate"],
    "Creatinine": ["creatinine"],
    "Glucose": ["glucose", "blood sugar"],
    "Potassium": ["potassium"],
}
EVENT_WORDS = ["emergency", "admission", "admitted", "hospital", "urgent care", "inpatient"]
CONDITION_ABBREV = {"ckd": "kidney", "afib": "fibrillation", "af": "fibrillation",
                    "t2dm": "diabetes", "htn": "hypertension"}
GENERIC_WORDS = {"disease", "disorder", "chronic", "stage", "mellitus", "essential",
                 "finding", "acute", "primary", "secondary"}

INTERPRETATION = re.compile(
    r"\b(consider\w*|recommend\w*|should|suggest\w*|indicat\w*|due to|because|likely|"
    r"consistent with|caused by|worsen\w*|improv\w*|concerning|controlled|uncontrolled|"
    r"diagnos\w*|risk\w*|progress\w*|significant\w*)\b", re.I)
VAGUE_DATE = re.compile(
    r"\b(those|these|that|this|same) (dates?|time|period|day)\b", re.I)
NON_ISO_DATE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.? \d{1,2}\b"
    r"|\b\d{1,2} (jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b", re.I)
ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# digits that are part of a name or unit, not a value: "type 2", "stage 3", "1.73m²"
NAMED_NUMBER = re.compile(r"\b(type|stage|grade|class)\s+\d+[ab]?\b|\bckd\s*g?\d[ab]?\b|"
                          r"1\.73\s*m(²|2|\^2|\\u00b2)", re.I)
NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?!\w)")
NORMAL_CLAIM = re.compile(r"\b(normal|in range|within (the )?(normal|reference) range)\b", re.I)


@dataclass
class Entity:
    kind: str                 # lab | medication | condition | event
    name: str
    patterns: list            # compiled regexes that mean "this sentence names me"
    numbers: set = field(default_factory=set)
    dates: set = field(default_factory=set)
    unit: str | None = None
    out_of_range: bool | None = None


def _num(x) -> float:
    return round(abs(float(x)), 2)


def _words(*terms) -> list:
    return [re.compile(rf"\b{re.escape(t)}\b", re.I) for t in terms]


def build_entities(ni: dict) -> list[Entity]:
    ents = []
    for lab in ni["labs_with_new_results"] + ni.get("labs_without_new_results", []):
        e = Entity("lab", lab["lab"], _words(*LAB_ALIASES.get(lab["lab"], [lab["lab"].lower()])),
                   unit=lab["latest"]["unit"], out_of_range=lab["latest_out_of_range"])
        for key in ("previous", "latest"):
            p = lab.get(key)
            if p:
                e.numbers.add(_num(p["value"]))
                e.dates.add(p["date"])
        if lab.get("change") is not None:
            e.numbers.add(_num(lab["change"]))
        ents.append(e)

    for m in ni["new_medications"]:
        ents.append(Entity("medication", m["name"], _words(m["name"]), dates={m["started"]}))
    for name in ni.get("active_medications", []):
        if not any(e.name == name for e in ents):
            ents.append(Entity("medication", name, _words(name)))

    for c in ni["new_conditions"]:
        keys = [w for w in re.findall(r"[a-z]+", c["name"].lower())
                if len(w) >= 5 and w not in GENERIC_WORDS]
        abbrevs = [a for a, k in CONDITION_ABBREV.items() if k in keys]
        ents.append(Entity("condition", c["name"], _words(*keys, *abbrevs), dates={c["onset"]}))

    if ni["events_since_last_visit"]:
        ents.append(Entity("event", "events since last visit", _words(*EVENT_WORDS),
                           dates={ev["date"] for ev in ni["events_since_last_visit"]}))
    return ents


def split_sentences(text: str) -> list[str]:
    parts = []
    for line in text.splitlines():
        line = re.sub(r"^\s*([-*•]|\d+\.)\s+", "", line).strip()
        parts += [s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    return parts


def _owner(value, attr: str, ents: list[Entity]) -> str | None:
    for e in ents:
        if value in getattr(e, attr):
            return e.name
    return None


NOT_PLAIN = re.compile(r"[{}\[\]`]|\\u[0-9a-f]{4}", re.I)


def check_sentence(s: str, ents: list[Entity], global_dates: set, global_numbers: set) -> list[str]:
    problems = []
    if NOT_PLAIN.search(s):
        problems.append("not plain text (JSON, code or escape characters)")
    if m := INTERPRETATION.search(s):
        problems.append(f"interpretation word '{m.group(0)}' — describe, don't interpret")
    if m := VAGUE_DATE.search(s):
        problems.append(f"vague date reference '{m.group(0)}' — give the date")
    if m := NON_ISO_DATE.search(s):
        problems.append(f"date '{m.group(0)}' not in YYYY-MM-DD format")

    named = [e for e in ents if any(p.search(s) for p in e.patterns)]
    labs = [e for e in named if e.kind == "lab"]

    dates = ISO_DATE.findall(s)
    rest = ISO_DATE.sub(" ", s)
    for e in labs:                       # a lab's own unit may contain digits
        if e.unit:
            rest = rest.replace(e.unit, " ")
    rest = NAMED_NUMBER.sub(" ", rest)
    numbers = [(m.group(0), m.end()) for m in NUMBER.finditer(rest)]

    own_dates = set().union(*(e.dates for e in named)) if named else set()
    own_numbers = set().union(*(e.numbers for e in named)) if named else set()

    non_global = [d for d in dates if d not in global_dates] + \
                 [n for n, _ in numbers if _num(n) not in global_numbers]
    if len(labs) > 1 and non_global:
        problems.append(f"values in a sentence naming {len(labs)} labs "
                        f"({', '.join(e.name for e in labs)}) — one lab per sentence")

    # A sentence that gives lab values may only use that lab's own dates, even if the
    # last-visit date is legal elsewhere: "eGFR was 46 (2026-04-01)" is wrong when the
    # eGFR was drawn 2026-03-20.
    gives_lab_values = bool(labs) and any(_num(n) not in global_numbers for n, _ in numbers)
    allowed_dates = own_dates if gives_lab_values else own_dates | global_dates

    for d in dates:
        if d in allowed_dates:
            continue
        owner = _owner(d, "dates", ents)
        if not named:
            problems.append(f"date {d} with no named lab or medication")
        elif owner:
            problems.append(f"date {d} belongs to {owner}, not {', '.join(e.name for e in named)}")
        else:
            problems.append(f"date {d} is not in the facts")

    for n, end in numbers:
        v = _num(n)
        is_percent = bool(re.match(r"\s*(%|percent)", rest[end:], re.I))
        if is_percent and not any(e.unit == "%" for e in labs):
            problems.append(f"percentage '{n}%' is not in the facts — don't calculate")
            continue
        if v in global_numbers or v in own_numbers:
            continue
        owner = _owner(v, "numbers", ents)
        if not named:
            problems.append(f"value {n} with no named lab")
        elif owner:
            problems.append(f"value {n} belongs to {owner}, not {', '.join(e.name for e in named)}")
        else:
            problems.append(f"value {n} is not in the facts")

    if NORMAL_CLAIM.search(s) and any(e.out_of_range for e in labs):
        problems.append("calls an out-of-range result normal")
    return problems


def _said_with(ent: Entity, sentences: list[str], date: str | None = None,
               value=None) -> bool:
    """Does some sentence name `ent` together with this date and/or value?"""
    for s in sentences:
        if not any(p.search(s) for p in ent.patterns):
            continue
        if date and date not in s:
            continue
        if value is not None:
            nums = {_num(n) for n in NUMBER.findall(ISO_DATE.sub(" ", s))}
            if _num(value) not in nums:
                continue
        return True
    return False


def missing_items(text: str, ni: dict, ents: list[Entity] | None = None) -> list[tuple]:
    """Things the briefing must say, each together with its key fact.

    Naming isn't enough: "The patient is taking ... spironolactone" mentions the drug but
    never says it is NEW. So a new medication must appear with its start date, a changed lab
    with its latest value and date, a new condition with its onset, an event with its date.

    Returns (key, label) pairs. The key lets code add the missing sentence (fallback.complete).
    """
    ents = ents or build_entities(ni)
    by_name = {e.name: e for e in ents}
    sentences = split_sentences(text)
    missing = []
    if ni["last_visit"] and ni["last_visit"]["date"] not in text:
        missing.append((("last_visit", None), f"last visit date {ni['last_visit']['date']}"))
    for i, lab in enumerate(ni["labs_with_new_results"]):
        v, d = lab["latest"]["value"], lab["latest"]["date"]
        if not _said_with(by_name[lab["lab"]], sentences, date=d, value=v):
            missing.append((("lab", i), f"{lab['lab']} with its latest value {v} ({d})"))
    for i, m in enumerate(ni["new_medications"]):
        if not _said_with(by_name[m["name"]], sentences, date=m["started"]):
            missing.append((("medication", i), f"{m['name']} as new, with its start date {m['started']}"))
    for i, c in enumerate(ni["new_conditions"]):
        if not _said_with(by_name[c["name"]], sentences, date=c["onset"]):
            missing.append((("condition", i), f"{c['name']} as new, with its onset {c['onset']}"))
    for i, ev in enumerate(ni["events_since_last_visit"]):
        if not _said_with(by_name["events since last visit"], sentences, date=ev["date"]):
            missing.append((("event", i), f"{ev['type']} on {ev['date']}"))
    return missing


def verify(text: str, ni: dict) -> list[dict]:
    ents = build_entities(ni)
    missing = missing_items(text, ni, ents)
    global_dates = {ni["as_of"]} | ({ni["last_visit"]["date"]} if ni["last_visit"] else set())
    age = (ni.get("patient") or {}).get("age")
    global_numbers = {_num(age)} if age is not None else set()
    violations = []
    for s in split_sentences(text):
        for p in check_sentence(s, ents, global_dates, global_numbers):
            violations.append({"sentence": s, "problem": p})
    for _, label in missing:
        violations.append({"sentence": "(whole briefing)", "problem": f"missing: {label}"})
    return violations
