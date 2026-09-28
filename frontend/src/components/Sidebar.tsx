import { useMemo, useState } from "react";
import type { PatientListItem } from "../api/types";
import { patientLine } from "../lib/format";
import { useTheme, type ThemePref } from "../lib/theme";
import { Spinner } from "./ui";

export const DEMO_ID = "demo-ravi-kumar";

interface Props {
  patients: PatientListItem[] | null;
  error: string | null;
  onRetry: () => void;
  selectedId: string | null;
  onSelect: (p: PatientListItem) => void;
}

export function Sidebar({ patients, error, onRetry, selectedId, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = (patients ?? []).filter((p) => !q || p.name.toLowerCase().includes(q));
    // demo patient pinned first, whatever order the API returns
    return [...list.filter((p) => p.id === DEMO_ID), ...list.filter((p) => p.id !== DEMO_ID)];
  }, [patients, query]);

  return (
    <nav aria-label="Patients" className="flex max-h-[30dvh] min-h-0 flex-col border-b border-border bg-surface md:h-full md:max-h-none md:border-r md:border-b-0">
      {/* fixed: title, theme, search */}
      <div className="shrink-0 border-b border-border p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h1 className="text-base font-semibold whitespace-nowrap">Doctor Copilot</h1>
          <ThemeToggle />
        </div>
        <label htmlFor="patient-search" className="mb-1 block text-sm text-fg-muted">
          Find a patient
        </label>
        <input
          id="patient-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name"
          className="w-full rounded-md border border-border-strong bg-bg px-3 py-1.5 placeholder:text-fg-subtle focus:border-accent focus:outline-2 focus:outline-accent-border"
        />
        {patients && (
          <p className="mt-2 text-xs text-fg-subtle" aria-live="polite">
            {shown.length} of {patients.length} patients
          </p>
        )}
      </div>

      {/* scrolls */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {error ? (
          <div className="p-4 text-sm">
            <p className="mb-2 text-danger-fg">Couldn't load patients: {error}</p>
            <button type="button" onClick={onRetry} className="rounded-md border border-border-strong bg-bg px-3 py-1 hover:bg-subtle">
              Try again
            </button>
          </div>
        ) : !patients ? (
          <p className="flex items-center gap-2 p-4 text-sm text-fg-muted">
            <Spinner /> Loading patients…
          </p>
        ) : shown.length === 0 ? (
          <p className="p-4 text-sm text-fg-muted">No patient matches "{query}".</p>
        ) : (
          <ul>
            {shown.map((p) => {
              const selected = p.id === selectedId;
              return (
                <li key={p.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(p)}
                    aria-current={selected ? "true" : undefined}
                    className={`w-full border-l-4 px-4 py-2 text-left focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent ${
                      selected ? "border-accent bg-accent-soft" : "border-transparent hover:bg-subtle"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <span className={selected ? "font-semibold" : "font-medium"}>{p.name}</span>
                      {p.id === DEMO_ID && (
                        <span className="rounded border border-accent-border px-1.5 text-[11px] font-medium uppercase tracking-wide text-accent-fg">demo</span>
                      )}
                    </span>
                    <span className="block text-sm text-fg-muted">{patientLine(p)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </nav>
  );
}

const THEMES: { value: ThemePref; label: string }[] = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
];

function ThemeToggle() {
  const [pref, setPref] = useTheme();
  return (
    <div role="group" aria-label="Colour theme" className="flex rounded-md border border-border-strong p-0.5 text-xs">
      {THEMES.map((t) => (
        <button
          key={t.value}
          type="button"
          aria-pressed={pref === t.value}
          onClick={() => setPref(t.value)}
          className={`rounded px-1 py-0.5 focus-visible:outline-2 focus-visible:outline-accent ${
            pref === t.value ? "bg-accent text-on-accent font-medium" : "text-fg-muted hover:bg-subtle"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
