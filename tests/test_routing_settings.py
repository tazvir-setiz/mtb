from dataclasses import replace

import pytest

from app.ai_defaults import FALLBACK_MODEL, PRIMARY_MODEL
from app.config import load_settings, settings
from app.services.ai_settings import load_ai_settings, parse_domains, save_ai_value


def test_fresh_and_legacy_settings():
    defaults = replace(settings, ai_model=PRIMARY_MODEL, ai_fallback_model=FALLBACK_MODEL)
    assert load_ai_settings(defaults).model == PRIMARY_MODEL
    assert load_ai_settings(defaults).fallback_model == FALLBACK_MODEL
    save_ai_value("model", "legacy-model")
    assert load_ai_settings(defaults).model == "legacy-model"
    assert load_ai_settings(defaults).fallback_model == FALLBACK_MODEL


def test_database_precedence_and_explicit_disable(monkeypatch):
    monkeypatch.setenv("AI_FALLBACK_MODEL", "env-model")
    monkeypatch.setenv("NEWS_ALLOWED_DOMAINS", "tasnimnews.com")
    monkeypatch.setenv("NEWS_GROUNDING_ENABLED", "true")
    defaults = load_settings()
    assert load_ai_settings(defaults).fallback_model == "env-model"
    save_ai_value("fallback_model", "db-model")
    save_ai_value("news_grounding_enabled", "false")
    save_ai_value("news_allowed_domains", "iribnews.ir")
    loaded = load_ai_settings(defaults)
    assert loaded.fallback_model == "db-model"
    assert not loaded.news_grounding_enabled
    assert loaded.news_allowed_domains == ("iribnews.ir",)
    save_ai_value("fallback_model", "")
    assert load_ai_settings(defaults).fallback_model == ""


@pytest.mark.parametrize("value", ["https://farsnews.ir", "*.farsnews.ir", "127.0.0.1", "localhost", "farsnews.ir/path"])
def test_invalid_domains_fail_closed(value):
    assert parse_domains(value) == ()
    with pytest.raises(ValueError):
        save_ai_value("news_allowed_domains", value)
