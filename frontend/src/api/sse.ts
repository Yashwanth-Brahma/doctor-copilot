// Server-sent events parser for the /ask stream. EventSource can't POST, so the client reads
// the response body itself and feeds decoded text chunks in here. Chunks split anywhere: in the
// middle of a line, between "\n" and "\n", or several events at once.

export interface SSEParser {
  /** Feed a chunk of decoded text; returns the `data` payloads of every event it completed. */
  push(chunk: string): string[];
  /** Call at end of stream: returns the last event if the server didn't send the blank line. */
  flush(): string[];
}

export function createSSEParser(): SSEParser {
  let buffer = "";

  function eventData(block: string): string | null {
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("data:")) data.push(line.slice(line.startsWith("data: ") ? 6 : 5));
      // other fields (event:, id:, retry:) and comments (":") aren't used by this API
    }
    return data.length ? data.join("\n") : null;
  }

  return {
    push(chunk) {
      buffer += chunk.replace(/\r\n?/g, "\n");
      const out: string[] = [];
      let end: number;
      while ((end = buffer.indexOf("\n\n")) !== -1) {
        const d = eventData(buffer.slice(0, end));
        buffer = buffer.slice(end + 2);
        if (d !== null) out.push(d);
      }
      return out;
    },
    flush() {
      const d = buffer.trim() ? eventData(buffer) : null;
      buffer = "";
      return d === null ? [] : [d];
    },
  };
}
