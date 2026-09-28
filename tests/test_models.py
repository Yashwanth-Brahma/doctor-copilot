from langchain_core.messages import AIMessage

from copilot.briefing.narrate import default_llm, narrator_name
from copilot.briefing.narrator_llm import NarratorWithFallback, display_name


def clean_env(monkeypatch, **values):
    # every narrator variable set explicitly (empty = off), so a developer's .env can't leak in
    for k in ("NARRATOR_PROVIDER", "NARRATOR_MODEL", "NARRATOR_BASE_URL", "NARRATOR_TOKEN",
              "NARRATOR_FALLBACK_MODEL"):
        monkeypatch.setenv(k, values.get(k, ""))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")


def test_narrator_is_a_setting(monkeypatch):
    clean_env(monkeypatch, NARRATOR_PROVIDER="openai", NARRATOR_MODEL="gpt-4.1-mini")
    assert type(default_llm()).__name__ == "ChatOpenAI"
    assert narrator_name() == "gpt-4.1-mini"
    clean_env(monkeypatch, NARRATOR_PROVIDER="ollama", NARRATOR_MODEL="hf.co/unsloth/medgemma-4b-it-GGUF:Q5_K_M")
    assert type(default_llm()).__name__ == "ChatOllama"
    assert narrator_name() == "MedGemma"


def test_remote_medgemma_with_openai_fallback_from_env(monkeypatch):
    clean_env(monkeypatch, NARRATOR_PROVIDER="ollama", NARRATOR_MODEL="medgemma",
              NARRATOR_BASE_URL="https://x.ngrok-free.app", NARRATOR_TOKEN="secret",
              NARRATOR_FALLBACK_MODEL="gpt-4.1-mini")
    llm = default_llm()
    assert isinstance(llm, NarratorWithFallback)
    assert llm.primary.base_url == "https://x.ngrok-free.app"
    assert llm.primary.client_kwargs["headers"]["Authorization"] == "Bearer secret"


class Down:
    calls = 0

    def invoke(self, messages):
        Down.calls += 1
        raise ConnectionError("Mac is asleep")


class Model:
    def __init__(self, name):
        self.name = name

    def invoke(self, messages):
        return AIMessage("ok", response_metadata={"model": self.name})


def test_fallback_when_the_mac_is_unreachable_then_cooldown_then_retry():
    t = [0.0]
    Down.calls = 0
    n = NarratorWithFallback(Down(), Model("gpt-4.1-mini"), "medgemma", cooldown=300, clock=lambda: t[0])
    reply = n.invoke([])
    assert reply.response_metadata == {"model": "gpt-4.1-mini", "fallback_from": "medgemma"}
    n.invoke([])
    assert Down.calls == 1                       # cooling down: the Mac isn't tried again
    assert n.status()["primary_available"] is False and "asleep" in n.status()["last_error"]
    t[0] = 301
    n.invoke([])
    assert Down.calls == 2                       # tried again after the cooldown


def test_primary_used_when_up():
    n = NarratorWithFallback(Model("hf.co/unsloth/medgemma-4b-it-GGUF:Q5_K_M"), Model("gpt-4.1-mini"), "medgemma")
    assert display_name(n.invoke([]).response_metadata["model"]) == "MedGemma"
