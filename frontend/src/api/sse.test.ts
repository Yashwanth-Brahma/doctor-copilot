import { describe, expect, it } from "vitest";
import { createSSEParser } from "./sse";

const ev = (o: object) => `data: ${JSON.stringify(o)}\n\n`;

describe("SSE parser", () => {
  it("parses one complete event", () => {
    const p = createSSEParser();
    expect(p.push(ev({ type: "start", question: "q?" }))).toEqual(['{"type":"start","question":"q?"}']);
  });

  it("parses several events in one chunk", () => {
    const p = createSSEParser();
    const out = p.push(ev({ type: "start" }) + ev({ type: "gate" }) + ev({ type: "done" }));
    expect(out.map((d) => JSON.parse(d).type)).toEqual(["start", "gate", "done"]);
  });

  it("joins an event split across chunks, at any byte", () => {
    const whole = ev({ type: "tool_result", result: { source: "x-1" } }) + ev({ type: "done" });
    for (let cut = 1; cut < whole.length; cut++) {
      const p = createSSEParser();
      const out = [...p.push(whole.slice(0, cut)), ...p.push(whole.slice(cut))];
      expect(out.map((d) => JSON.parse(d).type)).toEqual(["tool_result", "done"]);
    }
  });

  it("splits the blank-line terminator across chunks", () => {
    const p = createSSEParser();
    expect(p.push('data: {"type":"done"}\n')).toEqual([]);
    expect(p.push("\n")).toEqual(['{"type":"done"}']);
  });

  it("keeps a trailing partial event until more arrives or the stream ends", () => {
    const p = createSSEParser();
    expect(p.push(ev({ type: "start" }) + 'data: {"type":"do')).toHaveLength(1);
    expect(p.push('ne"}')).toEqual([]);
    expect(p.flush()).toEqual(['{"type":"done"}']);
    expect(p.flush()).toEqual([]);
  });

  it("handles CRLF line endings and ignores comments and other fields", () => {
    const p = createSSEParser();
    expect(p.push(': keep-alive\r\n\r\nevent: x\r\ndata: {"a":1}\r\n\r\n')).toEqual(['{"a":1}']);
  });

  it("joins multi-line data with newlines", () => {
    const p = createSSEParser();
    expect(p.push("data: a\ndata: b\n\n")).toEqual(["a\nb"]);
  });
});
