"""Run the full briefing graph and the three tools for one patient, against Supabase + Ollama.

    uv run python scripts/try_briefing.py demo-ravi-kumar
"""
import json
import sys
from datetime import date

from copilot import tools
from copilot.briefing.graph import briefing_response, build_briefing_graph
from copilot.db import connect, load_records, records_loader

pid = sys.argv[1] if len(sys.argv) > 1 else "demo-ravi-kumar"
today = date.today()

print("=== briefing graph (step by step) ===")
graph = build_briefing_graph(records_loader())
state = {}
for mode, chunk in graph.stream({"patient_id": pid, "today": today},
                                stream_mode=["updates", "values"]):
    if mode == "values":
        state = chunk                      # full state after each step
        continue
    for node, update in chunk.items():
        extra = ""
        if node == "write":
            a = update["attempts"][-1]
            extra = f"({a['seconds']}s, {len(a['violations'])} problems)"
        print(f"  ✓ {node} {extra}")
r = briefing_response(state)
print(f"\nstatus: {r['status']} after {r['attempts']} attempt(s)\n\n{r['text']}\n")
print("limitations:", r["limitations"])

with connect() as conn:
    records = load_records(conn, pid)
print("\n=== get_changes_since_last_visit ===")
print(json.dumps(tools.get_changes_since_last_visit(records, today), indent=1, default=str)[:1500])
print("\n=== get_lab_series('eGFR') ===")
print(json.dumps(tools.get_lab_series(records, "eGFR"), indent=1))
print("\n=== get_patient_summary (latest labs) ===")
print(json.dumps(tools.get_patient_summary(records, today)["latest_labs"], indent=1))
