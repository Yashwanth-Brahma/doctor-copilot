# scripts/checks.py
import json
import sys
from collections import defaultdict
from pathlib import Path

from copilot.ingest.fhir import parse_bundle

files = sorted(f for f in Path("data/synthea/fhir").glob("*.json")
               if not f.name.startswith(("hospital", "practitioner")))

# 1. living demo candidates
print("DEMO CANDIDATES (alive, diabetes + kidney disease)")
for f in files:
    rows = parse_bundle(json.loads(f.read_text()))
    p = rows["patients"][0]
    names = " ".join(c["display"].lower() for c in rows["conditions"])
    if p["deceased"] or "diabet" not in names or "kidney" not in names:
        continue
    egfr = sum(1 for o in rows["observations"] if o["concept"] == "egfr")
    print(f"  {p['name']:28} encounters={len(rows['encounters']):4}  egfr={egfr:4}  {f.name}")

# 2. how a single patient's data behaves
rows = parse_bundle(json.loads(Path(sys.argv[1]).read_text()))

print("\nKIDNEY / DIABETES CONDITIONS (all statuses, by onset)")
keywords = ("kidney", "renal", "diabet", "albumin", "proteinuria")
for c in sorted(rows["conditions"], key=lambda c: c["onset_at"]):
    if any(k in c["display"].lower() for k in keywords):
        print(f"  {c['code']:12} {c['clinical_status']:9} "
              f"onset={c['onset_at'].date()}  abated={c['abated_at'] and c['abated_at'].date()}  "
              f"{c['display']}")

print("\nSAME-DAY DUPLICATE CODES")
for concept in ("creatinine", "glucose", "potassium"):
    per_day = defaultdict(set)
    for o in rows["observations"]:
        if o["concept"] == concept:
            per_day[o["effective_at"].date()].add(o["loinc"])
    both = sum(1 for codes in per_day.values() if len(codes) > 1)
    print(f"  {concept:11} {len(per_day)} days measured, {both} days with both codes")