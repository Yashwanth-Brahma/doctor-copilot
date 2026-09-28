import { describe, expect, it } from "vitest";
import { parseCitations, sourceIds } from "./citations";

describe("parseCitations", () => {
  it("text without citations is one text segment", () => {
    expect(parseCitations("No results on record.")).toEqual([{ kind: "text", text: "No results on record." }]);
  });

  it("parses a single citation", () => {
    expect(parseCitations("Potassium was 5.2 mmol/L (2026-07-13) [demo-ravi-kumar-obs-potassium-3].")).toEqual([
      { kind: "text", text: "Potassium was 5.2 mmol/L (2026-07-13) " },
      { kind: "cite", ids: ["demo-ravi-kumar-obs-potassium-3"] },
      { kind: "text", text: "." },
    ]);
  });

  it("parses several ids in one bracket", () => {
    expect(parseCitations("Rose [a-1, b-2]. Started [c-3]")).toEqual([
      { kind: "text", text: "Rose " },
      { kind: "cite", ids: ["a-1", "b-2"] },
      { kind: "text", text: ". Started " },
      { kind: "cite", ids: ["c-3"] },
    ]);
  });

  it("parses UUID ids", () => {
    const id = "22a07c14-044c-3309-a24e-2d43e4a99dec";
    expect(parseCitations(`x [${id}]`)[1]).toEqual({ kind: "cite", ids: [id] });
  });

  it("leaves brackets that aren't ids as text", () => {
    expect(parseCitations("see [the note above] please")).toEqual([{ kind: "text", text: "see [the note above] please" }]);
  });

  it("empty text gives no segments", () => {
    expect(parseCitations("")).toEqual([]);
  });
});

describe("sourceIds", () => {
  it("collects every nested source field", () => {
    const result = { lab: "Potassium", points: [{ value: 4.7, source: "p-2" }, { value: 5.2, source: "p-3" }], latest: { source: "p-3" } };
    expect(sourceIds(result)).toEqual(["p-2", "p-3", "p-3"]);
  });
});
