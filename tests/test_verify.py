import json

from copilot.briefing.fallback import complete_briefing, context_lines, facts_only_text
from copilot.briefing.narrate import clean_output, narrate
from copilot.briefing.narrator_input import narrator_input
from copilot.briefing.verify import verify


def _lab(concept, loinc, unit, base, latest, out):
    (bv, bd), (lv, ld) = base, latest
    return {
        "id": f"lab.{concept}", "concept": concept, "measurements": 3,
        "latest": {"value": lv, "unit": unit, "date": ld, "loinc": loinc, "fhir_id": f"obs-{concept}-2"},
        "baseline": {"value": bv, "unit": unit, "date": bd, "loinc": loinc, "fhir_id": f"obs-{concept}-1"},
        "latest_out_of_range": out, "new_since_last_visit": True,
        "change": round(lv - bv, 2), "direction": "up" if lv > bv else "down",
    }


# Different dates per lab on purpose, so a date attached to the wrong lab is detectable.
FACTS = {
    "as_of": "2026-09-28",
    "patient": {"id": "demo-ravi-kumar", "name": "Ravi Kumar", "age": 62, "sex": "male"},
    "last_visit": {"date": "2026-04-01", "type": "General examination of patient (procedure)",
                   "encounter_id": "demo-ravi-kumar-enc-2"},
    "problems": [
        {"id": "c1", "code": "44054006", "display": "Diabetes mellitus type 2 (disorder)", "onset": "2017-09-15"},
        {"id": "c2", "code": "433144002", "display": "Chronic kidney disease stage 3 (disorder)", "onset": "2024-10-28"},
    ],
    "new_conditions": [],
    "medications": {
        "active": [{"rxnorm": "9997", "display": "spironolactone", "first_prescribed": "2026-05-31", "fhir_id": "m1"},
                   {"rxnorm": "6809", "display": "metformin", "first_prescribed": "2017-12-24", "fhir_id": "m2"}],
        "new_since_last_visit": [{"rxnorm": "9997", "display": "spironolactone",
                                  "first_prescribed": "2026-05-31", "fhir_id": "m1"}],
        "stopped_since_last_visit": None,
    },
    "labs": [
        _lab("hba1c", "4548-4", "%", (7.4, "2026-04-01"), (8.2, "2026-09-21"), True),
        _lab("egfr", "33914-3", "mL/min/{1.73_m2}", (46.0, "2026-03-20"), (38.0, "2026-09-14"), True),
        {"id": "lab.glucose", "concept": "glucose", "measurements": 1,
         "latest": {"value": 110.0, "unit": "mg/dL", "date": "2025-11-02", "loinc": "2345-7", "fhir_id": "g1"},
         "baseline": None, "latest_out_of_range": True, "new_since_last_visit": False,
         "change": None, "direction": None},
    ],
    "events_since_last_visit": [],
    "limitations": [],
}
NI = narrator_input(FACTS)

GOOD = (
    "Since the last visit on 2026-04-01, HbA1c and eGFR have new results. "
    "HbA1c rose from 7.4% (2026-04-01) to 8.2% (2026-09-21), above the reference range. "
    "eGFR fell from 46 mL/min/1.73m² (2026-03-20) to 38 mL/min/1.73m² (2026-09-14). "
    "Spironolactone was started on 2026-05-31. "
    "Known problems include type 2 diabetes and CKD stage 3."
)


def problems(text):
    """Per-sentence problems only; coverage is tested separately below."""
    return [v["problem"] for v in verify(text, NI) if v["sentence"] != "(whole briefing)"]


# --- narrator input -------------------------------------------------------------

def test_narrator_input_has_no_identifiers_or_codes():
    blob = json.dumps(NI, ensure_ascii=False)
    for secret in ["Ravi", "demo-ravi", "4548-4", "33914-3", "fhir", "encounter_id", "rxnorm"]:
        assert secret not in blob


