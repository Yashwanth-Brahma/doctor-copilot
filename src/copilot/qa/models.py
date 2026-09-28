"""Models for the Q&A side (OpenAI by default). Names come from .env, with no guessed defaults
(a guessed model name failed silently once already; see narrate.default_llm).

    OPENAI_API_KEY=sk-...
    AGENT_MODEL=<a tool-calling model your account has, e.g. gpt-4.1-mini>
    GATE_MODEL=<a small cheap model; can be the same as AGENT_MODEL>
    AGENT_PROVIDER=openai          # or "ollama" to run the agent on a local model (e.g. MedGemma)

The provider is a setting, not hard-wired: a hospital that can't send records to an outside
API can run the same agent, tools and checker on a local model.
"""
import os


def _require(name: str) -> str:
    from dotenv import load_dotenv
    load_dotenv()
    return _env(name)


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set. Add it to .env.")
    return value


def agent_llm():
    from dotenv import load_dotenv
    load_dotenv()                                   # before reading AGENT_PROVIDER
    if os.environ.get("AGENT_PROVIDER", "openai") == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=_require("AGENT_MODEL"), temperature=0)
    from langchain_openai import ChatOpenAI
    _require("OPENAI_API_KEY")
    return ChatOpenAI(model=_require("AGENT_MODEL"), temperature=0, timeout=60)


def gate_llm():
    from langchain_openai import ChatOpenAI
    _require("OPENAI_API_KEY")
    return ChatOpenAI(model=_require("GATE_MODEL"), temperature=0, timeout=30)
