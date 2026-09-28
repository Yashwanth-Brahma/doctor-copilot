"""HTTP API for the React UI.

    GET /health
    GET /patients                   demo patient first, then Synthea patients
    GET /patients/{id}/briefing     runs the briefing graph (~8 s with local MedGemma)
        ?debug=true                 also returns each model draft and why it was rejected
    POST /patients/{id}/ask         {"question": "..."}; streams the Q&A agent's steps as
                                    server-sent events: gate, tool_calls, tool_result, check, answer

    uv run uvicorn copilot.api:default_app --factory --reload

Public-demo protection (settings in .env, see Guards.from_env): briefings are cached per patient
per day; each visitor has a per-minute limit; model-backed requests have a daily budget.

The briefing endpoint calls the graph directly, not through MCP: it's our own code calling our
own functions. MCP is for the agent, which chooses tools at run time (Session 3).
"""
import json
import os
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .briefing.graph import briefing_response, build_briefing_graph
from .facts.compute import compute_facts
from .guard import DailyBudget, RateLimiter, client_ip


def _age(birth: date | None, today: date) -> int | None:
    if birth is None:
        return None
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


@dataclass
class Guards:
    """None = no limit (tests, local dev)."""
    briefing_rate: RateLimiter | None = None
    ask_rate: RateLimiter | None = None
    briefing_budget: DailyBudget | None = None
    ask_budget: DailyBudget | None = None

    @classmethod
    def from_env(cls) -> "Guards":
        def n(name, default):
            return int(os.environ.get(name, default))
        return cls(RateLimiter(n("BRIEFINGS_PER_MINUTE", 10)), RateLimiter(n("QUESTIONS_PER_MINUTE", 5)),
                   DailyBudget(n("DAILY_BRIEFING_LIMIT", 300)), DailyBudget(n("DAILY_QUESTION_LIMIT", 200)))


def _check(rate: RateLimiter | None, budget: DailyBudget | None, request: Request, what: str):
    if rate and not rate.allow(client_ip(request.headers, request.client and request.client.host)):
        raise HTTPException(429, f"Too many {what} in a minute. Please wait a moment.")
    if budget and not budget.try_spend():
        raise HTTPException(429, f"The demo's daily limit for {what} has been reached. Try again tomorrow.")


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def create_app(load_records: Callable[[str], dict | None], list_patients: Callable[[], list[dict]],
               llm=None, today: Callable[[], date] = date.today,
               compute: Callable = compute_facts, qa_graph=None, narrator: str | None = None,
               guards: Guards | None = None) -> FastAPI:
    """qa_graph: an async context manager that yields a compiled Q&A graph (connects to MCP).
    narrator: the name shown as author of model-written briefing lines."""
    guards = guards or Guards()
    cache: OrderedDict = OrderedDict()              # (patient_id, day) -> briefing response
    CACHE_SIZE = 500
    app = FastAPI(title="Doctor Copilot")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("ALLOWED_ORIGINS").split(","),
        allow_methods=["GET", "POST"], allow_headers=["*"],
    )
    graph = build_briefing_graph(load_records, llm=llm, compute=compute)

    @app.get("/health")
    def health():
        status = getattr(llm, "status", None)          # narrator with fallback reports its state
        return {"ok": True, **({"narrator": status()} if status else {})}

    @app.get("/patients")
    def patients():
        t = today()
        return [{"id": p["id"], "name": p["name"], "sex": p["sex"], "age": _age(p["birth_date"], t)}
                for p in list_patients()]

    @app.get("/patients/{patient_id}/briefing")
    def briefing(patient_id: str, request: Request, debug: bool = False):
        # sync def: FastAPI runs it in a worker thread, so a slow model call
        # doesn't block other requests
        key = (patient_id, today())
        if not debug and key in cache:              # written once per patient per day
            cache.move_to_end(key)
            return cache[key] | {"cached": True}
        _check(guards.briefing_rate, guards.briefing_budget, request, "briefings")
        try:
            state = graph.invoke({"patient_id": patient_id, "today": key[1]})
        except LookupError:
            raise HTTPException(404, f"No patient with id '{patient_id}'")
        response = briefing_response(state, debug=debug, narrator=narrator)
        if not debug:
            cache[key] = response
            while len(cache) > CACHE_SIZE:
                cache.popitem(last=False)
        return response | {"cached": False}

    @app.post("/patients/{patient_id}/ask")
    async def ask(patient_id: str, body: Ask, request: Request):
        from .qa.agent import ask_events
        if qa_graph is None:
            raise HTTPException(503, "Q&A agent is not configured")
        if load_records(patient_id) is None:
            raise HTTPException(404, f"No patient with id '{patient_id}'")
        _check(guards.ask_rate, guards.ask_budget, request, "questions")

        async def events():
            try:
                async with qa_graph() as graph:
                    async for event in ask_events(graph, patient_id, body.question):
                        yield f"data: {json.dumps(event, default=str)}\n\n"
            except Exception as e:                  # the stream is already open: report, don't crash
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


def default_app() -> FastAPI:
    """The real app: Supabase, the narrator from .env, OpenAI agent. Tests use create_app() with fakes."""
    from .db import connect, list_patients, records_loader

    def patients():
        with connect() as conn:
            return list_patients(conn)

    from .qa.agent import build_qa_graph
    from .qa.mcp_client import mcp_tools
    from .qa.models import agent_llm, gate_llm
    agent, gate = agent_llm(), gate_llm()          # fail at start-up if a setting is missing

    @asynccontextmanager
    async def qa_graph():
        async with mcp_tools() as tools:            # one MCP server process per question
            yield build_qa_graph(tools, agent, gate)

    from .briefing.narrate import default_llm, narrator_name
    return create_app(records_loader(), patients, llm=default_llm(), qa_graph=qa_graph,
                      narrator=narrator_name(), guards=Guards.from_env())

