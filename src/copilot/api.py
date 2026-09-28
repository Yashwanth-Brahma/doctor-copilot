"""HTTP API for the React UI.

    GET /health
    GET /patients                   demo patient first, then Synthea patients
    GET /patients/{id}/briefing     runs the briefing graph (~8 s with local MedGemma)
        ?debug=true                 also returns each model draft and why it was rejected
    POST /patients/{id}/ask         {"question": "..."}; streams the Q&A agent's steps as
                                    server-sent events: gate, tool_calls, tool_result, check, answer

    uv run uvicorn copilot.api:default_app --factory --reload

The briefing endpoint calls the graph directly, not through MCP: it's our own code calling our
own functions. MCP is for the agent, which chooses tools at run time (Session 3).
"""
import json
import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .briefing.graph import briefing_response, build_briefing_graph
from .facts.compute import compute_facts


def _age(birth: date | None, today: date) -> int | None:
    if birth is None:
        return None
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def create_app(load_records: Callable[[str], dict | None], list_patients: Callable[[], list[dict]],
               llm=None, today: Callable[[], date] = date.today,
               compute: Callable = compute_facts, qa_graph=None) -> FastAPI:
    """qa_graph: an async context manager that yields a compiled Q&A graph (connects to MCP)."""
    app = FastAPI(title="Doctor Copilot")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(","),
        allow_methods=["GET", "POST"], allow_headers=["*"],
    )
    graph = build_briefing_graph(load_records, llm=llm, compute=compute)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/patients")
    def patients():
        t = today()
        return [{"id": p["id"], "name": p["name"], "sex": p["sex"], "age": _age(p["birth_date"], t)}
                for p in list_patients()]

    @app.get("/patients/{patient_id}/briefing")
    def briefing(patient_id: str, debug: bool = False):
        # sync def: FastAPI runs it in a worker thread, so a slow model call
        # doesn't block other requests
        try:
            state = graph.invoke({"patient_id": patient_id, "today": today()})
        except LookupError:
            raise HTTPException(404, f"No patient with id '{patient_id}'")
        return briefing_response(state, debug=debug)

    @app.post("/patients/{patient_id}/ask")
    async def ask(patient_id: str, body: Ask):
        from .qa.agent import ask_events
        if qa_graph is None:
            raise HTTPException(503, "Q&A agent is not configured")
        if load_records(patient_id) is None:
            raise HTTPException(404, f"No patient with id '{patient_id}'")

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
    """The real app: Supabase + local MedGemma. Tests call create_app() with fakes instead."""
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

    return create_app(records_loader(), patients, qa_graph=qa_graph)

