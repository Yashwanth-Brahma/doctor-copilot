from datetime import date

import pytest

from copilot.briefing.fallback import facts_only_text
from copilot.briefing.graph import briefing_response, build_briefing_graph
from tests.test_verify import CONTEXT, FACTS, GOOD, LABS_ONLY, NI, NOTHING_NEW, FakeLLM

TODAY = date(2026, 9, 28)
RECORDS = {"patient": {"id": "p1"}, "encounters": [], "conditions": [],
           "medications": [], "observations": []}


def run(replies, loader=lambda pid: RECORDS):
    llm = FakeLLM(replies)
    graph = build_briefing_graph(loader, llm=llm, compute=lambda *a, **k: FACTS)
    return graph.invoke({"patient_id": "p1", "today": TODAY}), llm


def test_graph_first_draft_passes():
    state, llm = run([GOOD])
    assert state["status"] == "verified" and state["text"].startswith(GOOD)
    assert len(llm.calls) == 1


def test_graph_retries_once_with_feedback():
    state, llm = run(["eGFR was 38 (2026-09-21).", GOOD])
    assert state["status"] == "verified_after_retry"
    assert len(state["attempts"]) == 2
    assert "belongs to HbA1c" in llm.calls[1][-1][1]


def test_graph_falls_back_after_two_failures():
    state, llm = run(["eGFR is 8.2.", "eGFR is 8.2."])
    assert state["status"] == "fallback"
    assert state["text"].startswith(facts_only_text(NI))
    assert len(llm.calls) == 2                      # never a third model call


def test_graph_adds_missing_item_without_retry():
    state, llm = run([LABS_ONLY])
    assert state["status"] == "verified_with_additions"
    assert state["added"] == ["Spironolactone was started on 2026-05-31."]
    assert len(llm.calls) == 1


def test_graph_unknown_patient():
    with pytest.raises(LookupError):
        run([GOOD], loader=lambda pid: None)


def test_response_carries_facts_and_limitations():
    state, _ = run([GOOD])
    r = briefing_response(state)
    assert r["status"] == "verified" and r["attempts"] == 1 and r["added"] == []
    assert r["facts"] is FACTS and r["limitations"] == FACTS["limitations"]


def test_every_ending_includes_context_lines():
    for replies in ([GOOD], [LABS_ONLY], ["eGFR is 8.2.", "eGFR is 8.2."]):
        state, _ = run(replies)
        assert state["text"].endswith("\n".join(CONTEXT))


def test_graph_nothing_new_skips_the_model():
    llm = FakeLLM([])                                   # would fail if called
    graph = build_briefing_graph(lambda pid: RECORDS, llm=llm, compute=lambda *a, **k: NOTHING_NEW)
    state = graph.invoke({"patient_id": "p1", "today": TODAY})
    assert state["status"] == "no_changes" and llm.calls == []
    assert state["text"].startswith("The last visit was on 2026-08-12.")
    assert "No active medications on record." in state["text"]
    assert briefing_response(state)["attempts"] == 0
