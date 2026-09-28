import asyncio
import json
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from copilot import tools as T
from copilot.api import create_app
from copilot.qa.agent import MAX_TOOL_CALLS, UNVERIFIED, ask_events, build_qa_graph
from copilot.qa.check import check_answer
from copilot.qa.gate import REDIRECTS, GateDecision
from tests.test_tools import RECORDS


# --- fakes -----------------------------------------------------------------------------

class FakeAgent:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.calls.append(list(messages))
        return self.replies.pop(0)


class FakeGate:
    def __init__(self, category="record_question"):
        self.category = category

    def with_structured_output(self, schema):
        gate = self

        class Runner:
            async def ainvoke(self, messages):
                return GateDecision(category=gate.category, reason="test")
        return Runner()


def lab_series(patient_id: str, lab: str, since: str | None = None) -> dict:
    """Every result for one lab."""
    return T.get_lab_series(RECORDS if patient_id == "p1" else {"observations": []}, lab, since)


TOOLS = [StructuredTool.from_function(lab_series, name="get_lab_series")]


def call(tool="get_lab_series", **args):
    return AIMessage("", tool_calls=[{"name": tool, "args": args, "id": f"c{len(args)}"}])


GOOD = "Creatinine rose from 1.55 mg/dL (2026-04-01) to 1.9 mg/dL (2026-09-21) [c3, c4]."


def run(replies, category="record_question", question="How has creatinine changed?"):
    agent = FakeAgent(replies)
    graph = build_qa_graph(TOOLS, agent, FakeGate(category))
    state = asyncio.run(graph.ainvoke({"patient_id": "p1", "question": question}))
    return state, agent


# --- gate --------------------------------------------------------------------------------

def test_advice_request_is_redirected_without_touching_tools():
    state, agent = run([], category="advice_request", question="Should I stop spironolactone?")
    assert state["status"] == "redirected" and state["answer"] == REDIRECTS["advice_request"]
    assert agent.calls == [] and state.get("trace", []) == []


# --- agent + tools -----------------------------------------------------------------------

def test_answer_from_tool_results_is_verified():
    state, _ = run([call(patient_id="p1", lab="creatinine"), AIMessage(GOOD)])
    assert state["status"] == "verified" and state["answer"] == GOOD
    assert state["trace"][0]["tool"] == "get_lab_series"


def test_agent_is_told_todays_date():
    # It passed since=2023-01-01 for "last year" when it didn't know the date.
    agent = FakeAgent([call(patient_id="p1", lab="creatinine"), AIMessage(GOOD)])
    graph = build_qa_graph(TOOLS, agent, FakeGate(), today=lambda: __import__("datetime").date(2026, 9, 29))
    asyncio.run(graph.ainvoke({"patient_id": "p1", "question": "Creatinine last year?"}))
    assert "Today is 2026-09-29" in agent.calls[0][0].content


def test_agent_cannot_read_another_patient():
    state, _ = run([call(patient_id="someone-else", lab="creatinine"), AIMessage(GOOD)])
    t = state["trace"][0]
    assert t["args"]["patient_id"] == "p1" and t["patient_id_overridden"] is True
    assert [p["source"] for p in t["result"]["points"]] == ["c1", "c3", "c4"]


def test_invented_value_gets_one_retry_with_the_problems():
    bad = AIMessage("Creatinine rose to 2.3 mg/dL (2026-09-21) [c4].")
    state, agent = run([call(patient_id="p1", lab="creatinine"), bad, AIMessage(GOOD)])
    assert state["status"] == "verified" and len(state["checks"]) == 2
    assert "value 2.3 is not in any tool result" in agent.calls[-1][-1].content


def test_two_bad_answers_are_withheld():
    bad = AIMessage("Creatinine is 2.3 mg/dL [c4].")
    state, _ = run([call(patient_id="p1", lab="creatinine"), bad, bad])
    assert state["status"] == "unverified" and state["answer"] == UNVERIFIED


