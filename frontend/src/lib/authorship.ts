import type { Briefing } from "../api/types";

/** Who wrote a line of the briefing. */
export type Author = "model" | "added" | "record";

/** narrator: the model the API says wrote the model lines, e.g. "MedGemma" or "gpt-4.1-mini". */
export function authorLabel(a: Author, narrator: string | null): string {
  return { model: `${narrator ?? "Model"} · checked`, added: "Added from record", record: "From record" }[a];
}

export function authorHelp(a: Author, narrator: string | null): string {
  return {
    model: `Written by ${narrator ?? "the model"}, then checked by code against the record`,
    added: "The model left this out; code added it from the record",
    record: "Written by code directly from the record, no model involved",
  }[a];
}

export interface BriefingLine {
  text: string;
  author: Author;
}

/** Split the briefing text into lines and label each with who wrote it:
 *  a context line -> code; an added line -> code filling a model omission;
 *  fallback / no_changes, or no narrator (no model call) -> all code;
 *  anything else -> the model (verified). */
export function classifyLines(b: Pick<Briefing, "text" | "status" | "added" | "context" | "narrator">): BriefingLine[] {
  const context = new Set(b.context.map((s) => s.trim()));
  const added = new Set(b.added.map((s) => s.trim()));
  const allCode = b.status === "fallback" || b.status === "no_changes" || !b.narrator;
  return b.text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((text) => ({
      text,
      author: context.has(text) ? "record" : added.has(text) ? "added" : allCode ? "record" : "model",
    }));
}
