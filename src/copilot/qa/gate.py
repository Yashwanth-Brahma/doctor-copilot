"""Question gate: decide what kind of question this is BEFORE the agent touches any tool.

One small model call with structured output: the answer is a category from a fixed list,
not text, so code can branch on it. Advice and off-topic questions never reach the agent.
"""
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["record_question", "advice_request", "off_topic"]


class GateDecision(BaseModel):
    category: Category = Field(description="Exactly one category")
    reason: str = Field(description="One short sentence explaining the choice")


GATE_PROMPT = """You sort a clinician's question about ONE patient's medical record into one category.

record_question: asks what the record shows. Values, dates, trends, medications, conditions,
  visits, what changed, when something was started or measured.
advice_request: asks what to do or what something means clinically. Diagnosis, prognosis,
  treatment, dosing, whether to start, stop or change a drug, causes, risk.
off_topic: not about this patient's record at all.

If a question mixes a record question with advice, choose advice_request."""

REDIRECTS = {
    "advice_request": (
        "I can only report what the record shows, not give diagnosis or treatment advice. "
        "Try asking about the data, for example: \"How has potassium changed since "
        "spironolactone was started?\""
    ),
    "off_topic": (
        "I can only answer questions about this patient's record: labs, medications, "
        "conditions and visits."
    ),
}


async def classify(question: str, llm) -> GateDecision:
    gate = llm.with_structured_output(GateDecision)
    return await gate.ainvoke([("system", GATE_PROMPT), ("human", question)])
