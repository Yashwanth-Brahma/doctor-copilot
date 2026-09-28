import type { AnswerStatus, AskEvent, CheckProblem, GateCategory } from "../api/types";

export interface ToolStep {
  kind: "tool";
  key: string;
  tool: string;
  args: Record<string, unknown>;
  pending: boolean;
  result?: unknown;
  seconds?: number;
  overridden?: boolean;
}

export interface CheckStep {
  kind: "check";
  key: string;
  attempt: number;
  answer: string;
  problems: CheckProblem[];
}

export type Step = ToolStep | CheckStep;

export interface Turn {
  id: string;
  question: string;
  gate?: { category: GateCategory; reason: string };
  steps: Step[];
  answer?: { text: string; status: AnswerStatus };
  error?: string;
  limited?: string;                              // 429 before the stream started: a notice, not an error
  running: boolean;
}

export function newTurn(id: string, question: string): Turn {
  return { id, question, steps: [], running: true };
}

function sameArgs(a: Record<string, unknown>, b: Record<string, unknown>) {
  // the backend overwrites patient_id before running the tool, so compare everything else
  const strip = ({ patient_id: _p, ...rest }: Record<string, unknown>) => JSON.stringify(rest, Object.keys(rest).sort());
  return strip(a) === strip(b);
}

/** Fold one stream event into a turn. Pure, so the trace logic is testable without React. */
export function applyEvent(turn: Turn, e: AskEvent): Turn {
  const n = turn.steps.length;
  switch (e.type) {
    case "start":
      return turn;
    case "gate":
      return { ...turn, gate: { category: e.category, reason: e.reason } };
    case "tool_calls":
      return {
        ...turn,
        steps: [
          ...turn.steps,
          ...e.calls.map((c, i): ToolStep => ({ kind: "tool", key: `t${n + i}`, tool: c.tool, args: c.args, pending: true })),
        ],
      };
    case "tool_result": {
      const pending = turn.steps.filter((s): s is ToolStep => s.kind === "tool" && s.pending && s.tool === e.tool);
      const target = pending.find((s) => sameArgs(s.args, e.args)) ?? pending[0];
      const done = { pending: false, args: e.args, result: e.result, seconds: e.seconds, overridden: e.patient_id_overridden };
      if (!target) {
        return { ...turn, steps: [...turn.steps, { kind: "tool", key: `t${n}`, tool: e.tool, ...done }] };
      }
      return { ...turn, steps: turn.steps.map((s) => (s === target ? { ...target, ...done } : s)) };
    }
    case "check":
      return {
        ...turn,
        steps: [...turn.steps, { kind: "check", key: `c${n}`, attempt: e.attempt, answer: e.answer, problems: e.problems }],
      };
    case "answer":
      return { ...turn, answer: { text: e.text, status: e.status } };
    case "error":
      return { ...turn, error: e.message, running: false };
    case "done":
      return { ...turn, running: false };
  }
}
