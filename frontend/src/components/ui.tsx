import { useState, type ReactNode } from "react";

export function Spinner({ label }: { label?: string }) {
  return (
    <span
      role={label ? "status" : undefined}
      aria-label={label}
      className="inline-block size-3.5 shrink-0 animate-spin rounded-full border-2 border-border-strong border-t-accent"
    />
  );
}

/** A record id shown small and monospace, with a copy button. */
export function SourceId({ id }: { id: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // clipboard blocked; the id is still selectable
    }
  };
  return (
    <span className="inline-flex items-center gap-1 font-mono text-xs text-fg-muted">
      <span className="select-all break-all">{id}</span>
      <button
        type="button"
        onClick={copy}
        className="rounded px-1 text-accent-fg hover:bg-subtle focus-visible:outline-2 focus-visible:outline-accent"
        aria-label={`Copy source id ${id}`}
      >
        {copied ? "copied" : "copy"}
      </button>
    </span>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg-subtle">{children}</h3>;
}

/** Empty lists are said out loud so they never look like missing data. */
export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-fg-muted italic">{children}</p>;
}

/** A small label: colour plus words, never colour alone. */
export function Tag({ tone, children, className = "" }: { tone: "accent" | "ok" | "warn" | "danger" | "neutral"; children: ReactNode; className?: string }) {
  const cls = {
    accent: "bg-accent-soft text-accent-fg",
    ok: "bg-ok-soft text-ok-fg",
    warn: "bg-warn-soft text-warn-fg",
    danger: "bg-danger-soft text-danger-fg",
    neutral: "bg-subtle text-fg-muted",
  }[tone];
  return <span className={`inline-block rounded px-1.5 text-xs whitespace-nowrap ${cls} ${className}`}>{children}</span>;
}

/** A 429 from the API: shown as a calm notice, retried only when the user asks. */
export function LimitNotice({ message, onRetry, disabled }: { message: string; onRetry: () => void; disabled?: boolean }) {
  return (
    <div role="status" className="rounded-md border border-accent-border bg-accent-soft p-4 text-fg">
      <p className="font-medium"><span aria-hidden="true">ⓘ </span>{message}</p>
      <button
        type="button"
        onClick={onRetry}
        disabled={disabled}
        className="mt-3 rounded-md border border-accent-border bg-bg px-3 py-1 text-sm text-accent-fg hover:bg-subtle focus-visible:outline-2 focus-visible:outline-accent disabled:opacity-50"
      >
        Try again
      </button>
    </div>
  );
}
