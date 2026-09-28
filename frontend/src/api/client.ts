import { createSSEParser } from "./sse";
import type { AskEvent, Briefing, PatientListItem } from "./types";

export const API_URL: string = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** FastAPI errors: {"detail": "..."} for 404, {"detail": [{msg, ...}]} for 422. */
async function errorFrom(res: Response): Promise<ApiError> {
  let message = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg?: string }) => d.msg).join("; ");
  } catch {
    // not JSON; keep the status line
  }
  return new ApiError(res.status, message);
}

async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(API_URL + path, { signal });
  if (!res.ok) throw await errorFrom(res);
  return res.json() as Promise<T>;
}

export function getPatients(signal?: AbortSignal) {
  return getJSON<PatientListItem[]>("/patients", signal);
}

export function getBriefing(patientId: string, signal?: AbortSignal) {
  return getJSON<Briefing>(`/patients/${encodeURIComponent(patientId)}/briefing`, signal);
}

/** POST a question and call onEvent for each event as it arrives. Resolves when the stream ends.
 *  Throws ApiError for 404/422 (sent before any stream starts); aborting rejects with AbortError. */
export async function ask(
  patientId: string,
  question: string,
  onEvent: (e: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_URL}/patients/${encodeURIComponent(patientId)}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!res.ok) throw await errorFrom(res);
  if (!res.body) throw new Error("The server returned no stream");

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = createSSEParser();
  const emit = (payloads: string[]) => {
    for (const p of payloads) {
      try {
        onEvent(JSON.parse(p) as AskEvent);
      } catch {
        onEvent({ type: "error", message: "Received an unreadable event from the server" });
      }
    }
  };
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    emit(parser.push(value));
  }
  emit(parser.flush());
}
