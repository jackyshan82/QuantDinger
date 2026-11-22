from datetime import datetime

import pytest

from app.events.bar_clock import BarStreamKey, MarketBarCloseClock
from app.events.bus import InMemoryEventBus
from app.services.alpaca_trading.session_policy import extended_order_options
from app.services.market_schedule import is_equity_bar_close


@pytest.mark.parametrize("stamp,expected", [
    ("2026-11-12T09:00:00+00:00", False),
    ("2026-11-12T09:01:00+00:00", True),
    ("2026-11-12T13:00:00+00:00", True),
    ("2026-11-13T01:00:00+00:00", True),
    ("2026-11-13T01:01:00+00:00", False),
    ("2026-07-01T08:01:00+00:00", True),
    ("2026-07-03T13:00:00+00:00", False),
    ("2026-11-14T13:00:00+00:00", False),
    ("2026-11-27T22:00:00+00:00", True),
    ("2026-11-27T22:01:00+00:00", False),
])
def test_extended_calendar_boundaries(stamp, expected):
    assert is_equity_bar_close("USStock", datetime.fromisoformat(stamp), extended_hours=True) is expected


def test_premarket_clock_emits_once_without_fabricating_price_data():
    initial = datetime.fromisoformat("2026-11-12T10:00:30+00:00")
    bus = InMemoryEventBus()
    clock = MarketBarCloseClock(bus, now=lambda: initial, autostart=False)
    received = []
    key = BarStreamKey("alpaca", "USStock", "spot", "TQQQ", "TQQQ", "1m")
    subscription = clock.subscribe(key, received.append)
    boundary = datetime.fromisoformat("2026-11-12T10:01:01+00:00")
    assert clock.publish_due(boundary) == 1
    assert clock.publish_due(boundary) == 0
    assert len(received) == 1
    subscription.close()
    clock.close()


def test_extended_orders_keep_regular_and_crypto_behavior():
    pre = datetime.fromisoformat("2026-11-12T13:00:00+00:00")
    regular = datetime.fromisoformat("2026-11-12T15:00:00+00:00")
    assert extended_order_options("USStock", "limit", False, pre) == {"extended_hours": True}
    assert extended_order_options("USStock", "market", True, regular) == {}
    assert extended_order_options("crypto", "market", False, pre) == {}
    for kind, protected in [("market", False), ("limit", True)]:
        with pytest.raises(ValueError, match="plain_limit_order"):
            extended_order_options("USStock", kind, protected, pre)
    with pytest.raises(ValueError, match="session_closed"):
        extended_order_options("USStock", "limit", False, datetime.fromisoformat("2026-11-14T13:00:00+00:00"))
