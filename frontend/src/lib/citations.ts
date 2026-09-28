export type Segment = { kind: "text"; text: string } | { kind: "cite"; ids: string[] };

// A citation is [id] or [id1, id2]: ids are record ids like demo-ravi-kumar-obs-potassium-3
// or UUIDs, so no spaces inside an id. Brackets holding anything else stay as plain text.
const BRACKET = /\[([^[\]]+)\]/g;
const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]*$/;

export function parseCitations(text: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  const pushText = (t: string) => {
    if (!t) return;
    const prev = out[out.length - 1];
    if (prev?.kind === "text") prev.text += t;
    else out.push({ kind: "text", text: t });
  };
  for (const m of text.matchAll(BRACKET)) {
    const ids = m[1].split(",").map((s) => s.trim());
    const start = m.index!;
    pushText(text.slice(last, start));
    if (ids.every((id) => ID.test(id))) out.push({ kind: "cite", ids });
    else pushText(m[0]);
    last = start + m[0].length;
  }
  pushText(text.slice(last));
  return out;
}

/** Every value of a "source" field anywhere inside a tool result. */
export function sourceIds(result: unknown): string[] {
  const out: string[] = [];
  const walk = (v: unknown) => {
    if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v === "object") {
      for (const [k, x] of Object.entries(v)) {
        if (k === "source" && typeof x === "string") out.push(x);
        else walk(x);
      }
    }
  };
  walk(result);
  return out;
}
