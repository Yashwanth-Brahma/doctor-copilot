"""Run the briefing for every patient and count the outcomes.

    uv run python scripts/eval_briefings.py                 # replay: brief each patient FOR their last visit
    uv run python scripts/eval_briefings.py --mode today    # as of today (mostly "nothing changed")
    uv run python scripts/eval_briefings.py --limit 20

Replay is the realistic test: Synthea records end at each patient's last visit, so as of today
almost nobody has changes. Replay sets "today" to the date of the most recent visit, hides
everything recorded later, and compares with the visit before it (see copilot/replay.py).

Writes one JSON line per patient to eval/briefings-<mode>-<date>.jsonl (with every model draft
and its violations), then prints a summary and each fallback so it can be read and explained.
"""
import argparse
import json
import time
from collections import Counter
from datetime import date
from pathlib import Path

from copilot.briefing.graph import briefing_response, build_briefing_graph
from copilot.briefing.narrate import default_llm
from copilot.db import connect, list_patients, load_records
from copilot.facts.visits import last_visit
from copilot.replay import records_as_of, replay_day

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["replay", "today"], default="replay")
ap.add_argument("--limit", type=int)
args = ap.parse_args()

llm = default_llm()                    # fails here, before any patient, if NARRATOR_MODEL is missing
current: dict = {}                     # records for the patient being briefed
graph = build_briefing_graph(lambda pid: current.get(pid), llm=llm)

out_path = Path("eval") / f"briefings-{args.mode}-{date.today()}.jsonl"
out_path.parent.mkdir(exist_ok=True)
statuses, problems, model_seconds, rows = Counter(), Counter(), [], []
t_start = time.perf_counter()

with connect() as conn, out_path.open("w") as f:
    patients = list_patients(conn)[: args.limit]
    for i, p in enumerate(patients, 1):
        try:
            records = load_records(conn, p["id"])
            day = date.today()
            if args.mode == "replay":
                day = replay_day(records, last_visit)
                if day is None:
                    raise LookupError("no clinic visit to replay")
                records = records_as_of(records, day)
            current.clear()
            current[p["id"]] = records
            state = graph.invoke({"patient_id": p["id"], "today": day})
            r = briefing_response(state, debug=True) | {"as_of": str(day)}
        except Exception as e:                      # one bad record must not stop the run
            r = {"patient_id": p["id"], "status": f"error: {type(e).__name__}: {e}", "drafts": []}
        statuses[r["status"]] += 1
        for d in r["drafts"]:
            model_seconds.append(d["seconds"])
            for v in d["violations"]:
                problems[v["problem"].split(" '")[0].split(" 2")[0]] += 1
        f.write(json.dumps(r, default=str) + "\n")
        rows.append(r)
        print(f"[{i:3}/{len(patients)}] {r['status']:<24} {r.get('as_of', ''):<11} {p['name']}")

n = len(patients)
print(f"\n==== {n} patients, mode={args.mode}, {time.perf_counter() - t_start:.0f}s total ====")
for status, count in statuses.most_common():
    print(f"  {status:<26} {count:3}  ({100 * count / n:.0f}%)")
called = sum(1 for r in rows if r["drafts"])
if called:
    first = sum(1 for r in rows if r["status"] == "verified")
    print(f"\nmodel called for {called} patients: verified first try {first}/{called}, "
          f"avg {sum(model_seconds) / len(model_seconds):.1f}s per call")
print("most common problems:", problems.most_common(8))

for r in rows:
    if r["status"] == "fallback" or r["status"].startswith("error"):
        print(f"\n--- {r['status']}: {r['patient_id']}")
        for k, d in enumerate(r["drafts"], 1):
            print(f"  draft {k}: " + d["raw"].strip().replace("\n", " | ")[:400])
            for v in d["violations"]:
                print(f"    ✗ {v['problem']}  ←  {v['sentence'][:120]}")
print(f"\nfull results: {out_path}")
