import pytest


@pytest.fixture(autouse=True)
def isolated_model_env(monkeypatch):
    """Tests never read the developer's .env or real keys."""
    monkeypatch.setenv("CODEVIVA_NO_DOTENV", "1")
    for var in ("LLM_PROVIDER", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(var, raising=False)
