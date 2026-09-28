import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, ask } from "../api/client";
import { parseCitations, sourceIds } from "../lib/citations";
import { applyEvent, newTurn, type ToolStep, type Turn } from "../lib/trace";
import { LimitNotice, Spinner } from "./ui";
import { stepDomId, Trace } from "./Trace";

function examples(sex: string) {
  const who = sex === "male" ? "he" : sex === "female" ? "she" : "the patient";
  const is = who === "the patient" ? "is the patient" : `is ${who}`;
  const has = who === "the patient" ? "has the patient" : `has ${who}`;
  return [
    "How has potassium changed since spironolactone was started?",
    `What medications ${is} taking?`,
    `${has[0].toUpperCase()}${has.slice(1)} been to the hospital since the last visit?`,
    "Should I stop spironolactone?",
  ];
}

let nextId = 0;

/** Mounted with key={patient.id}: switching patients unmounts it, which aborts the stream
 *  and clears the conversation. */
export function QAPanel({ patientId, patientName, sex }: { patientId: string; patientName: string; sex: string }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [showExamples, setShowExamples] = useState(false);
  const [newActivity, setNewActivity] = useState(false);
  const ctrl = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const stick = useRef(true);                   // is the reader at (or near) the bottom?
  const running = turns.some((t) => t.running);
  const runningRef = useRef(running);
  runningRef.current = running;

  useEffect(() => () => ctrl.current?.abort(), []);

  // Follow the stream: whenever the conversation grows, stay pinned to the bottom if the reader
  // was there (checked even after the stream ends: the answer and "done" often arrive together).
  // If they scrolled up or are reading the trace, leave them and, while it runs, offer a button.
  useEffect(() => {
    const ro = new ResizeObserver(() => {
      if (stick.current) toBottom("auto");
      else if (runningRef.current) setNewActivity(true);
    });
    ro.observe(content.current!);
    return () => ro.disconnect();
  }, []);

  function toBottom(behavior: ScrollBehavior) {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior });
  }

  function onScroll() {
    const el = scroller.current!;
    stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 64;
    if (stick.current) setNewActivity(false);
  }

  const update = (id: string, f: (t: Turn) => Turn) => setTurns((ts) => ts.map((t) => (t.id === id ? f(t) : t)));

  async function run(q: string, replaceId?: string) {
    const c = new AbortController();
    ctrl.current = c;
    const turn = newTurn(String(++nextId), q);
    stick.current = true;                       // asking a question means you want to watch it
    setNewActivity(false);
    setShowExamples(false);
    setTurns((ts) => (replaceId ? ts.map((t) => (t.id === replaceId ? turn : t)) : [...ts, turn]));
    try {
      await ask(patientId, q, (e) => { if (!c.signal.aborted) update(turn.id, (t) => applyEvent(t, e)); }, c.signal);
      if (!c.signal.aborted) update(turn.id, (t) => (t.running ? { ...t, running: false, error: t.answer ? undefined : "The stream ended before an answer arrived." } : t));
    } catch (e) {
      if (c.signal.aborted) return;
      const msg = e instanceof Error ? e.message : String(e);
      if (e instanceof ApiError && e.status === 429) update(turn.id, (t) => ({ ...t, running: false, limited: msg }));
      else update(turn.id, (t) => ({ ...t, running: false, error: /fetch|network/i.test(msg) ? `Couldn't reach the server (${msg}).` : msg }));
    }
  }

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const q = question.trim();
    if (running || q.length < 3) return;
    setQuestion("");
    run(q);
  }

  const tooShort = question.trim().length > 0 && question.trim().length < 3;
  const chipsVisible = turns.length === 0 || showExamples;

  return (
    <section aria-labelledby="qa-title" className="flex h-full min-h-0 min-w-0 flex-col">
      {/* fixed top */}
      <header className="shrink-0 border-b border-border px-4 pt-4 pb-3 sm:px-6">
        <h2 id="qa-title" className="text-xl font-semibold">Ask about {patientName}</h2>
        <p className="text-sm text-fg-muted">Answers come only from the record. Every tool call and check is shown.</p>
      </header>

      {/* the only part that scrolls */}
      <div className="relative min-h-0 flex-1">
        <div ref={scroller} onScroll={onScroll} className="h-full overflow-y-auto px-4 py-4 sm:px-6" data-testid="conversation">
          <div ref={content} className="space-y-6" aria-live="polite">
            {turns.length === 0 && <p className="text-fg-muted">No questions yet. Try one of the examples below.</p>}
            {turns.map((t) => (
              <TurnView key={t.id} turn={t} onRetry={() => run(t.question, t.id)} canRetry={!running} onRead={() => { stick.current = false; }} />
            ))}
          </div>
        </div>
        {newActivity && (
          <button
            type="button"
            onClick={() => { stick.current = true; setNewActivity(false); toBottom("smooth"); }}
            className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full border border-accent-border bg-bg px-3 py-1 text-sm font-medium text-accent-fg shadow-md hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-accent"
          >
            <span aria-hidden="true">↓ </span>New activity
          </button>
        )}
      </div>

      {/* fixed bottom: never overlaps the conversation, which ends above it */}
      <div className="shrink-0 border-t border-border px-4 pt-3 pb-4 sm:px-6">
        {chipsVisible && (
          <div id="examples" className="mb-2 flex gap-2 overflow-x-auto pb-1 md:flex-wrap md:overflow-visible md:pb-0" aria-label="Example questions" role="group">
            {examples(sex).map((q) => (
              <button
                key={q}
                type="button"
                disabled={running}
                onClick={() => { setQuestion(""); run(q); }}
                className="shrink-0 rounded-full border border-border-strong px-3 py-1 text-left text-sm whitespace-nowrap md:shrink md:whitespace-normal text-fg-muted hover:border-accent hover:text-accent-fg focus-visible:outline-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50"
              >
                {q}
              </button>
            ))}
          </div>
        )}
        <form onSubmit={submit} className="flex gap-2">
          {turns.length > 0 && (
            <button
              type="button"
              onClick={() => setShowExamples((v) => !v)}
              aria-expanded={showExamples}
              aria-controls="examples"
              className="shrink-0 rounded-md border border-border-strong px-2.5 text-sm text-fg-muted hover:bg-subtle focus-visible:outline-2 focus-visible:outline-accent"
            >
              Examples
            </button>
          )}
          <label htmlFor="question" className="sr-only">Your question</label>
          <input
            id="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            maxLength={500}
            disabled={running}
            placeholder={running ? "Working on the current question…" : "Ask about labs, medications, conditions, visits"}
            aria-describedby={tooShort ? "question-hint" : undefined}
            className="min-w-0 flex-1 rounded-md border border-border-strong bg-bg px-3 py-2 placeholder:text-fg-subtle focus:border-accent focus:outline-2 focus:outline-accent-border disabled:bg-subtle"
          />
          <button
            type="submit"
            disabled={running || question.trim().length < 3}
            className="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 font-medium text-on-accent hover:bg-accent-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:bg-subtle disabled:text-fg-muted"
          >
            {running && <Spinner />} Ask
          </button>
        </form>
        {tooShort && <p id="question-hint" className="mt-1 text-xs text-fg-subtle">At least 3 characters.</p>}
      </div>
    </section>
  );
}

