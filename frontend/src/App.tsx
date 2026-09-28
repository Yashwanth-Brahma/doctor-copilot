import { useCallback, useEffect, useState } from "react";
import { getPatients } from "./api/client";
import type { PatientListItem } from "./api/types";
import { BriefingPanel } from "./components/BriefingPanel";
import { QAPanel } from "./components/QAPanel";
import { DEMO_ID, Sidebar } from "./components/Sidebar";

type Tab = "briefing" | "ask";

export default function App() {
  const [patients, setPatients] = useState<PatientListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<PatientListItem | null>(null);
  const [tab, setTab] = useState<Tab>("briefing");

  const load = useCallback((signal?: AbortSignal) => {
    setError(null);
    getPatients(signal)
      .then((ps) => {
        setPatients(ps);
        setSelected((s) => s ?? ps.find((p) => p.id === DEMO_ID) ?? ps[0] ?? null);
      })
      .catch((e: unknown) => { if (!signal?.aborted) setError(e instanceof Error ? e.message : String(e)); });
  }, []);

  useEffect(() => {
    const c = new AbortController();
    load(c.signal);
    return () => c.abort();
  }, [load]);

  // The page never scrolls: the app fills the viewport and each column scrolls on its own.
  return (
    <div className="flex h-dvh flex-col overflow-hidden md:grid md:grid-cols-[17rem_minmax(0,1fr)] md:grid-rows-[minmax(0,1fr)]">
      <Sidebar patients={patients} error={error} onRetry={() => load()} selectedId={selected?.id ?? null} onSelect={setSelected} />
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        {selected ? (
          <>
            {/* below xl there's no room for two columns: tabs instead (both panels stay mounted) */}
            <div role="tablist" aria-label="Panels" className="flex shrink-0 border-b border-border xl:hidden">
              {(["briefing", "ask"] as const).map((t) => (
                <button
                  key={t}
                  role="tab"
                  type="button"
                  aria-selected={tab === t}
                  onClick={() => setTab(t)}
                  className={`flex-1 border-b-2 px-4 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent ${
                    tab === t ? "border-accent text-accent-fg" : "border-transparent text-fg-muted hover:text-fg"
                  }`}
                >
                  {t === "briefing" ? "Briefing" : "Ask"}
                </button>
              ))}
            </div>
            {/* key = patient id: changing patient remounts both panels, which aborts the
                in-flight briefing fetch and Q&A stream and resets the conversation */}
            <div key={selected.id} className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)] grid-rows-[minmax(0,1fr)] xl:grid-cols-2 xl:divide-x xl:divide-border">
              <div className={`min-h-0 ${tab === "briefing" ? "" : "hidden xl:block"}`}>
                <BriefingPanel patient={selected} />
              </div>
              <div className={`min-h-0 ${tab === "ask" ? "" : "hidden xl:block"}`}>
                <QAPanel patientId={selected.id} patientName={selected.name} sex={selected.sex} />
              </div>
            </div>
          </>
        ) : (
          <p className="p-6 text-fg-muted">{patients ? "Select a patient." : ""}</p>
        )}
      </main>
    </div>
  );
}
