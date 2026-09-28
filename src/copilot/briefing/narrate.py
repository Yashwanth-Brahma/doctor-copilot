"""Narrator: MedGemma writes the briefing; the verifier decides what happens next.

write -> verify ->  clean ................................ "verified" / "verified_after_retry"
                    only left things out ................. code adds those sentences: "verified_with_additions"
                    wrote something wrong, 1st attempt ... retry with the problems
                    wrote something wrong, 2nd attempt ... facts-only template: "fallback"

Wrong content needs a rewrite. A missing item is a known fact with a known sentence, so code
adds it instead of throwing away a correct draft.

The app runs this flow as a LangGraph graph (graph.py). narrate() is the same loop in plain
Python, used by scripts/try_narrator.py.
"""
import json
import os
import re
import time

from .fallback import complete_briefing, facts_only_text, has_changes, no_changes_text
from .verify import verify

MAX_ATTEMPTS = 2

RULES = """You write a pre-visit briefing for a clinician: only what changed since the last visit, using FACTS (JSON).

Write these sentences, in this order, following the patterns exactly:
1. "The last visit was on <last_visit.date>."
2. For EACH lab in labs_with_new_results, one sentence:
   "<lab> rose from <previous.value> <unit> (<previous.date>) to <latest.value> <unit> (<latest.date>)."
   Use "rose" when direction is "up" and "fell" when direction is "down".
   If previous is null: "<lab> was <latest.value> <unit> (<latest.date>), the first result."
3. For EACH item in new_medications, one sentence: "<name> was started on <started>."
4. For EACH item in new_conditions, one sentence: "<name> was recorded on <onset>."
5. For EACH item in events_since_last_visit, one sentence: "Hospital or urgent care visit: <type> on <date>."
Skip a step when its list is empty: never write a hospital or urgent care sentence unless events_since_last_visit has items. Write nothing else.

Rules:
- Copy every number and date exactly from FACTS. Never calculate anything: no percentages, no differences.
- One lab per sentence. Dates always as YYYY-MM-DD.
- No interpretation, diagnoses, causes or advice. Never use words like suggests, indicates, likely, worsening, improving, controlled, risk, consider, should.
- Answer in plain text sentences, one per line. No JSON, no code blocks, no headings, no bullet points."""


def default_llm(temperature: float = 0.0):
    """The narrator, from .env. See narrator_llm.py (local MedGemma, a remote one behind a
    tunnel with OpenAI as fallback, or OpenAI only)."""
    from .narrator_llm import build_narrator
    return build_narrator(temperature)


def narrator_name() -> str:
    """The configured narrator's display name (used when a reply doesn't report its model)."""
    from .narrator_llm import display_name
    return display_name(os.environ.get("NARRATOR_MODEL", "")) or ""


def build_messages(ni: dict, attempts: list[dict]) -> list:
    """First call: rules + facts. Retry: the same, plus what the last draft got wrong.

    The failed draft itself is NOT sent back: a small model shown its own draft tends to copy it
    word for word (MedGemma did, twice). It gets the list of problems and writes from scratch.
    """
    messages = [("system", RULES), ("human", "FACTS:\n" + json.dumps(ni, indent=1))]
    if attempts:
        last = attempts[-1]["violations"]
        wrong = [f'- "{v["sentence"]}": {v["problem"]}' for v in last if v["sentence"] != "(whole briefing)"]
        left_out = [f'- {v["problem"].removeprefix("missing: ")}' for v in last if v["sentence"] == "(whole briefing)"]
        note = "Your previous briefing was rejected. Write it again from the start, following the patterns exactly."
        if wrong:
            note += "\nThese sentences broke the rules:\n" + "\n".join(wrong)
        if left_out:
            note += "\nIt left out (each needs its own sentence):\n" + "\n".join(left_out)
        messages[1] = ("human", messages[1][1] + "\n\n" + note)
    return messages


def _strings(x) -> list[str]:
    if isinstance(x, str):
        return [x]
    if isinstance(x, list):
        return [s for item in x for s in _strings(item)]
    if isinstance(x, dict):
        return [s for v in x.values() for s in _strings(v)]
    return []


def clean_output(raw: str) -> str:
    """Undo formatting the model adds around its sentences.

    MedGemma was given FACTS as JSON and often answered in JSON inside a code block
    (6 of 10 runs). Sentences are pulled out of the JSON; any leftover structure (e.g. a
    "new_medications" object instead of a sentence) is dropped, and coverage checking then
    notices what's missing. Literal escapes like "m\\u00b2" are turned into characters.
    """
    text = raw.strip()
    fence = re.fullmatch(r"```[a-zA-Z]*\s*(.*?)\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    if text[:1] in "{[":
        try:
            sentences = [s.strip() for s in _strings(json.loads(text))
                         if re.search(r"[.!?]$", s.strip())]
            text = "\n".join(sentences)
        except json.JSONDecodeError:
            pass                      # leave it: the verifier reports "not plain text"
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)


def write_and_check(ni: dict, llm, attempts: list[dict]) -> dict:
    from .narrator_llm import model_of
    t0 = time.perf_counter()
    reply = llm.invoke(build_messages(ni, attempts))
    text = clean_output(reply.content)
    meta = getattr(reply, "response_metadata", None) or {}
    return {"text": text, "raw": reply.content, "violations": verify(text, ni),
            "seconds": round(time.perf_counter() - t0, 1),
            "model": model_of(reply),                       # who actually wrote this draft
            "fallback_from": meta.get("fallback_from")}     # set when the primary was unreachable


def next_step(attempts: list[dict]) -> str:
    """accept | complete | write | fallback, from the latest attempt's violations."""
    v = attempts[-1]["violations"]
    if not v:
        return "accept"
    if all(x["sentence"] == "(whole briefing)" for x in v):
        return "complete"
    return "write" if len(attempts) < MAX_ATTEMPTS else "fallback"


def finish(ni: dict, attempts: list[dict], step: str) -> dict:
    text = attempts[-1]["text"]
    if step == "accept":
        return {"text": text, "added": [],
                "status": "verified" if len(attempts) == 1 else "verified_after_retry"}
    if step == "complete":
        completed, added = complete_briefing(text, ni)
        if not verify(completed, ni):
            return {"text": completed, "added": added, "status": "verified_with_additions"}
    return {"text": facts_only_text(ni), "added": [], "status": "fallback"}


def narrate(ni: dict, llm=None) -> dict:
    if not has_changes(ni):
        return {"text": no_changes_text(ni), "status": "no_changes", "added": [], "attempts": []}
    llm = llm or default_llm()
    attempts = []
    while True:
        attempts.append(write_and_check(ni, llm, attempts))
        step = next_step(attempts)
        if step != "write":
            return {**finish(ni, attempts, step), "attempts": attempts}