/** onRead: the doctor opened part of the trace, so growth shouldn't scroll it away from them. */
function TurnView({ turn, onRetry, canRetry, onRead }: { turn: Turn; onRetry: () => void; canRetry: boolean; onRead: () => void }) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [highlight, setHighlight] = useState<string[]>([]);

  // unverified: open every tool result so the doctor can read the raw data
  const unverified = turn.answer?.status === "unverified";
  useEffect(() => {
    if (unverified) setExpanded(new Set(turn.steps.filter((s) => s.kind === "tool").map((s) => s.key)));
  }, [unverified]);

  const toggle = (key: string) => {
    onRead();
    setExpanded((s) => {
      const n = new Set(s);
      if (!n.delete(key)) n.add(key);
      return n;
    });
  };

  // every finished tool call whose result contains this id (it can appear in more than one)
  const stepsFor = (id: string) =>
    turn.steps.filter((s): s is ToolStep => s.kind === "tool" && !s.pending && sourceIds(s.result).includes(id));

  function jump(id: string) {
    const keys = stepsFor(id).map((s) => s.key);
    if (!keys.length) return;
    onRead();
    setExpanded((s) => new Set([...s, ...keys]));
    setHighlight([]);
    requestAnimationFrame(() => {
      setHighlight(keys);
      const el = document.getElementById(stepDomId(turn.id, keys[0]));
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      // move focus so keyboard users land where the chip pointed
      el?.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
    });
    setTimeout(() => setHighlight((h) => (h.join() === keys.join() ? [] : h)), 2000);
  }

  return (
    <article className="space-y-3" aria-label={`Question: ${turn.question}`}>
      <p className="ml-auto w-fit max-w-[90%] rounded-lg bg-subtle px-3 py-2 font-medium">{turn.question}</p>
      <Trace turn={turn} expanded={expanded} onToggle={toggle} highlight={highlight} />

      {turn.answer && <Answer answer={turn.answer} onCite={jump} hasSource={(id) => stepsFor(id).length > 0} />}

      {turn.limited && <LimitNotice message={turn.limited} onRetry={onRetry} disabled={!canRetry} />}

      {turn.error && (
        <div role="alert" className="rounded-md border border-danger-border bg-danger-soft p-3 text-danger-fg">
          <p className="font-medium">Something went wrong{turn.answer ? " after the answer" : ""}.</p>
          <p className="text-sm">{turn.error}</p>
          <button
            type="button"
            onClick={onRetry}
            disabled={!canRetry}
            className="mt-2 rounded-md border border-danger-border bg-bg px-3 py-1 text-sm hover:bg-subtle disabled:opacity-50"
          >
            Ask again
          </button>
        </div>
      )}
    </article>
  );
}

