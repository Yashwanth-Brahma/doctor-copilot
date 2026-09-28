"""The Q&A agent as a LangGraph graph.

    gate ──(advice / off topic)──────────────────────────────► redirect ─► END   no tools, no agent
      │
      └─(record question)─► agent ──(tool calls)──► tools ──┐
                              ▲                             │
                              └─────────────────────────────┘
                              │
                              └─(answer)─► check ──(clean)────────────────► END   "verified"
                                             └─(problems, 1st)─► agent            retry with problems
                                             └─(problems, 2nd)─► END              "unverified": answer withheld

Rules enforced in code, not in the prompt:
  - the tools node overwrites patient_id with the patient on screen: the agent cannot read
    another patient's record, whatever it asks for
  - at most MAX_TOOL_CALLS tool calls per question
  - the answer is shown only if check_answer() passes

Tools come in as LangChain tools: from the MCP server in the app (mcp_client.py), plain
functions in tests.
"""
import json
import operator
import time
from datetime import date
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from .check import as_data, check_answer
from .gate import REDIRECTS, classify

MAX_TOOL_CALLS = 6
MAX_ANSWER_ATTEMPTS = 2

AGENT_PROMPT = """You answer a clinician's questions about ONE patient's record, using only the tools.
The patient is already selected (patient_id: {patient_id}). Today is {today}; use it for
relative dates like "last year" or "in the past 6 months".

Rules:
- Always call a tool to get the data. Never answer from memory.
- Copy numbers and dates exactly as the tools return them. Dates as YYYY-MM-DD. Don't calculate
  percentages or new numbers.
- Every sentence that contains a number or date ends with the source ids it came from, in square
  brackets, e.g. [demo-ravi-kumar-obs-potassium-3]. Use only ids that appear as "source" in tool results.
- Describe what the record shows. No diagnosis, causes, risk or advice.
- If the record doesn't contain the answer, say so plainly.
- Plain sentences, at most 5. No headings, no bullet points, no JSON."""

UNVERIFIED = ("I couldn't write an answer I could verify against the record. "
              "The data the tools returned is shown in the trace.")


class QAState(TypedDict, total=False):
    patient_id: str
    question: str
    gate: dict
    messages: Annotated[list[AnyMessage], add_messages]
    trace: Annotated[list[dict], operator.add]        # every tool call, for the UI
    checks: Annotated[list[dict], operator.add]       # every answer check, for the UI
    answer: str
    status: str                                       # verified | redirected | unverified


def build_qa_graph(tools: list, agent_llm, gate_llm, today=date.today):
    by_name = {t.name: t for t in tools}
    model = agent_llm.bind_tools(tools)

    async def gate(state):
        d = await classify(state["question"], gate_llm)
        return {"gate": {"category": d.category, "reason": d.reason}}

    def after_gate(state):
        return "agent" if state["gate"]["category"] == "record_question" else "redirect"

    def redirect(state):
        return {"answer": REDIRECTS[state["gate"]["category"]], "status": "redirected"}

    async def agent(state):
        messages = state.get("messages") or []
        if not messages:
            messages = [SystemMessage(AGENT_PROMPT.format(patient_id=state["patient_id"], today=today().isoformat())),
                        HumanMessage(state["question"])]
            reply = await model.ainvoke(messages)
            return {"messages": [*messages, reply]}
        return {"messages": [await model.ainvoke(messages)]}

    def after_agent(state):
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None) and len(state.get("trace", [])) < MAX_TOOL_CALLS:
            return "tools"
        return "check"

    async def run_tools(state):
        out_messages, trace = [], []
        for call in state["messages"][-1].tool_calls:
            args = dict(call["args"])
            asked_for = args.get("patient_id")
            args["patient_id"] = state["patient_id"]          # scope is enforced here, not trusted
            t0 = time.perf_counter()
            tool = by_name.get(call["name"])
            try:
                if tool is None:
                    raise ValueError(f"unknown tool {call['name']}")
                result = as_data(await tool.ainvoke(args))
            except Exception as e:                              # tell the agent, keep going
                result = {"error": str(e)}
            trace.append({"tool": call["name"], "args": args, "result": result,
                          "seconds": round(time.perf_counter() - t0, 2),
                          "patient_id_overridden": asked_for not in (None, state["patient_id"])})
            out_messages.append(ToolMessage(json.dumps(result, default=str), tool_call_id=call["id"]))
        return {"messages": out_messages, "trace": trace}

    def check(state):
        last = state["messages"][-1]
        answer = last.content if isinstance(last, AIMessage) and isinstance(last.content, str) else ""
        if getattr(last, "tool_calls", None):
            problems = [{"sentence": "(answer)", "problem": f"stopped after {MAX_TOOL_CALLS} tool calls"}]
        else:
            problems = check_answer(answer, [t["result"] for t in state.get("trace", [])],
                                    state["question"])
        attempt = len(state.get("checks", [])) + 1
        update = {"checks": [{"attempt": attempt, "answer": answer, "problems": problems}]}
        if not problems:
            return update | {"answer": answer, "status": "verified"}
        if attempt < MAX_ANSWER_ATTEMPTS and not getattr(last, "tool_calls", None):
            feedback = "\n".join(f'- "{p["sentence"]}": {p["problem"]}' for p in problems)
            return update | {"messages": [HumanMessage(
                "Your answer was rejected by the checker:\n" + feedback +
                "\nAnswer again, fixing these. Use only values and source ids from the tool results.")]}
        return update | {"answer": UNVERIFIED, "status": "unverified"}

    def after_check(state):
        return END if state.get("status") else "agent"

    g = StateGraph(QAState)
    g.add_node("gate", gate)
    g.add_node("redirect", redirect)
    g.add_node("agent", agent)
    g.add_node("tools", run_tools)
    g.add_node("check", check)
    g.add_edge(START, "gate")
    g.add_conditional_edges("gate", after_gate, ["agent", "redirect"])
    g.add_edge("redirect", END)
    g.add_conditional_edges("agent", after_agent, ["tools", "check"])
    g.add_edge("tools", "agent")
    g.add_conditional_edges("check", after_check, ["agent", END])
    return g.compile()


async def ask_events(graph, patient_id: str, question: str):
    """Run the graph and yield UI events as each step finishes."""
    yield {"type": "start", "question": question}
    async for step in graph.astream({"patient_id": patient_id, "question": question},
                                    stream_mode="updates"):
        for node, update in step.items():
            if node == "gate":
                yield {"type": "gate", **update["gate"]}
            elif node == "agent":
                calls = getattr(update["messages"][-1], "tool_calls", None) or []
                if calls:
                    yield {"type": "tool_calls", "calls": [{"tool": c["name"], "args": c["args"]} for c in calls]}
            elif node == "tools":
                for t in update["trace"]:
                    yield {"type": "tool_result", **t}
            elif node == "check":
                yield {"type": "check", **update["checks"][-1]}
                if "status" in update:
                    yield {"type": "answer", "text": update["answer"], "status": update["status"]}
            elif node == "redirect":
                yield {"type": "answer", "text": update["answer"], "status": update["status"]}
    yield {"type": "done"}
