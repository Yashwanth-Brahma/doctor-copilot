// Display helpers that mirror the backend's own (narrator_input.py): the UI should write
// labs and units the same way the briefing text does.

const LAB_NAMES: Record<string, string> = {
  hba1c: "HbA1c",
  egfr: "eGFR",
  creatinine: "Creatinine",
  glucose: "Glucose",
  potassium: "Potassium",
};

const UNIT_DISPLAY: Record<string, string> = { "mL/min/{1.73_m2}": "mL/min/1.73m²" };

export const labName = (concept: string) => LAB_NAMES[concept] ?? concept;
export const unit = (u: string) => UNIT_DISPLAY[u] ?? u;

/** "Essential hypertension (disorder)" -> "Essential hypertension" */
export const clean = (display: string) => display.replace(/\s*\([a-z/ ]+\)\s*$/, "").trim();

export function value(v: number, u: string) {
  const d = unit(u);
  return `${v}${d === "%" ? "" : " "}${d}`;
}

export function patientLine(p: { age: number | null; sex: string }) {
  return [p.age === null ? "age unknown" : `${p.age} y`, p.sex].filter(Boolean).join(" · ");
}
