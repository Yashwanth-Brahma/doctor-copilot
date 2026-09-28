import json
import sys
from collections import Counter
from pathlib import Path

from copilot.ingest.fhir import parse_bundle, time_shift

path = Path(sys.argv[1])
rows = parse_bundle(json.loads(path.read_text()))
offset = time_shift(rows)

print("rows per table:", {t: len(v) for t, v in rows.items()})
print("deceased:", rows["patients"][0]["deceased"])
print("time shift (days):", offset)

enc = sorted(e["start_at"] for e in rows["encounters"] if e["start_at"])
print("encounters:", enc[0].date(), "→", enc[-1].date())

active = sorted({c["display"] for c in rows["conditions"]
                 if c["clinical_status"] == "active" and c["abated_at"] is None and c["is_disorder"]})
print(f"\nactive disorders ({len(active)}):")
for a in active:
    print("  ", a)

print("\nlab concepts:", dict(Counter(o["concept"] for o in rows["observations"] if o["concept"])))
print("observation categories:", dict(Counter(o["category"] for o in rows["observations"])))
print("prescriptions with no drug code:", sum(1 for m in rows["medications"] if not m["rxnorm"]))