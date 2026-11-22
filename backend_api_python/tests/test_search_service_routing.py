from types import SimpleNamespace
from pathlib import Path
import ast

from app.services import search as search_module
from app.services.search_models import SearchResponse, SearchResult
from app.utils.config_loader import clear_config_cache


def _set_search_env(monkeypatch, **overrides):
    values = {
        "SEARCH_PROVIDER": "tavily",
        "SEARCH_MAX_RESULTS": "10",
        "TAVILY_API_KEYS": "",
        "SERPAPI_KEYS": "",
        "ALPHA_VANTAGE_API_KEY": "",
        "SEARCH_GOOGLE_API_KEY": "",
        "SEARCH_GOOGLE_CX": "",
        "SEARCH_SEARXNG_BASE_URL": "",
        "GDELT_MAX_RESULTS": "10",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    clear_config_cache()


def test_settings_schema_exposes_only_supported_search_providers():
    source = (Path(__file__).resolve().parents[1] / "app" / "routes" / "settings.py").read_text(encoding="utf-8")
    provider_fields = [
        node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Dict)
        and any(isinstance(key, ast.Constant) and key.value == 'key'
                and isinstance(value, ast.Constant) and value.value == 'SEARCH_PROVIDER'
                for key, value in zip(node.keys, node.values))
    ]
    assert len(provider_fields) == 1
    options = next(value for key, value in zip(provider_fields[0].keys, provider_fields[0].values)
                   if isinstance(key, ast.Constant) and key.value == 'options')
    values = [item['value'] if isinstance(item, dict) else item for item in ast.literal_eval(options)]
    assert values == ['alpaca', 'tavily', 'searxng', 'gdelt', 'serpapi', 'google', 'duckduckgo', 'none']
    assert "SEARCH_BING_API_KEY" not in source


def test_selected_provider_runs_first_then_registered_fallbacks(monkeypatch):
    _set_search_env(
        monkeypatch,
        SEARCH_PROVIDER="google",
        SEARCH_GOOGLE_API_KEY="google-key",
        SEARCH_GOOGLE_CX="google-cx",
        TAVILY_API_KEYS="tavily-key",
        SERPAPI_KEYS="serp-key",
        ALPHA_VANTAGE_API_KEY="alpha-key",
    )
    try:
        service = search_module.SearchService()
        assert [provider.name for provider in service._providers] == [
            "Google",
            "Tavily",
            "GDELT",
            "SerpAPI",
            "AlphaVantage",
            "DuckDuckGo",
        ]
    finally:
        clear_config_cache()


def test_global_result_limit_caps_every_fallback_attempt():
    calls = []

    def provider(name, succeeds):
        def run(query, max_results, days):
            calls.append((name, max_results))
            results = [SearchResult(name, "snippet", "https://example.com", name)] if succeeds else []
            return SearchResponse(query, results, name, success=succeeds)

        return SimpleNamespace(name=name, is_available=True, search=run)

    service = object.__new__(search_module.SearchService)
    service.max_results = 3
    service._providers = [provider("First", False), provider("Second", True)]

    response = service.search_with_fallback("query", max_results=10)

    assert response.provider == "Second"
    assert calls == [("First", 3), ("Second", 3)]


def test_gdelt_result_limit_is_effective(monkeypatch):
    _set_search_env(monkeypatch, GDELT_MAX_RESULTS="2")
    captured = {}

    def get(url, **kwargs):
        captured.update(kwargs.get("params") or {})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "articles": [
                    {"title": f"Article {index}", "url": f"https://example.com/{index}"}
                    for index in range(5)
                ]
            },
        )

    monkeypatch.setattr(search_module.requests, "get", get)
    try:
        response = search_module.GDELTSearchProvider()._do_search("query", "free", 10)
        assert response.success
        assert captured["maxrecords"] == 2
        assert len(response.results) == 2
    finally:
        clear_config_cache()
