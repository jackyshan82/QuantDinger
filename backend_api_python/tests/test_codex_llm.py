import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import codex_llm
from app.services.llm import LLMProvider, LLMService


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("CODEX_BRIDGE_TOKEN", "t" * 40)
    monkeypatch.setenv("CODEX_MODEL", "")
    monkeypatch.setenv("CODEX_TIMEOUT", "180")
    monkeypatch.setattr("app.services.llm.load_addon_config", lambda: {"llm": {"provider": "codex"}})
    return LLMService()


def test_codex_is_explicit_and_does_not_need_api_keys(provider, monkeypatch):
    monkeypatch.setattr(provider, "get_api_key", lambda *_args: pytest.fail("must not use API credentials"))
    request = MagicMock(return_value={"content": '{"ok":true}', "model": "test-model"})
    monkeypatch.setattr(codex_llm, "bridge_request", request)
    assert provider.provider == LLMProvider.CODEX
    assert provider.is_configured()
    assert provider.call_llm_api([{"role": "user", "content": "test"}], model="openai/old-model") == '{"ok":true}'
    assert request.call_args.args[1]["model"] == ""
    assert provider.last_provider_used == "codex"
    assert provider.last_model_used == "test-model"


def test_codex_failure_never_falls_back_to_paid_provider(provider, monkeypatch):
    monkeypatch.setattr(codex_llm, "bridge_request", MagicMock(side_effect=ValueError("codexBridge.unavailable")))
    monkeypatch.setattr(provider, "_try_alternative_providers", lambda *_a, **_k: pytest.fail("no fallback"))
    with pytest.raises(ValueError, match="codexBridge.unavailable"):
        provider.call_llm_api([{"role": "user", "content": "test"}])


def test_codex_stream_uses_same_login_provider(provider, monkeypatch):
    request = MagicMock(return_value={"content": "answer", "model": "test-model"})
    monkeypatch.setattr(codex_llm, "bridge_request", request)
    assert list(provider.stream_llm_api([{"role": "user", "content": "test"}])) == ["answer"]
    assert request.call_args.args[1]["json_mode"] is False


def test_bridge_client_does_not_proxy_or_redirect_subscription_requests(provider, monkeypatch):
    session = MagicMock()
    session.__enter__.return_value = session
    session.request.return_value = SimpleNamespace(status_code=200, json=lambda: {"content": "ok"})
    monkeypatch.setattr(codex_llm.requests, "Session", lambda: session)
    assert codex_llm.bridge_request("/generate", {"messages": []}) == {"content": "ok"}
    assert session.trust_env is False
    assert session.request.call_args.kwargs["allow_redirects"] is False
    session.request.return_value.status_code = 403
    with pytest.raises(ValueError, match="codexBridge.httpError:403"):
        codex_llm.bridge_request("/generate", {})


@pytest.fixture
def bridge():
    path = Path(__file__).resolve().parents[2] / "scripts" / "codex_bridge.py"
    spec = importlib.util.spec_from_file_location("test_codex_bridge", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_only_uses_chatgpt_auth_and_restricted_text_execution(bridge, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-inherit")
    monkeypatch.setenv("CODEX_API_KEY", "must-not-inherit")
    monkeypatch.setenv("CODEX_BRIDGE_TOKEN", "must-not-inherit")
    monkeypatch.setattr(bridge.subprocess, "run", lambda *_a, **_k:
                        SimpleNamespace(returncode=0, stdout="", stderr="Logged in using ChatGPT"))
    captured = {}

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            captured.update(command=command, **kwargs)
            Path(command[command.index("--output-last-message") + 1]).write_text(json.dumps({"response": '{"ok":true}'}))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def communicate(self, prompt=None, timeout=None):
            captured["prompt"] = prompt
            return None, "model: test-model\n"

    monkeypatch.setattr(bridge.subprocess, "Popen", Process)
    assert bridge.run_codex([{"role": "user", "content": "hello"}], json_mode=True) == {
        "content": '{"ok":true}', "model": "test-model",
    }
    command = captured["command"]
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert 'forced_login_method="chatgpt"' in command
    assert "--ignore-user-config" in command and "--ignore-rules" in command and "--ephemeral" in command
    assert not any("dangerously" in part for part in command)
    assert not any(key in captured["env"] for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_BRIDGE_TOKEN"))
    assert "hello" not in " ".join(command)
    assert not os.path.exists(captured["cwd"])


def test_cli_rejects_api_key_auth_before_generation(bridge, monkeypatch):
    monkeypatch.setattr(bridge.subprocess, "run", lambda *_a, **_k:
                        SimpleNamespace(returncode=0, stdout="", stderr="Logged in using an API key"))
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *_a, **_k: pytest.fail("must not generate"))
    with pytest.raises(RuntimeError, match="chatgptLoginRequired"):
        bridge.run_codex([{"role": "user", "content": "hello"}])


@pytest.mark.parametrize("messages,model", [([], ""), ([{"role": "user", "content": []}], ""),
                                           ([{"role": "invalid", "content": "text"}], ""),
                                           ([{"role": "user", "content": "hello"}], "--unsafe")])
def test_cli_rejects_unsupported_payloads(bridge, messages, model):
    with pytest.raises(ValueError):
        bridge.run_codex(messages, model=model)


def test_http_bridge_rejects_unauthorized_requests_before_invocation(bridge, monkeypatch):
    import threading
    import requests

    monkeypatch.setenv("CODEX_BRIDGE_TOKEN", "t" * 40)
    runner = MagicMock(return_value={"content": "ok", "model": "test-model"})
    monkeypatch.setattr(bridge, "run_codex", runner)
    server = bridge.ThreadingHTTPServer(("127.0.0.1", 0), bridge.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/generate"
    try:
        assert requests.post(url, json={"messages": []}, timeout=5).status_code == 401
        runner.assert_not_called()
        response = requests.post(url, json={"messages": [{"role": "user", "content": "hi"}]},
                                 headers={"Authorization": "Bearer " + "t" * 40}, timeout=5)
        assert response.status_code == 200 and response.json()["content"] == "ok"
    finally:
        server.shutdown()
        server.server_close()
