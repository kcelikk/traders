from decimal import Decimal

from fbot.core.market import SymbolMarket


def trade(T, p, q, a):
    return {"e": "aggTrade", "E": T + 50, "s": "BTCUSDT", "a": a, "p": p, "q": q, "f": a, "l": a, "T": T, "m": False}


def test_bars_close_on_first_trade_of_next_bucket_using_T():
    m = SymbolMarket("BTCUSDT", bar_ms=60_000)
    out = []
    out += m.on_agg_trade(trade(60_000, "100", "1", 1))
    out += m.on_agg_trade(trade(90_000, "110", "2", 2))
    out += m.on_agg_trade(trade(119_999, "90", "1", 3))
    assert out == []                                   # kova henüz kapanmadı
    out += m.on_agg_trade(trade(120_000, "95", "1", 4))  # yeni kova → önceki bar kapanır
    assert len(out) == 1
    b = out[0]
    assert (b.start_ms, b.end_ms) == (60_000, 119_999)
    assert (b.open, b.high, b.low, b.close) == (Decimal("100"), Decimal("110"), Decimal("90"), Decimal("90"))
    assert b.volume == Decimal("4") and b.trades == 3


def test_gap_minutes_produce_no_bars():
    m = SymbolMarket("BTCUSDT", bar_ms=60_000)
    m.on_agg_trade(trade(0, "1", "1", 1))
    out = m.on_agg_trade(trade(300_000, "2", "1", 2))   # 5 dk sonra
    assert len(out) == 1 and out[0].start_ms == 0        # yalnızca dolu bar; boş dakikalar yok


def test_book_ticker_and_mark_price_update_view():
    m = SymbolMarket("BTCUSDT", bar_ms=60_000)
    m.on_book_ticker({"e": "bookTicker", "u": 5, "s": "BTCUSDT", "b": "99.5", "B": "1", "a": "100.5", "A": "2", "T": 1, "E": 2})
    m.on_mark_price({"e": "markPriceUpdate", "s": "BTCUSDT", "p": "100.0", "i": "99.9", "r": "0.0001", "T": 999, "E": 3})
    assert m.best_bid == Decimal("99.5") and m.best_ask == Decimal("100.5")
    assert m.mark_price == Decimal("100.0") and m.funding_rate == Decimal("0.0001") and m.next_funding_ms == 999
    assert m.book_update_id == 5
