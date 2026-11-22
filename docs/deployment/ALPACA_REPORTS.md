# Alpaca data for professional reports

Save one Alpaca account under your own exchange credentials. Professional
reports reuse that account without requiring a second global API key. Credentials
and cached responses are scoped to the owning user and account.

In **Settings → News and web search**, select **Alpaca** as the search provider.
Alpaca supplies symbol-specific US stock news from Benzinga. General web queries
continue through the other available search providers. In **Professional report
→ Data sources**, Alpaca appears as an active community provider; configured
status reflects the current user's saved account.

New US-stock reports collect stock prices, quotes, trades and historical bars;
symbol news; near-term option snapshots with available IV and Greeks; corporate
actions; and public security metadata. Existing financial statements and SEC
sources remain responsible for accounting fundamentals. Regenerate an existing
report to collect the new evidence.

Use these settings (`SEARCH_PROVIDER` is selected explicitly; the report feed defaults are in `.env.example`):

```dotenv
ALPACA_REPORT_ENABLED=true
ALPACA_REPORT_FEED=iex
ALPACA_OPTIONS_FEED=indicative
SEARCH_PROVIDER=alpaca
```

IEX covers one venue. Indicative option prices are not consolidated OPRA quotes;
their limitations are retained in report evidence. Option collection is bounded
to near-term contracts and reports its sample scope. Snapshot data does not
supply open interest or volume ratios, and these values are never fabricated.
SIP and OPRA require the account's corresponding entitlement.

All Alpaca requests here are read-only. Availability depends on credentials,
entitlements, rate limits and the network. Failed optional datasets remain empty
with collection status; price, bars and news can use existing fallback providers
with their actual provenance. No missing accounting metrics are filled with zeros.

Official references: [market data](https://docs.alpaca.markets/docs/about-market-data-api),
[news](https://docs.alpaca.markets/us/reference/news-3),
[option chain](https://docs.alpaca.markets/us/reference/optionchain).
