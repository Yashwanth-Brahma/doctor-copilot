"""Ask the Q&A agent a question from the terminal: real OpenAI, real MCP server, real Supabase.

    uv run python scripts/ask.py demo-ravi-kumar "How has potassium changed since spironolactone started?"
    uv run python scripts/ask.py demo-ravi-kumar --demo       # a fixed set of questions + summary
"""
import asyncio
import json
import sys
import time

from copilot.qa.agent import ask_events, build_qa_graph
from copilot.qa.mcp_client import mcp_tools
from copilot.qa.models import agent_llm, gate_llm

DEMO = [
    "How has potassium changed since spironolactone was started?",
    "What medications is he taking right now?",
    "What was his eGFR at each measurement?",
    "Has he been to the hospital or ER since the last visit?",
    "What was his cholesterol last year?",                       # not in the record
    "Should I stop the spironolactone?",                         # advice -> redirect
    "What's a good restaurant nearby?",                          # off topic -> redirect
]


def show(e):
    t = e["type"]
    if t == "gate":
        print(f"  gate: {e['category']} ({e['reason']})")
    elif t == "tool_calls":
        for c in e["calls"]:
            print(f"  → {c['tool']}({', '.join(f'{k}={v}' for k, v in c['args'].items())})")
    elif t == "tool_result":
        flag = "  ⚠ patient_id overridden" if e["patient_id_overridden"] else ""
        print(f"  ← {e['tool']} {e['seconds']}s: {json.dumps(e['result'])[:160]}…{flag}")
    elif t == "check":
        mark = "✓" if not e["problems"] else "✗"
        print(f"  check {e['attempt']}: {mark} " + "; ".join(p["problem"] for p in e["problems"]))
    elif t == "answer":
        print(f"\n  [{e['status']}] {e['text']}\n")
    elif t == "error":
        print(f"  ERROR: {e['message']}")


async def main(pid: str, questions: list[str]):
    agent, gate = agent_llm(), gate_llm()
    results = []
    async with mcp_tools() as tools:
        graph = build_qa_graph(tools, agent, gate)
        for q in questions:
            print(f"Q: {q}")
            t0, status, n_tools = time.perf_counter(), None, 0
            async for e in ask_events(graph, pid, q):
                show(e)
                n_tools += e["type"] == "tool_result"
                status = e.get("status", status)
            results.append((q, status, n_tools, time.perf_counter() - t0))
    if len(questions) > 1:
        print("==== summary ====")
        for q, status, n, secs in results:
            print(f"  {status:<11} {n} tool call(s) {secs:5.1f}s  {q}")


pid = sys.argv[1]
qs = DEMO if sys.argv[2:] == ["--demo"] else [" ".join(sys.argv[2:])]
asyncio.run(main(pid, qs))
