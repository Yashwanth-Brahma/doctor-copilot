from datetime import date

from fastapi.testclient import TestClient

from copilot.api import create_app
from tests.test_verify import FACTS, GOOD, LABS_ONLY, FakeLLM

RECORDS = {"patient": {"id": "p1"}, "encounters": [], "conditions": [],
           "medications": [], "observations": []}
PATIENTS = [{"id": "demo-ravi-kumar", "name": "Ravi Kumar", "sex": "male", "birth_date": date(1964, 5, 10)},
            {"id": "syn-1", "name": "Ana Lopez", "sex": "female", "birth_date": None}]


def client(replies):
    app = create_app(lambda pid: RECORDS if pid == "demo-ravi-kumar" else None,
                     lambda: PATIENTS, llm=FakeLLM(replies),
                     today=lambda: date(2026, 9, 28), compute=lambda *a, **k: FACTS)
    return TestClient(app)


def test_health():
    assert client([]).get("/health").json() == {"ok": True}


def test_patients_list_with_age():
    body = client([]).get("/patients").json()
    assert body[0] == {"id": "demo-ravi-kumar", "name": "Ravi Kumar", "sex": "male", "age": 62}
    assert body[1]["age"] is None                     # unknown birth date stays unknown


def test_briefing_returns_text_status_and_facts():
    r = client([GOOD]).get("/patients/demo-ravi-kumar/briefing")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "verified" and body["attempts"] == 1
    assert body["text"].startswith(GOOD)
    assert body["context"][0].startswith("Current medications:")
    assert body["facts"]["last_visit"]["date"] == "2026-04-01"


def test_briefing_marks_lines_added_by_code():
    body = client([LABS_ONLY]).get("/patients/demo-ravi-kumar/briefing").json()
    assert body["status"] == "verified_with_additions"
    assert body["added"] == ["Spironolactone was started on 2026-05-31."]


def test_unknown_patient_is_404():
    assert client([GOOD]).get("/patients/nobody/briefing").status_code == 404


def test_debug_shows_each_draft_and_why_it_was_rejected():
    body = client(["eGFR is 8.2.", GOOD]).get("/patients/demo-ravi-kumar/briefing?debug=true").json()
    assert [len(d["violations"]) > 0 for d in body["drafts"]] == [True, False]
    assert body["drafts"][0]["raw"] == "eGFR is 8.2."
    assert "drafts" not in client([GOOD]).get("/patients/demo-ravi-kumar/briefing").json()


# --- production: cache, limits, narrator ------------------------------------------------

from copilot.api import Guards
from copilot.guard import DailyBudget, RateLimiter


def prod_client(replies, guards=None):
    app = create_app(lambda pid: RECORDS if pid == "demo-ravi-kumar" else None, lambda: PATIENTS,
                     llm=FakeLLM(replies), today=lambda: date(2026, 9, 28),
                     compute=lambda *a, **k: FACTS, narrator="gpt-4.1-mini", guards=guards)
    return TestClient(app)


def test_briefing_says_which_model_wrote_it():
    body = prod_client([GOOD]).get("/patients/demo-ravi-kumar/briefing").json()
    assert body["narrator"] == "gpt-4.1-mini"


def test_briefing_is_written_once_per_patient_per_day():
    c = prod_client([GOOD])                     # only ONE model reply available
    first = c.get("/patients/demo-ravi-kumar/briefing").json()
    second = c.get("/patients/demo-ravi-kumar/briefing").json()
    assert first["cached"] is False and second["cached"] is True
    assert second["text"] == first["text"]


def test_visitor_rate_limit_returns_429():
    c = prod_client([GOOD, GOOD], Guards(briefing_rate=RateLimiter(1)))
    assert c.get("/patients/demo-ravi-kumar/briefing").status_code == 200
    assert c.get("/patients/demo-ravi-kumar/briefing?debug=true").status_code == 429


def test_daily_budget_returns_429_but_cached_briefings_still_work():
    c = prod_client([GOOD], Guards(briefing_budget=DailyBudget(1)))
    assert c.get("/patients/demo-ravi-kumar/briefing").status_code == 200
    assert c.get("/patients/demo-ravi-kumar/briefing").status_code == 200        # cache: free
    r = c.get("/patients/demo-ravi-kumar/briefing?debug=true")                   # needs the model
    assert r.status_code == 429 and "daily limit" in r.json()["detail"]
