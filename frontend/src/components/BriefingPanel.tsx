import { useEffect, useState } from "react";
import { getBriefing } from "../api/client";
import type { Briefing, BriefingStatus, Facts, Lab, PatientListItem } from "../api/types";
import { authorHelp, authorLabel, classifyLines, type Author } from "../lib/authorship";
import { clean, labName, patientLine, value } from "../lib/format";
import { Empty, LimitNotice, SectionTitle, SourceId, Spinner, Tag } from "./ui";

const OK = "border-ok-border bg-ok-soft text-ok-fg";
const STATUS: Record<BriefingStatus, { label: string; icon: string; cls: string }> = {
  verified: { label: "Verified", icon: "✓", cls: OK },
  verified_after_retry: { label: "Verified after a retry", icon: "✓", cls: OK },
  verified_with_additions: { label: "Verified, with lines added from the record", icon: "✓", cls: OK },
  fallback: { label: "Written from the record (model output rejected)", icon: "!", cls: "border-warn-border bg-warn-soft text-warn-fg" },
  no_changes: { label: "Nothing new since the last visit", icon: "–", cls: "border-border-strong bg-subtle text-fg-muted" },
};

// Colour plus a text label on every row: colour is never the only signal.
const AUTHOR_STYLE: Record<Author, { border: string; tone: "accent" | "warn" | "neutral" }> = {
  model: { border: "border-l-stripe-model", tone: "accent" },
  added: { border: "border-l-stripe-added", tone: "warn" },
  record: { border: "border-l-stripe-record", tone: "neutral" },
};

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string; notFound: boolean }
  | { kind: "limited"; message: string }                    // 429: the demo's rate limit, not a failure
  | { kind: "ready"; data: Briefing };

