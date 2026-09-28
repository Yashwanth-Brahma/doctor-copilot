import os
import psycopg
from dotenv import load_dotenv

load_dotenv()
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    ext = conn.execute("select extname from pg_extension where extname = 'vector'").fetchall()
    tables = conn.execute(
        "select table_name from information_schema.tables where table_schema = 'public' order by 1"
    ).fetchall()
    print("pgvector:", ext)
    print("tables:", [t[0] for t in tables])