def test_narrator_input_only_what_to_write_in_order():
    # Current meds, problems and old labs are left out: with them in, MedGemma listed
    # current meds and skipped the new one.
    assert list(NI) == ["as_of", "last_visit", "labs_with_new_results", "new_medications",
                        "new_conditions", "events_since_last_visit"]
    assert [l["lab"] for l in NI["labs_with_new_results"]] == ["HbA1c", "eGFR"]   # no Glucose
    assert NI["labs_with_new_results"][1]["latest"]["unit"] == "mL/min/1.73m²"


# --- verifier ---------------------------------------------------------------------

def test_good_briefing_passes():
    assert problems(GOOD) == []


def test_invented_number_rejected():
    assert any("8.5" in p for p in problems("HbA1c rose to 8.5% (2026-09-21)."))


def test_regression_date_from_another_lab():
    # The MedGemma bug: HbA1c's date attached to eGFR.
    p = problems("eGFR was 38 (2026-09-21).")
    assert any("belongs to HbA1c" in x for x in p)


def test_regression_last_visit_date_on_lab_drawn_earlier():
    # eGFR's previous value was drawn 2026-03-20, not on the visit date.
    assert any("2026-04-01" in x for x in problems("eGFR was 46 (2026-04-01)."))


def test_value_from_another_lab_rejected():
    assert any("belongs to HbA1c" in x for x in problems("eGFR is now 8.2."))


def test_vague_date_phrase_rejected():
    assert any("vague" in p for p in problems("eGFR fell from 46 to 38 between those dates."))


def test_interpretation_rejected():
    assert any("interpretation" in p for p in
               problems("HbA1c rose to 8.2% (2026-09-21), suggesting worse control."))


def test_derived_percentage_rejected():
    # 8 is the real change, but "8%" turns it into a claim the facts don't make.
    assert any("percentage" in p for p in problems("eGFR fell 8% (2026-09-14)."))


def test_38_matches_38_0():
    assert problems("eGFR is 38.0 mL/min/1.73m² (2026-09-14).") == []
    assert problems("eGFR is 38 (2026-09-14).") == []


def test_two_labs_with_values_rejected():
    assert any("one lab per sentence" in p for p in problems("HbA1c is 8.2% and eGFR is 38."))


def test_value_without_named_lab_rejected():
    assert any("no named lab" in p for p in problems("It rose from 7.4 to 8.2."))


def test_non_iso_date_rejected():
    assert any("YYYY-MM-DD" in p for p in problems("HbA1c was 8.2% on September 21, 2026."))


def test_normal_claim_on_out_of_range_lab_rejected():
    assert any("normal" in p for p in problems("HbA1c is 8.2%, within the normal range."))


def test_missing_lab_rejected():
    # Accurate but incomplete: leaves out eGFR and the new medication.
    text = "Last visit 2026-04-01. HbA1c rose from 7.4% (2026-04-01) to 8.2% (2026-09-21)."
    missing = [v["problem"] for v in verify(text, NI) if v["sentence"] == "(whole briefing)"]
    assert missing == ["missing: eGFR with its latest value 38.0 (2026-09-14)",
                       "missing: spironolactone as new, with its start date 2026-05-31"]


def test_regression_new_med_named_but_not_called_new():
    # MedGemma run 7: listed spironolactone among current meds, never said it was new.
    text = GOOD.replace("Spironolactone was started on 2026-05-31. ",
                        "The patient is taking metformin and spironolactone. ")
    assert [v["problem"] for v in verify(text, NI)] == \
        ["missing: spironolactone as new, with its start date 2026-05-31"]


def test_missing_last_visit_date_rejected():
    text = GOOD.replace("Since the last visit on 2026-04-01, HbA1c", "HbA1c")
    text = text.replace("7.4% (2026-04-01)", "7.4%")
    assert [v["problem"] for v in verify(text, NI)] == ["missing: last visit date 2026-04-01"]


def test_fallback_always_passes_verifier():
    assert verify(facts_only_text(NI), NI) == []


# --- narrate loop (fake model, no Ollama needed) ---------------------------------------