def test_tool_call_limit():
    # a real model returns a new message each time (a reused object would be de-duplicated by id)
    state, _ = run([call(patient_id="p1", lab="creatinine") for _ in range(MAX_TOOL_CALLS + 1)])
    assert len(state["trace"]) == MAX_TOOL_CALLS and state["status"] == "unverified"


def test_unknown_tool_is_reported_to_the_agent_not_crashed():
    state, _ = run([call(tool="delete_patient", patient_id="p1"), AIMessage("The record has no such data.")])
    assert "unknown tool" in state["trace"][0]["result"]["error"]
    assert state["status"] == "verified"


# --- answer checker ----------------------------------------------------------------------

RESULT = lab_series("p1", "creatinine")


def problems(answer, question="How has creatinine changed?"):
    return [p["problem"] for p in check_answer(answer, [RESULT], question)]


def test_check_passes_grounded_answer():
    assert problems(GOOD) == []


def test_check_requires_a_citation_for_values():
    assert problems("Creatinine was 1.9 mg/dL (2026-09-21).") == ["gives values without citing a source id"]


def test_check_rejects_invented_citation():
    assert problems("Creatinine was 1.9 mg/dL (2026-09-21) [obs-999].") == \
        ["cites 'obs-999', which is not a source id from any tool result"]


def test_check_rejects_calculated_values_and_interpretation():
    assert "value 22.6 is not in any tool result" in problems("Creatinine rose 22.6% [c3, c4].")
    assert any("interpretation" in p for p in problems("Kidney function is worsening [c4]."))


def test_values_from_the_question_are_allowed():
    assert problems("There are no creatinine results after 2026-10-01.", "Any creatinine after 2026-10-01?") == []


# --- streaming events --------------------------------------------------------------------

def test_events_arrive_in_order():
    graph = build_qa_graph(TOOLS, FakeAgent([call(patient_id="p1", lab="creatinine"), AIMessage(GOOD)]), FakeGate())

    async def collect():
        return [e async for e in ask_events(graph, "p1", "How has creatinine changed?")]
    types = [e["type"] for e in asyncio.run(collect())]
    assert types == ["start", "gate", "tool_calls", "tool_result", "check", "answer", "done"]


# --- API ---------------------------------------------------------------------------------

def api(replies):
    @asynccontextmanager
    async def qa_graph():
        yield build_qa_graph(TOOLS, FakeAgent(replies), FakeGate())
    app = create_app(lambda pid: RECORDS if pid == "p1" else None, lambda: [], llm=object(),
                     compute=lambda *a, **k: None, qa_graph=qa_graph)
    return TestClient(app)


def test_ask_endpoint_streams_server_sent_events():
    r = api([call(patient_id="p1", lab="creatinine"), AIMessage(GOOD)]).post(
        "/patients/p1/ask", json={"question": "How has creatinine changed?"})
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    assert r.headers["content-type"].startswith("text/event-stream")
    assert events[-2] == {"type": "answer", "text": GOOD, "status": "verified"}


def test_ask_unknown_patient_is_404():
    assert api([]).post("/patients/nobody/ask", json={"question": "Any labs?"}).status_code == 404


# --- real MCP connection -----------------------------------------------------------------

def test_agent_tools_over_a_real_mcp_connection():
    """Spawns tests/stub_mcp_server.py as a real MCP server and calls a tool through the
    LangChain MCP adapter, exactly as the app does."""
    from copilot.qa.check import as_data
    from copilot.qa.mcp_client import mcp_tools, server_config

    async def go():
        async with mcp_tools(server_config(["-m", "tests.stub_mcp_server"])) as tools:
            by_name = {t.name: t for t in tools}
            assert set(by_name) == {"get_patient_summary", "get_changes_since_last_visit", "get_lab_series"}
            return as_data(await by_name["get_lab_series"].ainvoke({"patient_id": "p1", "lab": "creatinine"}))
    result = asyncio.run(go())
    assert [p["source"] for p in result["points"]] == ["c1", "c3", "c4"]
    assert check_answer(GOOD, [result], "How has creatinine changed?") == []
