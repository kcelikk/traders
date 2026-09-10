"""Çekirdekte kayan BTC-beta (K9 girdisi). Saf; araştırma koduyla aynı formül."""
from fbot.core.beta_tracker import BetaTracker
from fbot.research.beta import rolling_beta


def bars(sym, n, amp, ref="BTCUSDT"):
    out, p = [], 100.0
    for i in range(n):
        p *= 1 + amp * ((i % 7) - 3) / 1000
        out.append({"symbol": sym, "start_ms": i * 60_000, "close": p})
    return out


def test_matches_research_formula():
    t = BetaTracker(ref="BTCUSDT", window=50, min_n=10)
    btc, alt = bars("BTCUSDT", 80, 1.0), bars("ALTUSDT", 80, 2.0)
    for b, a in zip(btc, alt):
        t.on_bar(b["symbol"], b["start_ms"], b["close"])
        t.on_bar(a["symbol"], a["start_ms"], a["close"])
    assert t.beta("BTCUSDT") == 1.0
    b = t.beta("ALTUSDT")
    # log uzayında tam 2.0 değil (bileşik seri): yaklaşık; birebir kontrol araştırma formülüyle aşağıda
    assert b is not None and abs(b - 2.0) < 1e-4
    # araştırma fonksiyonuyla birebir
    import math
    rb = [math.log(btc[i]["close"] / btc[i - 1]["close"]) for i in range(1, 80)][-50:]
    ra = [math.log(alt[i]["close"] / alt[i - 1]["close"]) for i in range(1, 80)][-50:]
    assert abs(b - rolling_beta(rb, ra, min_n=10)) < 1e-9


def test_none_until_enough_history():
    t = BetaTracker(ref="BTCUSDT", window=50, min_n=30)
    for i, (b, a) in enumerate(zip(bars("BTCUSDT", 20, 1.0), bars("ALTUSDT", 20, 1.5))):
        t.on_bar("BTCUSDT", b["start_ms"], b["close"])
        t.on_bar("ALTUSDT", a["start_ms"], a["close"])
    assert t.beta("ALTUSDT") is None


def test_only_aligned_timestamps_are_used():
    """Eksik bar hizalamayı bozmamalı: ortak zaman damgası yoksa o an atlanır."""
    t = BetaTracker(ref="BTCUSDT", window=50, min_n=5)
    for i in range(40):
        t.on_bar("BTCUSDT", i * 60_000, 100 * (1 + 0.001 * (i % 5 - 2)))
        if i != 7:
            t.on_bar("ALTUSDT", i * 60_000, 50 * (1 + 0.002 * (i % 5 - 2)))
    b = t.beta("ALTUSDT")
    assert b is not None and abs(b - 2.0) < 0.2


def test_window_slides_and_memory_bounded():
    t = BetaTracker(ref="BTCUSDT", window=30, min_n=5)
    for i in range(500):
        t.on_bar("BTCUSDT", i * 60_000, 100 * (1 + 0.001 * (i % 5 - 2)))
        t.on_bar("ALTUSDT", i * 60_000, 50 * (1 + 0.001 * (i % 5 - 2)))
    assert len(t._rets["ALTUSDT"]) <= 30 and len(t._rets["BTCUSDT"]) <= 30
    assert t.beta("ALTUSDT") is not None


def test_unknown_symbol_and_ref_missing():
    t = BetaTracker(ref="BTCUSDT", window=30, min_n=5)
    assert t.beta("YOK") is None
    for i in range(20):
        t.on_bar("ALTUSDT", i * 60_000, 50 + i)
    assert t.beta("ALTUSDT") is None      # referans yok → bilinmiyor
