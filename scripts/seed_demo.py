"""Curated demo patient with clinically coherent values.

Synthea's lab values are generated independently and can be implausible
(e.g. creatinine and eGFR rising together), so the demo uses a hand-built patient.
Dates are relative to today so the briefing always looks current."""
import os
from datetime import date, datetime, time, timedelta, timezone
import random

import psycopg
from dotenv import load_dotenv

from copilot.ingest.load import ORDER, copy_rows

PID = "demo-ravi-kumar"
TODAY = date.today()

VISITS = [-365, -270, -180]      # clinic visits; -180 is the last visit
PRE_VISIT_LABS = -7              # drawn a week before the upcoming visit


def at(offset: int) -> datetime:
    return datetime.combine(TODAY + timedelta(days=offset), time(9, 30), tzinfo=timezone.utc)


LABS = {  # concept: (loinc, unit, values at the three visits, pre-visit value)
    "hba1c":      ("4548-4",  "%",                [7.1, 7.2, 7.4],  8.2),
    "egfr":       ("33914-3", "mL/min/{1.73_m2}", [55, 52, 46],     38),
    "creatinine": ("2160-0",  "mg/dL",            [1.3, 1.4, 1.55], 1.9),
    "potassium":  ("2823-3",  "mmol/L",           [4.6, 4.7, 4.7],  5.2),
}

CONDITIONS = [  # (snomed, display, onset offset) — verify codes against your data
    ("44054006",  "Diabetes mellitus type 2 (disorder)",       -3300),
    ("59621000",  "Essential hypertension (disorder)",         -4700),
    ("433144002", "Chronic kidney disease stage 3 (disorder)", -700),
    ("49436004",  "Atrial fibrillation (disorder)",            -300),
]

MEDS = [  # (rxnorm ingredient, display, prescribed offset) — verify RxCUIs via RxNav
    ("6809",    "metformin",      -3200),
    ("29046",   "lisinopril",     -4600),
    ("1364430", "apixaban",       -290),
    ("9997",    "spironolactone", -120),   # started AFTER the last visit
]


def build_rows() -> dict[str, list[dict]]:
    rows = {t: [] for t in ORDER}
    rows["patients"].append({"id": PID, "name": "Ravi Kumar",
                             "birth_date": TODAY - timedelta(days=62 * 365 + 40), "sex": "male"})

    for i, off in enumerate(VISITS):
        rows["encounters"].append({
            "id": f"{PID}-enc-{i}", "patient_id": PID,
            "start_at": at(off), "end_at": at(off) + timedelta(minutes=30),
            "class": "AMB", "type": "General examination of patient (procedure)",
        })

    for code, display, onset in CONDITIONS:
        rows["conditions"].append({
            "id": f"{PID}-cond-{code}", "patient_id": PID, "code": code, "display": display,
            "onset_at": at(onset), "abated_at": None, "clinical_status": "active",
            "is_disorder": display.endswith("(disorder)"),
        })

    for rx, display, authored in MEDS:
        rows["medications"].append({
            "id": f"{PID}-med-{rx}", "patient_id": PID, "encounter_id": None,
            "rxnorm": rx, "display": display, "status": "active", "authored_at": at(authored),
        })

    for concept, (loinc, unit, visit_values, pre_value) in LABS.items():
        points = list(zip(VISITS, visit_values)) + [(random.randint(-100, -1), pre_value)]
        for j, (off, value) in enumerate(points):
            rows["observations"].append({
                "id": f"{PID}-obs-{concept}-{j}", "patient_id": PID,
                "encounter_id": f"{PID}-enc-{j}" if j < len(VISITS) else None,
                "category": "laboratory", "loinc": loinc, "concept": concept,
                "display": concept, "value": value, "unit": unit,
                "effective_at": at(off), "ref_low": None, "ref_high": None,
            })
    return rows


def main() -> None:
    load_dotenv()
    rows = build_rows()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for table in reversed(ORDER):                 # children first when deleting
            col = "id" if table == "patients" else "patient_id"
            conn.execute(f"delete from {table} where {col} = %s", (PID,))
        with conn.cursor() as cur:
            for table in ORDER:
                copy_rows(cur, table, rows[table])
        conn.commit()
    print("seeded", PID, {t: len(v) for t, v in rows.items()})


if __name__ == "__main__":
    main()