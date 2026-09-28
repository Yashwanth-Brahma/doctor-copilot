import json
import os
import sys

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from copilot.facts.labs import lab_facts
from copilot.facts.visits import last_visit

load_dotenv()
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
    p = conn.execute("select id, name from patients where name ilike %s",
                     (f"%{sys.argv[1]}%",)).fetchone()
    rows = conn.execute("select * from observations where patient_id = %s and concept is not null",
                        (p["id"],)).fetchall()
    encs = conn.execute("select * from encounters where patient_id = %s", (p["id"],)).fetchall()
    visit = last_visit(encs)
    last = visit["start_at"].date() if visit else None

print(p["name"], "| last visit:", last)
print(json.dumps(lab_facts(rows, last), indent=2))
# print(p["name"])
# print(json.dumps(lab_facts(rows), indent=2))