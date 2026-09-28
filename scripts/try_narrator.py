"""Run the narrator N times on one patient's facts and count how often it passes.

    uv run python scripts/briefing_facts.py Ravi > ravi_facts.json
    uv run python scripts/try_narrator.py ravi_facts.json --runs 10 --temperature 0.7

Temperature 0 (what production uses) gives nearly the same text every run, so also run at
0.7 to see how the verifier copes with variation.
"""
import argparse
import json
from collections import Counter

from copilot.briefing.fallback import context_lines
from copilot.briefing.narrate import default_llm, narrate
from copilot.briefing.narrator_input import narrator_input

ap = argparse.ArgumentParser()
ap.add_argument("facts_file")
ap.add_argument("--runs", type=int, default=5)
ap.add_argument("--temperature", type=float, default=0.0)
args = ap.parse_args()

facts = json.load(open(args.facts_file))
ni = narrator_input(facts)
llm = default_llm(args.temperature)
statuses, problems, secs = Counter(), Counter(), []

for i in range(args.runs):
    out = narrate(ni, llm=llm)
    statuses[out["status"]] += 1
    secs += [a["seconds"] for a in out["attempts"]]
    for a in out["attempts"]:
        for v in a["violations"]:
            problems[v["problem"].split(" '")[0].split(" 2")[0]] += 1
    print(f"\n=== run {i + 1}: {out['status']} ===")
    for n, a in enumerate(out["attempts"], 1):
        print(f"--- attempt {n} ({a['seconds']}s) ---\n{a['text']}")
        for v in a["violations"]:
            print(f"  ✗ {v['problem']}\n      in: {v['sentence']}")
    if out["added"]:
        print("--- code added ---\n" + "\n".join(out["added"]))
    if out["status"] == "fallback":
        print(f"--- fallback text ---\n{out['text']}")

print("\n=== what the doctor sees (last run) ===")
print("\n".join([out["text"], *context_lines(facts)]))

n = args.runs
first = statuses["verified"]
print(f"\n==== {n} runs at temperature {args.temperature} ====")
print(f"passed first try:     {first}/{n}")
print(f"passed after retry:   {first + statuses['verified_after_retry']}/{n}")
print(f"model draft + code added missing items: {statuses['verified_with_additions']}/{n}")
print(f"fell back to template: {statuses['fallback']}/{n}")
print(f"nothing changed, no model call: {statuses['no_changes']}/{n}")
print(f"avg seconds per call: {sum(secs) / max(len(secs), 1):.1f}")
print("most common problems:", problems.most_common(5))
