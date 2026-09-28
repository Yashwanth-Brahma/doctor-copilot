"""Auth proxy in front of Ollama, run on the Mac that hosts MedGemma.

Ollama has no authentication, so it must never be exposed directly: anyone who found the tunnel
URL could use the model. This proxy is what the tunnel exposes. It
  - requires "Authorization: Bearer <NARRATOR_TOKEN>"
  - allows only the chat endpoint, and only the configured model (NARRATOR_MODEL)
  - streams Ollama's reply straight through

    uv run python -m copilot.narrator_proxy            # listens on 127.0.0.1:8787
    ngrok http 8787 --url=<your-static-domain>         # the public address Railway calls
"""
import hmac
import json
import os

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse


def create_proxy(token: str, model: str, ollama_url: str = "http://localhost:11434",
                 transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    if not token or len(token) < 24:
        raise RuntimeError("NARRATOR_TOKEN must be set and at least 24 characters long")
    app = FastAPI(title="narrator proxy", docs_url=None, redoc_url=None, openapi_url=None)
    client = httpx.AsyncClient(base_url=ollama_url, transport=transport,
                               timeout=httpx.Timeout(120, connect=5))

    def authorize(request: Request):
        given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(given.encode(), token.encode()):
            raise HTTPException(401, "unauthorized")

    @app.get("/health")
    async def health(request: Request):
        authorize(request)
        r = await client.get("/api/version")
        return {"ok": r.status_code == 200, "ollama": r.json() if r.status_code == 200 else None}

    @app.post("/api/chat")
    async def chat(request: Request):
        authorize(request)
        body = await request.json()
        if body.get("model") != model:
            raise HTTPException(403, "model not allowed")
        upstream = await client.send(client.build_request("POST", "/api/chat", json=body), stream=True)
        if upstream.status_code != 200:
            detail = (await upstream.aread()).decode(errors="replace")[:300]
            await upstream.aclose()
            return JSONResponse({"error": detail}, status_code=upstream.status_code)

        async def relay():
            try:
                async for chunk in upstream.aiter_bytes():      # decoded: we don't forward content-encoding
                    yield chunk
            finally:
                await upstream.aclose()
        return StreamingResponse(relay(), media_type=upstream.headers.get("content-type", "application/x-ndjson"))

    return app


def main():
    import uvicorn
    from dotenv import load_dotenv
    load_dotenv()
    app = create_proxy(os.environ.get("NARRATOR_TOKEN", ""), os.environ.get("NARRATOR_MODEL", ""),
                       os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("NARRATOR_PROXY_PORT", 8787)))


if __name__ == "__main__":
    main()
