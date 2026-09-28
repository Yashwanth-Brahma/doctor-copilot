"""Check an agent answer against what the tools actually returned in this conversation.

Same principle as the briefing verifier, different facts: here the facts are the tool results.
  - every number and date in the answer must appear in a tool result (or in the question)
  - every sentence with a number or date must cite a source id: [demo-ravi-kumar-obs-potassium-3]
  - every cited id must be a real source id from a tool result (no invented citations)
  - no interpretation or advice, dates as YYYY-MM-DD, plain text
"""
import json
import re

from ..briefing.verify import INTERPRETATION, ISO_DATE, NON_ISO_DATE, NUMBER, split_sentences

CITATION = re.compile(r"\[([^\[\]]+)\]")


def _num(x) -> float:
    return round(abs(float(x)), 2)


def _walk(x, numbers: set, dates: set, sources: set, key: str | None = None):
    if isinstance(x, dict):
        for k, v in x.items():
            _walk(v, numbers, dates, sources, k)
    elif isinstance(x, list):
        for v in x:
            _walk(v, numbers, dates, sources, key)
    elif isinstance(x, bool) or x is None:
        return
    elif isinstance(x, (int, float)):
        numbers.add(_num(x))
    elif isinstance(x, str):
        if key in ("source", "fhir_id", "id"):
            sources.add(x)
            return
        dates.update(ISO_DATE.findall(x))
        # numbers inside text values (drug strengths, "stage 3") are fair to repeat
        numbers.update(_num(n) for n in NUMBER.findall(ISO_DATE.sub(" ", x)))


def grounding(tool_results: list) -> tuple[set, set, set]:
    numbers, dates, sources = set(), set(), set()
    for r in tool_results:
        _walk(r, numbers, dates, sources)
    return numbers, dates, sources


def check_answer(answer: str, tool_results: list, question: str) -> list[dict]:
    numbers, dates, sources = grounding(tool_results)
    # the doctor's own numbers and dates may be repeated, and need no citation
    q_dates = set(ISO_DATE.findall(question))
    q_numbers = {_num(n) for n in NUMBER.findall(ISO_DATE.sub(" ", question))}
    problems = []

    def bad(sentence, problem):
        problems.append({"sentence": sentence, "problem": problem})

    if not answer.strip():
        bad("(answer)", "empty answer")
    for s in split_sentences(answer):
        cited = [c.strip() for group in CITATION.findall(s) for c in group.split(",")]
        for c in cited:
            if c not in sources:
                bad(s, f"cites '{c}', which is not a source id from any tool result")
        body = CITATION.sub(" ", s)
        if m := INTERPRETATION.search(body):
            bad(s, f"interpretation word '{m.group(0)}': describe, don't interpret")
        if m := NON_ISO_DATE.search(body):
            bad(s, f"date '{m.group(0)}' not in YYYY-MM-DD format")
        if re.search(r"[{}`]|\\u[0-9a-f]{4}", body, re.I):
            bad(s, "not plain text")
        found_dates = ISO_DATE.findall(body)
        found_numbers = NUMBER.findall(ISO_DATE.sub(" ", body))
        record_values = False
        for d in found_dates:
            if d in q_dates:
                continue
            record_values = True
            if d not in dates:
                bad(s, f"date {d} is not in any tool result")
        for n in found_numbers:
            if _num(n) in q_numbers:
                continue
            record_values = True
            if _num(n) not in numbers:
                bad(s, f"value {n} is not in any tool result")
        if record_values and not cited:
            bad(s, "gives values without citing a source id")
    return problems


def as_data(result):
    """MCP tools return JSON text (or content blocks); local tools return dicts."""
    if isinstance(result, (dict, list)) and not (
            isinstance(result, list) and result and isinstance(result[0], dict) and "text" in result[0]):
        return result
    if isinstance(result, list):                     # content blocks: [{"type": "text", "text": ...}]
        result = "".join(b.get("text", "") for b in result if isinstance(b, dict))
    try:
        return json.loads(result)
    except (TypeError, json.JSONDecodeError):
        return {"text": str(result)}
