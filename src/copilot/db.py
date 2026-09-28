"""The only module that talks to Supabase. Everything else takes plain lists and dicts."""
import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()

TABLES = ("encounters", "conditions", "medications", "observations")


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def list_patients(conn) -> list[dict]:
    return conn.execute(
        "select id, name, birth_date, sex from patients order by (id like 'demo-%') desc, name"
    ).fetchall()


def load_records(conn, patient_id: str) -> dict | None:
    patient = conn.execute("select * from patients where id = %s", (patient_id,)).fetchone()
    if patient is None:
        return None
    records = {"patient": patient}
    for t in TABLES:
        records[t] = conn.execute(f"select * from {t} where patient_id = %s",
                                  (patient_id,)).fetchall()
    return records


def records_loader():
    """A load_records(patient_id) function with its own short connection, for the graph."""
    def load(patient_id: str) -> dict | None:
        with connect() as conn:
            return load_records(conn, patient_id)
    return load
