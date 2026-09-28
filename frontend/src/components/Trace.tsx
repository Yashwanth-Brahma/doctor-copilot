import type { GateCategory } from "../api/types";
import type { CheckStep, ToolStep, Turn } from "../lib/trace";
import { Spinner } from "./ui";

const GATE: Record<GateCategory, string> = {
  record_question: "Question about the record",
  advice_request: "Asks for advice",
  off_topic: "Not about this record",
};

export const stepDomId = (turnId: string, key: string) => `step-${turnId}-${key}`;

interface Props {
  turn: Turn;
  expanded: Set<string>;
  onToggle: (key: string) => void;
  highlight: string[];
}

export function Trace({ turn, expanded, onToggle, highlight }: Props) {
  const lastCheck = [...turn.steps].reverse().find((s) => s.kind === "check");
  return (
    <ol className="space-y-1.5 border-l-2 border-border pl-3 text-sm" aria-label="How the answer was found">
      <li className="flex items-start gap-2">
        {turn.gate ? (
          <>
            <span aria-hidden="true" className="text-fg-subtle">◇</span>
            <span>
              <span className="font-medium">Gate:</span> {GATE[turn.gate.category] ?? turn.gate.category}
              <span className="text-fg-muted"> — {turn.gate.reason}</span>
            </span>
          </>
        ) : turn.running ? (
          <><Spinner /> <span className="text-fg-muted">Classifying the question…</span></>
        ) : null}
      </li>

      {turn.steps.map((s) =>
        s.kind === "tool" ? (
          <ToolRow
            key={s.key}
            id={stepDomId(turn.id, s.key)}
            step={s}
            open={expanded.has(s.key)}
            onToggle={() => onToggle(s.key)}
            flash={highlight.includes(s.key)}
            stopped={!turn.running}
          />
        ) : (
          <CheckRow key={s.key} step={s} retrying={s === lastCheck && turn.running && !turn.answer} finalUnverified={s === lastCheck && turn.answer?.status === "unverified"} />
        ),
      )}

      {turn.running && turn.gate?.category === "record_question" && turn.steps.length > 0 && turn.steps.every((s) => s.kind !== "tool" || !s.pending) && !turn.answer && (
        <li className="flex items-center gap-2 text-fg-muted"><Spinner /> Agent is working…</li>
      )}
    </ol>
  );
}

function ToolRow({ id, step, open, onToggle, flash, stopped }: {
  id: string; step: ToolStep; open: boolean; onToggle: () => void; flash: boolean; stopped: boolean;
}) {
  const { patient_id: _p, ...shownArgs } = step.args;
  const argText = Object.entries(shownArgs).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ");
  const error = isError(step.result);
  return (
    <li id={id} className={`-mx-1 rounded-md px-1 scroll-my-4 ${flash ? "flash ring-2 ring-highlight-ring" : ""}`}>
      <div className="flex items-start gap-2">
        <span className="mt-0.5">
          {step.pending ? (stopped ? <span aria-label="not finished" className="text-fg-subtle">○</span> : <Spinner label="running" />)
            : error ? <span aria-label="failed" className="text-danger-fg">✗</span>
            : <span aria-label="done" className="text-ok-fg">✓</span>}
        </span>
        <div className="min-w-0 flex-1">
          <p>
            <span className="font-mono text-[13px] font-medium">{step.tool}</span>
            <span className="font-mono text-[13px] text-fg-muted">({argText})</span>
            {step.seconds !== undefined && <span className="ml-2 text-xs text-fg-subtle">{step.seconds.toFixed(2)} s</span>}
          </p>
          {step.overridden && (
            <p role="note" className="mt-1 rounded border border-warn-border bg-warn-soft px-2 py-1 text-warn-fg">
              <span aria-hidden="true">⚠ </span>Agent asked for another patient; request was limited to this patient.
            </p>
          )}
          {!step.pending && (
            <>
              <p className={error ? "text-danger-fg" : "text-fg-muted"}>{summarize(step.tool, step.result)}</p>
              <button
                type="button"
                onClick={onToggle}
                aria-expanded={open}
                className="text-xs text-accent-fg underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-accent"
              >
                {open ? "Hide result" : "Show result"}
              </button>
              {open && (
                <pre className="mt-1 max-h-80 overflow-auto rounded bg-surface p-2 font-mono text-xs leading-relaxed text-fg ring-1 ring-border">
                  {JSON.stringify(step.result, null, 2)}
                </pre>
              )}
            </>
          )}
        </div>
      </div>
    </li>
  );
}

function CheckRow({ step, retrying, finalUnverified }: { step: CheckStep; retrying: boolean; finalUnverified: boolean }) {
  if (step.problems.length === 0) {
    return (
      <li className="flex items-start gap-2">
        <span aria-hidden="true" className="text-ok-fg">✓</span>
        <span>Answer checked against tool results{step.attempt > 1 && ` (attempt ${step.attempt})`}</span>
      </li>
    );
  }
  return (
    <li className="flex items-start gap-2">
      <span aria-hidden="true" className="text-danger-fg">✗</span>
      <div>
        <p>
          <span className="font-medium">Check failed</span> on attempt {step.attempt}
          {finalUnverified ? " — no more retries; the answer is withheld." : retrying ? " — retrying…" : " — the agent retried."}
        </p>
        <ul className="mt-0.5 list-disc pl-5 text-fg-muted">
          {step.problems.map((p, i) => (
            <li key={i}><q className="text-fg">{p.sentence}</q>: {p.problem}</li>
          ))}
        </ul>
      </div>
    </li>
  );
}

const isError = (r: unknown): r is { error: string } => !!r && typeof r === "object" && "error" in r;
const len = (x: unknown) => (Array.isArray(x) ? x.length : 0);
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

/** One line saying what a tool returned, so the doctor needn't open the JSON. */
export function summarize(tool: string, r: unknown): string {
  if (isError(r)) return `Error: ${r.error}`;
  if (!r || typeof r !== "object") return "Returned no data";
  const o = r as Record<string, unknown>;
  if (tool === "get_lab_series") {
    const n = len(o.points);
    return n ? `${o.lab}: ${plural(n, "result")}` : `${o.lab ?? "Lab"}: no results on record`;
  }
  if (tool === "get_changes_since_last_visit") {
    return `Since last visit: ${plural(len(o.labs), "new lab result")}, ${plural(len(o.new_medications), "new medication")}, ` +
      `${plural(len(o.new_conditions), "new condition")}, ${plural(len(o.events), "hospital event")}`;
  }
  if (tool === "get_patient_summary") {
    return `${plural(len(o.problems), "problem")}, ${plural(len(o.active_medications), "active medication")}, ${plural(len(o.latest_labs), "lab")}`;
  }
  return `Returned ${Object.keys(o).join(", ")}`;
}
