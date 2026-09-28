import { describe, expect, it } from "vitest";
import type { AskEvent } from "../api/types";
import { applyEvent, newTurn, type ToolStep } from "./trace";

const run = (events: AskEvent[]) => events.reduce(applyEvent, newTurn("1", "q"));

describe("applyEvent", () => {
  it("tool calls start pending and finish when their results arrive, matched by tool and args", () => {
    const t = run([
      { type: "tool_calls", calls: [
        { tool: "get_lab_series", args: { patient_id: "p", lab: "potassium" } },
        { tool: "get_lab_series", args: { patient_id: "p", lab: "egfr" } },
      ] },
      { type: "tool_result", tool: "get_lab_series", args: { patient_id: "p", lab: "egfr" }, result: { x: 1 }, seconds: 0.2, patient_id_overridden: false },
    ]);
    const [a, b] = t.steps as ToolStep[];
    expect(a.pending).toBe(true);
    expect(b.pending).toBe(false);
    expect(b.result).toEqual({ x: 1 });
  });

  it("matches a result whose patient_id the backend overrode", () => {
    const t = run([
      { type: "tool_calls", calls: [{ tool: "get_patient_summary", args: { patient_id: "someone-else" } }] },
      { type: "tool_result", tool: "get_patient_summary", args: { patient_id: "p" }, result: {}, seconds: 0.1, patient_id_overridden: true },
    ]);
    expect(t.steps).toHaveLength(1);
    expect((t.steps[0] as ToolStep).overridden).toBe(true);
  });

  it("records checks, the answer, and stops running on done", () => {
    const t = run([
      { type: "check", attempt: 1, answer: "a", problems: [{ sentence: "a", problem: "no source" }] },
      { type: "check", attempt: 2, answer: "b", problems: [] },
      { type: "answer", text: "b", status: "verified" },
      { type: "done" },
    ]);
    expect(t.steps.map((s) => s.kind)).toEqual(["check", "check"]);
    expect(t.answer).toEqual({ text: "b", status: "verified" });
    expect(t.running).toBe(false);
  });

  it("an error event stops the turn", () => {
    const t = run([{ type: "error", message: "boom" }]);
    expect(t).toMatchObject({ error: "boom", running: false });
  });
});
