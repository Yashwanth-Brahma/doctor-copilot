"""Replays of real MedGemma drafts from the replay eval on 101 Synthea patients (2026-09-28).
3 of the 5 fallbacks were the checker's fault; 2 were the model inventing a hospital visit."""
from copilot.briefing.narrate import finish, next_step
from copilot.briefing.verify import verify


def ni(last_visit, meds=(), conditions=(), events=()):
    return {"as_of": "2026-09-01", "last_visit": {"date": last_visit, "type": "Check up"},
            "labs_with_new_results": [],
            "new_medications": [{"name": n, "started": d} for n, d in meds],
            "new_conditions": [{"name": n, "onset": d} for n, d in conditions],
            "events_since_last_visit": [{"type": t, "date": d} for t, d in events]}


def sentence_problems(text, facts):
    return [v["problem"] for v in verify(text, facts) if v["sentence"] != "(whole briefing)"]


def outcome(text, facts):
    attempts = [{"text": text, "violations": verify(text, facts)}]
    return finish(facts, attempts, next_step(attempts))["status"]


YAZ = ("{24 (drospirenone 3 MG / ethinyl estradiol 0.02 MG Oral Tablet) / "
       "4 (inert ingredients 1 MG Oral Tablet) } Pack [Yaz 28 Day]")
YAZ_NI = ni("2025-12-06", meds=[(YAZ, "2026-08-25")], events=[("Emergency room admission", "2026-08-25")])


def test_regression_product_name_digits_and_brackets_belong_to_the_name():
    draft = ("The last visit was on 2025-12-06.\n"
             "Hospital or urgent care visit: Emergency room on 2026-08-25.\n"
             f"{YAZ} was started on 2026-08-25.")
    assert verify(draft, YAZ_NI) == []


def test_regression_brand_name_is_accepted_for_a_long_product():
    draft = "The last visit was on 2025-12-06.\nYaz 28 Day was started on 2026-08-25."
    assert sentence_problems(draft, YAZ_NI) == []
    assert outcome(draft, YAZ_NI) == "verified_with_additions"      # the ER visit is added by code


NUVA = "21 DAY ethinyl estradiol 0.000625 MG/HR / etonogestrel 0.005 MG/HR Vaginal System [NuvaRing]"
NUVA_NI = ni("2025-11-26", meds=[(NUVA, "2026-08-26")])


def test_regression_repeated_sentences_are_rejected():
    draft = "\n".join(["The last visit was on 2025-11-26."] * 3 + [f"{NUVA} was started on 2026-08-26."])
    assert sentence_problems(draft, NUVA_NI) == ["repeated sentence", "repeated sentence"]


def test_regression_long_product_name_with_decimals_passes():
    assert verify(f"The last visit was on 2025-11-26.\nNuvaRing was started on 2026-08-26.", NUVA_NI) == []


def test_regression_condition_name_containing_a_banned_word():
    # "diagnostic" is part of the condition's name, not the model interpreting.
    facts = ni("2026-08-20", conditions=[("Abnormal findings diagnostic imaging heart+coronary circulat", "2026-08-21")],
               events=[("Hospital admission", "2026-08-21")])
    draft = "The last visit was on 2026-08-20.\nHospital or urgent care visit: Hospital on 2026-08-21."
    assert outcome(draft, facts) == "verified_with_additions"


def test_regression_invented_hospital_visit_is_still_caught():
    # Real model error, twice: no event existed. This must keep failing.
    facts = ni("2026-08-11", conditions=[("Gingivitis", "2026-08-12")])
    draft = ("The last visit was on 2026-08-11.\n"
             "Hospital or urgent care visit: None on 2026-08-12.\n"
             "Gingivitis was recorded on 2026-08-12.")
    assert sentence_problems(draft, facts) == ["date 2026-08-12 with no named lab or medication"]
