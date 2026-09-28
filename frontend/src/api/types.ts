// Shapes of the Doctor Copilot API (src/copilot/api.py). Fields the backend sends but the UI
// doesn't use are left optional so the types stay honest without being load-bearing.

export type Sex = string;

export interface PatientListItem {
  id: string;
  name: string;
  sex: Sex;
  age: number | null;
}

// ---- Briefing: GET /patients/{id}/briefing ----

export type BriefingStatus =
  | "verified"
  | "verified_after_retry"
  | "verified_with_additions"
  | "fallback"
  | "no_changes";

export interface LabPoint {
  value: number;
  unit: string;
  date: string;
  fhir_id: string;
  loinc?: string;
}

export interface Lab {
  concept: string;
  id?: string;
  latest: LabPoint | null;
  baseline: LabPoint | null;
  change: number | null;
  direction: "up" | "down" | null;
  latest_out_of_range: boolean | null;
  new_since_last_visit: boolean | null;
  measurements?: number;
}

export interface Medication {
  display: string;
  first_prescribed: string | null;
  fhir_id: string;
  rxnorm?: string;
}

export interface Problem {
  display: string;
  onset: string | null;
  id: string;
  code?: string;
}

export interface Visit {
  date: string;
  type: string;
  encounter_id: string;
}

export interface HospitalEvent {
  type: string;
  date: string;
  id: string;
}

export interface Facts {
  as_of?: string;
  patient: { id: string; name: string; age: number | null; sex: Sex };
  last_visit: Visit | null;
  labs: Lab[];
  medications: {
    active: Medication[];
    // the backend treats this as possibly null (`or []`), so the type does too
    new_since_last_visit: Medication[] | null;
    stopped_since_last_visit?: Medication[] | null;
  };
  problems: Problem[];
  new_conditions?: Problem[];
  events_since_last_visit: HospitalEvent[];
  limitations: string[];
}

export interface Briefing {
  patient_id: string;
  text: string;
  status: BriefingStatus;
  attempts: number;
  /** who wrote the model lines, e.g. "MedGemma"; null when no model was called */
  narrator: string | null;
  /** true when the API returned a briefing it wrote earlier today */
  cached: boolean;
  added: string[];
  context: string[];
  facts: Facts;
  limitations: string[];
}

// ---- Q&A: POST /patients/{id}/ask (server-sent events) ----

export type GateCategory = "record_question" | "advice_request" | "off_topic";
export type AnswerStatus = "verified" | "redirected" | "unverified";

export interface ToolCall {
  tool: string;
  args: Record<string, unknown>;
}

export interface CheckProblem {
  sentence: string;
  problem: string;
}

export type AskEvent =
  | { type: "start"; question: string }
  | { type: "gate"; category: GateCategory; reason: string }
  | { type: "tool_calls"; calls: ToolCall[] }
  | {
      type: "tool_result";
      tool: string;
      args: Record<string, unknown>;
      result: unknown;
      seconds: number;
      patient_id_overridden: boolean;
    }
  | { type: "check"; attempt: number; answer: string; problems: CheckProblem[] }
  | { type: "answer"; text: string; status: AnswerStatus }
  | { type: "error"; message: string }
  | { type: "done" };