function Answer({ answer, onCite, hasSource }: {
  answer: NonNullable<Turn["answer"]>; onCite: (id: string) => void; hasSource: (id: string) => boolean;
}) {
  if (answer.status === "redirected") {
    return (
      <div role="note" className="rounded-md border border-border-strong bg-surface p-3 text-fg">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg-muted"><span aria-hidden="true">ⓘ </span>Outside what the record can answer</p>
        <p>{answer.text}</p>
      </div>
    );
  }
  if (answer.status === "unverified") {
    return (
      <div role="alert" className="rounded-md border border-warn-border bg-warn-soft p-3 text-fg">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-warn-fg"><span aria-hidden="true">⚠ </span>Not verified</p>
        <p>{answer.text}</p>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-ok-border bg-bg p-3">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ok-fg"><span aria-hidden="true">✓ </span>Verified answer</p>
      <p className="leading-relaxed">
        {parseCitations(answer.text).map((seg, i) =>
          seg.kind === "text" ? <span key={i}>{seg.text}</span> : (
            <span key={i} className="inline-flex flex-wrap gap-1 align-baseline">
              {seg.ids.map((id) => {
                const ok = hasSource(id);
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() => onCite(id)}
                    disabled={!ok}
                    title={ok ? `Show where ${id} came from` : `${id} was not found in this trace`}
                    className="rounded border border-accent-border bg-accent-soft px-1.5 font-mono text-[11px] leading-5 text-accent-fg hover:border-accent focus-visible:outline-2 focus-visible:outline-accent disabled:border-danger-border disabled:bg-danger-soft disabled:text-danger-fg"
                  >
                    {shortId(id)}
                  </button>
                );
              })}
            </span>
          ),
        )}
      </p>
    </div>
  );
}

/** "demo-ravi-kumar-obs-potassium-3" -> "obs-potassium-3"; the full id is in the title and trace. */
function shortId(id: string) {
  const m = id.match(/-(obs|med|cond|enc)-.+$/);
  return m ? m[0].slice(1) : id.length > 20 ? id.slice(0, 8) + "…" : id;
}
