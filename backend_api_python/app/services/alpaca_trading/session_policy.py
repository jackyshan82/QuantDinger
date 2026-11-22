"""Order eligibility during US equity pre-market and post-market sessions."""

from datetime import datetime, timezone

from app.services.market_schedule import is_equity_bar_close


def extended_order_options(market: str, order_type: str, protected: bool, now=None) -> dict:
    if market != "USStock":
        return {}
    current = now or datetime.now(timezone.utc)
    if is_equity_bar_close("USStock", current):
        return {}
    if not is_equity_bar_close("USStock", current, extended_hours=True):
        raise ValueError("alpaca_equity_session_closed")
    # Alpaca requires a DAY limit order. Never silently convert a market order
    # or remove broker-native bracket protection to make an order eligible.
    if order_type != "limit" or protected:
        raise ValueError("alpaca_extended_hours_requires_plain_limit_order")
    return {"extended_hours": True}