export function BriefingPanel({ patient }: { patient: PatientListItem }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();           // aborted when the patient changes (unmount) or on retry
    setState({ kind: "loading" });
    getBriefing(patient.id, ctrl.signal)
      .then((data) => setState({ kind: "ready", data }))
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        const status = (e as { status?: number }).status;
        const message = e instanceof Error ? e.message : String(e);
        setState(status === 429 ? { kind: "limited", message } : { kind: "error", message, notFound: status === 404 });
      });
    return () => ctrl.abort();
  }, [patient.id, attempt]);

  const b = state.kind === "ready" ? state.data : null;
  const facts = b?.facts;
  const s = b && STATUS[b.status];

  return (
    <section aria-labelledby="briefing-title" className="flex h-full min-h-0 min-w-0 flex-col">
      {/* fixed: who the patient is and how the briefing was produced */}
      <header className="shrink-0 border-b border-border px-4 pt-4 pb-3 sm:px-6">
        <h2 id="briefing-title" className="text-xl font-semibold">{facts?.patient.name ?? patient.name}</h2>
        <p className="text-fg-muted">{patientLine(facts?.patient ?? patient)}</p>
        {facts && (
          <p className="text-sm text-fg-muted">
            {facts.last_visit
              ? <>Last visit {facts.last_visit.date} · {clean(facts.last_visit.type)}</>
              : "No previous visit"}
          </p>
        )}
        {b && s && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm font-medium ${s.cls}`}>
              <span aria-hidden="true">{s.icon}</span> {s.label}
            </span>
            {b.attempts > 1 && <span className="text-xs text-fg-subtle">{b.attempts} model drafts</span>}
            {b.cached && <span className="text-xs text-fg-subtle">written earlier today</span>}
          </div>
        )}
        {b?.narrator && b.narrator_fallback_from && (
          <p className="mt-1 text-xs text-fg-subtle">
            {b.narrator_fallback_from} was unavailable, so {b.narrator} wrote these lines. The same checks applied.
          </p>
        )}
      </header>

      {/* scrolls */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">
        {state.kind === "loading" && <Loading />}
        {state.kind === "limited" && <LimitNotice message={state.message} onRetry={() => setAttempt((a) => a + 1)} />}
        {state.kind === "error" && (
          <div role="alert" className="rounded-md border border-danger-border bg-danger-soft p-4 text-danger-fg">
            <p className="font-medium">{state.notFound ? "This patient isn't in the record." : "Couldn't load the briefing."}</p>
            <p className="mb-3 text-sm">{state.message}</p>
            {!state.notFound && (
              <button type="button" onClick={() => setAttempt((a) => a + 1)} className="rounded-md border border-danger-border bg-bg px-3 py-1 text-sm hover:bg-subtle">
                Try again
              </button>
            )}
          </div>
        )}
        {b && <BriefingBody b={b} />}
      </div>
    </section>
  );
}

function Loading() {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div role="status" className="rounded-md border border-border bg-surface p-4">
      <p className="flex items-center gap-2 font-medium"><Spinner /> Checking the record and writing the briefing…</p>
      <p className="mt-1 text-sm text-fg-muted">
        A local model drafts the summary and code checks every number against the record. This usually takes 5–15 seconds
        {secs > 0 && <> ({secs} s so far)</>}.
      </p>
    </div>
  );
}

function BriefingBody({ b }: { b: Briefing }) {
  const lines = classifyLines(b);
  return (
    <div className="space-y-6">
      <div>
        <ol className="space-y-1.5" aria-label="Briefing">
          {lines.map((l, i) => (
            <li key={i} className={`border-l-4 py-1 pl-3 ${AUTHOR_STYLE[l.author].border}`}>
              <span>{l.text}</span>{" "}
              <span title={authorHelp(l.author, b.narrator)}>
                <Tag tone={AUTHOR_STYLE[l.author].tone} className="ml-1">{authorLabel(l.author, b.narrator)}</Tag>
              </span>
            </li>
          ))}
        </ol>

        <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-fg-muted" aria-label="Who wrote each line">
          {/* only the authors that wrote something here: no model entry when no model line */}
          {(["model", "added", "record"] as const).filter((a) => lines.some((l) => l.author === a)).map((a) => (
            <div key={a} className="flex items-center gap-1.5">
              <dt className={`border-l-4 pl-1.5 font-medium text-fg ${AUTHOR_STYLE[a].border}`}>{authorLabel(a, b.narrator)}</dt>
              <dd>{authorHelp(a, b.narrator)}</dd>
            </div>
          ))}
        </dl>
      </div>

      <Labs labs={b.facts.labs} />
      <Medications facts={b.facts} />
      <Problems facts={b.facts} />
      <Events facts={b.facts} />

      {b.limitations.length > 0 && (
        <aside className="border-t border-border pt-3 text-sm text-fg-subtle">
          <p className="font-medium">Limits of this record</p>
          <ul className="list-disc pl-5">{b.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </aside>
      )}
    </div>
  );
}

function Labs({ labs }: { labs: Lab[] }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div>
      <SectionTitle>Labs</SectionTitle>
      {labs.length === 0 ? <Empty>No lab results on record.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-fg-subtle">
              <tr className="border-b border-border">
                <th scope="col" className="py-1.5 pr-3 font-medium">Test</th>
                <th scope="col" className="py-1.5 pr-3 font-medium">Previous → latest</th>
                <th scope="col" className="py-1.5 pr-3 font-medium">Range</th>
                <th scope="col" className="py-1.5 font-medium"><span className="sr-only">Sources</span></th>
              </tr>
            </thead>
            <tbody>
              {labs.map((l) => {
                const shown = open === l.concept;
                return [
                  <tr key={l.concept} className="border-b border-border align-top">
                    <th scope="row" className="py-2 pr-3 font-medium">
                      {labName(l.concept)}
                      {l.new_since_last_visit && <span className="mt-0.5 block"><Tag tone="accent" className="font-normal">new result</Tag></span>}
                    </th>
                    <td className="py-2 pr-3">
                      {l.latest ? (
                        <>
                          {l.baseline && <><Point p={l.baseline} /> <span aria-hidden="true" className="text-fg-subtle">→</span><span className="sr-only">to</span> </>}
                          <Point p={l.latest} strong />
                          {" "}<Direction d={l.direction} />
                        </>
                      ) : <span className="text-fg-muted italic">No results</span>}
                    </td>
                    <td className="py-2 pr-3"><Range flag={l.latest_out_of_range} /></td>
                    <td className="py-2 text-right">
                      <button
                        type="button"
                        onClick={() => setOpen(shown ? null : l.concept)}
                        aria-expanded={shown}
                        className="rounded px-1.5 text-xs text-accent-fg hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-accent"
                      >
                        {shown ? "hide" : "source"}
                      </button>
                    </td>
                  </tr>,
                  shown && (
                    <tr key={l.concept + "-src"} className="border-b border-border bg-surface">
                      <td colSpan={4} className="px-2 py-1.5 text-xs">
                        {l.latest && <div>Latest: <SourceId id={l.latest.fhir_id} /></div>}
                        {l.baseline && <div>Previous: <SourceId id={l.baseline.fhir_id} /></div>}
                      </td>
                    </tr>
                  ),
                ];
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Point({ p, strong }: { p: { value: number; unit: string; date: string; fhir_id: string }; strong?: boolean }) {
  return (
    <span title={`Source: ${p.fhir_id}`}>
      <span className={strong ? "font-semibold" : ""}>{value(p.value, p.unit)}</span>{" "}
      <span className="text-xs text-fg-subtle">({p.date})</span>
    </span>
  );
}

function Direction({ d }: { d: Lab["direction"] }) {
  if (d === "up") return <span className="text-fg-muted" title="rose"><span aria-hidden="true">↑</span><span className="sr-only">rose</span></span>;
  if (d === "down") return <span className="text-fg-muted" title="fell"><span aria-hidden="true">↓</span><span className="sr-only">fell</span></span>;
  return null;
}

function Range({ flag }: { flag: boolean | null }) {
  if (flag === true) return <span className="inline-flex items-center gap-1 rounded bg-warn-soft px-1.5 font-medium whitespace-nowrap text-warn-fg"><span aria-hidden="true">⚠</span> Out of range</span>;
  if (flag === null) return <span className="text-xs text-fg-subtle">no reference range</span>;
  return null;
}

function Medications({ facts }: { facts: Facts }) {
  const newIds = new Set((facts.medications.new_since_last_visit ?? []).map((m) => m.fhir_id));
  const meds = [...facts.medications.active].sort((a, b) => a.display.localeCompare(b.display));
  return (
    <div>
      <SectionTitle>Current medications</SectionTitle>
      {meds.length === 0 ? <Empty>No active medications on record.</Empty> : (
        <ul className="space-y-1">
          {meds.map((m) => (
            <li key={m.fhir_id} className="flex flex-wrap items-baseline gap-x-2" title={`Source: ${m.fhir_id}`}>
              <span className="font-medium capitalize">{m.display}</span>
              {newIds.has(m.fhir_id) && <Tag tone="accent" className="font-medium">New since last visit</Tag>}
              {m.first_prescribed && <span className="text-sm text-fg-subtle">since {m.first_prescribed}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Problems({ facts }: { facts: Facts }) {
  const newIds = new Set((facts.new_conditions ?? []).map((c) => c.id));
  return (
    <div>
      <SectionTitle>Known problems</SectionTitle>
      {facts.problems.length === 0 ? <Empty>No known problems on record.</Empty> : (
        <ul className="space-y-1">
          {facts.problems.map((p) => (
            <li key={p.id} className="flex flex-wrap items-baseline gap-x-2" title={`Source: ${p.id}`}>
              <span>{clean(p.display)}</span>
              {newIds.has(p.id) && <Tag tone="accent" className="font-medium">New since last visit</Tag>}
              <span className="text-sm text-fg-subtle">{p.onset ? `since ${p.onset.slice(0, 4)}` : "onset not recorded"}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Events({ facts }: { facts: Facts }) {
  if (!facts.last_visit) return null;
  return (
    <div>
      <SectionTitle>Hospital or urgent care since last visit</SectionTitle>
      {facts.events_since_last_visit.length === 0 ? <Empty>None recorded since the last visit.</Empty> : (
        <ul className="space-y-1">
          {facts.events_since_last_visit.map((e) => (
            <li key={e.id} title={`Source: ${e.id}`}>{clean(e.type)} <span className="text-sm text-fg-subtle">{e.date}</span></li>
          ))}
        </ul>
      )}
    </div>
  );
}
