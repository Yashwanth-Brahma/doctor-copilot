import json

import httpx
import pytest
from fastapi.testclient import TestClient

from copilot.narrator_proxy import create_proxy

TOKEN = "t" * 32
MODEL = "hf.co/unsloth/medgemma-4b-it-GGUF:Q5_K_M"


def fake_ollama(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/version":
        return httpx.Response(200, json={"version": "0.12"})
    body = json.loads(request.content)
    lines = [{"model": body["model"], "message": {"role": "assistant", "content": "Hi"}, "done": False},
             {"model": body["model"], "message": {"role": "assistant", "content": ""}, "done": True}]
    return httpx.Response(200, content="\n".join(json.dumps(l) for l in lines).encode(),
                          headers={"content-type": "application/x-ndjson"})


def client():
    return TestClient(create_proxy(TOKEN, MODEL, transport=httpx.MockTransport(fake_ollama)))


def chat(c, token=TOKEN, model=MODEL):
    return c.post("/api/chat", json={"model": model, "messages": []},
                  headers={"Authorization": f"Bearer {token}"} if token else {})


def test_no_token_or_wrong_token_is_rejected():
    c = client()
    assert chat(c, token=None).status_code == 401
    assert chat(c, token="wrong" * 6).status_code == 401


def test_only_the_configured_model_is_allowed():
    assert chat(client(), model="llama3:70b").status_code == 403


def test_streams_ollama_reply_through():
    r = chat(client())
    assert r.status_code == 200
    assert [json.loads(l)["done"] for l in r.text.splitlines()] == [False, True]


def test_other_ollama_endpoints_are_not_exposed():
    c = client()
    h = {"Authorization": f"Bearer {TOKEN}"}
    assert c.post("/api/pull", json={"name": "x"}, headers=h).status_code in (404, 405)
    assert c.get("/api/tags", headers=h).status_code in (404, 405)


def test_refuses_to_start_with_a_weak_token():
    with pytest.raises(RuntimeError):
        create_proxy("short", MODEL)
