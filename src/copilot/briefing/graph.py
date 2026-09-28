"""The briefing as a LangGraph graph.

    load ─► compute ─► write ──(clean)──────────────────────► accept ───► END
                         ▲  ├─(only left things out)──────────► complete ─► END
                         └──┤ (wrong content, 1st attempt)
                            └─(wrong content, 2nd attempt)────► fallback ─► END

    accept / complete / fallback each also append the context lines (current medications,
    known problems), written by code from the facts.

    write = one model call + verify(). Its result is appended to state["attempts"], so a
    retry is told what the earlier draft got wrong. The routing rule is next_step() in
    narrate.py, shared with narrate() so both paths behave the same.

Same logic as narrate(), but as named steps: each step shows up in LangSmith traces and
can be streamed to the UI ("computing facts…", "checking draft…").

The database loader, fact computation and model are passed in, so tests run the whole
graph with fakes and no database or Ollama.
"""
import operator
from datetime import date
from typing import Annotated, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from ..facts.compute import compute_facts
from .fallback import context_lines
from .narrate import default_llm, finish, next_step, write_and_check
from .narrator_input import narrator_input


class BriefingState(TypedDict, total=False):
    patient_id: str
    today: date
    records: dict
    facts: dict
    ni: dict
    attempts: Annotated[list[dict], operator.add]   # each write+check appends one
    text: str
    added: list[str]                                  # sentences code added to the model's draft
    context: list[str]                                # current meds + problems, written by code
    status: str      # verified | verified_after_retry | verified_with_additions | fallback


def build_briefing_graph(load_records: Callable[[str], dict | None], llm=None,
                         compute: Callable = compute_facts):
    llm = llm or default_llm()

    def load(state):
        records = load_records(state["patient_id"])
        if records is None:
            raise LookupError(f"no patient {state['patient_id']}")
        return {"records": records}

    def compute_node(state):
        r = state["records"]
        facts = compute(r["patient"], r["encounters"], r["conditions"],
                        r["medications"], r["observations"], today=state["today"])
        return {"facts": facts, "ni": narrator_input(facts)}

    def write(state):
        return {"attempts": [write_and_check(state["ni"], llm, state.get("attempts", []))]}

    def after_write(state):
        return next_step(state["attempts"])

    def ending(step):
        def node(state):
            out = finish(state["ni"], state["attempts"], step)
            out["context"] = context_lines(state["facts"])
            out["text"] = "\n".join([out["text"], *out["context"]])
            return out
        return node

    g = StateGraph(BriefingState)
    g.add_node("load", load)
    g.add_node("compute", compute_node)
    g.add_node("write", write)          # write_and_check = model call + verify
    for step in ("accept", "complete", "fallback"):
        g.add_node(step, ending(step))
    g.add_edge(START, "load")
    g.add_edge("load", "compute")
    g.add_edge("compute", "write")
    g.add_conditional_edges("write", after_write, ["accept", "complete", "write", "fallback"])
    for step in ("accept", "complete", "fallback"):
        g.add_edge(step, END)
    return g.compile()


def briefing_response(state: dict) -> dict:
    """What the API returns: the text, how it was produced, and the facts behind it."""
    return {
        "patient_id": state["patient_id"],
        "text": state["text"],
        "status": state["status"],
        "attempts": len(state["attempts"]),
        "added": state["added"],
        "context": state["context"],
        "facts": state["facts"],
        "limitations": state["facts"]["limitations"],
    }
