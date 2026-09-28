# Doctor Copilot — frontend

React + TypeScript + Tailwind UI for the Doctor Copilot API: a pre-visit briefing that shows who
wrote each line, and a Q&A panel that streams every tool call and answer check live.

## Run it

Start the backend first, from the repo root:

```sh
uv run uvicorn copilot.api:default_app --factory --port 8000
```

Then, in `frontend/`:

```sh
npm install
npm run dev        # http://localhost:5173
npm test           # unit tests (Vitest)
npm run build      # type-check + production build into dist/
```

The dev server must run on port 5173: that is the origin the backend's CORS allows by default
(set `ALLOWED_ORIGINS` on the backend to serve the UI from anywhere else).

## Configuration

| Variable       | Default                 | Meaning             |
|----------------|-------------------------|---------------------|
| `VITE_API_URL` | `http://localhost:8000` | Backend base URL    |

Set it in `frontend/.env.local` (`VITE_API_URL=http://host:port`) or inline:
`VITE_API_URL=http://host:port npm run dev`. It is read at build time.

## Layout of the code

```
src/
  api/types.ts        every API shape
  api/client.ts       fetch calls; /ask streams with fetch + ReadableStream (EventSource can't POST)
  api/sse.ts          SSE parser: events split across chunks, several per chunk, trailing data
  lib/authorship.ts   who wrote each briefing line: MedGemma, added from record, or from record
  lib/citations.ts    splits answers into text and [source-id] citations
  lib/trace.ts        folds stream events into one Q&A turn (pure, tested)
  components/         Sidebar, BriefingPanel, QAPanel, Trace
```

Switching patients remounts both panels (`key={patient.id}`), which aborts the in-flight briefing
request and Q&A stream. React StrictMode is off on purpose: in dev it runs effects twice, and the
backend can't cancel a briefing once started, so every page load would run the local model twice.

## Theme

Light / Dark / System toggle in the sidebar header, saved in `localStorage` (`theme`); "System"
follows the OS setting live. Tailwind's class strategy (`<html class="dark">`) with every colour
defined once per theme as a CSS variable in `src/index.css`; components use only those tokens
(`bg-surface`, `text-fg-muted`, `border-warn-border`, …). `src/lib/contrast.test.ts` reads the
tokens from the CSS and fails if any text/background pair drops below WCAG AA (4.5:1).
