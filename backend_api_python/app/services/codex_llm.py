"""Client for a private Codex CLI bridge, without API-key fallback."""

import os

import requests


def configured() -> bool:
    return len(os.getenv("CODEX_BRIDGE_TOKEN", "")) >= 32


def bridge_request(path, payload=None, timeout=180):
    token = os.getenv("CODEX_BRIDGE_TOKEN", "")
    if len(token) < 32:
        raise ValueError("codexBridge.notConfigured")
    base = os.getenv("CODEX_BRIDGE_URL", "http://codex-bridge:8765").rstrip("/")
    # Internal authentication must never travel through a configured LLM proxy.
    with requests.Session() as session:
        session.trust_env = False
        try:
            response = session.request("GET" if payload is None else "POST", base + path,
                                       json=payload, headers={"Authorization": "Bearer " + token},
                                       timeout=(5, timeout + 10), allow_redirects=False)
        except requests.RequestException:
            raise ValueError("codexBridge.unavailable") from None
    if response.status_code != 200:
        raise ValueError(f"codexBridge.httpError:{response.status_code}")
    try:
        return response.json()
    except ValueError:
        raise ValueError("codexBridge.invalidResponse") from None
