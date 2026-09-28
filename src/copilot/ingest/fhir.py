from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from copilot.ingest.concepts import concept_for

KEEP = {"Patient", "Encounter", "Condition", "MedicationRequest", "Observation"}   # rule 1
KEEP_OBS_CATEGORIES = {"laboratory", "vital-signs"}                                # rule 5


def ref_id(reference: str | None) -> str | None:
    """'urn:uuid:abc' or 'Patient/abc' → 'abc'."""
    if not reference:
        return None
    return reference.split(":")[-1].split("/")[-1]


def first_coding(concept: dict | None) -> dict:
    """FHIR codings are lists; take the first one safely."""
    codings = (concept or {}).get("coding") or []
    return codings[0] if codings else {}


def parse_dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def parse_bundle(bundle: dict) -> dict[str, list[dict]]:
    resources = [e["resource"] for e in bundle.get("entry", [])]
    # some prescriptions point to a separate Medication resource instead of carrying the code
    meds_by_id = {r["id"]: r for r in resources if r["resourceType"] == "Medication"}

    rows: dict[str, list[dict]] = {
        "patients": [], "encounters": [], "conditions": [], "medications": [], "observations": [],
    }

    for r in resources:
        t = r["resourceType"]
        if t not in KEEP:
            continue

        if t == "Patient":
            name = (r.get("name") or [{}])[0]
            given = " ".join(name.get("given", []))
            full = re.sub(r"\d+", "", f"{given} {name.get('family', '')}").strip()   # Synthea adds digits
            rows["patients"].append({
                "id": r["id"],
                "name": full,
                "birth_date": date.fromisoformat(r["birthDate"]),
                "sex": r.get("gender"),
                "deceased": bool(r.get("deceasedDateTime") or r.get("deceasedBoolean")),
            })

        elif t == "Encounter":
            period = r.get("period", {})
            rows["encounters"].append({
                "id": r["id"],
                "patient_id": ref_id(r.get("subject", {}).get("reference")),
                "start_at": parse_dt(period.get("start")),
                "end_at": parse_dt(period.get("end")),
                "class": (r.get("class") or {}).get("code"),
                "type": first_coding((r.get("type") or [{}])[0]).get("display"),
            })

        elif t == "Condition":
            c = first_coding(r.get("code"))
            display = c.get("display", "")
            rows["conditions"].append({
                "id": r["id"],
                "patient_id": ref_id(r["subject"]["reference"]),
                "code": c.get("code"),
                "display": display,
                "onset_at": parse_dt(r.get("onsetDateTime")),
                "abated_at": parse_dt(r.get("abatementDateTime")),
                "clinical_status": first_coding(r.get("clinicalStatus")).get("code"),
                "is_disorder": display.endswith("(disorder)"),              # rule 3, stored as a flag
            })

        elif t == "MedicationRequest":
            if "medicationCodeableConcept" in r:
                m = first_coding(r["medicationCodeableConcept"])
            else:
                med = meds_by_id.get(ref_id(r.get("medicationReference", {}).get("reference")), {})
                m = first_coding(med.get("code"))
            rows["medications"].append({
                "id": r["id"],
                "patient_id": ref_id(r["subject"]["reference"]),
                "encounter_id": ref_id(r.get("encounter", {}).get("reference")),
                "rxnorm": m.get("code"),
                "display": m.get("display"),
                "status": r.get("status"),
                "authored_at": parse_dt(r.get("authoredOn")),
            })

        elif t == "Observation":
            category = first_coding((r.get("category") or [{}])[0]).get("code")
            if category not in KEEP_OBS_CATEGORIES or "valueQuantity" not in r:
                continue                                # skips surveys and panel-style values like BP
            c = first_coding(r.get("code"))
            rr = (r.get("referenceRange") or [{}])[0]
            rows["observations"].append({
                "id": r["id"],
                "patient_id": ref_id(r["subject"]["reference"]),
                "encounter_id": ref_id(r.get("encounter", {}).get("reference")),
                "category": category,
                "loinc": c.get("code"),
                "concept": concept_for(c.get("code")),    # rule 4
                "display": c.get("display"),
                "value": r["valueQuantity"].get("value"),
                "unit": r["valueQuantity"].get("unit"),
                "effective_at": parse_dt(r.get("effectiveDateTime")),
                "ref_low": (rr.get("low") or {}).get("value"),
                "ref_high": (rr.get("high") or {}).get("value"),
            })

    return rows


DATETIME_FIELDS = {
    "encounters": ["start_at", "end_at"],
    "conditions": ["onset_at", "abated_at"],
    "medications": ["authored_at"],
    "observations": ["effective_at"],
}


def time_shift(rows: dict[str, list[dict]], days_before_today: int = 30,
               today: date | None = None) -> int:
    """Rule 6: move every date by the same offset so the last encounter is recent.
    Returns the offset in days."""
    today = today or date.today()
    starts = [e["start_at"] for e in rows["encounters"] if e["start_at"]]
    if not starts:
        return 0
    last = max(starts).date()
    offset = timedelta(days=(today - timedelta(days=days_before_today) - last).days)

    for table, fields in DATETIME_FIELDS.items():
        for row in rows[table]:
            for f in fields:
                if row[f] is not None:
                    row[f] = row[f] + offset
    for p in rows["patients"]:
        p["birth_date"] = p["birth_date"] + offset       # see note below
    return offset.days