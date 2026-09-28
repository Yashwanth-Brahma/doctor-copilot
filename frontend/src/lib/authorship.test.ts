import { describe, expect, it } from "vitest";
import { classifyLines } from "./authorship";

const context = ["Current medications: apixaban, spironolactone (new since last visit).", "Known problems: Atrial fibrillation (since 2025)."];
const base = {
  text: ["The last visit was on 2026-04-01.", "Potassium rose from 4.7 mmol/L (2026-04-01) to 5.2 mmol/L (2026-07-13).", ...context].join("\n"),
  added: [] as string[],
  context,
  narrator: "MedGemma" as string | null,
};
const authors = (b: Parameters<typeof classifyLines>[0]) => classifyLines(b).map((l) => l.author);

describe("classifyLines", () => {
  it("verified: model lines, then context lines from the record", () => {
    expect(authors({ ...base, status: "verified" })).toEqual(["model", "model", "record", "record"]);
  });

  it("verified_after_retry is still the model", () => {
    expect(authors({ ...base, status: "verified_after_retry" })).toEqual(["model", "model", "record", "record"]);
  });

  it("marks lines code added to the model's draft", () => {
    const added = "Spironolactone was started on 2026-05-31.";
    const b = { ...base, status: "verified_with_additions" as const, added: [added], text: base.text.replace("\nCurrent", `\n${added}\nCurrent`) };
    expect(authors(b)).toEqual(["model", "model", "added", "record", "record"]);
  });

  it("fallback: every line written by code", () => {
    expect(authors({ ...base, status: "fallback" })).toEqual(["record", "record", "record", "record"]);
  });

  it("no_changes: every line written by code", () => {
    const text = ["The last visit was on 2026-04-01.", "No new lab results, medications, conditions or hospital visits since then.", ...context].join("\n");
    expect(authors({ ...base, text, status: "no_changes" })).toEqual(["record", "record", "record", "record"]);
  });

  it("no narrator means no model call: every line written by code", () => {
    expect(authors({ ...base, status: "verified", narrator: null })).toEqual(["record", "record", "record", "record"]);
  });

  it("keeps line text and drops blank lines", () => {
    const lines = classifyLines({ ...base, text: base.text + "\n\n", status: "verified" });
    expect(lines).toHaveLength(4);
    expect(lines[0].text).toBe("The last visit was on 2026-04-01.");
  });
});
