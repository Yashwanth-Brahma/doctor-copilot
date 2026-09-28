from datetime import datetime


def obs(id, loinc, concept, value, day, unit="mg/dL", ref_low=None, ref_high=None):
    return {
        "id": id, "patient_id": "p1", "encounter_id": None, "category": "laboratory",
        "loinc": loinc, "concept": concept, "display": "", "value": value, "unit": unit,
        "effective_at": datetime.fromisoformat(f"{day}T09:00:00+00:00"),
        "ref_low": ref_low, "ref_high": ref_high,
    }


FIXTURE_OBS = [
    obs("a1", "4548-4", "hba1c", 7.1, "2026-01-10", "%"),
    obs("a2", "4548-4", "hba1c", 7.4, "2026-04-10", "%"),
    obs("a3", "4548-4", "hba1c", 8.2, "2026-07-15", "%"),

    obs("e1", "33914-3", "egfr", 52, "2026-01-10", "mL/min/1.73m2"),
    obs("e2", "33914-3", "egfr", 46, "2026-04-10", "mL/min/1.73m2"),
    obs("e3", "33914-3", "egfr", 38, "2026-07-15", "mL/min/1.73m2"),

    # same day, two codes, DIFFERENT values: serum (2160-0) must win over blood
    obs("c1s", "2160-0", "creatinine", 1.6, "2026-04-10"),
    obs("c2s", "2160-0", "creatinine", 1.9, "2026-07-15"),
    obs("c2b", "38483-4", "creatinine", 2.0, "2026-07-15"),

    # measured only once: no previous value
    obs("k1", "6298-4", "potassium", 5.2, "2026-07-15", "mmol/L"),
]

def cond(id, code, display, onset, status="active", abated=None):
    return {
        "id": id, "patient_id": "p1", "code": code, "display": display,
        "onset_at": datetime.fromisoformat(f"{onset}T00:00:00+00:00"),
        "abated_at": datetime.fromisoformat(f"{abated}T00:00:00+00:00") if abated else None,
        "clinical_status": status, "is_disorder": display.endswith("(disorder)"),
    }


FIXTURE_CONDITIONS = [
    cond("c1", "431855005", "Chronic kidney disease stage 1 (disorder)", "2015-01-01"),
    cond("c2", "431856006", "Chronic kidney disease stage 2 (disorder)", "2018-01-01"),
    cond("c3", "433144002", "Chronic kidney disease stage 3 (disorder)", "2022-01-01"),
    cond("d1", "714628002", "Prediabetes (finding)", "2010-01-01"),
    cond("d2", "44054006", "Diabetes mellitus type 2 (disorder)", "2013-01-01"),
    cond("s1", "266948004", "Has a criminal record (finding)", "2000-01-01"),
    cond("g1", "90560007", "Gout", "2019-01-01"),
    cond("t1", "698306007", "Awaiting transplantation of kidney (situation)", "2023-01-01"),
    cond("t2", "161665007", "History of renal transplant (situation)", "2024-06-01"),
    cond("r1", "10509002", "Acute bronchitis (disorder)", "2021-01-01",
         status="resolved", abated="2021-02-01"),
    cond("n1", "49436004", "Atrial fibrillation (disorder)", "2026-06-01"),
]

from datetime import date


def enc(id, day, cls="AMB", type="General examination of patient (procedure)"):
    t = datetime.fromisoformat(f"{day}T09:00:00+00:00")
    return {"id": id, "patient_id": "p1", "start_at": t, "end_at": t, "class": cls, "type": type}


def med(id, rx, display, day, status="active"):
    return {"id": id, "patient_id": "p1", "encounter_id": None, "rxnorm": rx, "display": display,
            "status": status, "authored_at": datetime.fromisoformat(f"{day}T09:00:00+00:00")}


FIXTURE_PATIENT = {"id": "p1", "name": "Test Patient", "birth_date": date(1964, 5, 1), "sex": "male"}

FIXTURE_ENCOUNTERS = [
    enc("v1", "2026-01-10"),
    enc("v2", "2026-04-10"),                                               # the last real visit
    enc("x1", "2026-05-20", type="Outpatient procedure (procedure)"),       # dialysis-like: NOT a visit
    enc("er1", "2026-06-02", cls="EMER", type="Emergency room admission (procedure)"),
]

FIXTURE_MEDS = [
    med("m1", "6809", "metformin", "2020-01-01"),
    med("m2", "6809", "metformin", "2026-01-10"),              # a refill, not a new start
    med("m3", "9997", "spironolactone", "2026-05-01"),         # started after the last visit
    med("m4", "29046", "lisinopril", "2019-01-01", status="stopped"),
]