class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def invoke(self, messages):
        self.calls.append(messages)
        return type("Msg", (), {"content": self.replies.pop(0)})()


def test_retry_gets_violations_then_passes():
    llm = FakeLLM(["eGFR was 38 (2026-09-21).", GOOD])
    out = narrate(NI, llm=llm)
    assert out["status"] == "verified_after_retry"
    assert "belongs to HbA1c" in llm.calls[1][-1][1]   # feedback was sent back


def test_two_failures_fall_back_to_template():
    out = narrate(NI, llm=FakeLLM(["eGFR is 8.2.", "eGFR is 8.2."]))
    assert out["status"] == "fallback"
    assert out["text"] == facts_only_text(NI)


# MedGemma's actual output in all 10 runs of 2026-09-28: every lab right, new medication missing.
LABS_ONLY = (
    "The last visit was on 2026-04-01.\n"
    "HbA1c rose from 7.4 % (2026-04-01) to 8.2 % (2026-09-21).\n"
    "eGFR fell from 46.0 mL/min/1.73m2 (2026-03-20) to 38.0 mL/min/1.73m2 (2026-09-14)."
)


def test_regression_missing_med_is_added_by_code_not_retried():
    llm = FakeLLM([LABS_ONLY])
    out = narrate(NI, llm=llm)
    assert out["status"] == "verified_with_additions"
    assert out["added"] == ["Spironolactone was started on 2026-05-31."]
    assert out["text"].startswith(LABS_ONLY.split("\n")[0])   # the model's correct draft is kept
    assert len(llm.calls) == 1                                    # no retry needed


def test_wrong_content_still_retries_even_if_something_is_also_missing():
    out = narrate(NI, llm=FakeLLM(["eGFR is 8.2.", GOOD]))
    assert out["status"] == "verified_after_retry"


def test_completed_briefing_always_passes_verifier():
    for draft in ["", "The last visit was on 2026-04-01.", LABS_ONLY]:
        text, added = complete_briefing(draft, NI)
        assert verify(text, NI) == [], draft


# --- output format (MedGemma answered in JSON in 6 of 10 runs) --------------------------

JSON_ANSWER = """```json
{
 "pre_visit_briefing": [
  "The last visit was on 2026-04-01.",
  "HbA1c rose from 7.4 % (2026-04-01) to 8.2 % (2026-09-21).",
  "eGFR fell from 46.0 mL/min/1.73m\\u00b2 (2026-03-20) to 38.0 mL/min/1.73m\\u00b2 (2026-09-14)."
 ],
 "new_medications": [{"name": "spironolactone", "started": "2026-05-31"}]
}
```"""


def test_regression_json_answer_is_turned_into_sentences():
    text = clean_output(JSON_ANSWER)
    assert text.splitlines()[0] == "The last visit was on 2026-04-01."
    assert "{" not in text and "```" not in text
    assert "1.73m²" in text                      # escaped \\u00b2 decoded


def test_regression_json_answer_ends_verified_with_the_missing_med_added():
    out = narrate(NI, llm=FakeLLM([JSON_ANSWER]))
    assert out["status"] == "verified_with_additions"
    assert out["added"] == ["Spironolactone was started on 2026-05-31."]


def test_raw_json_is_never_verified():
    assert any("not plain text" in p for p in problems('{"text": "HbA1c is 8.2%."}'))


def test_regression_escaped_superscript_is_not_a_number():
    assert problems("eGFR fell from 46 mL/min/1.73m\\u00b2 (2026-03-20) to 38 (2026-09-14).") == \
        ["not plain text (JSON, code or escape characters)"]
    assert problems(clean_output("eGFR fell from 46 mL/min/1.73m\\u00b2 (2026-03-20) to 38 (2026-09-14).")) == []


# --- context lines (current meds + problems, written by code) --------------------------

def test_context_lines_show_current_meds_and_problems():
    assert context_lines(FACTS) == [
        "Current medications: metformin, spironolactone (new since last visit).",
        "Known problems: Diabetes mellitus type 2, Chronic kidney disease stage 3.",
    ]
