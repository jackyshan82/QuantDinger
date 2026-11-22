from inspect import unwrap
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import g

from app.services import codex_llm
from app.services.indicator_ai_generation import generate_indicator_code_candidate
from app.services.llm import LLMService


@pytest.fixture
def codex(monkeypatch):
    monkeypatch.setenv("CODEX_BRIDGE_TOKEN", "t" * 40)
    monkeypatch.setenv("CODEX_MODEL", "")
    monkeypatch.setattr("app.services.llm.load_addon_config", lambda: {"llm": {"provider": "codex"}})
    monkeypatch.setattr(LLMService, "get_api_key", lambda *_a: pytest.fail("Codex must not require an API key"))
    request = MagicMock(return_value={"content": 'rsi = df["close"]\n', "model": "test-codex"})
    monkeypatch.setattr(codex_llm, "bridge_request", request)
    return request


def generate(**kwargs):
    return generate_indicator_code_candidate(
        prompt="Use RSI and show Buy / Sell on the chart", existing="", context={},
        system_prompt="Generate a chart indicator", workspace_context=None,
        template_factory=lambda: pytest.fail("Never replace RSI with an EMA template"),
        logger=MagicMock(), **kwargs,
    )


def test_codex_indicator_generation_calls_login_provider_without_api_key(codex):
    code, plan = generate()
    assert "rsi" in code
    assert plan["executor"] == "model" and plan["provider"] == "codex"
    assert "RSI" in codex.call_args.args[1]["messages"][-1]["content"]


def test_empty_codex_response_cannot_be_replaced_with_unrelated_template(codex, monkeypatch):
    monkeypatch.setattr(LLMService, "call_llm_api", lambda *_a, **_kw: "")
    with pytest.raises(ValueError, match="indicator_ai_empty_response"):
        generate()


def test_unconfigured_codex_does_not_return_a_template(codex, monkeypatch):
    monkeypatch.delenv("CODEX_BRIDGE_TOKEN")
    with pytest.raises(ValueError, match="indicator_ai_not_configured"):
        generate()
    codex.assert_not_called()


def test_failed_generation_stream_never_publishes_or_persists_ema_template(app, monkeypatch):
    from app.routes import indicator as route

    monkeypatch.setattr("app.services.billing_service.get_billing_service", lambda: SimpleNamespace(
        check_and_consume=lambda **_kw: (True, "")))
    monkeypatch.setattr(route, "generate_indicator_code_candidate", MagicMock(side_effect=ValueError("provider unavailable")))
    monkeypatch.setattr(route, "_validate_indicator_code_internal", lambda _code: {"success": True, "hints": []})
    save = MagicMock()
    monkeypatch.setattr(route, "complete_indicator_ai_turn", save)
    with app.test_request_context("/api/indicator/aiGenerate", method="POST", json={"prompt": "RSI Buy Sell"}):
        g.user_id = 1
        response = unwrap(route.ai_generate)()
        body = "".join(response.response)
    assert "indicator_ai_generation_failed" in body
    assert '"content"' not in body and "Golden" not in body
    assert "[DONE]" in body
    save.assert_not_called()
