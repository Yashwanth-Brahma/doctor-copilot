import json
import os
import sys
from datetime import date

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from copilot.facts.compute import compute_facts

load_dotenv()
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
    p = conn.execute("select * from patients where name ilike %s", (f"%{sys.argv[1]}%",)).fetchone()

    def rows(table):
        return conn.execute(f"select * from {table} where patient_id = %s", (p["id"],)).fetchall()

    f = compute_facts(p, rows("encounters"), rows("conditions"),
                      rows("medications"), rows("observations"), today=date.today())

print(json.dumps(f, indent=2))