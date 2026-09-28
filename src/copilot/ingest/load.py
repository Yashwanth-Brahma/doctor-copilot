from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from copilot.ingest.fhir import parse_bundle, time_shift

COLUMNS = {
    "patients":     ["id", "name", "birth_date", "sex"],
    "encounters":   ["id", "patient_id", "start_at", "end_at", "class", "type"],
    "conditions":   ["id", "patient_id", "code", "display", "onset_at", "abated_at",
                     "clinical_status", "is_disorder"],
    "medications":  ["id", "patient_id", "encounter_id", "rxnorm", "display", "status",
                     "authored_at"],
    "observations": ["id", "patient_id", "encounter_id", "category", "loinc", "concept",
                     "display", "value", "unit", "effective_at", "ref_low", "ref_high"],
}
ORDER = ["patients", "encounters", "conditions", "medications", "observations"]   # parents first


def patient_files(folder: Path) -> list[Path]:
    return sorted(f for f in folder.glob("*.json")
                  if not f.name.startswith(("hospital", "practitioner")))


def copy_rows(cur: psycopg.Cursor, table: str, rows: list[dict]) -> None:
    cols = COLUMNS[table]
    with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as copy:
        for r in rows:
            copy.write_row([r[c] for c in cols])


def main(folder: str = "data/synthea/fhir") -> None:
    load_dotenv()
    files = patient_files(Path(folder))
    loaded = skipped = 0
    totals = dict.fromkeys(ORDER, 0)

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        # full reload every run: simple, repeatable, and cheap at this size
        conn.execute("truncate patients, encounters, conditions, medications, observations cascade")
        conn.commit()

        for i, f in enumerate(files, 1):
            rows = parse_bundle(json.loads(f.read_text()))
            if not rows["patients"] or rows["patients"][0]["deceased"]:
                skipped += 1
                print(f"[{i}/{len(files)}] skip (deceased)")
                continue

            time_shift(rows)
            with conn.cursor() as cur:
                for table in ORDER:
                    copy_rows(cur, table, rows[table])
                    totals[table] += len(rows[table])
            conn.commit()                      # one transaction per patient
            loaded += 1
            print(f"[{i}/{len(files)}] {rows['patients'][0]['name']}")

    print(f"\nloaded {loaded} patients, skipped {skipped} deceased")
    print("rows:", totals)


if __name__ == "__main__":
    main(*sys.argv[1:])