"""Which model writes the briefing, and what happens when it can't.

    NARRATOR_PROVIDER=ollama | openai
    NARRATOR_MODEL=<Ollama model name, or an OpenAI model>
    NARRATOR_BASE_URL=https://<tunnel>        # Ollama somewhere else (your Mac via a tunnel)
    NARRATOR_TOKEN=<secret>                   # sent to the auth proxy in front of that Ollama
    NARRATOR_FALLBACK_MODEL=gpt-4.1-mini      # OpenAI model used when Ollama can't be reached

Production: MedGemma on the developer's Mac through a tunnel, with OpenAI taking over when the
Mac is off, asleep or slow. The checker is what keeps the briefing accurate, so either model
is safe; the API reports which one actually wrote the lines.
"""
import os
import threading
import time

COOLDOWN_SECONDS = 300          # after a failure, skip the primary for 5 minutes
CONNECT_TIMEOUT = 3.0           # a sleeping Mac fails fast instead of stalling every briefing
READ_TIMEOUT = 90.0


def display_name(model: str | None) -> str | None:
    """"hf.co/unsloth/medgemma-4b-it-GGUF:Q5_K_M" -> "MedGemma"; OpenAI names stay as they are."""
    if not model:
        return None
    return "MedGemma" if "medgemma" in model.lower() else model


def model_of(message) -> str | None:
    """The model that actually produced a reply (Ollama: "model", OpenAI: "model_name")."""
    meta = getattr(message, "response_metadata", None) or {}
    return meta.get("model") or meta.get("model_name")


class NarratorWithFallback:
    """Try the primary model; on any error (unreachable, timeout, refused) use the fallback,
    and skip the primary for COOLDOWN_SECONDS so later briefings don't each wait for it."""

    def __init__(self, primary, fallback, primary_name: str, cooldown: float = COOLDOWN_SECONDS,
                 clock=time.monotonic):
        self.primary, self.fallback, self.primary_name = primary, fallback, primary_name
        self.cooldown, self.clock = cooldown, clock
        self.down_until = 0.0
        self.last_error: str | None = None
        self.lock = threading.Lock()

    def primary_available(self) -> bool:
        return self.clock() >= self.down_until

    def invoke(self, messages):
        if self.primary_available():
            try:
                return self.primary.invoke(messages)
            except Exception as e:                      # network errors, timeouts, 401/403 from the proxy
                with self.lock:
                    self.down_until = self.clock() + self.cooldown
                    self.last_error = f"{type(e).__name__}: {e}"[:300]
        reply = self.fallback.invoke(messages)
        meta = getattr(reply, "response_metadata", None)
        if isinstance(meta, dict):
            meta["fallback_from"] = self.primary_name
        return reply

    def status(self) -> dict:
        return {"primary": display_name(self.primary_name), "primary_available": self.primary_available(),
                "last_error": self.last_error}


def _ollama(model: str, temperature: float):
    import httpx
    from langchain_ollama import ChatOllama
    headers = {"ngrok-skip-browser-warning": "1"}
    if token := os.environ.get("NARRATOR_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    return ChatOllama(model=model, temperature=temperature,
                      base_url=os.environ.get("NARRATOR_BASE_URL") or None,
                      client_kwargs={"headers": headers,
                                     "timeout": httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT)})


def _openai(model: str, temperature: float):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model, temperature=temperature, timeout=60)


def build_narrator(temperature: float = 0.0):
    from dotenv import load_dotenv
    load_dotenv()
    model = os.environ.get("NARRATOR_MODEL")
    if not model:
        raise RuntimeError("NARRATOR_MODEL is not set. Add it to .env.")
    if os.environ.get("NARRATOR_PROVIDER", "ollama") == "openai":
        return _openai(model, temperature)
    primary = _ollama(model, temperature)
    fallback_model = os.environ.get("NARRATOR_FALLBACK_MODEL")
    if not fallback_model:
        return primary
    return NarratorWithFallback(primary, _openai(fallback_model, temperature), primary_name=model)
