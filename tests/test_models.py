from copilot.briefing.narrate import default_llm, narrator_name


def test_narrator_is_a_setting(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("NARRATOR_PROVIDER", "openai")
    monkeypatch.setenv("NARRATOR_MODEL", "gpt-4.1-mini")
    assert type(default_llm()).__name__ == "ChatOpenAI"
    assert narrator_name() == "gpt-4.1-mini"
    monkeypatch.setenv("NARRATOR_PROVIDER", "ollama")
    monkeypatch.setenv("NARRATOR_MODEL", "hf.co/unsloth/medgemma-4b-it-GGUF:Q5_K_M")
    assert type(default_llm()).__name__ == "ChatOllama"
    assert narrator_name() == "MedGemma"
