"""Geçmiş aggTrades → bar: çekirdek SymbolMarket ile bit-eşit olmalı; CSV ayrıştırma; funding/mark ekleme."""
from decimal import Decimal

from fbot.core.market import SymbolMarket
from fbot.research.history import agg_row_to_trade, attach_funding, attach_mark, bars_from_agg_rows

ROWS = [
    "3442572059,79075.9,0.007,8058762153,8058762154,1788825600170,true",
    "3442572060,79076.0,0.016,8058762155,8058762155,1788825600194,false",
    "3442572061,79070.0,0.010,8058762156,8058762156,1788825660001,true",   # yeni dakika → ilk bar kapanır
]


def test_row_parse_maps_to_stream_semantics():
    t = agg_row_to_trade(ROWS[0])
    assert t == {"e": "aggTrade", "a": 3442572059, "p": "79075.9", "q": "0.007", "T": 1788825600170, "m": True}


def test_history_bars_bit_equal_with_core():
    core = SymbolMarket("BTCUSDT", 60_000)
    expected = []
    for r in ROWS:
        expected += core.on_agg_trade(agg_row_to_trade(r))
    got = bars_from_agg_rows("BTCUSDT", ROWS, 60_000)
    assert got == expected
    assert got[0].volume == Decimal("0.023") and got[0].buy_volume == Decimal("0.016")


def test_attach_mark_and_funding():
    bars = [{"symbol": "X", "start_ms": 60_000, "end_ms": 119_999}]
    marks = {60_000: 100.5}
    attach_mark(bars, marks)
    assert bars[0]["mark"] == 100.5
    funding = [(100_000, 0.0001), (28_900_000, -0.0002)]  # (fundingTime, rate) artan
    attach_funding(bars, funding)
    assert bars[0]["next_funding_ms"] == 28_900_000 and bars[0]["funding_rate"] == -0.0002
    b2 = [{"symbol": "X", "start_ms": 0, "end_ms": 59_999}]
    attach_funding(b2, funding)
    assert b2[0]["next_funding_ms"] == 100_000 and b2[0]["funding_rate"] == 0.0001
