from __future__ import annotations

from datetime import date

# Hidden from the problem list. Built from every non-disorder code in the dataset.
SOCIAL_ADMIN = {
    "314529007",   # Medication review due
    "160903007", "160904001", "741062008", "73438004",       # employment status
    "224299000", "473461003", "224295006",                    # education
    "73595000", "423315002", "422650009",                     # stress, social contact/isolation
    "706893006", "424393004", "160968000",                    # abuse, violence, risk activity
    "105531004", "713458007", "266934004",                    # housing, transport
    "266948004", "1187604002", "446654005", "183996000",      # criminal record, military, refugee, sterilization request
}
TRANSIENT = {
    "386661006", "84229001", "49727002", "248595008", "36955009", "271825005",
    "267036007", "56018004", "236077008", "249497008", "422587007", "66857006",
    "246677007", "43724002", "68235000", "68962001", "25064002", "57676002",
    "840544004", "384709000", "48333001",
}
DENTAL = {"278598003", "278558000", "278588009", "278602001"}
HIDDEN = SOCIAL_ADMIN | TRANSIENT | DENTAL

# Stages Synthea never resolves: show only the most advanced active member.
STAGED_FAMILIES = {
    "glycemic":        ["714628002", "44054006"],                        # prediabetes → T2DM
    "ckd":             ["431855005", "431856006", "433144002",
                        "431857002", "46177005"],                        # stage 1-4 → ESRD
    "diabetic_kidney": ["90781000119102", "157141000119108"],            # microalbuminuria → proteinuria
}
# Statuses that can change back and forth: show the most recent.
LATEST_WINS_FAMILIES = {
    "kidney_transplant_status": ["698306007", "161665007"],             # awaiting ↔ transplanted
}


def is_active(c: dict) -> bool:
    return c["clinical_status"] == "active" and c["abated_at"] is None


def problem_list(conditions: list[dict]) -> list[dict]:
    active = [c for c in conditions if is_active(c) and c["code"] not in HIDDEN]

    # the same code can be recorded more than once: keep the most recent
    by_code: dict[str, dict] = {}
    for c in active:
        if c["code"] not in by_code or c["onset_at"] > by_code[c["code"]]["onset_at"]:
            by_code[c["code"]] = c
    active = list(by_code.values())

    superseded: set[str] = set()
    for codes in STAGED_FAMILIES.values():
        present = [c for c in active if c["code"] in codes]
        if len(present) > 1:
            keep = max(present, key=lambda c: codes.index(c["code"]))
            superseded |= {c["id"] for c in present if c is not keep}
    for codes in LATEST_WINS_FAMILIES.values():
        present = [c for c in active if c["code"] in codes]
        if len(present) > 1:
            keep = max(present, key=lambda c: c["onset_at"])
            superseded |= {c["id"] for c in present if c is not keep}

    kept = [c for c in active if c["id"] not in superseded]
    return [
        {"id": c["id"], "code": c["code"], "display": c["display"],
         "onset": c["onset_at"].date().isoformat()}
        for c in sorted(kept, key=lambda c: c["onset_at"])
    ]


def new_since(problems: list[dict], last_visit: date | None) -> list[dict]:
    if last_visit is None:
        return []
    return [p for p in problems if p["onset"] > last_visit.isoformat()]