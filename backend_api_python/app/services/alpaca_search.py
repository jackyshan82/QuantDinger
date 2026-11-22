"""Account-scoped Alpaca news provider; general web queries use other providers."""

import re

from app.data_providers.alpaca_research import AlpacaResearch, account_available
from app.services.search_models import BaseSearchProvider, SearchResponse, SearchResult


class AlpacaNewsProvider(BaseSearchProvider):
    def __init__(self, user_id):
        super().__init__([], "Alpaca")
        self.user_id = user_id

    @property
    def is_available(self):
        return account_available(self.user_id)

    def search_symbol(self, symbol, max_results=5, days=7):
        try:
            rows = AlpacaResearch(self.user_id).news(symbol, limit=max_results, days=days)
            results = [SearchResult(title=row["headline"], snippet=row["summary"], url=row["url"],
                                    source=row["source"], published_date=row["datetime"]) for row in rows]
            return SearchResponse(query=symbol, results=results, provider=self.name, success=bool(results))
        except Exception:
            return SearchResponse(query=symbol, results=[], provider=self.name, success=False,
                                  error_message="alpacaResearch.newsUnavailable")

    def search(self, query, max_results=5, days=7):
        matched = re.search(r"(?:USStock:|\$)([A-Z][A-Z0-9.\-]{0,19})\b", query)
        if matched and re.search(r"\bnews\b|headlines|新闻", query, re.IGNORECASE):
            return self.search_symbol(matched.group(1), max_results, days)
        return SearchResponse(query=query, results=[], provider=self.name, success=False,
                              error_message="alpacaResearch.symbolSpecificNewsOnly")

    def _do_search(self, query, api_key, max_results, days=7):
        return self.search(query, max_results, days)
